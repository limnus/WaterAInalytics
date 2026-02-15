from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass(frozen=True)
class HorizonPred:
    h: int
    t_target_utc: pd.Timestamp
    y_hat: float
    p05: Optional[float] = None
    p95: Optional[float] = None


@dataclass(frozen=True)
class RecentHistory:
    t_utc: List[pd.Timestamp]
    y: List[float]
    units: Optional[str] = None
    freq: str = "H"


@dataclass(frozen=True)
class ForecastProvenance:
    model_key: str
    forecast_output_hash: str
    model_version: Optional[str] = None
    run_id: Optional[str] = None
    training_data_signature: Optional[str] = None


@dataclass(frozen=True)
class ForecastContext:
    station_id: str
    parameter: str
    run_datetime_utc: pd.Timestamp

    horizons: List[HorizonPred]
    recent_history: RecentHistory

    provenance: ForecastProvenance
    timezone: str = "America/Fortaleza"
    meta: Optional[Dict[str, Any]] = None
