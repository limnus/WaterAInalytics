from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from core.llm_analysis.forecast_integration.models import ForecastContext
from core.llm_analysis.web_context.models import SourceDoc, Snippet, QueryPlan
from core.llm_analysis.extraction.models import FactBundle


@dataclass(frozen=True)
class ReportArtifact:
    format: str  # "markdown"
    content: str
    sources_bibliography: List[str]


@dataclass(frozen=True)
class AuditTrail:
    llm: Dict[str, Any]
    timing_ms: Dict[str, int]
    warnings: List[str]


@dataclass(frozen=True)
class AnalysisRunResult:
    cache_key: str
    created_at_utc: str

    forecast_context: ForecastContext

    query_plan: QueryPlan
    sources: List[SourceDoc]
    snippets: List[Snippet]

    facts: FactBundle
    report: ReportArtifact
    audit: AuditTrail
