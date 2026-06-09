from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.forecast_models.base import ForecastOutput
from core.llm_analysis.forecast_integration.adapter import forecast_output_to_context
from core.llm_analysis.llm_agent.quantitative_brief import build_quantitative_forecast_brief

from paper_tests_scripts.paper_common import load_json, save_json


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Render deterministic quantitative reports for selected paper benchmark windows.")
    ap.add_argument("--config", required=True, help="Path to artifacts/paper_results/<run_tag>/resolved_config.json")
    ap.add_argument("--selection-role", default="median", choices=["best", "median", "worst", "all"], help="Representative windows to render.")
    return ap.parse_args()


def _safe_stamp(ts: str) -> str:
    return str(ts).replace(":", "-").replace("+", "p").replace(" ", "_")


def _registry_cases(resolved: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {c["case_key"]: c for c in resolved.get("cases_included") or []}


def _choose_model(row: pd.Series) -> str:
    candidates = {
        "persistence": pd.to_numeric(row.get("persistence_rmse"), errors="coerce"),
        "ridge": pd.to_numeric(row.get("ridge_rmse"), errors="coerce"),
        "chronos-base": pd.to_numeric(row.get("chronos_base_rmse"), errors="coerce"),
    }
    valid = {k: float(v) for k, v in candidates.items() if pd.notna(v)}
    if not valid:
        return "chronos-base"
    return min(valid, key=valid.get)


def _read_forecast_output(case: Dict[str, Any], model_key: str, forecast_csv: Path) -> ForecastOutput:
    df = pd.read_csv(forecast_csv)
    ts = pd.to_datetime(df["timestamp_utc"], utc=True, errors="coerce")
    y_col = "y_hat" if "y_hat" in df.columns else "y_pred"
    y = pd.to_numeric(df[y_col], errors="coerce")
    ser = pd.Series(y.values, index=ts, name="y_pred").dropna()
    sigma = float(pd.to_numeric(df.get("sigma_residual", pd.Series([0.0])), errors="coerce").dropna().iloc[0]) if "sigma_residual" in df.columns else 0.0
    return ForecastOutput(
        station_id=case["station_id"],
        parameter=case["parameter_code"],
        model_key=model_key,
        y_pred=ser,
        sigma_residual=sigma,
        meta={"paper_run": True, "model_key": model_key, "source_forecast_csv": str(forecast_csv)},
    )


def _history_for_window(case: Dict[str, Any], history_end_utc: str, n: int = 168) -> pd.DataFrame:
    df = pd.read_parquet(case["frozen_data_path"])
    df["Datetime"] = pd.to_datetime(df["Datetime"], utc=True, errors="coerce")
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce")
    end = pd.Timestamp(history_end_utc)
    if end.tzinfo is None:
        end = end.tz_localize("UTC")
    else:
        end = end.tz_convert("UTC")
    hist = df[df["Datetime"] <= end].dropna(subset=["Datetime", "Value"]).sort_values("Datetime").tail(n)
    return hist[["Datetime", "Value"]].reset_index(drop=True)


def _brief_to_markdown(payload: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# Deterministic quantitative brief")
    lines.append("")
    lines.append(f"**Case:** {payload.get('case_key')}  ")
    lines.append(f"**Model:** {payload.get('model_key')}  ")
    lines.append(f"**Origin:** {payload.get('origin_utc')}  ")
    lines.append("")
    brief = payload.get("brief") or {}
    if brief.get("executive_summary"):
        lines.append("## Executive summary")
        lines.append(str(brief["executive_summary"]))
        lines.append("")
    for title, key in [
        ("Key findings", "key_findings"),
        ("Observed facts", "observed_facts"),
        ("Inferences", "inferences"),
        ("Alerts", "alerts"),
        ("Limitations", "limitations"),
    ]:
        vals = brief.get(key) or []
        if vals:
            lines.append(f"## {title}")
            for item in vals:
                lines.append(f"- {item}")
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    resolved = load_json(args.config)
    cases = _registry_cases(resolved)
    backtests_root = Path(resolved["paths"]["backtests_root"])
    reports_root = Path(resolved["paths"]["deterministic_reports_root"])
    reports_root.mkdir(parents=True, exist_ok=True)

    rep_path = backtests_root / "representative_windows.csv"
    metrics_path = backtests_root / "origin_metrics.csv"
    if not rep_path.exists():
        raise FileNotFoundError(rep_path)
    if not metrics_path.exists():
        raise FileNotFoundError(metrics_path)
    reps = pd.read_csv(rep_path)
    metrics = pd.read_csv(metrics_path)
    if args.selection_role != "all":
        reps = reps[reps["selection_role"].astype(str) == args.selection_role].copy()

    index_rows: List[Dict[str, Any]] = []
    for _, row in reps.iterrows():
        case_key = str(row["case_key"])
        case = cases.get(case_key)
        if not case:
            continue
        model_key = _choose_model(row)
        origin = str(row["origin_utc"])
        match = metrics[(metrics["case_key"].astype(str) == case_key) & (metrics["origin_utc"].astype(str) == origin) & (metrics["model_key"].astype(str) == model_key)]
        if match.empty:
            continue
        mrow = match.iloc[0]
        forecast_csv = Path(str(mrow["forecast_csv_path"]))
        if not forecast_csv.exists():
            continue
        out = _read_forecast_output(case, model_key, forecast_csv)
        hist = _history_for_window(case, str(row["history_end_utc"]))
        ctx = forecast_output_to_context(out, hist, run_datetime_utc=pd.Timestamp(origin))
        brief = build_quantitative_forecast_brief(ctx)
        payload = {
            "run_tag": resolved["run_tag"],
            "case_key": case_key,
            "group": case.get("group"),
            "station_id": case.get("station_id"),
            "parameter_code": case.get("parameter_code"),
            "label": case.get("label"),
            "model_key": model_key,
            "origin_utc": origin,
            "selection_role": row.get("selection_role"),
            "forecast_csv_path": str(forecast_csv),
            "forecast_run_json_path": str(mrow.get("forecast_run_json_path")),
            "experiment_summary_json_path": str(mrow.get("experiment_summary_json_path")),
            "brief": brief,
        }
        stem = f"{case_key}_{model_key}_{row.get('selection_role')}_{_safe_stamp(origin)}"
        json_path = reports_root / f"{stem}.json"
        md_path = reports_root / f"{stem}.md"
        save_json(json_path, payload)
        md_path.write_text(_brief_to_markdown(payload), encoding="utf-8")
        index_rows.append({**{k: payload.get(k) for k in ["case_key", "group", "station_id", "parameter_code", "label", "model_key", "origin_utc", "selection_role"]}, "json_path": str(json_path), "markdown_path": str(md_path)})

    index_df = pd.DataFrame(index_rows)
    index_df.to_csv(reports_root / "deterministic_report_index.csv", index=False)
    print(f"Deterministic reports written: {len(index_df)}")


if __name__ == "__main__":
    main()
