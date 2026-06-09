from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.cache.get_station_timeseries import fetch_iv_timeseries
from core.processing.iv_processing import aggregate_iv, validate_iv_df

from paper_tests_scripts.paper_common import (
    derive_windows,
    ensure_dir,
    load_json,
    normalize_case,
    parse_utc,
    save_json,
)
from paper_tests_scripts.paper_paths import build_run_paths, ensure_run_paths


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Freeze source data and resolve paper benchmark cases.")
    ap.add_argument("--config", required=True, help="Path to paper_cases.json")
    ap.add_argument("--data-end-utc", default=None, help="Inclusive final hourly UTC timestamp.")
    return ap.parse_args()


def _resolve_data_end(config: Dict[str, Any], cli_data_end: str | None) -> str:
    data_end = cli_data_end or config.get("data_end_utc")
    if not data_end:
        raise ValueError("Provide --data-end-utc or set data_end_utc in config.")
    data_end_ts = parse_utc(data_end)
    now_utc = pd.Timestamp.now(tz="UTC").floor("h")
    if data_end_ts > now_utc:
        raise ValueError(
            f"data_end_utc={data_end_ts.isoformat()} is in the future relative to current UTC {now_utc.isoformat()}. "
            "Choose a completed hourly timestamp at or before current UTC."
        )
    return data_end_ts.isoformat()


def _build_raw_df(site_no: str, parameter_code: str, raw_points: List[tuple[str, float | None]]) -> pd.DataFrame:
    df = pd.DataFrame(raw_points or [], columns=["datetime_utc", "value"])
    if df.empty:
        return pd.DataFrame(columns=["site_no", "parameter_code", "unit", "datetime_utc", "value"])
    df["site_no"] = site_no
    df["parameter_code"] = parameter_code
    df["unit"] = None
    return df[["site_no", "parameter_code", "unit", "datetime_utc", "value"]]


