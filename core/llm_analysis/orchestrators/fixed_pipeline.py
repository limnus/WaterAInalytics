from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List

from core.llm_analysis.config import AnalysisConfig
from core.llm_analysis.models import AnalysisRunResult, AuditTrail, ReportArtifact
from core.llm_analysis.cache.keying import build_cache_key, stable_json_hash
from core.llm_analysis.cache.store import load_json, save_json
from core.llm_analysis.web_context.models import QueryPlan, SourceDoc, Snippet
from core.llm_analysis.web_context.collector import collect_web_context
from core.llm_analysis.extraction.models import FactBundle, FactItem, FactEvidence
from core.llm_analysis.extraction.fact_extractor import extract_facts_rule_based
from core.llm_analysis.report.generator import generate_report_md
from core.llm_analysis.forecast_integration.models import ForecastContext


class FixedPipelineOrchestrator:
    """Deterministic MVP orchestrator (no agent framework)."""

    def run(self, cfg: AnalysisConfig, forecast_ctx: ForecastContext, cache_root: Path) -> AnalysisRunResult:
        t0 = time.time()

        # More focused query plan (reduces irrelevant "forecast drivers" business content)
        query_plan = QueryPlan(
            queries=[
                f"{forecast_ctx.station_id} site:waterdata.usgs.gov",
                f"{forecast_ctx.station_id} USGS NWIS site_no",
                f"{forecast_ctx.station_id} monitoring location USGS",
                "USGS Water Services API instantaneous values iv service",
                "USGS Water Services API daily values dv service",
                "USGS how can I obtain river forecasts flood forecasts",
                f"{forecast_ctx.station_id} discharge streamflow gage height",
            ],
            notes="MVP query plan (USGS/hydrology-focused).",
        )
        query_plan_hash = stable_json_hash({"queries": query_plan.queries, "notes": query_plan.notes})

        cache_payload = {
            "station_id": forecast_ctx.station_id,
            "parameter": forecast_ctx.parameter,
            "run_date_local": forecast_ctx.run_datetime_utc.date().isoformat(),
            "model_key": forecast_ctx.provenance.model_key,
            "forecast_output_hash": forecast_ctx.provenance.forecast_output_hash,
            "schema_version": cfg.schema_version,
            "query_plan_hash": query_plan_hash,
            "max_pages": cfg.page_policy.max_pages,
            "tone": cfg.report_style.tone,
            "max_snippets_per_page": cfg.page_policy.max_snippets_per_page,
            "max_chars_per_page": cfg.page_policy.max_chars_per_page,
            "collector_opts": cfg.collector_opts or {},
        }
        cache_key = build_cache_key(cache_payload)

        run_dir = (
            cache_root
            / "agentic_analysis"
            / forecast_ctx.station_id
            / forecast_ctx.parameter
            / cache_payload["run_date_local"]
            / cache_key
        )
        report_path = run_dir / "report.md"
        facts_path = run_dir / "facts.json"
        sources_path = run_dir / "sources.json"
        snippets_path = run_dir / "snippets.jsonl"
        audit_path = run_dir / "audit.json"

        # -------------------------
        # Cache hit
        # -------------------------
        if cfg.use_cache and not cfg.force_refresh and report_path.exists() and facts_path.exists() and sources_path.exists():
            facts_obj = load_json(facts_path) or {}
            sources_obj = load_json(sources_path) or {}
            audit_obj = load_json(audit_path) or {}

            # Sources
            sources: List[SourceDoc] = [SourceDoc(**s) for s in sources_obj.get("sources", [])]

            # Snippets (best-effort)
            snippets: List[Snippet] = []
            if snippets_path.exists():
                try:
                    for line in snippets_path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        snippets.append(Snippet(**json.loads(line)))
                except Exception:
                    snippets = []

            # Facts (full load)
            facts_list = []
            for f in facts_obj.get("facts", []) or []:
                evs = [FactEvidence(**e) for e in (f.get("evidence", []) or [])]
                f2 = dict(f)
                f2["evidence"] = evs
                facts_list.append(FactItem(**f2))

            facts = FactBundle(
                schema_version=facts_obj.get("schema_version", cfg.schema_version),
                station_id=facts_obj.get("station_id", forecast_ctx.station_id),
                parameter=facts_obj.get("parameter", forecast_ctx.parameter),
                run_datetime_utc=facts_obj.get("run_datetime_utc", forecast_ctx.run_datetime_utc.isoformat()),
                facts=facts_list,
                summary=facts_obj.get("summary", {}),
            )

            report = ReportArtifact(
                format="markdown",
                content=report_path.read_text(encoding="utf-8"),
                sources_bibliography=[],
            )

            return AnalysisRunResult(
                cache_key=cache_key,
                created_at_utc=audit_obj.get("created_at_utc", forecast_ctx.run_datetime_utc.isoformat()),
                forecast_context=forecast_ctx,
                query_plan=query_plan,
                sources=sources,
                snippets=snippets,
                facts=facts,
                report=report,
                audit=AuditTrail(
                    llm=audit_obj.get("llm", {}),
                    timing_ms=audit_obj.get("timing_ms", {}),
                    warnings=audit_obj.get("warnings", []),
                ),
            )

        # -------------------------
        # Cache miss -> collect web
        # -------------------------
        sources, snippets, used_pages = collect_web_context(
            cfg=cfg,
            forecast_ctx=forecast_ctx,
            query_plan=query_plan,
        )

        # -------------------------
        # Facts (rule-based MVP)
        # -------------------------
        facts = extract_facts_rule_based(
            cfg=cfg,
            forecast_ctx=forecast_ctx,
            sources=sources,
            snippets=snippets,
        )

        report = generate_report_md(
            style=cfg.report_style,
            forecast=forecast_ctx,
            facts=facts,
            sources=sources,
            used_pages=used_pages,
            max_pages=cfg.page_policy.max_pages,
        )

        created_at = forecast_ctx.run_datetime_utc.isoformat()
        timing_ms = {"total": int((time.time() - t0) * 1000)}

        # -------------------------
        # Persist audit artifacts
        # -------------------------
        run_dir.mkdir(parents=True, exist_ok=True)

        save_json(sources_path, {"sources": [s.__dict__ for s in sources]})

        with snippets_path.open("w", encoding="utf-8") as f:
            for sn in snippets:
                f.write(json.dumps(sn.__dict__, ensure_ascii=False) + "\n")

        # Persist full facts structure (including evidence)
        save_json(
            facts_path,
            {
                "schema_version": facts.schema_version,
                "station_id": facts.station_id,
                "parameter": facts.parameter,
                "run_datetime_utc": facts.run_datetime_utc,
                "facts": [
                    {
                        **fi.__dict__,
                        "evidence": [e.__dict__ for e in fi.evidence],
                    }
                    for fi in facts.facts
                ],
                "summary": facts.summary,
            },
        )

        report_path.write_text(report.content, encoding="utf-8")
        save_json(
            audit_path,
            {
                "created_at_utc": created_at,
                "llm": {"provider": None, "model": None, "prompt_hashes": {}},
                "timing_ms": timing_ms,
                "warnings": [],
            },
        )

        return AnalysisRunResult(
            cache_key=cache_key,
            created_at_utc=created_at,
            forecast_context=forecast_ctx,
            query_plan=query_plan,
            sources=sources,
            snippets=snippets,
            facts=facts,
            report=report,
            audit=AuditTrail(
                llm={"provider": None, "model": None, "prompt_hashes": {}},
                timing_ms=timing_ms,
                warnings=[],
            ),
        )
