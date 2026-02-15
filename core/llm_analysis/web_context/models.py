from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class QueryPlan:
    queries: List[str]
    notes: Optional[str] = None


@dataclass(frozen=True)
class SourceDoc:
    source_id: str
    url: str
    title: Optional[str]
    publisher: Optional[str]
    retrieved_at_utc: str
    published_at_utc: Optional[str] = None


@dataclass(frozen=True)
class Snippet:
    snippet_id: str
    source_id: str
    url: str
    text: str
    query: Optional[str] = None
    start: Optional[int] = None
    end: Optional[int] = None
