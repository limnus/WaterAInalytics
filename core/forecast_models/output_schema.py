from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from .base import ForecastOutput

FORECAST_TABLE_SCHEMA_VERSION = "forecast_table_v1"
FORECAST_RUN_SCHEMA_VERSION = "forecast_run_v1"


@dataclass(frozen=True)
class StationForecastBundle:
    station_id: str
    parameter: str
    requested_model_key: str
    requested_model_label: str
    used_model_key: str
    used_model_label: str
    forecast_output: ForecastOutput
    history_df: pd.DataFrame
    pi_low: Optional[pd.Series] = None
    pi_high: Optional[pd.Series] = None


def _iso_utc(ts: Any) -> str:
    dt = pd.Timestamp(ts)
    if dt.tzinfo is None:
        dt = dt.tz_localize("UTC")
    else:
        dt = dt.tz_convert("UTC")
    return dt.isoformat()


def _to_float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    if not np.isfinite(out):
        return None
    return out


def normalize_history_frame(history_df: pd.DataFrame) -> pd.DataFrame:
    if history_df is None or history_df.empty:
        raise ValueError("history_df is empty")
    if "Datetime" not in history_df.columns or "Value" not in history_df.columns:
        raise ValueError("history_df must contain 'Datetime' and 'Value' columns")

    out = history_df[["Datetime", "Value"]].copy()
    out["Datetime"] = pd.to_datetime(out["Datetime"], utc=True, errors="coerce")
    out["Value"] = pd.to_numeric(out["Value"], errors="coerce")
    out = out.dropna(subset=["Datetime", "Value"]).sort_values("Datetime").reset_index(drop=True)
    if out.empty:
        raise ValueError("history_df has no usable rows after normalization")
    return out


def forecast_output_to_rows(
    *,
    bundle: StationForecastBundle,
    horizon_h: int,
    interval_label: str,
    pi_method_label: str,
) -> List[Dict[str, Any]]:
    out = bundle.forecast_output
    rows: List[Dict[str, Any]] = []

    for i, ts in enumerate(out.y_pred.index, start=1):
        row: Dict[str, Any] = {
            "schema_version": FORECAST_TABLE_SCHEMA_VERSION,
            "station_id": bundle.station_id,
            "parameter": bundle.parameter,
            "requested_model_key": bundle.requested_model_key,
            "requested_model_label": bundle.requested_model_label,
            "used_model_key": bundle.used_model_key,
            "used_model_label": bundle.used_model_label,
            "horizon_h": int(horizon_h),
            "horizon_step": int(i),
            "interval": interval_label,
            "pi_method": pi_method_label,
            "timestamp_utc": _iso_utc(ts),
            "y_hat": float(out.y_pred.loc[ts]),
            "sigma_residual": _to_float_or_none(out.sigma_residual),
            "pi_low": None,
            "pi_high": None,
        }

        if bundle.pi_low is not None and ts in bundle.pi_low.index:
            row["pi_low"] = _to_float_or_none(bundle.pi_low.loc[ts])
        if bundle.pi_high is not None and ts in bundle.pi_high.index:
            row["pi_high"] = _to_float_or_none(bundle.pi_high.loc[ts])
        rows.append(row)

    return rows


