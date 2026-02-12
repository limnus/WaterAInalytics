# core/forecast_models/ridge.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from .base import ForecastOutput, ForecastRequest

_SENTINELS = {999999, -999999, 1e20, -1e20}


def _ensure_datetime_value(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        raise ValueError("history is empty")
    if "Datetime" not in df.columns or "Value" not in df.columns:
        raise ValueError("history must contain columns: 'Datetime', 'Value'")

    out = df.copy()
    out["Datetime"] = pd.to_datetime(out["Datetime"], utc=True, errors="coerce")
    out["Value"] = pd.to_numeric(out["Value"], errors="coerce")
    out = out.dropna(subset=["Datetime", "Value"]).sort_values("Datetime")

    if out.empty:
        raise ValueError("history has no valid Datetime/Value rows after cleaning")

    out = out[~out["Value"].isin(list(_SENTINELS))]
    out = out[(out["Value"] > -1e12) & (out["Value"] < 1e12)]

    if out.empty:
        raise ValueError("history is empty after removing sentinel/outlier values")
    return out


def _is_all_int(series: pd.Series) -> bool:
    v = series.dropna().astype(float).values
    return v.size > 0 and np.all(np.isclose(v, np.round(v)))


def _is_all_nonneg(series: pd.Series) -> bool:
    v = series.dropna().astype(float).values
    return v.size > 0 and np.all(v >= 0)


def _build_features(values: np.ndarray, *, lags: List[int], roll_means: List[int]) -> np.ndarray:
    feats: List[float] = []
    n = len(values)
    for lag in lags:
        feats.append(float(values[n - lag]) if n - lag >= 0 else float("nan"))
    for w in roll_means:
        if n - w >= 0:
            feats.append(float(np.mean(values[n - w : n])))
        else:
            feats.append(float("nan"))
    return np.asarray(feats, dtype=float)


def _build_supervised_matrix(
    series: pd.Series, *, lags: List[int], roll_means: List[int]
) -> Tuple[np.ndarray, np.ndarray]:
    y = series.astype(float).values
    max_lookback = max(max(lags, default=1), max(roll_means, default=1))

    rows_x: List[np.ndarray] = []
    rows_y: List[float] = []

    for t in range(max_lookback, len(y)):
        hist = y[:t]
        x_t = _build_features(hist, lags=lags, roll_means=roll_means)
        if np.any(~np.isfinite(x_t)):
            continue
        rows_x.append(x_t)
        rows_y.append(float(y[t]))

    if not rows_x:
        raise ValueError("Not enough data to build Ridge supervised dataset (after lookback).")

    X = np.vstack(rows_x)
    Y = np.asarray(rows_y, dtype=float)
    return X, Y


def _standardize_fit(X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd = np.where(sd == 0, 1.0, sd)
    Xs = (X - mu) / sd
    return Xs, mu, sd


def _standardize_apply(X: np.ndarray, mu: np.ndarray, sd: np.ndarray) -> np.ndarray:
    return (X - mu) / sd


def _ridge_fit_closed_form(X: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    n_features = X.shape[1]
    A = X.T @ X + alpha * np.eye(n_features)
    b = X.T @ y
    w = np.linalg.solve(A, b)
    return w


def _ridge_predict(X: np.ndarray, w: np.ndarray) -> np.ndarray:
    return X @ w


@dataclass
class RidgeModel:
    model_key: str = "ridge"

    def load_artifacts(self, artifacts_dir: Path, station_id: str, parameter: str) -> Dict[str, Any]:
        meta_path = artifacts_dir / "meta.json"
        weights_path = artifacts_dir / "weights.npz"
        if not meta_path.exists() or not weights_path.exists():
            raise FileNotFoundError(f"Missing Ridge artifacts in {artifacts_dir}")

        import json

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        npz = np.load(weights_path)
        meta["_w"] = npz["w"]
        meta["_mu"] = npz["mu"]
        meta["_sd"] = npz["sd"]
        return meta

    def predict(self, req: ForecastRequest, artifacts: Dict[str, Any]) -> ForecastOutput:
        df = _ensure_datetime_value(req.history)
        series = df["Value"]

        lags = list(artifacts.get("lags", [1, 2, 3, 6, 12, 24]))
        roll_means = list(artifacts.get("roll_means", [3, 6, 12, 24]))
        alpha = float(artifacts.get("alpha", 1.0))

        w = artifacts.get("_w")
        mu = artifacts.get("_mu")
        sd = artifacts.get("_sd")
        if w is None or mu is None or sd is None:
            raise ValueError("Ridge artifacts missing weights/scaler arrays.")

        last_dt = pd.to_datetime(df["Datetime"].iloc[-1], utc=True)
        future_idx = pd.date_range(
            last_dt + pd.Timedelta(hours=1), periods=req.horizon, freq=req.freq, tz="UTC"
        )

        values = series.astype(float).values.copy()
        preds: List[float] = []
        for _ in range(req.horizon):
            x = _build_features(values, lags=lags, roll_means=roll_means)
            if np.any(~np.isfinite(x)):
                yhat = float(values[-1])  # fallback persistence
            else:
                xs = _standardize_apply(x[None, :], mu, sd)
                yhat = float(_ridge_predict(xs, w)[0])
            preds.append(yhat)
            values = np.append(values, yhat)

        y_pred = pd.Series(preds, index=future_idx, name="y_pred")

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
                "alpha": alpha,
                "lags": lags,
                "roll_means": roll_means,
                "all_int": all_int,
                "all_nonneg": all_pos,
            },
        )


def _compute_sigma_rmse(resid: np.ndarray) -> tuple[float, float]:
    resid = np.asarray(resid, dtype=float)
    if resid.size >= 2:
        sigma = float(np.std(resid, ddof=1))
    else:
        sigma = float(np.std(resid))
    rmse = float(np.sqrt(np.mean(resid**2))) if resid.size else float("nan")
    return max(0.0, sigma), rmse


def train_ridge_from_history(
    history_df: pd.DataFrame,
    *,
    alpha: float = 1.0,
    lags: List[int] | None = None,
    roll_means: List[int] | None = None,
    valid_frac: float = 0.2,
    min_valid: int = 24,
) -> Dict[str, Any]:
    df = _ensure_datetime_value(history_df)
    series = df["Value"].astype(float)

    lags = lags or [1, 2, 3, 6, 12, 24]
    roll_means = roll_means or [3, 6, 12, 24]

    X, y = _build_supervised_matrix(series, lags=lags, roll_means=roll_means)
    n = len(y)

    n_valid = max(int(round(n * float(valid_frac))), int(min_valid))
    n_valid = min(n_valid, max(1, n - 1))
    n_train = max(1, n - n_valid)

    X_train, y_train = X[:n_train], y[:n_train]
    X_valid, y_valid = X[n_train:], y[n_train:]

    Xs_train, mu, sd = _standardize_fit(X_train)
    Xs_valid = _standardize_apply(X_valid, mu, sd)

    w = _ridge_fit_closed_form(Xs_train, y_train, float(alpha))

    resid_valid = y_valid - _ridge_predict(Xs_valid, w)
    resid_train = y_train - _ridge_predict(Xs_train, w)

    if resid_valid.size >= 2:
        sigma, rmse = _compute_sigma_rmse(resid_valid)
    elif resid_train.size >= 2:
        sigma, rmse = _compute_sigma_rmse(resid_train)
    else:
        sigma, rmse = 0.0, float("nan")

    all_int = _is_all_int(series)
    all_nonneg = _is_all_nonneg(series)

    return {
        "alpha": float(alpha),
        "lags": list(lags),
        "roll_means": list(roll_means),
        "sigma_residual": float(sigma),
        "rmse_valid": float(rmse),
        "n_rows": int(len(df)),
        "n_supervised": int(n),
        "n_train": int(n_train),
        "n_valid": int(n_valid),
        "all_int": bool(all_int),
        "all_nonneg": bool(all_nonneg),
        "_w": w,
        "_mu": mu,
        "_sd": sd,
    }


def tune_ridge_alpha(
    history_df: pd.DataFrame,
    *,
    alphas: List[float],
    lags: List[int] | None = None,
    roll_means: List[int] | None = None,
    valid_frac: float = 0.2,
    min_valid: int = 24,
) -> Dict[str, Any]:
    if not alphas:
        raise ValueError("alphas grid is empty")

    rmse_by_alpha: Dict[str, float] = {}
    best_artifacts: Dict[str, Any] | None = None
    best_rmse = float("inf")

    for a in alphas:
        art = train_ridge_from_history(
            history_df,
            alpha=float(a),
            lags=lags,
            roll_means=roll_means,
            valid_frac=valid_frac,
            min_valid=min_valid,
        )
        rmse = float(art.get("rmse_valid", float("inf")))
        rmse_by_alpha[f"{float(a):g}"] = rmse
        if np.isfinite(rmse) and rmse < best_rmse:
            best_rmse = rmse
            best_artifacts = art

    if best_artifacts is None:
        best_artifacts = train_ridge_from_history(history_df, alpha=float(alphas[0]), lags=lags, roll_means=roll_means)

    best_artifacts["alpha_grid"] = [float(a) for a in alphas]
    best_artifacts["rmse_by_alpha"] = rmse_by_alpha
    best_artifacts["best_alpha"] = float(best_artifacts["alpha"])
    return best_artifacts


def save_ridge_artifacts(artifacts_dir: Path, artifacts: Dict[str, Any]) -> None:
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    import json

    meta = {k: v for k, v in artifacts.items() if not str(k).startswith("_")}
    (artifacts_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    np.savez_compressed(
        artifacts_dir / "weights.npz",
        w=np.asarray(artifacts["_w"], dtype=float),
        mu=np.asarray(artifacts["_mu"], dtype=float),
        sd=np.asarray(artifacts["_sd"], dtype=float),
    )
