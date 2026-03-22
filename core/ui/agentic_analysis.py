"""core/ui/agentic_analysis.py

Streamlit UI for v0.6.0 Agentic AI Forecasting Analysis (MVP).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st
from dataclasses import replace

from core.llm_analysis.config import AnalysisConfig, PagePolicy, ReportStyle
from core.llm_analysis.pipeline import run_analysis
from core.llm_analysis.forecast_integration.adapter import forecast_output_to_context
from core.llm_analysis.llm_agent import LLMConfig, run_llm_analyst
from core.ui.playground_output import apply_output_policy


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
    st.session_state.setdefault("ollama_base_url", "")
    st.session_state.setdefault("openai_base_url", "")
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

        # Future prompt input (enabled only for paid)
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
    if "latest_forecast_output" not in st.session_state:
        st.warning("Run a forecast first in the Forecasting tab.")
        return

    forecast_output = st.session_state["latest_forecast_output"]
    history_df = st.session_state["latest_history_df"]

    # --- Build config ---
    cfg = AnalysisConfig(
        mode="full" if is_paid else "playground",
        use_cache=use_cache,
        force_refresh=force_refresh,
        page_policy=PagePolicy(max_pages=max_pages),
        report_style=ReportStyle(tone=tone),
        collector_opts={
            # reserved for future:
            # include user instructions later, after injection hardening + strict schema binding
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

        # Persist for reruns (critical)
        st.session_state["agentic_result"] = result
        st.session_state["agentic_forecast_ctx"] = forecast_ctx

        # Persist run.json path for optional LLM Analyst (v0.9.0)
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

    # --- Render persisted results (outside the button) ---
    result = st.session_state.get("agentic_result")
    forecast_ctx = st.session_state.get("agentic_forecast_ctx")

    if result is None or forecast_ctx is None:
        st.info("Run the analysis to generate the report and audit artifacts.")
        return

    st.markdown("### Generated Report")
    rendered_report = apply_output_policy(content=result.report.content, role=role)
    if rendered_report.truncated:
        st.warning(rendered_report.notice)
    st.markdown(rendered_report.content)

    st.markdown("### Audit Info")
    st.json({
        "run_id": result.audit.run_id,
        "schema_version": result.audit.schema_version,
        "mode": result.audit.mode,
        "budgets": result.audit.budgets,
        "timing_ms": result.audit.timing_ms,
        "warnings": result.audit.warnings,
        "llm": result.audit.llm,
        "queries": result.audit.queries,
        "sources": result.audit.sources_summary,
    })

    # v0.8.1 artifacts (best-effort)
    if is_paid and getattr(result.audit, "artifacts", None):
        with st.expander("v0.8.1 Artifacts (Evidence / Claims / Narrative)", expanded=False):
            st.json(result.audit.artifacts)

            # v0.8.1: show templated report (parallel) if available
            try:
                nar = (result.audit.artifacts or {}).get("narrative") or {}
                tmd = nar.get("templated_markdown")
                if tmd:
                    st.markdown("---")
                    st.markdown("**Templated report (v0.8.1)**")
                    st.code(tmd, language="markdown")
            except Exception:
                pass

    # -------------------------
    # v0.9.0: Optional LLM Analyst (read-only)
    # -------------------------
    if not is_paid:
        st.markdown("---")
        st.info("Optional LLM Analyst is available only for authenticated User/Admin accounts.")
        return

    st.markdown("---")
    st.markdown("### Optional LLM Analyst (v0.9.0)")
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

    # Sensible model default (set only once)
    if provider == "ollama" and not st.session_state.get("llm_model"):
        st.session_state["llm_model"] = "llama3"

    model = st.text_input(
        "Model",
        key="llm_model",
        placeholder="e.g., llama3.1 (Ollama) or gpt-4.1-mini (OpenAI)",
        disabled=(provider == "off"),
    )

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

    run_path_s = st.session_state.get("latest_agentic_run_path")
    if provider != "off":
        if not run_path_s:
            st.warning("LLM Analyst requires a saved run.json (run analysis first).")
        elif not Path(run_path_s).exists():
            st.warning(f"run.json not found at: {run_path_s}")

    if st.button("Run LLM Analyst", key="run_llm_analyst_btn"):
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
                rendered_llm = apply_output_policy(content=rep.output_markdown, role=role)
                if rendered_llm.truncated:
                    st.warning(rendered_llm.notice)
                st.markdown(rendered_llm.content)
                with st.expander("LLM Report JSON", expanded=False):
                    st.json(rep.output_json)
                with st.expander("LLM Audit", expanded=False):
                    st.json({
                        "provider": rep.provider,
                        "model": rep.model,
                        "schema_version": rep.schema_version,
                        "created_at_utc": rep.created_at_utc,
                        "input_hash": rep.input_hash,
                        "prompt_hashes": rep.prompt_hashes,
                        "run_path": str(run_path2),
                    })
            except Exception as e:
                st.error(f"LLM Analyst failed: {e}")
