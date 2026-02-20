import json
from pathlib import Path
import argparse
import os


def scan_runs(root: Path):
    if not root.exists():
        return []
    return list(root.rglob("run.json"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan-cache", action="store_true")
    parser.add_argument("--root", default=None, help="Root folder to scan for run.json (defaults to TEMP).")
    parser.add_argument("--out", default="eval/out", help="Output folder for metrics.")
    args = parser.parse_args()

    root = Path(args.root) if args.root else Path(os.getenv("TEMP", "."))
    runs = scan_runs(root) if args.scan_cache else []

    metrics = []
    for rp in runs:
        try:
            data = json.loads(rp.read_text(encoding="utf-8"))
            llm = (data.get("artifacts") or {}).get("llm_report")
            if not isinstance(llm, dict):
                continue
            if llm.get("llm_report_schema") != "0.9.1":
                continue
            val = llm.get("validation") or {}
            metrics.append({
                "run_path": str(rp),
                "citation_coverage": val.get("citation_coverage"),
                "missing_citations_count": val.get("missing_citations_count"),
                "unknown_claim_ids_count": val.get("unknown_claim_ids_count"),
                "unknown_evidence_ids_count": val.get("unknown_evidence_ids_count"),
            })
        except Exception:
            pass

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "llm_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"LLM evaluation complete. Runs scanned: {len(runs)}. Reports (0.9.1): {len(metrics)}.")
    print(f"Wrote: {out_dir / 'llm_metrics.json'}")


if __name__ == "__main__":
    main()
