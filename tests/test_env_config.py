from __future__ import annotations

from pathlib import Path

from core.config.env import get_runtime_settings, load_project_env


def test_load_project_env_parses_inline_comments(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "AUTH_ADMIN_RESET_PASSWORD=Reset-From-Env # keep comment out\n"
        "PLAYGROUND_REPORT_TRUNCATION_RATIO=0.75\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("AUTH_ADMIN_RESET_PASSWORD", raising=False)
    monkeypatch.delenv("PLAYGROUND_REPORT_TRUNCATION_RATIO", raising=False)
    load_project_env.cache_clear()
    get_runtime_settings.cache_clear()

    loaded = load_project_env(env_path, override=True)
    settings = get_runtime_settings()

    assert loaded == Path(env_path)
    assert settings.auth_admin_reset_password == "Reset-From-Env"
    assert settings.playground_report_truncation_ratio == 0.75


def test_runtime_settings_clamps_ratio(monkeypatch):
    monkeypatch.setenv("PLAYGROUND_REPORT_TRUNCATION_RATIO", "9.0")
    load_project_env.cache_clear()
    get_runtime_settings.cache_clear()

    settings = get_runtime_settings()

    assert settings.playground_report_truncation_ratio == 1.0
