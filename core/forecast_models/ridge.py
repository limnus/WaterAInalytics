# core/forecast_models/ridge.py
from __future__ import annotations

from datetime import datetime, timezone
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
    out = out[~out["Value"].isin(_SENTINELS)]
    if out.empty:
        raise ValueError("history has no usable rows after cleaning")
    return out.reset_index(drop=True)


def _is_all_int(series: pd.Series) -> bool:
    s = pd.to_numeric(series, errors="coerce")
    s = s.dropna()
    if s.empty:
        return False
    return bool(np.all(np.isclose(s.values, np.round(s.values))))


def _is_all_nonneg(series: pd.Series) -> bool:
    s = pd.to_numeric(series, errors="coerce")
    s = s.dropna()
    if s.empty:
        return False
    return bool(np.all(s.values >= 0.0))


def _build_features(values: np.ndarray, *, lags: List[int], roll_means: List[int]) -> np.ndarray:
    feats: List[float] = []
    # lags
    for k in lags:
        if len(values) - k < 0:
            feats.append(np.nan)
        else:
            feats.append(float(values[-k]))
    # rolling means
    for w in roll_means:
        if len(values) - w < 0:
            feats.append(np.nan)
        else:
            feats.append(float(np.mean(values[-w:])))
    return np.asarray(feats, dtype=float)


def _build_supervised_matrix(series: pd.Series, *, lags: List[int], roll_means: List[int]) -> Tuple[np.ndarray, np.ndarray]:
    vals = series.astype(float).values
    max_back = max(max(lags) if lags else 0, max(roll_means) if roll_means else 0)
    X_rows: List[np.ndarray] = []
    y_rows: List[float] = []
    for t in range(max_back, len(vals)):
        x = _build_features(vals[:t], lags=lags, roll_means=roll_means)
        if np.any(~np.isfinite(x)):
            continue
        X_rows.append(x)
        y_rows.append(float(vals[t]))
    if not X_rows:
        raise ValueError("Not enough data to build supervised matrix for Ridge.")
    return np.vstack(X_rows), np.asarray(y_rows, dtype=float)


