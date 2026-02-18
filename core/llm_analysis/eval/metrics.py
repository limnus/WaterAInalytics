from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class CaseMetrics:
    case_id: str
    run_id: str
    schema_version: str

    n_sources: int
    n_evidence: int
    n_claims: int

    unsupported_claims: int  # claims with empty evidence_ids
    missing_artifacts: bool

    uncertainty_counts: Dict[str, int]
    claim_type_counts: Dict[str, int]
    quality_flag_counts: Dict[str, int]


@dataclass(frozen=True)
class AggregateMetrics:
    n_cases: int
    n_sources: int
    n_evidence: int
    n_claims: int
    unsupported_claims: int
    missing_artifacts_cases: int

    uncertainty_counts: Dict[str, int]
    claim_type_counts: Dict[str, int]
    quality_flag_counts: Dict[str, int]


def _inc(d: Dict[str, int], k: str, by: int = 1) -> None:
    d[k] = int(d.get(k, 0)) + int(by)


def compute_case_metrics(case_id: str, run: Dict[str, Any]) -> CaseMetrics:
    run_id = str(run.get("run_id") or "")
    schema_version = str(run.get("schema_version") or "")

    sources = run.get("sources_summary") or []
    n_sources = len(sources)

    artifacts = run.get("artifacts")
    missing_artifacts = artifacts is None

    evidence = []
    claims = []
    qflags: Dict[str, int] = {}
    ucounts: Dict[str, int] = {}
    tcounts: Dict[str, int] = {}

    if not missing_artifacts:
        evidence = (artifacts.get("evidence") or []) if isinstance(artifacts, dict) else []
        claims = (artifacts.get("claims") or []) if isinstance(artifacts, dict) else []

        for e in evidence:
            for f in (e.get("quality_flags") or []):
                _inc(qflags, str(f))

        for c in claims:
            _inc(tcounts, str(c.get("claim_type") or "unknown"))
            _inc(ucounts, str(c.get("uncertainty_level") or "UNK"))

    unsupported = 0
    for c in claims:
        eids = c.get("evidence_ids") or []
        if not eids:
            unsupported += 1

    return CaseMetrics(
        case_id=case_id,
        run_id=run_id,
        schema_version=schema_version,
        n_sources=n_sources,
        n_evidence=len(evidence),
        n_claims=len(claims),
        unsupported_claims=unsupported,
        missing_artifacts=missing_artifacts,
        uncertainty_counts=ucounts,
        claim_type_counts=tcounts,
        quality_flag_counts=qflags,
    )


def aggregate_metrics(case_metrics: List[Dict[str, Any]]) -> AggregateMetrics:
    """Aggregate a list of CaseMetrics dicts.

    Kept intentionally small and transparent (no stats inference).
    """

    uc: Dict[str, int] = {}
    tc: Dict[str, int] = {}
    qc: Dict[str, int] = {}

    n_sources = 0
    n_evidence = 0
    n_claims = 0
    unsupported = 0
    missing = 0

    for cm in case_metrics:
        n_sources += int(cm.get("n_sources") or 0)
        n_evidence += int(cm.get("n_evidence") or 0)
        n_claims += int(cm.get("n_claims") or 0)
        unsupported += int(cm.get("unsupported_claims") or 0)
        missing += 1 if cm.get("missing_artifacts") else 0

        for k, v in (cm.get("uncertainty_counts") or {}).items():
            _inc(uc, str(k), int(v))
        for k, v in (cm.get("claim_type_counts") or {}).items():
            _inc(tc, str(k), int(v))
        for k, v in (cm.get("quality_flag_counts") or {}).items():
            _inc(qc, str(k), int(v))

    return AggregateMetrics(
        n_cases=len(case_metrics),
        n_sources=n_sources,
        n_evidence=n_evidence,
        n_claims=n_claims,
        unsupported_claims=unsupported,
        missing_artifacts_cases=missing,
        uncertainty_counts=dict(sorted(uc.items())),
        claim_type_counts=dict(sorted(tc.items())),
        quality_flag_counts=dict(sorted(qc.items())),
    )


@dataclass(frozen=True)
class LabeledMetrics:
    """Metrics computed when labels.csv is provided."""

    n_labeled: int
    n_correct: int
    n_incorrect: int
    n_inconclusive: int

    precision: Optional[float]


def compute_labeled_metrics(rows: List[Dict[str, str]]) -> LabeledMetrics:
    # labels expected: CORRECT / INCORRECT / INCONCLUSIVE
    n = len(rows)
    c = sum(1 for r in rows if (r.get("label") or "").strip().upper() == "CORRECT")
    ic = sum(1 for r in rows if (r.get("label") or "").strip().upper() == "INCORRECT")
    inc = sum(1 for r in rows if (r.get("label") or "").strip().upper() == "INCONCLUSIVE")

    denom = c + ic
    precision = (c / denom) if denom > 0 else None

    return LabeledMetrics(
        n_labeled=n,
        n_correct=c,
        n_incorrect=ic,
        n_inconclusive=inc,
        precision=precision,
    )
