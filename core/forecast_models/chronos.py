# core/forecast_models/chronos.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from .base import ForecastOutput, ForecastRequest


@dataclass
class ChronosModel:
    """Chronos inference wrapper (local). Implementation comes next.

    model_key must be 'chronos-tiny' or 'chronos-mini'.
    """
    model_key: str

    def load_artifacts(self, artifacts_dir: Path, station_id: str, parameter: str) -> Dict[str, Any]:
        raise FileNotFoundError(
            f"Chronos artifacts not found for {station_id}/{parameter}/{self.model_key}. Train/calibrate first."
        )

    def predict(self, req: ForecastRequest, artifacts: Dict[str, Any]) -> ForecastOutput:
        raise NotImplementedError("ChronosModel.predict will be implemented next (after scaffolding).")
