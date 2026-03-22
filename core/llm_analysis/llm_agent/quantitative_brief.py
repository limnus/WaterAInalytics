from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from core.llm_analysis.forecast_integration.models import ForecastContext


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    if not np.isfinite(out):
        return None
    return out


def _fmt_value(value: Optional[float]) -> str:
    if value is None:
        return "NA"
    return f"{value:.3g}"


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "NA"
    return f"{value * 100:.1f}%"


def _trend_label(delta: Optional[float], tolerance: float) -> str:
    if delta is None:
        return "indeterminate"
    if abs(delta) <= tolerance:
        return "roughly stable"
    return "increasing" if delta > 0 else "decreasing"


def _variability_label(cv: Optional[float]) -> str:
    if cv is None:
        return "unresolved"
    if cv < 0.05:
        return "low"
    if cv < 0.15:
        return "moderate"
    return "high"


def _anomaly_label(z_score: Optional[float]) -> Optional[str]:
    if z_score is None:
        return None
    if z_score >= 2.0:
        return "unusually high"
    if z_score <= -2.0:
        return "unusually low"
    return None


def _history_stats(forecast_ctx: ForecastContext) -> Dict[str, Any]:
    y = pd.Series(forecast_ctx.recent_history.y, dtype=float)
    t = pd.to_datetime(forecast_ctx.recent_history.t_utc, utc=True)

    n = int(len(y))
    if n == 0:
        raise ValueError("forecast_ctx.recent_history is empty")

    recent_n = min(24, n)
    trend_n = min(6, n)

    recent = y.tail(recent_n).reset_index(drop=True)
    trend_window = y.tail(trend_n).reset_index(drop=True)
    prev_value = _safe_float(y.iloc[-2]) if n >= 2 else None
    last_value = _safe_float(y.iloc[-1])
    recent_mean = _safe_float(recent.mean())
    recent_std = _safe_float(recent.std(ddof=1)) if recent_n >= 2 else 0.0
    recent_min = _safe_float(recent.min())
    recent_max = _safe_float(recent.max())
    recent_range = None
    if recent_min is not None and recent_max is not None:
        recent_range = recent_max - recent_min

    cv = None
    if recent_mean is not None and abs(recent_mean) > 1e-12 and recent_std is not None:
        cv = abs(recent_std) / abs(recent_mean)

    z_score = None
    if recent_std is not None and recent_std > 1e-12 and last_value is not None and recent_mean is not None:
        z_score = (last_value - recent_mean) / recent_std

    trend_delta = None
    trend_pct = None
    if trend_n >= 2:
        start = _safe_float(trend_window.iloc[0])
        end = _safe_float(trend_window.iloc[-1])
        if start is not None and end is not None:
            trend_delta = end - start
            if abs(start) > 1e-12:
                trend_pct = trend_delta / abs(start)

    tolerance = max(abs(recent_mean or 0.0) * 0.01, abs(recent_std or 0.0) * 0.25, 1e-9)

    return {
        "history_points": n,
        "recent_window_points": recent_n,
        "trend_window_points": trend_n,
        "last_timestamp_utc": pd.Timestamp(t[-1]).isoformat(),
        "last_value": last_value,
        "previous_value": prev_value,
        "recent_mean": recent_mean,
        "recent_std": recent_std,
        "recent_min": recent_min,
        "recent_max": recent_max,
        "recent_range": recent_range,
        "cv": cv,
        "variability_label": _variability_label(cv),
        "z_score": z_score,
        "anomaly_label": _anomaly_label(z_score),
        "trend_delta": trend_delta,
        "trend_pct": trend_pct,
        "trend_label": _trend_label(trend_delta, tolerance),
        "trend_tolerance": tolerance,
    }


def _forecast_stats(forecast_ctx: ForecastContext, history_stats: Dict[str, Any]) -> Dict[str, Any]:
    horizons = forecast_ctx.horizons or []
    if not horizons:
        return {
            "horizon_count": 0,
            "direction_label": "unresolved",
            "has_prediction_interval": False,
        }

    y_hat = [float(h.y_hat) for h in horizons]
    first_pred = y_hat[0]
    last_pred = y_hat[-1]
    min_pred = min(y_hat)
    max_pred = max(y_hat)

    last_obs = history_stats.get("last_value")
    delta_next = None if last_obs is None else first_pred - float(last_obs)
    delta_last = None if last_obs is None else last_pred - float(last_obs)

    recent_mean = history_stats.get("recent_mean")
    scale = max(abs(recent_mean or 0.0) * 0.01, abs(history_stats.get("recent_std") or 0.0) * 0.25, 1e-9)
    direction_label = _trend_label(delta_last, scale)

    widths: List[float] = []
    for h in horizons:
        if h.p05 is None or h.p95 is None:
            continue
        width = float(h.p95) - float(h.p05)
        if np.isfinite(width):
            widths.append(width)

    avg_width = float(np.mean(widths)) if widths else None
    rel_width = None
    if avg_width is not None and first_pred is not None and abs(first_pred) > 1e-12:
        rel_width = avg_width / abs(first_pred)

    if rel_width is None:
        uncertainty_label = "not available"
    elif rel_width < 0.10:
        uncertainty_label = "narrow"
    elif rel_width < 0.25:
        uncertainty_label = "moderate"
    else:
        uncertainty_label = "wide"

    return {
        "horizon_count": len(horizons),
        "first_target_utc": horizons[0].t_target_utc.isoformat(),
        "last_target_utc": horizons[-1].t_target_utc.isoformat(),
        "first_pred": first_pred,
        "last_pred": last_pred,
        "min_pred": min_pred,
        "max_pred": max_pred,
        "delta_next": delta_next,
        "delta_last": delta_last,
        "direction_label": direction_label,
        "has_prediction_interval": bool(widths),
        "avg_pi_width": avg_width,
        "relative_pi_width": rel_width,
        "uncertainty_label": uncertainty_label,
    }


