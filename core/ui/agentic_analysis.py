"""core/ui/agentic_analysis.py

Streamlit UI for v0.6.0 Agentic AI Forecasting Analysis (MVP).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from core.llm_analysis.config import AnalysisConfig, PagePolicy, ReportStyle
from core.llm_analysis.pipeline import run_analysis
from core.llm_analysis.forecast_integration.adapter import forecast_output_to_context


def render_agentic_analysis(role: str | None = None) -> None:
    is_paid = (role or "").lower().strip() in ("admin", "user")

    st.subheader("Agentic AI Forecasting Analysis (MVP v0.6.0)")

    if not is_paid:
        st.info(
            "Playground mode is restricted to authoritative domains only "
            "(USGS/NOAA/Weather.gov) to reduce noise and limit injection surface."
        )

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

        st.markdown("### Generated Report")
        st.markdown(result.report.content)

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

        # v0.8.0 artifacts (best-effort)
        if getattr(result.audit, "artifacts", None):
            with st.expander("v0.8.0 Artifacts (Evidence / Claims / Narrative)", expanded=False):
                st.json(result.audit.artifacts)
