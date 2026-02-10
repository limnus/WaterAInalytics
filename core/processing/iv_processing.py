"""Processing utilities for USGS Instantaneous Values (IV) time series.

Goals for v0.3.0
---------------
Provide a minimal, explicit processing layer:
  - schema normalization
  - basic validation (duplicates, ordering, dtype coercion)
  - optional temporal aggregation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

import pandas as pd


@dataclass(frozen=True)
class ValidationReport:
    rows_in: int
    rows_out: int
    n_null_datetime: int
    n_null_value: int
    n_duplicate_timestamps: int
    n_dropped_duplicates: int


def normalize_iv_df(df: pd.DataFrame) -> pd.DataFrame:
    """Return a normalized IV dataframe.

    Expected canonical columns:
      - site_no (str)
      - parameter_code (str)
      - unit (str|None)
      - datetime_utc (datetime64[ns, UTC])
      - value (float)

    This function is defensive: it will attempt to derive missing columns
    (e.g., legacy 'datetime').
    """
    if df is None or df.empty:
        return pd.DataFrame(
            columns=["site_no", "parameter_code", "unit", "datetime_utc", "value"]
        )

    out = df.copy()

    if "datetime_utc" not in out.columns:
        if "datetime" in out.columns:
            out["datetime_utc"] = out["datetime"]
        elif "datetime_iso" in out.columns:
            out["datetime_utc"] = out["datetime_iso"]
        else:
            raise ValueError("IV dataframe is missing datetime information.")

    out["datetime_utc"] = pd.to_datetime(out["datetime_utc"], utc=True, errors="coerce")

    if "value" not in out.columns:
        raise ValueError("IV dataframe is missing 'value' column.")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")

    # Optional columns
    if "site_no" not in out.columns:
        out["site_no"] = None
    if "parameter_code" not in out.columns:
        out["parameter_code"] = None
    if "unit" not in out.columns:
        out["unit"] = None

    # Keep only canonical columns (plus date_utc if present)
    cols = ["site_no", "parameter_code", "unit", "datetime_utc", "value"]
    keep = [c for c in cols if c in out.columns]
    out = out[keep]

    return out


def validate_iv_df(
    df: pd.DataFrame,
    *,
    drop_duplicate_timestamps: bool = True,
) -> tuple[pd.DataFrame, ValidationReport]:
    """Validate and lightly clean a normalized IV dataframe."""
    dfn = normalize_iv_df(df)

    rows_in = int(len(dfn))

    n_null_datetime = int(dfn["datetime_utc"].isna().sum())
    n_null_value = int(dfn["value"].isna().sum())

    # Drop null datetimes (cannot be used for time series)
    dfn = dfn.dropna(subset=["datetime_utc"]).copy()

    # Ensure ordering
    dfn = dfn.sort_values(["site_no", "parameter_code", "datetime_utc"]).reset_index(
        drop=True
    )

    n_dup = int(dfn.duplicated(subset=["site_no", "parameter_code", "datetime_utc"]).sum())
    dropped = 0

    if drop_duplicate_timestamps and n_dup:
        before = len(dfn)
        # Keep the last occurrence (often most recent / corrected)
        dfn = dfn.drop_duplicates(
            subset=["site_no", "parameter_code", "datetime_utc"], keep="last"
        ).reset_index(drop=True)
        dropped = int(before - len(dfn))

    rows_out = int(len(dfn))

    rep = ValidationReport(
        rows_in=rows_in,
        rows_out=rows_out,
        n_null_datetime=n_null_datetime,
        n_null_value=n_null_value,
        n_duplicate_timestamps=n_dup,
        n_dropped_duplicates=dropped,
    )
    return dfn, rep


AggFreq = Literal["H", "D", "M"]
AggFunc = Literal["mean", "sum", "min", "max", "median"]


def aggregate_iv(
    df: pd.DataFrame,
    *,
    freq: AggFreq = "D",
    how: AggFunc = "mean",
) -> pd.DataFrame:
    """Aggregate IV time series in UTC.

    - Uses pandas resample on datetime_utc.
    - Aggregates per (site_no, parameter_code).
    """
    dfn, _ = validate_iv_df(df, drop_duplicate_timestamps=True)
    if dfn.empty:
        return dfn

    # Resample requires datetime index
    out_frames: list[pd.DataFrame] = []
    for (site, pcode), g in dfn.groupby(["site_no", "parameter_code"], dropna=False):
        gg = g.set_index("datetime_utc").sort_index()
        if how == "mean":
            s = gg["value"].resample(freq).mean()
        elif how == "sum":
            s = gg["value"].resample(freq).sum()
        elif how == "min":
            s = gg["value"].resample(freq).min()
        elif how == "max":
            s = gg["value"].resample(freq).max()
        elif how == "median":
            s = gg["value"].resample(freq).median()
        else:
            raise ValueError(f"Unsupported aggregation: {how}")

        df_agg = s.reset_index().rename(columns={"datetime_utc": "datetime_utc", "value": "value"})
        df_agg["site_no"] = site
        df_agg["parameter_code"] = pcode
        # unit is not meaningful after aggregation if mixed; keep first non-null
        unit = g["unit"].dropna().astype(str)
        df_agg["unit"] = unit.iloc[0] if not unit.empty else None
        out_frames.append(df_agg[["site_no", "parameter_code", "unit", "datetime_utc", "value"]])

    out = pd.concat(out_frames, ignore_index=True)
    out = out.sort_values(["site_no", "parameter_code", "datetime_utc"]).reset_index(drop=True)
    return out
