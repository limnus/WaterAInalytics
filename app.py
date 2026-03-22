"""WaterWatch — main Streamlit app entry point."""

import os

from core.config.env import get_runtime_settings, load_project_env

load_project_env()

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
from core.ui.plot_timeseries import render_plot_timeseries
from core.ui.forecasting import render_forecasting
from core.ui.agentic_analysis import render_agentic_analysis
from core.ui.admin_models import render_admin_models
from core.ui.admin_users import render_admin_users

# ---------------------------------
# Locale bootstrap from .config/lang.txt
# ---------------------------------
LANG_FILE = os.path.join(".config", "lang.txt")
VALID_LOCALES = {"en", "fr", "pt_br"}


def load_initial_locale() -> None:
    """
    Define st.session_state['locale'] com base em .config/lang.txt (se existir)
    ou 'en' como fallback. Sempre toma o arquivo como fonte da verdade.
    """
    code = None

    # Tenta ler do arquivo .config/lang.txt
    try:
        with open(LANG_FILE, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if raw in VALID_LOCALES:
            code = raw
    except FileNotFoundError:
        pass
    except Exception:
        # qualquer erro de leitura → ignora e cai no fallback
        pass

    if code is None:
        code = "en"

    st.session_state["locale"] = code


# Inicializa session_state primeiro (para não sobrescrever depois o locale)
init_session_state()

# Em seguida, aplica o locale vindo do arquivo (login ou escolha anterior)
load_initial_locale()

# Agora carrega strings já no locale correto
S = get_strings()

st.set_page_config(
    page_title=f"{S.APP_TITLE} — {APP_VERSION}",
    page_icon="assets/brand/favicon_32x32.png",
    layout="wide",
)

# Runtime settings
RUNTIME_SETTINGS = get_runtime_settings()

# Garante admin padrão
_ = ensure_default_admin(db_path=DEFAULT_DB_PATH)

# Se logado, verifica timeout
if is_logged_in() and session_expired(timeout_minutes=RUNTIME_SETTINGS.session_timeout_minutes):
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

S = get_strings()  # recarrega strings se necessário (já com locale correto em session_state)

# Sidebar sessão
# Sidebar icon
icon_path = "assets/brand/sidebar_icon.png"
try:
    st.sidebar.image(icon_path, width=64)
    # st.sidebar.markdown("")   # 1 linha vazia
except Exception:
    pass

# Título da app
st.sidebar.title(f"{S.APP_TITLE}\n{APP_VERSION}")
with st.sidebar.expander("Session", expanded=True):
    st.markdown(f"**User:** `{user}`")
    st.markdown(f"**Role:** `{role}`")
    if st.button(S.BTN_LOGOUT):
        logout()
        st.rerun()

# ---------------------------------
# Language selector no sidebar
# ---------------------------------
st.sidebar.markdown("---")

# Opções com bandeira
langs = [
    ("🇺🇸 English", "en"),
    ("🇫🇷 Français", "fr"),
    ("🇧🇷 Português (BR)", "pt_br"),
]

current_locale = st.session_state.get("locale", "en")

labels = [label for (label, code) in langs]
codes = [code for (label, code) in langs]
label_to_code = {label: code for (label, code) in langs}
code_to_index = {code: i for i, code in enumerate(codes)}

current_index = code_to_index.get(current_locale, 0)

choice = st.sidebar.radio("Language", labels, index=current_index)

new_locale = label_to_code[choice]

if new_locale != current_locale:
    # Atualiza em memória
    st.session_state["locale"] = new_locale

    # Persiste em .config/lang.txt
    os.makedirs(os.path.dirname(LANG_FILE), exist_ok=True)
    try:
        with open(LANG_FILE, "w", encoding="utf-8") as f:
            f.write(new_locale + "\n")
    except Exception as e:
        st.warning(f"Could not persist language setting to {LANG_FILE}: {e}")

    # Recarrega a app para aplicar as novas strings
    st.rerun()

# ---------------------------------
# Conteúdo principal
# ---------------------------------
st.title(f"{S.APP_TITLE} — {APP_VERSION}")

# Abas principais
tabs = st.tabs(["Explorer & Map", "Plot Time Series", "Forecasting", "Agentic AI Forecasting Analysis", "Admin Panel"])

with tabs[0]:
    render_explorer_map(role=role)

with tabs[1]:
    render_plot_timeseries(role=role)

with tabs[2]:
    render_forecasting(role=role)

with tabs[3]:
    render_agentic_analysis(role=role)

with tabs[4]:
    admin_tabs = st.tabs(["Admin Users", "Admin Models"])
    with admin_tabs[0]:
        render_admin_users(role=role, db_path=DEFAULT_DB_PATH)
    with admin_tabs[1]:
        render_admin_models(role=role)
