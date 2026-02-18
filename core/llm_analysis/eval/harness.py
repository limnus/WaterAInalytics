from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .schema import EvalCase, EvalConfig, load_cases, _as_path
from .metrics import (
    CaseMetrics,
    LabeledMetrics,
    aggregate_metrics,
    compute_case_metrics,
    compute_labeled_metrics,
)


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def _load_labels(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        return [dict(row) for row in r]


def _claims_to_label_rows(case: EvalCase, run: Dict[str, Any]) -> List[Dict[str, Any]]:
    artifacts = run.get("artifacts") or {}
    claims = artifacts.get("claims") or []
    evidence = artifacts.get("evidence") or []

    # quick lookup of evidence -> quality flags
    ev_qf: Dict[str, List[str]] = {}
    for e in evidence:
        ev_id = str(e.get("evidence_id") or "")
        if not ev_id:
            continue
        ev_qf[ev_id] = [str(x) for x in (e.get("quality_flags") or [])]

    rows: List[Dict[str, Any]] = []
    for c in claims:
        eids = [str(x) for x in (c.get("evidence_ids") or [])]
        qflags: List[str] = []
        for eid in eids:
            qflags.extend(ev_qf.get(eid, []))

        rows.append(
            {
                "case_id": case.case_id,
                "run_id": str(run.get("run_id") or ""),
                "schema_version": str(run.get("schema_version") or ""),
                "claim_id": str(c.get("claim_id") or ""),
                "claim_type": str(c.get("claim_type") or ""),
                "uncertainty_level": str(c.get("uncertainty_level") or ""),
                "support_score": c.get("support_score"),
                "title": str(c.get("title") or ""),
                "text": str(c.get("text") or ""),
                "evidence_count": len(eids),
                "quality_flags": ";".join(sorted(set(qflags))) if qflags else "",
                # label columns (to be filled by human)
                "label": "",
                "reason": "",
            }
        )

    return rows


def run_evaluation(cfg: EvalConfig, base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Run evaluation.

    Produces:
    - out_dir/claims_to_label.csv
    - out_dir/metrics.json

    If labels_csv exists, also produces:
    - out_dir/labeled_metrics.json

    base_dir is used to resolve relative run_json paths.
    """

    base_dir = base_dir or cfg.cases_path.parent
    cases = load_cases(cfg.cases_path)

    all_case_metrics: List[Dict[str, Any]] = []
    all_label_rows: List[Dict[str, Any]] = []

    for case in cases:
        run_path = _as_path(case.run_json, base_dir)
        run = _read_json(run_path)

        cm = compute_case_metrics(case.case_id, run)
        all_case_metrics.append(cm.__dict__)

        # export claims to label
        if run.get("artifacts"):
            all_label_rows.extend(_claims_to_label_rows(case, run))

    # Write claims_to_label.csv
    fieldnames = [
        "case_id",
        "run_id",
        "schema_version",
        "claim_id",
        "claim_type",
        "uncertainty_level",
        "support_score",
        "title",
        "text",
        "evidence_count",
        "quality_flags",
        "label",
        "reason",
    ]
    _write_csv(cfg.out_dir / "claims_to_label.csv", all_label_rows, fieldnames)

    # Aggregate metrics
    agg = aggregate_metrics(all_case_metrics)
    agg_obj: Dict[str, Any] = {
        "n_cases": agg.n_cases,
        "aggregate": agg.__dict__,
        "cases": all_case_metrics,
    }
    _write_json(cfg.out_dir / "metrics.json", agg_obj)

    out: Dict[str, Any] = {"metrics": agg_obj, "claims_to_label": str(cfg.out_dir / "claims_to_label.csv")}

    # Optional labeled metrics
    if cfg.labels_csv is not None and cfg.labels_csv.exists():
        labels = _load_labels(cfg.labels_csv)
        lm = compute_labeled_metrics(labels)
        _write_json(cfg.out_dir / "labeled_metrics.json", lm.__dict__)
        out["labeled_metrics"] = lm.__dict__

    return out
