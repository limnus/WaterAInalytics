# core/forecast_models/__init__.py
"""Forecast model backends (v0.5.x).

PlayGround: inference only.
Training: Admin/User flows write artifacts to disk.
"""

from .base import ForecastModel, ForecastRequest, ForecastOutput
from .pi import gaussian_residual_pi, PredictionInterval

__all__ = [
    "ForecastModel",
    "ForecastRequest",
    "ForecastOutput",
    "gaussian_residual_pi",
    "PredictionInterval",
]
