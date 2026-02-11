# core/ui/forecasting.py

from __future__ import annotations

from io import BytesIO
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from core.forecast_models import PersistenceConfig, PersistenceForecast


def _future_index_utc(horizon_hours: int) -> pd.DatetimeIndex:
    now = pd.Timestamp.utcnow().floor("H")
    return pd.date_range(now + pd.Timedelta(hours=1), periods=horizon_hours, freq="H", tz="UTC")


def _pi_level(interval_label: str) -> float:
    return {"80%": 0.8, "90%": 0.9, "95%": 0.95}.get(interval_label, 0.9)


def _station_base_value(station_id: str) -> float:
    """Deterministic per-station base so plots aren't identical even before wiring real data."""
    h = abs(hash(station_id)) % 10_000
    return 1.0 + (h / 10_000.0)  # [1.0, 2.0)


def _build_persistence_forecast(
    station_ids: list[str],
    horizon_hours: int,
    interval_label: str,
    noise_frac: float,
    pi_method: str,
    native_quantiles: Optional[list[float]] = None,
    bootstrap_samples: int = 200,
    conformal_growth: float = 0.15,
) -> pd.DataFrame:
    """Persistence baseline forecast with optional noise + PI.

    noise_frac: sigma as a fraction of last_value (0 = pure persistence, horizontal line)
    PI methods:
      - Native: if model provides quantiles (placeholder here). If not, falls back to Bootstrap behavior.
      - Conformal: heuristic conformal-style widening with horizon (until real calibration is wired).
      - Bootstrap: sample paths from N(0, sigma) and take quantiles per horizon step.
    """
    future = _future_index_utc(horizon_hours)
    level = _pi_level(interval_label)

    # Map nominal PI level -> lower/upper quantiles
    q_low = (1.0 - level) / 2.0
    q_high = 1.0 - q_low

    rows: list[dict] = []
    for sid in station_ids:
        last_value = _station_base_value(sid)
        # v0.4.0: use the real persistence model implementation.
        model = PersistenceForecast(
            PersistenceConfig(
                noise_frac=float(noise_frac),
                connect_last_measured=False,  # UI expects only future steps
                reject_nulls=True,
                preserve_integers_if_series_integer=True,
            )
        )

        sigma = float(noise_frac) * float(abs(last_value) if last_value != 0 else 1.0)

        # Deterministic RNG per station/options (good for reproducible UI tests)
        seed = abs(hash((sid, horizon_hours, interval_label, noise_frac, pi_method))) % (2**32 - 1)
        rng = np.random.default_rng(seed)

        # Core persistence forecast (measured series is placeholder: only the last value)
        y_hat_list = model.forecast([float(last_value)], horizon_hours, seed=int(seed))
        y_hat = np.asarray(y_hat_list, dtype=float)

        # Prediction intervals
        pi_low = np.empty_like(y_hat, dtype=float)
        pi_high = np.empty_like(y_hat, dtype=float)

        if pi_method == "Bootstrap" or (pi_method == "Native" and not native_quantiles):
            # Bootstrap around y_hat using the same sigma (placeholder, until real residual structure exists)
            if sigma == 0:
                # Avoid degenerate quantiles
                width = 0.03 * abs(last_value) if last_value != 0 else 0.03
                # widen with horizon a bit
                for i in range(horizon_hours):
                    w = width * (1.0 + 0.01 * i)
                    pi_low[i] = y_hat[i] - w
                    pi_high[i] = y_hat[i] + w
            else:
                sims = y_hat[None, :] + rng.normal(0.0, sigma, size=(int(bootstrap_samples), horizon_hours))
                pi_low[:] = np.quantile(sims, q_low, axis=0)
                pi_high[:] = np.quantile(sims, q_high, axis=0)

        elif pi_method == "Conformal":
            # Heuristic conformal-like band: PI widens with horizon.
            # In a real implementation, we'd compute residual quantiles on a calibration split.
            base_scale = sigma if sigma > 0 else 0.05 * (abs(last_value) if last_value != 0 else 1.0)
            # Horizon-dependent widening
            for i in range(horizon_hours):
                step = i + 1
                widen = 1.0 + conformal_growth * (step / max(1, horizon_hours))
                band = base_scale * widen
                pi_low[i] = y_hat[i] - band
                pi_high[i] = y_hat[i] + band

        else:  # Native (placeholder)
            # If native quantiles are provided, we use them as overrides; otherwise, fallback handled above.
            # Here we emulate "native" by producing symmetric bounds using sigma and the requested quantiles.
            if sigma == 0:
                sigma = 0.05 * (abs(last_value) if last_value != 0 else 1.0)
            # Convert requested quantiles into bounds; pick closest to q_low/q_high
            qs = sorted(set([q_low, q_high] + (native_quantiles or [])))
            lo_q = min(qs, key=lambda q: abs(q - q_low))
            hi_q = min(qs, key=lambda q: abs(q - q_high))
            sims = y_hat[None, :] + rng.normal(0.0, sigma, size=(int(bootstrap_samples), horizon_hours))
            pi_low[:] = np.quantile(sims, lo_q, axis=0)
            pi_high[:] = np.quantile(sims, hi_q, axis=0)

        for ts, yh, lo, hi in zip(future, y_hat, pi_low, pi_high):
            rows.append(
                {
                    "station_id": sid,
                    "model": "Persistence (baseline)",
                    "horizon_h": horizon_hours,
                    "interval": interval_label,
                    "pi_method": pi_method,
                    "timestamp_utc": ts,
                    "y_hat": float(yh),
                    "pi_low": float(lo),
                    "pi_high": float(hi),
                }
            )

    return pd.DataFrame(rows)


