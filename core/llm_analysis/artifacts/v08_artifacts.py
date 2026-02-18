from __future__ import annotations

"""core/llm_analysis/artifacts/v08_artifacts.py

v0.8.0 structured artifacts (deterministic, append-only in run.json).

Design goals:
  - No external providers (LLM is null provider)
  - Stable IDs and deterministic ordering
  - Minimal, paper-friendly structure: evidence -> claims -> narrative
  - Do NOT touch forecasting contracts
"""

import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.llm_analysis.cache.keying import stable_json_hash
from core.llm_analysis.extraction.models import FactBundle, FactItem
from core.llm_analysis.web_context.models import SourceDoc, Snippet


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _classify_source(host: Optional[str], publisher: Optional[str]) -> str:
    h = (host or "").lower()
    p = (publisher or "").lower()
    # Keep it intentionally conservative and deterministic.
    if h.endswith(".gov") or ".gov" in h or ".gov" in p or "usgs" in h or "noaa" in h:
        return "gov"
    if h.endswith(".edu") or ".edu" in h:
        return "edu"
    return "other"


def _recency_days(retrieved_at_utc: Optional[str], now_utc: Optional[datetime] = None) -> Optional[int]:
    if not retrieved_at_utc:
        return None
    try:
        dt = datetime.fromisoformat(retrieved_at_utc.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = now_utc or datetime.now(timezone.utc)
        return max(0, (now - dt).days)
    except Exception:
        return None


def build_evidence_artifacts(
    sources: List[SourceDoc],
    snippets: List[Snippet],
    queries_tagged: Optional[List[Dict[str, Any]]],
    evidence_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Build EvidenceItems.

    Evidence in v0.8.0 is intentionally "metadata-first": it relies on SourceDoc
    hardening metadata (host/hash/flags) and references persisted sanitized text
    (evidence/<source_id>.txt) when available.
    """
    q2section: Dict[str, str] = {}
    for qt in (queries_tagged or []):
        q = (qt.get("q") or "").strip()
        sec = (qt.get("section") or "").strip()
        if q and sec:
            q2section[q] = sec

    # Map source_id -> set(sections) via snippets
    src_sections: Dict[str, set[str]] = {}
    for sn in (snippets or []):
        sid = (sn.source_id or "").strip()
        if not sid:
            continue
        sec = q2section.get((sn.query or "").strip())
        if sec:
            src_sections.setdefault(sid, set()).add(sec)

    evidence: List[Dict[str, Any]] = []
    for s in sources:
        sid = (s.source_id or "").strip()
        if not sid:
            continue

        # Deterministic evidence_id
        evidence_id = f"ev_{sid}"

        text_path = None
        if evidence_dir is not None:
            p = evidence_dir / f"{sid}.txt"
            if p.exists():
                text_path = str(p.name)  # store relative name only

        ev = {
            "evidence_id": evidence_id,
            "source_id": sid,
            "url": getattr(s, "url", None),
            "title": getattr(s, "title", None),
            "publisher": getattr(s, "publisher", None),
            "host": getattr(s, "host", None),
            "retrieved_at_utc": getattr(s, "retrieved_at_utc", None),
            "published_at_utc": getattr(s, "published_at_utc", None),
            "content_hash": getattr(s, "content_hash", None),
            "sanitized_char_count": getattr(s, "sanitized_char_count", None),
            "truncated": getattr(s, "truncated", None),
            "flags": list(getattr(s, "flags", None) or []),
            "cache_hit": getattr(s, "cache_hit", None),
            "source_class": _classify_source(getattr(s, "host", None), getattr(s, "publisher", None)),
            "recency_days": _recency_days(getattr(s, "retrieved_at_utc", None)),
            "sections": sorted(list(src_sections.get(sid, set()))),
            "evidence_text_file": text_path,
        }
        evidence.append(ev)

    # Stable ordering
    evidence.sort(key=lambda x: (x.get("source_class") or "", x.get("host") or "", x.get("source_id") or ""))
    return evidence


def _support_from_confidence(conf_level: str) -> Tuple[float, str]:
    lvl = (conf_level or "low").lower().strip()
    if lvl == "high":
        return 0.90, "LOW"
    if lvl == "medium":
        return 0.70, "MED"
    return 0.40, "HIGH"


def build_claims_from_facts(
    facts: FactBundle,
    evidence_items: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Convert rule-based facts into v0.8.0 claims.

    This is the controlled evolution beyond "rule-based only":
      - facts remain deterministic
      - claims carry explicit support_score and uncertainty
      - each claim links to evidence_ids
    """
    evidence_by_source: Dict[str, str] = {}
    for ev in (evidence_items or []):
        sid = (ev.get("source_id") or "").strip()
        eid = (ev.get("evidence_id") or "").strip()
        if sid and eid:
            evidence_by_source[sid] = eid

    claims: List[Dict[str, Any]] = []
    for fi in (facts.facts or []):
        conf_level = (fi.confidence or {}).get("level", "low")
        support_score, unc = _support_from_confidence(conf_level)

        # Map fact.type to a small claim_type surface (keep it stable)
        claim_type = (fi.type or "general").strip()

        # Evidence links (prefer source-based evidence ids)
        ev_ids: List[str] = []
        for e in fi.evidence or []:
            eid = evidence_by_source.get((e.source_id or "").strip())
            if eid and eid not in ev_ids:
                ev_ids.append(eid)

        claim_id = f"cl_{fi.fact_id}"
        claims.append(
            {
                "claim_id": claim_id,
                "claim_type": claim_type,
                "title": fi.title,
                "text": fi.claim,
                "support_score": round(float(support_score), 3),
                "uncertainty_level": unc,
                "evidence_ids": ev_ids,
                "constraints_applied": ["no_causality", "deterministic_rule_based"],
                "relevance_to_horizons": dict(fi.relevance_to_horizons or {}),
                "confidence": dict(fi.confidence or {}),
                "tags": list(fi.tags or []),
            }
        )

    claims.sort(key=lambda c: (c.get("claim_type") or "", -(c.get("support_score") or 0.0), c.get("claim_id") or ""))
    return claims


_H_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def build_narrative_from_report(
    report_md: str,
    claims: List[Dict[str, Any]],
    render_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a minimal structured narrative from the existing markdown report.

    v0.8.0 Narrative Builder (C) starts as *structuring* and *auditing* the report.
    A deeper template-based generator can iterate later without breaking this contract.
    """
    render_profile = render_profile or {"format": "markdown", "style": "deterministic_v0"}

    lines = (report_md or "").splitlines()
    sections: List[Dict[str, Any]] = []
    cur_title = "Overview"
    cur_level = 2
    cur_buf: List[str] = []

    def flush():
        nonlocal cur_title, cur_level, cur_buf
        text = "\n".join(cur_buf).strip()
        if text:
            sec_id = stable_json_hash({"t": cur_title, "l": cur_level, "x": text})[:12]
            sections.append(
                {
                    "section_id": f"sec_{sec_id}",
                    "title": cur_title,
                    "level": cur_level,
                    "text": text,
                    # In v0.8.0 we conservatively associate *all* claims for audit.
                    # Later versions can do section-by-section assignment.
                    "claim_ids": [c.get("claim_id") for c in claims if c.get("claim_id")],
                }
            )
        cur_buf = []

    for ln in lines:
        m = _H_RE.match(ln)
        if m:
            flush()
            hashes, title = m.group(1), m.group(2)
            cur_level = len(hashes)
            cur_title = title.strip()
            continue
        cur_buf.append(ln)
    flush()

    report_id = stable_json_hash({"sections": [(s["title"], s["section_id"]) for s in sections]})[:12]
    return {
        "report_id": f"rep_{report_id}",
        "generated_at_utc": _utc_now_iso(),
        "render_profile": render_profile,
        "sections": sections,
    }


def build_artifacts_bundle(
    sources: List[SourceDoc],
    snippets: List[Snippet],
    queries_tagged: Optional[List[Dict[str, Any]]],
    facts: FactBundle,
    report_md: str,
    evidence_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    evidence = build_evidence_artifacts(
        sources=sources,
        snippets=snippets,
        queries_tagged=queries_tagged,
        evidence_dir=evidence_dir,
    )
    claims = build_claims_from_facts(facts=facts, evidence_items=evidence)
    narrative = build_narrative_from_report(report_md=report_md, claims=claims)
    return {
        "version": "0.8.0",
        "evidence": evidence,
        "claims": claims,
        "narrative": narrative,
    }
