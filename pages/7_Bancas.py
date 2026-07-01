from __future__ import annotations

import unicodedata
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

import src.boards as boards_module
from src.auth import render_footer, require_login
from src.boards import (
    EXAM_STAGES,
    advisor_id_for_user,
    board_grade_summary,
    board_partial_grade,
    board_status,
    consolidated_results,
    create_exam_criterion,
    delete_exam_criteria_by_stage,
    delete_exam_criterion,
    delete_exam_board,
    get_exam_board,
    get_member,
    get_minutes,
    import_exam_criteria_batch,
    list_board_members,
    list_exam_boards,
    list_exam_criteria,
    list_grades,
    normalize_exam_stage,
    save_exam_board,
    save_grades,
    save_minutes,
    seed_exam_criteria,
    update_exam_criterion,
)
from src.pdf_generator import generate_board_pdf
from src.timezone import today_local
from src.ui import apply_app_style, paginate_dataframe, render_item_list
from src.utils import create_professor, format_date_br, list_advisors, list_all_students, rows_to_df, update_student_plan_partials


st.set_page_config(page_title="Bancas", layout="wide")
apply_app_style()
user = require_login()


@st.cache_resource
def bootstrap_boards_page() -> bool:
    seed_exam_criteria()
    return True


def to_dicts(rows) -> list[dict]:
    return [dict(row) for row in rows]


def calculate_plan_occupation_grade(partial_1: object, partial_2: object, board_average: object) -> float | None:
    if hasattr(boards_module, "calculate_plan_occupation_grade"):
        return boards_module.calculate_plan_occupation_grade(partial_1, partial_2, board_average)
    if board_average is None:
        return None

    def as_float(value: object) -> float:
        if value is None:
            return 0.0
        text = str(value).strip().replace(",", ".")
        if not text or text.lower() in {"nan", "none", "null"}:
            return 0.0
        return float(text)

    return round(as_float(partial_1) * 0.1 + as_float(partial_2) * 0.2 + as_float(board_average) * 0.7, 2)


@st.cache_data(ttl=60, show_spinner=False)
def cached_boards(scope: str, current_advisor_id: int | None) -> list[dict]:
    if scope == "coord":
        return to_dicts(list_exam_boards())
    return to_dicts(list_exam_boards({"advisor_id": current_advisor_id or -1}))


@st.cache_data(ttl=60, show_spinner=False)
def cached_board(board_id: int) -> dict | None:
    row = get_exam_board(board_id)
    return dict(row) if row else None


@st.cache_data(ttl=60, show_spinner=False)
def cached_board_members(board_id: int) -> list[dict]:
    return to_dicts(list_board_members(board_id))


@st.cache_data(ttl=60, show_spinner=False)
def cached_exam_criteria(stage: str, active_only: bool = True) -> list[dict]:
    return to_dicts(list_exam_criteria(stage, active_only=active_only))


@st.cache_data(ttl=20, show_spinner=False)
def cached_grades(board_id: int, current_advisor_id: int | None = None) -> list[dict]:
    return to_dicts(list_grades(board_id, current_advisor_id))


@st.cache_data(ttl=20, show_spinner=False)
def cached_minutes(board_id: int) -> dict | None:
    row = get_minutes(board_id)
    return dict(row) if row else None


@st.cache_data(ttl=20, show_spinner=False)
def cached_grade_summary(board_id: int) -> list[dict]:
    return to_dicts(board_grade_summary(board_id))


@st.cache_data(ttl=20, show_spinner=False)
def cached_board_status(board_id: int) -> dict:
    return board_status(board_id)


@st.cache_data(ttl=20, show_spinner=False)
def cached_board_partial_grade(board_id: int) -> dict | None:
    row = board_partial_grade(board_id)
    return dict(row) if row else None


@st.cache_data(ttl=60, show_spinner=False)
def cached_board_overview(board_id: int) -> dict:
    if hasattr(boards_module, "board_overview"):
        return boards_module.board_overview(board_id)
    status = dict(board_status(board_id))
    partial_grade = board_partial_grade(board_id)
    status["average_grade"] = partial_grade["average_grade"] if partial_grade else None
    status["grades_count"] = partial_grade["grades_count"] if partial_grade else 0
    return status


@st.cache_data(ttl=20, show_spinner=False)
def cached_results(scope: str, current_advisor_id: int | None) -> list[dict]:
    advisor_filter = None if scope == "coord" else current_advisor_id or -1
    return to_dicts(consolidated_results(advisor_filter))


