from __future__ import annotations

import io
import json
import zipfile
from typing import Any, Dict, Optional

import pandas as pd

from core.version import APP_VERSION


def _json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _csv_bytes(df: Optional[pd.DataFrame]) -> bytes:
    if df is None:
        return b""
    return df.to_csv(index=False).encode("utf-8")


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

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", _json_bytes(manifest))
        zf.writestr("forecast.csv", _csv_bytes(forecast_df))
        zf.writestr("forecast_run.json", _json_bytes(forecast_run_artifact or {}))
        zf.writestr("experiment_config.json", _json_bytes(profile))
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

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", _json_bytes(manifest))
        zf.writestr("forecast.csv", _csv_bytes(forecast_df))
        zf.writestr("forecast_run.json", _json_bytes(forecast_run_artifact or {}))
        zf.writestr("experiment_config.json", _json_bytes(profile))
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
