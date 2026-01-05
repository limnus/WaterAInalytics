"""App Foundation — Streamlit entry point (template)."""

import streamlit as st

from core.version import APP_VERSION
from core.ui.strings.loader import get_strings
from core.auth.storage import ensure_default_admin, DEFAULT_DB_PATH
from core.auth.session import (
    init_session_state,
    is_logged_in,
    session_expired,
    logout,
    update_last_activity,
    get_current_user,
    get_current_role,
)
from core.auth.login_ui import render_login

S = get_strings()
st.set_page_config(page_title=f"{S.APP_TITLE} — {APP_VERSION}", layout="wide")

# Ensure admin exists
_ = ensure_default_admin(db_path=DEFAULT_DB_PATH)

init_session_state()

# If logged in, enforce timeout
if is_logged_in() and session_expired():
    S = get_strings()
    st.warning(S.INFO_SESSION_EXPIRED)
    logout()

# Login gate
if not is_logged_in():
    render_login(db_path=DEFAULT_DB_PATH)
    st.stop()

update_last_activity()
user = get_current_user()
role = get_current_role()

S = get_strings()

# Sidebar session box
st.sidebar.title(f"{S.APP_TITLE}\n{APP_VERSION}")
with st.sidebar.expander("Session", expanded=True):
    st.markdown(f"**User:** `{user}`")
    st.markdown(f"**Role:** `{role}`")
    if st.button(S.BTN_LOGOUT, use_container_width=True):
        logout()
        st.rerun()

st.title(f"{S.APP_TITLE} — {APP_VERSION}")
st.success(f"Authenticated session active: {user} ({role})")
st.info("Replace this placeholder with your app's Explorer / Admin / Playground routes.")
