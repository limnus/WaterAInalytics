"""Basic descriptive indicators for IV time series (v0.3.0).

This is intentionally lightweight: the goal is to provide a first analytic
layer that can be exported and used in reports.
"""

from __future__ import annotations

import pandas as pd

from core.processing.iv_processing import validate_iv_df


def basic_iv_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """Compute descriptive statistics per (site_no, parameter_code).

    Output columns:
      - site_no, parameter_code
      - n
      - min, p05, p25, median, mean, p75, p95, max
      - std
      - first_time_utc, last_time_utc
      - last_value
    """
    dfn, _ = validate_iv_df(df, drop_duplicate_timestamps=True)
    if dfn.empty:
        return pd.DataFrame(
            columns=[
                "site_no",
                "parameter_code",
                "n",
                "min",
                "p05",
                "p25",
                "median",
                "mean",
                "p75",
                "p95",
                "max",
                "std",
                "first_time_utc",
                "last_time_utc",
                "last_value",
            ]
        )

    def _q(x: pd.Series, q: float) -> float:
        return float(x.quantile(q)) if len(x) else float("nan")

    rows = []
    for (site, pcode), g in dfn.groupby(["site_no", "parameter_code"], dropna=False):
        v = g["value"].dropna()
        if v.empty:
            continue
        g_sorted = g.sort_values("datetime_utc")
        last_row = g_sorted.tail(1).iloc[0]

        rows.append(
            {
                "site_no": site,
                "parameter_code": pcode,
                "n": int(v.size),
                "min": float(v.min()),
                "p05": _q(v, 0.05),
                "p25": _q(v, 0.25),
                "median": _q(v, 0.50),
                "mean": float(v.mean()),
                "p75": _q(v, 0.75),
                "p95": _q(v, 0.95),
                "max": float(v.max()),
                "std": float(v.std(ddof=1)) if v.size > 1 else 0.0,
                "first_time_utc": g_sorted["datetime_utc"].iloc[0],
                "last_time_utc": g_sorted["datetime_utc"].iloc[-1],
                "last_value": float(last_row.get("value")) if pd.notna(last_row.get("value")) else float("nan"),
            }
        )

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["site_no", "parameter_code"]).reset_index(drop=True)
    return out
