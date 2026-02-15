from __future__ import annotations

from typing import Dict, List, Tuple

from core.llm_analysis.cache.keying import stable_json_hash
from core.llm_analysis.config import AnalysisConfig
from core.llm_analysis.forecast_integration.models import ForecastContext
from core.llm_analysis.web_context.models import SourceDoc, Snippet
from core.llm_analysis.extraction.models import FactBundle, FactEvidence, FactItem


def _mk_fact_id(payload: Dict) -> str:
    return stable_json_hash(payload)[:12]


def _mk_confidence(level: str, rationale: str) -> Dict[str, str]:
    level = (level or "low").lower().strip()
    if level not in ("low", "medium", "high"):
        level = "low"
    return {"level": level, "rationale": rationale}


def _mk_relevance(h1: str = "low", h2: str = "low", h3: str = "low") -> Dict[str, str]:
    # horizons labeled as strings for now; keep stable contract
    return {"H1": h1, "H2": h2, "H3": h3}


def _keyword_rules() -> List[Tuple[str, str, str, List[str], Dict[str, str]]]:
    """
    Returns list of rules:
      (fact_type, title, claim_template, keywords, relevance_to_horizons)
    claim_template can use {station_id}.
    """
    return [
        (
            "data_source",
            "USGS NWIS monitoring page",
            "USGS NWIS provides time series data and station metadata for {station_id}.",
            ["waterdata.usgs.gov", "nwis", "monitoring-location", "site_no", "gage", "streamflow", "discharge"],
            _mk_relevance("medium", "medium", "medium"),
        ),
        (
            "data_source",
            "USGS Water Services API documentation",
            "USGS Water Services endpoints can be used to retrieve daily/instantaneous values relevant to {station_id}.",
            ["waterservices.usgs.gov", "daily values", "dv service", "iv service", "service details", "dataretrieval"],
            _mk_relevance("medium", "medium", "medium"),
        ),
        (
            "hydro_forecast_context",
            "River and flood forecasts are typically provided by forecast agencies (not USGS)",
            "USGS indicates that river/flood forecasts are generally provided by dedicated forecast agencies; USGS focuses on observations for {station_id}.",
            ["river forecast", "flood forecast", "obtain river forecasts", "how can i obtain", "forecast"],
            _mk_relevance("high", "high", "high"),
        ),
        (
            "station_metadata",
            "Station metadata and monitoring context",
            "Station metadata (location/site info) helps interpret short-term changes at {station_id}.",
            ["station", "monitoring", "location", "site information", "drainage", "basin", "latitude", "longitude"],
            _mk_relevance("medium", "medium", "medium"),
        ),
        (
            "meteorology",
            "Short-term weather context may affect observed values",
            "Short-term weather conditions (rainfall/temperature/alerts) may influence near-term variability affecting {station_id}.",
            ["weather", "hourly", "radar", "alerts", "rain", "precip", "forecast", "nws", "noaa"],
            _mk_relevance("high", "medium", "medium"),
        ),
    ]


def extract_facts_rule_based(
    cfg: AnalysisConfig,
    forecast_ctx: ForecastContext,
    sources: List[SourceDoc],
    snippets: List[Snippet],
) -> FactBundle:
    """
    MVP rule-based fact extraction (no LLM).
    - Uses keyword matching on snippets
    - Emits a small set of facts with attached evidence
    """
    station_id = forecast_ctx.station_id
    parameter = forecast_ctx.parameter
    run_dt = forecast_ctx.run_datetime_utc.isoformat()

    # Index sources
    src_by_id: Dict[str, SourceDoc] = {s.source_id: s for s in sources}

    rules = _keyword_rules()

    # Collect evidence candidates per rule
    evidence_by_rule: Dict[str, List[FactEvidence]] = {}

    for sn in snippets:
        text_l = (sn.text or "").lower()
        source_id = sn.source_id
        src = src_by_id.get(source_id)

        for (fact_type, title, claim_tpl, keywords, _rel) in rules:
            rule_key = f"{fact_type}:{title}"
            if any(k.lower() in text_l for k in keywords):
                if src is None:
                    continue
                evidence = FactEvidence(
                    source_id=src.source_id,
                    url=src.url,
                    retrieved_at_utc=src.retrieved_at_utc,
                    snippet_id=sn.snippet_id,
                    snippet_text=sn.text[:1200],
                    publisher=src.publisher,
                    published_at_utc=src.published_at_utc,
                )
                evidence_by_rule.setdefault(rule_key, []).append(evidence)

    facts: List[FactItem] = []

    # Cap facts to keep report tight in MVP
    max_facts = 12
    for (fact_type, title, claim_tpl, _keywords, relevance) in rules:
        rule_key = f"{fact_type}:{title}"
        ev_list = evidence_by_rule.get(rule_key, [])
        if not ev_list:
            continue

        # Dedup evidence by (source_id, snippet_id) BEFORE slicing
        seen_ev = set()
        ev_uniq: List[FactEvidence] = []
        for e in ev_list:
            key = (e.source_id, e.url)
            if key in seen_ev:
                continue
            seen_ev.add(key)
            ev_uniq.append(e)
        ev_list = ev_uniq

        # Keep only a few evidence items per fact (audit still in snippets.jsonl)
        ev_list = ev_list[:3]

        claim = claim_tpl.format(station_id=station_id)

        # Confidence heuristic: more deduped evidence => higher confidence
        if len(ev_list) >= 3:
            conf = _mk_confidence("medium", "Multiple matching snippets across sources.")
        else:
            conf = _mk_confidence("low", "Single/few matching snippets; heuristic extraction.")

        fact_id = _mk_fact_id(
            {
                "station_id": station_id,
                "parameter": parameter,
                "type": fact_type,
                "title": title,
                "claim": claim,
                "evidence": [(e.source_id, e.snippet_id) for e in ev_list],
            }
        )

        facts.append(
            FactItem(
                fact_id=fact_id,
                type=fact_type,
                title=title,
                claim=claim,
                time_window={"scope": "general", "run_datetime_utc": run_dt},
                location={"station_id": station_id},
                expected_effect={"direction": "unknown", "mechanism": "contextual"},
                relevance_to_horizons=relevance,
                confidence=conf,
                evidence=ev_list,
                tags=[fact_type, "mvp", "rule_based"],
            )
        )

        if len(facts) >= max_facts:
            break

    summary = {
        "top_facts": [f.title for f in facts[:5]],
        "risk_notes": [],
        "counts": {"facts": len(facts), "snippets": len(snippets), "sources": len(sources)},
        "method": "rule_based_v0",
    }

    return FactBundle(
        schema_version=cfg.schema_version,
        station_id=station_id,
        parameter=parameter,
        run_datetime_utc=run_dt,
        facts=facts,
        summary=summary,
    )
