from __future__ import annotations

import pandas as pd

from core.forecast_models.base import ForecastOutput
from core.llm_analysis.forecast_integration.adapter import forecast_output_to_context


def test_forecast_output_to_context_uses_datetime_column_not_range_index():
    y_pred = pd.Series(
        [10.0, 11.0],
        index=pd.date_range("2026-03-22T03:00:00Z", periods=2, freq="h", tz="UTC"),
        name="y_pred",
    )
    out = ForecastOutput(
        station_id="USGS-01013500",
        parameter="00065",
        model_key="ridge",
        y_pred=y_pred,
        sigma_residual=0.5,
        meta={},
    )
    history_df = pd.DataFrame(
        {
            "Datetime": pd.to_datetime(
                ["2026-03-22T00:00:00Z", "2026-03-22T01:00:00Z", "2026-03-22T02:00:00Z"],
                utc=True,
            ),
            "Value": [7.0, 8.0, 9.0],
        },
        index=[10, 20, 30],
    )

    ctx = forecast_output_to_context(out, history_df)
    assert ctx.recent_history.y == [7.0, 8.0, 9.0]
    assert ctx.recent_history.t_utc[0] == pd.Timestamp("2026-03-22T00:00:00Z")
    assert ctx.recent_history.t_utc[-1] == pd.Timestamp("2026-03-22T02:00:00Z")
    assert ctx.horizons[0].t_target_utc == pd.Timestamp("2026-03-22T03:00:00Z")
