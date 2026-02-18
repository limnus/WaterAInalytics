from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class EvalCase:
    """A single evaluation unit.

    The harness is run.json-first to avoid depending on internal cache key logic.
    """

    case_id: str
    run_json: str  # path (relative or absolute) to a run.json

    # Optional expectations (kept minimal)
    expected_claim_types: Optional[List[str]] = None


@dataclass(frozen=True)
class EvalConfig:
    """Evaluation configuration."""

    cases_path: Path
    out_dir: Path

    # Optional human labels file (CSV). If missing, harness still produces artifacts to label.
    labels_csv: Optional[Path] = None


def _as_path(p: str, base: Path) -> Path:
    pp = Path(p)
    return pp if pp.is_absolute() else (base / pp)


def load_cases(cases_path: Path) -> List[EvalCase]:
    obj: Dict[str, Any] = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = obj.get("cases", [])
    out: List[EvalCase] = []

    for i, c in enumerate(cases):
        case_id = str(c.get("case_id") or f"case_{i:03d}")
        run_json = str(c.get("run_json") or "").strip()
        if not run_json:
            raise ValueError(f"Missing run_json for case_id={case_id}")
        ect = c.get("expected_claim_types")
        if ect is not None:
            ect = [str(x) for x in ect]
        out.append(EvalCase(case_id=case_id, run_json=run_json, expected_claim_types=ect))

    if not out:
        raise ValueError("No cases found in cases file.")
    return out
