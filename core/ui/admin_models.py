# core/ui/admin_models.py

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st

from core.cache.get_station_timeseries import (
    _site_from_monitoring_location_id,
    ensure_iv_window,
    ALL_PARAMETERS,
)
from core.ui.strings.loader import get_strings
from core.forecast_models.paths import model_dir
from core.forecast_models.ridge import train_ridge_from_history, save_ridge_artifacts


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _stations_csv_path() -> Path:
    # Same filename as Explorer
    fname = "usgs_00060_00065_base_from_ts_metadata.csv"
    return _project_root() / "data" / fname


def _load_all_monitoring_ids() -> list[str]:
    p = _stations_csv_path()
    if not p.exists():
        return []
    df = pd.read_csv(p)
    if "monitoring_location_id" not in df.columns:
        return []
    mids = df["monitoring_location_id"].astype(str).dropna().tolist()
    mids = [m for m in mids if m.startswith("USGS-")]
    # de-dup preserve order
    seen = set()
    out = []
    for m in mids:
        if m not in seen:
            out.append(m); seen.add(m)
    return out


def render_admin_models(role: str | None = None) -> None:
    S = get_strings()
    st.markdown("### Admin Models")

    if not role or role.lower() != "admin":
        st.warning("Admin Models is restricted to Admin users.")
        return

    st.caption("Train Ridge models for stations/parameters that have data in the IV cache.")

    days = st.slider("Training window (days)", min_value=7, max_value=90, value=30, step=1)
    min_points = st.number_input("Minimum points required", min_value=48, max_value=2000, value=200, step=10)
    alpha = st.number_input("Ridge alpha (regularization)", min_value=0.01, max_value=1000.0, value=1.0, step=0.5)

    st.markdown("**Parameters to scan**")
    params = st.multiselect(
        "USGS parameter codes",
        options=ALL_PARAMETERS,
        default=ALL_PARAMETERS,
        help="Models will be trained per station + parameter code where enough data is available.",
    )

    run = st.button("Train Ridge for ALL stations with data", type="primary")

    if not run:
        st.info("Configure options and click **Train Ridge for ALL stations with data**.")
        return

    mids = _load_all_monitoring_ids()
    if not mids:
        st.error("Stations CSV not found or empty. Refresh stations in Explorer first.")
        return

    total = len(mids) * len(params)
    prog = st.progress(0)
    log = st.empty()

    done = 0
    trained = 0
    skipped = 0
    errors = 0

    for mid in mids:
        site = _site_from_monitoring_location_id(mid)
        for pcode in params:
            done += 1
            try:
                df = ensure_iv_window(site=site, parameter_code=pcode, days=int(days))
                if df is None or df.empty or len(df) < int(min_points):
                    skipped += 1
                    continue

                # Normalize to the ForecastRequest schema expected by models
                hist = pd.DataFrame(
                    {
                        "Datetime": pd.to_datetime(df["datetime_utc"], utc=True, errors="coerce"),
                        "Value": pd.to_numeric(df["value"], errors="coerce"),
                    }
                ).dropna()

                if len(hist) < int(min_points):
                    skipped += 1
                    continue

                artifacts = train_ridge_from_history(hist, alpha=float(alpha))
                out_dir = model_dir(station_id=f"USGS-{site}", parameter=str(pcode), model_key="ridge")
                save_ridge_artifacts(out_dir, artifacts)
                trained += 1

            except Exception as e:
                errors += 1
                # keep going
                log.warning(f"Error training ridge for {mid} / {pcode}: {e}")

            prog.progress(min(1.0, done / max(1, total)))

    st.success(
        f"Done. Trained: {trained} | Skipped: {skipped} | Errors: {errors} | Total combos: {total}"
    )
