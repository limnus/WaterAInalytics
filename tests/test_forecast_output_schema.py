from __future__ import annotations

import pandas as pd

from core.forecast_models.base import ForecastOutput
from core.forecast_models.output_schema import (
    FORECAST_RUN_SCHEMA_VERSION,
    FORECAST_TABLE_SCHEMA_VERSION,
    StationForecastBundle,
    build_experiment_summary_artifact,
    build_forecast_run_artifact,
    experiment_summary_to_frame,
    forecast_output_to_rows,
    normalize_history_frame,
    rows_to_frame,
)


def _make_output() -> ForecastOutput:
    idx = pd.date_range("2026-03-22T00:00:00Z", periods=2, freq="h", tz="UTC")
    y_pred = pd.Series([10.5, 11.0], index=idx, name="y_pred")
    return ForecastOutput(
        station_id="USGS-01013500",
        parameter="00065",
        model_key="ridge",
        y_pred=y_pred,
        sigma_residual=0.75,
        meta={"alpha": 1.0},
    )


def test_normalize_history_frame_sorts_and_cleans():
    raw = pd.DataFrame(
        {
            "Datetime": ["2026-03-22T02:00:00Z", "bad", "2026-03-22T01:00:00Z"],
            "Value": [2.0, 3.0, 1.0],
        }
    )
    out = normalize_history_frame(raw)
    assert list(out["Value"]) == [1.0, 2.0]
    assert out["Datetime"].iloc[0] < out["Datetime"].iloc[1]


def test_forecast_output_rows_and_run_artifact_are_standardized():
    hist = pd.DataFrame(
        {
            "Datetime": pd.date_range("2026-03-21T22:00:00Z", periods=3, freq="h", tz="UTC"),
            "Value": [8.0, 9.0, 10.0],
        }
    )
    out = _make_output()
    pi_low = pd.Series([9.5, 10.0], index=out.y_pred.index, name="pi_low")
    pi_high = pd.Series([11.5, 12.0], index=out.y_pred.index, name="pi_high")

    bundle = StationForecastBundle(
        station_id="USGS-01013500",
        parameter="00065",
        requested_model_key="chronos-mini",
        requested_model_label="Chronos-Mini",
        used_model_key="ridge",
        used_model_label="Ridge",
        forecast_output=out,
        history_df=hist,
        pi_low=pi_low,
        pi_high=pi_high,
    )

    rows = forecast_output_to_rows(
        bundle=bundle,
        horizon_h=2,
        interval_label="80%",
        pi_method_label="GaussianResidual(80%)",
    )
    assert len(rows) == 2
    assert rows[0]["schema_version"] == FORECAST_TABLE_SCHEMA_VERSION
    assert rows[0]["requested_model_key"] == "chronos-mini"
    assert rows[0]["used_model_key"] == "ridge"
    assert rows[0]["pi_low"] == 9.5

    df = rows_to_frame(rows)
    assert list(df["horizon_step"]) == [1, 2]
    assert str(df["timestamp_utc"].dtype).startswith("datetime64[ns, UTC]")

    artifact = build_forecast_run_artifact(
        station_bundles=[bundle],
        requested_model_key="chronos-mini",
        requested_model_label="Chronos-Mini",
        parameter="00065",
        horizon_h=2,
        interval_label="80%",
        pi_method_label="GaussianResidual(80%)",
        session_seed=123,
        created_at_utc="2026-03-22T03:00:00+00:00",
    )
    assert artifact["schema_version"] == FORECAST_RUN_SCHEMA_VERSION
    assert artifact["station_count"] == 1
    assert artifact["stations"][0]["history"]["last_value"] == 10.0
    assert artifact["stations"][0]["forecast"][0]["used_model_label"] == "Ridge"


def test_experiment_summary_artifact_flattens_station_and_manifest_data():
    hist = pd.DataFrame(
        {
            "Datetime": pd.date_range("2026-03-21T22:00:00Z", periods=3, freq="h", tz="UTC"),
            "Value": [8.0, 9.0, 10.0],
        }
    )
    out = _make_output()
    bundle = StationForecastBundle(
        station_id="USGS-01013500",
        parameter="00065",
        requested_model_key="ridge",
        requested_model_label="Ridge",
        used_model_key="ridge",
        used_model_label="Ridge",
        forecast_output=out,
        history_df=hist,
    )

    artifact = build_forecast_run_artifact(
        station_bundles=[bundle],
        requested_model_key="ridge",
        requested_model_label="Ridge",
        parameter="00065",
        horizon_h=2,
        interval_label="80%",
        pi_method_label="GaussianResidual(80%)",
        session_seed=123,
        created_at_utc="2026-03-22T03:00:00+00:00",
    )
    artifact["article_mode"] = True
    artifact["article_preset_key"] = "paper-core-flow"
    artifact["article_preset_name"] = "Paper Core — Flow (00060)"

    training_manifests = {
        "ridge|USGS-01013500|00065": {
            "trained_at_utc": "2026-03-21T00:00:00+00:00",
            "n_train": 40,
            "n_valid": 10,
            "rmse_valid": 0.75,
            "best_alpha": 1.0,
            "best_rmse_valid": 0.75,
            "rmse_by_alpha": {"0.1": 0.9, "1.0": 0.75},
            "_path": "/tmp/training_manifest.json",
        }
    }

    summary = build_experiment_summary_artifact(artifact, training_manifests=training_manifests)
    assert summary["schema_version"] == "experiment_summary_v1"
    assert summary["article_mode"] is True
    assert summary["article_preset_key"] == "paper-core-flow"
    assert summary["station_count"] == 1
    assert summary["stations"][0]["best_alpha"] == 1.0
    assert summary["stations"][0]["training_manifest_path"] == "/tmp/training_manifest.json"

    df = experiment_summary_to_frame(summary)
    assert list(df["station_id"]) == ["USGS-01013500"]
    assert df.loc[0, "forecast_first_y_hat"] == 10.5
