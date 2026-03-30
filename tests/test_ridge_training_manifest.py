from __future__ import annotations

import json

import pandas as pd

from core.forecast_models.ridge import save_ridge_artifacts, train_ridge_from_history


def _make_history() -> pd.DataFrame:
    idx = pd.date_range("2026-03-01T00:00:00Z", periods=96, freq="h", tz="UTC")
    vals = [100 + (i % 12) * 3 for i in range(len(idx))]
    return pd.DataFrame({"Datetime": idx, "Value": vals})


def test_save_ridge_artifacts_writes_training_manifest(tmp_path):
    hist = _make_history()
    artifacts = train_ridge_from_history(hist, alpha=0.5)

    out_dir = tmp_path / "models" / "ridge" / "USGS-12345678" / "00060"
    save_ridge_artifacts(
        out_dir,
        artifacts,
        station_id="USGS-12345678",
        parameter="00060",
        model_key="ridge",
        trained_at_utc="2026-03-30T12:00:00+00:00",
        generated_by="tests.test_ridge_training_manifest",
    )

    assert (out_dir / "meta.json").exists()
    assert (out_dir / "weights.npz").exists()
    manifest_path = out_dir / "training_manifest.json"
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "ridge_training_manifest_v1"
    assert manifest["trained_at_utc"] == "2026-03-30T12:00:00+00:00"
    assert manifest["station_id"] == "USGS-12345678"
    assert manifest["parameter"] == "00060"
    assert manifest["model_key"] == "ridge"
    assert manifest["generated_by"] == "tests.test_ridge_training_manifest"
    assert manifest["n_rows"] == len(hist)
    assert manifest["n_supervised"] >= manifest["n_train"]
    assert manifest["n_valid"] >= 1
    assert manifest["alpha"] == 0.5
    assert manifest["best_alpha"] == 0.5
    assert "training_manifest.json" in manifest["files_generated"]


def test_save_ridge_artifacts_includes_alpha_grid_summary_when_available(tmp_path):
    hist = _make_history()
    artifacts = train_ridge_from_history(hist, alpha=1.0)
    artifacts["rmse_by_alpha"] = {"0.1": 1.25, "1.0": 1.1}
    artifacts["best_alpha"] = 1.0
    artifacts["best_rmse_valid"] = 1.1

    out_dir = tmp_path / "models" / "ridge" / "USGS-99999999" / "63680"
    save_ridge_artifacts(out_dir, artifacts, station_id="USGS-99999999", parameter="63680")

    manifest = json.loads((out_dir / "training_manifest.json").read_text(encoding="utf-8"))
    assert manifest["rmse_by_alpha"] == {"0.1": 1.25, "1.0": 1.1}
    assert manifest["best_alpha"] == 1.0
    assert manifest["best_rmse_valid"] == 1.1
