# core/ui/forecasting.py

from __future__ import annotations

from io import BytesIO
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from core.forecast_models.base import ForecastRequest
from core.forecast_models.pi import gaussian_residual_pi
from core.forecast_models.registry import create_model
from core.forecast_models.paths import model_dir


# -----------------------------
# Synthetic history (v0.4.1)
# -----------------------------
def _station_base_value(station_id: str) -> float:
    """Deterministic per-station base so plots aren't identical even before wiring real data."""
    h = abs(hash(station_id)) % 10_000
    return 1.0 + (h / 10_000.0)  # [1.0, 2.0)


def _build_synthetic_history_utc(station_id: str, hours: int = 14 * 24) -> pd.DataFrame:
    """Create a deterministic hourly history with mild variability.

    This is a temporary stand-in until real station/parameter time series are wired.
    """
    end = pd.Timestamp.utcnow().floor("H")
    if end.tzinfo is None:
        end = end.tz_localize("UTC")
    else:
        end = end.tz_convert("UTC")

    idx = pd.date_range(end - pd.Timedelta(hours=hours - 1), periods=hours, freq="H", tz="UTC")

    base = _station_base_value(station_id)

    # Deterministic RNG per station for stable visuals
    seed = abs(hash(("synthetic_history", station_id))) % (2**32 - 1)
    rng = np.random.default_rng(seed)

    # Gentle daily sinusoid + tiny noise to allow sigma estimation
    t = np.arange(hours, dtype=float)
    daily = 0.05 * np.sin(2.0 * np.pi * (t / 24.0))
    noise = rng.normal(0.0, 0.01, size=hours)

    values = base * (1.0 + daily) + noise

    return pd.DataFrame({"Datetime": idx, "Value": values})


# -----------------------------
# Plotting / export
# -----------------------------
def _render_forecast_plot(
    df_fcst: pd.DataFrame,
    history_by_station: dict[str, pd.DataFrame],
    station_ids: list[str],
    title: str,
    history_tail_hours: int = 72,
) -> tuple[plt.Figure, bytes]:
    """Render a multi-station plot with measured history + forecast.

    - Measured: solid line
    - Forecast: dashed line (+ markers), same color as measured
    - PI: shaded band (or errorbar if horizon==1)
    """
    fig = plt.figure()
    ax = fig.add_subplot(111)

    for sid in station_ids:
        # ---- measured history ----
        hist = history_by_station.get(sid)
        if hist is None or hist.empty:
            continue
        h = hist.sort_values("Datetime").copy()
        h["Datetime"] = pd.to_datetime(h["Datetime"], utc=True)
        if history_tail_hours and len(h) > history_tail_hours:
            h = h.iloc[-history_tail_hours:]

        measured_line = ax.plot(
            h["Datetime"],
            h["Value"].astype(float).values,
            label=f"{sid} (measured)",
            linestyle="-",
        )
        color = measured_line[0].get_color()

        # ---- forecast ----
        d = df_fcst[df_fcst["station_id"] == sid].copy()
        if d.empty:
            continue
        d = d.sort_values("timestamp_utc")
        d["timestamp_utc"] = pd.to_datetime(d["timestamp_utc"], utc=True)

        # For readability, connect the last measured point to the first forecast point
        # by prepending the last measured point to the forecast curve.
        x_fc = d["timestamp_utc"]
        y_fc = d["y_hat"].astype(float)

        x0 = h["Datetime"].iloc[-1]
        y0 = float(h["Value"].iloc[-1])

        x_plot = pd.Index([x0]).append(pd.Index(x_fc))  # Index.append ainda existe
        y_plot = pd.concat(
            [pd.Series([y0], index=[x0]), pd.Series(y_fc.values, index=x_fc)],
            axis=0,
        )

        ax.plot(
            x_plot,
            y_plot.values,
            linestyle="--",
            marker="o",
            markersize=3,
            color=color,
            label=f"{sid} (forecast)",
        )

        # ---- PI ----
        if "pi_low" in d.columns and "pi_high" in d.columns and d["pi_low"].notna().any():
            lo = d["pi_low"].astype(float).values
            hi = d["pi_high"].astype(float).values
            if len(d) >= 2:
                ax.fill_between(
                    d["timestamp_utc"].dt.to_pydatetime(),
                    lo,
                    hi,
                    alpha=0.15,
                    color=color,
                )
            else:
                # Horizon==1: fill_between won't be visible; draw an errorbar band instead.
                x = d["timestamp_utc"].iloc[0].to_pydatetime()
                y = float(d["y_hat"].iloc[0])
                yerr = [[y - float(d["pi_low"].iloc[0])], [float(d["pi_high"].iloc[0]) - y]]
                ax.errorbar(
                    [x],
                    [y],
                    yerr=yerr,
                    fmt="o",
                    color=color,
                    alpha=0.35,
                    capsize=3,
                )

    ax.set_title(title)
    ax.set_xlabel("Time (UTC)")
    ax.set_ylabel("Value")
    ax.legend(loc="best")
    fig.autofmt_xdate()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    png_bytes = buf.getvalue()
    buf.close()
    return fig, png_bytes


