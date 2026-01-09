"""
core/auth/login_ui.py

Login UI for WaterWatch NA.
- Language selector with persistence (session + .config)
- Centered layout with gutters
- Supports authenticated login and anonymous Playground mode
"""

from __future__ import annotations

import streamlit as st

from core.auth.storage import authenticate_user, DEFAULT_DB_PATH
from core.auth.session import (
    init_session_state,
    login,
    login_playground,
    update_last_activity,
)
from core.ui.strings.loader import (
    get_strings,
    set_lang,
    SUPPORTED,
)


def render_login(db_path: str = DEFAULT_DB_PATH) -> None:
    """
    Renders the login screen.
    On success, sets session auth state.
    Caller should stop() if still not logged in.
    """
    init_session_state()

    # -------------------------
    # Language handling
    # -------------------------
    # Aqui usamos SEMPRE st.session_state["locale"] como fonte de verdade,
    # em alinhamento com o app.py (que já leu .config/lang.txt).
    if "locale" not in st.session_state:
        st.session_state["locale"] = "en"

    lang_codes = list(SUPPORTED.keys())
    current_lang = st.session_state["locale"]
    if current_lang not in lang_codes:
        current_lang = "en"

    current_idx = lang_codes.index(current_lang)

    # -------------------------
    # Global page gutters
    # -------------------------

    # ---- Language selector (top-right, subtle) ----
    l1, l2 = st.columns([6, 1])
    with l2:
        selected_lang = st.selectbox(
            "Language",
            options=lang_codes,
            index=current_idx,
            format_func=lambda c: SUPPORTED[c][0],
            key="login_language_select",
        )
        if selected_lang != current_lang:
            # Atualiza a mesma chave usada pelo app principal
            st.session_state["locale"] = selected_lang
            # E deixa o loader sincronizar com .config/lang.txt
            set_lang(selected_lang)
            st.rerun()

    g1, center, g2 = st.columns([1, 2, 1])

    with center:
        # Load strings AFTER language is resolved
        S = get_strings()

        # -------------------------
        # Banner (Water AInalytics US)
        # -------------------------
        # Caminho relativo a partir da raiz onde o app é executado (app.py)
        banner_path = "assets/brand/login_banner.png"
        try:
            st.image(banner_path, width="stretch")
        except Exception:
            # Se o arquivo não existir ou der erro, simplesmente não quebra o login.
            pass

        # -------------------------
        # Titles
        # -------------------------
        st.title(S.APP_TITLE)
        st.subheader(S.LOGIN_TITLE)
        st.caption(S.LOGIN_SUBTITLE)

        # -------------------------
        # Login box
        # -------------------------
        container = st.container(border=True)

        with container:
            with st.form("login_form", clear_on_submit=False):
                username = st.text_input(
                    S.USERNAME_LABEL,
                    value="",
                    autocomplete="username",
                )
                password = st.text_input(
                    S.PASSWORD_LABEL,
                    value="",
                    type="password",
                    autocomplete="current-password",
                )

                # Narrow, centered login button
                b1, b2, b3 = st.columns([1, 2, 1])
                with b2:
                    submitted = st.form_submit_button(
                        S.BTN_LOGIN,
                        use_container_width=True,
                    )

                if submitted:
                    res = authenticate_user(
                        username=username,
                        password=password,
                        db_path=db_path,
                    )

                    if res.ok:
                        login(res.username or username, res.role or "User")
                        update_last_activity()
                        st.success(S.SUCCESS_LOGIN)
                        st.rerun()
                    else:
                        msg = (res.reason or "").lower()
                        if "locked" in msg:
                            st.error(S.ERR_ACCOUNT_LOCKED)
                        elif "disabled" in msg:
                            st.error(S.ERR_ACCOUNT_DISABLED)
                        else:
                            st.error(S.ERR_INVALID_CREDENTIALS)

            st.divider()

            # -------------------------
            # Playground button
            # -------------------------
            p1, p2, p3 = st.columns([1, 5, 1])
            with p2:
                if st.button(
                    S.BTN_PLAYGROUND,
                    help=S.TOOLTIP_PLAYGROUND,
                    use_container_width=True,
                    type="secondary",
                    key="btn_playground_login",
                ):
                    login_playground()
                    update_last_activity()
                    st.rerun()

            # -------------------------
            # Playground info (centered)
            # -------------------------
            c1, c2, c3 = st.columns([1, 8, 1])
            with c2:
                st.caption(S.INFO_PLAYGROUND_LIMITS)
