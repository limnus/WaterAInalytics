from __future__ import annotations

from typing import List

from core.llm_analysis.config import ReportStyle
from core.llm_analysis.forecast_integration.models import ForecastContext
from core.llm_analysis.extraction.models import FactBundle
from core.llm_analysis.web_context.models import SourceDoc
from core.llm_analysis.models import ReportArtifact
from core.llm_analysis.report.templates import TEMPLATES


def format_sources(sources: List[SourceDoc]) -> List[str]:
    bib = []
    for s in sources:
        title = s.title or "Untitled"
        pub = s.publisher or "Unknown publisher"
        bib.append(f"- [{s.source_id}] {pub}. *{title}*. {s.url} (retrieved {s.retrieved_at_utc})")
    return bib


def generate_report_md(
    style: ReportStyle,
    forecast: ForecastContext,
    facts: FactBundle,
    sources: List[SourceDoc],
    used_pages: int,
    max_pages: int,
) -> ReportArtifact:
    tpl = TEMPLATES.get(style.tone, TEMPLATES["neutral"])
    bib = format_sources(sources)

    lines = []
    lines.append(f"# {tpl['title']}")
    lines.append("")
    lines.append(f"**Station:** {forecast.station_id}  ")
    lines.append(f"**Parameter:** {forecast.parameter}  ")
    lines.append(f"**Model:** {forecast.provenance.model_key}  ")
    lines.append(f"**Run (UTC):** {forecast.run_datetime_utc.isoformat()}  ")
    lines.append("")
    lines.append("## Web Context Collection")
    lines.append(f"- Pages used: {used_pages}/{max_pages}")
    lines.append("")
    lines.append("## Extracted Facts (Summary)")

    if not getattr(facts, "facts", None):
        lines.append("No facts extracted (MVP placeholder).")
    else:
        # Summary line
        lines.append(f"{len(facts.facts)} facts extracted (rule-based MVP).")
        lines.append("")
        # Render facts
        for i, fi in enumerate(facts.facts, start=1):
            title = getattr(fi, "title", "") or "(untitled fact)"
            claim = getattr(fi, "claim", "") or ""
            ftype = getattr(fi, "type", "") or "unknown"
            conf = getattr(fi, "confidence", {}) or {}
            conf_level = conf.get("level", "low")
            conf_rat = conf.get("rationale", "")

            lines.append(f"{i}. **{title}**  \n   Type: `{ftype}` | Confidence: **{conf_level}**")
            if claim:
                lines.append(f"   - Claim: {claim}")

            if conf_rat:
                lines.append(f"   - Rationale: {conf_rat}")

            # Evidence (up to 3)
            evs = getattr(fi, "evidence", []) or []
            if evs:
                lines.append("   - Evidence:")
                for ev in evs[:3]:
                    url = getattr(ev, "url", None) or ""
                    snippet_id = getattr(ev, "snippet_id", None) or ""
                    publisher = getattr(ev, "publisher", None) or ""
                    retrieved = getattr(ev, "retrieved_at_utc", None) or ""
                    lines.append(f"     - [{snippet_id}] {publisher} {url} (retrieved {retrieved})")
            lines.append("")

    lines.append("")
    lines.append("## Sources")
    lines.extend(bib)

    return ReportArtifact(format="markdown", content="\n".join(lines), sources_bibliography=bib)
