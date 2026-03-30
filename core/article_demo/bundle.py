from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from core.forecast_models.output_schema import build_experiment_summary_artifact, experiment_summary_to_frame
from core.forecast_models.paths import model_dir
from core.version import APP_VERSION


def _json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _csv_bytes(df: Optional[pd.DataFrame]) -> bytes:
    if df is None:
        return b""
    return df.to_csv(index=False).encode("utf-8")




def _load_training_manifests(forecast_run_artifact: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    manifests: Dict[str, Dict[str, Any]] = {}
    for station_payload in list((forecast_run_artifact or {}).get("stations") or []):
        station_id = station_payload.get("station_id")
        parameter = station_payload.get("parameter")
        used_model_key = station_payload.get("used_model_key")
        if not station_id or not parameter or not used_model_key:
            continue
        manifest_path = model_dir(station_id=station_id, parameter=str(parameter), model_key=str(used_model_key)) / "training_manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        manifest = dict(manifest)
        manifest["_path"] = str(Path(manifest_path).resolve())
        manifests[f"{used_model_key}|{station_id}|{parameter}"] = manifest
    return manifests


def build_experiment_summary_outputs(forecast_run_artifact: Dict[str, Any]) -> tuple[Dict[str, Any], pd.DataFrame]:
    manifests = _load_training_manifests(forecast_run_artifact or {})
    summary = build_experiment_summary_artifact(
        forecast_run_artifact or {},
        training_manifests=manifests,
    )
    summary_df = experiment_summary_to_frame(summary)
    return summary, summary_df

def build_article_forecast_bundle_bytes(
    *,
    forecast_df: pd.DataFrame,
    forecast_run_artifact: Dict[str, Any],
    profile: Dict[str, Any],
    station_context_snapshot: Optional[Dict[str, Any]] = None,
) -> bytes:
    manifest = {
        "app_version": APP_VERSION,
        "bundle_type": "article_forecast_bundle_v1",
        "station_count": int(len((forecast_run_artifact or {}).get("stations") or [])),
        "profile": profile,
    }

    experiment_summary, experiment_summary_df = build_experiment_summary_outputs(forecast_run_artifact or {})

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", _json_bytes(manifest))
        zf.writestr("forecast.csv", _csv_bytes(forecast_df))
        zf.writestr("forecast_run.json", _json_bytes(forecast_run_artifact or {}))
        zf.writestr("experiment_config.json", _json_bytes(profile))
        zf.writestr("experiment_summary.json", _json_bytes(experiment_summary))
        zf.writestr("experiment_summary.csv", _csv_bytes(experiment_summary_df))
        if station_context_snapshot is not None:
            zf.writestr("station_context_snapshot.json", _json_bytes(station_context_snapshot))
    return buf.getvalue()


def build_article_analysis_bundle_bytes(
    *,
    forecast_df: pd.DataFrame,
    forecast_run_artifact: Dict[str, Any],
    quantitative_brief_markdown: str,
    deterministic_report_markdown: str,
    profile: Dict[str, Any],
    station_context: Optional[Dict[str, Any]],
    execution_telemetry: Optional[Dict[str, Any]],
    focus_text: str,
    presentation_label: str,
    llm_report: Optional[Dict[str, Any]] = None,
) -> bytes:
    manifest = {
        "app_version": APP_VERSION,
        "bundle_type": "article_analysis_bundle_v1",
        "profile": profile,
        "focus_text": focus_text,
        "presentation_label": presentation_label,
        "has_station_context": bool(station_context),
        "has_llm_report": bool(llm_report),
    }

    experiment_summary, experiment_summary_df = build_experiment_summary_outputs(forecast_run_artifact or {})

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", _json_bytes(manifest))
        zf.writestr("forecast.csv", _csv_bytes(forecast_df))
        zf.writestr("forecast_run.json", _json_bytes(forecast_run_artifact or {}))
        zf.writestr("experiment_config.json", _json_bytes(profile))
        zf.writestr("experiment_summary.json", _json_bytes(experiment_summary))
        zf.writestr("experiment_summary.csv", _csv_bytes(experiment_summary_df))
        zf.writestr("quantitative_brief.md", (quantitative_brief_markdown or "").encode("utf-8"))
        zf.writestr("deterministic_report.md", (deterministic_report_markdown or "").encode("utf-8"))
        if station_context is not None:
            zf.writestr("official_station_context.json", _json_bytes(station_context))
        if execution_telemetry is not None:
            zf.writestr("execution_telemetry.json", _json_bytes(execution_telemetry))
        if llm_report is not None:
            zf.writestr("llm_report.json", _json_bytes(llm_report))
            markdown = llm_report.get("output_markdown") if isinstance(llm_report, dict) else None
            if markdown:
                zf.writestr("llm_report.md", str(markdown).encode("utf-8"))
    return buf.getvalue()
