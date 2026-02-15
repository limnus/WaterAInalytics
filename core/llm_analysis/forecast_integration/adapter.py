from __future__ import annotations

from typing import Optional

import pandas as pd

from core.forecast_models.base import ForecastOutput
from core.llm_analysis.forecast_integration.models import (
    ForecastContext, ForecastProvenance, HorizonPred, RecentHistory
)
from core.llm_analysis.cache.keying import stable_json_hash


def forecast_output_to_context(
    out: ForecastOutput,
    history_df: pd.DataFrame,
    run_datetime_utc: Optional[pd.Timestamp] = None,
    timezone: str = "America/Fortaleza",
) -> ForecastContext:
    """Convert ForecastOutput into ForecastContext (H=1..3)."""

    if run_datetime_utc is not None:
        run_dt = run_datetime_utc
    else:
        now = pd.Timestamp.utcnow()
        if now.tzinfo is None:
            run_dt = now.tz_localize("UTC")
        else:
            run_dt = now.tz_convert("UTC")

    horizons = []
    for i, (ts, val) in enumerate(out.y_pred.items(), start=1):
        horizons.append(HorizonPred(h=i, t_target_utc=pd.Timestamp(ts), y_hat=float(val)))

    if "Value" in history_df.columns:
        y = history_df["Value"].astype(float).tolist()
    else:
        y = history_df.iloc[:, 0].astype(float).tolist()

    t = [pd.Timestamp(x) for x in history_df.index.tolist()]

    prov = ForecastProvenance(
        model_key=out.model_key,
        forecast_output_hash=stable_json_hash({
            "station_id": out.station_id,
            "parameter": out.parameter,
            "model_key": out.model_key,
            "y_pred": [(str(k), float(v)) for k, v in out.y_pred.items()],
            "sigma_residual": float(out.sigma_residual),
            "meta": out.meta,
        }),
        model_version=out.meta.get("model_version") if isinstance(out.meta, dict) else None,
        run_id=out.meta.get("run_id") if isinstance(out.meta, dict) else None,
        training_data_signature=out.meta.get("training_data_signature") if isinstance(out.meta, dict) else None,
    )

    return ForecastContext(
        station_id=out.station_id,
        parameter=out.parameter,
        run_datetime_utc=run_dt,
        horizons=horizons[:3],
        recent_history=RecentHistory(t_utc=t, y=y),
        provenance=prov,
        timezone=timezone,
        meta=out.meta if isinstance(out.meta, dict) else None,
    )
