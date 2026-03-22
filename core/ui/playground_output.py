from __future__ import annotations

from dataclasses import dataclass

from core.config.env import get_runtime_settings


@dataclass(frozen=True)
class OutputRenderPolicy:
    content: str
    truncated: bool
    ratio: float
    notice: str


def apply_output_policy(*, content: str, role: str | None) -> OutputRenderPolicy:
    text = str(content or "")
    normalized_role = (role or "").strip().lower()
    ratio = get_runtime_settings().playground_report_truncation_ratio

    if normalized_role != "playground" or ratio >= 1.0 or len(text) <= 1:
        return OutputRenderPolicy(content=text, truncated=False, ratio=ratio, notice="")

    keep_chars = max(1, int(len(text) * ratio))
    keep_chars = min(keep_chars, len(text) - 1)
    trimmed = text[:keep_chars].rstrip()
    pct = int(round(ratio * 100))
    notice = (
        f"Playground limitation: this output is intentionally truncated to {pct}% "
        f"of the full analysis. Change PLAYGROUND_REPORT_TRUNCATION_RATIO in .env to adjust it."
    )
    trimmed = trimmed + "\n\n---\n" + notice
    return OutputRenderPolicy(content=trimmed, truncated=True, ratio=ratio, notice=notice)
