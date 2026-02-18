from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class TaggedQuery:
    """A query with a lightweight intent/section tag.

    This is meant for auditability and paper-friendly methodology descriptions.
    It is NOT an agent instruction.
    """

    q: str
    section: str


@dataclass(frozen=True)
class QueryPlan:
    """Deterministic query plan for the fixed pipeline.

    Backward compatibility:
      - `queries` is still a list[str] used by collectors.
      - `tagged_queries` adds traceability (optional).
    """

    queries: List[str]
    notes: Optional[str] = None

    # v0.7.0+ (optional)
    profile: Optional[str] = None
    tagged_queries: Optional[List[TaggedQuery]] = None


@dataclass(frozen=True)
class SourceDoc:
    source_id: str
    url: str
    title: Optional[str]
    publisher: Optional[str]
    retrieved_at_utc: str
    published_at_utc: Optional[str] = None

    # v0.7.x hardening metadata (optional / backward-compatible)
    host: Optional[str] = None
    content_hash: Optional[str] = None
    sanitized_char_count: Optional[int] = None
    truncated: Optional[bool] = None
    flags: Optional[List[str]] = None
    cache_hit: Optional[bool] = None


@dataclass(frozen=True)
class Snippet:
    snippet_id: str
    source_id: str
    url: str
    text: str
    query: Optional[str] = None
    start: Optional[int] = None
    end: Optional[int] = None
