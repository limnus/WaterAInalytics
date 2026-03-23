from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class AgenticExecutionPlan:
    include_station_context: bool
    llm_enabled: bool
    llm_provider: str = "off"
    llm_model: str = ""


def llm_request_is_runnable(*, enabled: bool, provider: str | None, model: str | None, provider_available: bool = True) -> bool:
    if not enabled:
        return False
    provider_norm = (provider or "off").strip().lower()
    if provider_norm not in {"ollama", "openai"}:
        return False
    if not (model or "").strip():
        return False
    return bool(provider_available)


def build_execution_plan_lines(plan: AgenticExecutionPlan) -> List[str]:
    lines: List[str] = [
        "1. Build forecast context and deterministic quantitative analysis.",
    ]
    if plan.include_station_context:
        lines.append("2. Enrich the analysis with official station context (USGS / Census / NWS).")
    else:
        lines.append("2. Skip official station context enrichment.")

    if llm_request_is_runnable(
        enabled=plan.llm_enabled,
        provider=plan.llm_provider,
        model=plan.llm_model,
        provider_available=True,
    ):
        provider_label = (plan.llm_provider or "off").strip().lower()
        lines.append(
            f"3. Run optional LLM refinement using {provider_label} with model '{plan.llm_model.strip()}'."
        )
    elif plan.llm_enabled:
        lines.append("3. Optional LLM refinement is enabled, but it will be skipped unless provider and model are valid.")
    else:
        lines.append("3. Skip optional LLM refinement.")

    lines.append("4. Persist artifacts, telemetry, and export-ready analysis outputs.")
    return lines
