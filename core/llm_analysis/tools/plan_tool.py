from __future__ import annotations

from core.llm_analysis.config import AnalysisConfig
from core.llm_analysis.forecast_integration.models import ForecastContext
from core.llm_analysis.web_context.models import QueryPlan
from core.llm_analysis.web_context.queries import build_query_plan


def tool_build_query_plan(forecast_ctx: ForecastContext, cfg: AnalysisConfig) -> QueryPlan:
    return build_query_plan(forecast_ctx=forecast_ctx, cfg=cfg)
