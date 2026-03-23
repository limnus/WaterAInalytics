from __future__ import annotations

import json
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class StageTelemetry:
    stage: str
    started_at_perf: float = field(default_factory=time.perf_counter)
    duration_ms: int | None = None
    status: str = "running"
    detail: str = ""

    def finish(self, *, status: str = "ok", detail: str = "") -> None:
        self.duration_ms = int(round((time.perf_counter() - self.started_at_perf) * 1000.0))
        self.status = status
        self.detail = detail


def start_stage(stage: str) -> StageTelemetry:
    return StageTelemetry(stage=stage)


def finalize_stage(telemetry: StageTelemetry, *, status: str = "ok", detail: str = "") -> Dict[str, Any]:
    telemetry.finish(status=status, detail=detail)
    return {
        "stage": telemetry.stage,
        "duration_ms": telemetry.duration_ms or 0,
        "status": telemetry.status,
        "detail": telemetry.detail,
    }


def summarize_stage_timings(stage_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    stages = []
    total_ms = 0
    slowest: Dict[str, Any] | None = None

    for event in stage_events:
        row = {
            "stage": str(event.get("stage") or "unknown"),
            "duration_ms": int(event.get("duration_ms") or 0),
            "status": str(event.get("status") or "unknown"),
            "detail": str(event.get("detail") or "").strip(),
        }
        total_ms += row["duration_ms"]
        stages.append(row)
        if slowest is None or row["duration_ms"] > slowest["duration_ms"]:
            slowest = row

    return {
        "stage_count": len(stages),
        "total_duration_ms": total_ms,
        "slowest_stage": slowest,
        "stages": stages,
    }


def _agentic_log_path() -> Path:
    out_dir = Path(tempfile.gettempdir()) / "waterainalytics_agentic_logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "agentic_execution_log.jsonl"


def append_agentic_execution_log(record: Dict[str, Any]) -> Path:
    path = _agentic_log_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def build_agentic_execution_record(
    *,
    role: str | None,
    station_id: str,
    execution_surface: str,
    include_station_context: bool,
    force_refresh: bool,
    focus_text_present: bool,
    status: str,
    timing_summary: Dict[str, Any],
    warnings: List[str] | None = None,
    error: str | None = None,
) -> Dict[str, Any]:
    return {
        "role": (role or "").strip().lower() or "unknown",
        "station_id": station_id,
        "execution_surface": execution_surface,
        "include_station_context": bool(include_station_context),
        "force_refresh": bool(force_refresh),
        "focus_text_present": bool(focus_text_present),
        "status": status,
        "warnings": list(warnings or []),
        "error": error,
        "timing": timing_summary,
        "recorded_at_epoch_ms": int(time.time() * 1000),
    }
