from __future__ import annotations

from typing import List

from core.llm_analysis.forecast_integration.models import ForecastContext
from core.llm_analysis.report.generator import generate_report_md
from core.llm_analysis.extraction.models import FactBundle
from core.llm_analysis.config import ReportStyle
from core.llm_analysis.web_context.models import SourceDoc


def tool_generate_report_md(
    style: ReportStyle,
    forecast: ForecastContext,
    facts: FactBundle,
    sources: List[SourceDoc],
    used_pages: int,
    max_pages: int,
):
    return generate_report_md(
        style=style,
        forecast=forecast,
        facts=facts,
        sources=sources,
        used_pages=used_pages,
        max_pages=max_pages,
    )
