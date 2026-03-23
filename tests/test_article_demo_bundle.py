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
    run_artifact = {"schema_version": "forecast_run_v1", "stations": [{"station_id": "USGS-1"}]}
    profile = {"profile_type": "article_demo", "station_ids": ["USGS-1"]}

    data = build_article_forecast_bundle_bytes(
        forecast_df=df,
        forecast_run_artifact=run_artifact,
        profile=profile,
    )
    files = _read_zip(data)

    assert set(files) >= {"manifest.json", "forecast.csv", "forecast_run.json", "experiment_config.json"}
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
    run_artifact = {"schema_version": "forecast_run_v1", "stations": [{"station_id": "USGS-1"}]}
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
