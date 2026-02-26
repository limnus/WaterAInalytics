# core/forecast_models/chronos.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .base import ForecastOutput, ForecastRequest
from .ridge import _ensure_datetime_value, _is_all_int, _is_all_nonneg


def _require_chronos():
    try:
        import torch  # noqa: F401
        # IMPORTANT:
        # Use BaseChronosPipeline so Bolt models load with the correct pipeline/config.
        from chronos import BaseChronosPipeline  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Chronos dependencies are not installed or Chronos import failed. "
            "Install torch + chronos-forecasting (+ transformers).\n"
            "Suggested: pip install git+https://github.com/amazon-science/chronos-forecasting.git"
        ) from e
    return BaseChronosPipeline


_PIPELINE_CACHE: Dict[tuple[str, str], Any] = {}


def _get_device(prefer: Optional[str] = None) -> str:
    try:
        import torch
        if prefer in ("cpu", "cuda"):
            return prefer
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _get_pipeline(model_id: str, device: str) -> Any:
    key = (model_id, device)
    if key in _PIPELINE_CACHE:
        return _PIPELINE_CACHE[key]

    BaseChronosPipeline = _require_chronos()
    pipe = BaseChronosPipeline.from_pretrained(model_id, device_map=device, torch_dtype="auto")
    _PIPELINE_CACHE[key] = pipe
    return pipe


def _pipe_predict(pipe: Any, ctx_t: Any, prediction_length: int, num_samples: int) -> Any:
    """
    Compatibility wrapper for Chronos pipelines.
    - Some Bolt builds don't accept num_samples.
    - Some builds have positional-only context (and sometimes prediction_length).
    """
    # Attempt 1: common API (non-bolt)
    try:
        return pipe.predict(ctx_t, prediction_length=int(prediction_length), num_samples=int(num_samples))
    except TypeError as e:
        msg = str(e)
        if "num_samples" in msg:
            pass
        else:
            raise

    # Attempt 2: no num_samples (Bolt)
    try:
        return pipe.predict(ctx_t, prediction_length=int(prediction_length))
    except TypeError as e:
        msg = str(e)
        # Some variants may not accept prediction_length as keyword
        if "prediction_length" in msg or "unexpected keyword argument" in msg:
            return pipe.predict(ctx_t, int(prediction_length))
        raise


@dataclass
class ChronosModel:
    model_key: str = "chronos"
    model_id: str = "amazon/chronos-bolt-tiny"

    def load_artifacts(self, artifacts_dir: Path, station_id: str, parameter: str) -> Dict[str, Any]:
        meta_path = artifacts_dir / "meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"Missing Chronos artifacts in {artifacts_dir}")
        import json
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def predict(self, req: ForecastRequest, artifacts: Dict[str, Any]) -> ForecastOutput:
        import torch

        df = _ensure_datetime_value(req.history)
        series = df["Value"].astype(float)

        model_id = str(artifacts.get("model_id", self.model_id))
        context_hours = int(artifacts.get("best_context_hours", 24 * 14))
        context_hours = max(1, min(context_hours, 24 * 14))  # <= 14 days

        values = series.values
        ctx = values[-min(len(values), context_hours):].astype(np.float32)
        ctx_t = torch.tensor(ctx)

        device = _get_device(artifacts.get("device"))
        pipe = _get_pipeline(model_id, device=device)

        num_samples = int(artifacts.get("num_samples", 20))
        num_samples = max(10, min(num_samples, 200))

        last_dt = pd.to_datetime(df["Datetime"].iloc[-1], utc=True)
        future_idx = pd.date_range(
            last_dt + pd.Timedelta(hours=1), periods=int(req.horizon), freq=req.freq, tz="UTC"
        )

        fc = _pipe_predict(pipe, ctx_t, int(req.horizon), num_samples)

        try:
            fc_np = fc.detach().cpu().numpy()
        except Exception:
            fc_np = np.asarray(fc)

        # For Bolt: [num_series, num_quantiles, prediction_length]
        # For non-bolt: often [num_samples, prediction_length]
        # Take a robust median across the "sample/quantile" dimension(s).
        if fc_np.ndim == 3:
            yhat = np.median(fc_np, axis=1)[0]
        elif fc_np.ndim == 2:
            yhat = np.median(fc_np, axis=0)
        else:
            yhat = fc_np.reshape(-1)

        yhat = np.asarray(yhat, dtype=float)
        y_pred = pd.Series(yhat, index=future_idx, name="y_pred")

        all_int = bool(artifacts.get("all_int", _is_all_int(series)))
        all_pos = bool(artifacts.get("all_nonneg", _is_all_nonneg(series)))
        if all_pos:
            y_pred = y_pred.clip(lower=0.0)
        if all_int:
            y_pred = y_pred.round().astype(int)

        sigma = float(artifacts.get("sigma_residual", 0.0))
        sigma = max(0.0, sigma)
        if sigma == 0.0:
            last_val = float(series.iloc[-1])
            sigma = max(0.01, 0.01 * abs(last_val))

        return ForecastOutput(
            station_id=req.station_id,
            parameter=req.parameter,
            model_key=self.model_key,
            y_pred=y_pred,
            sigma_residual=float(sigma),
            meta={
                "model_id": model_id,
                "best_context_hours": context_hours,
                "num_samples": num_samples,
                "device": device,
                "all_int": all_int,
                "all_nonneg": all_pos,
            },
        )


