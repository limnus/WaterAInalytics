from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional


LLMProvider = Literal["off", "ollama", "openai"]


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for the optional LLM Analyst layer.

    Notes:
      - Keep defaults safe: provider OFF.
      - temperature is forced to 0 by design (methodological stability).
      - endpoints and keys are read from env unless explicitly provided.
    """

    provider: LLMProvider = "off"
    model: str = ""

    # Provider endpoints (optional overrides)
    ollama_base_url: str = ""
    openai_base_url: str = ""

    # Secrets are read from environment by default
    openai_api_key: str = ""

    # Hard guardrails
    temperature: float = 0.0
    max_output_chars: int = 24_000
    ollama_timeout_s: int = 60

    @staticmethod
    def from_env(provider: LLMProvider, model: str) -> "LLMConfig":
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
        openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com").strip()
        openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        try:
            ollama_timeout_s = int(os.getenv("OLLAMA_TIMEOUT_S", "60").strip() or "60")
        except ValueError:
            ollama_timeout_s = 60
        ollama_timeout_s = max(5, min(600, ollama_timeout_s))
        return LLMConfig(
            provider=provider,
            model=(model or "").strip(),
            ollama_base_url=ollama_base_url,
            openai_base_url=openai_base_url,
            openai_api_key=openai_api_key,
            ollama_timeout_s=ollama_timeout_s,
        )


@dataclass(frozen=True)
class LLMReport:
    """Audit-friendly report produced by the LLM Analyst."""

    schema_version: str
    provider: str
    model: str
    created_at_utc: str

    input_hash: str
    prompt_hashes: Dict[str, str]

    # Structured output (JSON) + surface output (markdown)
    output_json: Dict[str, Any]
    output_markdown: str

    warnings: list[str]
