from __future__ import annotations

import pytest

from core.auth.storage import (
    DEFAULT_ADMIN_USERNAME,
    authenticate_user,
    create_user,
    delete_user,
    ensure_default_admin,
    list_users,
    set_active,
)
from core.config.env import get_runtime_settings, load_project_env


def test_ensure_default_admin_uses_env_initial_password(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    monkeypatch.setenv("AUTH_ADMIN_INITIAL_PASSWORD", "Admin-Env-Init-123")
    load_project_env.cache_clear()
    get_runtime_settings.cache_clear()

    info = ensure_default_admin(db_path=str(db_path))
    auth = authenticate_user(DEFAULT_ADMIN_USERNAME, "Admin-Env-Init-123", db_path=str(db_path))

    assert info["created"] is True
    assert info["initial_password"] == "Admin-Env-Init-123"
    assert auth.ok is True
    assert auth.role == "Admin"


def test_list_and_delete_user(tmp_path):
    db_path = tmp_path / "auth.db"
    ensure_default_admin(db_path=str(db_path), initial_password="Admin-123")
    create_user("user@example.com", "Passw0rd!", db_path=str(db_path))

    before = list_users(db_path=str(db_path))
    delete_user("user@example.com", db_path=str(db_path))
    after = list_users(db_path=str(db_path))

    assert any(u["username"] == "user@example.com" for u in before)
    assert not any(u["username"] == "user@example.com" for u in after)


def test_default_admin_cannot_be_deleted_or_deactivated(tmp_path):
    db_path = tmp_path / "auth.db"
    ensure_default_admin(db_path=str(db_path), initial_password="Admin-123")

    with pytest.raises(ValueError):
        delete_user(DEFAULT_ADMIN_USERNAME, db_path=str(db_path))

    with pytest.raises(ValueError):
        set_active(DEFAULT_ADMIN_USERNAME, False, db_path=str(db_path))
