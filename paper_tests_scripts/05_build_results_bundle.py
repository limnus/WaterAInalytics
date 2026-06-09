from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from paper_tests_scripts.paper_common import load_json, save_json
from paper_tests_scripts.paper_plot_style import apply_paper_style, model_colors, heatmap_cmap, figure_size, save_figure


MODEL_ORDER_MAIN = ["persistence", "ridge", "chronos-base"]
MODEL_LABELS = {"persistence": "Persistence", "ridge": "Ridge", "chronos-base": "Chronos-Base", "chronos-mini": "Chronos-Mini", "chronos-tiny": "Chronos-Tiny", "chronos-large": "Chronos-Large"}
GROUP_ORDER = ["core_flow", "core_stage", "supplement_turbidity"]
GROUP_LABELS = {"core_flow": "Discharge", "core_stage": "Stage", "supplement_turbidity": "Water quality"}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Build manuscript-ready tables and modern scientific figures for the WaterAInalytics paper benchmark.")
    ap.add_argument("--config", required=True, help="Path to artifacts/paper_results/<run_tag>/resolved_config.json")
    return ap.parse_args()


def _require_columns(df: pd.DataFrame, cols: Iterable[str], source: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in {source}: {missing}")


def _fmt_number(x: Any) -> str:
    try:
        v = float(x)
    except Exception:
        return ""
    if not np.isfinite(v):
        return ""
    av = abs(v)
    if av >= 1000:
        return f"{v:,.0f}"
    if av >= 100:
        return f"{v:.1f}"
    if av >= 10:
        return f"{v:.2f}"
    if av >= 1:
        return f"{v:.3f}"
    return f"{v:.4f}"


def _ordered_cases(df: pd.DataFrame) -> List[str]:
    tmp = df[["case_key", "group", "label"]].drop_duplicates().copy()
    tmp["group_rank"] = tmp["group"].map({g: i for i, g in enumerate(GROUP_ORDER)}).fillna(99)
    tmp = tmp.sort_values(["group_rank", "label"])
    return tmp["case_key"].astype(str).tolist()


def _case_labels(df: pd.DataFrame, case_order: List[str]) -> List[str]:
    meta = df[["case_key", "label"]].drop_duplicates().set_index("case_key")["label"].to_dict()
    return [str(meta.get(k, k)) for k in case_order]


def _group_boundaries(df: pd.DataFrame, case_order: List[str]) -> List[Tuple[int, str]]:
    meta = df[["case_key", "group"]].drop_duplicates().set_index("case_key")["group"].to_dict()
    out = []
    last_group = None
    for i, ck in enumerate(case_order):
        g = meta.get(ck, "")
        if g != last_group:
            out.append((i, GROUP_LABELS.get(g, g)))
            last_group = g
    return out


def _row_normalize(values: np.ndarray) -> np.ndarray:
    arr = values.astype(float).copy()
    out = np.full_like(arr, np.nan, dtype=float)
    for i in range(arr.shape[0]):
        row = arr[i, :]
        valid = np.isfinite(row)
        if not valid.any():
            continue
        mn = np.nanmin(row)
        mx = np.nanmax(row)
        if np.isclose(mx, mn):
            out[i, valid] = 0.5
        else:
            out[i, valid] = (row[valid] - mn) / (mx - mn)
    return out


def _metric_matrix(df: pd.DataFrame, value_col: str, case_order: List[str], model_order: List[str]) -> np.ndarray:
    piv = df.pivot_table(index="case_key", columns="model_key", values=value_col, aggfunc="first")
    return piv.reindex(index=case_order, columns=model_order).to_numpy(dtype=float)


def _draw_heatmap_panel(ax, raw: np.ndarray, title: str, case_labels: List[str], model_labels: List[str], *, row_normalized: bool = True, cmap=None, diverging: bool = False) -> None:
    data = _row_normalize(raw) if row_normalized else raw
    if diverging:
        vmax = np.nanmax(np.abs(raw)) if np.isfinite(raw).any() else 1
        vmin = -vmax
        shown = raw
    else:
        vmin = 0
        vmax = 1 if row_normalized else (np.nanmax(data) if np.isfinite(data).any() else 1)
        shown = data
    im = ax.imshow(shown, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")
    ax.set_title(title, pad=8, fontweight="semibold")
    ax.set_xticks(range(len(model_labels)))
    ax.set_xticklabels(model_labels, rotation=30, ha="right")
    ax.set_yticks(range(len(case_labels)))
    ax.set_yticklabels(case_labels)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for i in range(raw.shape[0]):
        finite = np.isfinite(raw[i, :])
        best_j = None
        if finite.any():
            best_j = int(np.nanargmin(raw[i, :])) if not diverging else int(np.nanargmax(raw[i, :]))
        for j in range(raw.shape[1]):
            val = raw[i, j]
            if not np.isfinite(val):
                txt = ""
            elif "Skill" in title:
                txt = f"{val:.2f}"
            else:
                txt = _fmt_number(val)
            if txt:
                weight = "bold" if j == best_j else "normal"
                ax.text(j, i, txt, ha="center", va="center", fontsize=7.5, color="#111827", fontweight=weight)
    ax.set_xticks(np.arange(-.5, raw.shape[1], 1), minor=True)
    ax.set_yticks(np.arange(-.5, raw.shape[0], 1), minor=True)
    ax.grid(which="minor", color="#FFFFFF", linestyle="-", linewidth=1.2)
    ax.tick_params(which="minor", bottom=False, left=False)
    return im


def make_figure_2_main_benchmark_heatmaps(resolved: Dict[str, Any], case_metrics: pd.DataFrame) -> Dict[str, str]:
    required = ["case_key", "group", "label", "model_key", "rmse_mean", "mae_mean", "skill_vs_persistence_mean"]
    _require_columns(case_metrics, required, "case_model_metrics.csv")
    case_order = _ordered_cases(case_metrics)
    labels = _case_labels(case_metrics, case_order)
    model_labels = [MODEL_LABELS[m] for m in MODEL_ORDER_MAIN]
    rmse = _metric_matrix(case_metrics, "rmse_mean", case_order, MODEL_ORDER_MAIN)
    mae = _metric_matrix(case_metrics, "mae_mean", case_order, MODEL_ORDER_MAIN)
    skill = _metric_matrix(case_metrics, "skill_vs_persistence_mean", case_order, MODEL_ORDER_MAIN)

    fig, axes = plt.subplots(1, 3, figsize=figure_size("heatmap_main"), sharey=True)
    fig.subplots_adjust(left=0.41, right=0.985, top=0.92, bottom=0.10, wspace=0.18)
    _draw_heatmap_panel(axes[0], rmse, "(a) RMSE", labels, model_labels, row_normalized=True, cmap=heatmap_cmap("rmse"))
    _draw_heatmap_panel(axes[1], mae, "(b) MAE", labels, model_labels, row_normalized=True, cmap=heatmap_cmap("mae"))
    _draw_heatmap_panel(axes[2], skill, "(c) Skill vs Persistence", labels, model_labels, row_normalized=False, cmap=heatmap_cmap("skill"), diverging=True)
    for ax in axes:
        for y, label in _group_boundaries(case_metrics, case_order):
            if y > 0:
                ax.axhline(y - 0.5, color="#111827", linewidth=0.8, alpha=0.55)
            if ax is axes[0]:
                ax.text(-0.98, y, label, transform=ax.get_yaxis_transform(), va="center", ha="right", fontsize=7.8, color="#374151", fontweight="semibold", clip_on=False)
    out_pdf = Path(resolved["paths"]["figures_root"]) / "figure_2_main_benchmark_heatmaps.pdf"
    out_png = Path(resolved["paths"]["figures_root"]) / "figure_2_main_benchmark_heatmaps.png"
    save_figure(fig, out_pdf, out_png)
    plt.close(fig)
    return {"pdf": str(out_pdf), "png": str(out_png)}


def _read_forecast_series(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True, errors="coerce")
    y_col = "y_hat" if "y_hat" in df.columns else "y_pred"
    df["y_pred"] = pd.to_numeric(df[y_col], errors="coerce")
    if "pi_low" in df.columns:
        df["pi_low"] = pd.to_numeric(df["pi_low"], errors="coerce")
    if "pi_high" in df.columns:
        df["pi_high"] = pd.to_numeric(df["pi_high"], errors="coerce")
    return df.dropna(subset=["timestamp_utc", "y_pred"])


def _read_actual(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["Datetime"] = pd.to_datetime(df["Datetime"], utc=True, errors="coerce")
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce")
    return df.dropna(subset=["Datetime", "Value"])


def _plot_window(ax, metrics: pd.DataFrame, rep_row: pd.Series, title: str, *, show_interval: bool = True) -> None:
    colors = model_colors()
    ck = str(rep_row["case_key"])
    origin = str(rep_row["origin_utc"])
    sub = metrics[(metrics["case_key"].astype(str) == ck) & (metrics["origin_utc"].astype(str) == origin)]
    # actual future from first available row
    if not sub.empty:
        actual_path = Path(str(sub.iloc[0]["artifact_dir"])) / "actual_future.csv"
        if actual_path.exists():
            actual = _read_actual(actual_path)
            ax.plot(actual["Datetime"], actual["Value"], color=colors["observed"], linewidth=2.2, label="Observed", zorder=5)
    for mk in MODEL_ORDER_MAIN:
        row = sub[sub["model_key"].astype(str) == mk]
        if row.empty:
            continue
        fdf = _read_forecast_series(str(row.iloc[0]["forecast_csv_path"]))
        ax.plot(fdf["timestamp_utc"], fdf["y_pred"], color=colors.get(mk, "#666"), linewidth=1.55, label=MODEL_LABELS.get(mk, mk), alpha=0.96)
        if show_interval and mk == "chronos-base" and {"pi_low", "pi_high"}.issubset(fdf.columns):
            ax.fill_between(fdf["timestamp_utc"], fdf["pi_low"].astype(float), fdf["pi_high"].astype(float), color=colors.get(mk, "#D97706"), alpha=0.12, linewidth=0)
    ax.set_title(title, loc="left", fontweight="semibold")
    ax.grid(True, axis="y")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="x", rotation=25)


def make_figure_3_hydrologic_trajectories(resolved: Dict[str, Any], metrics: pd.DataFrame, reps: pd.DataFrame) -> Dict[str, str]:
    _require_columns(reps, ["case_key", "group", "label", "origin_utc", "selection_role"], "representative_windows.csv")
    hyd = reps[reps["group"].isin(["core_flow", "core_stage"])].copy()
    selected = []
    for group in ["core_flow", "core_stage"]:
        med = hyd[(hyd["group"] == group) & (hyd["selection_role"] == "median")]
        if not med.empty:
            selected.append(med.iloc[0])
    worst = hyd[hyd["selection_role"] == "worst"]
    best = hyd[hyd["selection_role"] == "best"]
    if not worst.empty:
        selected.append(worst.iloc[0])
    if not best.empty:
        selected.append(best.iloc[0])
    if len(selected) < 2:
        raise RuntimeError("Not enough hydrologic representative windows for Figure 3")
    selected = selected[:4]
    n = len(selected)
    fig, axes = plt.subplots(2, 2, figsize=figure_size("trajectories"))
    fig.subplots_adjust(left=0.08, right=0.985, top=0.92, bottom=0.16, hspace=0.34, wspace=0.22)
    axes = axes.ravel()
    for i, row in enumerate(selected):
        title = f"({chr(97+i)}) {row['label']} — {row['selection_role']} window"
        _plot_window(axes[i], metrics, row, title)
    for j in range(n, len(axes)):
        axes[j].axis("off")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.03))
    out_pdf = Path(resolved["paths"]["figures_root"]) / "figure_3_hydrologic_trajectories.pdf"
    out_png = Path(resolved["paths"]["figures_root"]) / "figure_3_hydrologic_trajectories.png"
    save_figure(fig, out_pdf, out_png)
    plt.close(fig)
    return {"pdf": str(out_pdf), "png": str(out_png)}


