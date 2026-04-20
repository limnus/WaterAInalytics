from __future__ import annotations

import sys
import types

import pytest


if "streamlit" not in sys.modules:
    sys.modules["streamlit"] = types.SimpleNamespace()

from core.ui.forecasting import _resolve_model_and_artifacts


class _FakeMissingModel:
    def __init__(self, model_key: str):
        self.model_key = model_key

    def load_artifacts(self, art_dir, station_id, parameter: str):
        raise FileNotFoundError(f"missing artifacts in {art_dir}")


class _FakePersistenceModel:
    def __init__(self):
        self.model_key = "persistence"

    def load_artifacts(self, art_dir, station_id, parameter: str):
        return {}


def test_standard_mode_falls_back_to_persistence(monkeypatch, tmp_path):
    def _fake_create_model(model_key: str):
        if model_key == "persistence":
            return _FakePersistenceModel()
        return _FakeMissingModel(model_key)

    monkeypatch.setattr("core.ui.forecasting.create_model", _fake_create_model)
    monkeypatch.setattr("core.ui.forecasting.model_dir", lambda station_id, parameter, model_key: tmp_path / model_key)

    model, artifacts, used_label, fell_back = _resolve_model_and_artifacts(
        station_id="USGS-1",
        parameter_code="00060",
        selected_model_key="ridge",
        model_label="Ridge",
        use_article_mode=False,
    )

    assert model.model_key == "persistence"
    assert artifacts == {}
    assert used_label == "Persistence"
    assert fell_back is True


def test_article_mode_raises_instead_of_falling_back(monkeypatch, tmp_path):
    monkeypatch.setattr("core.ui.forecasting.create_model", lambda model_key: _FakeMissingModel(model_key))
    monkeypatch.setattr("core.ui.forecasting.model_dir", lambda station_id, parameter, model_key: tmp_path / model_key)

    with pytest.raises(FileNotFoundError) as excinfo:
        _resolve_model_and_artifacts(
            station_id="USGS-1",
            parameter_code="00060",
            selected_model_key="ridge",
            model_label="Ridge",
            use_article_mode=True,
        )

    msg = str(excinfo.value)
    assert "Article mode requires trained artifacts" in msg
    assert "Falling back to" not in msg
