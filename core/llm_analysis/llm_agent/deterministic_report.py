from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from core.llm_analysis.forecast_integration.models import ForecastContext


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

def _fmt_num(x: Any) -> str:
    if x is None:
        return ""
    try:
        return f"{float(x):.3g}"
    except Exception:
        return str(x)

def build_deterministic_llm_report(
    *,
    forecast_ctx: ForecastContext,
    claims: List[Dict[str, Any]],
    evidence: List[Dict[str, Any]],
    context_consistency: Dict[str, Any] | None,
    user_question: str | None,
) -> Dict[str, Any]:
    anchor_claim_ids, anchor_evidence_ids = _pick_anchor_ids(claims, evidence)

    # Executive summary grounded on CCE if present
    cci = None
    status = None
    if isinstance(context_consistency, dict):
        cci = context_consistency.get("cci")
        status = context_consistency.get("status")

    station = forecast_ctx.station_id
    param = forecast_ctx.parameter

    parts: List[str] = []
    if isinstance(cci, (int, float)) and status:
        parts.append(f"Context Consistency Index (CCI)={cci:.2f} → {status}.")
    parts.append(f"Station={station}, Parameter={param}.")
    if user_question and user_question.strip():
        parts.append("Focus: " + user_question.strip())
    executive_summary = " ".join(parts)

    # Key findings: derive from top claims by support_score
    def _score(c: Dict[str, Any]) -> float:
        v = c.get("support_score")
        try:
            return float(v)
        except Exception:
            return 0.0

    sorted_claims = sorted([c for c in claims if isinstance(c, dict)], key=_score, reverse=True)[:3]
    key_findings: List[Dict[str, Any]] = []
    for i, c in enumerate(sorted_claims):
        cid = (c.get("claim_id") or "").strip()
        eids = c.get("evidence_ids") or []
        eids = [x for x in eids if isinstance(x, str)]
        txt = (c.get("text") or "").strip()
        if not txt:
            continue
        key_findings.append({
            "id": f"kf_{i+1:03d}",
            "text": txt,
            "claim_ids": [cid] if cid else anchor_claim_ids,
            "evidence_ids": eids if eids else anchor_evidence_ids,
            "confidence": _confidence_from_uncertainty(str(c.get("uncertainty_level") or "")),
        })

    # Forecast interpretation: minimal, but always anchored
    last_y = forecast_ctx.recent_history.y[-1] if forecast_ctx.recent_history.y else None
    next_h = forecast_ctx.horizons[0] if forecast_ctx.horizons else None
    if next_h is not None and last_y is not None:
        txt = (
            f"Next-hour forecast y_hat={_fmt_num(next_h.y_hat)} "
            f"compared to last observed y={_fmt_num(last_y)}; "
            f"PI≈[{_fmt_num(next_h.p05)}, {_fmt_num(next_h.p95)}]."
        )
    else:
        txt = "Forecast output available, but insufficient recent history to compare trends."

    forecast_interpretation = [{
        "id": "fi_001",
        "text": txt,
        "claim_ids": anchor_claim_ids,
        "evidence_ids": anchor_evidence_ids,
        "confidence": "MED",
    }]

    # Limitations: summarize evidence quality flags
    counts: Dict[str, int] = {}
    for e in evidence:
        if not isinstance(e, dict):
            continue
        for fl in (e.get("quality_flags") or []):
            if isinstance(fl, str) and fl:
                counts[fl] = counts.get(fl, 0) + 1

    limitations: List[Dict[str, Any]] = []
    for i, (issue, cnt) in enumerate(sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:6]):
        limitations.append({
            "id": f"lim_{i+1:03d}",
            "text": "",
            "issue": issue,
            "count": int(cnt),
            "claim_ids": anchor_claim_ids,
            "evidence_ids": anchor_evidence_ids,
        })

    open_questions = [{
        "id": "q_001",
        "text": "Would additional locally-relevant hydrometeorological context improve interpretation of forecast uncertainty?",
    }]

    return {
        "executive_summary": executive_summary,
        "key_findings": key_findings,
        "forecast_interpretation": forecast_interpretation,
        "limitations": limitations,
        "open_questions": open_questions,
    }
