# core/forecast_models/registry.py
from __future__ import annotations

from .persistence import PersistenceModel
from .ridge import RidgeModel
from .chronos import ChronosModel


def create_model(model_key: str):
    key = (model_key or "").lower().strip()

    if key in ("persistence", "persist"):
        return PersistenceModel()
    if key == "ridge":
        return RidgeModel()

    # Chronos-Bolt
    if key in ("chronos-tiny", "chronos_bolt_tiny", "chronos-bolt-tiny"):
        return ChronosModel(model_key="chronos-tiny", model_id="amazon/chronos-bolt-tiny")
    if key in ("chronos-mini", "chronos_bolt_mini", "chronos-bolt-mini"):
        return ChronosModel(model_key="chronos-mini", model_id="amazon/chronos-bolt-mini")
    if key in ("chronos-base", "chronos_bolt_base", "chronos-bolt-base"):
        return ChronosModel(model_key="chronos-base", model_id="amazon/chronos-bolt-base")

    # Chronos-T5
    if key in ("chronos-large", "chronos_t5_large", "chronos-t5-large"):
        return ChronosModel(model_key="chronos-large", model_id="amazon/chronos-t5-large")

    raise ValueError(f"Unknown model_key: {model_key}")
