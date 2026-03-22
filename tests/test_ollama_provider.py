from __future__ import annotations

import requests

from core.llm_analysis.llm_agent.models import LLMConfig
from core.llm_analysis.llm_agent.providers.ollama import ollama_chat_json, probe_ollama_catalog


class _Response:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError(f"HTTP {self.status_code}")
            err.response = self
            raise err

    def json(self):
        return self._payload


def test_probe_ollama_catalog_reads_installed_models(monkeypatch):
    def _fake_get(url: str, timeout: int):
        assert url == "http://localhost:11434/api/tags"
        assert timeout == 5
        return _Response({
            "models": [
                {"model": "gemma3:1b"},
                {"name": "llama3.2"},
            ]
        })

    monkeypatch.setattr(requests, "get", _fake_get)
    catalog = probe_ollama_catalog("http://localhost:11434", timeout_s=5)

    assert catalog.available is True
    assert catalog.models == ["gemma3:1b", "llama3.2"]
    assert "2 model(s)" in catalog.message


def test_ollama_chat_json_surfaces_timeout_with_clear_message(monkeypatch):
    def _fake_post(url: str, json: dict, timeout: int):
        raise requests.Timeout("timed out")

    monkeypatch.setattr(requests, "post", _fake_post)

    try:
        ollama_chat_json(
            base_url="http://localhost:11434",
            model="llama3.2",
            system="sys",
            user="user",
            schema_hint="hint",
            timeout_s=17,
        )
    except TimeoutError as exc:
        assert "17s" in str(exc)
        assert "/api/chat" in str(exc)
    else:
        raise AssertionError("Expected TimeoutError")


def test_llm_config_reads_ollama_timeout_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_TIMEOUT_S", "120")

    cfg = LLMConfig.from_env(provider="ollama", model="gemma3:1b")

    assert cfg.ollama_base_url == "http://localhost:11434"
    assert cfg.ollama_timeout_s == 120
