from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from core.article_demo.model_validation import (
    build_article_artifact_validation,
    validate_article_model_artifacts_or_raise,
)


def test_article_artifact_validation_reports_missing_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    validation = build_article_artifact_validation(
        station_id="USGS-05586100",
        parameter_code="00060",
        model_key="ridge",
    )

    assert validation["exists"] is False
    assert validation["all_required_present"] is False
    assert [item["name"] for item in validation["required_files"]] == ["meta.json", "weights.npz", "training_manifest.json"]
    assert all(item["present"] is False for item in validation["required_files"])


def test_article_artifact_validation_accepts_complete_ridge_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    art_dir = tmp_path / "data" / "models" / "ridge" / "USGS-05586100" / "00060"
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "meta.json").write_text(json.dumps({"alpha": 1.0}), encoding="utf-8")
    np.savez(art_dir / "weights.npz", w=np.array([1.0]), mu=np.array([0.0]), sd=np.array([1.0]))
    (art_dir / "training_manifest.json").write_text(json.dumps({"alpha": 1.0}), encoding="utf-8")

    validation = validate_article_model_artifacts_or_raise(
        station_id="USGS-05586100",
        parameter_code="00060",
        model_key="ridge",
    )

    assert validation["exists"] is True
    assert validation["all_required_present"] is True
    assert all(item["present"] is True for item in validation["required_files"])


def test_article_artifact_validation_raises_clear_error_when_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError) as exc:
        validate_article_model_artifacts_or_raise(
            station_id="USGS-07374525",
            parameter_code="00060",
            model_key="ridge",
        )

    msg = str(exc.value)
    assert "Article mode requires trained artifacts" in msg
    assert "weights.npz" in msg
    assert "meta.json" in msg
    assert "training_manifest.json" in msg
