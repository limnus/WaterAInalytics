from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd


def rmse(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    yt = np.asarray(list(y_true), dtype=float)
    yp = np.asarray(list(y_pred), dtype=float)
    if yt.size == 0 or yp.size == 0 or yt.size != yp.size:
        return float("nan")
    return float(math.sqrt(np.mean((yt - yp) ** 2)))


def mae(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    yt = np.asarray(list(y_true), dtype=float)
    yp = np.asarray(list(y_pred), dtype=float)
    if yt.size == 0 or yp.size == 0 or yt.size != yp.size:
        return float("nan")
    return float(np.mean(np.abs(yt - yp)))


def skill_vs_baseline(model_rmse: float, baseline_rmse: float) -> float | None:
    try:
        br = float(baseline_rmse)
        mr = float(model_rmse)
    except Exception:
        return None
    if not np.isfinite(br) or br == 0.0 or not np.isfinite(mr):
        return None
    return float(1.0 - (mr / br))


def select_best_median_worst(origin_metrics_df: pd.DataFrame) -> pd.DataFrame:
    if origin_metrics_df.empty:
        return origin_metrics_df.copy()
    work = origin_metrics_df.copy().sort_values("difficulty_score").reset_index(drop=True)
    idx_best = 0
    idx_worst = len(work) - 1
    idx_median = len(work) // 2
    selected = pd.concat([
        work.iloc[[idx_best]].assign(selection_role="best"),
        work.iloc[[idx_median]].assign(selection_role="median"),
        work.iloc[[idx_worst]].assign(selection_role="worst"),
    ], ignore_index=True)
    selected = selected.drop_duplicates(subset=["origin_utc", "selection_role"], keep="first")
    return selected.reset_index(drop=True)
