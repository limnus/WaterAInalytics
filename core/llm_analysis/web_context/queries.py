from __future__ import annotations

from typing import List

from core.llm_analysis.config import AnalysisConfig
from core.llm_analysis.forecast_integration.models import ForecastContext
from core.llm_analysis.web_context.models import QueryPlan, TaggedQuery

# Preset profiles keep v0.7.x deterministic (no LLM) while making the pipeline maintainable.
# Avoid overengineering: profiles are just query templates, not agents.
DEFAULT_PROFILE = "default"


def _is_usgs_station(station_id: str) -> bool:
    s = (station_id or "").strip().upper()
    return s.startswith("USGS-") or s.startswith("USGS ")


def _profile_from_cfg(cfg: AnalysisConfig) -> str:
    opts = cfg.collector_opts or {}
    p = (opts.get("query_profile") or opts.get("profile") or "").strip().lower()
    return p or DEFAULT_PROFILE


def build_query_plan(forecast_ctx: ForecastContext, cfg: AnalysisConfig) -> QueryPlan:
    """Build a deterministic query plan for the fixed pipeline.

    Goals (v0.7.0):
      - Keep behavior stable and rule-based.
      - Centralize query templates (methodology clarity).
      - Record which profile was used and a lightweight section tag per query.

    Profiles (minimal):
      - default: generic station + parameter context
      - usgs: USGS/NWIS + Water Services API context
    """

    station_id = (forecast_ctx.station_id or "").strip()
    param = (forecast_ctx.parameter or "").strip()
    profile = _profile_from_cfg(cfg)

    tagged: List[TaggedQuery] = []
    notes_parts: List[str] = []

    is_usgs = _is_usgs_station(station_id) or ("USGS" in (forecast_ctx.meta or {}).get("agency", "").upper())

    if profile == "usgs" or (profile == DEFAULT_PROFILE and is_usgs):
        # Keep it focused: station page + NWIS + API docs + variable interpretation.
        chosen_profile = "usgs"
        notes_parts.append("USGS/NWIS-focused plan")
        sid = station_id

        tagged.extend(
            [
                TaggedQuery(q=f"{sid} site:waterdata.usgs.gov", section="station_metadata"),
                TaggedQuery(q=f"{sid} USGS NWIS site_no", section="station_metadata"),
                TaggedQuery(q=f"{sid} monitoring location USGS", section="station_metadata"),
                TaggedQuery(q="USGS Water Services API instantaneous values iv service", section="api_docs"),
                TaggedQuery(q="USGS Water Services API daily values dv service", section="api_docs"),
                TaggedQuery(q="USGS Water Services API parameter codes discharge gage height", section="parameter_codes"),
                TaggedQuery(q=f"{sid} discharge streamflow gage height", section="parameter_context"),
            ]
        )
        # Optional: if parameter isn't the generic 'Value', add it.
        if param and param.lower() != "value":
            tagged.append(TaggedQuery(q=f"{sid} {param} USGS", section="parameter_context"))
    else:
        chosen_profile = DEFAULT_PROFILE
        notes_parts.append("Generic station context plan")
        base_q = station_id
        if base_q:
            tagged.extend(
                [
                    TaggedQuery(q=f"{base_q} monitoring station", section="station_metadata"),
                    TaggedQuery(q=f"{base_q} site metadata location watershed", section="station_metadata"),
                    TaggedQuery(q=f"{base_q} {param} time series" if param else f"{base_q} time series", section="parameter_context"),
                    TaggedQuery(q=f"{base_q} data source API documentation", section="api_docs"),
                ]
            )
        else:
            tagged.extend(
                [
                    TaggedQuery(q="monitoring station metadata API documentation", section="station_metadata"),
                    TaggedQuery(q=f"{param} hydrology monitoring station" if param else "hydrology monitoring station", section="parameter_context"),
                ]
            )

    # De-duplicate while preserving order.
    seen = set()
    tagged_dedup: List[TaggedQuery] = []
    for tq in tagged:
        q2 = (tq.q or "").strip()
        if not q2:
            continue
        if q2 in seen:
            continue
        seen.add(q2)
        tagged_dedup.append(TaggedQuery(q=q2, section=(tq.section or "unknown")))

    notes = "; ".join(notes_parts) if notes_parts else None
    queries = [tq.q for tq in tagged_dedup]

    return QueryPlan(
        queries=queries,
        notes=notes,
        profile=chosen_profile,
        tagged_queries=tagged_dedup,
    )
