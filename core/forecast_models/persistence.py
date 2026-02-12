# core/forecast_models/persistence.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

from .base import ForecastOutput, ForecastRequest


@dataclass
class PersistenceModel:
    model_key: str = "persistence"

    def load_artifacts(self, artifacts_dir: Path, station_id: str, parameter: str) -> Dict[str, Any]:
        """Persistence is training-free; artifacts are optional.

        We still allow a stored sigma_residual (global calibration for station/parameter),
        but if missing we will estimate from recent history.
        """
        meta_path = artifacts_dir / "meta.json"
        if meta_path.exists():
            import json

            return json.loads(meta_path.read_text(encoding="utf-8"))
        return {}

    def _estimate_sigma_from_history(self, history: pd.Series) -> float:
        # One-step persistence residuals on available history
        if history.size < 3:
            return 0.0
        y = history.astype(float).values
        y_hat = y[:-1]
        y_true = y[1:]
        resid = y_true - y_hat
        sigma = float(np.std(resid, ddof=1)) if resid.size >= 2 else float(np.std(resid))
        return max(0.0, sigma)

    def predict(self, req: ForecastRequest, artifacts: Dict[str, Any]) -> ForecastOutput:
        # Expect history_df with at least 'Datetime' and 'Value' columns (AirNow-style)
        df = req.history.copy()
        if "Datetime" not in df.columns or "Value" not in df.columns:
            raise ValueError("history must contain columns: 'Datetime', 'Value'")

        df = df.sort_values("Datetime")
        last_dt = pd.to_datetime(df["Datetime"].iloc[-1], utc=True)
        last_val = float(df["Value"].iloc[-1])

        future_idx = pd.date_range(
            last_dt + pd.Timedelta(hours=1),
            periods=req.horizon,
            freq=req.freq,
            tz="UTC",
        )

        # Noise (0..0.05) handled by UI; still allow artifacts override
        noise = float(artifacts.get("noise", 0.0))
        noise = max(0.0, min(0.05, noise))

        seed = req.session_seed
        if seed is None:
            seed = abs(hash((req.station_id, req.parameter, req.horizon))) % (2**32 - 1)
        rng = np.random.default_rng(int(seed))

        if noise > 0:
            eps = rng.uniform(-noise, noise, size=req.horizon)
            y_pred = last_val * (1.0 + eps)
        else:
            y_pred = np.full(req.horizon, last_val, dtype=float)

        y_pred_s = pd.Series(y_pred, index=future_idx, name="y_pred")

        # Sigma: prefer stored calibration, else estimate from history
        sigma = float(artifacts.get("sigma_residual", float("nan")))
        if not np.isfinite(sigma):
            hist_series = pd.to_numeric(df["Value"], errors="coerce").dropna()
            sigma = self._estimate_sigma_from_history(hist_series)

        # Post-processing: integer & non-negative rules (consistent with your earlier constraints)
        values = pd.to_numeric(df["Value"], errors="coerce").dropna()
        all_int = values.size > 0 and np.all(np.isclose(values.values, np.round(values.values)))
        all_pos = values.size > 0 and np.all(values.values >= 0)
        if all_pos:
            y_pred_s = y_pred_s.clip(lower=0.0)
        if all_int:
            y_pred_s = y_pred_s.round().astype(int)

        return ForecastOutput(
            station_id=req.station_id,
            parameter=req.parameter,
            model_key=self.model_key,
            y_pred=y_pred_s,
            sigma_residual=float(sigma),
            meta={"noise": noise, "seed": int(seed)},
        )
