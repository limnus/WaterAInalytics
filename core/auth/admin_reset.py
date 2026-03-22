"""core/auth/admin_reset.py

Utility to ensure Admin exists and reset its password.

Preferred:
  python -m core.auth.admin_reset
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config.env import get_runtime_settings, load_project_env

load_project_env()

from core.auth.storage import DEFAULT_ADMIN_USERNAME, DEFAULT_DB_PATH, ensure_default_admin, set_password


def main() -> int:
    info = ensure_default_admin(db_path=DEFAULT_DB_PATH)
    if info.get("created"):
        print(f"[OK] Admin created: {info['username']}")
        print(f"[IMPORTANT] Initial password: {info['initial_password']}")
        print("Please log in and change it immediately.")
        return 0

    settings = get_runtime_settings()
    new_pw = settings.auth_admin_reset_password or settings.auth_admin_initial_password
    if not new_pw:
        print("[ERROR] Admin reset password is not configured.")
        print("Set AUTH_ADMIN_RESET_PASSWORD in .env (preferred) or in the process environment.")
        return 2

    set_password(DEFAULT_ADMIN_USERNAME, new_pw, db_path=DEFAULT_DB_PATH)
    print("[OK] Admin password reset.")
    print(f"[IMPORTANT] New password: {new_pw}")
    print("Please log in and change it immediately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
