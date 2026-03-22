from __future__ import annotations

from core.config.env import get_runtime_settings, load_project_env
from core.ui.playground_output import apply_output_policy


def test_apply_output_policy_truncates_for_playground(monkeypatch):
    monkeypatch.setenv("PLAYGROUND_REPORT_TRUNCATION_RATIO", "0.60")
    load_project_env.cache_clear()
    get_runtime_settings.cache_clear()

    content = "A" * 100
    result = apply_output_policy(content=content, role="Playground")

    assert result.truncated is True
    assert "Playground limitation" in result.notice
    assert len(result.content) > 60
    assert result.content.startswith("A" * 60)


def test_apply_output_policy_keeps_full_output_for_user(monkeypatch):
    monkeypatch.setenv("PLAYGROUND_REPORT_TRUNCATION_RATIO", "0.60")
    load_project_env.cache_clear()
    get_runtime_settings.cache_clear()

    content = "Full output"
    result = apply_output_policy(content=content, role="User")

    assert result.truncated is False
    assert result.content == content
