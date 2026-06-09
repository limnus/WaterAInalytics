from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.forecast_models.chronos import optimize_chronos_context, save_chronos_artifacts
from core.forecast_models.ridge import save_ridge_artifacts, tune_ridge_alpha

from paper_tests_scripts.paper_common import load_json, parse_utc, save_json


ALLOWED_STATUS = {"trained", "failed", "disabled"}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Train Ridge and Chronos family artifacts for included paper cases.")
    ap.add_argument("--config", required=True, help="Path to resolved_config.json")
    return ap.parse_args()


def _load_train_df(case_entry: Dict[str, Any], windows: Dict[str, Any]) -> pd.DataFrame:
    df = pd.read_parquet(case_entry["frozen_data_path"])
    df["Datetime"] = pd.to_datetime(df["Datetime"], utc=True, errors="coerce")
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce")
    df = df.dropna(subset=["Datetime", "Value"]).sort_values("Datetime").reset_index(drop=True)
    start = parse_utc(windows["train_start_utc"])
    end = parse_utc(windows["train_end_utc"])
    df = df[(df["Datetime"] >= start) & (df["Datetime"] <= end)].reset_index(drop=True)
    return df[["Datetime", "Value"]]


def _write_chronos_training_manifest(artifacts_dir: Path, artifacts: Dict[str, Any]) -> str:
    payload = dict(artifacts)
    payload.setdefault("schema_version", "chronos_training_manifest_v1")
    payload.setdefault("trained_at_utc", datetime.now(timezone.utc).isoformat())
    out_path = artifacts_dir / "training_manifest.json"
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(out_path)


