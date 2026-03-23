from __future__ import annotations

from typing import Dict, List

PRESENTATION_OPTIONS: List[str] = [
    "Narrative paragraph",
    "Structured bullets",
    "Technical report",
]


_PRESENTATION_MAP: Dict[str, Dict[str, str]] = {
    "Narrative paragraph": {
        "report_tone": "executive",
        "brief_format": "narrative",
        "description": "A flowing, human-readable summary prioritized for readability.",
    },
    "Structured bullets": {
        "report_tone": "neutral",
        "brief_format": "structured",
        "description": "A concise summary grouped into bullet sections.",
    },
    "Technical report": {
        "report_tone": "technical",
        "brief_format": "technical",
        "description": "A denser, metrics-forward summary for technical review.",
    },
}


def resolve_agentic_presentation(label: str | None) -> Dict[str, str]:
    normalized = (label or "").strip()
    return dict(_PRESENTATION_MAP.get(normalized, _PRESENTATION_MAP["Narrative paragraph"]))


def normalize_focus_text(text: str | None) -> str:
    return (text or "").strip()
