from __future__ import annotations

from pathlib import Path
from typing import Tuple

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap


def apply_paper_style() -> None:
    """Apply the WaterAInalytics paper plotting style.

    This intentionally avoids raw Matplotlib defaults while staying journal-safe:
    clean white background, restrained colors, readable labels, and vector-friendly output.
    """
    plt.rcParams.update(
        {
            "figure.dpi": 140,
            "savefig.dpi": 320,
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "axes.linewidth": 0.8,
            "axes.edgecolor": "#333333",
            "axes.facecolor": "#FFFFFF",
            "figure.facecolor": "#FFFFFF",
            "grid.color": "#E6E8EB",
            "grid.linewidth": 0.6,
            "grid.alpha": 0.9,
            "axes.grid": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def model_colors() -> dict[str, str]:
    return {
        "observed": "#1F2933",
        "actual": "#1F2933",
        "persistence": "#8B949E",
        "ridge": "#2563A9",
        "chronos-base": "#D97706",
        "chronos-mini": "#B45309",
        "chronos-tiny": "#F59E0B",
        "chronos-large": "#92400E",
        "grid": "#E6E8EB",
        "text": "#111827",
        "muted_text": "#4B5563",
    }


def heatmap_cmap(metric: str):
    metric = str(metric).lower()
    if "skill" in metric or "relative" in metric:
        return "RdYlGn"
    return LinearSegmentedColormap.from_list(
        "waterainalytics_blues",
        ["#F8FAFC", "#DBEAFE", "#60A5FA", "#1D4ED8"],
    )


def figure_size(kind: str) -> Tuple[float, float]:
    sizes = {
        "heatmap_main": (9.2, 5.1),
        "heatmap_family": (8.7, 5.0),
        "trajectories": (8.9, 6.35),
        "turbidity_traceability": (9.2, 5.1),
        "tradeoff": (6.2, 4.2),
    }
    return sizes.get(kind, (7.0, 4.5))


def save_figure(fig, pdf_path: str | Path, png_path: str | Path) -> None:
    pdf_path = Path(pdf_path)
    png_path = Path(png_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, bbox_inches="tight")