def main() -> None:
    args = parse_args()
    resolved = load_json(args.config)
    paths = dict(resolved["paths"])
    windows = dict(resolved["derived_windows"])
    models_cfg = dict(resolved["models"])
    trained_models_root = Path(paths["trained_models_root"])
    trained_models_root.mkdir(parents=True, exist_ok=True)

    ridge_cfg = dict(models_cfg.get("ridge") or {})
    chronos_cfg = dict(models_cfg.get("chronos_family") or {})
    primary_chronos_key = str(chronos_cfg.get("primary_model_key") or "chronos-base")

    summary_rows: List[Dict[str, Any]] = []
    registry_entries: List[Dict[str, Any]] = []
    fatal_failures: List[str] = []

    for case in resolved.get("cases_included") or []:
        hist = _load_train_df(case, windows)
        if hist.empty:
            fatal_failures.append(f"{case['case_key']}: empty training history")
            continue

        case_registry: Dict[str, Any] = {
            "case_key": case["case_key"],
            "group": case["group"],
            "station_id": case["station_id"],
            "site_no": case["site_no"],
            "parameter_code": case["parameter_code"],
            "label": case["label"],
            "source_frozen_data_path": case["frozen_data_path"],
        }

        # Ridge
        ridge_dir = trained_models_root / "ridge" / case["station_id"] / case["parameter_code"]
        ridge_result: Dict[str, Any]
        ridge_start = time.perf_counter()
        try:
            ridge_artifacts = tune_ridge_alpha(
                hist,
                alphas=[float(x) for x in ridge_cfg.get("alphas") or [0.1, 1.0, 10.0, 100.0]],
                lags=[int(x) for x in ridge_cfg.get("lags") or [1, 2, 3, 6, 12, 24]],
                roll_means=[int(x) for x in ridge_cfg.get("roll_means") or [3, 6, 12, 24]],
                valid_frac=float(ridge_cfg.get("valid_frac", 0.2)),
                min_valid=int(ridge_cfg.get("min_valid", 24)),
            )
            save_ridge_artifacts(
                ridge_dir,
                ridge_artifacts,
                station_id=case["station_id"],
                parameter=case["parameter_code"],
                model_key="ridge",
                generated_by="paper_tests_scripts.02_train_ridge_and_chronos",
            )
            ridge_manifest_path = str(ridge_dir / "training_manifest.json")
            ridge_result = {
                "status": "trained",
                "artifact_dir": str(ridge_dir),
                "artifact_manifest_path": ridge_manifest_path,
                "selected_alpha": float(ridge_artifacts.get("best_alpha", ridge_artifacts.get("alpha", 1.0))),
                "validation_metric_name": "rmse_valid",
                "validation_metric_value": float(ridge_artifacts.get("best_rmse_valid", ridge_artifacts.get("rmse_valid", float("nan")))),
                "training_wallclock_s": round(time.perf_counter() - ridge_start, 6),
            }
        except Exception as exc:
            ridge_result = {
                "status": "failed",
                "artifact_dir": str(ridge_dir),
                "artifact_manifest_path": None,
                "selected_alpha": None,
                "validation_metric_name": "rmse_valid",
                "validation_metric_value": None,
                "training_wallclock_s": round(time.perf_counter() - ridge_start, 6),
                "error": str(exc),
            }
            fatal_failures.append(f"{case['case_key']}: ridge failed: {exc}")

        summary_rows.append(
            {
                "run_tag": resolved["run_tag"],
                "case_key": case["case_key"],
                "group": case["group"],
                "station_id": case["station_id"],
                "site_no": case["site_no"],
                "parameter_code": case["parameter_code"],
                "label": case["label"],
                "model_family": "ridge",
                "model_key": "ridge",
                "hf_model_id": None,
                "is_primary_chronos": False,
                "artifact_dir": ridge_result.get("artifact_dir"),
                "artifact_manifest_path": ridge_result.get("artifact_manifest_path"),
                "source_frozen_data_path": case["frozen_data_path"],
                "train_start_utc": windows["train_start_utc"],
                "train_end_utc": windows["train_end_utc"],
                "n_train_points": int(len(hist)),
                "status": ridge_result["status"],
                "reason": "passed" if ridge_result["status"] == "trained" else "training_exception",
                "selected_alpha": ridge_result.get("selected_alpha"),
                "best_context_hours": None,
                "validation_metric_name": ridge_result.get("validation_metric_name"),
                "validation_metric_value": ridge_result.get("validation_metric_value"),
                "training_wallclock_s": ridge_result.get("training_wallclock_s"),
            }
        )
        case_registry["ridge"] = ridge_result

        # Chronos family
        family_registry = {
            "primary_model_key": primary_chronos_key,
            "flavors": {},
        }
        for flavor in chronos_cfg.get("flavors") or []:
            flavor = dict(flavor)
            model_key = str(flavor["model_key"])
            hf_model_id = str(flavor["hf_model_id"])
            enabled = bool(flavor.get("enabled", False))
            flavor_dir = trained_models_root / "chronos" / model_key / case["station_id"] / case["parameter_code"]

            if not enabled:
                flavor_result = {
                    "enabled": False,
                    "status": "disabled",
                    "hf_model_id": hf_model_id,
                }
            else:
                ch_start = time.perf_counter()
                try:
                    ch_artifacts = optimize_chronos_context(
                        hist,
                        model_id=hf_model_id,
                        candidates_hours=[int(x) for x in chronos_cfg.get("context_candidates_h") or [24, 48, 72, 168, 336]],
                        eval_points=int(chronos_cfg.get("eval_points", 168)),
                        num_samples=int(chronos_cfg.get("num_samples", 20)),
                    )
                    ch_artifacts = dict(ch_artifacts)
                    ch_artifacts.update(
                        {
                            "schema_version": "chronos_training_manifest_v1",
                            "trained_at_utc": datetime.now(timezone.utc).isoformat(),
                            "station_id": case["station_id"],
                            "parameter": case["parameter_code"],
                            "model_key": model_key,
                        }
                    )
                    save_chronos_artifacts(flavor_dir, ch_artifacts)
                    manifest_path = _write_chronos_training_manifest(flavor_dir, ch_artifacts)
                    flavor_result = {
                        "enabled": True,
                        "status": "trained",
                        "hf_model_id": hf_model_id,
                        "artifact_dir": str(flavor_dir),
                        "artifact_manifest_path": manifest_path,
                        "best_context_hours": int(ch_artifacts.get("best_context_hours", 24)),
                        "validation_metric_name": "rmse_valid",
                        "validation_metric_value": float(ch_artifacts.get("rmse_valid", float("nan"))),
                        "training_wallclock_s": round(time.perf_counter() - ch_start, 6),
                    }
                except Exception as exc:
                    flavor_result = {
                        "enabled": True,
                        "status": "failed",
                        "hf_model_id": hf_model_id,
                        "artifact_dir": str(flavor_dir),
                        "artifact_manifest_path": None,
                        "best_context_hours": None,
                        "validation_metric_name": "rmse_valid",
                        "validation_metric_value": None,
                        "training_wallclock_s": round(time.perf_counter() - ch_start, 6),
                        "error": str(exc),
                    }
                    if model_key == primary_chronos_key:
                        fatal_failures.append(f"{case['case_key']}: {model_key} failed: {exc}")

            family_registry["flavors"][model_key] = flavor_result
            summary_rows.append(
                {
                    "run_tag": resolved["run_tag"],
                    "case_key": case["case_key"],
                    "group": case["group"],
                    "station_id": case["station_id"],
                    "site_no": case["site_no"],
                    "parameter_code": case["parameter_code"],
                    "label": case["label"],
                    "model_family": "chronos",
                    "model_key": model_key,
                    "hf_model_id": hf_model_id,
                    "is_primary_chronos": model_key == primary_chronos_key,
                    "artifact_dir": flavor_result.get("artifact_dir"),
                    "artifact_manifest_path": flavor_result.get("artifact_manifest_path"),
                    "source_frozen_data_path": case["frozen_data_path"],
                    "train_start_utc": windows["train_start_utc"],
                    "train_end_utc": windows["train_end_utc"],
                    "n_train_points": int(len(hist)),
                    "status": flavor_result["status"],
                    "reason": "passed" if flavor_result["status"] == "trained" else flavor_result["status"],
                    "selected_alpha": None,
                    "best_context_hours": flavor_result.get("best_context_hours"),
                    "validation_metric_name": flavor_result.get("validation_metric_name"),
                    "validation_metric_value": flavor_result.get("validation_metric_value"),
                    "training_wallclock_s": flavor_result.get("training_wallclock_s"),
                }
            )

        case_registry["chronos_family"] = family_registry
        registry_entries.append(case_registry)

    summary_df = pd.DataFrame(summary_rows)
    summary_path = trained_models_root / "model_training_summary.csv"
    summary_df.to_csv(summary_path, index=False)

    registry_path = trained_models_root / "training_registry.json"
    registry_payload = {
        "run_tag": resolved["run_tag"],
        "train_start_utc": windows["train_start_utc"],
        "train_end_utc": windows["train_end_utc"],
        "primary_chronos_model_key": primary_chronos_key,
        "registry": registry_entries,
    }
    save_json(registry_path, registry_payload)

    freeze_manifest = {
        "run_tag": resolved["run_tag"],
        "train_start_utc": windows["train_start_utc"],
        "train_end_utc": windows["train_end_utc"],
        "primary_chronos_model_key": primary_chronos_key,
        "n_cases_included": len(resolved.get("cases_included") or []),
        "n_ridge_trained": int(((summary_df["model_key"] == "ridge") & (summary_df["status"] == "trained")).sum()) if not summary_df.empty else 0,
        "chronos_family_counts": {
            mk: int(((summary_df["model_key"] == mk) & (summary_df["status"] == "trained")).sum())
            for mk in [str(f["model_key"]) for f in chronos_cfg.get("flavors") or []]
        },
        "training_registry_path": str(registry_path),
        "model_training_summary_path": str(summary_path),
    }
    save_json(trained_models_root / "training_freeze_manifest.json", freeze_manifest)

    if fatal_failures:
        raise RuntimeError("Training failed for required model/case combinations: " + "; ".join(fatal_failures))

    print(f"Training registry saved to: {registry_path}")
    print(f"Training summary saved to: {summary_path}")


if __name__ == "__main__":
    main()