def rows_to_frame(rows: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(list(rows))
    if df.empty:
        return df
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True, errors="coerce")
    sort_cols = [c for c in ["station_id", "timestamp_utc", "horizon_step"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)
    return df




def _normalize_manifest_dict(training_manifest: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(training_manifest, dict):
        return {}
    return dict(training_manifest)


def summarize_station_forecast(
    station_payload: Dict[str, Any],
    *,
    article_preset_key: Optional[str] = None,
    article_preset_name: Optional[str] = None,
    training_manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    hist = dict(station_payload.get("history") or {})
    forecast_rows = list(station_payload.get("forecast") or [])
    meta = dict(station_payload.get("meta") or {})
    manifest = _normalize_manifest_dict(training_manifest)

    first_row = forecast_rows[0] if forecast_rows else {}
    last_row = forecast_rows[-1] if forecast_rows else {}

    return {
        "article_preset_key": article_preset_key,
        "article_preset_name": article_preset_name,
        "station_id": station_payload.get("station_id"),
        "parameter": station_payload.get("parameter"),
        "requested_model_key": station_payload.get("requested_model_key"),
        "requested_model_label": station_payload.get("requested_model_label"),
        "used_model_key": station_payload.get("used_model_key"),
        "used_model_label": station_payload.get("used_model_label"),
        "history_n_rows": hist.get("n_rows"),
        "history_start_utc": hist.get("start_utc"),
        "history_end_utc": hist.get("end_utc"),
        "history_last_value": hist.get("last_value"),
        "sigma_residual": station_payload.get("sigma_residual"),
        "alpha": meta.get("alpha"),
        "forecast_start_utc": first_row.get("timestamp_utc"),
        "forecast_end_utc": last_row.get("timestamp_utc"),
        "forecast_first_y_hat": first_row.get("y_hat"),
        "forecast_last_y_hat": last_row.get("y_hat"),
        "trained_at_utc": manifest.get("trained_at_utc"),
        "n_train": manifest.get("n_train"),
        "n_valid": manifest.get("n_valid"),
        "rmse_valid": manifest.get("rmse_valid"),
        "best_alpha": manifest.get("best_alpha", meta.get("alpha")),
        "best_rmse_valid": manifest.get("best_rmse_valid", manifest.get("rmse_valid")),
        "rmse_by_alpha": manifest.get("rmse_by_alpha"),
        "training_manifest_path": manifest.get("_path"),
    }


def build_experiment_summary_artifact(
    forecast_run_artifact: Dict[str, Any],
    *,
    training_manifests: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    run = dict(forecast_run_artifact or {})
    article_preset_key = run.get("article_preset_key")
    article_preset_name = run.get("article_preset_name")

    station_rows: List[Dict[str, Any]] = []
    for station_payload in list(run.get("stations") or []):
        station_id = station_payload.get("station_id")
        parameter = station_payload.get("parameter")
        used_model_key = station_payload.get("used_model_key")
        manifest_key = f"{used_model_key}|{station_id}|{parameter}"
        manifest = (training_manifests or {}).get(manifest_key)
        station_rows.append(
            summarize_station_forecast(
                station_payload,
                article_preset_key=article_preset_key,
                article_preset_name=article_preset_name,
                training_manifest=manifest,
            )
        )

    return {
        "schema_version": "experiment_summary_v1",
        "created_at_utc": run.get("created_at_utc"),
        "article_mode": bool(run.get("article_mode", False)),
        "article_preset_key": article_preset_key,
        "article_preset_name": article_preset_name,
        "parameter": run.get("parameter"),
        "requested_model_key": run.get("requested_model_key"),
        "requested_model_label": run.get("requested_model_label"),
        "requested_horizon_h": run.get("requested_horizon_h"),
        "interval": run.get("interval"),
        "pi_method": run.get("pi_method"),
        "station_count": int(run.get("station_count") or len(station_rows)),
        "stations": station_rows,
    }


def experiment_summary_to_frame(summary_artifact: Dict[str, Any]) -> pd.DataFrame:
    rows = list((summary_artifact or {}).get("stations") or [])
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    sort_cols = [c for c in ["article_preset_key", "station_id"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)
    return df

def build_forecast_run_artifact(
    *,
    station_bundles: List[StationForecastBundle],
    requested_model_key: str,
    requested_model_label: str,
    parameter: str,
    horizon_h: int,
    interval_label: str,
    pi_method_label: str,
    session_seed: Optional[int],
    created_at_utc: Optional[str] = None,
) -> Dict[str, Any]:
    created = created_at_utc or datetime.now(timezone.utc).isoformat()

    stations_payload: List[Dict[str, Any]] = []
    for bundle in station_bundles:
        hist = normalize_history_frame(bundle.history_df)
        rows = forecast_output_to_rows(
            bundle=bundle,
            horizon_h=horizon_h,
            interval_label=interval_label,
            pi_method_label=pi_method_label,
        )

        stations_payload.append(
            {
                "station_id": bundle.station_id,
                "parameter": bundle.parameter,
                "requested_model_key": bundle.requested_model_key,
                "requested_model_label": bundle.requested_model_label,
                "used_model_key": bundle.used_model_key,
                "used_model_label": bundle.used_model_label,
                "sigma_residual": _to_float_or_none(bundle.forecast_output.sigma_residual),
                "history": {
                    "n_rows": int(len(hist)),
                    "start_utc": _iso_utc(hist["Datetime"].iloc[0]),
                    "end_utc": _iso_utc(hist["Datetime"].iloc[-1]),
                    "last_value": float(hist["Value"].iloc[-1]),
                },
                "forecast": rows,
                "meta": dict(bundle.forecast_output.meta or {}),
            }
        )

    return {
        "schema_version": FORECAST_RUN_SCHEMA_VERSION,
        "created_at_utc": created,
        "parameter": str(parameter),
        "requested_model_key": requested_model_key,
        "requested_model_label": requested_model_label,
        "requested_horizon_h": int(horizon_h),
        "interval": interval_label,
        "pi_method": pi_method_label,
        "session_seed": int(session_seed) if session_seed is not None else None,
        "station_count": int(len(station_bundles)),
        "stations": stations_payload,
    }
