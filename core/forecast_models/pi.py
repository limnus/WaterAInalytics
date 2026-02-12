# core/forecast_models/pi.py
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class PredictionInterval:
    lower: pd.Series
    upper: pd.Series
    level: float


def gaussian_residual_pi(y_pred: pd.Series, sigma: float, level: float = 0.8) -> PredictionInterval:
    """Fast Gaussian residual-based PI.

    Assumes errors ~ N(0, sigma^2). For a central PI:
      alpha = 1 - level
      lower = y - z_{1-alpha/2} * sigma
      upper = y + z_{1-alpha/2} * sigma

    We hard-code z for common levels to avoid scipy dependency.
    """
    if not isinstance(y_pred, pd.Series):
        raise TypeError("y_pred must be a pandas Series")

    if sigma < 0:
        raise ValueError("sigma must be non-negative")

    # Common z-values (two-sided central intervals)
    z_map = {
        0.80: 1.2815515655446004,
        0.90: 1.6448536269514722,
        0.95: 1.959963984540054,
    }
    z = z_map.get(round(float(level), 2))
    if z is None:
        # Fallback: linear interpolation between 80% and 95% (good enough for UI bands)
        lvl = float(level)
        if lvl <= 0.80:
            z = z_map[0.80]
        elif lvl >= 0.95:
            z = z_map[0.95]
        else:
            # interpolate on (level, z)
            x0, x1 = 0.80, 0.95
            y0, y1 = z_map[0.80], z_map[0.95]
            z = y0 + (y1 - y0) * ((lvl - x0) / (x1 - x0))

    sigma_f = float(sigma)
    lower = (y_pred - z * sigma_f).rename("pi_low")
    upper = (y_pred + z * sigma_f).rename("pi_high")
    return PredictionInterval(lower=lower, upper=upper, level=float(level))
