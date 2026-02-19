from __future__ import annotations

import json
from typing import Any, Dict, List

import requests


def openai_chat_json(
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    schema_hint: str,
    temperature: float = 0.0,
    timeout_s: int = 60,
) -> Dict[str, Any]:
    """Call OpenAI Chat Completions-compatible endpoint and parse JSON.

    Note: we avoid SDK dependencies to keep the project lightweight.
    Users can override OPENAI_BASE_URL if their endpoint differs.
    """

    base_url = (base_url or "https://api.openai.com").rstrip("/")
    url = f"{base_url}/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system},
        {"role": "system", "content": schema_hint},
        {"role": "user", "content": user},
    ]
    payload = {
        "model": model,
        "temperature": float(temperature),
        "messages": messages,
        # Nudge: request JSON. Some models respect this without response_format.
        "response_format": {"type": "json_object"},
    }

    r = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
    r.raise_for_status()
    obj = r.json()

    content = (((obj.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    try:
        return json.loads(content)
    except Exception:
        return {
            "summary": "LLM output was not valid JSON.",
            "key_findings": [],
            "forecast_interpretation": "",
            "limitations": ["invalid_json_output"],
            "recommended_next_steps": [],
            "open_questions": [],
            "_raw": content,
        }
