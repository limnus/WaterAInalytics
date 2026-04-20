import io
import json
import zipfile

import pandas as pd

from core.article_demo.bundle import (
    build_article_analysis_bundle_bytes,
    build_article_forecast_bundle_bytes,
)


def _read_zip(data: bytes):
    with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def test_build_article_forecast_bundle_contains_expected_files():
    df = pd.DataFrame(
        {
            "station_id": ["USGS-1"],
            "timestamp_utc": ["2026-03-23T00:00:00+00:00"],
            "y_hat": [1.23],
        }
    )
    run_artifact = {"schema_version": "forecast_run_v1", "article_mode": True, "article_preset_key": "paper-core-flow", "article_preset_name": "Paper Core — Flow (00060)", "stations": [{"station_id": "USGS-1", "parameter": "00060", "used_model_key": "ridge", "history": {"n_rows": 1, "start_utc": "2026-03-22T00:00:00+00:00", "end_utc": "2026-03-22T00:00:00+00:00", "last_value": 1.0}, "forecast": [{"timestamp_utc": "2026-03-23T00:00:00+00:00", "y_hat": 1.23}], "meta": {"alpha": 1.0}}]}
    profile = {"profile_type": "article_demo", "station_ids": ["USGS-1"]}

    data = build_article_forecast_bundle_bytes(
        forecast_df=df,
        forecast_run_artifact=run_artifact,
        profile=profile,
    )
    files = _read_zip(data)

    assert set(files) >= {"manifest.json", "forecast.csv", "forecast_run.json", "experiment_config.json", "experiment_summary.json", "experiment_summary.csv"}
    manifest = json.loads(files["manifest.json"].decode("utf-8"))
    assert manifest["bundle_type"] == "article_forecast_bundle_v1"
    assert manifest["profile"]["profile_type"] == "article_demo"


def test_build_article_analysis_bundle_contains_expected_files():
    df = pd.DataFrame(
        {
            "station_id": ["USGS-1"],
            "timestamp_utc": ["2026-03-23T00:00:00+00:00"],
            "y_hat": [1.23],
        }
    )
    run_artifact = {"schema_version": "forecast_run_v1", "article_mode": True, "article_preset_key": "paper-core-flow", "article_preset_name": "Paper Core — Flow (00060)", "stations": [{"station_id": "USGS-1", "parameter": "00060", "used_model_key": "ridge", "history": {"n_rows": 1, "start_utc": "2026-03-22T00:00:00+00:00", "end_utc": "2026-03-22T00:00:00+00:00", "last_value": 1.0}, "forecast": [{"timestamp_utc": "2026-03-23T00:00:00+00:00", "y_hat": 1.23}], "meta": {"alpha": 1.0}}]}
    profile = {"profile_type": "article_demo", "station_ids": ["USGS-1"]}
    llm_report = {"output_markdown": "# LLM output"}

    data = build_article_analysis_bundle_bytes(
        forecast_df=df,
        forecast_run_artifact=run_artifact,
        quantitative_brief_markdown="Summary",
        deterministic_report_markdown="Detailed report",
        profile=profile,
        station_context={"station_id": "USGS-1"},
        execution_telemetry={"status": "ok"},
        focus_text="focus",
        presentation_label="Narrative paragraph",
        llm_report=llm_report,
    )
    files = _read_zip(data)

    assert set(files) >= {
        "manifest.json",
        "forecast.csv",
        "forecast_run.json",
        "experiment_config.json",
        "experiment_summary.json",
        "experiment_summary.csv",
        "quantitative_brief.md",
        "deterministic_report.md",
        "official_station_context.json",
        "execution_telemetry.json",
        "llm_report.json",
        "llm_report.md",
    }
    manifest = json.loads(files["manifest.json"].decode("utf-8"))
    assert manifest["bundle_type"] == "article_analysis_bundle_v1"
    assert manifest["has_llm_report"] is True


def test_build_article_analysis_bundle_sanitizes_internal_paths():
    df = pd.DataFrame(
        {
            "station_id": ["USGS-1"],
            "timestamp_utc": ["2026-03-23T00:00:00+00:00"],
            "y_hat": [1.23],
        }
    )
    run_artifact = {
        "schema_version": "forecast_run_v1",
        "stations": [{
            "station_id": "USGS-1",
            "parameter": "00060",
            "used_model_key": "ridge",
            "history": {"n_rows": 1, "start_utc": "2026-03-22T00:00:00+00:00", "end_utc": "2026-03-22T00:00:00+00:00", "last_value": 1.0},
            "forecast": [{"timestamp_utc": "2026-03-23T00:00:00+00:00", "y_hat": 1.23}],
            "meta": {"alpha": 1.0},
        }],
    }
    data = build_article_analysis_bundle_bytes(
        forecast_df=df,
        forecast_run_artifact=run_artifact,
        quantitative_brief_markdown="Summary",
        deterministic_report_markdown="Detailed report",
        profile={"profile_type": "article_demo"},
        station_context={
            "sources": [{"name": "local_station_cache", "path": r"G:\Meu Drive\AI Code\WaterAInalytics\data\usgs_00060_00065_base_from_ts_metadata.csv"}]
        },
        execution_telemetry={"status": "ok", "log_path": r"G:\Meu Drive\AI Code\WaterAInalytics\artifacts\agentic\agentic_execution_log.jsonl"},
        focus_text="focus",
        presentation_label="Narrative paragraph",
    )
    files = _read_zip(data)

    station_context = json.loads(files["official_station_context.json"].decode("utf-8"))
    execution_telemetry = json.loads(files["execution_telemetry.json"].decode("utf-8"))

    assert station_context["sources"][0]["path"] == "data/usgs_00060_00065_base_from_ts_metadata.csv"
    assert execution_telemetry["log_path"] == "agentic_execution_log.jsonl"
