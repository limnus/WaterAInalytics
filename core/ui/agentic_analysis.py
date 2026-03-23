"""core/ui/agentic_analysis.py

Streamlit UI for the Agentic Analysis tab.
"""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import replace
from pathlib import Path

import streamlit as st

from core.article_demo import build_article_analysis_bundle_bytes
from core.config import get_runtime_settings
from core.context_enrichment import enrich_us_station_context, get_station_context_markdown
from core.llm_analysis.config import AnalysisConfig, PagePolicy, ReportStyle
from core.llm_analysis.forecast_integration.adapter import forecast_output_to_context
from core.llm_analysis.llm_agent import LLMConfig, run_llm_analyst
from core.llm_analysis.llm_agent.providers import probe_ollama_catalog
from core.llm_analysis.llm_agent.quantitative_brief import (
    build_quantitative_forecast_brief,
    render_quantitative_brief_markdown,
)
from core.llm_analysis.pipeline import run_analysis
from core.ui.agentic_flow import AgenticExecutionPlan, build_execution_plan_lines, llm_request_is_runnable
from core.ui.agentic_observability import (
    append_agentic_execution_log,
    build_agentic_execution_record,
    finalize_stage,
    start_stage,
    summarize_stage_timings,
)
from core.ui.agentic_presentation import (
    PRESENTATION_OPTIONS,
    normalize_focus_text,
    resolve_agentic_presentation,
)


def _env_or_default(name: str, fallback: str) -> str:
    return os.getenv(name, fallback).strip() or fallback


def _render_markdown_bullets(lines: list[str]) -> None:
    for line in lines:
        st.markdown(f"- {line}")


