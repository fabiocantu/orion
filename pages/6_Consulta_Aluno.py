from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.auth import render_footer
from src.boards import list_student_public_exam_boards
from src.pdf_generator import generate_board_pdf, generate_record_pdf, latest_pdf_for_record
from src.ui import apply_app_style
from src.utils import format_date_br, get_answers, get_student_by_ra, list_criteria, list_student_public_sessions


st.set_page_config(page_title="Consulta do Aluno", page_icon="\U0001F393", layout="wide")
apply_app_style()

st.markdown(
    """
    <style>
    [data-testid="stSidebar"] {display: none;}
    [data-testid="collapsedControl"] {display: none;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Consulta do Aluno")
st.caption("Acesso somente leitura às fichas de assessoria e atas de banca já disponíveis.")

st.page_link("app.py", label="Voltar para o Inicio", icon="\U0001F3E0")

with st.form("student_ra_lookup"):
    ra = st.text_input("Digite seu RA")
    submitted = st.form_submit_button("Consultar")

if submitted:
    student = get_student_by_ra(ra)
    if not student:
        st.error("RA não encontrado. Confira o número informado.")
        st.stop()

    st.session_state["student_public_ra"] = student["ra"]

stored_ra = st.session_state.get("student_public_ra")
if stored_ra:
    student = get_student_by_ra(stored_ra)
    if not student:
        st.stop()

    st.subheader(student["name"])
    col1, col2, col3 = st.columns(3)
    col1.metric("RA", student["ra"] or "-")
    col2.metric("Etapa", student["tfg_stage"])
    col3.metric("Ano/Semestre", f"{student['year']}/{student['semester']}")
    st.write(f"**Tema:** {student['theme']}")

    sessions = list_student_public_sessions(student["id"])
    boards = list_student_public_exam_boards(student["id"])
    if not sessions and not boards:
        st.info("Ainda não há fichas ou atas disponíveis para consulta.")
        render_footer()
        st.stop()

    if sessions:
        st.subheader("Fichas disponíveis")
    for session in sessions:
        title = f"Assessoria {session['session_number']} | {session['phase']} | {session['final_evaluation'] or 'Sem avaliação'}"
        with st.expander(title):
            col_a, col_b, col_c = st.columns(3)
            col_a.write(f"**Orientador:** {session['advisor_name']}")
            col_b.write(f"**Data prevista:** {format_date_br(session['planned_date'])}")
            col_c.write(f"**Data realizada:** {format_date_br(session['actual_date'])}")

            st.markdown("**Critérios avaliados**")
            criteria = list_criteria(session["tfg_stage"], session["phase"])
            answers = get_answers(session["record_id"])
            for criterion in criteria:
                answer = answers.get(criterion["id"], {})
                st.write(f"**{criterion['group_name']}**")
                st.caption(criterion["description"])
                st.write(f"Avaliação: {answer.get('answer', '-')}")
                if answer.get("comment"):
                    st.write(f"Observação: {answer['comment']}")

            st.markdown("**Síntese da orientação**")
            st.write(f"**Situação atual e recomendações gerais:** {session['general_notes'] or '-'}")
            st.write(f"**Encaminhamentos:** {session['referrals'] or '-'}")
            st.write(f"**Pendências:** {session['pending_issues'] or '-'}")
            st.write(f"**Avaliação final:** {session['final_evaluation'] or '-'}")
            st.write(f"**Comentário geral:** {session['final_comment'] or '-'}")

            pdf_path = latest_pdf_for_record(session["record_id"])
            if st.button("Gerar PDF para baixar", key=f"student_pdf_{session['id']}"):
                pdf_path = generate_record_pdf(session["id"])
            if pdf_path and Path(pdf_path).exists():
                with open(pdf_path, "rb") as pdf_file:
                    st.download_button(
                        "Baixar PDF",
                        pdf_file,
                        file_name=Path(pdf_path).name,
                        mime="application/pdf",
                        key=f"student_download_{session['id']}",
                    )


    if boards:
        st.subheader("Atas de banca disponíveis")
        for board in boards:
            title = f"{board['stage']} | {format_date_br(board['scheduled_date'])} | {board['status']}"
            with st.expander(title):
                col_a, col_b, col_c = st.columns(3)
                col_a.write(f"**Orientador:** {board['orientador'] or '-'}")
                col_b.write(f"**Avaliadores:** {board['avaliadores'] or '-'}")
                col_c.write(f"**Horário:** {board['scheduled_time'] or '-'}")
                st.write(f"**Local:** {board['location'] or '-'}")
                st.write(f"**Tema:** {board['theme'] or '-'}")
                st.write(f"**Ata registrada em:** {format_date_br(board['minutes_updated_at'])}")

                pdf_key = f"student_board_pdf_{board['id']}"
                pdf_path = st.session_state.get(pdf_key)
                if st.button("Gerar ata em PDF para baixar", key=f"student_generate_board_pdf_{board['id']}"):
                    pdf_path = generate_board_pdf(board["id"])
                    st.session_state[pdf_key] = str(pdf_path)
                if pdf_path and Path(pdf_path).exists():
                    with open(pdf_path, "rb") as pdf_file:
                        st.download_button(
                            "Baixar ata da banca em PDF",
                            pdf_file,
                            file_name=Path(pdf_path).name,
                            mime="application/pdf",
                            key=f"student_download_board_pdf_{board['id']}",
                        )

render_footer()
