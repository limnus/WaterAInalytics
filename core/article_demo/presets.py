from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from core.config.env import load_project_env


@dataclass(frozen=True)
class ArticleDemoProfile:
    enabled: bool
    name: str
    station_ids: List[str]
    station_labels: Dict[str, str]
    parameter_code: str
    history_days: int
    horizon_h: int
    model_key: str

    def to_dict(self) -> dict:
        return asdict(self)


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int, *, min_value: int, max_value: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(min_value, min(max_value, value))


def _parse_csv(raw: str) -> List[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_labels(station_ids: List[str], labels: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for idx, station_id in enumerate(station_ids):
        label = labels[idx] if idx < len(labels) and labels[idx].strip() else station_id
        out[station_id] = label
    return out



def get_article_demo_profile() -> Optional[ArticleDemoProfile]:
    load_project_env()
    enabled = _get_bool("ARTICLE_DEMO_ENABLED", False)
    station_ids = _parse_csv(os.getenv("ARTICLE_DEMO_STATION_IDS", ""))
    if not enabled or not station_ids:
        return None

    labels = _parse_csv(os.getenv("ARTICLE_DEMO_STATION_LABELS", ""))
    return ArticleDemoProfile(
        enabled=True,
        name=os.getenv("ARTICLE_DEMO_NAME", "Article demo").strip() or "Article demo",
        station_ids=station_ids,
        station_labels=_parse_labels(station_ids, labels),
        parameter_code=os.getenv("ARTICLE_DEMO_PARAMETER_CODE", "00065").strip() or "00065",
        history_days=_get_int("ARTICLE_DEMO_HISTORY_DAYS", 7, min_value=1, max_value=30),
        horizon_h=_get_int("ARTICLE_DEMO_HORIZON_H", 24, min_value=1, max_value=168),
        model_key=os.getenv("ARTICLE_DEMO_MODEL_KEY", "ridge").strip() or "ridge",
    )
