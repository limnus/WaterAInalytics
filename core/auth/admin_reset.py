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

from core.auth.storage import DEFAULT_DB_PATH, ensure_default_admin, set_password, DEFAULT_ADMIN_USERNAME


def main() -> int:
    info = ensure_default_admin(db_path=DEFAULT_DB_PATH)
    if info.get("created"):
        print(f"[OK] Admin created: {info['username']}")
        print(f"[IMPORTANT] Initial password: {info['initial_password']}")
        print("Please log in and change it immediately.")
        return 0

    new_pw = "Admin-Reset-1234"
    set_password(DEFAULT_ADMIN_USERNAME, new_pw, db_path=DEFAULT_DB_PATH)
    print("[OK] Admin password reset.")
    print(f"[IMPORTANT] New password: {new_pw}")
    print("Please log in and change it immediately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
