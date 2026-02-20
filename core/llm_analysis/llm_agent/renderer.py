from __future__ import annotations

from typing import Any, Dict, List


def _fmt_cites(item: Dict[str, Any]) -> str:
    cids = item.get("claim_ids") or []
    eids = item.get("evidence_ids") or []
    bits: List[str] = []

    if cids:
        bits.append("claims: " + ", ".join(cids))
    if eids:
        bits.append("evidence: " + ", ".join(eids))

    conf = item.get("confidence")
    if conf:
        bits.append("conf: " + str(conf))

    return (" (" + " | ".join(bits) + ")") if bits else ""


def _fallback_text(it: Dict[str, Any]) -> str:
    issue = (it.get("issue") or "").strip()
    count = it.get("count")
    if issue and count is not None:
        return f"issue={issue} (count={count})"
    if issue:
        return f"issue={issue}"
    return ""


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []

    lines.append("## LLM Analyst Report (v0.9.1)")
    lines.append("")

    summary = (report.get("executive_summary") or "").strip()
    if summary:
        lines.append("### Executive Summary")
        lines.append(summary)
        lines.append("")

    def _section(title: str, key: str):
        items = report.get(key) or []
        items = [x for x in items if isinstance(x, dict)]
        if not items:
            return

        lines.append(f"### {title}")
        for it in items:
            txt = (it.get("text") or "").strip()
            if not txt:
                txt = _fallback_text(it)
            if txt:
                lines.append(f"- {txt}{_fmt_cites(it)}")
        lines.append("")

    _section("Key Findings", "key_findings")
    _section("Forecast Interpretation", "forecast_interpretation")
    _section("Limitations", "limitations")

    oq = report.get("open_questions") or []
    oq = [x for x in oq if isinstance(x, dict)]
    if oq:
        lines.append("### Open Questions")
        for it in oq:
            txt = (it.get("text") or "").strip()
            if txt:
                lines.append(f"- {txt}")
        lines.append("")

    val = report.get("validation") or {}

    lines.append("### Validation")
    lines.append(f"- citation_coverage: {val.get('citation_coverage')}")
    lines.append(f"- missing_citations_count: {val.get('missing_citations_count')}")
    lines.append(f"- unknown_claim_ids_count: {val.get('unknown_claim_ids_count')}")
    lines.append(f"- unknown_evidence_ids_count: {val.get('unknown_evidence_ids_count')}")

    flags = val.get("flags") or []
    if flags:
        lines.append(f"- flags: {', '.join(flags)}")

    lines.append("")

    return "\n".join(lines)
