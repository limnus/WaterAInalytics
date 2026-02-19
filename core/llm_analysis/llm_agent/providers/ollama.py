from __future__ import annotations

import json
from typing import Any, Dict, List

import requests


def ollama_chat_json(
    base_url: str,
    model: str,
    system: str,
    user: str,
    schema_hint: str,
    temperature: float = 0.0,
    timeout_s: int = 60,
) -> Dict[str, Any]:
    """Call Ollama /api/chat and request JSON output.

    We keep `stream=False` for determinism in IO and simpler error handling.
    """

    base_url = (base_url or "http://localhost:11434").rstrip("/")
    url = f"{base_url}/api/chat"

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system},
        {"role": "system", "content": schema_hint},
        {"role": "user", "content": user},
    ]

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        # Ollama supports `format: json` to enforce JSON output in many models
        "format": "json",
        "options": {
            "temperature": float(temperature),
        },
    }

    r = requests.post(url, json=payload, timeout=timeout_s)
    r.raise_for_status()
    obj = r.json()

    # Typical response: {"message": {"role": "assistant", "content": "{...}"}, ...}
    content = ((obj.get("message") or {}).get("content") or "").strip()
    try:
        return json.loads(content)
    except Exception:
        # Last-resort: return raw
        return {
            "summary": "LLM output was not valid JSON.",
            "key_findings": [],
            "forecast_interpretation": "",
            "limitations": ["invalid_json_output"],
            "recommended_next_steps": [],
            "open_questions": [],
            "_raw": content,
        }
