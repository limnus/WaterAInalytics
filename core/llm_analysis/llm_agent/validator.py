from __future__ import annotations

from typing import Any, Dict, List, Set


def _collect_ids(items: List[Dict[str, Any]], key: str) -> Set[str]:
    out: Set[str] = set()
    for it in items:
        if isinstance(it, dict):
            v = it.get(key)
            if isinstance(v, str) and v:
                out.add(v)
    return out


def validate_llm_report(report: Dict[str, Any], *, claims: List[Dict[str, Any]], evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministic validation of citation references.

    Expects claim ids under 'claim_id' and evidence ids under 'evidence_id' (as stored by v0.8.x artifacts).
    LLM report items reference those via 'claim_ids' and 'evidence_ids' lists.
    """

    claim_ids: Set[str] = _collect_ids(claims, "claim_id")
    evidence_ids: Set[str] = _collect_ids(evidence, "evidence_id")

    missing = 0
    unknown_claim = 0
    unknown_evidence = 0
    total_items = 0

    def _iter_items(section_name: str) -> List[Dict[str, Any]]:
        items = report.get(section_name) or []
        return [x for x in items if isinstance(x, dict)]

    for sec in ("key_findings", "forecast_interpretation", "limitations"):
        for item in _iter_items(sec):
            total_items += 1
            c_ids = item.get("claim_ids") or []
            e_ids = item.get("evidence_ids") or []

            has_any = bool(c_ids) or bool(e_ids)
            if not has_any:
                missing += 1

            for cid in c_ids:
                if cid not in claim_ids:
                    unknown_claim += 1

            for eid in e_ids:
                if eid not in evidence_ids:
                    unknown_evidence += 1

    coverage = 0.0
    if total_items > 0:
        coverage = (total_items - missing) / total_items

    flags: list[str] = []
    if missing:
        flags.append("missing_citations")
    if unknown_claim:
        flags.append("unknown_claim_ids")
    if unknown_evidence:
        flags.append("unknown_evidence_ids")

    return {
        "missing_citations_count": int(missing),
        "unknown_claim_ids_count": int(unknown_claim),
        "unknown_evidence_ids_count": int(unknown_evidence),
        "citation_coverage": round(float(coverage), 4),
        "flags": flags,
    }
