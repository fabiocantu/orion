from __future__ import annotations

from datetime import date
from pathlib import Path

import streamlit as st

from src.auth import render_footer, require_role
from src.database import query
from src.pdf_generator import generate_record_pdf
from src.timezone import today_local
from src.ui import apply_app_style
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
apply_app_style()
user = require_role("coordenacao")


def to_dicts(rows) -> list[dict]:
    return [dict(row) for row in rows]


@st.cache_data(ttl=30, show_spinner=False)
def cached_advisors() -> list[dict]:
    return to_dicts(query("SELECT * FROM advisors ORDER BY name"))


@st.cache_data(ttl=30, show_spinner=False)
def cached_students(advisor_id: int | None, tfg_stage: str | None, year: int, semester: int | None) -> list[dict]:
    return to_dicts(
        list_all_students(
            {
                "advisor_id": advisor_id,
                "tfg_stage": tfg_stage,
                "year": year,
                "semester": semester,
            }
        )
    )


@st.cache_data(ttl=30, show_spinner=False)
def cached_sessions(orientation_id: int) -> list[dict]:
    return to_dicts(list_sessions(orientation_id))


@st.cache_data(ttl=30, show_spinner=False)
def cached_student_context(session_id: int) -> dict | None:
    row = get_student_context_by_session(session_id)
    return dict(row) if row else None


@st.cache_data(ttl=30, show_spinner=False)
def cached_record(session_id: int) -> dict | None:
    row = get_record(session_id)
    return dict(row) if row else None


@st.cache_data(ttl=30, show_spinner=False)
def cached_criteria(tfg_stage: str, phase: str) -> list[dict]:
    return to_dicts(list_criteria(tfg_stage, phase))


@st.cache_data(ttl=30, show_spinner=False)
def cached_answers(record_id: int) -> dict[int, dict]:
    return get_answers(record_id)


@st.cache_data(ttl=30, show_spinner=False)
def cached_pdf_exports(record_id: int) -> list[dict]:
    return to_dicts(list_pdf_exports(record_id))


def clear_read_cache() -> None:
    cached_advisors.clear()
    cached_students.clear()
    cached_sessions.clear()
    cached_student_context.clear()
    cached_record.clear()
    cached_criteria.clear()
    cached_answers.clear()
    cached_pdf_exports.clear()

st.title("Coordenação")
if st.session_state.pop("record_finalized", False):
    st.balloons()
    st.success(st.session_state.pop("record_finalized_message", "Ficha finalizada com sucesso."))

advisors = cached_advisors()
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
students = cached_students(filters["advisor_id"], filters["tfg_stage"], filters["year"], filters["semester"])
if not students:
    st.warning("Nenhum aluno encontrado.")
    st.stop()

search_text = st.text_input("Buscar aluno ou professor", key="coord_student_search").strip().lower()
if search_text:
    students = [
        student
        for student in students
        if search_text in str(student["name"]).lower()
        or search_text in str(student["advisor_name"]).lower()
        or search_text in str(student["theme"]).lower()
    ]
    if not students:
        st.info("Nenhum aluno encontrado para a busca atual.")
        st.stop()

student_map = {f"{s['name']} - {s['advisor_name']} - {s['tfg_stage']}": s for s in students}
student = student_map[st.selectbox("Aluno", list(student_map.keys()))]
st.write(f"**Tema:** {student['theme']}")

sessions = cached_sessions(student["orientation_id"])
session_map = {f"{s['session_number']} - {s['phase']} - {s['status']} - {s['final_evaluation'] or '-'}": s for s in sessions}
session = session_map[st.selectbox("Ficha", list(session_map.keys()))]
context = cached_student_context(session["id"])
record = cached_record(session["id"])
criteria_rows = cached_criteria(context["tfg_stage"], context["phase"])
existing_answers = cached_answers(record["id"]) if record else {}

with st.expander("Controles de coordenação", expanded=True):
    col_a, col_b = st.columns(2)
    unlock_justification = col_a.text_input("Justificativa para destravar")
    if col_a.button("Destravar assessoria"):
        if not unlock_justification.strip():
            st.error("Informe justificativa.")
        else:
            unlock_session(session["id"], user["id"], unlock_justification)
            st.success("Assessoria destravada.")
            clear_read_cache()
            st.rerun()
    new_date = col_b.date_input("Nova data prevista", value=date.fromisoformat(context["planned_date"]), format="DD/MM/YYYY")
    date_justification = col_b.text_input("Justificativa para alterar data")
    if col_b.button("Alterar data prevista"):
        if not date_justification.strip():
            st.error("Informe justificativa.")
        else:
            update_planned_date(session["id"], new_date.isoformat(), user["id"], date_justification)
            st.success("Data atualizada.")
            clear_read_cache()
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
    actual_date_key: date.fromisoformat(context["actual_date"]) if context["actual_date"] else today_local(),
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
    answer = cols[0].radio(
        "Avaliação",
        RATINGS,
        key=answer_key,
        horizontal=True,
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
save_col, finish_col = st.columns(2)
submitted = save_col.button("Salvar rascunho")
submitted_finish = finish_col.button("Finalizar ficha")

if submitted or submitted_finish:
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
                lock_record=bool(submitted_finish or context["locked"]),
            )
            if submitted_finish:
                st.session_state["record_finalized"] = True
                st.session_state["record_finalized_message"] = "Ficha finalizada com sucesso."
            else:
                st.success("Rascunho salvo.")
            clear_read_cache()
            st.rerun()

record = cached_record(session["id"])
if record:
    col_pdf, col_download = st.columns(2)
    if col_pdf.button("Gerar PDF"):
        pdf_path = generate_record_pdf(session["id"])
        st.success(f"PDF gerado: {pdf_path.name}")
        clear_read_cache()
        st.rerun()
    exports = cached_pdf_exports(record["id"])
    if exports:
        latest = Path(exports[0]["file_path"])
        if latest.exists():
            col_download.download_button("Baixar PDF", latest.read_bytes(), file_name=latest.name, mime="application/pdf")

st.subheader("Histórico do aluno")
st.dataframe(
    [{"Assessoria": s["session_number"], "Fase": s["phase"], "Prevista": format_date_br(s["planned_date"]), "Status": s["status"], "Avaliação": s["final_evaluation"] or "-"} for s in sessions],
    width="stretch",
)

render_footer()

