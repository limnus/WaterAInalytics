from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schema import EvalCase


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def scan_run_cache(
    scan_root: Path,
    limit: int = 0,
    filter_profile: Optional[str] = None,
) -> List[EvalCase]:
    """Scan the cache for run.json files.

    This is intentionally conservative:
    - No network
    - Only looks for files named 'run.json'
    - Filters are evaluated by reading the run.json payload

    The app's default cache location is: tempfile.gettempdir()/agentic_analysis/...
    """

    if not scan_root.exists():
        return []

    # Deterministic ordering by path
    paths = sorted(scan_root.rglob("run.json"), key=lambda p: str(p).lower())
    out: List[EvalCase] = []

    for p in paths:
        try:
            run = _read_json(p)
        except Exception:
            continue

        if filter_profile:
            qp = str(run.get("query_profile") or "").strip().lower()
            if qp != filter_profile.strip().lower():
                continue

        run_id = str(run.get("run_id") or "").strip()
        case_id = run_id if run_id else p.parent.name
        out.append(EvalCase(case_id=case_id, run_json=str(p)))

        if limit and len(out) >= int(limit):
            break

    return out


def write_cases_file(path: Path, cases: List[EvalCase]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    obj = {"cases": [asdict(c) for c in cases]}
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
