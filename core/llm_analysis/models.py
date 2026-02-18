from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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
    """Minimal but paper-friendly audit trail.

    Notes:
      - Keep llm block even when provider is None (Null provider).
      - Fields added in v0.7.x are optional for backward compatibility.
    """

    llm: Dict[str, Any]
    timing_ms: Dict[str, int]
    warnings: List[str]

    # v0.7.x additions (optional but expected to be present going forward)
    run_id: Optional[str] = None
    schema_version: Optional[str] = None
    mode: Optional[str] = None
    budgets: Optional[Dict[str, Any]] = None

    # Query audit
    query_profile: Optional[str] = None
    queries: Optional[List[str]] = None
    queries_tagged: Optional[List[Dict[str, Any]]] = None

    sources_summary: Optional[List[Dict[str, Any]]] = None

    # v0.8.0 structured artifacts (append-only in run.json)
    artifacts: Optional[Dict[str, Any]] = None


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