def _filter_hourly_window(hourly_df: pd.DataFrame, start_utc: str, end_utc: str) -> pd.DataFrame:
    if hourly_df.empty:
        return hourly_df.copy()
    start = parse_utc(start_utc)
    end = parse_utc(end_utc)
    out = hourly_df.copy()
    out["datetime_utc"] = pd.to_datetime(out["datetime_utc"], utc=True, errors="coerce")
    out = out[(out["datetime_utc"] >= start) & (out["datetime_utc"] <= end)].copy()
    out = out.dropna(subset=["value"]).sort_values("datetime_utc").reset_index(drop=True)
    out["Datetime"] = out["datetime_utc"]
    out["Value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["Value"]).reset_index(drop=True)
    return out


def _compute_window_coverage(hourly_df: pd.DataFrame, start_utc: str, end_utc: str, expected_hours: int) -> tuple[int, float]:
    if hourly_df.empty:
        return 0, 0.0
    win = _filter_hourly_window(hourly_df, start_utc, end_utc)
    observed = int(len(win))
    coverage = float(observed / max(1, int(expected_hours)))
    return observed, coverage


def _build_candidate_origins(windows: Dict[str, Any], benchmark_cfg: Dict[str, Any]) -> List[pd.Timestamp]:
    eval_start = parse_utc(windows["eval_start_utc"])
    eval_end = parse_utc(windows["eval_end_utc"])
    horizon_h = int(benchmark_cfg["horizon_h"])
    stride_h = int(benchmark_cfg["origin_stride_h"])

    first_origin = eval_start - pd.Timedelta(hours=1)
    last_origin = eval_end - pd.Timedelta(hours=horizon_h)
    if last_origin < first_origin:
        return []
    origins = list(pd.date_range(first_origin, last_origin, freq=f"{stride_h}h", tz="UTC"))
    return origins


def _origin_is_valid(hourly_df: pd.DataFrame, origin: pd.Timestamp, benchmark_cfg: Dict[str, Any]) -> bool:
    hist_min = int(benchmark_cfg["min_history_points"])
    horizon_h = int(benchmark_cfg["horizon_h"])
    require_full = bool(benchmark_cfg.get("require_full_future_horizon", True))

    hist = hourly_df[hourly_df["Datetime"] <= origin].copy()
    if len(hist) < hist_min:
        return False

    fut_start = origin + pd.Timedelta(hours=1)
    fut_end = origin + pd.Timedelta(hours=horizon_h)
    future = hourly_df[(hourly_df["Datetime"] >= fut_start) & (hourly_df["Datetime"] <= fut_end)].copy()
    if require_full and len(future) != horizon_h:
        return False
    return not future.empty


def _resolve_case(case: Dict[str, Any], hourly_df: pd.DataFrame, windows: Dict[str, Any], benchmark_cfg: Dict[str, Any], paths: Dict[str, str]) -> Dict[str, Any]:
    expected_train_hours = int(windows["expected_train_hours"])
    expected_eval_hours = int(windows["expected_eval_hours"])

    observed_train_hours, train_coverage = _compute_window_coverage(
        hourly_df, windows["train_start_utc"], windows["train_end_utc"], expected_train_hours
    )
    observed_eval_hours, eval_coverage = _compute_window_coverage(
        hourly_df, windows["eval_start_utc"], windows["eval_end_utc"], expected_eval_hours
    )

    origins = _build_candidate_origins(windows, benchmark_cfg)
    valid_origins = [o for o in origins if _origin_is_valid(hourly_df, o, benchmark_cfg)]

    frozen_data_path = str(Path(paths["frozen_data_root"]) / f"{case['key']}.parquet")
    validation_path = str(Path(paths["frozen_data_root"]) / f"{case['key']}_validation.csv")

    status = "included"
    reason = "passed"

    if hourly_df.empty:
        status, reason = "excluded", "empty_after_hourly_aggregation"
    elif len(hourly_df) < int(benchmark_cfg["min_train_points"]):
        status, reason = "excluded", "insufficient_hourly_points"
    elif bool(benchmark_cfg.get("enforce_coverage_thresholds", False)) and train_coverage < float(benchmark_cfg["min_train_coverage"]):
        status, reason = "excluded", "insufficient_train_coverage"
    elif bool(benchmark_cfg.get("enforce_coverage_thresholds", False)) and eval_coverage < float(benchmark_cfg["min_eval_coverage"]):
        status, reason = "excluded", "insufficient_eval_coverage"
    elif len(valid_origins) < int(benchmark_cfg["min_valid_origins_per_case"]):
        status, reason = "excluded", "insufficient_valid_origins"

    return {
        "run_tag": None,
        "case_key": case["key"],
        "group": case["group"],
        "station_id": case["station_id"],
        "site_no": case["site_no"],
        "parameter_code": case["parameter_code"],
        "label": case["label"],
        "priority": case["priority"],
        "availability_policy": case["availability_policy"],
        "status": status,
        "reason": reason,
        "data_end_utc": windows["data_end_utc"],
        "train_start_utc": windows["train_start_utc"],
        "train_end_utc": windows["train_end_utc"],
        "eval_start_utc": windows["eval_start_utc"],
        "eval_end_utc": windows["eval_end_utc"],
        "n_points_raw": None,
        "n_points_validated": None,
        "n_points_hourly": int(len(hourly_df)),
        "expected_train_hours": expected_train_hours,
        "observed_train_hours": observed_train_hours,
        "train_coverage": round(train_coverage, 6),
        "expected_eval_hours": expected_eval_hours,
        "observed_eval_hours": observed_eval_hours,
        "eval_coverage": round(eval_coverage, 6),
        "candidate_origins": int(len(origins)),
        "valid_origins": int(len(valid_origins)),
        "min_history_points": int(benchmark_cfg["min_history_points"]),
        "horizon_h": int(benchmark_cfg["horizon_h"]),
        "origin_stride_h": int(benchmark_cfg["origin_stride_h"]),
        "frozen_data_path": frozen_data_path,
        "validation_path": validation_path,
    }


def main() -> None:
    args = parse_args()
    config = load_json(args.config)
    run_tag = str(config["run_tag"])
    data_end_utc = _resolve_data_end(config, args.data_end_utc)
    benchmark_cfg = dict(config["benchmark"])
    windows = derive_windows(data_end_utc, benchmark_cfg["train_days"], benchmark_cfg["eval_days"])

    paths = build_run_paths(config.get("output_root", "artifacts/paper_results"), run_tag)
    ensure_run_paths(paths)
    ensure_dir(paths["frozen_data_root"])

    resolution_rows: List[Dict[str, Any]] = []
    source_manifest_cases: List[Dict[str, Any]] = []

    fetch_start = windows["train_start_utc"]
    fetch_end = windows["eval_end_utc"]

    for raw_case in config["cases"]:
        case = normalize_case(raw_case)
        fetched = fetch_iv_timeseries(
            case["site_no"],
            parameter_codes=[case["parameter_code"]],
            period=None,
            startDT=fetch_start,
            endDT=fetch_end,
            api_key=None,
            timeout=60,
        )
        raw_points = list((fetched or {}).get(case["parameter_code"], []))
        raw_df = _build_raw_df(case["site_no"], case["parameter_code"], raw_points)
        validated_df, rep = validate_iv_df(raw_df)
        hourly_df = aggregate_iv(validated_df, freq=str(benchmark_cfg.get("aggregation_freq", "h")), how=str(benchmark_cfg.get("aggregation_how", "mean")))
        hourly_df = _filter_hourly_window(hourly_df, windows["train_start_utc"], windows["eval_end_utc"])

        row = _resolve_case(case, hourly_df, windows, benchmark_cfg, paths)
        row["run_tag"] = run_tag
        row["n_points_raw"] = int(len(raw_df))
        row["n_points_validated"] = int(rep.rows_out)
        resolution_rows.append(row)

        hourly_df.to_csv(row["validation_path"], index=False)
        if row["status"] == "included":
            hourly_df.to_parquet(row["frozen_data_path"], index=False)

        source_manifest_cases.append(
            {
                "case_key": case["key"],
                "site_no": case["site_no"],
                "parameter_code": case["parameter_code"],
                "fetched_points": int(len(raw_df)),
                "validated_points": int(rep.rows_out),
                "hourly_points": int(len(hourly_df)),
                "fetch_start_utc": fetch_start,
                "fetch_end_utc": fetch_end,
                "status": row["status"],
                "reason": row["reason"],
            }
        )

    report_path = Path(paths["run_root"]) / "case_resolution_report.csv"
    pd.DataFrame(resolution_rows).to_csv(report_path, index=False)
    source_manifest_path = Path(paths["run_root"]) / "source_manifest.json"
    save_json(
        source_manifest_path,
        {
            "run_tag": run_tag,
            "fetch_start_utc": fetch_start,
            "fetch_end_utc": fetch_end,
            "cases": source_manifest_cases,
        },
    )

    included = [r for r in resolution_rows if r["status"] == "included"]
    excluded = [r for r in resolution_rows if r["status"] != "included"]

    required_failed = [r for r in resolution_rows if r["priority"] == "required" and r["status"] != "included"]
    if required_failed:
        failed_labels = ", ".join(f"{r['case_key']} ({r['reason']})" for r in required_failed)
        raise RuntimeError(
            f"Required cases failed resolution: {failed_labels}. "
            f"Diagnostic report written to: {report_path}"
        )

    resolved_config = {
        "run_tag": run_tag,
        "data_end_utc": data_end_utc,
        "benchmark": benchmark_cfg,
        "models": config["models"],
        "derived_windows": windows,
        "paths": paths,
        "cases_included": included,
        "cases_excluded": excluded,
        "case_resolution_report_path": str(report_path),
        "source_manifest_path": str(source_manifest_path),
        "resolution_summary": {
            "n_candidate_cases": len(resolution_rows),
            "n_included_cases": len(included),
            "n_excluded_cases": len(excluded),
            "n_flow_cases_included": sum(1 for r in included if r["group"] == "core_flow"),
            "n_stage_cases_included": sum(1 for r in included if r["group"] == "core_stage"),
            "n_turbidity_cases_included": sum(1 for r in included if r["group"] == "supplement_turbidity"),
        },
    }
    save_json(Path(paths["run_root"]) / "resolved_config.json", resolved_config)

    print(f"Resolved config saved to: {Path(paths['run_root']) / 'resolved_config.json'}")
    print(f"Included cases: {len(included)} | Excluded cases: {len(excluded)}")


if __name__ == "__main__":
    main()
