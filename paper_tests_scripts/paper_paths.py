from __future__ import annotations

from pathlib import Path
from typing import Dict


def build_run_paths(output_root: str, run_tag: str) -> Dict[str, str]:
    run_root = Path(output_root) / run_tag
    paths = {
        "run_root": str(run_root),
        "frozen_data_root": str(run_root / "frozen_data"),
        "trained_models_root": str(run_root / "trained_models"),
        "backtests_root": str(run_root / "backtests"),
        "backtests_chronos_family_root": str(run_root / "backtests_chronos_family"),
        "deterministic_reports_root": str(run_root / "deterministic_reports"),
        "tables_root": str(run_root / "tables"),
        "figures_root": str(run_root / "figures"),
        "manifests_root": str(run_root / "manifests"),
    }
    return paths


def ensure_run_paths(paths: Dict[str, str]) -> None:
    for p in paths.values():
        Path(p).mkdir(parents=True, exist_ok=True)


def per_origin_dir(backtests_root: str, case_key: str, model_key: str, origin_stamp: str) -> Path:
    safe = origin_stamp.replace(":", "-")
    return Path(backtests_root) / "per_origin" / case_key / model_key / safe


def per_origin_family_dir(backtests_root: str, case_key: str, model_key: str, origin_stamp: str) -> Path:
    safe = origin_stamp.replace(":", "-")
    return Path(backtests_root) / "per_origin" / case_key / model_key / safe
