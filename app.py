"""WaterWatch — main Streamlit app entry point."""

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
from core.ui.explorer_map import render_explorer_map  # ui está dentro de core

# Carrega strings (APP_TITLE já deve estar como "WaterWatch" nos arquivos de strings)
S = get_strings()

st.set_page_config(page_title=f"{S.APP_TITLE} — {APP_VERSION}", layout="wide")

# Garante admin padrão
_ = ensure_default_admin(db_path=DEFAULT_DB_PATH)

init_session_state()

# Se logado, verifica timeout
if is_logged_in() and session_expired():
    S = get_strings()
    st.warning(S.INFO_SESSION_EXPIRED)
    logout()

# Tela de login
if not is_logged_in():
    render_login(db_path=DEFAULT_DB_PATH)
    st.stop()

update_last_activity()
user = get_current_user()
role = get_current_role()

S = get_strings()  # recarrega strings se necessário

# Sidebar sessão
st.sidebar.title(f"{S.APP_TITLE}\n{APP_VERSION}")
with st.sidebar.expander("Session", expanded=True):
    st.markdown(f"**User:** `{user}`")
    st.markdown(f"**Role:** `{role}`")
    if st.button(S.BTN_LOGOUT, width="stretch"):
        logout()
        st.rerun()

st.title(f"{S.APP_TITLE} — {APP_VERSION}")

# Abas principais
tabs = st.tabs(["Explorer & Map", "Plot Time Series", "Admin Panel"])

with tabs[0]:
    render_explorer_map(role=role)

with tabs[1]:
    st.info(
        "Time series plotting will be implemented here. "
        "This tab will use the selected stations from 'Explorer & Map' "
        "to fetch and display 1, 2, 3, 5, and 7-day windows."
    )

with tabs[2]:
    st.info("Admin panel not implemented yet.")

