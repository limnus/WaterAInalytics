"""core/rbac/permissions.py

RBAC scaffolding. Extend per app.

Self-test:
  python -m core.rbac.permissions
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Set


@dataclass(frozen=True)
class Permission:
    name: str


PERMISSIONS: Dict[str, Permission] = {
    "view_app": Permission("view_app"),
    "admin_panel": Permission("admin_panel"),
}

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "Admin": {"view_app", "admin_panel"},
    "User": {"view_app"},
    "Playground": {"view_app"},
}


def has_permission(role: str, permission_name: str) -> bool:
    return permission_name in ROLE_PERMISSIONS.get(role or "", set())


def _self_test() -> int:
    print("Running core/rbac/permissions.py self-test...")
    assert has_permission("Admin", "admin_panel") is True
    assert has_permission("User", "admin_panel") is False
    assert has_permission("Playground", "view_app") is True
    print("Self-test PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
