"""core/auth/storage.py

Generic SQLite-backed authentication store (MVP).

- Default admin user: "Admin"
- Non-admin usernames must be emails (default policy)
- Password hashing: Argon2id (argon2-cffi)
- Basic lockout policy

Self-test:
  python -m core.auth.storage
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError


DEFAULT_DB_PATH = str(Path("data") / "auth.db")
DEFAULT_ADMIN_USERNAME = "Admin"

ROLES = {"Admin", "User"}

MAX_FAILED_ATTEMPTS = 8
LOCKOUT_MINUTES = 15

REQUIRE_EMAIL_FOR_NON_ADMIN = True
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

PH = PasswordHasher()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dt_to_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _iso_to_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ensure_parent_dir(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def _validate_username(username: str) -> None:
    if not username or not isinstance(username, str):
        raise ValueError("Username must be a non-empty string.")
    u = username.strip()
    if u == DEFAULT_ADMIN_USERNAME:
        return
    if REQUIRE_EMAIL_FOR_NON_ADMIN and not EMAIL_RE.match(u):
        raise ValueError("Non-admin usernames must be valid email addresses.")


def _validate_role(role: str) -> None:
    if role not in ROLES:
        raise ValueError(f"Invalid role '{role}'. Must be one of: {sorted(ROLES)}")


def _connect(db_path: str) -> sqlite3.Connection:
    _ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,

    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,

    last_login_utc TEXT,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);
"""


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


def ensure_default_admin(db_path: str = DEFAULT_DB_PATH, initial_password: Optional[str] = None) -> Dict[str, Any]:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT username FROM users WHERE username = ?", (DEFAULT_ADMIN_USERNAME,)).fetchone()
        if row:
            return {"created": False, "username": DEFAULT_ADMIN_USERNAME}

        if initial_password is None:
            initial_password = f"Admin-{_utc_now().strftime('%Y%m%d%H%M%S')}"

        pw_hash = PH.hash(initial_password)
        now = _dt_to_iso(_utc_now())

        conn.execute(
            """
            INSERT INTO users (username, password_hash, role, is_active, created_at_utc, updated_at_utc)
            VALUES (?, ?, ?, 1, ?, ?)
            """,
            (DEFAULT_ADMIN_USERNAME, pw_hash, "Admin", now, now),
        )
        conn.commit()

        return {"created": True, "username": DEFAULT_ADMIN_USERNAME, "initial_password": initial_password}


def create_user(username: str, password: str, role: str = "User", db_path: str = DEFAULT_DB_PATH, is_active: bool = True) -> None:
    init_db(db_path)
    _validate_username(username)
    _validate_role(role)
    if not password:
        raise ValueError("Password must be non-empty.")

    pw_hash = PH.hash(password)
    now = _dt_to_iso(_utc_now())

    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO users (username, password_hash, role, is_active, created_at_utc, updated_at_utc)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (username.strip(), pw_hash, role, 1 if is_active else 0, now, now),
        )
        conn.commit()


def set_password(username: str, new_password: str, db_path: str = DEFAULT_DB_PATH) -> None:
    init_db(db_path)
    if not new_password:
        raise ValueError("New password must be non-empty.")
    pw_hash = PH.hash(new_password)
    now = _dt_to_iso(_utc_now())

    with _connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash = ?, updated_at_utc = ?, failed_attempts = 0, locked_until_utc = NULL WHERE username = ?",
            (pw_hash, now, username.strip()),
        )
        if cur.rowcount == 0:
            raise ValueError("User not found.")
        conn.commit()


def set_active(username: str, is_active: bool, db_path: str = DEFAULT_DB_PATH) -> None:
    init_db(db_path)
    now = _dt_to_iso(_utc_now())
    with _connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE users SET is_active = ?, updated_at_utc = ? WHERE username = ?",
            (1 if is_active else 0, now, username.strip()),
        )
        if cur.rowcount == 0:
            raise ValueError("User not found.")
        conn.commit()


@dataclass
class AuthResult:
    ok: bool
    username: Optional[str] = None
    role: Optional[str] = None
    reason: Optional[str] = None


def authenticate_user(username: str, password: str, db_path: str = DEFAULT_DB_PATH) -> AuthResult:
    init_db(db_path)
    u = (username or "").strip()
    if not u:
        return AuthResult(ok=False, reason="Missing username.")
    if not password:
        return AuthResult(ok=False, reason="Missing password.")

    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (u,)).fetchone()
        if not row:
            return AuthResult(ok=False, reason="Invalid credentials.")

        user = dict(row)
        if not bool(user["is_active"]):
            return AuthResult(ok=False, reason="Account is disabled.")

        locked_until = _iso_to_dt(user.get("locked_until_utc"))
        now = _utc_now()
        if locked_until and now < locked_until:
            return AuthResult(ok=False, reason="Account is temporarily locked due to failed attempts.")

        try:
            if not PH.verify(user["password_hash"], password):
                raise VerifyMismatchError()
        except VerifyMismatchError:
            failed = int(user.get("failed_attempts") or 0) + 1
            lock_until_iso = None
            if failed >= MAX_FAILED_ATTEMPTS:
                lock_until_iso = _dt_to_iso(now + timedelta(minutes=LOCKOUT_MINUTES))

            conn.execute(
                """
                UPDATE users
                SET failed_attempts = ?, locked_until_utc = COALESCE(?, locked_until_utc), updated_at_utc = ?
                WHERE username = ?
                """,
                (failed, lock_until_iso, _dt_to_iso(now), u),
            )
            conn.commit()
            return AuthResult(ok=False, reason="Invalid credentials.")

        conn.execute(
            """
            UPDATE users
            SET failed_attempts = 0,
                locked_until_utc = NULL,
                last_login_utc = ?,
                updated_at_utc = ?
            WHERE username = ?
            """,
            (_dt_to_iso(now), _dt_to_iso(now), u),
        )
        conn.commit()

        return AuthResult(ok=True, username=u, role=user["role"])


def _self_test() -> int:
    print("Running core/auth/storage.py self-test...")

    test_db = str(Path("data") / "auth_selftest.db")
    p = Path(test_db)
    if p.exists():
        p.unlink()

    init_db(test_db)
    admin = ensure_default_admin(test_db)
    assert admin["username"] == DEFAULT_ADMIN_USERNAME
    assert admin.get("initial_password")

    r = authenticate_user(DEFAULT_ADMIN_USERNAME, "wrong", test_db)
    assert not r.ok

    r = authenticate_user(DEFAULT_ADMIN_USERNAME, admin["initial_password"], test_db)
    assert r.ok and r.role == "Admin"

    create_user("user@example.com", "Passw0rd!", "User", test_db)
    r = authenticate_user("user@example.com", "Passw0rd!", test_db)
    assert r.ok and r.role == "User"

    try:
        create_user("not-an-email", "x", "User", test_db)
        raise AssertionError("Expected email validation to fail.")
    except ValueError:
        pass

    set_active("user@example.com", False, test_db)
    r = authenticate_user("user@example.com", "Passw0rd!", test_db)
    assert not r.ok

    print("Self-test PASSED.")
    try:
        p.unlink()
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
