from __future__ import annotations

from datetime import date
from pathlib import Path

import streamlit as st

from src.auth import render_footer, require_role
from src.email_sender import send_record_email
from src.pdf_generator import generate_record_pdf
from src.utils import (
    ANSWERS,
    NOT_APPLICABLE,
    RATINGS,
    format_date_br,
    get_advisor_by_user,
    get_answers,
    get_record,
    get_student_context_by_session,
    list_criteria,
    list_professor_students,
    list_sessions,
    normalize_rating_value,
    save_record,
    validate_record,
)


st.set_page_config(page_title="Orientação", layout="wide")
user = require_role("professor")


def to_dicts(rows) -> list[dict]:
    return [dict(row) for row in rows]


@st.cache_data(ttl=30, show_spinner=False)
def cached_advisor_by_user(user_id: int) -> dict | None:
    row = get_advisor_by_user(user_id)
    return dict(row) if row else None


@st.cache_data(ttl=30, show_spinner=False)
def cached_professor_students(user_id: int) -> list[dict]:
    return to_dicts(list_professor_students(user_id))


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
    from src.utils import list_pdf_exports

    return to_dicts(list_pdf_exports(record_id))


def clear_read_cache() -> None:
    st.cache_data.clear()


advisor = cached_advisor_by_user(user["id"])

st.title("Área de Orientação")
st.caption(f"Orientador logado: {user['name']}")
if st.session_state.pop("celebrate_record_sent", False):
    st.balloons()
    st.success(st.session_state.pop("celebrate_record_message", "Ficha finalizada com sucesso."))

students = cached_professor_students(user["id"])
if not students:
    st.warning("Nenhum orientando vinculado.")
    st.stop()

student_map = {f"{row['name']} - {row['tfg_stage']}": row for row in students}
selected_label = st.selectbox("Orientando", list(student_map.keys()))
student = student_map[selected_label]

col_a, col_b, col_c = st.columns(3)
col_a.metric("Etapa", student["tfg_stage"])
col_b.metric("Ano/Semestre", f"{student['year']}/{student['semester']}")
col_c.metric("Orientador", student["advisor_name"])
st.write(f"**Tema:** {student['theme']}")

sessions = cached_sessions(student["orientation_id"])
session_label = st.selectbox(
    "Assessoria",
    [f"{s['session_number']} - {s['phase']} - {s['status']}" for s in sessions],
)
session = sessions[[f"{s['session_number']} - {s['phase']} - {s['status']}" for s in sessions].index(session_label)]

st.subheader(f"Ficha da assessoria {session['session_number']}")
if session["locked"]:
    st.info("Esta ficha está bloqueada após preenchimento. A coordenação pode destravar se necessário.")

context = cached_student_context(session["id"])
record = cached_record(session["id"])
criteria_rows = cached_criteria(context["tfg_stage"], context["phase"])
existing_answers = cached_answers(record["id"]) if record else {}

st.caption("Rascunho preservado nesta sessão enquanto você preenche a ficha. Evite abrir duas janelas da mesma ficha ao mesmo tempo.")
disabled_record = bool(session["locked"] and record)