@st.cache_data(ttl=20, show_spinner=False)
def cached_students() -> list[dict]:
    return to_dicts(list_all_students())


@st.cache_data(ttl=20, show_spinner=False)
def cached_advisors() -> list[dict]:
    return to_dicts(list_advisors())


def clear_read_cache() -> None:
    cached_boards.clear()
    cached_board.clear()
    cached_board_members.clear()
    cached_exam_criteria.clear()
    cached_grades.clear()
    cached_minutes.clear()
    cached_grade_summary.clear()
    cached_board_status.clear()
    cached_board_partial_grade.clear()
    cached_board_overview.clear()
    cached_results.clear()
    cached_students.clear()
    cached_advisors.clear()
    st.cache_data.clear()


bootstrap_boards_page()

st.title("Bancas")
st.caption("Avaliações, atas e acompanhamento das bancas de TFG.")
if st.session_state.pop("grades_saved", False):
    st.success("Notas salvas.")
if st.session_state.pop("minutes_saved", False):
    st.success("Ata salva.")
if st.session_state.pop("celebrate_minutes_saved", False):
    st.snow()
    st.success("Ata salva. Nota final maior ou igual a 7.")

advisor_id = advisor_id_for_user(user["id"])
is_coord = user["role"] == "coordenacao"
scope = "coord" if is_coord else "advisor"


def board_label(board: dict) -> str:
    time_part = f" {board['scheduled_time']}" if board["scheduled_time"] else ""
    return f"{format_date_br(board['scheduled_date'])}{time_part} | {board['stage']} | {board['student_name']} | {board['status']}"


def advisor_options() -> tuple[list[dict], dict[str, int]]:
    advisors = cached_advisors()
    return advisors, {f"{row['name']} ({row['email']})": row["id"] for row in advisors}


def normalize_lookup(value: object) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.replace("_", " ").split())


def normalize_batch_columns(df: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "aluno": "aluno",
        "estudante": "aluno",
        "orientando": "aluno",
        "etapa": "etapa",
        "banca": "etapa",
        "data": "data",
        "data banca": "data",
        "horario": "horario",
        "hora": "horario",
        "local": "local",
        "sala": "local",
        "orientador": "orientador",
        "avaliador 1": "avaliador_1",
        "avaliador1": "avaliador_1",
        "avaliador 2": "avaliador_2",
        "avaliador2": "avaliador_2",
        "avaliador 3": "avaliador_3",
        "avaliador3": "avaliador_3",
        "email avaliador 1": "email_avaliador_1",
        "email avaliador1": "email_avaliador_1",
        "email avaliador 2": "email_avaliador_2",
        "email avaliador2": "email_avaliador_2",
        "email avaliador 3": "email_avaliador_3",
        "email avaliador3": "email_avaliador_3",
    }
    renamed = {}
    for column in df.columns:
        normalized = normalize_lookup(column)
        renamed[column] = aliases.get(normalized, normalized.replace(" ", "_"))
    return df.rename(columns=renamed)


def parse_batch_date(value: object) -> date:
    text = str(value or "").strip()
    if not text:
        raise ValueError("data vazia")
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"data inválida: {text}")
    return parsed.date()


def build_batch_template(students: list[dict]) -> pd.DataFrame:
    sample_student = students[0] if students else {"name": "Nome do aluno", "advisor_name": "Orientador"}
    return pd.DataFrame(
        [
            {
                "aluno": sample_student["name"],
                "etapa": "Pré-Banca",
                "data": today_local().strftime("%d/%m/%Y"),
                "horario": "19:00",
                "local": "Sala 1",
                "orientador": sample_student.get("advisor_name", ""),
                "avaliador_1": "Nome do avaliador",
                "email_avaliador_1": "",
                "avaliador_2": "Nome do convidado externo",
                "email_avaliador_2": "convidado@email.com",
            }
        ]
    )


def build_exam_criteria_template() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "stage": "Pré-Banca",
                "criterion": "Domínio do conteúdo",
                "description": "Clareza, segurança e domínio da pesquisa apresentada.",
                "active": 1,
            }
        ]
    )


