"""Mock artifacts for Admin Models.

While the real Admin Models workflow is being implemented, we generate *mock*
JSON artifacts on disk so the rest of the application can be wired against a
stable contract.

The mocks are intentionally simple and human-readable.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from core.ml.contracts import ArtifactPaths, FeatureSetSpec, ModelMetrics, TuningResult


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")


def default_feature_set() -> FeatureSetSpec:
    """Baseline feature set (union of all candidates).

    This mirrors the feature-engineering plan you described (lags, sin terms,
    rolling stats, diffs). Admin Models can later remove features during
    selection, but the raw generated CSV keeps the full superset.
    """
    feats: List[str] = []

    feats += ["sin_hour", "sin_doy", "sin_dow"]

    # Lags (hours)
    for h in [1, 2, 3, 6, 12, 24, 48, 168]:
        feats.append(f"lag_{h}h")

    # Rolling means
    for h in [3, 6, 12, 24]:
        feats.append(f"roll_mean_{h}h")

    # Rolling min/max (24h)
    feats += ["roll_min_24h", "roll_max_24h"]

    # Differences
    for h in [1, 2, 3]:
        feats.append(f"diff_{h}h")

    return FeatureSetSpec(
        name="baseline_ts_features",
        version="1",
        target_col="y",
        time_col="datetime_utc",
        feature_cols=feats,
    )


def generate_mock_ridge_artifacts(
    *,
    data_root: str | Path = "data",
    station_id: str = "USGS-01013500",
    parameter_code: str = "00060",
) -> ArtifactPaths:
    """Create mock JSON artifacts for a Ridge model.

    Hyperparameter values are *representative defaults* commonly used as a
    starting point in practice.

    Notes / provenance (quick references):
      - scikit-learn Ridge estimator docs (alpha is the L2 regularization strength)
        https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html
      - scikit-learn linear models user guide (Ridge objective and alpha effect)
        https://scikit-learn.org/stable/modules/linear_model.html#ridge-regression-and-classification
      - Ridge is a standard regularized regression tool used for prediction in time-series settings
        (see e.g. Ballarin, 2021, arXiv:2105.00860)
        https://arxiv.org/abs/2105.00860
    """
    root = Path(data_root)
    paths = ArtifactPaths(root_dir=root, model_name="ridge", station_id=station_id, parameter_code=parameter_code)

    # --- Feature set spec (superset)
    fspec = default_feature_set()
    _write_json(paths.feature_spec_path(), fspec.to_dict())

    # --- Tuning result (mock)
    # Note: In real tuning we will select a subset and optimize alpha.
    # Common practice is to search alpha on a log-scale (e.g., 1e-3 ... 1e3)
    # and pick via time-series CV.
    tuning = TuningResult(
        selected_features=list(fspec.feature_cols),
        hyperparameters={
            "alpha": 1.0,
            "fit_intercept": True,
            "solver": "auto",
            "random_state": 42,
            "alpha_search": [1e-3, 1e-2, 1e-1, 1.0, 10.0, 100.0, 1000.0],
        },
        notes=(
            "Mock tuning result. alpha is L2 regularization strength; larger alpha => stronger shrinkage. "
            "Search grid is log-spaced, a common baseline for Ridge tuning."
        ),
    )
    _write_json(paths.tuning_path(), tuning.to_dict())

    # --- Metrics (mock)
    metrics = ModelMetrics(
        rmse=2.7,
        mae=2.1,
        r2=0.78,
        mape=0.09,
        notes="Mock metrics for wiring. Replace with real eval once training is implemented.",
    )
    _write_json(paths.metrics_path(), metrics.to_dict())

    return paths