def render_agentic_analysis(role: str | None = None) -> None:
    is_paid = (role or "").lower().strip() in ("admin", "user")

    st.subheader("Agentic AI Forecasting Analysis")
    st.caption(
        "Single-run workflow: deterministic quantitative analysis first, optional official context enrichment next, "
        "and optional LLM refinement last. Detailed audit artifacts remain available below in collapsed sections."
    )

    if not is_paid:
        st.info(
            "Playground mode is restricted to authoritative domains only "
            "(USGS/NOAA/Weather.gov) to reduce noise and limit injection surface."
        )

    st.session_state.setdefault("agentic_result", None)
    st.session_state.setdefault("agentic_forecast_ctx", None)
    st.session_state.setdefault("latest_agentic_run_path", None)
    st.session_state.setdefault("agentic_station_context", None)
    st.session_state.setdefault("agentic_is_running", False)
    st.session_state.setdefault("agentic_last_execution", None)

    st.session_state.setdefault("llm_provider_label", "OFF (deterministic only)")
    st.session_state.setdefault("llm_model", "")
    st.session_state.setdefault("llm_model_manual_mode", False)
    st.session_state.setdefault("ollama_base_url", _env_or_default("OLLAMA_BASE_URL", "http://localhost:11434"))
    st.session_state.setdefault("openai_base_url", _env_or_default("OPENAI_BASE_URL", "https://api.openai.com"))
    st.session_state.setdefault("openai_api_key_override", "")
    st.session_state.setdefault("agentic_focus_text", "")
    st.session_state.setdefault("agentic_enable_llm", False)

    settings = get_runtime_settings()

    if is_paid:
        max_pages = st.slider(
            "Max pages (documents fetched)",
            min_value=5,
            max_value=30,
            value=10,
            step=1,
        )
        if max_pages > 10:
            st.warning("High page budget: execution may be slower.")

        presentation_label = st.selectbox(
            "Analysis presentation",
            options=PRESENTATION_OPTIONS,
            index=0,
            help="Controls how the primary analysis summary is rendered below.",
        )
        presentation = resolve_agentic_presentation(presentation_label)
        tone = presentation["report_tone"]
        focus_text = st.text_area(
            "Analysis focus (optional)",
            key="agentic_focus_text",
            height=90,
            placeholder="Example: emphasize uncertainty, local environmental drivers, or operational monitoring implications.",
            help="This single field guides the deterministic summary and the optional LLM refinement, if enabled.",
        )
        st.caption(presentation["description"])

        include_station_context = st.toggle(
            "Enrich with official station context",
            value=settings.station_context_enrichment_enabled,
            help="Uses official USGS, Census, and NWS endpoints with caching when station coordinates are available.",
        )

        exec_mode = st.radio(
            "Execution mode",
            options=["Use cache (if available)", "Force refresh (recompute)"],
            index=0,
            horizontal=True,
        )
        use_cache = exec_mode.startswith("Use cache")
        force_refresh = exec_mode.startswith("Force refresh")
    else:
        st.slider(
            "Max pages (documents fetched)",
            min_value=5,
            max_value=30,
            value=5,
            step=1,
            disabled=True,
        )
        st.selectbox(
            "Analysis presentation",
            options=["Narrative paragraph"],
            index=0,
            disabled=True,
        )
        st.text_area(
            "Analysis focus (optional)",
            value="",
            height=90,
            disabled=True,
            placeholder="Enabled for User/Admin.",
        )
        st.toggle(
            "Enrich with official station context",
            value=settings.station_context_enrichment_enabled,
            disabled=True,
            help="Playground follows the project default for official station context enrichment.",
        )
        st.radio(
            "Execution mode",
            options=["Use cache (if available)", "Force refresh (recompute)"],
            index=0,
            horizontal=True,
            disabled=True,
        )

        max_pages = 5
        presentation = resolve_agentic_presentation("Narrative paragraph")
        tone = presentation["report_tone"]
        focus_text = ""
        use_cache = True
        force_refresh = False
        include_station_context = settings.station_context_enrichment_enabled
        presentation_label = "Narrative paragraph"

    analysis_inputs = st.session_state.get("latest_forecast_analysis_inputs") or {}

    if analysis_inputs:
        station_ids = sorted(analysis_inputs.keys())
        if len(station_ids) > 1:
            selected_station_id = st.selectbox(
                "Station for Agentic Analysis",
                options=station_ids,
                index=0,
                key="agentic_selected_station_id",
                help="Agentic Analysis currently runs on one station at a time, using the most recent forecast run.",
            )
            st.caption("Multiple stations were forecast. Select the station to analyze below.")
        else:
            selected_station_id = station_ids[0]

        selected_input = analysis_inputs[selected_station_id]
        forecast_output = selected_input["forecast_output"]
        history_df = selected_input["history_df"]
        used_model_label = selected_input.get("used_model_label") or forecast_output.model_key
        st.caption(f"Analyzing station **{selected_station_id}** with model **{used_model_label}**.")
    else:
        if "latest_forecast_output" not in st.session_state:
            st.warning("Run a forecast first in the Forecasting tab.")
            return

        forecast_output = st.session_state["latest_forecast_output"]
        history_df = st.session_state["latest_history_df"]
        st.caption(f"Analyzing station **{forecast_output.station_id}** with legacy single-station forecast context.")

    llm_enabled = bool(st.session_state.get("agentic_enable_llm", False))
    provider_label = "OFF (deterministic only)"
    provider = "off"
    model = st.session_state.get("llm_model", "")
    provider_available = True
    llm_skip_reason = ""

    with st.expander("Optional LLM refinement settings", expanded=False):
        st.toggle(
            "Enable LLM refinement after the deterministic analysis",
            key="agentic_enable_llm",
            help="Keeps a single execution flow. The LLM, when enabled, runs after the deterministic artifacts are ready.",
        )
        llm_enabled = bool(st.session_state.get("agentic_enable_llm", False))

        provider_label = st.selectbox(
            "LLM provider",
            options=["OFF (deterministic only)", "Ollama (local)", "OpenAI API"],
            index=0,
            key="llm_provider_label",
            disabled=not llm_enabled,
            help="Disabled by default. Enable only when you want an extra narrative layer on top of the deterministic analysis.",
        )
        if provider_label.startswith("Ollama"):
            provider = "ollama"
        elif provider_label.startswith("OpenAI"):
            provider = "openai"
        else:
            provider = "off"

        col1, col2 = st.columns(2)
        with col1:
            ollama_base_url = st.text_input(
                "Ollama base URL",
                key="ollama_base_url",
                placeholder="http://localhost:11434",
                disabled=(not llm_enabled or provider != "ollama"),
            )
        with col2:
            openai_base_url = st.text_input(
                "OpenAI base URL",
                key="openai_base_url",
                placeholder="https://api.openai.com",
                disabled=(not llm_enabled or provider != "openai"),
            )

        if provider == "ollama" and llm_enabled:
            llm_cfg_preview = LLMConfig.from_env(provider="ollama", model=st.session_state.get("llm_model", ""))
            catalog = probe_ollama_catalog(ollama_base_url.strip() or llm_cfg_preview.ollama_base_url, timeout_s=5)
            provider_available = catalog.available
            if catalog.available:
                st.success(catalog.message)
            else:
                st.warning(catalog.message)
                llm_skip_reason = catalog.message

            c_manual, c_refresh = st.columns([2, 1])
            with c_manual:
                manual_mode = st.checkbox(
                    "Enter model manually (advanced)",
                    key="llm_model_manual_mode",
                    help="Use this only when you intentionally want to type a model name instead of choosing an installed one.",
                    disabled=(provider != "ollama" or not llm_enabled),
                )
            with c_refresh:
                if st.button("Refresh Ollama models", disabled=(provider != "ollama" or not llm_enabled), key="refresh_ollama_models"):
                    st.rerun()

            if catalog.models and not manual_mode:
                if st.session_state.get("llm_model") not in catalog.models:
                    st.session_state["llm_model"] = catalog.models[0]
                selected_model = st.selectbox(
                    "Installed Ollama model",
                    options=catalog.models,
                    index=catalog.models.index(st.session_state["llm_model"]),
                    key="llm_model_selectbox",
                    help="Models are read from the local Ollama installation.",
                )
                st.session_state["llm_model"] = selected_model
                model = selected_model
            else:
                model = st.text_input(
                    "Model",
                    key="llm_model",
                    placeholder="e.g., llama3.2 or gemma3:1b",
                    disabled=(provider == "off" or not llm_enabled),
                )
            st.caption(
                f"Ollama timeout for inference: {llm_cfg_preview.ollama_timeout_s}s "
                "(configure with OLLAMA_TIMEOUT_S in .env)."
            )
        else:
            model = st.text_input(
                "Model",
                key="llm_model",
                placeholder="e.g., gpt-4.1-mini",
                disabled=(provider == "off" or not llm_enabled),
            )

        openai_api_key_override = st.text_input(
            "OpenAI API key (optional override)",
            key="openai_api_key_override",
            type="password",
            placeholder="Uses OPENAI_API_KEY env var if empty",
            disabled=(provider != "openai" or not llm_enabled),
        )

        if focus_text:
            st.caption(f"Any LLM refinement will reuse the current analysis focus: {focus_text}")
        else:
            st.caption("No explicit analysis focus is set. Any LLM refinement will summarize the structured artifacts as-is.")

    llm_ready = llm_request_is_runnable(
        enabled=llm_enabled,
        provider=provider,
        model=model,
        provider_available=provider_available,
    )
    if llm_enabled and not llm_ready and not llm_skip_reason:
        if provider == "off":
            llm_skip_reason = "Select a provider to enable LLM refinement."
        elif not (model or "").strip():
            llm_skip_reason = "Choose a valid model before enabling LLM refinement."
        elif not provider_available:
            llm_skip_reason = "The selected LLM provider is not currently reachable."
        else:
            llm_skip_reason = "The optional LLM refinement is not currently runnable with the selected settings."

    if llm_enabled:
        if llm_ready:
            st.success("Optional LLM refinement is configured and will run inside the same execution flow.")
        else:
            st.warning(f"Optional LLM refinement is enabled but may be skipped: {llm_skip_reason}")

    plan_lines = build_execution_plan_lines(
        AgenticExecutionPlan(
            include_station_context=include_station_context,
            llm_enabled=llm_enabled,
            llm_provider=provider,
            llm_model=model,
        )
    )
    with st.expander("Execution plan", expanded=False):
        _render_markdown_bullets(plan_lines)

    cfg = AnalysisConfig(
        mode="full" if is_paid else "playground",
        use_cache=use_cache,
        force_refresh=force_refresh,
        page_policy=PagePolicy(max_pages=max_pages),
        report_style=ReportStyle(tone=tone),
        collector_opts={
            "focus_text_present": bool(normalize_focus_text(focus_text)),
        },
    )

    run_clicked = st.button(
        "Generate Full Analysis",
        type="primary",
        disabled=bool(st.session_state.get("agentic_is_running")),
        help="Runs the deterministic analysis first, then optional context enrichment and optional LLM refinement in the same flow.",
    )

    if st.session_state.get("agentic_is_running"):
        st.info("Agentic Analysis is already running. Please wait for the current execution to finish.")

    if run_clicked:
        if st.session_state.get("agentic_is_running"):
            st.warning("A previous Agentic Analysis execution is still marked as running. Please wait and try again.")
            return

        st.session_state["agentic_is_running"] = True
        st.session_state["latest_llm_report"] = None
        stage_events = []
        execution_warnings = []
        station_context = None
        forecast_ctx = None
        result = None
        cache_root = Path(tempfile.gettempdir())
        status_box = st.status("Starting unified Agentic Analysis...", expanded=True) if hasattr(st, "status") else None
        stage_start_total = time.perf_counter()

        try:
            build_stage = start_stage("build_forecast_context")
            if status_box is not None:
                status_box.update(label="Building forecast context from the latest forecast run...", state="running")
            forecast_ctx = forecast_output_to_context(
                forecast_output,
                history_df,
            )
            stage_events.append(finalize_stage(build_stage, detail=f"station={forecast_ctx.station_id}"))

            if include_station_context:
                context_stage = start_stage("station_context_enrichment")
                if status_box is not None:
                    status_box.update(label="Resolving official station context (USGS / Census / NWS)...", state="running")
                try:
                    station_context = enrich_us_station_context(
                        forecast_ctx.station_id,
                        timeout_s=settings.station_context_timeout_s,
                        cache_ttl_days=settings.station_context_cache_days,
                        force_refresh=force_refresh,
                    )
                    detail = station_context.get("census", {}).get("status") or "ok"
                    stage_events.append(finalize_stage(context_stage, detail=f"status={detail}"))
                except Exception as exc:
                    execution_warnings.append(
                        f"Official station context enrichment failed and was skipped: {type(exc).__name__}: {exc}"
                    )
                    stage_events.append(finalize_stage(context_stage, status="warning", detail=type(exc).__name__))
                    station_context = {
                        "station_id": forecast_ctx.station_id,
                        "enabled": False,
                        "narrative": {
                            "key_findings": [],
                            "limitations": [execution_warnings[-1]],
                            "open_questions": [],
                        },
                    }

                forecast_meta = dict(forecast_ctx.meta or {}) if isinstance(forecast_ctx.meta, dict) else {}
                forecast_meta["official_station_context"] = station_context
                forecast_ctx = replace(forecast_ctx, meta=forecast_meta)

            analysis_stage = start_stage("deterministic_agentic_pipeline")
            if status_box is not None:
                status_box.update(label="Running deterministic agentic pipeline and assembling audit artifacts...", state="running")
            result = run_analysis(
                cfg=cfg,
                forecast_ctx=forecast_ctx,
                cache_root=cache_root,
            )
            stage_events.append(finalize_stage(analysis_stage, detail=f"cache_key={result.cache_key}"))

            persist_stage = start_stage("persist_session_state")
            st.session_state["agentic_result"] = result
            st.session_state["agentic_forecast_ctx"] = forecast_ctx
            st.session_state["agentic_station_context"] = station_context

            try:
                run_date_local = forecast_ctx.run_datetime_utc.date().isoformat()
                run_path = (
                    cache_root
                    / "agentic_analysis"
                    / forecast_ctx.station_id
                    / forecast_ctx.parameter
                    / run_date_local
                    / result.cache_key
                    / "run.json"
                )
                st.session_state["latest_agentic_run_path"] = str(run_path)
            except Exception:
                st.session_state["latest_agentic_run_path"] = None
            stage_events.append(finalize_stage(persist_stage, detail="session_state_updated"))

            run_path_s = st.session_state.get("latest_agentic_run_path")
            if llm_enabled:
                if llm_ready and run_path_s and Path(run_path_s).exists():
                    llm_stage = start_stage("optional_llm_refinement")
                    if status_box is not None:
                        status_box.update(label="Running optional LLM refinement on top of the deterministic artifacts...", state="running")
                    try:
                        llm_cfg = LLMConfig.from_env(provider=provider, model=model)
                        if provider == "ollama":
                            ollama_base_url = st.session_state.get("ollama_base_url", "").strip()
                            if ollama_base_url:
                                llm_cfg = replace(llm_cfg, ollama_base_url=ollama_base_url)
                        if provider == "openai":
                            openai_base_url = st.session_state.get("openai_base_url", "").strip()
                            if openai_base_url:
                                llm_cfg = replace(llm_cfg, openai_base_url=openai_base_url)
                            openai_api_key_override = st.session_state.get("openai_api_key_override", "").strip()
                            if openai_api_key_override:
                                llm_cfg = replace(llm_cfg, openai_api_key=openai_api_key_override)

                        rep = run_llm_analyst(
                            run_path=Path(run_path_s),
                            forecast_ctx=forecast_ctx,
                            llm_cfg=llm_cfg,
                            user_question=focus_text,
                        )
                        st.session_state["latest_llm_report"] = {
                            "provider": rep.provider,
                            "model": rep.model,
                            "schema_version": rep.schema_version,
                            "created_at_utc": rep.created_at_utc,
                            "input_hash": rep.input_hash,
                            "prompt_hashes": rep.prompt_hashes,
                            "output_json": rep.output_json,
                            "output_markdown": rep.output_markdown,
                        }
                        stage_events.append(finalize_stage(llm_stage, detail=f"provider={rep.provider};model={rep.model}"))
                    except Exception as exc:
                        execution_warnings.append(
                            f"Optional LLM refinement failed and was skipped: {type(exc).__name__}: {exc}"
                        )
                        stage_events.append(finalize_stage(llm_stage, status="warning", detail=type(exc).__name__))
                        st.session_state["latest_llm_report"] = None
                else:
                    execution_warnings.append(
                        f"Optional LLM refinement was enabled but skipped: {llm_skip_reason or 'run.json was not available yet.'}"
                    )

            timing_summary = summarize_stage_timings(stage_events)
            if timing_summary.get("slowest_stage") and timing_summary["slowest_stage"].get("duration_ms", 0) >= settings.agentic_stage_slow_threshold_ms:
                execution_warnings.append(
                    f"Slowest stage was {timing_summary['slowest_stage']['stage']} at {timing_summary['slowest_stage']['duration_ms']} ms."
                )

            execution_record = build_agentic_execution_record(
                role=role,
                station_id=forecast_ctx.station_id,
                execution_surface="authenticated" if is_paid else "playground",
                include_station_context=include_station_context,
                force_refresh=force_refresh,
                focus_text_present=bool(normalize_focus_text(focus_text)),
                status="ok",
                timing_summary=timing_summary,
                warnings=execution_warnings,
            )
            execution_record["llm"] = {
                "enabled": bool(llm_enabled),
                "provider": provider if llm_enabled else "off",
                "model": (model or "").strip() if llm_enabled else "",
                "executed": bool(st.session_state.get("latest_llm_report")),
                "skip_reason": None if st.session_state.get("latest_llm_report") else (llm_skip_reason or None),
            }
            if settings.agentic_execution_log_enabled:
                log_path = append_agentic_execution_log(execution_record)
                execution_record["log_path"] = str(log_path)
            execution_record["total_wall_clock_ms"] = int(round((time.perf_counter() - stage_start_total) * 1000.0))
            st.session_state["agentic_last_execution"] = execution_record

            if status_box is not None:
                status_box.update(label="Unified Agentic Analysis completed.", state="complete")
            if execution_warnings:
                for warning in execution_warnings:
                    st.warning(warning)
        except Exception as exc:
            if forecast_ctx is not None:
                station_id_for_log = forecast_ctx.station_id
            else:
                station_id_for_log = forecast_output.station_id
            timing_summary = summarize_stage_timings(stage_events)
            execution_record = build_agentic_execution_record(
                role=role,
                station_id=station_id_for_log,
                execution_surface="authenticated" if is_paid else "playground",
                include_station_context=include_station_context,
                force_refresh=force_refresh,
                focus_text_present=bool(normalize_focus_text(focus_text)),
                status="error",
                timing_summary=timing_summary,
                warnings=execution_warnings,
                error=f"{type(exc).__name__}: {exc}",
            )
            execution_record["llm"] = {
                "enabled": bool(llm_enabled),
                "provider": provider if llm_enabled else "off",
                "model": (model or "").strip() if llm_enabled else "",
                "executed": False,
                "skip_reason": llm_skip_reason or None,
            }
            if settings.agentic_execution_log_enabled:
                log_path = append_agentic_execution_log(execution_record)
                execution_record["log_path"] = str(log_path)
            execution_record["total_wall_clock_ms"] = int(round((time.perf_counter() - stage_start_total) * 1000.0))
            st.session_state["agentic_last_execution"] = execution_record
            if status_box is not None:
                status_box.update(label="Unified Agentic Analysis failed.", state="error")
            st.error(f"Agentic Analysis failed: {type(exc).__name__}: {exc}")
            return
        finally:
            st.session_state["agentic_is_running"] = False

    result = st.session_state.get("agentic_result")
    forecast_ctx = st.session_state.get("agentic_forecast_ctx")

    if result is None or forecast_ctx is None:
        st.info("Run the analysis to generate the report and audit artifacts.")
        return

    execution_record = st.session_state.get("agentic_last_execution")
    if isinstance(execution_record, dict):
        slowest_stage = ((execution_record.get("timing") or {}).get("slowest_stage") or {})
        summary_bits = [f"Last run surface: {execution_record.get('execution_surface')}"]
        if slowest_stage:
            summary_bits.append(
                f"slowest stage: {slowest_stage.get('stage')} ({slowest_stage.get('duration_ms')} ms)"
            )
        if execution_record.get("llm", {}).get("executed"):
            summary_bits.append("LLM refinement executed")
        elif execution_record.get("llm", {}).get("enabled"):
            summary_bits.append("LLM refinement enabled but skipped")
        st.caption(" | ".join(summary_bits))
        with st.expander("Execution telemetry", expanded=False):
            st.json(execution_record)

    focus_text = normalize_focus_text(st.session_state.get("agentic_focus_text"))
    brief_format = presentation["brief_format"] if isinstance(presentation, dict) else "structured"

    st.markdown("### Primary Analysis Summary")
    st.caption(
        "Deterministic natural-language interpretation grounded only in the recent history and the forecast artifact. "
        "No web search or external LLM call is needed for this section."
    )
    quantitative_brief = build_quantitative_forecast_brief(forecast_ctx)
    quantitative_brief_markdown = render_quantitative_brief_markdown(
        quantitative_brief,
        format_style=brief_format,
        focus_text=focus_text,
    )
    st.markdown(quantitative_brief_markdown)

    latest_llm_report = st.session_state.get("latest_llm_report")
    if isinstance(latest_llm_report, dict):
        st.markdown("### LLM Refinement Summary")
        st.caption(
            "Optional narrative layer produced from the deterministic artifacts above. It does not replace the deterministic summary."
        )
        st.markdown(latest_llm_report.get("output_markdown") or "")
        with st.expander("LLM refinement audit JSON", expanded=False):
            st.json(latest_llm_report)

    with st.expander("Underlying deterministic source report", expanded=False):
        st.markdown(result.report.content)

    station_context = st.session_state.get("agentic_station_context")
    if isinstance(station_context, dict):
        with st.expander("Official station context", expanded=False):
            st.caption(
                "Deterministic station enrichment from official USGS, Census, and NWS services, cached locally when available."
            )
            st.markdown(get_station_context_markdown(station_context))

    latest_forecast_df = st.session_state.get("latest_forecast_df")
    latest_forecast_run_artifact = st.session_state.get("latest_forecast_run_artifact")
    latest_forecast_profile = st.session_state.get("latest_forecast_profile") or {}

    if latest_forecast_df is not None and latest_forecast_run_artifact:
        st.markdown("### Article Export Bundle")
        st.caption(
            "Exports the reproducible artifacts for the current experiment: forecast table, run JSON, deterministic summary, context, and execution telemetry."
        )
        article_bundle = build_article_analysis_bundle_bytes(
            forecast_df=latest_forecast_df,
            forecast_run_artifact=latest_forecast_run_artifact,
            quantitative_brief_markdown=quantitative_brief_markdown,
            deterministic_report_markdown=result.report.content,
            profile=latest_forecast_profile,
            station_context=station_context if isinstance(station_context, dict) else None,
            execution_telemetry=execution_record if isinstance(execution_record, dict) else None,
            focus_text=focus_text,
            presentation_label=presentation_label,
            llm_report=latest_llm_report if isinstance(latest_llm_report, dict) else None,
        )
        st.download_button(
            "Download article analysis bundle (ZIP)",
            data=article_bundle,
            file_name="article_analysis_bundle.zip",
            mime="application/zip",
            help="Includes the current forecast artifact, deterministic narrative, context enrichment, and execution telemetry for audit.",
        )

    with st.expander("Quantitative brief statistics", expanded=False):
        st.json(
            {
                "history_stats": quantitative_brief.get("history_stats"),
                "forecast_stats": quantitative_brief.get("forecast_stats"),
                "official_station_context": quantitative_brief.get("official_station_context"),
            }
        )

    with st.expander("Audit info", expanded=False):
        st.json(
            {
                "run_id": result.audit.run_id,
                "schema_version": result.audit.schema_version,
                "mode": result.audit.mode,
                "budgets": result.audit.budgets,
                "timing_ms": result.audit.timing_ms,
                "warnings": result.audit.warnings,
                "llm": result.audit.llm,
                "queries": result.audit.queries,
                "sources": result.audit.sources_summary,
            }
        )

    if getattr(result.audit, "artifacts", None):
        with st.expander("v0.8.1 Artifacts (Evidence / Claims / Narrative)", expanded=False):
            st.json(result.audit.artifacts)
            try:
                nar = (result.audit.artifacts or {}).get("narrative") or {}
                tmd = nar.get("templated_markdown")
                if tmd:
                    st.markdown("---")
                    st.markdown("**Templated report (v0.8.1)**")
                    st.code(tmd, language="markdown")
            except Exception:
                pass
