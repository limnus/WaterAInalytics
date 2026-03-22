"""core/ui/agentic_analysis.py

Streamlit UI for the Agentic Analysis tab.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import replace
from pathlib import Path

import streamlit as st

from core.llm_analysis.config import AnalysisConfig, PagePolicy, ReportStyle
from core.llm_analysis.forecast_integration.adapter import forecast_output_to_context
from core.llm_analysis.llm_agent import LLMConfig, run_llm_analyst
from core.llm_analysis.llm_agent.providers import probe_ollama_catalog
from core.llm_analysis.llm_agent.quantitative_brief import (
    build_quantitative_forecast_brief,
    render_quantitative_brief_markdown,
)
from core.llm_analysis.pipeline import run_analysis


def _env_or_default(name: str, fallback: str) -> str:
    return os.getenv(name, fallback).strip() or fallback


def render_agentic_analysis(role: str | None = None) -> None:
    is_paid = (role or "").lower().strip() in ("admin", "user")

    st.subheader("Agentic AI Forecasting Analysis (Deterministic + Optional LLM Analyst)")

    if not is_paid:
        st.info(
            "Playground mode is restricted to authoritative domains only "
            "(USGS/NOAA/Weather.gov) to reduce noise and limit injection surface."
        )

    # --- Persist UI state across reruns ---
    st.session_state.setdefault("agentic_result", None)
    st.session_state.setdefault("agentic_forecast_ctx", None)
    st.session_state.setdefault("latest_agentic_run_path", None)

    # LLM widget state
    st.session_state.setdefault("llm_provider_label", "OFF (deterministic)")
    st.session_state.setdefault("llm_model", "")
    st.session_state.setdefault("llm_model_manual_mode", False)
    st.session_state.setdefault("ollama_base_url", _env_or_default("OLLAMA_BASE_URL", "http://localhost:11434"))
    st.session_state.setdefault("openai_base_url", _env_or_default("OPENAI_BASE_URL", "https://api.openai.com"))
    st.session_state.setdefault("openai_api_key_override", "")
    st.session_state.setdefault("llm_user_question", "")

    # --- Controls ---
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

        tone = st.selectbox(
            "Report tone",
            options=["neutral", "technical", "operational", "executive"],
            index=0,
        )

        user_instructions = st.text_area(
            "Additional instructions (future LLM input)",
            value="",
            height=110,
            placeholder="Optional. Will be used in future versions. Avoid secrets.",
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
            "Report tone",
            options=["neutral"],
            index=0,
            disabled=True,
        )
        st.text_area(
            "Additional instructions (future LLM input)",
            value="",
            height=110,
            disabled=True,
            placeholder="Enabled for User/Admin. In future versions this will feed the LLM (with injection protection).",
        )
        st.radio(
            "Execution mode",
            options=["Use cache (if available)", "Force refresh (recompute)"],
            index=0,
            horizontal=True,
            disabled=True,
        )

        max_pages = 5
        tone = "neutral"
        user_instructions = ""
        use_cache = True
        force_refresh = False

    # --- Check forecast availability ---
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

    cfg = AnalysisConfig(
        mode="full" if is_paid else "playground",
        use_cache=use_cache,
        force_refresh=force_refresh,
        page_policy=PagePolicy(max_pages=max_pages),
        report_style=ReportStyle(tone=tone),
        collector_opts={
            "user_instructions_present": bool(user_instructions.strip()),
        },
    )

    if st.button("Run Agentic Analysis", type="primary"):
        forecast_ctx = forecast_output_to_context(
            forecast_output,
            history_df,
        )

        cache_root = Path(tempfile.gettempdir())

        result = run_analysis(
            cfg=cfg,
            forecast_ctx=forecast_ctx,
            cache_root=cache_root,
        )

        st.session_state["agentic_result"] = result
        st.session_state["agentic_forecast_ctx"] = forecast_ctx

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

    result = st.session_state.get("agentic_result")
    forecast_ctx = st.session_state.get("agentic_forecast_ctx")

    if result is None or forecast_ctx is None:
        st.info("Run the analysis to generate the report and audit artifacts.")
        return

    st.markdown("### Generated Report")
    st.markdown(result.report.content)

    st.markdown("### Quantitative Forecast Brief (v0.9.3)")
    st.caption(
        "Deterministic natural-language interpretation grounded only in the recent history and the forecast artifact. "
        "No web search or external LLM call is needed for this section."
    )
    quantitative_brief = build_quantitative_forecast_brief(forecast_ctx)
    st.markdown(render_quantitative_brief_markdown(quantitative_brief))
    with st.expander("Quantitative brief statistics", expanded=False):
        st.json(
            {
                "history_stats": quantitative_brief.get("history_stats"),
                "forecast_stats": quantitative_brief.get("forecast_stats"),
            }
        )

    st.markdown("### Audit Info")
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

    st.markdown("---")
    st.markdown("### Optional LLM Analyst (v0.9.3)")
    st.caption(
        "Read-only: uses ONLY structured artifacts already produced above. "
        "Does not browse the web. Output is appended to run.json with hashes for audit."
    )

    provider_label = st.selectbox(
        "LLM provider",
        options=["OFF (deterministic)", "Ollama (local)", "OpenAI API"],
        index=0,
        key="llm_provider_label",
        help="Default is OFF. Enable explicitly to generate an LLM narrative layer.",
    )
    provider = "off"
    if provider_label.startswith("Ollama"):
        provider = "ollama"
    elif provider_label.startswith("OpenAI"):
        provider = "openai"

    run_path_s = st.session_state.get("latest_agentic_run_path")
    if provider != "off":
        if not run_path_s:
            st.warning("LLM Analyst requires a saved run.json (run analysis first).")
        elif not Path(run_path_s).exists():
            st.warning(f"run.json not found at: {run_path_s}")

    model = st.session_state.get("llm_model", "")
    can_run_llm = True

    col1, col2 = st.columns(2)
    with col1:
        ollama_base_url = st.text_input(
            "Ollama base URL",
            key="ollama_base_url",
            placeholder="http://localhost:11434",
            disabled=(provider != "ollama"),
        )
    with col2:
        openai_base_url = st.text_input(
            "OpenAI base URL",
            key="openai_base_url",
            placeholder="https://api.openai.com",
            disabled=(provider != "openai"),
        )

    if provider == "ollama":
        llm_cfg_preview = LLMConfig.from_env(provider="ollama", model=st.session_state.get("llm_model", ""))
        catalog = probe_ollama_catalog(ollama_base_url.strip() or llm_cfg_preview.ollama_base_url, timeout_s=5)
        if catalog.available:
            st.success(catalog.message)
        else:
            st.warning(catalog.message)
            can_run_llm = False

        c_manual, c_refresh = st.columns([2, 1])
        with c_manual:
            manual_mode = st.checkbox(
                "Enter model manually (advanced)",
                key="llm_model_manual_mode",
                help="Use this only when you intentionally want to type a model name instead of choosing an installed one.",
                disabled=(provider != "ollama"),
            )
        with c_refresh:
            if st.button("Refresh Ollama models", disabled=(provider != "ollama"), key="refresh_ollama_models"):
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
                disabled=(provider == "off"),
            )
            if not model.strip():
                can_run_llm = False

        st.caption(f"Ollama timeout for inference: {llm_cfg_preview.ollama_timeout_s}s (configure with OLLAMA_TIMEOUT_S in .env).")

    else:
        model = st.text_input(
            "Model",
            key="llm_model",
            placeholder="e.g., gpt-4.1-mini",
            disabled=(provider == "off"),
        )
        if provider == "openai" and not model.strip():
            can_run_llm = False

    openai_api_key_override = st.text_input(
        "OpenAI API key (optional override)",
        key="openai_api_key_override",
        type="password",
        placeholder="Uses OPENAI_API_KEY env var if empty",
        disabled=(provider != "openai"),
    )

    user_question = st.text_area(
        "Optional question / focus",
        key="llm_user_question",
        height=80,
        placeholder="Example: Summarize key environmental drivers relevant to the forecast uncertainty.",
        disabled=(provider == "off"),
    )

    if st.button("Run LLM Analyst", key="run_llm_analyst_btn", disabled=not can_run_llm):
        run_path2 = Path(run_path_s) if run_path_s else None
        if not run_path2 or not run_path2.exists():
            st.error("Cannot run LLM Analyst: run.json path is missing.")
            return

        llm_cfg = LLMConfig.from_env(provider=provider, model=model)
        if ollama_base_url.strip():
            llm_cfg = replace(llm_cfg, ollama_base_url=ollama_base_url.strip())
        if openai_base_url.strip():
            llm_cfg = replace(llm_cfg, openai_base_url=openai_base_url.strip())
        if openai_api_key_override.strip():
            llm_cfg = replace(llm_cfg, openai_api_key=openai_api_key_override.strip())

        with st.spinner("Running LLM Analyst..."):
            try:
                rep = run_llm_analyst(
                    run_path=run_path2,
                    forecast_ctx=forecast_ctx,
                    llm_cfg=llm_cfg,
                    user_question=user_question,
                )
                st.success("LLM report generated and appended to run.json")
                st.markdown(rep.output_markdown)
                with st.expander("LLM Report JSON", expanded=False):
                    st.json(rep.output_json)
                with st.expander("LLM Audit", expanded=False):
                    st.json(
                        {
                            "provider": rep.provider,
                            "model": rep.model,
                            "schema_version": rep.schema_version,
                            "created_at_utc": rep.created_at_utc,
                            "input_hash": rep.input_hash,
                            "prompt_hashes": rep.prompt_hashes,
                            "run_path": str(run_path2),
                        }
                    )
            except Exception as e:
                st.error(f"LLM Analyst failed: {e}")
