from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List

import requests


@dataclass(frozen=True)
class OllamaCatalog:
    base_url: str
    available: bool
    models: List[str]
    message: str


def _normalize_base_url(base_url: str) -> str:
    return (base_url or "http://localhost:11434").rstrip("/")


def _friendly_request_error(exc: Exception, *, url: str, timeout_s: int) -> RuntimeError:
    if isinstance(exc, requests.Timeout):
        return TimeoutError(f"Ollama request timed out after {timeout_s}s at {url}.")
    if isinstance(exc, requests.ConnectionError):
        return ConnectionError(f"Could not connect to Ollama at {url}. Is the Ollama service running?")
    if isinstance(exc, requests.HTTPError):
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", None)
        if status == 404:
            return RuntimeError(f"Ollama endpoint was not found at {url} (HTTP 404). Check the base URL and Ollama version.")
        return RuntimeError(f"Ollama request failed with HTTP {status} at {url}.")
    return RuntimeError(f"Ollama request failed at {url}: {exc}")


def probe_ollama_catalog(base_url: str, timeout_s: int = 5) -> OllamaCatalog:
    base = _normalize_base_url(base_url)
    url = f"{base}/api/tags"
    try:
        response = requests.get(url, timeout=timeout_s)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return OllamaCatalog(
            base_url=base,
            available=False,
            models=[],
            message=str(_friendly_request_error(exc, url=url, timeout_s=timeout_s)),
        )

    models: List[str] = []
    for item in payload.get("models") or []:
        if not isinstance(item, dict):
            continue
        name = (item.get("model") or item.get("name") or "").strip()
        if name and name not in models:
            models.append(name)

    if models:
        message = f"Connected to Ollama at {base}. {len(models)} model(s) detected."
    else:
        message = f"Connected to Ollama at {base}, but no installed models were reported."

    return OllamaCatalog(
        base_url=base,
        available=True,
        models=models,
        message=message,
    )


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

    base = _normalize_base_url(base_url)
    url = f"{base}/api/chat"

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

    try:
        r = requests.post(url, json=payload, timeout=timeout_s)
        r.raise_for_status()
        obj = r.json()
    except Exception as exc:
        raise _friendly_request_error(exc, url=url, timeout_s=timeout_s) from exc

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
