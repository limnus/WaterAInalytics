# core/forecast_models/registry.py
from __future__ import annotations

from typing import Dict, Type

from .base import ForecastModel
from .persistence import PersistenceModel
from .ridge import RidgeModel
from .chronos import ChronosModel


MODEL_REGISTRY: Dict[str, Type[ForecastModel]] = {
    "persistence": PersistenceModel,
    "ridge": RidgeModel,
    "chronos-tiny": ChronosModel,
    "chronos-mini": ChronosModel,
}


def create_model(model_key: str) -> ForecastModel:
    key = (model_key or "").strip().lower()
    if key not in MODEL_REGISTRY:
        raise ValueError(f"Unknown model_key='{model_key}'. Allowed: {sorted(MODEL_REGISTRY)}")
    cls = MODEL_REGISTRY[key]

    # ChronosModel needs model_key to select tiny/mini
    if key.startswith("chronos-"):
        return cls(model_key=key)  # type: ignore[arg-type]

    return cls()  # type: ignore[call-arg]
