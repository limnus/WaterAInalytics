from __future__ import annotations

from typing import Any, Dict, List, Tuple

from core.llm_analysis.forecast_integration.models import ForecastContext

from .quantitative_brief import build_quantitative_forecast_brief


def _confidence_from_uncertainty(unc: str) -> str:
    u = (unc or "").strip().upper()
    if u == "LOW":
        return "HIGH"
    if u == "MED":
        return "MED"
    return "LOW"


def _pick_anchor_ids(claims: List[Dict[str, Any]], evidence: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    # Provide at least one valid id to satisfy validation rules.
    claim_id = ""
    if claims:
        for c in claims:
            cid = (c.get("claim_id") or "").strip()
            if cid:
                claim_id = cid
                break
    ev_id = ""
    if evidence:
        for e in evidence:
            eid = (e.get("evidence_id") or "").strip()
            if eid:
                ev_id = eid
                break
    claim_ids = [claim_id] if claim_id else []
    evidence_ids = [ev_id] if ev_id else []
    return claim_ids, evidence_ids


def _score(c: Dict[str, Any]) -> float:
    v = c.get("support_score")
    try:
        return float(v)
    except Exception:
        return 0.0


def build_deterministic_llm_report(
    *,
    forecast_ctx: ForecastContext,
    claims: List[Dict[str, Any]],
    evidence: List[Dict[str, Any]],
    context_consistency: Dict[str, Any] | None,
    user_question: str | None,
) -> Dict[str, Any]:
    anchor_claim_ids, anchor_evidence_ids = _pick_anchor_ids(claims, evidence)
    quantitative = build_quantitative_forecast_brief(forecast_ctx)

    cci = None
    status = None
    if isinstance(context_consistency, dict):
        cci = context_consistency.get("cci")
        status = context_consistency.get("status")

    summary_parts: List[str] = [quantitative["executive_summary"]]
    if isinstance(cci, (int, float)) and status:
        summary_parts.append(f"Context Consistency Index (CCI)={cci:.2f} → {status}.")
    if user_question and user_question.strip():
        summary_parts.append("Focus: " + user_question.strip())
    executive_summary = " ".join(part.strip() for part in summary_parts if part and str(part).strip())

    key_findings: List[Dict[str, Any]] = []
    for i, text in enumerate(quantitative.get("key_findings") or [], start=1):
        if not text:
            continue
        key_findings.append(
            {
                "id": f"kf_{i:03d}",
                "text": text,
                "claim_ids": anchor_claim_ids,
                "evidence_ids": anchor_evidence_ids,
                "confidence": "MED",
            }
        )

    remaining_slots = max(0, 4 - len(key_findings))
    sorted_claims = sorted([c for c in claims if isinstance(c, dict)], key=_score, reverse=True)[:remaining_slots]
    for idx, claim in enumerate(sorted_claims, start=len(key_findings) + 1):
        cid = (claim.get("claim_id") or "").strip()
        text = (claim.get("text") or "").strip()
        if not text:
            continue
        eids = [x for x in (claim.get("evidence_ids") or []) if isinstance(x, str)]
        key_findings.append(
            {
                "id": f"kf_{idx:03d}",
                "text": text,
                "claim_ids": [cid] if cid else anchor_claim_ids,
                "evidence_ids": eids if eids else anchor_evidence_ids,
                "confidence": _confidence_from_uncertainty(str(claim.get("uncertainty_level") or "")),
            }
        )

    forecast_interpretation: List[Dict[str, Any]] = []
    for i, text in enumerate((quantitative.get("inferences") or quantitative.get("forecast_interpretation") or []), start=1):
        if not text:
            continue
        forecast_interpretation.append(
            {
                "id": f"fi_{i:03d}",
                "text": text,
                "claim_ids": anchor_claim_ids,
                "evidence_ids": anchor_evidence_ids,
                "confidence": "MED",
            }
        )

    alerts: List[Dict[str, Any]] = []
    for i, text in enumerate(quantitative.get("alerts") or [], start=1):
        if not text:
            continue
        alerts.append(
            {
                "id": f"alr_{i:03d}",
                "text": text,
                "claim_ids": anchor_claim_ids,
                "evidence_ids": anchor_evidence_ids,
                "confidence": "MED",
            }
        )

    limitations: List[Dict[str, Any]] = []
    for i, text in enumerate(quantitative.get("limitations") or [], start=1):
        if not text:
            continue
        limitations.append(
            {
                "id": f"lim_{i:03d}",
                "text": text,
                "claim_ids": anchor_claim_ids,
                "evidence_ids": anchor_evidence_ids,
            }
        )

    counts: Dict[str, int] = {}
    for e in evidence:
        if not isinstance(e, dict):
            continue
        for fl in (e.get("quality_flags") or []):
            if isinstance(fl, str) and fl:
                counts[fl] = counts.get(fl, 0) + 1

    offset = len(limitations)
    for j, (issue, cnt) in enumerate(sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:6], start=1):
        limitations.append(
            {
                "id": f"lim_{offset + j:03d}",
                "text": f"Evidence quality flag '{issue}' appeared {int(cnt)} time(s) in the collected context.",
                "issue": issue,
                "count": int(cnt),
                "claim_ids": anchor_claim_ids,
                "evidence_ids": anchor_evidence_ids,
            }
        )

    open_questions = [
        {"id": f"q_{i:03d}", "text": text}
        for i, text in enumerate(quantitative.get("open_questions") or [], start=1)
        if text
    ]

    return {
        "executive_summary": executive_summary,
        "key_findings": key_findings,
        "forecast_interpretation": forecast_interpretation,
        "alerts": alerts,
        "limitations": limitations,
        "open_questions": open_questions,
        "quantitative_brief": quantitative,
    }
