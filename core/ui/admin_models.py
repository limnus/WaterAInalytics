# core/ui/admin_models.py
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from core.cache.get_station_timeseries import (
    _site_from_monitoring_location_id,
    ensure_iv_window,
    ALL_PARAMETERS,
)
from core.ui.strings.loader import get_strings
from core.forecast_models.paths import model_dir
from core.forecast_models.ridge import (
    train_ridge_from_history,
    tune_ridge_alpha,
    save_ridge_artifacts,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _stations_csv_path() -> Path:
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
    seen: set[str] = set()
    out: list[str] = []
    for m in mids:
        if m not in seen:
            out.append(m)
            seen.add(m)
    return out


def render_admin_models(role: str | None = None) -> None:
    S = get_strings()
    st.markdown("### Admin Models")

    if not role or role.lower() != "admin":
        st.warning("Admin Models is restricted to Admin users.")
        return

    st.caption("Train forecasting models for station/parameter pairs that have data in the IV cache.")

    st.markdown("#### Ridge")
    days = st.slider("Training window (days)", min_value=7, max_value=90, value=30, step=1)
    min_points = st.number_input("Minimum points required", min_value=48, max_value=2000, value=200, step=10)

    st.markdown("**Ridge alpha**")
    auto_alpha = st.checkbox("Auto-tune alpha (grid search, Admin only)", value=True)
    if auto_alpha:
        alpha_grid = st.multiselect(
            "Alpha grid",
            options=[0.01, 0.1, 1.0, 10.0, 100.0, 300.0],
            default=[0.1, 1.0, 10.0, 100.0],
            help="Temporal validation split; selects alpha with lowest RMSE for H=1.",
        )
        alpha = None
    else:
        alpha = st.number_input(
            "Ridge alpha (regularization)",
            min_value=0.01,
            max_value=1000.0,
            value=1.0,
            step=0.5,
        )
        alpha_grid = []

    st.markdown("#### Chronos (context optimization)")
    chronos_enable = st.checkbox("Also optimize Chronos context (Tiny/Mini/Base/Large)", value=False)

    chronos_size = st.selectbox(
        "Chronos model",
        options=["Bolt Tiny", "Bolt Mini", "Bolt Base", "T5 Large"],
        index=0,
        disabled=not chronos_enable,
        help="Large can be heavy; recommend GPU if available.",
    )
    chronos_eval_points = st.number_input(
        "Chronos eval points (H=1)",
        min_value=24,
        max_value=1000,
        value=168,
        step=24,
        disabled=not chronos_enable,
    )
    chronos_candidates = st.multiselect(
        "Context candidates (hours, max 336)",
        options=[24, 48, 72, 168, 336],
        default=[24, 48, 72, 168, 336],
        disabled=not chronos_enable,
        help="Selects best context length (<= 14 days) for H=1.",
    )

    st.markdown("#### Parameters")
    params = st.multiselect(
        "USGS parameter codes",
        options=ALL_PARAMETERS,
        default=ALL_PARAMETERS,
        help="Models will be trained per station + parameter code where enough data is available.",
    )

    run = st.button("Train models for ALL stations with data", type="primary")
    if not run:
        st.info("Configure options and click **Train models for ALL stations with data**.")
        return

    mids = _load_all_monitoring_ids()
    if not mids:
        st.error("Stations CSV not found or empty. Refresh stations in Explorer first.")
        return

    if chronos_enable:
        try:
            from core.forecast_models.chronos import optimize_chronos_context, save_chronos_artifacts
        except Exception as e:
            st.error(
                "Chronos is enabled, but its dependencies are not installed or Chronos import failed.\n\n"
                f"Error: {e}\n\n"
                "Disable Chronos or install torch + chronos-forecasting."
            )
            return
    else:
        optimize_chronos_context = None  # type: ignore[assignment]
        save_chronos_artifacts = None  # type: ignore[assignment]

    def _chronos_choice() -> tuple[str, str]:
        if chronos_size == "Bolt Tiny":
            return "amazon/chronos-bolt-tiny", "chronos-tiny"
        if chronos_size == "Bolt Mini":
            return "amazon/chronos-bolt-mini", "chronos-mini"
        if chronos_size == "Bolt Base":
            return "amazon/chronos-bolt-base", "chronos-base"
        return "amazon/chronos-t5-large", "chronos-large"

    total = len(mids) * max(1, len(params))
    prog = st.progress(0)
    log = st.empty()

    done = 0
    ridge_trained = 0
    chronos_trained = 0
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

                hist = pd.DataFrame(
                    {
                        "Datetime": pd.to_datetime(df["datetime_utc"], utc=True, errors="coerce"),
                        "Value": pd.to_numeric(df["value"], errors="coerce"),
                    }
                ).dropna()

                if len(hist) < int(min_points):
                    skipped += 1
                    continue

                # Ridge (fixed or tuned)
                if auto_alpha:
                    grid = [float(x) for x in (alpha_grid or [0.1, 1.0, 10.0, 100.0])]
                    artifacts = tune_ridge_alpha(hist, alphas=grid)
                else:
                    artifacts = train_ridge_from_history(hist, alpha=float(alpha))

                out_dir = model_dir(station_id=f"USGS-{site}", parameter=str(pcode), model_key="ridge")
                save_ridge_artifacts(out_dir, artifacts)
                ridge_trained += 1

                # Chronos optimization
                if chronos_enable and optimize_chronos_context and save_chronos_artifacts:
                    model_id, ch_key = _chronos_choice()
                    ch = optimize_chronos_context(
                        hist,
                        model_id=model_id,
                        candidates_hours=[int(x) for x in (chronos_candidates or [24, 48, 72, 168, 336])],
                        eval_points=int(chronos_eval_points),
                        num_samples=20,
                    )
                    ch_dir = model_dir(station_id=f"USGS-{site}", parameter=str(pcode), model_key=ch_key)
                    save_chronos_artifacts(ch_dir, ch)
                    chronos_trained += 1

            except Exception as e:
                errors += 1
                log.warning(f"Error training for {mid} / {pcode}: {e}")

            prog.progress(min(1.0, done / max(1, total)))

    st.success(
        "Done.\n\n"
        f"- Ridge trained: {ridge_trained}\n"
        f"- Chronos optimized: {chronos_trained}\n"
        f"- Skipped: {skipped}\n"
        f"- Errors: {errors}\n"
        f"- Total combos scanned: {total}"
    )
