"""End-to-end helpers for a minimal IV pipeline (v0.3.0).

This pipeline is designed to be callable from Streamlit *or* a CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from core.cache.get_station_timeseries import ensure_iv_window
from core.processing.iv_processing import validate_iv_df
from core.analysis.iv_indicators import basic_iv_statistics
from core.utils.fs_cache import cleanup_tree_older_than, CacheCleanupResult


@dataclass(frozen=True)
class PipelineResult:
    raw: pd.DataFrame
    cleaned: pd.DataFrame
    validation_reports: list
    stats: pd.DataFrame
    cleanup: CacheCleanupResult | None


def fetch_iv_for_sites(
    sites: Iterable[str],
    *,
    parameter_code: str,
    days: int,
    cache_root: str | Path = "iv_cache",
    api_key: Optional[str] = None,
    timeout: int = 60,
) -> pd.DataFrame:
    """Fetch/cached IV data for multiple sites and return a concatenated DataFrame."""
    frames: list[pd.DataFrame] = []
    for site in sites:
        df_site = ensure_iv_window(
            site,
            parameter_code,
            days=days,
            out_root=str(cache_root),
            api_key=api_key,
            timeout=timeout,
        )
        if df_site is None or df_site.empty:
            continue
        frames.append(df_site)
    if not frames:
        return pd.DataFrame(
            columns=["site_no", "parameter_code", "unit", "datetime_utc", "value", "date_utc"]
        )
    return pd.concat(frames, ignore_index=True)


def run_iv_pipeline(
    sites: Iterable[str],
    *,
    parameter_code: str = "00065",
    days: int = 7,
    cache_root: str | Path = "iv_cache",
    cleanup_cache_older_than_days: int | None = 30,
    api_key: Optional[str] = None,
    timeout: int = 60,
) -> PipelineResult:
    """Run the v0.3.0 minimal pipeline for IV data.

    Returns raw, cleaned, and basic descriptive stats.
    """
    cleanup_res = None
    if cleanup_cache_older_than_days is not None:
        cleanup_res = cleanup_tree_older_than(
            cache_root, older_than_days=int(cleanup_cache_older_than_days)
        )

    raw = fetch_iv_for_sites(
        sites,
        parameter_code=parameter_code,
        days=days,
        cache_root=cache_root,
        api_key=api_key,
        timeout=timeout,
    )

    # Validation per-site (for reporting)
    reports = []
    cleaned_frames: list[pd.DataFrame] = []
    if not raw.empty:
        for (site, pcode), g in raw.groupby(["site_no", "parameter_code"], dropna=False):
            g_clean, rep = validate_iv_df(g, drop_duplicate_timestamps=True)
            reports.append({"site_no": site, "parameter_code": pcode, **rep.__dict__})
            cleaned_frames.append(g_clean)

    cleaned = (
        pd.concat(cleaned_frames, ignore_index=True)
        if cleaned_frames
        else pd.DataFrame(columns=["site_no", "parameter_code", "unit", "datetime_utc", "value"])
    )

    stats = basic_iv_statistics(cleaned)

    return PipelineResult(
        raw=raw,
        cleaned=cleaned,
        validation_reports=reports,
        stats=stats,
        cleanup=cleanup_res,
    )


def write_pipeline_outputs(
    result: PipelineResult,
    *,
    out_dir: str | Path,
    stem: str,
) -> dict[str, str]:
    """Write pipeline outputs (Parquet + CSV) and return paths."""
    out_p = Path(out_dir)
    out_p.mkdir(parents=True, exist_ok=True)

    paths: dict[str, str] = {}

    raw_pq = out_p / f"{stem}__raw.parquet"
    result.raw.to_parquet(raw_pq, index=False)
    paths["raw_parquet"] = str(raw_pq)

    clean_pq = out_p / f"{stem}__clean.parquet"
    result.cleaned.to_parquet(clean_pq, index=False)
    paths["clean_parquet"] = str(clean_pq)

    stats_csv = out_p / f"{stem}__stats.csv"
    result.stats.to_csv(stats_csv, index=False)
    paths["stats_csv"] = str(stats_csv)

    val_csv = out_p / f"{stem}__validation.csv"
    pd.DataFrame(result.validation_reports).to_csv(val_csv, index=False)
    paths["validation_csv"] = str(val_csv)

    return paths
