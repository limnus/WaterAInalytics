from __future__ import annotations

import importlib
import json
import os
import platform
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import get_runtime_settings
from core.version import APP_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RELEASE_CHECKS_DIR = PROJECT_ROOT / "artifacts" / "release_checks"
DEFAULT_RELEASE_REPORT_PATH = RELEASE_CHECKS_DIR / "release_check_report.json"

REQUIRED_RELEASE_FILES = [
    "README.md",
    "CHANGELOG.md",
    ".env.example",
    ".gitattributes",
    "app.py",
    "run_pipeline.py",
    "docs/design/architecture.md",
    f"docs/REPRODUCIBILITY_{APP_VERSION}.md",
    f"docs/RUNBOOK_{APP_VERSION}.md",
    f"docs/CODE_FREEZE_CHECKLIST_{APP_VERSION}.md",
    f"docs/RELEASE_VALIDATION_{APP_VERSION}.md",
]

KEY_IMPORTS = [
    "core.version",
    "core.config",
    "core.release.manifest",
    "core.article_demo.presets",
    "core.article_demo.bundle",
    "core.llm_analysis.forecast_integration.adapter",
    "core.llm_analysis.llm_agent.quantitative_brief",
    "core.context_enrichment.official_us_context",
]

SUPPORTED_FORECAST_MODEL_KEYS = [
    "persistence",
    "ridge",
    "chronos-tiny",
    "chronos-mini",
    "chronos-base",
    "chronos-large",
]


def _safe_settings_summary() -> dict[str, Any]:
    settings = get_runtime_settings()
    payload = asdict(settings)
    return {
        "session_timeout_minutes": payload["session_timeout_minutes"],
        "playground_report_truncation_ratio": payload["playground_report_truncation_ratio"],
        "station_context_enrichment_enabled": payload["station_context_enrichment_enabled"],
        "station_context_timeout_s": payload["station_context_timeout_s"],
        "station_context_cache_days": payload["station_context_cache_days"],
        "auth_admin_initial_password_present": bool(payload["auth_admin_initial_password"]),
        "auth_admin_reset_password_present": bool(payload["auth_admin_reset_password"]),
    }


def _file_checks() -> dict[str, Any]:
    required = []
    missing = []
    for rel in REQUIRED_RELEASE_FILES:
        path = PROJECT_ROOT / rel
        required.append({"path": rel, "exists": path.exists()})
        if not path.exists():
            missing.append(rel)
    station_base = PROJECT_ROOT / "data" / "usgs_00060_00065_base_from_ts_metadata.csv"
    return {
        "required": required,
        "missing": missing,
        "optional": [
            {
                "path": "data/usgs_00060_00065_base_from_ts_metadata.csv",
                "exists": station_base.exists(),
                "purpose": "official station context enrichment seed table",
            }
        ],
    }


def _import_checks() -> dict[str, Any]:
    checks = []
    failures = []
    for name in KEY_IMPORTS:
        try:
            importlib.import_module(name)
            ok = True
            error = None
        except Exception as exc:  # pragma: no cover
            ok = False
            error = f"{type(exc).__name__}: {exc}"
            failures.append({"module": name, "error": error})
        checks.append({"module": name, "ok": ok, "error": error})
    return {"modules": checks, "failures": failures}


def build_release_manifest() -> dict[str, Any]:
    return {
        "app_version": APP_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(PROJECT_ROOT),
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": os.getenv("PYTHON_EXECUTABLE_OVERRIDE", ""),
        },
        "forecast_models": {
            "supported_model_keys": SUPPORTED_FORECAST_MODEL_KEYS,
            "deterministic_outputs_schema": "forecast_run.json + forecast.csv",
            "manuscript_support_artifacts": [
                "experiment_summary.json",
                "experiment_summary.csv",
            ],
            "ridge_required_artifacts": [
                "meta.json",
                "weights.npz",
                "training_manifest.json",
            ],
        },
        "article_demo": {
            "strict_model_validation": True,
            "multiple_presets": True,
            "main_preset_parameter": "00060",
            "supplementary_quality_parameter": "63680",
        },
        "agentic_analysis": {
            "deterministic_quantitative_brief": True,
            "official_station_context_enrichment": True,
            "optional_llm_refinement": True,
            "playground_output_truncation": True,
            "narrative_sections": [
                "observed_facts",
                "inferences",
                "alerts",
                "limitations",
            ],
        },
        "runtime_settings": _safe_settings_summary(),
        "files": _file_checks(),
    }


def run_release_smoke_checks() -> dict[str, Any]:
    manifest = build_release_manifest()
    import_results = _import_checks()
    file_missing = list(manifest.get("files", {}).get("missing", []))
    import_failures = list(import_results.get("failures", []))

    passed = not file_missing and not import_failures
    summary = {
        "passed": passed,
        "missing_required_files": file_missing,
        "import_failures": import_failures,
        "required_file_count": len(manifest.get("files", {}).get("required", [])),
        "checked_import_count": len(import_results.get("modules", [])),
    }
    return {
        "summary": summary,
        "manifest": manifest,
        "imports": import_results,
    }


def write_release_smoke_report(report: dict[str, Any], output_path: str | Path | None = None) -> Path:
    path = Path(output_path) if output_path else DEFAULT_RELEASE_REPORT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