def import_exam_boards_batch(df: pd.DataFrame, students: list[dict], advisors: list[dict], user_id: int) -> dict:
    if df.empty:
        raise ValueError("Envie uma planilha antes de importar.")

    df = df.copy().fillna("")
    df = normalize_batch_columns(df)
    required = {"aluno", "etapa", "data", "horario"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes: {', '.join(sorted(missing))}")

    student_by_name = {normalize_lookup(row["name"]): row for row in students}
    advisor_by_name = {normalize_lookup(row["name"]): row["id"] for row in advisors}
    advisor_by_email = {normalize_lookup(row["email"]): row["id"] for row in advisors}
    created = 0
    errors = []
    created_advisors = 0

    for index, row in df.iterrows():
        line = index + 2
        try:
            student = student_by_name.get(normalize_lookup(row.get("aluno")))
            if not student:
                raise ValueError(f"aluno não encontrado: {row.get('aluno')}")
            stage = normalize_exam_stage(str(row.get("etapa", "")))
            scheduled_date = parse_batch_date(row.get("data"))
            scheduled_time = str(row.get("horario", "")).strip()
            location = str(row.get("local", "")).strip()
            orientador_text = str(row.get("orientador", "")).strip()
            orientador_id = student["advisor_id"]
            if orientador_text:
                orientador_id = advisor_by_name.get(normalize_lookup(orientador_text)) or advisor_by_email.get(normalize_lookup(orientador_text))
                if not orientador_id:
                    raise ValueError(f"orientador não encontrado: {orientador_text}")

            evaluator_ids = []
            for number in (1, 2, 3):
                name = str(row.get(f"avaliador_{number}", "")).strip()
                email = str(row.get(f"email_avaliador_{number}", "")).strip()
                if not name and not email:
                    continue
                evaluator_id = advisor_by_email.get(normalize_lookup(email)) if email else None
                if not evaluator_id and name:
                    evaluator_id = advisor_by_name.get(normalize_lookup(name))
                if not evaluator_id:
                    evaluator_id = create_professor(name or email, email, "professor123")
                    created_advisors += 1
                    advisor_by_name[normalize_lookup(name or email)] = evaluator_id
                    if email:
                        advisor_by_email[normalize_lookup(email)] = evaluator_id
                evaluator_ids.append(evaluator_id)

            save_exam_board(student["id"], stage, scheduled_date, scheduled_time, location, orientador_id, evaluator_ids, user_id)
            created += 1
        except Exception as exc:
            errors.append(f"Linha {line}: {exc}")

    return {"created": created, "errors": errors, "created_advisors": created_advisors}


sections = ["Minhas bancas", "Calendário", "Dashboard"]
if is_coord:
    sections.extend(["Gerenciar", "Critérios"])

section = st.radio("Área", sections, horizontal=True, label_visibility="collapsed")


if section == "Minhas bancas":
    if not is_coord and advisor_id is None:
        st.warning("Seu usuário ainda não está vinculado a um cadastro de professor.")
    else:
        boards = cached_boards(scope, advisor_id)
        if not boards:
            st.info("Nenhuma banca encontrada para este usuário.")
        else:
            board_by_id = {int(item["id"]): item for item in boards}
            board_ids = list(board_by_id.keys())
            if st.session_state.get("selected_exam_board_id") not in board_ids:
                st.session_state["selected_exam_board_id"] = board_ids[0]
            selected_board_id = st.selectbox(
                "Banca",
                board_ids,
                format_func=lambda board_id: board_label(board_by_id[int(board_id)]),
                key="selected_exam_board_id",
            )
            board = cached_board(int(selected_board_id))
            if not board:
                st.warning("Banca não encontrada.")
                st.stop()

            overview = cached_board_overview(board["id"])
            status = overview
            partial_average = overview["average_grade"] if overview.get("average_grade") is not None else None
            is_plan_occupation = "plano" in str(board["stage"]).lower() and "ocupa" in str(board["stage"]).lower()
            plan_occupation_grade = calculate_plan_occupation_grade(
                board.get("plan_partial_1"),
                board.get("plan_partial_2"),
                partial_average,
            ) if is_plan_occupation else None
            metric_columns = st.columns(6 if is_plan_occupation else 5)
            metric_columns[0].metric("Aluno", board["student_name"])
            metric_columns[1].metric("Etapa", board["stage"])
            metric_columns[2].metric("Data", format_date_br(board["scheduled_date"]))
            metric_columns[3].metric("Status", status["status"])
            metric_columns[4].metric("Média da banca", "-" if partial_average is None else f"{float(partial_average):.2f}")
            if is_plan_occupation:
                metric_columns[5].metric("Nota final", "-" if plan_occupation_grade is None else f"{plan_occupation_grade:.2f}")

            st.markdown("**Composição da nota**")
            if is_plan_occupation:
                partial_1_value = float(board.get("plan_partial_1") or 0)
                partial_2_value = float(board.get("plan_partial_2") or 0)
                board_average_value = None if partial_average is None else float(partial_average)
                composition_rows = [
                    {
                        "Componente": "Parcial 1 x 0,1",
                        "Nota bruta": f"{partial_1_value:.2f}",
                        "Valor ponderado": f"{partial_1_value * 0.1:.2f}",
                    },
                    {
                        "Componente": "Parcial 2 x 0,2",
                        "Nota bruta": f"{partial_2_value:.2f}",
                        "Valor ponderado": f"{partial_2_value * 0.2:.2f}",
                    },
                    {
                        "Componente": "Média dos avaliadores x 0,7",
                        "Nota bruta": "-" if board_average_value is None else f"{board_average_value:.2f}",
                        "Valor ponderado": "-" if board_average_value is None else f"{board_average_value * 0.7:.2f}",
                    },
                    {
                        "Componente": "Nota final",
                        "Nota bruta": "-",
                        "Valor ponderado": "-" if plan_occupation_grade is None else f"{plan_occupation_grade:.2f}",
                    },
                ]
            else:
                composition_rows = [
                    {
                        "Componente": "Média da banca",
                        "Peso": "100%",
                        "Nota considerada": "-" if partial_average is None else f"{float(partial_average):.2f}",
                    },
                    {
                        "Componente": "Nota final",
                        "Peso": "100%",
                        "Nota considerada": "-" if partial_average is None else f"{float(partial_average):.2f}",
                    },
                ]
            st.dataframe(pd.DataFrame(composition_rows), width="stretch", hide_index=True)
            st.write(f"**Tema:** {board['theme']}")
            if board["location"]:
                st.write(f"**Local:** {board['location']}")

            notes_status = "Pendente"
            if status["total_criteria"] > 0 and status["sent"] and not status["pending"]:
                notes_status = "Completa"
            elif status["sent"]:
                notes_status = "Parcial"
            pdf_path_value = st.session_state.get(f"board_pdf_{board['id']}")
            pdf_status = "Registrada" if pdf_path_value and Path(pdf_path_value).exists() else "Pendente"
            st.subheader("Fluxo da banca")
            render_item_list(
                [
                    {
                        "title": "Dados da banca",
                        "meta": f"{format_date_br(board['scheduled_date'])} {board['scheduled_time'] or ''} | {board['location'] or '-'}",
                        "status": "Completa",
                    },
                    {
                        "title": "Notas",
                        "meta": f"{len(status['sent'])}/{status['total_evaluators']} avaliador(es) com nota completa",
                        "status": notes_status,
                    },
                    {
                        "title": "Ata",
                        "meta": "Registrada pelo orientador" if status["minutes"] else "Aguardando registro",
                        "status": "Registrada" if status["minutes"] else "Pendente",
                    },
                    {
                        "title": "PDF",
                        "meta": "Relatório disponível para download" if pdf_status == "Registrada" else "Gerado sob demanda",
                        "status": pdf_status,
                    },
                ]
            )

            members = cached_board_members(board["id"])
            st.subheader("Composição da banca")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Nome": member["name"],
                            "Papel": "Orientador" if member["can_record_minutes"] else "Avaliador",
                            "Lança nota": "Sim" if member["can_grade"] else "Não",
                            "Ata": "Sim" if member["can_record_minutes"] else "Não",
                        }
                        for member in members
                    ]
                ),
                width="stretch",
                hide_index=True,
            )

            member = get_member(board["id"], advisor_id) if advisor_id else None
            if is_coord and not member:
                st.info("Coordenação visualiza esta banca em modo acompanhamento. Para lançar nota ou ata, vincule seu professor à banca.")

            if member and member["can_grade"]:
                st.subheader("Lançar notas")
                criteria = cached_exam_criteria(board["stage"])
                existing = {row["criterion_id"]: row for row in cached_grades(board["id"], advisor_id)}
                if not criteria:
                    st.warning("Nenhum critério ativo cadastrado para esta etapa.")
                else:
                    grades = {}
                    for criterion in criteria:
                        current = existing.get(criterion["id"], {})
                        st.markdown(f"**{criterion['criterion']}**")
                        st.caption(criterion["description"])
                        cols = st.columns([1, 2])
                        grades[criterion["id"]] = {
                            "grade": cols[0].number_input(
                                "Nota",
                                min_value=0.0,
                                max_value=10.0,
                                value=float(current.get("grade", 6.0) or 6.0),
                                step=1.0,
                                format="%.1f",
                                key=f"grade_{board['id']}_{criterion['id']}",
                            ),
                            "observation": cols[1].text_input(
                                "Observação",
                                value=current.get("observation", "") or "",
                                key=f"grade_obs_{board['id']}_{criterion['id']}",
                            ).strip(),
                        }

                    current_values = [float(item["grade"]) for item in grades.values()]
                    evaluator_preview = sum(current_values) / len(current_values)
                    st.metric("Sua média prévia", f"{evaluator_preview:.2f}")
                    st.caption(
                        f"Cálculo local: média aritmética simples dos {len(current_values)} critério(s) preenchidos. "
                        "A prévia parcial da banca é atualizada após salvar as notas."
                    )

                    st.caption("As alterações nas notas só são gravadas ao clicar em Salvar notas.")

                    if st.button("Salvar notas", key=f"save_grades_{board['id']}_{advisor_id}"):
                        try:
                            save_grades(board["id"], advisor_id, grades)
                            st.session_state["grades_saved"] = True
                            clear_read_cache()
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))

            if member and member["can_record_minutes"]:
                st.subheader("Ata da banca")
                minutes = cached_minutes(board["id"])
                minutes_key = f"board_minutes_{board['id']}"
                if minutes_key not in st.session_state:
                    st.session_state[minutes_key] = minutes["minutes_text"] if minutes else ""
                text = st.text_area(
                    "Ata",
                    key=minutes_key,
                    height=260,
                    placeholder="Registre decisões, observações, encaminhamentos e recomendações da banca.",
                )
                st.caption("As alterações na ata só são gravadas ao clicar em Salvar ata.")
                submitted = st.button("Salvar ata", key=f"save_minutes_{board['id']}")
                if submitted:
                    try:
                        save_minutes(board["id"], advisor_id, text)
                        final_average = partial_average
                        final_result = calculate_plan_occupation_grade(
                            board.get("plan_partial_1"),
                            board.get("plan_partial_2"),
                            final_average,
                        ) if is_plan_occupation else final_average
                        if final_result is not None and float(final_result) >= 7:
                            st.session_state["celebrate_minutes_saved"] = True
                        else:
                            st.session_state["minutes_saved"] = True
                        clear_read_cache()
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

                st.subheader("Relatório da banca")
                if st.button("Gerar relatório em PDF", key=f"generate_board_pdf_{board['id']}"):
                    try:
                        pdf_path = generate_board_pdf(board["id"])
                        st.session_state[f"board_pdf_{board['id']}"] = str(pdf_path)
                        st.success(f"Relatório gerado: {pdf_path.name}")
                    except Exception as exc:
                        st.error(str(exc))

                pdf_path_value = st.session_state.get(f"board_pdf_{board['id']}")
                if pdf_path_value:
                    pdf_path = Path(pdf_path_value)
                    if pdf_path.exists():
                        st.download_button(
                            "Baixar relatório em PDF",
                            pdf_path.read_bytes(),
                            file_name=pdf_path.name,
                            mime="application/pdf",
                            key=f"download_board_pdf_{board['id']}",
                        )

            st.subheader("Resumo das notas")
            summary = rows_to_df(cached_grade_summary(board["id"]))
            if summary.empty:
                st.info("Ainda não há notas lançadas.")
            else:
                summary["average_grade"] = summary["average_grade"].astype(float).round(2)
                st.dataframe(summary, width="stretch", hide_index=True)