# -----------------------------
# UI
# -----------------------------
# -----------------------------
# Model options (role-aware)
# -----------------------------
# PlayGround policy: Tiny/Mini only.
# User/Admin: may also use Bolt Base and T5 Large for benchmarking.
_BASE_MODEL_OPTIONS = {
    "Persistence": "persistence",
    "Ridge": "ridge",
    "Chronos-Tiny": "chronos-tiny",
    "Chronos-Mini": "chronos-mini",
}
_ADMIN_USER_EXTRAS = {
    "Chronos-Base": "chronos-base",     # amazon/chronos-bolt-base
    "Chronos-Large": "chronos-large",   # amazon/chronos-t5-large
}


def _model_options_for_role(role: Optional[str]) -> dict[str, str]:
    r = (role or "").lower().strip()
    opts = dict(_BASE_MODEL_OPTIONS)
    if r in ("admin", "user"):
        opts.update(_ADMIN_USER_EXTRAS)
    return opts


def render_forecasting(role: Optional[str] = None) -> None:
    """Forecasting tab (PlayGround).

    v0.5.x PlayGround policy:
      - Horizon limited to 1–3 steps
      - No training in PlayGround (Admin/User train elsewhere)
      - No History Range limit (UI may show large spans)
      - Allowed models (PlayGround): Persistence, Ridge, Chronos-Tiny, Chronos-Mini
      - User/Admin extras: Chronos-Base, Chronos-Large
      - PI: Gaussian residual-based PI only (80% fixed)
      - Persistence noise: 0..0.05, deterministic seed per session
      - No guardrails/quotas beyond the above
    """
    st.markdown("### Forecasting")

    selected_ids = (st.session_state.get("explorer_selected_ids", []) or []).copy()
    if not selected_ids:
        st.info("Select at least one station in **Explorer & Map** to enable forecasting.")
        return

    # Session seed (fixed for reproducibility in a session)
    if "session_seed" not in st.session_state:
        sid = st.session_state.get("session_id", None)
        st.session_state.session_seed = abs(hash(sid if sid is not None else "waterainalytics")) % (2**32 - 1)
    session_seed = int(st.session_state.session_seed)

    # --- Controls ---
    top1, top2 = st.columns([2, 1])
    with top1:
        scope = st.radio(
            "Forecast scope",
            options=["All selected stations", "Choose stations"],
            horizontal=True,
            index=0,
        )
    with top2:
        st.caption(f"Selected in Explorer: **{len(selected_ids)}**")

    if scope == "Choose stations":
        station_ids = st.multiselect(
            "Stations",
            options=selected_ids,
            default=selected_ids[:1] if selected_ids else [],
        )
    else:
        station_ids = selected_ids

    if not station_ids:
        st.warning("Choose at least one station to proceed.")
        return

    model_options = _model_options_for_role(role)

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        model_label = st.selectbox(
            "Model",
            options=list(model_options.keys()),
            index=0,
        )
    with c2:
        horizon = st.number_input("Horizon (steps)", min_value=1, max_value=3, value=1, step=1)
    with c3:
        use_pi = st.toggle("Show prediction interval (80%)", value=True)
    with c4:
        run = st.button("Run forecast", type="primary")

    selected_model_key = model_options[model_label]

    # --- Model-specific controls ---
    if selected_model_key == "persistence":
        noise_frac = st.slider(
            "Noise (±fraction of last value)",
            min_value=0.0,
            max_value=0.05,
            value=0.0,
            step=0.005,
            help="0.00 = pure persistence. Increase slightly (e.g., 0.01–0.03) for visual separation.",
        )
    else:
        noise_frac = 0.0

    st.caption(
        "PlayGround uses a fixed, fast PI: **Gaussian residual-based 80% interval**. "
        "Training is disabled here (Admin/User training only)."
    )

    if (role or '').lower().strip() in ('admin', 'user'):
        st.caption("Admin/User: Chronos-Base and Chronos-Large are enabled for benchmarking.")

    if not run:
        st.info("Configure the options above, then click **Run forecast**.")
        return

    horizon_i = int(horizon)
    interval_label = "80%"
    pi_method_label = "GaussianResidual(80%)" if use_pi else "None"

    rows: list[dict] = []
    history_by_station: dict[str, pd.DataFrame] = {}

    # NOTE: Until real data is wired, we generate a synthetic history per station.
    for station_id in station_ids:
        history_df = _build_synthetic_history_utc(station_id, hours=14 * 24)
        history_by_station[station_id] = history_df

        # Artifacts directory (may not exist yet; model implementations decide behavior)
        art_dir = model_dir(station_id, parameter="Value", model_key=selected_model_key)

        # Instantiate model
        model = create_model(selected_model_key)

        # Load artifacts; if missing for non-persistence, fallback to persistence
        try:
            artifacts = model.load_artifacts(art_dir, station_id, parameter="Value")
            used_model_label = model_label
        except FileNotFoundError:
            if selected_model_key != "persistence":
                st.warning(
                    f"Artifacts not found for **{model_label}** on station **{station_id}**. "
                    "Train this model in Admin/User training first. Falling back to **Persistence**."
                )
            model = create_model("persistence")
            art_dir_eff = model_dir(station_id, parameter="Value", model_key="persistence")
            try:
                artifacts = model.load_artifacts(art_dir_eff, station_id, parameter="Value")
            except FileNotFoundError:
                artifacts = {}
            used_model_label = "Persistence"

        # Inject UI noise into persistence artifacts (clamped inside the model)
        if model.model_key == "persistence":
            artifacts = dict(artifacts)
            artifacts["noise"] = float(noise_frac)

        req = ForecastRequest(
            station_id=station_id,
            parameter="Value",
            history=history_df[["Datetime", "Value"]].copy(),
            horizon=horizon_i,
            session_seed=session_seed,
        )

        out = model.predict(req, artifacts)
        y_pred = out.y_pred
        sigma = float(out.sigma_residual)

        # --- Persist latest forecast for Agentic Analysis ---
        st.session_state["latest_forecast_output"] = out
        st.session_state["latest_history_df"] = history_df.copy()
        st.session_state["latest_station_ids"] = station_ids
        st.session_state["latest_model_key"] = selected_model_key
        st.session_state["latest_horizon"] = horizon_i

        if use_pi:
            pi = gaussian_residual_pi(y_pred, sigma, level=0.8)
            pi_low = pi.lower
            pi_high = pi.upper
        else:
            pi_low = pd.Series([np.nan] * len(y_pred), index=y_pred.index, name="pi_low")
            pi_high = pd.Series([np.nan] * len(y_pred), index=y_pred.index, name="pi_high")

        for ts in y_pred.index:
            rows.append(
                {
                    "station_id": station_id,
                    "model": used_model_label,
                    "horizon_h": horizon_i,
                    "interval": interval_label,
                    "pi_method": pi_method_label,
                    "timestamp_utc": ts,
                    "y_hat": float(y_pred.loc[ts]),
                    "pi_low": float(pi_low.loc[ts]) if use_pi else np.nan,
                    "pi_high": float(pi_high.loc[ts]) if use_pi else np.nan,
                }
            )

    df_fcst = pd.DataFrame(rows)

    title = f"Forecast — {model_label} | PI: {pi_method_label}"

    # --- Plot (downloadable) ---
    st.markdown("#### Forecast plot")
    fig, png_bytes = _render_forecast_plot(
        df_fcst=df_fcst,
        history_by_station=history_by_station,
        station_ids=station_ids,
        title=title,
        history_tail_hours=72,
    )
    st.pyplot(fig, clear_figure=False)
    st.download_button(
        "Download plot (PNG)",
        data=png_bytes,
        file_name="forecast_plot.png",
        mime="image/png",
    )

    # --- Table (downloadable + copy-friendly) ---
    st.markdown("#### Forecast table")
    st.dataframe(df_fcst, width="stretch", hide_index=True)

    csv_bytes = df_fcst.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download forecast CSV",
        data=csv_bytes,
        file_name="forecast.csv",
        mime="text/csv",
    )

    with st.expander("Copy as CSV (manual)", expanded=False):
        st.text_area("CSV", value=df_fcst.to_csv(index=False), height=200)
