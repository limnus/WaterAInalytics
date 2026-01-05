"""core/auth/session.py

Streamlit session management (generic).
- Authenticated sessions (Admin/User) + anonymous Playground mode
- Inactivity timeout

Self-test:
  python -m core.auth.session
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional


KEY_LOGGED_IN = "auth_logged_in"
KEY_USERNAME = "auth_username"
KEY_ROLE = "auth_role"
KEY_LAST_ACTIVITY_UTC = "auth_last_activity_utc"

PLAYGROUND_USERNAME = "Playground"
PLAYGROUND_ROLE = "Playground"

DEFAULT_TIMEOUT_MINUTES = 60


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def init_session_state() -> None:
    import streamlit as st
    if KEY_LOGGED_IN not in st.session_state:
        st.session_state[KEY_LOGGED_IN] = False
    if KEY_USERNAME not in st.session_state:
        st.session_state[KEY_USERNAME] = None
    if KEY_ROLE not in st.session_state:
        st.session_state[KEY_ROLE] = None
    if KEY_LAST_ACTIVITY_UTC not in st.session_state:
        st.session_state[KEY_LAST_ACTIVITY_UTC] = None


def login(username: str, role: str) -> None:
    import streamlit as st
    st.session_state[KEY_LOGGED_IN] = True
    st.session_state[KEY_USERNAME] = username
    st.session_state[KEY_ROLE] = role
    st.session_state[KEY_LAST_ACTIVITY_UTC] = _utc_now().isoformat()


def login_playground() -> None:
    login(PLAYGROUND_USERNAME, PLAYGROUND_ROLE)


def logout() -> None:
    import streamlit as st
    st.session_state[KEY_LOGGED_IN] = False
    st.session_state[KEY_USERNAME] = None
    st.session_state[KEY_ROLE] = None
    st.session_state[KEY_LAST_ACTIVITY_UTC] = None


def is_logged_in() -> bool:
    import streamlit as st
    return bool(st.session_state.get(KEY_LOGGED_IN, False))


def get_current_user() -> Optional[str]:
    import streamlit as st
    return st.session_state.get(KEY_USERNAME)


def get_current_role() -> Optional[str]:
    import streamlit as st
    return st.session_state.get(KEY_ROLE)


def update_last_activity() -> None:
    import streamlit as st
    st.session_state[KEY_LAST_ACTIVITY_UTC] = _utc_now().isoformat()


def session_expired(timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES) -> bool:
    import streamlit as st
    last_s = st.session_state.get(KEY_LAST_ACTIVITY_UTC)
    if not last_s:
        return False
    try:
        last = datetime.fromisoformat(last_s)
    except Exception:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    last = last.astimezone(timezone.utc)
    return (_utc_now() - last) > timedelta(minutes=timeout_minutes)


def _self_test() -> int:
    print("Running core/auth/session.py self-test...")
    now = _utc_now()
    last_ok = (now - timedelta(minutes=DEFAULT_TIMEOUT_MINUTES - 1)).isoformat()
    last_bad = (now - timedelta(minutes=DEFAULT_TIMEOUT_MINUTES + 1)).isoformat()

    def _expired(last_s: str, timeout: int) -> bool:
        last = datetime.fromisoformat(last_s)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        last = last.astimezone(timezone.utc)
        return (_utc_now() - last) > timedelta(minutes=timeout)

    assert _expired(last_ok, DEFAULT_TIMEOUT_MINUTES) is False
    assert _expired(last_bad, DEFAULT_TIMEOUT_MINUTES) is True

    print("Self-test PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
