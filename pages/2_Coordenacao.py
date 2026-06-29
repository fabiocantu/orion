from __future__ import annotations

from datetime import date
from pathlib import Path

import streamlit as st

from src.auth import render_footer, require_role
from src.database import query
from src.email_sender import send_record_email
from src.pdf_generator import generate_record_pdf
from src.utils import (
    ANSWERS,
    NOT_APPLICABLE,
    RATINGS,
    format_date_br,
    get_answers,
    get_record,
    get_student_context_by_session,
    list_all_students,
    list_criteria,
    list_pdf_exports,
    list_sessions,
    normalize_rating_value,
    save_record,
    unlock_session,
    update_planned_date,
    validate_record,
)


st.set_page_config(page_title="Coordenação", layout="wide")
user = require_role("coordenacao")

st.title("Coordenação")
if st.session_state.pop("celebrate_record_sent", False):
    st.balloons()
    st.success(st.session_state.pop("celebrate_record_message", "Ficha finalizada com sucesso."))

advisors = query("SELECT * FROM advisors ORDER BY name")
advisor_options = {"Todos": None} | {a["name"]: a["id"] for a in advisors}
col1, col2, col3, col4 = st.columns(4)
advisor_filter = col1.selectbox("Professor", list(advisor_options.keys()))
stage_filter = col2.selectbox("Etapa", ["Todas", "TFG I", "TFG II"])
year_filter = col3.number_input("Ano", min_value=2020, max_value=2100, value=2026)
semester_filter = col4.selectbox("Semestre", ["Todos", 1, 2])

filters = {
    "advisor_id": advisor_options[advisor_filter],
    "tfg_stage": None if stage_filter == "Todas" else stage_filter,
    "year": int(year_filter),
    "semester": None if semester_filter == "Todos" else int(semester_filter),
}
students = list_all_students(filters)
if not students:
    st.warning("Nenhum aluno encontrado.")
    st.stop()

student_map = {f"{s['name']} - {s['advisor_name']} - {s['tfg_stage']}": s for s in students}
student = student_map[st.selectbox("Aluno", list(student_map.keys()))]
st.write(f"**Tema:** {student['theme']}")

sessions = list_sessions(student["orientation_id"])
session_map = {f"{s['session_number']} - {s['phase']} - {s['status']} - {s['final_evaluation'] or '-'}": s for s in sessions}
session = session_map[st.selectbox("Ficha", list(session_map.keys()))]
context = get_student_context_by_session(session["id"])
record = get_record(session["id"])
criteria_rows = list_criteria(context["tfg_stage"], context["phase"])
existing_answers = get_answers(record["id"]) if record else {}

with st.expander("Controles de coordenação", expanded=True):
    col_a, col_b = st.columns(2)
    unlock_justification = col_a.text_input("Justificativa para destravar")
    if col_a.button("Destravar assessoria"):
        if not unlock_justification.strip():
            st.error("Informe justificativa.")
        else:
            unlock_session(session["id"], user["id"], unlock_justification)
            st.success("Assessoria destravada.")
            st.rerun()
    new_date = col_b.date_input("Nova data prevista", value=date.fromisoformat(context["planned_date"]), format="DD/MM/YYYY")
    date_justification = col_b.text_input("Justificativa para alterar data")
    if col_b.button("Alterar data prevista"):
        if not date_justification.strip():
            st.error("Informe justificativa.")
        else:
            update_planned_date(session["id"], new_date.isoformat(), user["id"], date_justification)
            st.success("Data atualizada.")
            st.rerun()

st.subheader("Editar ficha")
st.caption("Rascunho preservado nesta sessão enquanto você preenche a ficha. Evite abrir duas janelas da mesma ficha ao mesmo tempo.")

