# core/ui/forecasting.py

from __future__ import annotations

import json
from io import BytesIO
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from core.forecast_models.base import ForecastRequest
from core.forecast_models.output_schema import (
    StationForecastBundle,
    build_forecast_run_artifact,
    forecast_output_to_rows,
    rows_to_frame,
)
from core.forecast_models.pi import gaussian_residual_pi
from core.forecast_models.registry import create_model
from core.forecast_models.paths import model_dir

from core.cache.get_station_timeseries import (
    _site_from_monitoring_location_id,
    ensure_iv_window,
    PCODE_FLOW,
    PCODE_STAGE,
)

# Optional water-quality parameter catalog (keep Forecasting dropdown consistent with Plot Time Series).
# We try to import the same catalog used elsewhere; if unavailable, we fall back to a small, safe set.
try:
    from core.cache.get_station_timeseries import (
        ALL_PARAMETERS,
        PCODE_TEMP,
        PCODE_SC,
        PCODE_DO,
        PCODE_PH,
        PCODE_TURB,
    )
except Exception:
    ALL_PARAMETERS = [
        str(PCODE_FLOW),
        str(PCODE_STAGE),
        "00010",  # temperature
        "00095",  # specific conductance
        "00300",  # dissolved oxygen
        "00400",  # pH
        "63680",  # turbidity
    ]
    PCODE_TEMP = "00010"
    PCODE_SC = "00095"
    PCODE_DO = "00300"
    PCODE_PH = "00400"
    PCODE_TURB = "63680"


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
    end = pd.Timestamp.utcnow().floor("h")
    if end.tzinfo is None:
        end = end.tz_localize("UTC")
    else:
        end = end.tz_convert("UTC")

    idx = pd.date_range(end - pd.Timedelta(hours=hours - 1), periods=hours, freq="h", tz="UTC")

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
    # More compact, slide-friendly canvas
    fig = plt.figure(figsize=(10, 4.6), dpi=110)
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
                    d["timestamp_utc"].dt.to_pydatetime().astype("datetime64[ns]"),
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
    ax.legend(
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        borderaxespad=0.0,
        frameon=True,
    )
    fig.autofmt_xdate()

    fig.tight_layout()
    
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150) #, bbox_inches="tight", pad_inches=0.2)
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
            key="fcst_scope",
        )
    with top2:
        st.caption(f"Selected in Explorer: **{len(selected_ids)}**")

    if scope == "Choose stations":
        station_ids = st.multiselect(
            "Stations",
            options=selected_ids,
            default=selected_ids[:1] if selected_ids else [],
            key="fcst_station_ids",
        )
    else:
        station_ids = selected_ids

    if not station_ids:
        st.warning("Choose at least one station to proceed.")
        return

    # --- Parameter selection (consistent with Plot Time Series) ---
    # Always show the app-wide parameter catalog; per-station availability is handled during execution.
    param_labels = {
        str(PCODE_FLOW): "00060 – Flow (Discharge)",
        str(PCODE_STAGE): "00065 – Stage (Gage height)",
        str(PCODE_TEMP): "00010 – Water temperature",
        str(PCODE_SC):   "00095 – Specific conductance",
        str(PCODE_DO):   "00300 – Dissolved oxygen",
        str(PCODE_PH):   "00400 – pH",
        str(PCODE_TURB): "63680 – Turbidity",
    }

    role_norm = (role or "").lower().strip()
    if role_norm == "playground":
        parameter_code = str(PCODE_STAGE)
        st.info("Playground is restricted to parameter **00065 (Stage)**.")
    else:
        # Plot Time Series behavior: show all known parameters, try per station, warn if missing.
        _all_params_str = [str(p) for p in ALL_PARAMETERS]
        parameter_code = st.selectbox(
            "Parameter",
            options=_all_params_str,
            format_func=lambda p: param_labels.get(str(p), str(p)),
            index=_all_params_str.index(str(PCODE_STAGE)) if str(PCODE_STAGE) in _all_params_str else 0,
            key="fcst_parameter_code",
        )

    if role_norm == "playground":
        history_days = 1
    else:
        history_days = st.selectbox("History window (days)", options=[1, 2, 3, 5, 7], index=4)

    model_options = _model_options_for_role(role)

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        model_label = st.selectbox(
            "Model",
            options=list(model_options.keys()),
            index=0,
            key="fcst_model_label",
        )
    with c2:
        if (role or "").lower().strip() == "playground":
            horizon = st.number_input("Horizon (hours)", min_value=1, max_value=3, value=1, step=1)
        else:
            horizon = st.selectbox("Horizon (hours)", options=[24, 48, 72], index=0)
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

    if (role or "").lower().strip() in ("admin", "user"):
        st.caption("Admin/User: Chronos-Base and Chronos-Large are enabled for benchmarking.")

    if not run:
        st.info("Configure the options above, then click **Run forecast**.")
        return

    horizon_i = int(horizon)
    interval_label = "80%"
    pi_method_label = "GaussianResidual(80%)" if use_pi else "None"

    rows: list[dict] = []
    history_by_station: dict[str, pd.DataFrame] = {}
    station_bundles: list[StationForecastBundle] = []
    analysis_inputs: dict[str, dict] = {}

    for station_id in station_ids:
        site_no = _site_from_monitoring_location_id(station_id)

        try:
            df_iv = ensure_iv_window(site_no, parameter_code, days=int(history_days))
        except Exception as e:
            df_iv = pd.DataFrame()
            st.warning(
                f"IV history load failed for {station_id} {parameter_code}: {e}. Skipping."
            )

        if df_iv is None or df_iv.empty:
            st.warning(f"No IV data returned for station {station_id} parameter {parameter_code}. Skipping.")
            continue
        else:
            history_df = df_iv.copy()
            if "datetime_utc" in history_df.columns:
                history_df["Datetime"] = pd.to_datetime(history_df["datetime_utc"], utc=True, errors="coerce")
            else:
                history_df["Datetime"] = pd.to_datetime(history_df.get("Datetime"), utc=True, errors="coerce")

            if "value" in history_df.columns:
                history_df["Value"] = pd.to_numeric(history_df["value"], errors="coerce")
            else:
                history_df["Value"] = pd.to_numeric(history_df.get("Value"), errors="coerce")

            history_df = history_df.dropna(subset=["Datetime", "Value"]).sort_values("Datetime")
            history_df = history_df[["Datetime", "Value"]]

            if history_df.empty:
                st.warning(
                    f"No usable rows after cleaning for station {station_id} parameter {parameter_code}. Skipping."
                )
                continue

        history_by_station[station_id] = history_df

        # Artifacts directory (may not exist yet; model implementations decide behavior)
        art_dir = model_dir(station_id, parameter=str(parameter_code), model_key=selected_model_key)

        # Instantiate model
        model = create_model(selected_model_key)

        # Load artifacts; if missing for non-persistence, fallback to persistence
        try:
            artifacts = model.load_artifacts(art_dir, station_id, parameter=str(parameter_code))
            used_model_label = model_label
        except FileNotFoundError:
            if selected_model_key != "persistence":
                st.warning(
                    f"Artifacts not found for **{model_label}** on station **{station_id}**. "
                    "Train this model in Admin/User training first. Falling back to **Persistence**."
                )
            model = create_model("persistence")
            art_dir_eff = model_dir(station_id, parameter=str(parameter_code), model_key="persistence")
            try:
                artifacts = model.load_artifacts(art_dir_eff, station_id, parameter=str(parameter_code))
            except FileNotFoundError:
                artifacts = {}
            used_model_label = "Persistence"

        used_model_key = model.model_key

        # Inject UI noise into persistence artifacts (clamped inside the model)
        if model.model_key == "persistence":
            artifacts = dict(artifacts)
            artifacts["noise"] = float(noise_frac)

        req = ForecastRequest(
            station_id=station_id,
            parameter=str(parameter_code),
            history=history_df[["Datetime", "Value"]].copy(),
            horizon=horizon_i,
            session_seed=session_seed,
        )

        out = model.predict(req, artifacts)
        y_pred = out.y_pred
        sigma = float(out.sigma_residual)

        if use_pi:
            pi = gaussian_residual_pi(y_pred, sigma, level=0.8)
            pi_low = pi.lower
            pi_high = pi.upper
        else:
            pi_low = pd.Series([np.nan] * len(y_pred), index=y_pred.index, name="pi_low")
            pi_high = pd.Series([np.nan] * len(y_pred), index=y_pred.index, name="pi_high")

        bundle = StationForecastBundle(
            station_id=station_id,
            parameter=str(parameter_code),
            requested_model_key=selected_model_key,
            requested_model_label=model_label,
            used_model_key=used_model_key,
            used_model_label=used_model_label,
            forecast_output=out,
            history_df=history_df.copy(),
            pi_low=pi_low if use_pi else None,
            pi_high=pi_high if use_pi else None,
        )
        station_bundles.append(bundle)
        analysis_inputs[station_id] = {
            "forecast_output": out,
            "history_df": history_df.copy(),
            "used_model_key": used_model_key,
            "used_model_label": used_model_label,
        }
        rows.extend(
            forecast_output_to_rows(
                bundle=bundle,
                horizon_h=horizon_i,
                interval_label=interval_label,
                pi_method_label=pi_method_label,
            )
        )

    df_fcst = rows_to_frame(rows)

    if df_fcst.empty:
        st.warning("No stations returned data for the selected parameter. Nothing to forecast.")
        return

    forecast_run_artifact = build_forecast_run_artifact(
        station_bundles=station_bundles,
        requested_model_key=selected_model_key,
        requested_model_label=model_label,
        parameter=str(parameter_code),
        horizon_h=horizon_i,
        interval_label=interval_label,
        pi_method_label=pi_method_label,
        session_seed=session_seed,
    )

    st.session_state["latest_forecast_run_artifact"] = forecast_run_artifact
    st.session_state["latest_forecast_analysis_inputs"] = analysis_inputs
    st.session_state["latest_forecast_df"] = df_fcst.copy()
    st.session_state["latest_station_ids"] = station_ids
    st.session_state["latest_model_key"] = selected_model_key
    st.session_state["latest_horizon"] = horizon_i

    # Backward compatibility for callers that still expect single-station keys.
    if station_bundles:
        first_station_id = station_bundles[0].station_id
        first_input = analysis_inputs[first_station_id]
        st.session_state["latest_forecast_output"] = first_input["forecast_output"]
        st.session_state["latest_history_df"] = first_input["history_df"].copy()

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
    json_bytes = json.dumps(forecast_run_artifact, indent=2).encode("utf-8")
    st.download_button(
        "Download forecast run JSON",
        data=json_bytes,
        file_name="forecast_run.json",
        mime="application/json",
    )

    with st.expander("Forecast run artifact (JSON)", expanded=False):
        st.json(forecast_run_artifact)
