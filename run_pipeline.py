"""CLI entrypoint for WaterAInalytics IV pipeline (v0.3.0).

Example
-------
python run_pipeline.py --sites 01013500 02087500 --parameter 00065 --days 7
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from core.pipeline.iv_pipeline import run_iv_pipeline, write_pipeline_outputs
from core.cache.get_stations import update_usgs_station_cache


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run IV pipeline (download → validate → stats).")

    p.add_argument(
        "--sites",
        nargs="*",
        default=None,
        help="USGS site numbers (e.g., 01013500). If omitted, use --stations-csv.",
    )
    p.add_argument(
        "--stations-csv",
        default=None,
        help="Path to a stations CSV (must include monitoring_location_id starting with USGS-).",
    )
    p.add_argument(
        "--refresh-stations",
        action="store_true",
        help="Refresh the stations CSV from USGS OGC API before running (requires --stations-csv).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of sites when using --stations-csv.",
    )

    p.add_argument("--parameter", default="00065", help="USGS parameter code (e.g., 00065).")
    p.add_argument("--days", type=int, default=7, help="Window size in days (ending today UTC).")
    p.add_argument("--cache-root", default="iv_cache", help="Cache directory for daily Parquets.")
    p.add_argument(
        "--cleanup-days",
        type=int,
        default=30,
        help="Delete cache files older than N days before running (0 disables).",
    )
    p.add_argument(
        "--out-dir",
        default=str(Path("data") / "processed" / "iv"),
        help="Directory for pipeline outputs.",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="HTTP timeout (seconds) for USGS calls.",
    )

    return p.parse_args()


def _load_sites_from_csv(csv_path: str, limit: int | None) -> list[str]:
    df = pd.read_csv(csv_path)
    if "monitoring_location_id" not in df.columns:
        raise ValueError("stations-csv must contain 'monitoring_location_id' column")
    mids = df["monitoring_location_id"].astype(str)
    sites = [m.replace("USGS-", "").strip() for m in mids if m.startswith("USGS-")]
    # de-duplicate preserving order
    seen = set()
    uniq = []
    for s in sites:
        if s and s not in seen:
            uniq.append(s)
            seen.add(s)
    if limit is not None:
        uniq = uniq[: int(limit)]
    return uniq


def main() -> None:
    args = _parse_args()

    if (not args.sites) and (not args.stations_csv):
        raise SystemExit("Provide --sites ... OR --stations-csv ...")

    if args.refresh_stations and not args.stations_csv:
        raise SystemExit("--refresh-stations requires --stations-csv")

    if args.stations_csv and args.refresh_stations:
        update_usgs_station_cache(output_csv_path=args.stations_csv, polite_sleep_s=0.0)

    if args.sites:
        sites = [str(s).strip() for s in args.sites if str(s).strip()]
    else:
        sites = _load_sites_from_csv(args.stations_csv, args.limit)

    if not sites:
        raise SystemExit("No sites found to process.")

    cleanup_days = None if int(args.cleanup_days) <= 0 else int(args.cleanup_days)

    api_key = os.getenv("USGS_API_KEY")

    res = run_iv_pipeline(
        sites,
        parameter_code=str(args.parameter),
        days=int(args.days),
        cache_root=args.cache_root,
        cleanup_cache_older_than_days=cleanup_days,
        api_key=api_key,
        timeout=int(args.timeout),
    )

    # Deterministic-ish stem for outputs
    today = datetime.now(timezone.utc).date().isoformat()
    stem = f"usgs_iv__p{args.parameter}__days{args.days}__asof{today}__n{len(sites)}"

    paths = write_pipeline_outputs(res, out_dir=args.out_dir, stem=stem)

    print("\n=== Pipeline complete ===")
    print(f"Sites: {len(sites)}")
    print(f"Parameter: {args.parameter} | Days: {args.days}")
    if res.cleanup is not None:
        print(
            f"Cache cleanup: scanned={res.cleanup.scanned_files} "
            f"deleted_files={res.cleanup.deleted_files} deleted_dirs={res.cleanup.deleted_dirs} "
            f"bytes_freed={res.cleanup.bytes_freed}"
        )
    for k, v in paths.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