def _build_placeholder_forecast(
    station_ids: list[str],
    model_name: str,
    horizon_hours: int,
    interval_label: str,
) -> pd.DataFrame:
    """Create a deterministic placeholder forecast table.

    Output contract (stable going forward):
      - station_id
      - model
      - horizon_h
      - interval
      - pi_method
      - timestamp_utc
      - y_hat
      - pi_low
      - pi_high
    """
    future = _future_index_utc(horizon_hours)

    level = _pi_level(interval_label)
    width0 = 0.10
    width_growth = 0.005 * (horizon_hours / 24.0)
    width = (width0 + width_growth) * (1.0 + (level - 0.8))

    rows: list[dict] = []
    for sid in station_ids:
        base = _station_base_value(sid)
        for i, ts in enumerate(future, start=1):
            y_hat = base + 0.02 * i  # deterministic small trend
            pi_low = y_hat * (1.0 - width)
            pi_high = y_hat * (1.0 + width)
            rows.append(
                {
                    "station_id": sid,
                    "model": model_name,
                    "horizon_h": horizon_hours,
                    "interval": interval_label,
                    "pi_method": "Heuristic",
                    "timestamp_utc": ts,
                    "y_hat": float(y_hat),
                    "pi_low": float(pi_low),
                    "pi_high": float(pi_high),
                }
            )

    return pd.DataFrame(rows)


