"""Evaluation harness for deterministic Agentic AI artifacts.

This module is intentionally lightweight:
- No network
- No LLM provider
- No training

It operates on cached run.json files and optional human labels.
"""

from .schema import EvalCase, EvalConfig, load_cases  # noqa: F401
from .harness import run_evaluation  # noqa: F401
from .scan import scan_run_cache, write_cases_file  # noqa: F401