def make_figure_4_turbidity_and_traceability(resolved: Dict[str, Any], metrics: pd.DataFrame, reps: pd.DataFrame) -> Dict[str, str]:
    turb = reps[(reps["group"] == "supplement_turbidity") & (reps["selection_role"] == "median")]
    if turb.empty:
        turb = reps[reps["group"] == "supplement_turbidity"]
    if turb.empty:
        raise RuntimeError("No turbidity representative window available for Figure 4")
    report_index_path = Path(resolved["paths"]["deterministic_reports_root"]) / "deterministic_report_index.csv"
    report_text = "Deterministic report not generated yet. Run 04_render_deterministic_reports.py first."
    if report_index_path.exists():
        idx = pd.read_csv(report_index_path)
        tidx = idx[idx["group"].astype(str) == "supplement_turbidity"]
        if not tidx.empty:
            jpath = Path(str(tidx.iloc[0].get("json_path")))
            if jpath.exists():
                payload = json.loads(jpath.read_text(encoding="utf-8"))
                brief = payload.get("brief") or {}
                findings = brief.get("key_findings") or []
                summary = brief.get("executive_summary") or ""
                wrapped_summary = textwrap.fill(summary, width=46)
                wrapped_findings = []
                for x in findings[:3]:
                    wrapped_findings.append(textwrap.fill(str(x), width=43, initial_indent="• ", subsequent_indent="  "))
                report_text = wrapped_summary + "\n\n" + "\n".join(wrapped_findings)
    fig, axes = plt.subplots(1, 2, figsize=figure_size("turbidity_traceability"), gridspec_kw={"width_ratios": [1.35, 1.15]})
    fig.subplots_adjust(left=0.055, right=0.985, top=0.92, bottom=0.10, wspace=0.10)
    _plot_window(axes[0], metrics, turb.iloc[0], "(a) Turbidity representative forecast")
    handles, labels = axes[0].get_legend_handles_labels()
    axes[0].legend(handles, labels, loc="upper left", frameon=False, ncol=2, fontsize=8)
    axes[1].axis("off")
    axes[1].set_title("(b) Deterministic artifact-based interpretation", loc="left", fontweight="semibold")
    box = dict(boxstyle="round,pad=0.55", facecolor="#F8FAFC", edgecolor="#CBD5E1", linewidth=0.9)
    axes[1].text(0.03, 0.95, report_text[:1600], transform=axes[1].transAxes, va="top", ha="left", fontsize=7.7, linespacing=1.25, color="#111827", bbox=box, wrap=False, clip_on=False)
    out_pdf = Path(resolved["paths"]["figures_root"]) / "figure_4_turbidity_and_traceability.pdf"
    out_png = Path(resolved["paths"]["figures_root"]) / "figure_4_turbidity_and_traceability.png"
    save_figure(fig, out_pdf, out_png)
    plt.close(fig)
    return {"pdf": str(out_pdf), "png": str(out_png)}


