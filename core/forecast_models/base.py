# core/forecast_models/base.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

import pandas as pd


@dataclass(frozen=True)
class ForecastRequest:
    station_id: str
    parameter: str
    history: pd.DataFrame
    horizon: int  # steps (hours)
    freq: str = "H"
    # A deterministic seed set by the UI/session layer (e.g., hash of session id)
    session_seed: Optional[int] = None


@dataclass(frozen=True)
class ForecastOutput:
    station_id: str
    parameter: str
    model_key: str
    y_pred: pd.Series  # index: timestamps (UTC), name: 'y_pred'
    sigma_residual: float  # for Gaussian PI
    # Optional extras for debugging/UX
    meta: Dict[str, Any]


class ForecastModel(Protocol):
    """Contract for all forecasting models.

    - Training happens outside the PlayGround (Admin/User training flows).
    - Inference must be fast and deterministic given the same inputs + session_seed.
    """

    model_key: str

    def load_artifacts(self, artifacts_dir: Path, station_id: str, parameter: str) -> Dict[str, Any]:
        """Load model artifacts. Must raise FileNotFoundError if missing."""

    def predict(self, req: ForecastRequest, artifacts: Dict[str, Any]) -> ForecastOutput:
        """Run inference and return ForecastOutput."""
