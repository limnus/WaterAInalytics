from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from core.llm_analysis.config import AnalysisConfig
from core.llm_analysis.forecast_integration.models import ForecastContext
from core.llm_analysis.web_context.collector import collect_web_context
from core.llm_analysis.web_context.models import QueryPlan, SourceDoc, Snippet


def tool_collect_web_context(
    cfg: AnalysisConfig,
    forecast_ctx: ForecastContext,
    query_plan: QueryPlan,
    cache_root: Path,
) -> Tuple[List[SourceDoc], List[Snippet], int, Dict[str, str]]:
    return collect_web_context(
        cfg=cfg,
        forecast_ctx=forecast_ctx,
        query_plan=query_plan,
        cache_root=cache_root,
    )