general_key = f"prof_general_{session['id']}"
referrals_key = f"prof_referrals_{session['id']}"
pending_key = f"prof_pending_{session['id']}"
final_eval_key = f"prof_final_eval_{session['id']}"
final_comment_key = f"prof_final_comment_{session['id']}"
actual_date_key = f"prof_actual_date_{session['id']}"
defaults = {
    general_key: record["general_notes"] if record else "",
    referrals_key: record["referrals"] if record else "",
    pending_key: record["pending_issues"] if record else "",
    final_eval_key: record["final_evaluation"] if record and record["final_evaluation"] in ANSWERS else "Sim",
    final_comment_key: record["final_comment"] if record else "",
    actual_date_key: date.fromisoformat(context["actual_date"]) if context["actual_date"] else date.today(),
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

actual_date = st.date_input("Data realizada", key=actual_date_key, disabled=disabled_record, format="DD/MM/YYYY")
general_notes = st.text_area("Situação atual e recomendações gerais", key=general_key, disabled=disabled_record)

st.markdown("**Critérios**")
answers = {}
for criterion in criteria_rows:
    previous = existing_answers.get(criterion["id"], {})
    answer_key = f"prof_answer_{session['id']}_{criterion['id']}"
    comment_key = f"prof_comment_{session['id']}_{criterion['id']}"
    not_applicable_key = f"prof_na_{session['id']}_{criterion['id']}"
    if answer_key not in st.session_state:
        st.session_state[answer_key] = normalize_rating_value(previous.get("answer"))
    if comment_key not in st.session_state:
        st.session_state[comment_key] = previous.get("comment", "")
    if not_applicable_key not in st.session_state:
        st.session_state[not_applicable_key] = previous.get("answer") == NOT_APPLICABLE

    cols = st.columns([5, 4])
    cols[0].write(f"**{criterion['group_name']}**")
    cols[0].caption(criterion["description"])
    not_applicable = cols[0].checkbox(
        "Não compete à etapa",
        key=not_applicable_key,
        disabled=disabled_record,
    )
    answer = cols[0].select_slider(
        "Avaliação",
        RATINGS,
        key=answer_key,
        disabled=disabled_record or not_applicable,
    )
    comment_disabled = disabled_record or not_applicable
    comment = cols[1].text_area(
        "Observação",
        key=comment_key,
        height=80,
        disabled=comment_disabled,
        placeholder="Não compete à etapa" if not_applicable else "",
    )
    if not_applicable:
        cols[0].caption("Critério desabilitado.")
        answer = NOT_APPLICABLE
        comment = ""
    answers[criterion["id"]] = {"answer": answer, "comment": comment}

st.markdown("**Observações gerais**")
referrals = st.text_area("Encaminhamentos", key=referrals_key, disabled=disabled_record)
pending_issues = st.text_area("Pendências", key=pending_key, disabled=disabled_record)
final_comment = st.text_area("Comentário geral", key=final_comment_key, disabled=disabled_record)
final_evaluation = st.selectbox("Avaliação final", ANSWERS, key=final_eval_key, disabled=disabled_record)

st.markdown("**Ações da ficha**")
save_col, send_col = st.columns(2)
submitted = save_col.button("Salvar", disabled=disabled_record)
submitted_send = send_col.button("Salvar e enviar", disabled=disabled_record)

if submitted or submitted_send:
    errors = validate_record(criteria_rows, answers, final_evaluation, final_comment)
    if errors:
        for error in errors:
            st.error(error)
    else:
        save_record(
            session["id"],
            advisor["id"],
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
            lock_record=submitted_send,
        )
        if submitted_send:
            pdf_path = generate_record_pdf(session["id"])
            result = send_record_email(context["email"] or "sem-email", "Ficha de Assessoria de TFG", str(pdf_path))
            st.session_state["celebrate_record_sent"] = True
            st.session_state["celebrate_record_message"] = f"Ficha salva e envio simulado. {result['message']}"
        else:
            st.success("Ficha salva.")
        clear_read_cache()
        st.rerun()

record = cached_record(session["id"])
if record:
    pdf_col, download_col, email_col = st.columns(3)
    if pdf_col.button("Gerar PDF"):
        pdf_path = generate_record_pdf(session["id"])
        st.success(f"PDF gerado: {pdf_path.name}")
        clear_read_cache()
        st.rerun()
    exports = cached_pdf_exports(record["id"])
    if exports:
        latest = Path(exports[0]["file_path"])
        if latest.exists():
            download_col.download_button("Baixar PDF", latest.read_bytes(), file_name=latest.name, mime="application/pdf")
    if email_col.button("Simular envio por e-mail"):
        result = send_record_email(context["email"] or "sem-email", "Ficha de Assessoria de TFG")
        st.info(result["message"])

st.subheader("Histórico do aluno")
history = cached_sessions(student["orientation_id"])
st.dataframe(
    [
        {
            "Assessoria": h["session_number"],
            "Fase": h["phase"],
            "Data prevista": format_date_br(h["planned_date"]),
            "Status": h["status"],
            "Avaliação": h["final_evaluation"] or "-",
        }
        for h in history
    ],
    width="stretch",
)

render_footer()

