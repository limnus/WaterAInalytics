# core/ui/admin_models.py
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from core.cache.get_station_timeseries import (
    _site_from_monitoring_location_id,
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
    """Return repository root (folder that contains app.py).

    For this file (core/ui/admin_models.py):
    - parents[0] = core/ui
    - parents[1] = core
    - parents[2] = project root
    """
    return Path(__file__).resolve().parents[2]


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


def _load_cached_sites(out_root: str = "iv_cache") -> list[str]:
    """Return USGS site_no values that already have IV cache on disk.

    This intentionally *does not* consult the stations CSV, because that file
    represents a candidate universe and can be much larger than what has been
    cached. Admin training should not trigger new downloads by default.
    """
    base = _project_root() / out_root
    if not base.exists() or not base.is_dir():
        return []
    sites: list[str] = []
    for p in sorted(base.iterdir()):
        if p.is_dir() and p.name.isdigit():
            sites.append(p.name)
    return sites


def _read_iv_window_cached(
    *,
    site: str,
    parameter_code: str,
    days: int,
    out_root: str = "iv_cache",
) -> pd.DataFrame:
    """Read IV cache for a window *without downloading missing days*.

    Mirrors the read path of ensure_iv_window(), but never performs network IO.
    """
    from datetime import datetime, timedelta

    if days <= 0:
        raise ValueError("days must be a positive integer")

    today_utc = datetime.utcnow().date()
    window_dates = [today_utc - timedelta(days=i) for i in range(days)]

    base_dir = _project_root() / out_root / site / str(parameter_code)
    frames: list[pd.DataFrame] = []

    for d in window_dates:
        path = base_dir / f"{d.isoformat()}.parquet"
        if not path.exists():
            continue
        try:
            df_day = pd.read_parquet(path)
        except Exception:
            continue

        if "site_no" not in df_day.columns:
            df_day["site_no"] = site
        if "parameter_code" not in df_day.columns:
            df_day["parameter_code"] = str(parameter_code)
        if "unit" not in df_day.columns:
            df_day["unit"] = None

        if "datetime_utc" in df_day.columns:
            df_day["datetime_utc"] = pd.to_datetime(df_day["datetime_utc"], utc=True, errors="coerce")
        elif "datetime" in df_day.columns:
            df_day["datetime_utc"] = pd.to_datetime(df_day["datetime"], utc=True, errors="coerce")
        else:
            continue

        if "date_utc" not in df_day.columns:
            df_day["date_utc"] = df_day["datetime_utc"].dt.date.astype(str)

        frames.append(df_day)

    if not frames:
        return pd.DataFrame(columns=["site_no", "parameter_code", "unit", "datetime_utc", "value", "date_utc"])

    df_out = pd.concat(frames, ignore_index=True)
    df_out = df_out.sort_values("datetime_utc").reset_index(drop=True)
    return df_out


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

    st.markdown("**Data sourcing**")
    st.caption(
        "By default, training uses only the existing IV cache on disk and will not download new data. "
        "Enable the option below only if you explicitly want to fetch missing days/sites."
    )
    allow_downloads = st.checkbox(
        "Allow downloads for missing cache (may fetch many stations)",
        value=False,
        help="If disabled, only stations already present under iv_cache/ will be trained.",
    )

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

    # Station selection:
    # - default: only stations that already have IV cache
    # - optional: fall back to the stations CSV universe (may trigger downloads)
    if allow_downloads:
        mids = _load_all_monitoring_ids()
        if not mids:
            st.error("Stations CSV not found or empty. Refresh stations in Explorer first.")
            return
        sites = [_site_from_monitoring_location_id(mid) for mid in mids]
    else:
        sites = _load_cached_sites(out_root="iv_cache")
        if not sites:
            st.error("No cached stations found under iv_cache/. Use Explorer first to cache at least one station.")
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

    total = len(sites) * max(1, len(params))
    prog = st.progress(0)
    log = st.empty()

    done = 0
    ridge_trained = 0
    chronos_trained = 0
    skipped = 0
    errors = 0

    for site in sites:
        for pcode in params:
            done += 1
            try:
                if allow_downloads:
                    # Import locally to avoid accidentally pulling requests into paths that don't need it.
                    from core.cache.get_station_timeseries import ensure_iv_window

                    df = ensure_iv_window(site=site, parameter_code=pcode, days=int(days))
                else:
                    df = _read_iv_window_cached(site=site, parameter_code=pcode, days=int(days), out_root="iv_cache")
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
                log.warning(f"Error training for USGS-{site} / {pcode}: {e}")

            prog.progress(min(1.0, done / max(1, total)))

    st.success(
        "Done.\n\n"
        f"- Ridge trained: {ridge_trained}\n"
        f"- Chronos optimized: {chronos_trained}\n"
        f"- Skipped: {skipped}\n"
        f"- Errors: {errors}\n"
        f"- Total combos scanned: {total}"
    )
