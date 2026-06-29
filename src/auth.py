from __future__ import annotations

import streamlit as st

from .database import execute, query_one
from .security import hash_password, is_password_hash, verify_password


NAV_ITEMS = {
    "professor": [
        {"path": "app.py", "label": "Início", "icon": "🏠"},
        {"path": "pages/1_Professor.py", "label": "Orientação", "icon": "📚"},
        {"path": "pages/7_Bancas.py", "label": "Bancas", "icon": "🏛️"},
        {"path": "pages/4_Config.py", "label": "Configurações", "icon": "🔧"},
    ],
    "coordenacao": [
        {"path": "app.py", "label": "Início", "icon": "🏠"},
        {"path": "pages/2_Coordenacao.py", "label": "Coordenação", "icon": "🏛️"},
        {"path": "pages/5_Cadastros.py", "label": "Cadastros", "icon": "📝"},
        {"path": "pages/7_Bancas.py", "label": "Bancas", "icon": "🏛️"},
        {"path": "pages/3_Relatorios.py", "label": "Relatórios", "icon": "📊"},
        {"path": "pages/4_Config.py", "label": "Configurações", "icon": "🔧"},
    ],
}


def authenticate(email_or_name: str, password: str):
    value = email_or_name.strip().lower()
    user = query_one(
        """
        SELECT * FROM users
        WHERE lower(email) = ? OR lower(name) = ?
        """,
        (value, value),
    )
    if not user or not verify_password(password, user["password"]):
        return None
    if not is_password_hash(user["password"]):
        execute("UPDATE users SET password = ? WHERE id = ?", (hash_password(password), user["id"]))
        user = query_one("SELECT * FROM users WHERE id = ?", (user["id"],))
    return user


def login_form():
    st.subheader("Login")
    with st.form("login_form"):
        user = st.text_input("Usuário ou e-mail")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")
    if submitted:
        found = authenticate(user, password)
        if found:
            st.session_state["user"] = dict(found)
            st.success("Login realizado.")
            st.rerun()
        st.error("Usuário ou senha inválidos.")


def require_login():
    user = st.session_state.get("user")
    if not user:
        st.warning("Faça login para continuar.")
        st.page_link("app.py", label="Ir para o login", icon="🏠")
        st.stop()
    render_sidebar_navigation(user)
    return user


def require_role(role: str):
    user = require_login()
    if user["role"] != role:
        st.error("Acesso restrito.")
        st.stop()
    return user


def change_password(user_id: int, current_password: str, new_password: str) -> tuple[bool, str]:
    user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not user:
        return False, "Usuário não encontrado."
    if not verify_password(current_password, user["password"]):
        return False, "Senha atual incorreta."
    if len(new_password.strip()) < 4:
        return False, "A nova senha deve ter pelo menos 4 caracteres."
    execute("UPDATE users SET password = ? WHERE id = ?", (hash_password(new_password), user_id))
    return True, "Senha alterada com sucesso."


def apply_sidebar_visibility(role: str) -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebarNav"] {
            display: none !important;
        }
        [data-testid="stSidebar"] .stButton button {
            width: 100%;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_navigation(user: dict) -> None:
    apply_sidebar_visibility(user["role"])
    st.sidebar.markdown("### Gestor TFG")
    st.sidebar.caption(f"{user['name']} | {user['role']}")
    st.sidebar.markdown("---")
    for item in NAV_ITEMS.get(user["role"], []):
        st.sidebar.page_link(item["path"], label=item["label"], icon=item["icon"])
    st.sidebar.markdown("---")
    logout_button()


def render_footer() -> None:
    st.markdown("---")
    st.caption("feito por fabinho e seu amigo codex")


def logout_button() -> None:
    if st.sidebar.button("Sair", key="sidebar_logout_button"):
        st.session_state.pop("user", None)
        st.rerun()
