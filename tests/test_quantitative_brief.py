from __future__ import annotations

import pandas as pd

from core.llm_analysis.forecast_integration.models import (
    ForecastContext,
    ForecastProvenance,
    HorizonPred,
    RecentHistory,
)
from core.llm_analysis.llm_agent.quantitative_brief import (
    build_quantitative_forecast_brief,
    render_quantitative_brief_markdown,
)


def _make_context() -> ForecastContext:
    history_t = pd.date_range("2026-03-22T00:00:00Z", periods=8, freq="h", tz="UTC")
    history_y = [10.0, 10.2, 10.1, 10.3, 10.4, 10.6, 10.9, 11.2]
    horizons = [
        HorizonPred(h=1, t_target_utc=pd.Timestamp("2026-03-22T08:00:00Z"), y_hat=11.4, p05=11.0, p95=11.8),
        HorizonPred(h=2, t_target_utc=pd.Timestamp("2026-03-22T09:00:00Z"), y_hat=11.6, p05=11.1, p95=12.1),
        HorizonPred(h=3, t_target_utc=pd.Timestamp("2026-03-22T10:00:00Z"), y_hat=11.7, p05=11.0, p95=12.4),
    ]
    return ForecastContext(
        station_id="USGS-01013500",
        parameter="00065",
        run_datetime_utc=pd.Timestamp("2026-03-22T07:00:00Z"),
        horizons=horizons,
        recent_history=RecentHistory(t_utc=list(history_t), y=history_y, units="ft"),
        provenance=ForecastProvenance(
            model_key="ridge",
            forecast_output_hash="abc123",
        ),
    )


def test_quantitative_brief_is_grounded_and_renders_markdown():
    brief = build_quantitative_forecast_brief(_make_context())

    assert "latest observed value is 11.2" in brief["executive_summary"]
    assert any("Latest observation = 11.2" in item for item in brief["observed_facts"])
    assert any("Short-term history is increasing" in item for item in brief["inferences"])
    assert any("forecast uncertainty appears" in item for item in brief["inferences"])
    assert brief["history_stats"]["history_points"] == 8
    assert brief["forecast_stats"]["direction_label"] == "increasing"

    md = render_quantitative_brief_markdown(brief)
    assert "#### Executive Summary" in md
    assert "#### Interpretive Inferences" in md
    assert "USGS-01013500" in md


def test_quantitative_brief_includes_official_station_context_findings():
    fc = _make_context()
    fc = ForecastContext(
        station_id=fc.station_id,
        parameter=fc.parameter,
        run_datetime_utc=fc.run_datetime_utc,
        horizons=fc.horizons,
        recent_history=fc.recent_history,
        provenance=fc.provenance,
        meta={
            "official_station_context": {
                "base_context": {"state_name": "Maine", "hydrologic_unit_code": "01030003"},
                "narrative": {
                    "key_findings": ["Approximate ground elevation at the monitoring point is 53.2 m above sea level."],
                    "limitations": ["County-level geography could not be resolved from the Census geocoder for this station."],
                    "open_questions": ["Would adding NLCD-derived land cover help here?"],
                },
            }
        },
    )

    brief = build_quantitative_forecast_brief(fc)

    assert "state Maine and HUC 01030003" in brief["executive_summary"]
    assert any("53.2 m above sea level" in item for item in brief["observed_facts"])
    assert any("County-level geography" in item for item in brief["limitations"])
    assert any("NLCD-derived land cover" in item for item in brief["open_questions"])
