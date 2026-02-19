from __future__ import annotations

from typing import Dict


def build_system_prompt() -> str:
    """Hard guardrails.

    The model MUST:
      - Use only the provided JSON inputs.
      - Cite claim_id/evidence_id for any factual statement.
      - Avoid causal language unless explicitly supported by inputs.
      - If insufficient evidence, say so explicitly.

    We keep this short, stable, and provider-agnostic.
    """

    return (
        "You are an environmental data analyst writing a careful, audit-ready report. "
        "Use ONLY the provided JSON input. Do NOT browse the web. Do NOT assume facts not present. "
        "Every non-trivial statement must cite claim_id(s) and/or evidence_id(s). "
        "If evidence is insufficient, say 'Insufficient evidence' and list what is missing. "
        "Avoid strong causal claims (e.g., 'causes', 'due to') unless the input explicitly supports them. "
        "Return a single JSON object matching the required schema."
    )


def required_output_schema_hint() -> str:
    """A compact schema description to steer JSON output.

    Keep it deterministic: fixed keys, simple types.
    """

    return (
        "Output JSON schema: {"
        "\n  'summary': str,"
        "\n  'key_findings': [ {'text': str, 'claim_ids': [str], 'evidence_ids': [str], 'confidence': 'LOW|MED|HIGH'} ],"
        "\n  'forecast_interpretation': str,"
        "\n  'limitations': [str],"
        "\n  'recommended_next_steps': [str],"
        "\n  'open_questions': [str]"
        "\n}"
    )


def build_user_message(payload_json: str, user_question: str | None) -> str:
    q = (user_question or "").strip()
    if q:
        return (
            "User question (optional focus, not a source of facts):\n" + q + "\n\n" +
            "Input JSON (authoritative for facts):\n" + payload_json
        )
    return "Input JSON (authoritative for facts):\n" + payload_json


def prompt_hash_inputs(system: str, schema_hint: str, user: str) -> Dict[str, str]:
    return {
        "system": system,
        "schema_hint": schema_hint,
        "user": user,
    }