general_key = f"coord_general_{session['id']}"
referrals_key = f"coord_referrals_{session['id']}"
pending_key = f"coord_pending_{session['id']}"
final_eval_key = f"coord_final_eval_{session['id']}"
final_comment_key = f"coord_final_comment_{session['id']}"
actual_date_key = f"coord_actual_date_{session['id']}"
justification_key = f"coord_justification_{session['id']}"
defaults = {
    general_key: record["general_notes"] if record else "",
    referrals_key: record["referrals"] if record else "",
    pending_key: record["pending_issues"] if record else "",
    final_eval_key: record["final_evaluation"] if record and record["final_evaluation"] in ANSWERS else "Sim",
    final_comment_key: record["final_comment"] if record else "",
    actual_date_key: date.fromisoformat(context["actual_date"]) if context["actual_date"] else date.today(),
    justification_key: "",
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

actual_date = st.date_input("Data realizada", key=actual_date_key, format="DD/MM/YYYY")
general_notes = st.text_area("Situação atual e recomendações gerais", key=general_key)

st.markdown("**Critérios**")
answers = {}
for criterion in criteria_rows:
    previous = existing_answers.get(criterion["id"], {})
    answer_key = f"coord_answer_{session['id']}_{criterion['id']}"
    comment_key = f"coord_comment_{session['id']}_{criterion['id']}"
    not_applicable_key = f"coord_na_{session['id']}_{criterion['id']}"
    if answer_key not in st.session_state:
        st.session_state[answer_key] = normalize_rating_value(previous.get("answer"))
    if comment_key not in st.session_state:
        st.session_state[comment_key] = previous.get("comment", "")
    if not_applicable_key not in st.session_state:
        st.session_state[not_applicable_key] = previous.get("answer") == NOT_APPLICABLE

    cols = st.columns([5, 4])
    cols[0].write(f"**{criterion['group_name']}**")
    cols[0].caption(criterion["description"])
    not_applicable = cols[0].checkbox("Não compete à etapa", key=not_applicable_key)
    answer = cols[0].select_slider(
        "Avaliação",
        RATINGS,
        key=answer_key,
        disabled=not_applicable,
    )
    comment_disabled = not_applicable
    comment = cols[1].text_area(
        "Observação",
        key=comment_key,
        height=80,
        disabled=comment_disabled,
        placeholder="Não compete à etapa" if comment_disabled else "",
    )
    if comment_disabled:
        cols[0].caption("Critério desabilitado.")
        answer = NOT_APPLICABLE
        comment = ""
    answers[criterion["id"]] = {"answer": answer, "comment": comment}

st.markdown("**Observações gerais**")
referrals = st.text_area("Encaminhamentos", key=referrals_key)
pending_issues = st.text_area("Pendências", key=pending_key)
final_comment = st.text_area("Comentário geral", key=final_comment_key)
final_evaluation = st.selectbox("Avaliação final", ANSWERS, key=final_eval_key)
justification = st.text_area("Justificativa da edição", key=justification_key, help="Obrigatória quando a ficha já existe.")

st.markdown("**Ações da ficha**")
save_col, send_col = st.columns(2)
submitted = save_col.button("Salvar")
submitted_send = send_col.button("Salvar e enviar")

if submitted or submitted_send:
    if record and not justification.strip():
        st.error("Informe justificativa para editar ficha já preenchida.")
    else:
        errors = validate_record(criteria_rows, answers, final_evaluation, final_comment)
        if errors:
            for error in errors:
                st.error(error)
        else:
            save_record(
                session["id"],
                context["advisor_id"],
                {
                    "answers": answers,
                    "general_notes": general_notes,
                    "referrals": referrals,
                    "pending_issues": pending_issues,
                    "final_evaluation": final_evaluation,
                    "final_comment": final_comment,
                    "actual_date": actual_date.isoformat(),
                },
                user,
                justification,
                lock_record=bool(submitted_send or context["locked"]),
            )
            if submitted_send:
                pdf_path = generate_record_pdf(session["id"])
                result = send_record_email(context["email"] or "sem-email", "Ficha de Assessoria de TFG", str(pdf_path))
                st.session_state["celebrate_record_sent"] = True
                st.session_state["celebrate_record_message"] = f"Ficha salva e envio simulado. {result['message']}"
            else:
                st.success("Ficha salva.")
            st.rerun()

record = get_record(session["id"])
if record:
    col_pdf, col_download, col_email = st.columns(3)
    if col_pdf.button("Gerar PDF"):
        pdf_path = generate_record_pdf(session["id"])
        st.success(f"PDF gerado: {pdf_path.name}")
        st.rerun()
    exports = list_pdf_exports(record["id"])
    if exports:
        latest = Path(exports[0]["file_path"])
        if latest.exists():
            col_download.download_button("Baixar PDF", latest.read_bytes(), file_name=latest.name, mime="application/pdf")
    if col_email.button("Simular envio por e-mail"):
        result = send_record_email(context["email"] or "sem-email", "Ficha de Assessoria de TFG")
        st.info(result["message"])

st.subheader("Histórico do aluno")
st.dataframe(
    [{"Assessoria": s["session_number"], "Fase": s["phase"], "Prevista": format_date_br(s["planned_date"]), "Status": s["status"], "Avaliação": s["final_evaluation"] or "-"} for s in sessions],
    width="stretch",
)

render_footer()

