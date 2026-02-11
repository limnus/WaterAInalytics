"""Forecasting models.

The *project* version is tracked in :mod:`core.version`.
Model files are intentionally not versioned in filenames.
"""

from .persistence import PersistenceConfig, PersistenceForecast

__all__ = [
    "PersistenceConfig",
    "PersistenceForecast",
]
