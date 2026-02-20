from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import List

from core.llm_analysis.cache.keying import build_cache_key, stable_json_hash
from core.llm_analysis.cache.store import load_json, save_json
from core.llm_analysis.config import AnalysisConfig
from core.llm_analysis.extraction.models import FactBundle, FactEvidence, FactItem
from core.llm_analysis.forecast_integration.models import ForecastContext
from core.llm_analysis.models import AnalysisRunResult, AuditTrail, ReportArtifact
from core.llm_analysis.context_consistency import compute_context_consistency
from core.llm_analysis.artifacts.v08_artifacts import build_artifacts_bundle as build_artifacts_bundle_v080
from core.llm_analysis.artifacts.v081_artifacts import build_artifacts_bundle as build_artifacts_bundle_v081
from core.llm_analysis.tools.extract_tool import tool_extract_facts_rule_based
from core.llm_analysis.tools.plan_tool import tool_build_query_plan
from core.llm_analysis.tools.report_tool import tool_generate_report_md
from core.llm_analysis.tools.web_tool import tool_collect_web_context
from core.llm_analysis.web_context.models import QueryPlan, SourceDoc, Snippet


class FixedPipelineOrchestrator:
    """Deterministic orchestrator (no agent framework).

    v0.7.x notes:
      - Query templates are centralized in web_context/queries.py (planner-lite).
      - Pipeline steps are called via internal tools (LLM-ready but deterministic).
    """

    def run(self, cfg: AnalysisConfig, forecast_ctx: ForecastContext, cache_root: Path) -> AnalysisRunResult:
        t0 = time.time()

        run_id = str(uuid.uuid4())
        created_at_utc = forecast_ctx.run_datetime_utc.isoformat()
        budgets = {
            "max_pages": int(cfg.page_policy.max_pages),
            "max_snippets_per_page": int(cfg.page_policy.max_snippets_per_page),
            "max_chars_per_page": int(cfg.page_policy.max_chars_per_page),
        }

        # Planner-lite (deterministic, profile-aware)
        query_plan: QueryPlan = tool_build_query_plan(forecast_ctx=forecast_ctx, cfg=cfg)
        queries_tagged = [
            {"q": tq.q, "section": tq.section} for tq in (query_plan.tagged_queries or [])
        ]

        # Hash should be stable and methodology-relevant (tagged preferred, fallback to raw queries)
        query_plan_hash = stable_json_hash(
            {
                "profile": query_plan.profile,
                "queries_tagged": queries_tagged if queries_tagged else list(query_plan.queries),
                "notes": query_plan.notes,
            }
        )

        cache_payload = {
            "station_id": forecast_ctx.station_id,
            "parameter": forecast_ctx.parameter,
            "run_date_local": forecast_ctx.run_datetime_utc.date().isoformat(),
            "model_key": forecast_ctx.provenance.model_key,
            "forecast_output_hash": forecast_ctx.provenance.forecast_output_hash,
            "schema_version": cfg.schema_version,
            "query_plan_hash": query_plan_hash,
            "query_profile": query_plan.profile,
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
        run_path = run_dir / "run.json"
        evidence_dir = run_dir / "evidence"

        # -------------------------
        # Cache hit
        # -------------------------
        if cfg.use_cache and not cfg.force_refresh and report_path.exists() and facts_path.exists() and sources_path.exists():
            facts_obj = load_json(facts_path) or {}
            sources_obj = load_json(sources_path) or {}

            # v0.7.x: prefer run.json (richer). Fallback to audit.json for backward-compat.
            if run_path.exists():
                audit_obj = load_json(run_path) or {}
            else:
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
            facts_list: List[FactItem] = []
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

            # v0.8.0: structured artifacts (best-effort). Do not mutate cache on read.
            artifacts = audit_obj.get("artifacts")
            if artifacts is None:
                try:
                    artifacts = build_artifacts_bundle(
                        sources=sources,
                        snippets=snippets,
                        queries_tagged=audit_obj.get("queries_tagged"),
                        facts=facts,
                        report_md=report.content,
                        evidence_dir=evidence_dir if evidence_dir.exists() else None,
                    )
                except Exception:
                    artifacts = None

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
                    run_id=audit_obj.get("run_id"),
                    schema_version=audit_obj.get("schema_version"),
                    mode=audit_obj.get("mode"),
                    budgets=audit_obj.get("budgets"),
                    query_profile=audit_obj.get("query_profile"),
                    queries=audit_obj.get("queries"),
                    queries_tagged=audit_obj.get("queries_tagged"),
                    sources_summary=audit_obj.get("sources_summary"),
                    artifacts=artifacts,
                ),
            )

        # -------------------------
        # Cache miss -> collect web
        # -------------------------
        timing_ms: dict[str, int] = {}
        warnings: list[str] = []

        t_collect = time.time()
        sources, snippets, used_pages, evidence_texts = tool_collect_web_context(
            cfg=cfg,
            forecast_ctx=forecast_ctx,
            query_plan=query_plan,
            cache_root=cache_root,
        )
        timing_ms["collect_web_ms"] = int((time.time() - t_collect) * 1000)

        # Persist sanitized evidence text for reproducibility (best-effort)
        try:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            for sid, txt in (evidence_texts or {}).items():
                if not sid or not txt:
                    continue
                (evidence_dir / f"{sid}.txt").write_text(txt, encoding="utf-8")
        except Exception:
            warnings.append("evidence_persist_failed")

        # -------------------------
        # Facts (rule-based)
        # -------------------------
        t_extract = time.time()
        facts = tool_extract_facts_rule_based(
            cfg=cfg,
            forecast_ctx=forecast_ctx,
            sources=sources,
            snippets=snippets,
        )
        timing_ms["extract_facts_ms"] = int((time.time() - t_extract) * 1000)

        # -------------------------
        # Report
        # -------------------------
        t_report = time.time()
        report = tool_generate_report_md(
            style=cfg.report_style,
            forecast=forecast_ctx,
            facts=facts,
            sources=sources,
            used_pages=used_pages,
            max_pages=cfg.page_policy.max_pages,
        )
        timing_ms["generate_report_ms"] = int((time.time() - t_report) * 1000)

        timing_ms["total_ms"] = int((time.time() - t0) * 1000)

        # -------------------------
        # Persist artifacts
        # -------------------------
        run_dir.mkdir(parents=True, exist_ok=True)

        save_json(sources_path, {"sources": [s.__dict__ for s in sources]})

        with snippets_path.open("w", encoding="utf-8") as f:
            for sn in snippets:
                f.write(json.dumps(sn.__dict__, ensure_ascii=False) + "\n")

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

        sources_summary = [
            {
                "source_id": getattr(s, "source_id", None),
                "url": getattr(s, "url", None),
                "host": getattr(s, "host", None),
                "title": getattr(s, "title", None),
                "publisher": getattr(s, "publisher", None),
                "retrieved_at_utc": getattr(s, "retrieved_at_utc", None),
                "published_at_utc": getattr(s, "published_at_utc", None),
                "content_hash": getattr(s, "content_hash", None),
                "sanitized_char_count": getattr(s, "sanitized_char_count", None),
                "truncated": getattr(s, "truncated", None),
                "flags": getattr(s, "flags", None) or [],
                "cache_hit": getattr(s, "cache_hit", None),
            }
            for s in sources
        ]

        audit_obj = {
            "run_id": run_id,
            "schema_version": getattr(cfg, "schema_version", None),
            "mode": getattr(cfg, "mode", None),
            "created_at_utc": created_at_utc,
            "budgets": budgets,
            "query_profile": query_plan.profile,
            "queries": list(query_plan.queries),
            "queries_tagged": queries_tagged,
            "llm": {"provider": None, "model": None, "prompt_hashes": {}},
            "timing_ms": timing_ms,
            "warnings": warnings,
            "sources_summary": sources_summary,
        }

        # v0.8.0: structured artifacts (append-only)
        # Select artifacts builder by schema_version (keep deterministic, backward compatible)
        schema_v = (cfg.schema_version or "0.8.0").strip()
        _build_artifacts = build_artifacts_bundle_v081 if schema_v.startswith("0.8.1") else build_artifacts_bundle_v080
        try:
            audit_obj["artifacts"] = _build_artifacts(
                sources=sources,
                snippets=snippets,
                queries_tagged=queries_tagged,
                facts=facts,
                report_md=report.content,
                evidence_dir=evidence_dir if evidence_dir.exists() else None,
            )
        except Exception:
            warnings.append("artifacts_build_failed")
            audit_obj["artifacts"] = None

        
        # v0.9.1: Context Consistency Engine (CCE) - deterministic index for UX/paper
        try:
            if isinstance(audit_obj.get("artifacts"), dict):
                audit_obj["artifacts"]["context_consistency"] = compute_context_consistency(
                    artifacts=audit_obj.get("artifacts"),
                    forecast_ctx=forecast_ctx,
                )
        except Exception:
            warnings.append("context_consistency_failed")
# v0.7.x: persist richer run.json; keep audit.json for backward compatibility
        save_json(run_path, audit_obj)
        save_json(audit_path, audit_obj)

        return AnalysisRunResult(
            cache_key=cache_key,
            created_at_utc=created_at_utc,
            forecast_context=forecast_ctx,
            query_plan=query_plan,
            sources=sources,
            snippets=snippets,
            facts=facts,
            report=report,
            audit=AuditTrail(
                llm={"provider": None, "model": None, "prompt_hashes": {}},
                timing_ms=timing_ms,
                warnings=warnings,
                run_id=run_id,
                schema_version=getattr(cfg, "schema_version", None),
                mode=getattr(cfg, "mode", None),
                budgets=budgets,
                query_profile=query_plan.profile,
                queries=list(query_plan.queries),
                queries_tagged=queries_tagged,
                sources_summary=sources_summary,
                artifacts=audit_obj.get("artifacts"),
            ),
        )