"""Admin Models (mocked for v0.4.0).

This panel will eventually:
  1) read cached IV Parquets
  2) generate per-station/per-parameter feature tables (CSV/Parquet)
  3) run feature selection + hyperparameter tuning
  4) persist trained models + evaluation metrics

For now, we generate *mock artifacts* that follow the training contracts.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from core.ml.mock_artifacts import generate_mock_ridge_artifacts


def render_admin_models(role: str | None = None) -> None:
    st.markdown("### Admin Models")

    if role not in ("Admin", "admin"):
        st.warning("Admin Models is restricted to Admin users.")
        return

    st.info(
        "Admin Models is still under construction. "
        "In v0.4.0 we generate mock JSON artifacts (features, tuned hyperparameters, metrics) "
        "so the training/evaluation contracts can be finalized and wired." 
    )

    st.markdown("#### Cache pruning policy (IV cache)")
    st.caption(
        "IV Parquets are cached under `iv_cache/`. They are treated as a cache, not as curated training data. "
        "Size pruning is controlled by the environment variable `IV_CACHE_MAX_MB` and applied opportunistically "
        "after downloads (best-effort)."
    )
    current = os.getenv("IV_CACHE_MAX_MB", "(not set)")
    st.code(f"IV_CACHE_MAX_MB={current}")
    st.caption(
        "Recommendation: start with 1024 (≈1 GB). Increase if you want to keep longer history across many stations/parameters." 
    )

    st.markdown("#### Generate mock model artifacts")
    c1, c2, c3 = st.columns([1.2, 1, 1])
    with c1:
        station_id = st.text_input("Station ID", value="USGS-01013500")
    with c2:
        parameter_code = st.text_input("Parameter code", value="00060")
    with c3:
        data_root = st.text_input("Data root", value="data")

    if st.button("Generate mock Ridge artifacts", type="primary"):
        paths = generate_mock_ridge_artifacts(
            data_root=Path(data_root),
            station_id=station_id.strip(),
            parameter_code=parameter_code.strip(),
        )
        st.success("Mock artifacts written.")
        st.code(str(paths.base_dir()))

    st.markdown("#### What gets created")
    st.markdown(
        "- `feature_set.json`: full feature superset used to generate training tables\n"
        "- `tuning_result.json`: selected features + tuned hyperparameters (mock)\n"
        "- `metrics.json`: evaluation metrics (mock)\n"
        "\nLayout: `data/models/ridge/<station_id>/<parameter_code>/...`"
    )