def make_figure_s1_chronos_family_heatmaps(resolved: Dict[str, Any], family_metrics: pd.DataFrame) -> Dict[str, str]:
    required = ["case_key", "group", "label", "model_key", "rmse_mean", "mae_mean", "relative_to_chronos_base_mean"]
    _require_columns(family_metrics, required, "chronos_family_case_metrics.csv")
    flavor_order = [m for m in ["chronos-tiny", "chronos-mini", "chronos-base", "chronos-large"] if m in set(family_metrics["model_key"].astype(str))]
    if len(flavor_order) < 3:
        raise RuntimeError("Fewer than three Chronos flavors available for Figure S1")
    case_order = _ordered_cases(family_metrics)
    labels = _case_labels(family_metrics, case_order)
    model_labels = [MODEL_LABELS.get(m, m) for m in flavor_order]
    rmse = _metric_matrix(family_metrics, "rmse_mean", case_order, flavor_order)
    mae = _metric_matrix(family_metrics, "mae_mean", case_order, flavor_order)
    rel = _metric_matrix(family_metrics, "relative_to_chronos_base_mean", case_order, flavor_order)
    fig, axes = plt.subplots(1, 3, figsize=figure_size("heatmap_family"), constrained_layout=True, sharey=True)
    _draw_heatmap_panel(axes[0], rmse, "(a) RMSE", labels, model_labels, row_normalized=True, cmap=heatmap_cmap("rmse"))
    _draw_heatmap_panel(axes[1], mae, "(b) MAE", labels, model_labels, row_normalized=True, cmap=heatmap_cmap("mae"))
    _draw_heatmap_panel(axes[2], rel, "(c) Relative to Base", labels, model_labels, row_normalized=False, cmap=heatmap_cmap("relative"), diverging=True)
    out_pdf = Path(resolved["paths"]["figures_root"]) / "figure_s1_chronos_family_heatmaps.pdf"
    out_png = Path(resolved["paths"]["figures_root"]) / "figure_s1_chronos_family_heatmaps.png"
    save_figure(fig, out_pdf, out_png)
    plt.close(fig)
    return {"pdf": str(out_pdf), "png": str(out_png)}


