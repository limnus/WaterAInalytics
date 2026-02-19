from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.llm_analysis.cache.store import load_json, save_json
from core.llm_analysis.forecast_integration.models import ForecastContext

from .models import LLMConfig, LLMReport
from .prompts import build_system_prompt, required_output_schema_hint, build_user_message, prompt_hash_inputs
from .providers import ollama_chat_json, openai_chat_json
from .utils import sha256_json, sha256_text, safe_json_dumps, clamp_text


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _forecast_summary(fc: ForecastContext) -> Dict[str, Any]:
    last_y = fc.recent_history.y[-1] if (fc.recent_history.y or []) else None
    last_t = fc.recent_history.t_utc[-1].isoformat() if (fc.recent_history.t_utc or []) else None
    next_h = fc.horizons[0] if (fc.horizons or []) else None
    next_pred = None
    if next_h is not None:
        next_pred = {
            "h": int(next_h.h),
            "t_target_utc": next_h.t_target_utc.isoformat(),
            "y_hat": float(next_h.y_hat),
            "p05": None if next_h.p05 is None else float(next_h.p05),
            "p95": None if next_h.p95 is None else float(next_h.p95),
        }
    return {
        "station_id": fc.station_id,
        "parameter": fc.parameter,
        "run_datetime_utc": fc.run_datetime_utc.isoformat(),
        "model_key": fc.provenance.model_key,
        "forecast_output_hash": fc.provenance.forecast_output_hash,
        "horizon_count": len(fc.horizons or []),
        "history_points": len(fc.recent_history.y or []),
        "last_observation": {
            "t_utc": last_t,
            "y": last_y,
            "units": fc.recent_history.units,
        },
        "next_prediction": next_pred,
    }


def _build_llm_payload(run_obj: Dict[str, Any], forecast_ctx: ForecastContext) -> Dict[str, Any]:
    artifacts = (run_obj.get("artifacts") or {})

    # Keep only structured, methodology-relevant signals (no raw HTML)
    # Backward/variant compatibility:
    #   - v0.8.x may store evidence/claims as either a dict wrapper (with 'sources'/'items')
    #     or directly as a list.
    def _as_list(x: Any, *, wrapped_key: str) -> list:
        if x is None:
            return []
        if isinstance(x, list):
            return x
        if isinstance(x, dict):
            v = x.get(wrapped_key)
            return v if isinstance(v, list) else []
        return []

    evidence = _as_list(artifacts.get("evidence"), wrapped_key="sources")
    claims = _as_list(artifacts.get("claims"), wrapped_key="items")
    nar = artifacts.get("narrative") or {}

    payload = {
        "run": {
            "run_id": run_obj.get("run_id"),
            "schema_version": run_obj.get("schema_version"),
            "created_at_utc": run_obj.get("created_at_utc"),
            "query_profile": run_obj.get("query_profile"),
        },
        "station": {
            "station_id": forecast_ctx.station_id,
            "parameter": forecast_ctx.parameter,
        },
        "forecast": _forecast_summary(forecast_ctx),
        "evidence": {
            "sources": [
                {
                    "evidence_id": s.get("evidence_id"),
                    "source_id": s.get("source_id"),
                    "url": s.get("url"),
                    "host": s.get("host"),
                    "title": s.get("title"),
                    "publisher": s.get("publisher"),
                    "retrieved_at_utc": s.get("retrieved_at_utc"),
                    "published_at_utc": s.get("published_at_utc"),
                    "quality_flags": s.get("quality_flags") or [],
                }
                for s in evidence
            ],
        },
        "claims": {
            "items": [
                {
                    "claim_id": c.get("claim_id"),
                    "type": c.get("type"),
                    "text": c.get("text"),
                    "support_score": c.get("support_score"),
                    "uncertainty_level": c.get("uncertainty_level"),
                    "evidence_ids": c.get("evidence_ids") or [],
                    "score_breakdown": c.get("score_breakdown") or {},
                }
                for c in claims
            ],
        },
        "narrative": {
            "templated_markdown": nar.get("templated_markdown"),
        },
    }
    return payload


def _validate_output(obj: Dict[str, Any]) -> Dict[str, Any]:
    # Ensure required keys exist (best-effort). Keep deterministic.
    out = dict(obj or {})
    out.setdefault("summary", "")
    out.setdefault("key_findings", [])
    out.setdefault("forecast_interpretation", "")
    out.setdefault("limitations", [])
    out.setdefault("recommended_next_steps", [])
    out.setdefault("open_questions", [])
    return out


