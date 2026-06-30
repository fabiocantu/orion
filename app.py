from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from src.auth import login_form, render_footer, render_sidebar_navigation
from src.boards import list_public_exam_boards, public_exam_calendar_enabled
from src.dashboard import dashboard_snapshot
from src.seed import seed_initial_data
from src.ui import apply_app_style, render_item_list, render_kpis
from src.utils import format_date_br


st.set_page_config(page_title="Gestor de Assessoria de TFG", page_icon="🎓", layout="wide")


apply_app_style()


@st.cache_resource
def bootstrap_app() -> bool:
    seed_initial_data()
    return True


bootstrap_app()


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

    def format_weekday_date(value: date) -> str:
        weekdays = [
            "Segunda-feira",
            "Terça-feira",
            "Quarta-feira",
            "Quinta-feira",
            "Sexta-feira",
            "Sábado",
            "Domingo",
        ]
        return f"{weekdays[value.weekday()]}, dia {value.strftime('%d/%m/%Y')}"

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
                "Data completa": format_weekday_date(board_date),
                "Horário": board["scheduled_time"] or "-",
                "Etapa": board["stage"],
                "Aluno": board["student_name"],
                "Tema": board["theme"],
                "Local": board["location"] or "-",
                "Orientador": board["orientador"] or "-",
                "Avaliadores": board["avaliadores"] or "-",
                "Data ISO": board_date.isoformat(),
            }
        )

    st.caption(f"Semana de {start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}")
    if not rows:
        st.info("Nenhuma banca pública encontrada nesta semana.")
        return

    view_mode = st.radio(
        "Visualização",
        ["Cards", "Tabela"],
        horizontal=True,
        key="public_exam_calendar_view",
    )
    df = pd.DataFrame(rows).drop(columns=["Data ISO", "Data completa"])

    if view_mode == "Cards":
        today_rows = [row for row in rows if row["Data ISO"] == date.today().isoformat()]
        render_item_list(
            [
                {
                    "title": f"{row['Data completa']} | {row['Horário']} | {row['Etapa']} | {row['Aluno']}",
                    "meta": f"Tema: {row['Tema']} | Local: {row['Local']} | Orientador: {row['Orientador']} | Avaliadores: {row['Avaliadores']}",
                    "status": row["Status"],
                }
                for row in today_rows
            ],
            "Nenhuma banca agendada para hoje.",
        )
        return

    def color_status(row):
        colors = {
            "A seguir": "color: #15803d; font-weight: 600",
            "Em andamento": "color: #c2410c; font-weight: 600",
            "Finalizada": "color: #b91c1c; font-weight: 600",
        }
        return [colors.get(row["Status"], "") if column == "Status" else "" for column in row.index]

    st.dataframe(df.style.apply(color_status, axis=1), width="stretch", hide_index=True)

user = st.session_state.get("user")
if not user:
    st.title("Início")
    st.caption("Gestor de Assessoria de TFG | Arquitetura e Urbanismo - Centro Universitário Mater Dei")
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
    st.title("Hoje")
    st.caption(f"Bem-vindo(a), {user['name']}.")

    snapshot = dashboard_snapshot(user)
    render_kpis(snapshot["kpis"])

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Pendências de assessoria")
        render_item_list(snapshot["pending_sessions"], "Nenhuma ficha pendente no momento.")
    with col2:
        st.subheader("Bancas de hoje")
        render_item_list(snapshot["today_boards"], "Nenhuma banca marcada para hoje.")

    st.subheader("Próximas bancas")
    render_item_list(snapshot["upcoming_boards"], "Nenhuma banca futura cadastrada.")

    st.subheader("Acessos rápidos")
    if user["role"] == "professor":
        quick_col1, quick_col2 = st.columns(2)
        quick_col1.page_link("pages/1_Professor.py", label="Abrir orientação", icon="📚")
        quick_col2.page_link("pages/7_Bancas.py", label="Abrir bancas", icon="🏛️")
    else:
        quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)
        quick_col1.page_link("pages/2_Coordenacao.py", label="Coordenação", icon="🏛️")
        quick_col2.page_link("pages/5_Cadastros.py", label="Cadastros", icon="📝")
        quick_col3.page_link("pages/7_Bancas.py", label="Bancas", icon="🏛️")
        quick_col4.page_link("pages/3_Relatorios.py", label="Relatórios", icon="📊")
    st.page_link("pages/4_Config.py", label="Configurações", icon="🔧")

render_footer()
