from __future__ import annotations

import json
from pathlib import Path

from core.ui.agentic_observability import (
    append_agentic_execution_log,
    build_agentic_execution_record,
    finalize_stage,
    start_stage,
    summarize_stage_timings,
)


def test_summarize_stage_timings_tracks_total_and_slowest() -> None:
    stage_a = start_stage("build_forecast_context")
    event_a = finalize_stage(stage_a, detail="station=01234567")

    stage_b = start_stage("deterministic_agentic_pipeline")
    event_b = finalize_stage(stage_b, status="warning", detail="cache miss")
    event_b["duration_ms"] = max(event_a["duration_ms"] + 10, 10)

    summary = summarize_stage_timings([event_a, event_b])

    assert summary["stage_count"] == 2
    assert summary["total_duration_ms"] >= event_a["duration_ms"] + event_b["duration_ms"]
    assert summary["slowest_stage"]["stage"] == "deterministic_agentic_pipeline"
    assert summary["slowest_stage"]["status"] == "warning"


def test_append_agentic_execution_log_writes_jsonl(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "core.ui.agentic_observability._agentic_log_path",
        lambda: tmp_path / "agentic_execution_log.jsonl",
    )

    record = build_agentic_execution_record(
        role="user",
        station_id="12345678",
        execution_surface="authenticated",
        include_station_context=True,
        force_refresh=False,
        focus_text_present=True,
        status="ok",
        timing_summary={"total_duration_ms": 42, "stages": []},
        warnings=["slow stage"],
    )
    out_path = append_agentic_execution_log(record)

    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8").strip())
    assert payload["station_id"] == "12345678"
    assert payload["status"] == "ok"
    assert payload["warnings"] == ["slow stage"]