def run_llm_analyst(
    *,
    run_path: Path,
    forecast_ctx: ForecastContext,
    llm_cfg: LLMConfig,
    user_question: Optional[str] = None,
) -> LLMReport:
    """Run the optional LLM Analyst and append results to run.json.

    - Read-only w.r.t. pipeline artifacts (evidence/claims/narrative).
    - Appends `artifacts.llm_report` and updates top-level `llm` audit block.
    """

    if llm_cfg.provider == "off":
        raise ValueError("LLM provider is OFF")
    if not llm_cfg.model:
        raise ValueError("LLM model is required")

    run_obj = load_json(run_path) or {}
    payload = _build_llm_payload(run_obj, forecast_ctx)
    input_hash = sha256_json(payload)
    payload_json = safe_json_dumps(payload)

    system = build_system_prompt()
    schema_hint = required_output_schema_hint()
    user_msg = build_user_message(payload_json=payload_json, user_question=user_question)
    prompt_parts = prompt_hash_inputs(system, schema_hint, user_msg)
    prompt_hashes = {k: sha256_text(v) for k, v in prompt_parts.items()}

    warnings: list[str] = []

    # Call provider
    if llm_cfg.provider == "ollama":
        out_obj = ollama_chat_json(
            base_url=llm_cfg.ollama_base_url,
            model=llm_cfg.model,
            system=system,
            user=user_msg,
            schema_hint=schema_hint,
            temperature=0.0,
        )
    elif llm_cfg.provider == "openai":
        if not llm_cfg.openai_api_key:
            raise ValueError("OPENAI_API_KEY missing")
        out_obj = openai_chat_json(
            base_url=llm_cfg.openai_base_url,
            api_key=llm_cfg.openai_api_key,
            model=llm_cfg.model,
            system=system,
            user=user_msg,
            schema_hint=schema_hint,
            temperature=0.0,
        )
    else:
        raise ValueError(f"Unsupported provider: {llm_cfg.provider}")

    out_obj = _validate_output(out_obj)

    # Produce a stable markdown surface (derived deterministically from JSON)
    # Keep this simple; do not depend on LLM formatting.
    md_lines = []
    if out_obj.get("summary"):
        md_lines.append("## LLM Analyst Summary")
        md_lines.append(out_obj.get("summary", ""))
        md_lines.append("")

    kf = out_obj.get("key_findings") or []
    if kf:
        md_lines.append("## Key Findings")
        for item in kf:
            txt = (item or {}).get("text", "").strip()
            cids = (item or {}).get("claim_ids") or []
            eids = (item or {}).get("evidence_ids") or []
            conf = (item or {}).get("confidence")
            cite = []
            if cids:
                cite.append("claims: " + ", ".join(cids))
            if eids:
                cite.append("evidence: " + ", ".join(eids))
            if conf:
                cite.append(f"confidence: {conf}")
            suffix = f" ({' | '.join(cite)})" if cite else ""
            if txt:
                md_lines.append(f"- {txt}{suffix}")
        md_lines.append("")

    if out_obj.get("forecast_interpretation"):
        md_lines.append("## Forecast Interpretation")
        md_lines.append(out_obj.get("forecast_interpretation", ""))
        md_lines.append("")

    lim = out_obj.get("limitations") or []
    if lim:
        md_lines.append("## Limitations")
        for s in lim:
            if str(s).strip():
                md_lines.append(f"- {str(s).strip()}")
        md_lines.append("")

    rec = out_obj.get("recommended_next_steps") or []
    if rec:
        md_lines.append("## Recommended Next Steps")
        for s in rec:
            if str(s).strip():
                md_lines.append(f"- {str(s).strip()}")
        md_lines.append("")

    oq = out_obj.get("open_questions") or []
    if oq:
        md_lines.append("## Open Questions")
        for s in oq:
            if str(s).strip():
                md_lines.append(f"- {str(s).strip()}")
        md_lines.append("")

    output_markdown = "\n".join(md_lines).strip() + "\n"
    output_markdown = clamp_text(output_markdown, llm_cfg.max_output_chars)

    rep = LLMReport(
        schema_version="0.9.0",
        provider=llm_cfg.provider,
        model=llm_cfg.model,
        created_at_utc=_utc_now_iso(),
        input_hash=input_hash,
        prompt_hashes=prompt_hashes,
        output_json=out_obj,
        output_markdown=output_markdown,
        warnings=warnings,
    )

    # Append to run.json (audit-friendly)
    artifacts = run_obj.get("artifacts") or {}
    artifacts["llm_report"] = {
        **asdict(rep),
        # keep output_markdown manageable (already clamped)
    }
    run_obj["artifacts"] = artifacts

    # Update top-level llm audit block (without deleting older fields)
    llm_block = run_obj.get("llm") or {}
    llm_block.update(
        {
            "provider": llm_cfg.provider,
            "model": llm_cfg.model,
            "temperature": 0.0,
            "input_hash": input_hash,
            "prompt_hashes": prompt_hashes,
            "created_at_utc": rep.created_at_utc,
        }
    )
    run_obj["llm"] = llm_block

    save_json(run_path, run_obj)

    return rep