def _standardize_fit(X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    mu = np.mean(X, axis=0)
    sd = np.std(X, axis=0)
    sd = np.where(sd == 0.0, 1.0, sd)
    Xs = (X - mu) / sd
    return Xs, mu, sd


def _standardize_apply(X: np.ndarray, mu: np.ndarray, sd: np.ndarray) -> np.ndarray:
    sd = np.where(sd == 0.0, 1.0, sd)
    return (X - mu) / sd


def _ridge_fit_closed_form(X: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    # Solve (X^T X + alpha I) w = X^T y
    n_features = X.shape[1]
    A = X.T @ X + float(alpha) * np.eye(n_features)
    b = X.T @ y
    w = np.linalg.solve(A, b)
    return w


def _ridge_predict(X: np.ndarray, w: np.ndarray) -> np.ndarray:
    return X @ w


def _compute_sigma_rmse(resid: np.ndarray) -> Tuple[float, float]:
    rmse = float(np.sqrt(np.mean(resid**2)))
    sigma = float(np.std(resid, ddof=1)) if resid.size >= 2 else 0.0
    return sigma, rmse


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
        y_mean = float(artifacts.get("_y_mean", 0.0))
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
                yhat = float(_ridge_predict(xs, w)[0] + y_mean)
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

    # --- Minimal "intercept" fix: center y and store y_mean as artifact ---
    y_mean = float(np.mean(y_train))
    y_train_c = y_train - y_mean
    y_valid_c = y_valid - y_mean

    w = _ridge_fit_closed_form(Xs_train, y_train_c, float(alpha))

    resid_valid = y_valid_c - _ridge_predict(Xs_valid, w)
    resid_train = y_train_c - _ridge_predict(Xs_train, w)

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
        "_y_mean": float(y_mean),
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
        rmse_by_alpha[str(a)] = rmse
        if np.isfinite(rmse) and rmse < best_rmse:
            best_rmse = rmse
            best_artifacts = art

    if best_artifacts is None:
        best_artifacts = train_ridge_from_history(
            history_df,
            alpha=float(alphas[0]),
            lags=lags,
            roll_means=roll_means,
            valid_frac=valid_frac,
            min_valid=min_valid,
        )
        best_rmse = float(best_artifacts.get("rmse_valid", float("nan")))

    best_artifacts = dict(best_artifacts)
    best_artifacts["rmse_by_alpha"] = rmse_by_alpha
    best_artifacts["best_alpha"] = float(best_artifacts.get("alpha", float(alphas[0])))
    best_artifacts["best_rmse_valid"] = float(best_rmse)
    return best_artifacts


def build_ridge_training_manifest(
    *,
    artifacts: Dict[str, Any],
    station_id: str | None = None,
    parameter: str | None = None,
    model_key: str = "ridge",
    artifacts_dir: Path | None = None,
    trained_at_utc: str | None = None,
    generated_by: str = "core.ui.admin_models",
) -> Dict[str, Any]:
    files = ["meta.json", "weights.npz", "training_manifest.json"]
    manifest: Dict[str, Any] = {
        "schema_version": "ridge_training_manifest_v1",
        "trained_at_utc": trained_at_utc or datetime.now(timezone.utc).isoformat(),
        "station_id": station_id,
        "parameter": str(parameter) if parameter is not None else None,
        "model_key": model_key,
        "generated_by": generated_by,
        "artifacts_dir": str(artifacts_dir) if artifacts_dir is not None else None,
        "alpha": float(artifacts.get("alpha", float("nan"))),
        "best_alpha": float(artifacts.get("best_alpha", artifacts.get("alpha", float("nan")))),
        "rmse_valid": float(artifacts.get("rmse_valid", float("nan"))),
        "best_rmse_valid": float(artifacts.get("best_rmse_valid", artifacts.get("rmse_valid", float("nan")))),
        "n_rows": int(artifacts.get("n_rows", 0)),
        "n_supervised": int(artifacts.get("n_supervised", 0)),
        "n_train": int(artifacts.get("n_train", 0)),
        "n_valid": int(artifacts.get("n_valid", 0)),
        "lags": list(artifacts.get("lags", [])),
        "roll_means": list(artifacts.get("roll_means", [])),
        "all_int": bool(artifacts.get("all_int", False)),
        "all_nonneg": bool(artifacts.get("all_nonneg", False)),
        "sigma_residual": float(artifacts.get("sigma_residual", 0.0)),
        "rmse_by_alpha": dict(artifacts.get("rmse_by_alpha", {})),
        "files_generated": files,
    }
    return manifest


def save_ridge_artifacts(
    artifacts_dir: Path,
    artifacts: Dict[str, Any],
    *,
    station_id: str | None = None,
    parameter: str | None = None,
    model_key: str = "ridge",
    trained_at_utc: str | None = None,
    generated_by: str = "core.ui.admin_models",
) -> None:
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    import json

    meta = dict(artifacts)
    w = meta.pop("_w")
    mu = meta.pop("_mu")
    sd = meta.pop("_sd")

    meta_json = json.dumps(meta, indent=2, sort_keys=True)
    (artifacts_dir / "meta.json").write_text(meta_json, encoding="utf-8")

    np.savez_compressed(
        artifacts_dir / "weights.npz",
        w=w,
        mu=mu,
        sd=sd,
    )

    manifest = build_ridge_training_manifest(
        artifacts=artifacts,
        station_id=station_id,
        parameter=parameter,
        model_key=model_key,
        artifacts_dir=artifacts_dir,
        trained_at_utc=trained_at_utc,
        generated_by=generated_by,
    )
    (artifacts_dir / "training_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    