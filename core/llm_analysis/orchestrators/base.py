from __future__ import annotations

from pathlib import Path
from typing import Protocol

from core.llm_analysis.config import AnalysisConfig
from core.llm_analysis.models import AnalysisRunResult
from core.llm_analysis.forecast_integration.models import ForecastContext


class Orchestrator(Protocol):
    """Orchestrator contract.

    v0.6.0: fixed/deterministic pipeline orchestrator.
    v0.7.0+: agent orchestrator (e.g., Agno) must still return the SAME AnalysisRunResult.
    """

    def run(
        self,
        cfg: AnalysisConfig,
        forecast_ctx: ForecastContext,
        cache_root: Path,
    ) -> AnalysisRunResult:
        ...