def _rmse(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean((a - b) ** 2)))


def optimize_chronos_context(
    history_df: pd.DataFrame,
    *,
    model_id: str,
    candidates_hours: Optional[List[int]] = None,
    eval_points: int = 168,
    device: Optional[str] = None,
    num_samples: int = 20,
) -> Dict[str, Any]:
    import torch

    df = _ensure_datetime_value(history_df)
    y = df["Value"].astype(float).values

    if len(y) < 30:
        raise ValueError("Not enough data to optimize Chronos context (need >= 30 points).")

    candidates_hours = candidates_hours or [24, 48, 72, 168, 336]
    candidates_hours = [int(h) for h in candidates_hours if 1 <= int(h) <= 336]
    if not candidates_hours:
        candidates_hours = [336]

    device = _get_device(device)
    pipe = _get_pipeline(str(model_id), device=device)

    eval_points = int(eval_points)
    eval_points = max(24, min(eval_points, len(y) - 2))
    start_t = max(1, len(y) - eval_points)

    best_ctx: Optional[int] = None
    best_rmse = float("inf")
    best_resid: Optional[np.ndarray] = None

    num_samples = max(10, min(int(num_samples), 200))

    for ctx_h in candidates_hours:
        preds: List[float] = []
        trues: List[float] = []
        for k in range(start_t, len(y)):
            ctx = y[max(0, k - ctx_h):k].astype(np.float32)
            if ctx.size < 2:
                continue

            ctx_t = torch.tensor(ctx)
            fc = _pipe_predict(pipe, ctx_t, 1, num_samples)

            try:
                fc_np = fc.detach().cpu().numpy()
            except Exception:
                fc_np = np.asarray(fc)

            if fc_np.ndim == 3:
                yhat = float(np.median(fc_np, axis=1)[0, 0])
            elif fc_np.ndim == 2:
                yhat = float(np.median(fc_np, axis=0)[0])
            else:
                yhat = float(np.asarray(fc_np).reshape(-1)[0])

            preds.append(yhat)
            trues.append(float(y[k]))

        if len(trues) < 5:
            continue

        rmse = _rmse(np.asarray(trues), np.asarray(preds))
        if rmse < best_rmse:
            best_rmse = rmse
            best_ctx = ctx_h
            best_resid = np.asarray(trues) - np.asarray(preds)

    if best_ctx is None:
        best_ctx = max(candidates_hours)
        best_rmse = float("nan")
        best_resid = np.asarray([])

    sigma = float(np.std(best_resid, ddof=1)) if best_resid.size >= 2 else float(np.std(best_resid))
    sigma = max(0.0, sigma)

    series = df["Value"].astype(float)
    all_int = _is_all_int(series)
    all_nonneg = _is_all_nonneg(series)

    return {
        "model_id": str(model_id),
        "best_context_hours": int(best_ctx),
        "candidates_hours": list(candidates_hours),
        "eval_points": int(eval_points),
        "num_samples": int(num_samples),
        "device": str(device),
        "sigma_residual": float(sigma),
        "rmse_valid": float(best_rmse),
        "n_rows": int(len(df)),
        "all_int": bool(all_int),
        "all_nonneg": bool(all_nonneg),
    }


def save_chronos_artifacts(artifacts_dir: Path, artifacts: Dict[str, Any]) -> None:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    import json
    (artifacts_dir / "meta.json").write_text(json.dumps(artifacts, indent=2), encoding="utf-8")