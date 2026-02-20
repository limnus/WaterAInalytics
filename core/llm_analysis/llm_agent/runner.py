from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.llm_analysis.cache.store import load_json, save_json
from core.llm_analysis.forecast_integration.models import ForecastContext

from .models import LLMConfig, LLMReport
from .prompts import build_system_prompt, required_output_schema_hint, build_user_message, prompt_hash_inputs
from .providers import ollama_chat_json, openai_chat_json
from .utils import sha256_json, sha256_text, safe_json_dumps, clamp_text
from .validator import validate_llm_report
from .renderer import render_markdown
from .deterministic_report import build_deterministic_llm_report


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
                if isinstance(s, dict)
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
                if isinstance(c, dict)
            ],
        },
        "narrative": {
            "templated_markdown": nar.get("templated_markdown"),
        },
    }
    return payload


def _normalize_v091(out_obj: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(out_obj or {})
    if "executive_summary" not in out and "summary" in out:
        out["executive_summary"] = out.get("summary") or ""

    out.setdefault("executive_summary", "")
    out.setdefault("key_findings", [])
    out.setdefault("forecast_interpretation", [])
    out.setdefault("limitations", [])
    out.setdefault("open_questions", [])

    def _ensure_ids(items, prefix):
        out_items = []
        for i, it in enumerate(items or []):
            if not isinstance(it, dict):
                continue
            it = dict(it)
            it.setdefault("id", f"{prefix}_{i+1:03d}")
            it.setdefault("text", "")
            it.setdefault("claim_ids", [])
            it.setdefault("evidence_ids", [])
            if prefix in ("kf", "fi"):
                it.setdefault("confidence", "LOW")
            out_items.append(it)
        return out_items

    out["key_findings"] = _ensure_ids(out.get("key_findings"), "kf")
    out["forecast_interpretation"] = _ensure_ids(out.get("forecast_interpretation"), "fi")
    out["limitations"] = _ensure_ids(out.get("limitations"), "lim")

    oq2 = []
    for i, it in enumerate(out.get("open_questions") or []):
        if not isinstance(it, dict):
            continue
        it = dict(it)
        it.setdefault("id", f"q_{i+1:03d}")
        it.setdefault("text", "")
        oq2.append(it)
    out["open_questions"] = oq2

    return out


def _canon_one(s: str, *, kind: str) -> str:
    s = s.strip()
    if kind == "ev":
        m = re.match(r"^ev_([0-9a-f]{11})$", s)
        if m:
            return "ev_0" + m.group(1)
    if kind == "cl":
        m = re.match(r"^cl_([0-9a-f]{11})$", s)
        if m:
            return "cl_0" + m.group(1)
    return s


def _canon_id_list(ids: Any, *, kind: str) -> list[str]:
    out: list[str] = []
    if not isinstance(ids, list):
        return out
    for x in ids:
        if isinstance(x, str):
            out.append(_canon_one(x, kind=kind))
    return out


def _normalize_ids_in_report(report: Dict[str, Any]) -> None:
    for sec in ("key_findings", "forecast_interpretation", "limitations"):
        items = report.get(sec) or []
        for it in items:
            if not isinstance(it, dict):
                continue
            it["claim_ids"] = _canon_id_list(it.get("claim_ids") or [], kind="cl")
            it["evidence_ids"] = _canon_id_list(it.get("evidence_ids") or [], kind="ev")


def run_llm_analyst(
    *,
    run_path: Path,
    forecast_ctx: ForecastContext,
    llm_cfg: LLMConfig,
    user_question: Optional[str] = None,
) -> LLMReport:
    if llm_cfg.provider != "off" and (not llm_cfg.model):
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

    # ---------------------------------------------------------
    # Provider dispatch (single source of truth)
    # ---------------------------------------------------------

    if llm_cfg.provider == "off":
        # Deterministic analyst (no external LLM call)
        from .deterministic_report import build_deterministic_llm_report

        artifacts = (run_obj.get("artifacts") or {})

        # claims
        claims_obj = artifacts.get("claims")
        if isinstance(claims_obj, dict):
            claims = claims_obj.get("items") or []
        elif isinstance(claims_obj, list):
            claims = claims_obj
        else:
            claims = []

        # evidence
        evidence_obj = artifacts.get("evidence")
        if isinstance(evidence_obj, dict):
            evidence = evidence_obj.get("sources") or []
        elif isinstance(evidence_obj, list):
            evidence = evidence_obj
        else:
            evidence = []

        # context consistency
        context_consistency = artifacts.get("context_consistency")
        if not isinstance(context_consistency, dict):
            context_consistency = None

        report_obj = build_deterministic_llm_report(
            forecast_ctx=forecast_ctx,
            claims=[c for c in claims if isinstance(c, dict)],
            evidence=[e for e in evidence if isinstance(e, dict)],
            context_consistency=context_consistency,
            user_question=user_question,
        )

        provider_used = "off"
        model_used = "deterministic"

    else:
        # External LLM call (Ollama / OpenAI)
        if llm_cfg.provider == "ollama":
            report_obj = ollama_chat_json(
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

            report_obj = openai_chat_json(
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

        provider_used = llm_cfg.provider
        model_used = llm_cfg.model
        
    # Normalize to v0.9.1 shape (works for deterministic too)
    out_obj = _normalize_v091(report_obj)

    report = {
        "llm_report_schema": "0.9.1",
        "provider": provider_used,
        "model": model_used,
        "created_at_utc": _utc_now_iso(),
        "input_hash": input_hash,
        "prompt_hashes": prompt_hashes,
        "executive_summary": clamp_text(out_obj.get("executive_summary", ""), llm_cfg.max_output_chars),
        "key_findings": out_obj.get("key_findings") or [],
        "forecast_interpretation": out_obj.get("forecast_interpretation") or [],
        "limitations": out_obj.get("limitations") or [],
        "open_questions": out_obj.get("open_questions") or [],
    }

    _normalize_ids_in_report(report)

    artifacts = (run_obj.get("artifacts") or {})
    claims = artifacts.get("claims")
    evidence = artifacts.get("evidence")

    claims_list = (claims.get("items") if isinstance(claims, dict) else claims) or []
    evidence_list = (evidence.get("sources") if isinstance(evidence, dict) else evidence) or []

    report["validation"] = validate_llm_report(
        report,
        claims=[c for c in claims_list if isinstance(c, dict)],
        evidence=[e for e in evidence_list if isinstance(e, dict)],
    )

    report["rendered_markdown"] = render_markdown(report)

    artifacts2 = dict(artifacts)
    artifacts2["llm_report"] = report
    run_obj["artifacts"] = artifacts2

    run_obj["llm"] = {
        "enabled": True,
        "provider": provider_used,
        "model": model_used,
        "created_at_utc": report["created_at_utc"],
        "input_hash": input_hash,
        "prompt_hashes": prompt_hashes,
        "schema": "0.9.1",
        "warnings": warnings,
    }

    save_json(run_path, run_obj)

    return LLMReport(
        schema_version="0.9.1",
        provider=provider_used,
        model=model_used,
        created_at_utc=report["created_at_utc"],
        input_hash=input_hash,
        prompt_hashes=prompt_hashes,
        output_json=report,
        output_markdown=report["rendered_markdown"],
        warnings=warnings,
    )
