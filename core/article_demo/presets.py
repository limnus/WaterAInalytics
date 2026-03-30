from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from core.config.env import load_project_env


@dataclass(frozen=True)
class ArticleDemoProfile:
    enabled: bool
    key: str
    name: str
    station_ids: List[str]
    station_labels: Dict[str, str]
    parameter_code: str
    history_days: int
    horizon_h: int
    model_key: str
    description: str = ""

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


def get_article_demo_profiles() -> List[ArticleDemoProfile]:
    load_project_env()
    enabled = _get_bool("ARTICLE_DEMO_ENABLED", False)
    station_ids = _parse_csv(os.getenv("ARTICLE_DEMO_STATION_IDS", ""))
    if not enabled or not station_ids:
        return []

    labels = _parse_csv(os.getenv("ARTICLE_DEMO_STATION_LABELS", ""))
    history_days = _get_int("ARTICLE_DEMO_HISTORY_DAYS", 7, min_value=1, max_value=30)
    horizon_h = _get_int("ARTICLE_DEMO_HORIZON_H", 24, min_value=1, max_value=168)
    model_key = os.getenv("ARTICLE_DEMO_MODEL_KEY", "ridge").strip() or "ridge"

    core_profile = ArticleDemoProfile(
        enabled=True,
        key="paper-core-flow",
        name=os.getenv("ARTICLE_DEMO_NAME", "Paper Core — Flow (00060)").strip() or "Paper Core — Flow (00060)",
        station_ids=station_ids,
        station_labels=_parse_labels(station_ids, labels),
        parameter_code=os.getenv("ARTICLE_DEMO_PARAMETER_CODE", "00060").strip() or "00060",
        history_days=history_days,
        horizon_h=horizon_h,
        model_key=model_key,
        description="Primary reproducible paper experiment across the three article stations using discharge (00060).",
    )

    profiles: List[ArticleDemoProfile] = [core_profile]

    include_supplement = _get_bool("ARTICLE_DEMO_INCLUDE_SUPPLEMENTAL_PRESETS", True)
    supplement_station_id = os.getenv("ARTICLE_DEMO_SUPPLEMENT_STATION_ID", "USGS-07374525").strip() or "USGS-07374525"
    supplement_station_label = os.getenv("ARTICLE_DEMO_SUPPLEMENT_STATION_LABEL", "USGS-07374525 — Water quality case").strip() or supplement_station_id
    supplement_parameter = os.getenv("ARTICLE_DEMO_SUPPLEMENT_PARAMETER_CODE", "63680").strip() or "63680"
    supplement_name = os.getenv("ARTICLE_DEMO_SUPPLEMENT_NAME", "Paper Supplement — Turbidity (63680)").strip() or "Paper Supplement — Turbidity (63680)"

    if include_supplement:
        profiles.append(
            ArticleDemoProfile(
                enabled=True,
                key="paper-supplement-turbidity",
                name=supplement_name,
                station_ids=[supplement_station_id],
                station_labels={supplement_station_id: supplement_station_label},
                parameter_code=supplement_parameter,
                history_days=history_days,
                horizon_h=horizon_h,
                model_key=model_key,
                description="Supplementary reproducible paper experiment for the water-quality case study using turbidity (63680).",
            )
        )

    return profiles


def get_article_demo_profile(profile_key: str | None = None) -> Optional[ArticleDemoProfile]:
    profiles = get_article_demo_profiles()
    if not profiles:
        return None
    if profile_key:
        for profile in profiles:
            if profile.key == profile_key:
                return profile
    return profiles[0]
