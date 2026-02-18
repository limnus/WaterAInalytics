from __future__ import annotations

"""core/llm_analysis/artifacts/v081_artifacts.py

v0.8.1 structured artifacts (deterministic, append-only in run.json).

Delta vs v0.8.0:
  - Evidence: adds quality_flags (simple, metadata-first)
  - Claims: support_score becomes evidence-aware with score_breakdown + claim_rationale
  - Narrative: adds templated_markdown (parallel to legacy report structuring)

Constraints:
  - Deterministic (no provider)
  - Minimal changes, modular
  - Do NOT touch forecasting contracts
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.llm_analysis.cache.keying import stable_json_hash
from core.llm_analysis.extraction.models import FactBundle
from core.llm_analysis.web_context.models import SourceDoc, Snippet

from core.llm_analysis.artifacts.v08_artifacts import (
    _classify_source,
    _recency_days,
    build_narrative_from_report,
)

# -------------------------
# Evidence (with flags)
# -------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _mk_quality_flags(ev: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    # Published date is often missing; track it explicitly for audit/calibration.
    if not ev.get("published_at_utc"):
        flags.append("no_published_date")
    # Low content length is a weak signal; keep conservative threshold.
    try:
        n = int(ev.get("sanitized_char_count") or 0)
        if n and n < 600:
            flags.append("low_sanitized_length")
    except Exception:
        pass
    if ev.get("truncated") is True:
        flags.append("truncated_content")
    # Surface upstream hardening flags (if any) distinctly.
    upstream = list(ev.get("flags") or [])
    if upstream:
        flags.append("upstream_flags_present")
    return sorted(list(dict.fromkeys(flags)))

def build_evidence_artifacts_v081(
    sources: List[SourceDoc],
    snippets: List[Snippet],
    queries_tagged: Optional[List[Dict[str, Any]]],
    evidence_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    # Map query -> section
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

        evidence_id = f"ev_{sid}"

        text_path = None
        if evidence_dir is not None:
            p = evidence_dir / f"{sid}.txt"
            if p.exists():
                text_path = str(p.name)

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
        ev["quality_flags"] = _mk_quality_flags(ev)
        evidence.append(ev)

    evidence.sort(key=lambda x: (x.get("source_class") or "", x.get("host") or "", x.get("source_id") or ""))
    return evidence


# -------------------------
# Claims (with breakdown)
# -------------------------

def _base_confidence_score(level: str) -> float:
    lvl = (level or "low").lower().strip()
    if lvl == "high":
        return 0.70
    if lvl == "medium":
        return 0.50
    return 0.30

def _authoritative_bonus(evidence_items: List[Dict[str, Any]]) -> float:
    for ev in evidence_items:
        if (ev.get("source_class") or "") in ("gov", "edu"):
            return 0.10
    return 0.0

def _multi_source_bonus(evidence_ids: List[str]) -> float:
    # Conservative: bonus only when at least 2 distinct sources support the claim.
    return 0.10 if len(set(evidence_ids or [])) >= 2 else 0.0

def _quality_penalty(evidence_items: List[Dict[str, Any]]) -> float:
    penalty = 0.0
    for ev in evidence_items:
        qf = set(ev.get("quality_flags") or [])
        if "truncated_content" in qf:
            penalty += 0.05
        if "low_sanitized_length" in qf:
            penalty += 0.03
    return min(0.15, penalty)

def _uncertainty_from_score(score: float) -> str:
    if score >= 0.80:
        return "LOW"
    if score >= 0.55:
        return "MED"
    return "HIGH"

def _mk_rationale(conf_level: str, evidence_ids: List[str], evidence_items: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    parts.append(f"confidence={((conf_level or 'low').lower().strip())}")
    parts.append(f"sources={len(set(evidence_ids or []))}")
    if _authoritative_bonus(evidence_items) > 0:
        parts.append("authoritative_source")
    qpen = _quality_penalty(evidence_items)
    if qpen > 0:
        parts.append("quality_penalty")
    return "; ".join(parts)

def build_claims_from_facts_v081(
    facts: FactBundle,
    evidence_items: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    evidence_by_id: Dict[str, Dict[str, Any]] = { (ev.get("evidence_id") or ""): ev for ev in (evidence_items or []) if ev.get("evidence_id") }
    evidence_by_source: Dict[str, str] = {}
    for ev in (evidence_items or []):
        sid = (ev.get("source_id") or "").strip()
        eid = (ev.get("evidence_id") or "").strip()
        if sid and eid:
            evidence_by_source[sid] = eid

    claims: List[Dict[str, Any]] = []
    for fi in (facts.facts or []):
        conf_level = (fi.confidence or {}).get("level", "low")
        base = _base_confidence_score(conf_level)

        ev_ids: List[str] = []
        for e in fi.evidence or []:
            eid = evidence_by_source.get((e.source_id or "").strip())
            if eid and eid not in ev_ids:
                ev_ids.append(eid)

        ev_items = [evidence_by_id[eid] for eid in ev_ids if eid in evidence_by_id]

        bonus_auth = _authoritative_bonus(ev_items)
        bonus_ms = _multi_source_bonus(ev_ids)
        pen_q = _quality_penalty(ev_items)

        raw = base + bonus_auth + bonus_ms - pen_q
        score = max(0.0, min(1.0, raw))

        breakdown = {
            "base_confidence": round(base, 3),
            "bonus_authoritative": round(bonus_auth, 3),
            "bonus_multi_source": round(bonus_ms, 3),
            "penalty_quality": round(-pen_q, 3),
        }

        claim_type = (fi.type or "general").strip()
        claim_id = f"cl_{fi.fact_id}"

        claims.append(
            {
                "claim_id": claim_id,
                "claim_type": claim_type,
                "title": fi.title,
                "text": fi.claim,
                "support_score": round(float(score), 3),
                "uncertainty_level": _uncertainty_from_score(score),
                "score_breakdown": breakdown,
                "claim_rationale": _mk_rationale(conf_level, ev_ids, ev_items),
                "evidence_ids": ev_ids,
                "constraints_applied": ["no_causality", "deterministic_rule_based", "evidence_aware_scoring"],
                "relevance_to_horizons": dict(fi.relevance_to_horizons or {}),
                "confidence": dict(fi.confidence or {}),
                "tags": list(fi.tags or []),
            }
        )

    claims.sort(key=lambda c: (c.get("claim_type") or "", -(c.get("support_score") or 0.0), c.get("claim_id") or ""))
    return claims


# -------------------------
# Narrative (templated parallel)
# -------------------------

_SECTION_ORDER: List[Tuple[str, str, List[str]]] = [
    ("Station Context", "station_context", ["station_metadata"]),
    ("Data Sources & Services", "data_sources", ["data_source"]),
    ("Environmental / Weather Context", "environment", ["meteorology"]),
    ("Forecast Interpretation Context", "forecast_context", ["hydro_forecast_context"]),
]

def _hedged_prefix(unc: str) -> str:
    u = (unc or "HIGH").upper().strip()
    if u == "LOW":
        return ""
    if u == "MED":
        return "May indicate: "
    return "Suggests (low support): "

def _templated_markdown(claims: List[Dict[str, Any]], evidence: List[Dict[str, Any]]) -> str:
    # index evidence flags for limitations
    qflags: Dict[str, int] = {}
    for ev in evidence or []:
        for f in (ev.get("quality_flags") or []):
            qflags[f] = qflags.get(f, 0) + 1

    md_lines: List[str] = []
    md_lines.append("# Deterministic Context Report (Templated v0.8.1)")
    md_lines.append("")

    # Sections
    for title, _, types in _SECTION_ORDER:
        md_lines.append(f"## {title}")
        picked = [c for c in claims if (c.get("claim_type") in types)]
        picked.sort(key=lambda c: (-(c.get("support_score") or 0.0), c.get("claim_id") or ""))
        if not picked:
            md_lines.append("Insufficient evidence to conclude for this section.")
            md_lines.append("")
            continue

        for c in picked[:3]:
            prefix = _hedged_prefix(c.get("uncertainty_level"))
            text = (c.get("text") or "").strip()
            score = c.get("support_score")
            md_lines.append(f"- {prefix}{text} (score={score}, id={c.get('claim_id')})")
        md_lines.append("")

    # Limitations
    md_lines.append("## Limitations / Data Gaps")
    if not qflags:
        md_lines.append("No quality flags detected in collected sources.")
        md_lines.append("")
    else:
        md_lines.append("Observed issues in collected sources:")
        for k in sorted(qflags.keys()):
            md_lines.append(f"- {k}: {qflags[k]}")
        md_lines.append("")

    return "\n".join(md_lines).strip() + "\n"

def build_narrative_v081(
    report_md: str,
    claims: List[Dict[str, Any]],
    evidence: List[Dict[str, Any]],
    render_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    narrative = build_narrative_from_report(report_md=report_md, claims=claims, render_profile=render_profile)
    narrative["templated_markdown"] = _templated_markdown(claims=claims, evidence=evidence)
    narrative["templated_version"] = "0.8.1"
    return narrative


def build_artifacts_bundle(
    sources: List[SourceDoc],
    snippets: List[Snippet],
    queries_tagged: Optional[List[Dict[str, Any]]],
    facts: FactBundle,
    report_md: str,
    evidence_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    evidence = build_evidence_artifacts_v081(
        sources=sources,
        snippets=snippets,
        queries_tagged=queries_tagged,
        evidence_dir=evidence_dir,
    )
    claims = build_claims_from_facts_v081(facts=facts, evidence_items=evidence)
    narrative = build_narrative_v081(report_md=report_md, claims=claims, evidence=evidence)
    bundle_id = stable_json_hash({"e": [e["evidence_id"] for e in evidence], "c": [c["claim_id"] for c in claims]})[:12]
    return {
        "version": "0.8.1",
        "bundle_id": f"ab_{bundle_id}",
        "generated_at_utc": _utc_now_iso(),
        "evidence": evidence,
        "claims": claims,
        "narrative": narrative,
    }