def build_quantitative_forecast_brief(forecast_ctx: ForecastContext) -> Dict[str, Any]:
    hstats = _history_stats(forecast_ctx)
    fstats = _forecast_stats(forecast_ctx, hstats)

    station = forecast_ctx.station_id
    parameter = forecast_ctx.parameter
    last_value = hstats["last_value"]
    recent_mean = hstats["recent_mean"]
    recent_std = hstats["recent_std"]
    next_pred = fstats.get("first_pred")

    executive_summary = (
        f"For station {station} and parameter {parameter}, the latest observed value is {_fmt_value(last_value)}. "
        f"Against the last {hstats['recent_window_points']} observations, the short-term behavior is {hstats['trend_label']} "
        f"with {hstats['variability_label']} variability. "
        f"The forecast over the next {fstats['horizon_count']} step(s) looks {fstats['direction_label']}, "
        f"starting at {_fmt_value(next_pred)}."
    )

    key_findings: List[str] = [
        (
            f"Latest observation = {_fmt_value(last_value)}; recent mean over the last {hstats['recent_window_points']} points = "
            f"{_fmt_value(recent_mean)} and recent standard deviation = {_fmt_value(recent_std)}."
        ),
        (
            f"Short-term history is {hstats['trend_label']} over the last {hstats['trend_window_points']} points "
            f"(net change = {_fmt_value(hstats['trend_delta'])}, relative change = {_fmt_pct(hstats['trend_pct'])})."
        ),
        (
            f"Recent variability is {hstats['variability_label']} (coefficient of variation = {_fmt_pct(hstats['cv'])}); "
            f"observed range in the recent window = {_fmt_value(hstats['recent_range'])}."
        ),
    ]
    if hstats.get("anomaly_label"):
        key_findings.append(
            f"The latest observed point looks {hstats['anomaly_label']} relative to the recent window "
            f"(z-score = {_fmt_value(hstats['z_score'])})."
        )

    forecast_interpretation: List[str] = [
        (
            f"The next predicted value is {_fmt_value(fstats.get('first_pred'))}, which differs from the latest observation by "
            f"{_fmt_value(fstats.get('delta_next'))}."
        ),
        (
            f"Across the forecast horizon, predicted values span from {_fmt_value(fstats.get('min_pred'))} to "
            f"{_fmt_value(fstats.get('max_pred'))}; the end-of-horizon direction is {fstats.get('direction_label')}."
        ),
    ]
    if fstats.get("has_prediction_interval"):
        forecast_interpretation.append(
            f"Prediction interval width is {fstats.get('uncertainty_label')} on average "
            f"(mean PI width = {_fmt_value(fstats.get('avg_pi_width'))}, relative width = {_fmt_pct(fstats.get('relative_pi_width'))})."
        )
    else:
        forecast_interpretation.append(
            "Prediction-interval diagnostics are not available for this forecast artifact, so uncertainty is only partially characterized."
        )

    limitations: List[str] = []
    if hstats["history_points"] < 24:
        limitations.append(
            f"Only {hstats['history_points']} historical point(s) were available, so the recent-window statistics are based on a short sample."
        )
    limitations.append(
        "This quantitative brief is deterministic and data-grounded, but it does not yet incorporate local watershed, geological, meteorological, or land-use context."
    )

    open_questions = [
        "Would adding trustworthy local hydro-meteorological and watershed context materially change the interpretation of the current forecast?"
    ]

    return {
        "station_id": station,
        "parameter": parameter,
        "executive_summary": executive_summary,
        "key_findings": key_findings,
        "forecast_interpretation": forecast_interpretation,
        "limitations": limitations,
        "open_questions": open_questions,
        "history_stats": hstats,
        "forecast_stats": fstats,
    }


def render_quantitative_brief_markdown(brief: Dict[str, Any]) -> str:
    lines: List[str] = []

    summary = (brief.get("executive_summary") or "").strip()
    if summary:
        lines.append("#### Executive Summary")
        lines.append(summary)
        lines.append("")

    for title, key in (
        ("Key Findings", "key_findings"),
        ("Forecast Interpretation", "forecast_interpretation"),
        ("Limitations", "limitations"),
        ("Open Questions", "open_questions"),
    ):
        items = [x for x in (brief.get(key) or []) if isinstance(x, str) and x.strip()]
        if not items:
            continue
        lines.append(f"#### {title}")
        for item in items:
            lines.append(f"- {item.strip()}")
        lines.append("")

    return "\n".join(lines).strip()