elif section == "Calendário":
    reference = st.date_input("Semana de referência", value=today_local(), format="DD/MM/YYYY")
    start = reference - timedelta(days=reference.weekday())
    end = start + timedelta(days=6)
    rows = []
    for board in cached_boards(scope, advisor_id):
        try:
            scheduled = date.fromisoformat(board["scheduled_date"][:10])
        except ValueError:
            continue
        if start <= scheduled <= end:
            rows.append(
                {
                    "Data": format_date_br(board["scheduled_date"]),
                    "Horário": board["scheduled_time"] or "-",
                    "Etapa": board["stage"],
                    "Aluno": board["student_name"],
                    "Tema": board["theme"],
                    "Status": board["status"],
                }
            )
    st.write(f"Semana de {start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}")
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.info("Nenhuma banca encontrada nesta semana.")

elif section == "Dashboard":
    results = rows_to_df(cached_results(scope, advisor_id))
    if results.empty:
        st.info("Nenhuma banca cadastrada.")
    else:
        col1, col2, col3 = st.columns(3)
        col1.metric("Bancas", len(results))
        col2.metric("Completas", int((results["status"] == "Completa").sum()))
        col3.metric("Pendentes/parciais", int((results["status"] != "Completa").sum()))
        results["average_grade"] = pd.to_numeric(results["average_grade"], errors="coerce").round(2)
        st.dataframe(
            paginate_dataframe(
                results.rename(
                columns={
                    "student_name": "Aluno",
                    "stage": "Etapa",
                    "status": "Status",
                    "average_grade": "Média",
                    "evaluators_with_grade": "Avaliadores com nota",
                    "grades_count": "Notas registradas",
                    "minutes_status": "Ata",
                }
                ),
                "board_results",
            ),
            width="stretch",
            hide_index=True,
        )
        plan_source = results[(results["tfg_stage"] == "TFG I") & (results["stage"] == "Plano de Ocupação")].copy()
        if not plan_source.empty:
            plan_source["plan_partial_1"] = pd.to_numeric(plan_source["plan_partial_1"], errors="coerce")
            plan_source["plan_partial_2"] = pd.to_numeric(plan_source["plan_partial_2"], errors="coerce")
            plan_source["nota_plano_ocupacao"] = (
                plan_source["plan_partial_1"].fillna(0) * 0.1
                + plan_source["plan_partial_2"].fillna(0) * 0.2
                + plan_source["average_grade"].fillna(0) * 0.7
            ).round(2)
            st.subheader("Consolidação Plano de Ocupação - TFG I")
            consolidation = plan_source[[
                "student_name",
                "plan_partial_1",
                "plan_partial_2",
                "average_grade",
                "nota_plano_ocupacao",
            ]].rename(columns={
                "student_name": "Aluno",
                "plan_partial_1": "Parcial 1 (10%)",
                "plan_partial_2": "Parcial 2 (20%)",
                "average_grade": "Banca final (70%)",
                "nota_plano_ocupacao": "Nota Plano de Ocupação",
            })
            st.dataframe(
                paginate_dataframe(consolidation, "board_tfg_consolidation"),
                width="stretch",
                hide_index=True,
            )

