from __future__ import annotations

from pathlib import Path

from core.llm_analysis.config import AnalysisConfig, apply_mode_defaults
from core.llm_analysis.forecast_integration.models import ForecastContext
from core.llm_analysis.models import AnalysisRunResult
from core.llm_analysis.orchestrators.fixed_pipeline import FixedPipelineOrchestrator


def run_analysis(cfg: AnalysisConfig, forecast_ctx: ForecastContext, cache_root: Path) -> AnalysisRunResult:
    cfg = apply_mode_defaults(cfg)
    return FixedPipelineOrchestrator().run(cfg=cfg, forecast_ctx=forecast_ctx, cache_root=cache_root)
