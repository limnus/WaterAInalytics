"""Training contracts for forecasting models.

These contracts are the *stable interface* between:
  - Data acquisition / caching (USGS IV Parquets)
  - Feature generation (Admin Models)
  - Training / tuning
  - Model artifacts on disk

We keep the contracts lightweight (plain dict/JSON compatible) to make it easy
to inspect and version artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


# ------------------------
# Canonical data schemas
# ------------------------


@dataclass(frozen=True)
class SeriesFrameSchema:
    """Minimum schema required to represent a measured time series."""

    datetime_col: str = "datetime_utc"
    value_col: str = "value"
    station_col: str = "station_id"
    parameter_col: str = "parameter_code"


@dataclass(frozen=True)
class FeatureSetSpec:
    """Feature set used to generate the training table for a station/parameter."""

    name: str
    version: str
    target_col: str = "y"
    time_col: str = "datetime_utc"
    feature_cols: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d["feature_cols"] is None:
            d["feature_cols"] = []
        return d


@dataclass(frozen=True)
class TuningResult:
    """Result of feature selection + hyperparameter tuning."""

    selected_features: List[str]
    hyperparameters: Dict[str, Any]
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModelMetrics:
    """Standard metrics written after training/evaluation."""

    rmse: float
    mae: float
    r2: float
    mape: Optional[float] = None
    mase: Optional[float] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ------------------------
# Artifact layout
# ------------------------


@dataclass(frozen=True)
class ArtifactPaths:
    """Filesystem layout for model artifacts."""

    root_dir: Path
    model_name: str
    station_id: str
    parameter_code: str

    def base_dir(self) -> Path:
        return self.root_dir / "models" / self.model_name / self.station_id / self.parameter_code

    def feature_spec_path(self) -> Path:
        return self.base_dir() / "feature_set.json"

    def tuning_path(self) -> Path:
        return self.base_dir() / "tuning_result.json"

    def metrics_path(self) -> Path:
        return self.base_dir() / "metrics.json"

    def model_binary_path(self) -> Path:
        # placeholder for future (joblib/pickle)
        return self.base_dir() / "model.joblib"
