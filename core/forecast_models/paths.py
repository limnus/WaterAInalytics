# core/forecast_models/paths.py
from __future__ import annotations

import os
from pathlib import Path


def artifacts_root() -> Path:
    """Root folder for all model artifacts.

    Override via env var WATERAINALYTICS_ARTIFACTS_DIR.

    Default: ./data/models (aligned with existing project structure).
    """
    root = os.getenv("WATERAINALYTICS_ARTIFACTS_DIR", os.path.join("data", "models"))
    return Path(root).expanduser().resolve()


def model_dir(station_id: str, parameter: str, model_key: str) -> Path:
    """Standard location for a model's artifacts."""
    return artifacts_root() / model_key / station_id / parameter
