from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.release.manifest import (
    DEFAULT_RELEASE_REPORT_PATH,
    build_release_manifest,
    run_release_smoke_checks,
    write_release_smoke_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run machine-readable release smoke checks for WaterAInalytics."
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(DEFAULT_RELEASE_REPORT_PATH),
        help="Path to the JSON report to write.",
    )
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Write only the release manifest, without import smoke checks.",
    )
    args = parser.parse_args(argv)

    if args.manifest_only:
        payload = {"manifest": build_release_manifest()}
    else:
        payload = run_release_smoke_checks()

    output_path = write_release_smoke_report(payload, args.output)
    print(f"Saved release report: {output_path}")
    print(json.dumps(payload.get("summary") or {"manifest_only": True}, indent=2, ensure_ascii=False))

    if args.manifest_only:
        return 0
    return 0 if payload.get("summary", {}).get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
