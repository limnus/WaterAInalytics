from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal, Optional


Mode = Literal["playground", "full"]
Tone = Literal["neutral", "technical", "operational", "executive"]
PageDefinition = Literal["document_fetched"]


@dataclass(frozen=True)
class PagePolicy:
    """Defines the 'page budget' for web context collection.

    Page definition (MVP): 1 page = 1 document fetched (1 URL collected + stored).
    """

    max_pages: int
    page_definition: PageDefinition = "document_fetched"
    count_serp: bool = False
    dedup_urls: bool = True

    # Guardrails to keep runs stable even when max_pages is large (e.g., 30)
    max_snippets_per_page: int = 3
    max_chars_per_page: int = 12_000


@dataclass(frozen=True)
class ReportStyle:
    """Controls the report surface, independent from web page budget."""

    tone: Tone = "neutral"
    max_report_words: int = 1600


@dataclass(frozen=True)
class AnalysisConfig:
    """Top-level configuration for the analysis run."""

    mode: Mode
    use_cache: bool = True
    force_refresh: bool = False

    page_policy: PagePolicy = PagePolicy(max_pages=10)
    report_style: ReportStyle = ReportStyle()

    schema_version: str = "0.7.0"

    # Optional knobs; keep small in v0.6.0
    collector_opts: Optional[Dict[str, str]] = None


def apply_mode_defaults(cfg: AnalysisConfig) -> AnalysisConfig:
    """Return a new config with mode-based constraints enforced.

    - playground: max_pages fixed at 5, tone fixed to neutral.
    - full: slider range expected 5..30 (enforced in UI); no changes here.
    """
    if cfg.mode == "playground":
        return AnalysisConfig(
            mode=cfg.mode,
            use_cache=cfg.use_cache,
            force_refresh=cfg.force_refresh,
            page_policy=PagePolicy(
                max_pages=5,
                page_definition=cfg.page_policy.page_definition,
                count_serp=cfg.page_policy.count_serp,
                dedup_urls=cfg.page_policy.dedup_urls,
                max_snippets_per_page=cfg.page_policy.max_snippets_per_page,
                max_chars_per_page=cfg.page_policy.max_chars_per_page,
            ),
            report_style=ReportStyle(
                tone="neutral",
                max_report_words=cfg.report_style.max_report_words,
            ),
            schema_version=cfg.schema_version,
            collector_opts=cfg.collector_opts,
        )
    return cfg
