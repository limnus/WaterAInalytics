"""LLM Analyst (v0.9.0)

This package provides an *optional* read-only LLM layer that:
  - Consumes only structured artifacts already produced by the deterministic pipeline.
  - Produces an audit-friendly report (JSON + markdown).
  - Does not browse the web and does not call internal tools that mutate state.

Default provider is OFF.
"""

from .models import LLMConfig, LLMProvider, LLMReport
from .runner import run_llm_analyst

__all__ = [
    "LLMConfig",
    "LLMProvider",
    "LLMReport",
    "run_llm_analyst",
]