elif is_coord and section == "Gerenciar":
    st.subheader("Criar bancas em lote")
    students = cached_students()
    advisors, advisor_map = advisor_options()

    if not students:
        st.warning("Cadastre alunos antes de criar bancas.")
    elif not advisors:
        st.warning("Cadastre professores ou convidados antes de criar bancas.")
    else:
        template = build_batch_template(students)
        st.download_button("Baixar modelo CSV", template.to_csv(index=False).encode("utf-8-sig"), "modelo_bancas.csv", "text/csv")
        uploaded_boards = st.file_uploader(
            "Arquivo CSV ou XLSX das bancas",
            type=["csv", "xlsx"],
            key="exam_boards_batch_upload",
            help="Colunas obrigatórias: aluno, etapa, data, horario. Avaliadores externos são criados se nome/e-mail não existirem.",
        )
        boards_df = None
        if uploaded_boards:
            try:
                if uploaded_boards.name.lower().endswith(".csv"):
                    boards_df = pd.read_csv(uploaded_boards, dtype=str).fillna("")
                else:
                    boards_df = pd.read_excel(uploaded_boards, dtype=str).fillna("")
                preview = normalize_batch_columns(boards_df)
                st.dataframe(preview, width="stretch", hide_index=True)
            except Exception as exc:
                st.warning(f"Não consegui pré-visualizar a tabela: {exc}")

        if st.button("Importar bancas em lote", disabled=boards_df is None):
            try:
                result = import_exam_boards_batch(boards_df, students, advisors, user["id"])
                clear_read_cache()
                if result["created"]:
                    st.success(
                        f"{result['created']} banca(s) criada(s)/atualizada(s). "
                        f"{result['created_advisors']} convidado(s)/professor(es) criado(s)."
                    )
                if result["errors"]:
                    st.error("Algumas linhas não foram importadas.")
                    for error in result["errors"]:
                        st.write(error)
                if result["created"] and not result["errors"]:
                    st.rerun()
            except Exception as exc:
                st.error(str(exc))

        st.divider()
        st.subheader("Criar ou atualizar uma banca")
        student_options = {f"{student['name']} | {student['tfg_stage']} | {student['advisor_name']}": student for student in students}
        advisor_labels = list(advisor_map.keys())
        boards_for_form = cached_boards("coord", None)
        board_options = {"Nova banca": None}
        board_options.update({board_label(board): board for board in boards_for_form})
        selected_board_label = st.selectbox("Banca para editar", list(board_options.keys()), key="edit_board_select")
        editing_board = board_options[selected_board_label]
        editing_members = cached_board_members(editing_board["id"]) if editing_board else []
        editing_orientador_id = next((member["advisor_id"] for member in editing_members if member["can_record_minutes"]), None)
        editing_evaluator_ids = [member["advisor_id"] for member in editing_members if member["can_grade"]]

        student_labels = list(student_options.keys())
        default_student_index = 0
        default_stage_index = 0
        default_date = today_local()
        default_time = ""
        default_location = ""
        if editing_board:
            for index, label in enumerate(student_labels):
                if int(student_options[label]["id"]) == int(editing_board["student_id"]):
                    default_student_index = index
                    break
            default_stage_index = EXAM_STAGES.index(editing_board["stage"]) if editing_board["stage"] in EXAM_STAGES else 0
            try:
                default_date = date.fromisoformat(str(editing_board["scheduled_date"])[:10])
            except ValueError:
                default_date = today_local()
            default_time = editing_board["scheduled_time"] or ""
            default_location = editing_board["location"] or ""

        with st.form("exam_board_form"):
            selected_student_label = st.selectbox("Aluno", student_labels, index=default_student_index)
            student = student_options[selected_student_label]
            stage = st.selectbox("Etapa da banca", EXAM_STAGES, index=default_stage_index)
            scheduled_date = st.date_input("Data", value=default_date, format="DD/MM/YYYY")
            scheduled_time = st.text_input("Horário", value=default_time, placeholder="19:00")
            location = st.text_input("Local", value=default_location, placeholder="Sala, link ou observação")

            default_orientador_index = 0
            target_orientador_id = editing_orientador_id or student["advisor_id"]
            for index, label in enumerate(advisor_labels):
                if advisor_map[label] == target_orientador_id:
                    default_orientador_index = index
                    break
            orientador_label = st.selectbox("Orientador responsável pela ata", advisor_labels, index=default_orientador_index)
            default_evaluators = [label for label in advisor_labels if advisor_map[label] in editing_evaluator_ids]
            evaluator_labels = st.multiselect(
                "Avaliadores",
                advisor_labels,
                default=default_evaluators,
                help="Convidados externos devem ser cadastrados como professores em Cadastros ou criados pelo importador em lote.",
            )
            submitted = st.form_submit_button("Salvar banca")

        if submitted:
            try:
                save_exam_board(
                    student["id"],
                    stage,
                    scheduled_date,
                    scheduled_time,
                    location,
                    advisor_map[orientador_label],
                    [advisor_map[label] for label in evaluator_labels],
                    user["id"],
                )
                clear_read_cache()
                st.success("Banca salva.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        st.divider()
        st.subheader("Notas parciais - Plano de Ocupação")
        tfg1_students = [item for item in students if item["tfg_stage"] == "TFG I"]
        if not tfg1_students:
            st.info("Nenhum aluno de TFG I encontrado para lançamento das parciais.")
        else:
            partial_options = {f"{item['name']} | {item['advisor_name']} | {item['year']}/{item['semester']}": item for item in tfg1_students}
            selected_partial_label = st.selectbox("Aluno", list(partial_options.keys()), key="plan_partial_student")
            selected_partial_student = partial_options[selected_partial_label]
            with st.form("plan_partial_form"):
                partial_1 = st.text_input(
                    "Parcial 1 (peso 0,1)",
                    value="" if selected_partial_student["plan_partial_1"] is None else str(selected_partial_student["plan_partial_1"]),
                )
                partial_2 = st.text_input(
                    "Parcial 2 (peso 0,2)",
                    value="" if selected_partial_student["plan_partial_2"] is None else str(selected_partial_student["plan_partial_2"]),
                )
                partial_submitted = st.form_submit_button("Salvar notas parciais")
            if partial_submitted:
                try:
                    update_student_plan_partials(selected_partial_student["id"], partial_1, partial_2)
                    clear_read_cache()
                    st.success("Notas parciais salvas.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    st.subheader("Bancas cadastradas")
    boards = cached_boards("coord", None)
    if boards:
        selected = st.selectbox("Selecionar banca", list(range(len(boards))), format_func=lambda idx: board_label(boards[idx]), key="manage_board")
        board = boards[selected]
        st.dataframe(rows_to_df(cached_board_members(board["id"])), width="stretch")
        confirm = st.checkbox("Confirmo que quero excluir esta banca e seus lançamentos.")
        if st.button("Excluir banca", disabled=not confirm):
            delete_exam_board(board["id"], user["id"])
            clear_read_cache()
            st.success("Banca excluída.")
            st.rerun()
    else:
        st.info("Nenhuma banca cadastrada.")

elif is_coord and section == "Critérios":
    st.subheader("Critérios de avaliação")
    stage_filter = st.selectbox("Etapa", EXAM_STAGES, key="criteria_stage")
    criteria = cached_exam_criteria(stage_filter, active_only=False)
    criteria_df = rows_to_df(criteria)
    st.dataframe(paginate_dataframe(criteria_df, "exam_criteria"), width="stretch")

    st.subheader("Importar critérios de banca em lote")
    criteria_template = build_exam_criteria_template()
    st.download_button(
        "Baixar modelo CSV de critérios",
        criteria_template.to_csv(index=False).encode("utf-8-sig"),
        "modelo_criterios_banca.csv",
        "text/csv",
    )
    uploaded_criteria = st.file_uploader("Arquivo CSV ou XLSX dos critérios de banca", type=["csv", "xlsx"], key="exam_criteria_upload")
    if uploaded_criteria:
        try:
            if uploaded_criteria.name.lower().endswith(".csv"):
                criteria_df = pd.read_csv(uploaded_criteria, dtype=str).fillna("")
            else:
                criteria_df = pd.read_excel(uploaded_criteria, dtype=str).fillna("")
            st.dataframe(criteria_df, width="stretch")
            if st.button("Importar critérios de banca"):
                result = import_exam_criteria_batch(criteria_df)
                clear_read_cache()
                st.success(f"Importação concluída: {result['criteria']} critério(s) de banca criado(s).")
                st.rerun()
        except Exception as exc:
            st.error(str(exc))

    st.subheader("Novo critério")
    with st.form("new_exam_criterion"):
        criterion = st.text_input("Critério")
        description = st.text_area("Descrição")
        active = st.checkbox("Ativo", value=True)
        submitted = st.form_submit_button("Cadastrar")
    if submitted:
        try:
            create_exam_criterion(stage_filter, criterion, description, active)
            clear_read_cache()
            st.success("Critério cadastrado.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    if criteria:
        st.subheader("Editar critério")
        criteria_options = {item["criterion"]: item for item in criteria}
        selected_label = st.selectbox("Critério", list(criteria_options.keys()))
        selected = criteria_options[selected_label]
        with st.form(f"edit_exam_criterion_{selected['id']}"):
            edit_stage = st.selectbox("Etapa", EXAM_STAGES, index=EXAM_STAGES.index(selected["stage"]))
            edit_criterion = st.text_input("Critério", value=selected["criterion"])
            edit_description = st.text_area("Descrição", value=selected["description"])
            edit_active = st.checkbox("Ativo", value=bool(selected["active"]))
            edit_submitted = st.form_submit_button("Salvar alterações")
        if edit_submitted:
            try:
                update_exam_criterion(selected["id"], edit_stage, edit_criterion, edit_description, edit_active)
                clear_read_cache()
                st.success("Critério atualizado.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        st.subheader("Excluir critério")
        confirm_delete_criterion = st.checkbox(
            "Confirmo que quero excluir este critério de banca.",
            key=f"confirm_delete_exam_criterion_{selected['id']}",
        )
        if st.button("Excluir critério selecionado", disabled=not confirm_delete_criterion):
            try:
                delete_exam_criterion(selected["id"])
                clear_read_cache()
                st.success("Critério de banca excluído.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.subheader("Excluir todos os critérios da etapa")
    st.warning("Esta ação remove todos os critérios da etapa selecionada, desde que nenhum deles tenha notas lançadas.")
    confirm_delete_all = st.checkbox(
        f"Confirmo que quero excluir todos os critérios de {stage_filter}.",
        key=f"confirm_delete_all_exam_criteria_{stage_filter}",
    )
    if st.button("Excluir todos os critérios da etapa", disabled=not confirm_delete_all):
        try:
            total_deleted = delete_exam_criteria_by_stage(stage_filter)
            clear_read_cache()
            st.success(f"{total_deleted} critério(s) de banca excluído(s).")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

render_footer()