def _render_forecast_plot(df: pd.DataFrame, station_ids: list[str], title: str) -> tuple[plt.Figure, bytes]:
    """Render a simple multi-station plot and return (fig, png_bytes)."""

    fig = plt.figure()
    ax = fig.add_subplot(111)

    for sid in station_ids:
        d = df[df["station_id"] == sid].copy()
        if d.empty:
            continue
        d = d.sort_values("timestamp_utc")
        ax.plot(d["timestamp_utc"], d["y_hat"], label=str(sid))
        ax.fill_between(
            d["timestamp_utc"].dt.to_pydatetime(),
            d["pi_low"].values,
            d["pi_high"].values,
            alpha=0.15,
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


def render_forecasting(role: Optional[str] = None) -> None:
    """Forecasting tab.

    v0.3.0 goal: UI + stable output contract + export buttons.
    Real models are wired in later versions.
    """

    st.markdown("### Forecasting")

    selected_ids = (st.session_state.get("explorer_selected_ids", []) or []).copy()
    if not selected_ids:
        st.info("Select at least one station in **Explorer & Map** to enable forecasting.")
        return

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

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        model = st.selectbox(
            "Model",
            options=[
                "Persistence (baseline)",
                "Ridge Regressor (planned)",
                "Chronos-Bolt (planned)",
                "Foundation model (planned)",
            ],
            index=0,
        )
    with c2:
        horizon = st.number_input("Horizon (hours)", min_value=1, max_value=168, value=24, step=1)
    with c3:
        interval = st.selectbox("Prediction interval", options=["80%", "90%", "95%"], index=1)
    with c4:
        run = st.button("Run forecast", type="primary")

    # --- Model-specific controls (minimal, v0.3.0) ---
    if model == "Persistence (baseline)":
        noise_frac = st.slider(
            "Noise (σ as fraction of last value)",
            min_value=0.0,
            max_value=0.50,
            value=0.0,
            step=0.01,
            help="0.00 = pure persistence (horizontal line). Increase slightly (e.g., 0.02–0.05) for visual separation.",
        )
    else:
        noise_frac = 0.0

    with st.expander("Uncertainty / Prediction Interval (PI) options", expanded=True):
        pi_method = st.radio(
            "PI method",
            options=["Native (if available)", "Conformal", "Bootstrap"],
            index=1,
            horizontal=True,
            help="Native uses model-provided quantiles (e.g., Chronos). Conformal/Bootstrap are generic methods.",
        )

        native_quantiles: list[float] = []
        if pi_method == "Native (if available)":
            if "Chronos" in model:
                native_quantiles = st.multiselect(
                    "Native quantiles (if provided by the model)",
                    options=[0.01, 0.05, 0.10, 0.20, 0.50, 0.80, 0.90, 0.95, 0.99],
                    default=[0.10, 0.90],
                )
                st.caption("Chronos-Bolt is planned; this will be wired once the model is integrated.")
            else:
                st.warning("This model does not expose native quantiles yet. It will fall back to Bootstrap behavior.")

        if pi_method == "Bootstrap":
            bootstrap_samples = st.number_input("Bootstrap samples", min_value=50, max_value=2000, value=200, step=50)
        else:
            bootstrap_samples = 200

        if pi_method == "Conformal":
            conformal_growth = st.slider(
                "Conformal widening with horizon",
                min_value=0.0,
                max_value=1.0,
                value=0.15,
                step=0.05,
                help="Heuristic widening factor (placeholder) until calibration residuals are wired.",
            )
        else:
            conformal_growth = 0.15

    st.caption(
        "Forecast output schema is stable and exportable (CSV/PNG). "
        "Persistence is implemented; other models will be wired next."
    )

    if not run:
        st.info("Configure the options above, then click **Run forecast**.")
        return

    horizon_i = int(horizon)

    if model == "Persistence (baseline)":
        df_fcst = _build_persistence_forecast(
            station_ids=station_ids,
            horizon_hours=horizon_i,
            interval_label=interval,
            noise_frac=float(noise_frac),
            pi_method="Native" if pi_method.startswith("Native") else pi_method,
            native_quantiles=native_quantiles or None,
            bootstrap_samples=int(bootstrap_samples),
            conformal_growth=float(conformal_growth),
        )
        title = f"Forecast — Persistence | PI: {pi_method}"
    else:
        df_fcst = _build_placeholder_forecast(
            station_ids=station_ids,
            model_name=model,
            horizon_hours=horizon_i,
            interval_label=interval,
        )
        title = "Forecast (placeholder)"

    # --- Plot (downloadable) ---
    st.markdown("#### Forecast plot")
    fig, png_bytes = _render_forecast_plot(df_fcst, station_ids, title=title)
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
