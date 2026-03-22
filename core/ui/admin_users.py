from __future__ import annotations

import pandas as pd
import streamlit as st

from core.auth.session import get_current_user
from core.auth.storage import (
    DEFAULT_ADMIN_USERNAME,
    DEFAULT_DB_PATH,
    create_user,
    delete_user,
    list_users,
    set_active,
    set_password,
)


def _users_dataframe(records: list[dict]) -> pd.DataFrame:
    rows = []
    for item in records:
        rows.append(
            {
                "Username": item.get("username"),
                "Role": item.get("role"),
                "Active": bool(item.get("is_active")),
                "Created (UTC)": item.get("created_at_utc"),
                "Updated (UTC)": item.get("updated_at_utc"),
                "Last login (UTC)": item.get("last_login_utc"),
                "Failed attempts": int(item.get("failed_attempts") or 0),
                "Locked until (UTC)": item.get("locked_until_utc"),
            }
        )
    return pd.DataFrame(rows)


def render_admin_users(role: str | None = None, db_path: str = DEFAULT_DB_PATH) -> None:
    st.markdown("### Admin Users")

    if not role or role.lower() != "admin":
        st.warning("Admin Users is restricted to Admin users.")
        return

    users = list_users(db_path=db_path)
    current_user = (get_current_user() or "").strip()

    st.caption("Create, inspect, activate/deactivate, reset passwords, and remove users.")
    if users:
        st.dataframe(_users_dataframe(users), width="stretch", hide_index=True)
    else:
        st.info("No users found.")

    st.markdown("#### Create user")
    with st.form("admin_users_create_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            new_username = st.text_input(
                "Username",
                value="",
                help="Use an email address for non-admin accounts.",
            )
            new_password = st.text_input("Initial password", value="", type="password")
        with c2:
            new_role = st.selectbox("Role", options=["User", "Admin"], index=0)
            new_active = st.checkbox("Active", value=True)

        create_submitted = st.form_submit_button("Create user", type="primary")
        if create_submitted:
            try:
                create_user(
                    username=new_username,
                    password=new_password,
                    role=new_role,
                    db_path=db_path,
                    is_active=new_active,
                )
            except Exception as e:
                st.error(f"Could not create user: {e}")
            else:
                st.success(f"User '{new_username.strip()}' created.")
                st.rerun()

    if not users:
        return

    st.markdown("#### Manage existing user")
    usernames = [str(u.get("username")) for u in users]
    selected_username = st.selectbox(
        "Select user",
        options=usernames,
        key="admin_users_selected_username",
    )
    selected = next((u for u in users if str(u.get("username")) == selected_username), None) or {}
    is_active = bool(selected.get("is_active"))
    is_default_admin = selected_username == DEFAULT_ADMIN_USERNAME
    is_self = selected_username == current_user

    st.caption(
        f"Selected: {selected_username} | Role={selected.get('role')} | "
        f"Active={is_active} | Failed attempts={int(selected.get('failed_attempts') or 0)}"
    )

    col_toggle, col_reset = st.columns(2)
    with col_toggle:
        toggle_label = "Deactivate user" if is_active else "Activate user"
        toggle_disabled = bool(is_default_admin and is_active)
        if st.button(toggle_label, use_container_width=True, disabled=toggle_disabled, key="admin_users_toggle_active"):
            try:
                if is_self and is_active:
                    raise ValueError("You cannot deactivate the account currently in use.")
                set_active(selected_username, not is_active, db_path=db_path)
            except Exception as e:
                st.error(f"Could not update active state: {e}")
            else:
                st.success(f"User '{selected_username}' updated.")
                st.rerun()

    with col_reset:
        with st.form("admin_users_password_reset_form", clear_on_submit=True):
            reset_password_value = st.text_input("New password", value="", type="password")
            reset_submitted = st.form_submit_button("Reset password", use_container_width=True)
            if reset_submitted:
                try:
                    set_password(selected_username, reset_password_value, db_path=db_path)
                except Exception as e:
                    st.error(f"Could not reset password: {e}")
                else:
                    st.success(f"Password updated for '{selected_username}'.")
                    st.rerun()

    st.markdown("#### Remove user")
    with st.form("admin_users_delete_form"):
        delete_confirm = st.checkbox(
            f"I understand that user '{selected_username}' will be permanently removed.",
            value=False,
        )
        delete_submitted = st.form_submit_button(
            "Delete user",
            type="secondary",
            disabled=is_default_admin,
        )
        if delete_submitted:
            try:
                if is_self:
                    raise ValueError("You cannot delete the account currently in use.")
                if not delete_confirm:
                    raise ValueError("Please confirm deletion before removing the user.")
                delete_user(selected_username, db_path=db_path)
            except Exception as e:
                st.error(f"Could not delete user: {e}")
            else:
                st.success(f"User '{selected_username}' deleted.")
                st.rerun()