def make_figure_s2_chronos_tradeoff(resolved: Dict[str, Any], family_metrics: pd.DataFrame, training_summary: pd.DataFrame) -> Dict[str, str]:
    _require_columns(family_metrics, ["model_key", "rmse_mean"], "chronos_family_case_metrics.csv")
    _require_columns(training_summary, ["model_key", "training_wallclock_s"], "model_training_summary.csv")
    perf = family_metrics.groupby("model_key", as_index=False).agg(rmse_mean=("rmse_mean", "mean"), n_cases=("case_key", "nunique"))
    time = training_summary[training_summary["model_family"].astype(str) == "chronos"].groupby("model_key", as_index=False).agg(training_wallclock_s=("training_wallclock_s", "mean"))
    df = perf.merge(time, on="model_key", how="inner")
    if len(df) < 3:
        raise RuntimeError("Not enough Chronos flavors with timing data for Figure S2")
    colors = model_colors()
    fig, ax = plt.subplots(figsize=figure_size("tradeoff"), constrained_layout=True)
    for _, r in df.iterrows():
        mk = str(r["model_key"])
        ax.scatter(float(r["training_wallclock_s"]), float(r["rmse_mean"]), s=70 + 15 * int(r.get("n_cases", 1)), color=colors.get(mk, "#D97706"), edgecolor="#111827", linewidth=0.6)
        ax.annotate(MODEL_LABELS.get(mk, mk), (float(r["training_wallclock_s"]), float(r["rmse_mean"])), xytext=(6, 4), textcoords="offset points", fontsize=8)
    ax.set_xlabel("Mean training / optimization wallclock (s)")
    ax.set_ylabel("Mean RMSE across included cases")
    ax.set_title("Chronos-family performance–cost tradeoff", fontweight="semibold")
    ax.grid(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    out_pdf = Path(resolved["paths"]["figures_root"]) / "figure_s2_chronos_tradeoff.pdf"
    out_png = Path(resolved["paths"]["figures_root"]) / "figure_s2_chronos_tradeoff.png"
    save_figure(fig, out_pdf, out_png)
    plt.close(fig)
    return {"pdf": str(out_pdf), "png": str(out_png)}


def make_tables(resolved: Dict[str, Any], case_metrics: pd.DataFrame, family_metrics: pd.DataFrame, training_summary: pd.DataFrame, case_resolution: pd.DataFrame) -> List[Dict[str, Any]]:
    tables_root = Path(resolved["paths"]["tables_root"])
    tables_root.mkdir(parents=True, exist_ok=True)
    outputs: List[Dict[str, Any]] = []
    # Table 1
    inc = case_resolution[case_resolution["status"].astype(str) == "included"].copy()
    t1_cols = [c for c in ["case_key", "group", "station_id", "parameter_code", "label", "train_coverage", "eval_coverage", "valid_origins"] if c in inc.columns]
    t1 = inc[t1_cols].copy()
    t1["horizon_h"] = resolved["benchmark"].get("horizon_h")
    t1_path = tables_root / "table_1_frozen_benchmark_inventory.csv"
    t1.to_csv(t1_path, index=False)
    outputs.append({"table_id": "table_1_frozen_benchmark_inventory", "status": "generated", "output_csv": str(t1_path)})
    # Table 2
    t2_cols = [c for c in ["case_key", "group", "label", "model_key", "n_origins_used", "rmse_mean", "rmse_median", "mae_mean", "mae_median", "skill_vs_persistence_mean"] if c in case_metrics.columns]
    t2 = case_metrics[t2_cols].copy()
    t2_path = tables_root / "table_2_main_benchmark_metrics.csv"
    t2.to_csv(t2_path, index=False)
    outputs.append({"table_id": "table_2_main_benchmark_metrics", "status": "generated", "output_csv": str(t2_path)})
    # Table 3
    perf = family_metrics.groupby("model_key", as_index=False).agg(rmse_mean=("rmse_mean", "mean"), mae_mean=("mae_mean", "mean"), relative_to_chronos_base_mean=("relative_to_chronos_base_mean", "mean"), n_cases=("case_key", "nunique"))
    time = training_summary[training_summary["model_family"].astype(str) == "chronos"].groupby("model_key", as_index=False).agg(training_wallclock_s=("training_wallclock_s", "mean")) if "model_family" in training_summary.columns else pd.DataFrame(columns=["model_key", "training_wallclock_s"])
    t3 = perf.merge(time, on="model_key", how="left")
    t3_path = tables_root / "table_3_chronos_family_summary.csv"
    t3.to_csv(t3_path, index=False)
    outputs.append({"table_id": "table_3_chronos_family_summary", "status": "generated", "output_csv": str(t3_path)})
    # Supplements
    s1_path = tables_root / "table_s1_chronos_family_case_metrics.csv"
    family_metrics.to_csv(s1_path, index=False)
    outputs.append({"table_id": "table_s1_chronos_family_case_metrics", "status": "generated", "output_csv": str(s1_path)})
    s2 = inc.copy()
    s2_path = tables_root / "table_s2_case_provenance.csv"
    s2.to_csv(s2_path, index=False)
    outputs.append({"table_id": "table_s2_case_provenance", "status": "generated", "output_csv": str(s2_path)})
    return outputs


def write_results_summary(resolved: Dict[str, Any], case_metrics: pd.DataFrame, family_metrics: pd.DataFrame, path: Path) -> None:
    lines = ["# WaterAInalytics paper results summary", ""]
    lines.append(f"Run tag: `{resolved['run_tag']}`")
    lines.append("")
    lines.append("## Main benchmark")
    for ck, g in case_metrics.groupby("case_key"):
        best = g.sort_values("rmse_mean").iloc[0]
        lines.append(f"- `{ck}`: best mean RMSE = **{best['model_key']}** ({_fmt_number(best['rmse_mean'])}); best mean MAE = {_fmt_number(best['mae_mean'])}.")
    lines.append("")
    lines.append("## Chronos family")
    fam = family_metrics.groupby("model_key", as_index=False).agg(rmse_mean=("rmse_mean", "mean"), mae_mean=("mae_mean", "mean"))
    for _, r in fam.sort_values("rmse_mean").iterrows():
        lines.append(f"- `{r['model_key']}`: average RMSE = {_fmt_number(r['rmse_mean'])}; average MAE = {_fmt_number(r['mae_mean'])}.")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    apply_paper_style()
    resolved = load_json(args.config)
    root = Path(resolved["paths"]["run_root"])
    backtests_root = Path(resolved["paths"]["backtests_root"])
    family_root = Path(resolved["paths"].get("backtests_chronos_family_root", root / "backtests_chronos_family"))
    trained_root = Path(resolved["paths"]["trained_models_root"])
    manifests_root = Path(resolved["paths"]["manifests_root"])
    manifests_root.mkdir(parents=True, exist_ok=True)
    case_metrics = pd.read_csv(backtests_root / "case_model_metrics.csv")
    origin_metrics = pd.read_csv(backtests_root / "origin_metrics.csv")
    reps = pd.read_csv(backtests_root / "representative_windows.csv")
    family_metrics = pd.read_csv(family_root / "chronos_family_case_metrics.csv")
    training_summary = pd.read_csv(trained_root / "model_training_summary.csv")
    case_resolution = pd.read_csv(root / "case_resolution_report.csv")

    figure_manifest: List[Dict[str, Any]] = []
    table_manifest: List[Dict[str, Any]] = []
    for fid, fn in [
        ("figure_2_main_benchmark_heatmaps", lambda: make_figure_2_main_benchmark_heatmaps(resolved, case_metrics)),
        ("figure_3_hydrologic_trajectories", lambda: make_figure_3_hydrologic_trajectories(resolved, origin_metrics, reps)),
        ("figure_4_turbidity_and_traceability", lambda: make_figure_4_turbidity_and_traceability(resolved, origin_metrics, reps)),
        ("figure_s1_chronos_family_heatmaps", lambda: make_figure_s1_chronos_family_heatmaps(resolved, family_metrics)),
        ("figure_s2_chronos_tradeoff", lambda: make_figure_s2_chronos_tradeoff(resolved, family_metrics, training_summary)),
    ]:
        try:
            out = fn()
            figure_manifest.append({"figure_id": fid, "status": "generated", **out})
        except Exception as exc:
            status = "failed"
            figure_manifest.append({"figure_id": fid, "status": status, "error": str(exc)})
            if fid in {"figure_2_main_benchmark_heatmaps", "figure_3_hydrologic_trajectories", "figure_4_turbidity_and_traceability"}:
                raise
    table_manifest = make_tables(resolved, case_metrics, family_metrics, training_summary, case_resolution)
    save_json(manifests_root / "figures_manifest.json", {"figures": figure_manifest})
    save_json(manifests_root / "tables_manifest.json", {"tables": table_manifest})
    summary_path = root / "results_summary.md"
    write_results_summary(resolved, case_metrics, family_metrics, summary_path)
    freeze = {"run_tag": resolved["run_tag"], "figures_manifest": str(manifests_root / "figures_manifest.json"), "tables_manifest": str(manifests_root / "tables_manifest.json"), "results_summary": str(summary_path)}
    save_json(manifests_root / "results_freeze_manifest.json", freeze)
    print("Results bundle generated.")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
