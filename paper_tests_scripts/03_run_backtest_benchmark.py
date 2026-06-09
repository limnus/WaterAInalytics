from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.forecast_models.base import ForecastRequest
from core.forecast_models.chronos import ChronosModel
from core.forecast_models.output_schema import (
    StationForecastBundle,
    build_experiment_summary_artifact,
    build_forecast_run_artifact,
    experiment_summary_to_frame,
    forecast_output_to_rows,
    rows_to_frame,
)
from core.forecast_models.persistence import PersistenceModel
from core.forecast_models.pi import gaussian_residual_pi
from core.forecast_models.ridge import RidgeModel

from paper_tests_scripts.paper_common import load_json, parse_utc, stable_seed
from paper_tests_scripts.paper_metrics import mae, rmse, select_best_median_worst, skill_vs_baseline
from paper_tests_scripts.paper_paths import per_origin_dir, per_origin_family_dir


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run rolling-origin paper benchmark.")
    ap.add_argument("--config", required=True, help="Path to resolved_config.json")
    ap.add_argument("--debug-fail-fast", action="store_true", help="Raise the first prediction exception with full traceback instead of logging and continuing.")
    return ap.parse_args()


def _registry_by_case(registry_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {entry["case_key"]: entry for entry in registry_payload.get("registry") or []}


def _load_hourly_case(case_entry: Dict[str, Any]) -> pd.DataFrame:
    df = pd.read_parquet(case_entry["frozen_data_path"])
    df["Datetime"] = pd.to_datetime(df["Datetime"], utc=True, errors="coerce")
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce")
    df = df.dropna(subset=["Datetime", "Value"]).sort_values("Datetime").reset_index(drop=True)
    return df[["Datetime", "Value"]]


def _generate_origins(windows: Dict[str, Any], benchmark_cfg: Dict[str, Any]) -> List[pd.Timestamp]:
    eval_start = parse_utc(windows["eval_start_utc"])
    eval_end = parse_utc(windows["eval_end_utc"])
    horizon_h = int(benchmark_cfg["horizon_h"])
    stride_h = int(benchmark_cfg["origin_stride_h"])
    first_origin = eval_start - pd.Timedelta(hours=1)
    last_origin = eval_end - pd.Timedelta(hours=horizon_h)
    if last_origin < first_origin:
        return []
    return list(pd.date_range(first_origin, last_origin, freq=f"{stride_h}h", tz="UTC"))


def _slice_history(hourly_df: pd.DataFrame, origin: pd.Timestamp, min_history_points: int) -> pd.DataFrame:
    hist = hourly_df[hourly_df["Datetime"] <= origin].copy().sort_values("Datetime")
    if len(hist) < int(min_history_points):
        return pd.DataFrame(columns=["Datetime", "Value"])
    return hist.iloc[-int(min_history_points):].reset_index(drop=True)


def _align_actual_future(hourly_df: pd.DataFrame, origin: pd.Timestamp, horizon_h: int) -> pd.DataFrame:
    fut_start = origin + pd.Timedelta(hours=1)
    fut_end = origin + pd.Timedelta(hours=int(horizon_h))
    future = hourly_df[(hourly_df["Datetime"] >= fut_start) & (hourly_df["Datetime"] <= fut_end)].copy()
    future = future.sort_values("Datetime").reset_index(drop=True)
    if len(future) != int(horizon_h):
        return pd.DataFrame(columns=["Datetime", "Value"])
    expected_idx = pd.date_range(fut_start, periods=int(horizon_h), freq="h", tz="UTC")
    if not future["Datetime"].reset_index(drop=True).equals(pd.Series(expected_idx)):
        return pd.DataFrame(columns=["Datetime", "Value"])
    return future[["Datetime", "Value"]]


def _load_training_manifest(path_value: str | None) -> Dict[str, Any] | None:
    if not path_value:
        return None
    p = Path(path_value)
    if not p.exists():
        return None
    payload = json.loads(p.read_text(encoding="utf-8"))
    payload["_path"] = str(p)
    return payload


def _run_model_once(model_key: str, req: ForecastRequest, reg_entry: Dict[str, Any] | None, model_cfg: Dict[str, Any]) -> Tuple[Any, Dict[str, Any], Dict[str, Any] | None]:
    model_key = str(model_key)
    if model_key == "persistence":
        model = PersistenceModel()
        artifacts = {
            "noise": float(model_cfg.get("noise", 0.0)),
        }
        manifest = None
    elif model_key == "ridge":
        model = RidgeModel()
        artifacts = model.load_artifacts(Path(reg_entry["artifact_dir"]), req.station_id, req.parameter)
        manifest = _load_training_manifest(reg_entry.get("artifact_manifest_path"))
    else:
        model = ChronosModel()
        model.model_key = model_key
        if reg_entry is None:
            raise FileNotFoundError(f"Missing registry entry for {model_key}")
        artifacts = model.load_artifacts(Path(reg_entry["artifact_dir"]), req.station_id, req.parameter)
        model.model_id = str(artifacts.get("model_id", reg_entry.get("hf_model_id")))
        manifest = _load_training_manifest(reg_entry.get("artifact_manifest_path"))

    out = model.predict(req, artifacts)
    return out, artifacts, manifest


def _save_per_origin_bundle(
    out_root: Path,
    case: Dict[str, Any],
    model_key: str,
    requested_label: str,
    req: ForecastRequest,
    forecast_out,
    actual_future: pd.DataFrame,
    training_manifest: Dict[str, Any] | None,
    pi_level: float,
) -> Dict[str, str]:
    out_root.mkdir(parents=True, exist_ok=True)
    pi = gaussian_residual_pi(forecast_out.y_pred, sigma=float(forecast_out.sigma_residual), level=float(pi_level))
    bundle = StationForecastBundle(
        station_id=case["station_id"],
        parameter=case["parameter_code"],
        requested_model_key=model_key,
        requested_model_label=requested_label,
        used_model_key=model_key,
        used_model_label=requested_label,
        forecast_output=forecast_out,
        history_df=req.history,
        pi_low=pi.lower,
        pi_high=pi.upper,
    )
    rows = forecast_output_to_rows(bundle=bundle, horizon_h=req.horizon, interval_label=f"{int(pi_level*100)}% PI", pi_method_label="gaussian_residual")
    forecast_df = rows_to_frame(rows)
    forecast_csv_path = out_root / "forecast.csv"
    forecast_df.to_csv(forecast_csv_path, index=False)

    actual_csv_path = out_root / "actual_future.csv"
    actual_future.to_csv(actual_csv_path, index=False)

    run_artifact = build_forecast_run_artifact(
        station_bundles=[bundle],
        requested_model_key=model_key,
        requested_model_label=requested_label,
        parameter=case["parameter_code"],
        horizon_h=req.horizon,
        interval_label=f"{int(pi_level*100)}% PI",
        pi_method_label="gaussian_residual",
        session_seed=req.session_seed,
    )
    forecast_run_json_path = out_root / "forecast_run.json"
    forecast_run_json_path.write_text(json.dumps(run_artifact, indent=2, sort_keys=True), encoding="utf-8")

    training_manifests = {}
    if training_manifest is not None:
        key = f"{model_key}|{case['station_id']}|{case['parameter_code']}"
        training_manifests[key] = training_manifest
    summary_artifact = build_experiment_summary_artifact(run_artifact, training_manifests=training_manifests)
    experiment_summary_json_path = out_root / "experiment_summary.json"
    experiment_summary_json_path.write_text(json.dumps(summary_artifact, indent=2, sort_keys=True), encoding="utf-8")
    summary_df = experiment_summary_to_frame(summary_artifact)
    experiment_summary_csv_path = out_root / "experiment_summary.csv"
    summary_df.to_csv(experiment_summary_csv_path, index=False)

    return {
        "artifact_dir": str(out_root),
        "forecast_csv_path": str(forecast_csv_path),
        "forecast_run_json_path": str(forecast_run_json_path),
        "experiment_summary_json_path": str(experiment_summary_json_path),
        "experiment_summary_csv_path": str(experiment_summary_csv_path),
        "actual_future_csv_path": str(actual_csv_path),
    }


def _aggregate_case_metrics(origin_metrics_df: pd.DataFrame) -> pd.DataFrame:
    if origin_metrics_df.empty:
        return pd.DataFrame()
    group_cols = [
        "run_tag", "benchmark_mode", "case_key", "group", "station_id", "site_no",
        "parameter_code", "label", "model_family", "model_key", "hf_model_id", "is_primary_chronos"
    ]
    rows: List[Dict[str, Any]] = []
    for keys, g in origin_metrics_df.groupby(group_cols, dropna=False):
        keys = list(keys)
        row = {col: keys[i] for i, col in enumerate(group_cols)}
        row.update(
            {
                "n_origins_used": int(len(g)),
                "rmse_mean": float(g["rmse"].mean()),
                "rmse_median": float(g["rmse"].median()),
                "rmse_std": float(g["rmse"].std(ddof=0)) if len(g) else float("nan"),
                "mae_mean": float(g["mae"].mean()),
                "mae_median": float(g["mae"].median()),
                "mae_std": float(g["mae"].std(ddof=0)) if len(g) else float("nan"),
                "sigma_residual_mean": float(g["sigma_residual"].mean()),
            }
        )
        if "skill_vs_persistence" in g.columns:
            row["skill_vs_persistence_mean"] = float(g["skill_vs_persistence"].mean())
            row["skill_vs_persistence_median"] = float(g["skill_vs_persistence"].median())
        if "relative_to_chronos_base" in g.columns:
            row["relative_to_chronos_base_mean"] = float(g["relative_to_chronos_base"].mean())
            row["relative_to_chronos_base_median"] = float(g["relative_to_chronos_base"].median())
        rows.append(row)
    return pd.DataFrame(rows)


def _representative_windows_main(origin_metrics_df: pd.DataFrame) -> pd.DataFrame:
    if origin_metrics_df.empty:
        return pd.DataFrame()
    piv = origin_metrics_df.pivot_table(index=["case_key", "group", "station_id", "site_no", "parameter_code", "label", "origin_utc", "history_start_utc", "history_end_utc", "future_start_utc", "future_end_utc"], columns="model_key", values="rmse", aggfunc="first").reset_index()
    for col in ["persistence", "ridge", "chronos-base"]:
        if col not in piv.columns:
            piv[col] = np.nan
    piv["difficulty_score"] = piv[["persistence", "ridge", "chronos-base"]].mean(axis=1)
    rows = []
    for case_key, g in piv.groupby("case_key"):
        sel = select_best_median_worst(g[[
            "case_key", "group", "station_id", "site_no", "parameter_code", "label", "origin_utc",
            "history_start_utc", "history_end_utc", "future_start_utc", "future_end_utc",
            "difficulty_score", "persistence", "ridge", "chronos-base"
        ]].rename(columns={"persistence": "persistence_rmse", "ridge": "ridge_rmse", "chronos-base": "chronos_base_rmse"}))
        rows.append(sel)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _representative_windows_family(origin_metrics_df: pd.DataFrame, enabled_flavors: List[str]) -> pd.DataFrame:
    if origin_metrics_df.empty:
        return pd.DataFrame()
    piv = origin_metrics_df.pivot_table(index=["case_key", "group", "station_id", "site_no", "parameter_code", "label", "origin_utc", "history_start_utc", "history_end_utc", "future_start_utc", "future_end_utc"], columns="model_key", values="rmse", aggfunc="first").reset_index()
    for col in enabled_flavors:
        if col not in piv.columns:
            piv[col] = np.nan
    piv["difficulty_score"] = piv[enabled_flavors].mean(axis=1)
    rename_map = {k: k.replace("-", "_") + "_rmse" for k in enabled_flavors}
    rows = []
    for case_key, g in piv.groupby("case_key"):
        sel = select_best_median_worst(g.rename(columns=rename_map)[[
            "case_key", "group", "station_id", "site_no", "parameter_code", "label", "origin_utc",
            "history_start_utc", "history_end_utc", "future_start_utc", "future_end_utc", "difficulty_score", *rename_map.values()
        ]])
        rows.append(sel)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main() -> None:
    args = parse_args()
    resolved = load_json(args.config)
    registry_payload = load_json(Path(resolved["paths"]["trained_models_root"]) / "training_registry.json")
    registry_by_case = _registry_by_case(registry_payload)
    windows = dict(resolved["derived_windows"])
    benchmark_cfg = dict(resolved["benchmark"])
    models_cfg = dict(resolved["models"])
    chronos_cfg = dict(models_cfg.get("chronos_family") or {})
    primary_chronos_key = str(chronos_cfg.get("primary_model_key") or "chronos-base")
    enabled_flavors = [str(f["model_key"]) for f in chronos_cfg.get("flavors") or [] if bool(f.get("enabled", False))]

    origins = _generate_origins(windows, benchmark_cfg)
    main_origin_rows: List[Dict[str, Any]] = []
    main_skipped_rows: List[Dict[str, Any]] = []
    family_origin_rows: List[Dict[str, Any]] = []
    family_skipped_rows: List[Dict[str, Any]] = []

    for case in resolved.get("cases_included") or []:
        hourly = _load_hourly_case(case)
        reg_case = registry_by_case.get(case["case_key"])
        if reg_case is None:
            raise RuntimeError(f"Case missing from training registry: {case['case_key']}")

        for origin in origins:
            history = _slice_history(hourly, origin, int(benchmark_cfg["min_history_points"]))
            future = _align_actual_future(hourly, origin, int(benchmark_cfg["horizon_h"]))
            history_start = history["Datetime"].iloc[0].isoformat() if not history.empty else None
            history_end = history["Datetime"].iloc[-1].isoformat() if not history.empty else None
            future_start = future["Datetime"].iloc[0].isoformat() if not future.empty else None
            future_end = future["Datetime"].iloc[-1].isoformat() if not future.empty else None
            origin_iso = pd.Timestamp(origin).isoformat()

            if history.empty:
                main_skipped_rows.append({
                    "run_tag": resolved["run_tag"], "benchmark_mode": "main_benchmark", "case_key": case["case_key"], "group": case["group"],
                    "station_id": case["station_id"], "site_no": case["site_no"], "parameter_code": case["parameter_code"], "label": case["label"],
                    "origin_utc": origin_iso, "reason": "insufficient_history_points", "history_start_utc": history_start, "history_end_utc": history_end,
                    "future_start_utc": future_start, "future_end_utc": future_end, "n_history_points": 0, "n_future_points": int(len(future)),
                })
                continue
            if future.empty:
                main_skipped_rows.append({
                    "run_tag": resolved["run_tag"], "benchmark_mode": "main_benchmark", "case_key": case["case_key"], "group": case["group"],
                    "station_id": case["station_id"], "site_no": case["site_no"], "parameter_code": case["parameter_code"], "label": case["label"],
                    "origin_utc": origin_iso, "reason": "incomplete_future_horizon", "history_start_utc": history_start, "history_end_utc": history_end,
                    "future_start_utc": future_start, "future_end_utc": future_end, "n_history_points": int(len(history)), "n_future_points": 0,
                })
                continue

            req = ForecastRequest(
                station_id=case["station_id"],
                parameter=case["parameter_code"],
                history=history,
                horizon=int(benchmark_cfg["horizon_h"]),
                freq="h",
                session_seed=stable_seed(resolved["run_tag"], case["case_key"], origin_iso),
            )

            # Main benchmark: Persistence, Ridge, Primary Chronos
            main_results: Dict[str, Dict[str, Any]] = {}
            main_order = ["persistence", "ridge", primary_chronos_key]
            main_failed_reason = None
            main_failed_model = None
            main_failed_detail = None
            for mk in main_order:
                try:
                    reg_entry = None
                    requested_label = mk.replace("-", " ").title()
                    if mk == "ridge":
                        reg_entry = reg_case.get("ridge")
                        if reg_entry.get("status") != "trained":
                            raise FileNotFoundError("ridge artifacts unavailable")
                        model_cfg = dict(models_cfg.get("ridge") or {})
                    elif mk == "persistence":
                        model_cfg = dict(models_cfg.get("persistence") or {})
                    else:
                        reg_entry = (reg_case.get("chronos_family") or {}).get("flavors", {}).get(mk)
                        if not reg_entry or reg_entry.get("status") != "trained":
                            raise FileNotFoundError(f"{mk} artifacts unavailable")
                        model_cfg = dict(chronos_cfg)
                    out, artifacts, manifest = _run_model_once(mk, req, reg_entry, model_cfg)
                    out_dir = per_origin_dir(resolved["paths"]["backtests_root"], case["case_key"], mk, origin_iso)
                    files = _save_per_origin_bundle(
                        out_root=Path(out_dir),
                        case=case,
                        model_key=mk,
                        requested_label=requested_label,
                        req=req,
                        forecast_out=out,
                        actual_future=future,
                        training_manifest=manifest,
                        pi_level=float(model_cfg.get("pi_level", 0.8)),
                    )
                    main_results[mk] = {
                        "out": out,
                        "manifest": manifest,
                        **files,
                    }
                except Exception as exc:
                    detail = traceback.format_exc()
                    if args.debug_fail_fast:
                        print(f"First main benchmark prediction exception | case={case['case_key']} model={mk} origin={origin_iso}", file=sys.stderr)
                        print(detail, file=sys.stderr)
                        raise
                    main_failed_reason = f"{mk}: {exc}"
                    main_failed_model = mk
                    main_failed_detail = detail
                    break

            if main_failed_reason is not None:
                main_skipped_rows.append({
                    "run_tag": resolved["run_tag"], "benchmark_mode": "main_benchmark", "case_key": case["case_key"], "group": case["group"],
                    "station_id": case["station_id"], "site_no": case["site_no"], "parameter_code": case["parameter_code"], "label": case["label"],
                    "origin_utc": origin_iso, "model_key": main_failed_model, "reason": "prediction_exception", "exception_detail": main_failed_reason, "traceback": main_failed_detail, "history_start_utc": history_start, "history_end_utc": history_end,
                    "future_start_utc": future_start, "future_end_utc": future_end, "n_history_points": int(len(history)), "n_future_points": int(len(future)),
                })
            else:
                persistence_rmse = rmse(future["Value"], main_results["persistence"]["out"].y_pred.values)
                for mk in main_order:
                    pred = main_results[mk]["out"].y_pred.values
                    row = {
                        "run_tag": resolved["run_tag"],
                        "benchmark_mode": "main_benchmark",
                        "case_key": case["case_key"],
                        "group": case["group"],
                        "station_id": case["station_id"],
                        "site_no": case["site_no"],
                        "parameter_code": case["parameter_code"],
                        "label": case["label"],
                        "model_family": "baseline" if mk == "persistence" else ("ridge" if mk == "ridge" else "chronos"),
                        "model_key": mk,
                        "hf_model_id": None if mk in {"persistence", "ridge"} else (reg_case.get("chronos_family") or {}).get("flavors", {}).get(mk, {}).get("hf_model_id"),
                        "is_primary_chronos": mk == primary_chronos_key,
                        "origin_utc": origin_iso,
                        "history_start_utc": history_start,
                        "history_end_utc": history_end,
                        "future_start_utc": future_start,
                        "future_end_utc": future_end,
                        "n_history_points": int(len(history)),
                        "n_future_points": int(len(future)),
                        "rmse": rmse(future["Value"], pred),
                        "mae": mae(future["Value"], pred),
                        "sigma_residual": float(main_results[mk]["out"].sigma_residual),
                        "skill_vs_persistence": 0.0 if mk == "persistence" else skill_vs_baseline(rmse(future["Value"], pred), persistence_rmse),
                        "artifact_dir": main_results[mk]["artifact_dir"],
                        "forecast_csv_path": main_results[mk]["forecast_csv_path"],
                        "forecast_run_json_path": main_results[mk]["forecast_run_json_path"],
                        "experiment_summary_json_path": main_results[mk]["experiment_summary_json_path"],
                        "experiment_summary_csv_path": main_results[mk]["experiment_summary_csv_path"],
                    }
                    main_origin_rows.append(row)

            # Chronos family benchmark
            family_results: Dict[str, Dict[str, Any]] = {}
            family_failed = None
            family_failed_model = None
            family_failed_detail = None
            for mk in enabled_flavors:
                try:
                    reg_entry = (reg_case.get("chronos_family") or {}).get("flavors", {}).get(mk)
                    if not reg_entry or reg_entry.get("status") != "trained":
                        raise FileNotFoundError(f"{mk} artifacts unavailable")
                    out, artifacts, manifest = _run_model_once(mk, req, reg_entry, chronos_cfg)
                    out_dir = per_origin_family_dir(resolved["paths"]["backtests_chronos_family_root"], case["case_key"], mk, origin_iso)
                    files = _save_per_origin_bundle(
                        out_root=Path(out_dir),
                        case=case,
                        model_key=mk,
                        requested_label=mk.replace("-", " ").title(),
                        req=req,
                        forecast_out=out,
                        actual_future=future,
                        training_manifest=manifest,
                        pi_level=float(chronos_cfg.get("pi_level", 0.8)),
                    )
                    family_results[mk] = {"out": out, "manifest": manifest, **files}
                except Exception as exc:
                    detail = traceback.format_exc()
                    if args.debug_fail_fast:
                        print(f"First Chronos-family prediction exception | case={case['case_key']} model={mk} origin={origin_iso}", file=sys.stderr)
                        print(detail, file=sys.stderr)
                        raise
                    family_failed = f"{mk}: {exc}"
                    family_failed_model = mk
                    family_failed_detail = detail
                    break

            if family_failed is not None:
                family_skipped_rows.append({
                    "run_tag": resolved["run_tag"], "benchmark_mode": "chronos_family_benchmark", "case_key": case["case_key"], "group": case["group"],
                    "station_id": case["station_id"], "site_no": case["site_no"], "parameter_code": case["parameter_code"], "label": case["label"],
                    "model_key": family_failed_model, "hf_model_id": None, "origin_utc": origin_iso, "reason": "prediction_exception", "exception_detail": family_failed, "traceback": family_failed_detail,
                    "history_start_utc": history_start, "history_end_utc": history_end, "future_start_utc": future_start, "future_end_utc": future_end,
                    "n_history_points": int(len(history)), "n_future_points": int(len(future)),
                })
            else:
                base_rmse = rmse(future["Value"], family_results[primary_chronos_key]["out"].y_pred.values)
                for mk in enabled_flavors:
                    pred = family_results[mk]["out"].y_pred.values
                    family_origin_rows.append(
                        {
                            "run_tag": resolved["run_tag"],
                            "benchmark_mode": "chronos_family_benchmark",
                            "case_key": case["case_key"],
                            "group": case["group"],
                            "station_id": case["station_id"],
                            "site_no": case["site_no"],
                            "parameter_code": case["parameter_code"],
                            "label": case["label"],
                            "model_family": "chronos",
                            "model_key": mk,
                            "hf_model_id": (reg_case.get("chronos_family") or {}).get("flavors", {}).get(mk, {}).get("hf_model_id"),
                            "is_primary_chronos": mk == primary_chronos_key,
                            "origin_utc": origin_iso,
                            "history_start_utc": history_start,
                            "history_end_utc": history_end,
                            "future_start_utc": future_start,
                            "future_end_utc": future_end,
                            "n_history_points": int(len(history)),
                            "n_future_points": int(len(future)),
                            "rmse": rmse(future["Value"], pred),
                            "mae": mae(future["Value"], pred),
                            "sigma_residual": float(family_results[mk]["out"].sigma_residual),
                            "relative_to_chronos_base": 0.0 if mk == primary_chronos_key else (rmse(future["Value"], pred) - base_rmse),
                            "artifact_dir": family_results[mk]["artifact_dir"],
                            "forecast_csv_path": family_results[mk]["forecast_csv_path"],
                            "forecast_run_json_path": family_results[mk]["forecast_run_json_path"],
                            "experiment_summary_json_path": family_results[mk]["experiment_summary_json_path"],
                            "experiment_summary_csv_path": family_results[mk]["experiment_summary_csv_path"],
                        }
                    )

    main_origin_df = pd.DataFrame(main_origin_rows)
    main_case_df = _aggregate_case_metrics(main_origin_df)
    rep_main_df = _representative_windows_main(main_origin_df)
    main_skip_df = pd.DataFrame(main_skipped_rows)

    backtests_root = Path(resolved["paths"]["backtests_root"])
    backtests_root.mkdir(parents=True, exist_ok=True)
    main_origin_df.to_csv(backtests_root / "origin_metrics.csv", index=False)
    main_case_df.to_csv(backtests_root / "case_model_metrics.csv", index=False)
    rep_main_df.to_csv(backtests_root / "representative_windows.csv", index=False)
    main_skip_df.to_csv(backtests_root / "skipped_origins.csv", index=False)

    family_origin_df = pd.DataFrame(family_origin_rows)
    family_case_df = _aggregate_case_metrics(family_origin_df)
    if not family_case_df.empty:
        summary_df = pd.read_csv(Path(resolved["paths"]["trained_models_root"]) / "model_training_summary.csv")
        timing = summary_df[["case_key", "model_key", "training_wallclock_s"]].drop_duplicates()
        family_case_df = family_case_df.merge(timing, on=["case_key", "model_key"], how="left")
    rep_family_df = _representative_windows_family(family_origin_df, enabled_flavors) if enabled_flavors else pd.DataFrame()
    family_skip_df = pd.DataFrame(family_skipped_rows)

    family_root = Path(resolved["paths"]["backtests_chronos_family_root"])
    family_root.mkdir(parents=True, exist_ok=True)
    family_origin_df.to_csv(family_root / "chronos_family_origin_metrics.csv", index=False)
    family_case_df.to_csv(family_root / "chronos_family_case_metrics.csv", index=False)
    rep_family_df.to_csv(family_root / "chronos_family_representative_windows.csv", index=False)
    family_skip_df.to_csv(family_root / "chronos_family_skipped_origins.csv", index=False)

    print(f"Main benchmark origins: {len(main_origin_df)} rows")
    print(f"Chronos family origins: {len(family_origin_df)} rows")


if __name__ == "__main__":
    main()
