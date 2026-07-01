from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import streamlit as st

from .database import execute, query_one
from .security import hash_password, is_password_hash, verify_password


AUTH_COOKIE_NAME = "orion_remember_token"
AUTH_SESSION_DAYS = 30


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


@st.cache_resource(show_spinner=False)
def cookie_manager():
    try:
        import extra_streamlit_components as stx
    except ImportError:
        return None
    return stx.CookieManager()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _public_user(row) -> dict:
    data = dict(row)
    data.pop("password", None)
    return data


def _get_cookie_token() -> str:
    manager = cookie_manager()
    if manager is None:
        return ""
    try:
        return manager.get(AUTH_COOKIE_NAME) or ""
    except Exception:
        return ""


def _set_cookie_token(token: str, expires_at: datetime) -> None:
    manager = cookie_manager()
    if manager is None:
        return
    try:
        manager.set(AUTH_COOKIE_NAME, token, expires_at=expires_at)
    except Exception:
        pass


def _delete_cookie_token() -> None:
    manager = cookie_manager()
    if manager is None:
        return
    try:
        manager.delete(AUTH_COOKIE_NAME)
    except Exception:
        pass


def create_persistent_session(user_id: int) -> None:
    token = secrets.token_urlsafe(32)
    expires_at = _utc_now() + timedelta(days=AUTH_SESSION_DAYS)
    execute(
        """
        INSERT INTO auth_sessions (user_id, token_hash, expires_at)
        VALUES (?, ?, ?)
        """,
        (user_id, _token_hash(token), expires_at.isoformat()),
    )
    _set_cookie_token(token, expires_at)


def clear_persistent_session() -> None:
    token = _get_cookie_token()
    if token:
        execute("DELETE FROM auth_sessions WHERE token_hash = ?", (_token_hash(token),))
    _delete_cookie_token()


def restore_user_from_cookie() -> dict | None:
    if st.session_state.get("user"):
        return st.session_state["user"]
    token = _get_cookie_token()
    if not token:
        return None
    now_text = _utc_now().isoformat()
    row = query_one(
        """
        SELECT users.*
        FROM auth_sessions
        JOIN users ON users.id = auth_sessions.user_id
        WHERE auth_sessions.token_hash = ? AND auth_sessions.expires_at > ?
        """,
        (_token_hash(token), now_text),
    )
    if not row:
        _delete_cookie_token()
        return None
    execute("UPDATE auth_sessions SET last_seen_at = CURRENT_TIMESTAMP WHERE token_hash = ?", (_token_hash(token),))
    st.session_state["user"] = _public_user(row)
    return st.session_state["user"]


def current_user() -> dict | None:
    return st.session_state.get("user") or restore_user_from_cookie()


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
    restore_user_from_cookie()
    st.subheader("Login")
    with st.form("login_form"):
        user = st.text_input("Usuário ou e-mail")
        password = st.text_input("Senha", type="password")
        remember = st.checkbox("Manter conectado neste dispositivo", value=True)
        submitted = st.form_submit_button("Entrar")
    if submitted:
        found = authenticate(user, password)
        if found:
            st.session_state["user"] = _public_user(found)
            if remember:
                create_persistent_session(found["id"])
            st.success("Login realizado.")
            st.rerun()
        st.error("Usuário ou senha inválidos.")


def require_login():
    user = current_user()
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
        clear_persistent_session()
        st.session_state.pop("user", None)
        st.rerun()
