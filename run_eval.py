"""CLI for evaluating deterministic Agentic AI artifacts (v0.8.x).

This tool is intentionally simple and safe:
- Reads cached run.json files
- Produces a CSV to label + metrics JSON
- Optionally computes labeled metrics if you provide labels.csv

Example
-------
python run_eval.py --cases eval/evaluation_cases.json --out eval/out

Cases file format
-----------------
{
  "cases": [
    {"case_id": "usgs_02430005", "run_json": "C:/.../run.json"},
    {"case_id": "another", "run_json": "../some/run.json"}
  ]
}
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from core.llm_analysis.eval.schema import EvalConfig
from core.llm_analysis.eval.harness import run_evaluation
from core.llm_analysis.eval.scan import scan_run_cache, write_cases_file


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate run.json artifacts (deterministic).")
    p.add_argument("--cases", default=None, help="Path to evaluation_cases.json")
    p.add_argument("--out", default=str(Path("eval") / "out"), help="Output directory")
    p.add_argument("--labels", default=None, help="Optional labels.csv (same columns as claims_to_label.csv)")

    # v0.8.2: convenience mode to avoid hand-maintaining cases
    p.add_argument(
        "--scan-cache",
        action="store_true",
        help="Scan the local cache for run.json files (safe, no network).",
    )
    p.add_argument(
        "--cache-root",
        default=None,
        help="Optional cache root. Default is the OS temp dir used by the app.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit on number of cases (0 = no limit).",
    )
    p.add_argument(
        "--filter-profile",
        default=None,
        help="Optional filter: query_profile must match (e.g., usgs).",
    )
    p.add_argument(
        "--write-cases",
        action="store_true",
        help="When scanning cache, print where cases.generated.json was written.",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    out_dir = Path(args.out)

    # Determine cases path
    if args.scan_cache:
        root = Path(args.cache_root) if args.cache_root else Path(tempfile.gettempdir())
        scan_root = root / "agentic_analysis"
        cases = scan_run_cache(
            scan_root=scan_root,
            limit=int(args.limit or 0),
            filter_profile=str(args.filter_profile).strip() if args.filter_profile else None,
        )
        if not cases:
            raise SystemExit(f"No run.json files found under: {scan_root}")
        cases_path = out_dir / "cases.generated.json"
        write_cases_file(cases_path, cases)
        if args.write_cases:
            print(f"cases.generated.json: {cases_path}")
    else:
        if not args.cases:
            raise SystemExit("--cases is required unless --scan-cache is provided")
        cases_path = Path(args.cases)

    cfg = EvalConfig(
        cases_path=cases_path,
        out_dir=out_dir,
        labels_csv=Path(args.labels) if args.labels else None,
    )
    res = run_evaluation(cfg)

    print("\n=== Evaluation complete ===")
    print(f"Cases: {res['metrics']['n_cases']}")
    print(f"claims_to_label.csv: {res['claims_to_label']}")
    if 'labeled_metrics' in res:
        lm = res['labeled_metrics']
        print("Labeled metrics:")
        print(f"  n_labeled: {lm.get('n_labeled')}")
        print(f"  precision: {lm.get('precision')}")


if __name__ == "__main__":
    main()
