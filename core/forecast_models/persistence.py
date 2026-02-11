from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple, Union

import math

import numpy as np


Number = Union[int, float]


def _is_null(x: object) -> bool:
    """Null check supporting None and NaN."""
    if x is None:
        return True
    if isinstance(x, float) and math.isnan(x):
        return True
    return False


def _all_effective_integers(values: Sequence[Number]) -> bool:
    """True if every element is an int or an integer-valued float."""
    if not values:
        return False
    for v in values:
        if isinstance(v, bool):
            return False
        if isinstance(v, int):
            continue
        if isinstance(v, float) and v.is_integer():
            continue
        return False
    return True


@dataclass(frozen=True)
class PersistenceConfig:
    """Configuration for the persistence baseline.

    Key principles (aligned with your v0.4.0 direction):
      - No clamp/guardrail by default (the UI-controlled noise is the primary knob).
      - Strict handling of nulls (None/NaN).
      - Preserve integer-only series as integer outputs.
    """

    noise_frac: float = 0.0
    connect_last_measured: bool = True
    reject_nulls: bool = True
    preserve_integers_if_series_integer: bool = True


class PersistenceForecast:
    """Persistence baseline forecast.

    Forecast rule:
      - Point forecast is the last observed value.
      - Optional Gaussian noise is added per step (sigma = noise_frac * |last|, with |last|=1 if last==0).

    Output:
      - If connect_last_measured=True: returns (horizon + 1) values (starts with last measured).
      - Else: returns exactly horizon values.
    """

    def __init__(self, config: PersistenceConfig | None = None):
        self.config = config or PersistenceConfig()

    def forecast(
        self,
        measured: Sequence[Number],
        horizon: int,
        *,
        seed: int | None = None,
    ) -> List[Number]:
        if horizon <= 0:
            raise ValueError("horizon must be > 0")
        if measured is None or len(measured) == 0:
            raise ValueError("measured must be a non-empty sequence")

        # Validate / sanitize
        if self.config.reject_nulls:
            for v in measured:
                if _is_null(v):
                    raise ValueError("measured contains null (None/NaN) values")
            clean = measured
        else:
            clean = [v for v in measured if not _is_null(v)]
            if not clean:
                raise ValueError("measured contains only null (None/NaN) values")

        series_is_int = bool(self.config.preserve_integers_if_series_integer and _all_effective_integers(clean))

        last = float(clean[-1])
        base = abs(last) if last != 0 else 1.0
        sigma = float(self.config.noise_frac) * float(base)
        if sigma < 0:
            raise ValueError("noise_frac must be >= 0")

        rng = np.random.default_rng(seed)

        # Build forecast path
        out: List[Number] = []
        if self.config.connect_last_measured:
            out.append(int(last) if series_is_int else float(last))

        if sigma > 0:
            noise = rng.normal(loc=0.0, scale=sigma, size=horizon)
            y = last + noise
        else:
            y = np.full(shape=(horizon,), fill_value=last, dtype=float)

        if series_is_int:
            y = np.rint(y).astype(int)
            out.extend([int(v) for v in y.tolist()])
        else:
            out.extend([float(v) for v in y.tolist()])

        if not self.config.connect_last_measured:
            return out[:horizon]
        return out

    def forecast_with_pi(
        self,
        measured: Sequence[Number],
        horizon: int,
        *,
        level: float = 0.9,
        bootstrap_samples: int = 200,
        seed: int | None = None,
    ) -> Tuple[List[Number], List[float], List[float]]:
        """Convenience helper to produce a simple PI consistent with the current UI.

        This is *not* a calibrated PI. It is a bootstrap-style band around the point forecast
        using the same sigma implied by noise_frac.
        """
        if not (0.0 < level < 1.0):
            raise ValueError("level must be in (0, 1)")
        if bootstrap_samples < 10:
            raise ValueError("bootstrap_samples must be >= 10")

        # Point forecast (includes optional connect_last_measured behavior)
        y_hat = self.forecast(measured, horizon, seed=seed)

        # For PI we only band the horizon future steps (exclude the optional first 'connect' point)
        offset = 1 if self.config.connect_last_measured else 0
        yh = np.asarray(y_hat[offset:], dtype=float)

        # sigma derived from last value and noise_frac (same as point model)
        last = float(measured[-1])
        base = abs(last) if last != 0 else 1.0
        sigma = float(self.config.noise_frac) * float(base)

        q_low = (1.0 - level) / 2.0
        q_high = 1.0 - q_low

        rng = np.random.default_rng(seed)

        if sigma == 0.0:
            # Degenerate: create a tiny symmetric band that widens slightly with horizon
            width0 = 0.03 * (abs(last) if last != 0 else 1.0)
            lo = np.empty_like(yh)
            hi = np.empty_like(yh)
            for i in range(horizon):
                w = width0 * (1.0 + 0.01 * i)
                lo[i] = yh[i] - w
                hi[i] = yh[i] + w
        else:
            sims = yh[None, :] + rng.normal(0.0, sigma, size=(int(bootstrap_samples), horizon))
            lo = np.quantile(sims, q_low, axis=0)
            hi = np.quantile(sims, q_high, axis=0)

        return y_hat, lo.tolist(), hi.tolist()
