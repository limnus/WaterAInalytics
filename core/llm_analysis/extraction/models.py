from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class FactEvidence:
    source_id: str
    url: str
    retrieved_at_utc: str
    snippet_id: str
    snippet_text: str
    publisher: Optional[str] = None
    published_at_utc: Optional[str] = None


@dataclass(frozen=True)
class FactItem:
    fact_id: str
    type: str
    title: str
    claim: str
    time_window: Dict[str, Any]
    location: Dict[str, Any]
    expected_effect: Dict[str, Any]
    relevance_to_horizons: Dict[str, str]
    confidence: Dict[str, str]
    evidence: List[FactEvidence]
    tags: List[str]


@dataclass(frozen=True)
class FactBundle:
    schema_version: str
    station_id: str
    parameter: str
    run_datetime_utc: str
    facts: List[FactItem]
    summary: Dict[str, Any]
