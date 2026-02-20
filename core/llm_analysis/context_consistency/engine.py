from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from core.llm_analysis.forecast_integration.models import ForecastContext


_AUTH_WEIGHTS = {
    "gov": 1.00,
    "edu": 0.85,
    "org": 0.70,
    "com": 0.55,
    "other": 0.40,
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def _as_list(x: Any, wrapped_key: str) -> List[Dict[str, Any]]:
    if x is None:
        return []
    if isinstance(x, list):
        return [it for it in x if isinstance(it, dict)]
    if isinstance(x, dict):
        v = x.get(wrapped_key)
        if isinstance(v, list):
            return [it for it in v if isinstance(it, dict)]
    return []


def _authority_score(evidence: List[Dict[str, Any]]) -> float:
    if not evidence:
        return 0.0
    ws = []
    for e in evidence:
        cls = (e.get("source_class") or e.get("class") or e.get("source_type") or "").strip().lower()
        ws.append(_AUTH_WEIGHTS.get(cls, _AUTH_WEIGHTS["other"]))
    return float(sum(ws) / max(len(ws), 1))


def _quality_score(evidence: List[Dict[str, Any]]) -> Tuple[float, List[Dict[str, Any]]]:
    # Penalize objective quality flags; caps prevent runaway penalties.
    counts: Dict[str, int] = {}
    for e in evidence:
        for f in (e.get("quality_flags") or e.get("flags") or []):
            if isinstance(f, str) and f:
                counts[f] = counts.get(f, 0) + 1

    p = 0.0
    # Common flags in this project
    p += min(0.25, 0.03 * counts.get("no_published_date", 0))
    p += min(0.30, 0.10 * counts.get("truncated_content", 0))
    p += min(0.20, 0.05 * counts.get("cache_miss", 0))

    q = _clamp(1.0 - p)

    risk_flags: List[Dict[str, Any]] = []
    if counts.get("no_published_date", 0) > 0:
        risk_flags.append({"code": "NO_PUBLISHED_DATE", "severity": "LOW", "count": counts["no_published_date"]})
    if counts.get("truncated_content", 0) > 0:
        risk_flags.append({"code": "TRUNCATED_CONTENT", "severity": "MED", "count": counts["truncated_content"]})
    if counts.get("cache_miss", 0) > 0:
        risk_flags.append({"code": "CACHE_MISS", "severity": "LOW", "count": counts["cache_miss"]})

    return q, risk_flags


def _claim_support_score(claims: List[Dict[str, Any]]) -> float:
    if not claims:
        return 0.0
    vals = []
    for c in claims:
        v = c.get("support_score")
        if isinstance(v, (int, float)):
            vals.append(float(v))
    if not vals:
        return 0.0
    return _clamp(float(sum(vals) / len(vals)))


def _coverage_score(claims: List[Dict[str, Any]]) -> float:
    if not claims:
        return 0.0
    anchored = 0
    total = 0
    for c in claims:
        total += 1
        ev = c.get("evidence_ids") or []
        if isinstance(ev, list) and any(isinstance(x, str) and x for x in ev):
            anchored += 1
    if total == 0:
        return 0.0
    return float(anchored / total)


def _forecast_sanity_score(fc: ForecastContext) -> Tuple[float, List[Dict[str, Any]]]:
    # Simple anomaly proxy using recent variability.
    risk_flags: List[Dict[str, Any]] = []
    y_hist = [float(x) for x in (fc.recent_history.y or []) if isinstance(x, (int, float))]
    if len(y_hist) < 5 or not (fc.horizons or []):
        return 0.5, [{"code": "INSUFFICIENT_HISTORY", "severity": "LOW", "count": len(y_hist)}]

    y_last = y_hist[-1]
    y_next = float(fc.horizons[0].y_hat)

    window = y_hist[-24:] if len(y_hist) >= 24 else y_hist
    # Robust-ish std
    try:
        import statistics
        std = statistics.pstdev(window)
    except Exception:
        std = 0.0

    delta = abs(y_next - y_last)

    if std <= 1e-9:
        # fallback: relative change
        denom = abs(y_last) if abs(y_last) > 1e-9 else 1.0
        rel = delta / denom
        if rel <= 0.10:
            f = 1.0
        elif rel <= 0.25:
            f = 0.7
        elif rel <= 0.50:
            f = 0.4
        else:
            f = 0.2
    else:
        r = delta / std
        if r <= 1.0:
            f = 1.0
        elif r <= 2.0:
            f = 0.7
        elif r <= 3.0:
            f = 0.4
        else:
            f = 0.2

    if f <= 0.2:
        risk_flags.append({"code": "FORECAST_ANOMALY", "severity": "HIGH", "value": round(float(delta), 6)})
    elif f <= 0.4:
        risk_flags.append({"code": "FORECAST_SHIFT", "severity": "MED", "value": round(float(delta), 6)})

    return f, risk_flags


def compute_context_consistency(
    *,
    artifacts: Dict[str, Any] | None,
    forecast_ctx: ForecastContext,
) -> Dict[str, Any]:
    """Compute Context Consistency Index (CCI) deterministically.

    Works for both v0.8.0 and v0.8.1 artifact shapes.
    """

    artifacts = artifacts or {}

    evidence = _as_list(artifacts.get("evidence"), wrapped_key="sources")
    claims = _as_list(artifacts.get("claims"), wrapped_key="items")

    A = _authority_score(evidence)
    Q, flags_q = _quality_score(evidence)
    S = _claim_support_score(claims)
    C = _coverage_score(claims)
    F, flags_f = _forecast_sanity_score(forecast_ctx)

    # weights (fixed for v0.9.1)
    wA, wQ, wS, wF, wC = 0.20, 0.20, 0.25, 0.25, 0.10
    cci = _clamp(wA*A + wQ*Q + wS*S + wF*F + wC*C)

    status = "GREEN" if cci >= 0.80 else "YELLOW" if cci >= 0.60 else "RED"

    risk_flags = flags_q + flags_f
    if C < 0.5:
        risk_flags.append({"code": "LOW_COVERAGE", "severity": "MED", "value": round(float(C), 4)})
    if len(claims) < 2:
        risk_flags.append({"code": "LOW_CLAIM_COUNT", "severity": "LOW", "count": int(len(claims))})

    # deterministic explanations (short, UI-friendly)
    explain: List[str] = []
    if A >= 0.85:
        explain.append("Evidence sources are predominantly authoritative (e.g., gov/edu).")
    else:
        explain.append("Evidence source authority is mixed; interpret context cautiously.")
    if Q < 0.8:
        explain.append("Evidence quality flags reduce confidence (e.g., missing published dates or truncated content).")
    if S < 0.6:
        explain.append("Extracted claims have limited support on average.")
    if F < 0.7:
        explain.append("Forecast shows a notable shift vs recent variability; potential anomaly.")
    if C < 0.8:
        explain.append("Not all claims are anchored to explicit evidence IDs (coverage gap).")

    return {
        "cce_schema": "0.9.1",
        "cci": round(float(cci), 4),
        "status": status,
        "components": {
            "data_authority": round(float(A), 4),
            "evidence_quality": round(float(Q), 4),
            "claim_support": round(float(S), 4),
            "forecast_sanity": round(float(F), 4),
            "coverage": round(float(C), 4),
        },
        "risk_flags": risk_flags,
        "explain": explain,
    }
