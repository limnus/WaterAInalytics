from __future__ import annotations

from typing import List

from core.llm_analysis.config import AnalysisConfig
from core.llm_analysis.extraction.fact_extractor import extract_facts_rule_based
from core.llm_analysis.extraction.models import FactBundle
from core.llm_analysis.forecast_integration.models import ForecastContext
from core.llm_analysis.web_context.models import SourceDoc, Snippet


def tool_extract_facts_rule_based(
    cfg: AnalysisConfig,
    forecast_ctx: ForecastContext,
    sources: List[SourceDoc],
    snippets: List[Snippet],
) -> FactBundle:
    return extract_facts_rule_based(
        cfg=cfg,
        forecast_ctx=forecast_ctx,
        sources=sources,
        snippets=snippets,
    )
