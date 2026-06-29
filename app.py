from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from src.auth import login_form, render_footer, render_sidebar_navigation
from src.boards import list_public_exam_boards, public_exam_calendar_enabled
from src.seed import seed_initial_data
from src.utils import format_date_br


st.set_page_config(page_title="Gestor de Assessoria de TFG", page_icon="🎓", layout="wide")


@st.cache_resource
def bootstrap_app() -> bool:
    seed_initial_data()
    return True


bootstrap_app()

st.title("Início")
st.caption("Gestor de Assessoria de TFG | Arquitetura e Urbanismo - Centro Universitário Mater Dei")


def render_public_exam_calendar() -> None:
    st.subheader("Calendário público de bancas")
    reference = st.date_input("Semana de referência", value=date.today(), format="DD/MM/YYYY", key="public_exam_week")
    start = reference - timedelta(days=reference.weekday())
    end = start + timedelta(days=6)
    boards = list_public_exam_boards(start, end)

    def parse_board_time(value: object) -> time | None:
        text = str(value or "").strip().lower()
        if not text or text == "-":
            return None
        text = text.replace("h", ":")
        if ":" not in text and text.isdigit():
            text = f"{text}:00"
        try:
            return datetime.strptime(text, "%H:%M").time()
        except ValueError:
            return None

    def public_status(board_date: date, board_time: time | None) -> str:
        now = datetime.now()
        if board_time is None:
            if board_date < now.date():
                return "Finalizada"
            if board_date == now.date():
                return "Em andamento"
            return "A seguir"

        starts_at = datetime.combine(board_date, board_time)
        ends_at = starts_at + timedelta(hours=1)
        if now < starts_at:
            return "A seguir"
        if starts_at <= now < ends_at:
            return "Em andamento"
        return "Finalizada"

    rows = []
    for board in boards:
        try:
            board_date = date.fromisoformat(str(board["scheduled_date"])[:10])
        except ValueError:
            board_date = start
        board_time = parse_board_time(board["scheduled_time"])
        rows.append(
            {
                "Status": public_status(board_date, board_time),
                "Data": format_date_br(board["scheduled_date"]),
                "Horário": board["scheduled_time"] or "-",
                "Etapa": board["stage"],
                "Aluno": board["student_name"],
                "Tema": board["theme"],
                "Local": board["location"] or "-",
            }
        )

    st.caption(f"Semana de {start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}")
    if rows:
        df = pd.DataFrame(rows)

        def color_status(row):
            colors = {
                "A seguir": "color: #15803d; font-weight: 600",
                "Em andamento": "color: #c2410c; font-weight: 600",
                "Finalizada": "color: #b91c1c; font-weight: 600",
            }
            return [colors.get(row["Status"], "") if column == "Status" else "" for column in row.index]

        st.dataframe(df.style.apply(color_status, axis=1), width="stretch", hide_index=True)
    else:
        st.info("Nenhuma banca pública encontrada nesta semana.")


user = st.session_state.get("user")
if not user:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {display: none;}
        [data-testid="collapsedControl"] {display: none;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    if public_exam_calendar_enabled():
        render_public_exam_calendar()
        st.divider()
    st.info("Entre para acessar o sistema.")
    login_form()
    st.page_link("pages/6_Consulta_Aluno.py", label="Consulta do aluno por RA", icon="🎓")
else:
    render_sidebar_navigation(user)
    st.write(f"Bem-vindo(a), **{user['name']}**.")
    if user["role"] == "professor":
        st.page_link("pages/1_Professor.py", label="Abrir orientação", icon="📚")
        st.page_link("pages/7_Bancas.py", label="Abrir bancas", icon="🏛️")
    else:
        st.page_link("pages/2_Coordenacao.py", label="Abrir coordenação", icon="🏛️")
        st.page_link("pages/5_Cadastros.py", label="Abrir cadastros", icon="📝")
        st.page_link("pages/7_Bancas.py", label="Abrir bancas", icon="🏛️")
        st.page_link("pages/3_Relatorios.py", label="Abrir relatórios", icon="📊")
    st.page_link("pages/4_Config.py", label="Configurações", icon="🔧")

render_footer()
