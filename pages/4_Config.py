from __future__ import annotations

from datetime import date

import streamlit as st

from src.auth import change_password, render_footer, require_login
from src.audit import list_audit
from src.boards import public_exam_calendar_enabled, set_public_exam_calendar_enabled
from src.database import DB_PATH, database_label, get_database_backend, init_db, query, set_database_backend
from src.google_sheets import get_google_sheet_url, import_from_google_sheets, save_google_sheet_url
from src.seed import (
    clear_advisory_criteria,
    clear_advisory_records,
    clear_audit_log,
    clear_exam_boards,
    clear_exam_criteria,
    clear_orientations,
    clear_pdf_exports,
    clear_professors,
    clear_students,
    reset_academic_data,
    reset_exam_results,
    reset_database,
    seed_initial_data,
)
from src.utils import default_calendar_dates, get_advisory_calendar, rows_to_df, save_advisory_calendar


st.set_page_config(page_title="Configurações", layout="wide")
user = require_login()

st.title("Configurações")
st.write(f"Banco em uso: `{database_label()}`")

st.subheader("Minha senha")
with st.form("change_password_form"):
    current_password = st.text_input("Senha atual", type="password")
    new_password = st.text_input("Nova senha", type="password")
    confirm_password = st.text_input("Confirmar nova senha", type="password")
    change_submitted = st.form_submit_button("Alterar senha")
if change_submitted:
    if new_password != confirm_password:
        st.error("A confirmação não confere com a nova senha.")
    else:
        ok, message = change_password(user["id"], current_password, new_password)
        if ok:
            st.success(message)
        else:
            st.error(message)

if user["role"] == "coordenacao":
    st.subheader("Banco de dados")
    backend_options = {
        "SQLite local (rápido e seguro para operação diária)": "sqlite",
        "Neon/PostgreSQL (nuvem)": "neon",
    }
    current_backend = get_database_backend()
    selected_backend_label = st.selectbox(
        "Backend ativo",
        list(backend_options.keys()),
        index=0 if current_backend == "sqlite" else 1,
    )
    st.caption(f"Arquivo local SQLite: `{DB_PATH}`")
    if st.button("Salvar backend do banco"):
        selected_backend = backend_options[selected_backend_label]
        try:
            set_database_backend(selected_backend)
            init_db()
            seed_initial_data()
            st.success(f"Backend alterado para {selected_backend.upper()}.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    settings = query("SELECT key, value FROM settings ORDER BY key")
    st.subheader("Configurações básicas")
    st.dataframe(rows_to_df(settings), width="stretch")

    st.subheader("Calendário público de bancas")
    st.caption("Quando ligado, visitantes veem o calendário semanal de bancas antes do login.")
    public_calendar = st.toggle(
        "Mostrar calendário público de bancas",
        value=public_exam_calendar_enabled(),
    )
    if st.button("Salvar calendário público"):
        set_public_exam_calendar_enabled(public_calendar)
        if public_calendar:
            st.success("Calendário público de bancas ativado.")
        else:
            st.warning("Calendário público de bancas desativado.")
        st.rerun()

    st.subheader("Calendario de assessorias")
    st.caption("Defina as datas gerais do semestre. TFG I acontece mensalmente; TFG II acontece semanalmente.")
    cal_col1, cal_col2 = st.columns(2)
    calendar_year = cal_col1.number_input("Ano do calendario", min_value=2020, max_value=2100, value=2026)
    calendar_semester = cal_col2.selectbox("Semestre do calendario", [1, 2], key="calendar_semester")

    def parse_calendar_date(value: str, fallback: date) -> date:
        try:
            return date.fromisoformat(value[:10])
        except (TypeError, ValueError):
            return fallback

    for stage, label, start_key in [
        ("TFG I", "TFG I - 4 assessorias mensais", "calendar_start_tfg_i"),
        ("TFG II", "TFG II - 10 assessorias semanais", "calendar_start_tfg_ii"),
    ]:
        with st.expander(label, expanded=False):
            current_calendar = get_advisory_calendar(int(calendar_year), int(calendar_semester), stage)
            fallback_start = date(int(calendar_year), 3 if int(calendar_semester) == 1 else 8, 1)
            start_date = st.date_input("Data da primeira assessoria", value=fallback_start, format="DD/MM/YYYY", key=start_key)
            if st.button(f"Gerar datas automaticas - {stage}", key=f"generate_{stage}"):
                for item, generated_date in zip(current_calendar, default_calendar_dates(start_date, stage)):
                    st.session_state[f"calendar_{stage}_{item['session_number']}"] = generated_date
                st.rerun()

            st.write("Datas planejadas")
            date_values = {}
            for item in current_calendar:
                key = f"calendar_{stage}_{item['session_number']}"
                default_value = st.session_state.get(
                    key,
                    parse_calendar_date(item["planned_date"], fallback_start),
                )
                cols = st.columns([1, 3, 2])
                cols[0].write(f"#{item['session_number']}")
                cols[1].write(item["phase"])
                date_values[item["session_number"]] = cols[2].date_input(
                    "Data",
                    value=default_value,
                    format="DD/MM/YYYY",
                    key=key,
                    label_visibility="collapsed",
                )
            if st.button(f"Salvar calendario - {stage}", key=f"save_calendar_{stage}"):
                total_updated = save_advisory_calendar(
                    int(calendar_year),
                    int(calendar_semester),
                    stage,
                    date_values,
                    user["id"],
                )
                st.success(f"Calendario salvo para {stage}. {total_updated} assessoria(s) atualizada(s).")

    st.subheader("Google Sheets")
    st.caption("Uso exclusivo da coordenação. Cole o link da planilha com as abas Alunos e Criterios. A planilha deve estar compartilhada para qualquer pessoa com o link.")
    with st.form("google_sheet_config"):
        sheet_url = st.text_input(
            "Link ou ID da planilha Google",
            value=get_google_sheet_url(),
            placeholder="https://docs.google.com/spreadsheets/d/...",
        )
        saved = st.form_submit_button("Salvar planilha")
    if saved:
        save_google_sheet_url(sheet_url)
        st.success("Link da planilha salvo nas configurações.")

    confirm_import = st.checkbox("Estou ciente de que a importação substitui alunos, critérios, assessorias e fichas atuais.")
    if st.button("Importar dados do Google Sheets", disabled=not confirm_import):
        with st.spinner("Importando planilha..."):
            result = import_from_google_sheets()
        if result["ok"]:
            st.success(result["message"])
        else:
            st.error(result["message"])

    col1, col2 = st.columns(2)
    if col1.button("Inicializar banco se necessário"):
        init_db()
        seed_initial_data()
        st.success("Banco inicializado/verificado.")

    danger = col2.checkbox("Estou ciente de que isso apaga os dados mockados atuais.")
    if col2.button("Recriar dados mockados", disabled=not danger):
        reset_database()
        st.success("Dados mockados recriados.")

    st.subheader("Reset acadêmico")
    st.warning("Remove alunos, professores, orientações, critérios, assessorias, fichas, PDFs registrados e auditoria. A coordenação e as configurações são preservadas.")
    confirm_academic_reset = st.checkbox("Confirmo que quero limpar alunos, professores e fichas atuais.")
    if st.button("Resetar alunos, professores e fichas", disabled=not confirm_academic_reset):
        reset_academic_data()
        st.success("Base acadêmica resetada. A coordenação foi preservada.")

    st.subheader("Limpezas seletivas")
    st.warning("Use com cuidado. As ações abaixo apagam dados do banco ativo e não desfazem automaticamente.")

    cleanup_options = [
        {
            "title": "Reiniciar bancas do zero",
            "description": "Remove apenas notas e atas. Preserva bancas cadastradas, alunos, membros avaliadores, horários, locais e critérios.",
            "note": "Use quando quiser manter a agenda das bancas, mas refazer todos os lançamentos.",
            "confirm": "reiniciar bancas",
            "button": "Reiniciar bancas",
            "action": reset_exam_results,
        },
        {
            "title": "Reiniciar orientações do zero",
            "description": "Remove fichas preenchidas, respostas e PDFs registrados. Preserva alunos, professores, orientações e as assessorias geradas.",
            "note": "Use quando quiser manter quem orienta quem, mas refazer as fichas das assessorias.",
            "confirm": "reiniciar orientacoes",
            "button": "Reiniciar orientações",
            "action": clear_advisory_records,
        },
        {
            "title": "Excluir bancas cadastradas",
            "description": "Remove bancas, membros, notas e atas. Preserva alunos, professores e critérios de banca.",
            "note": "Use somente quando quiser apagar a agenda das bancas e cadastrar tudo novamente.",
            "confirm": "excluir bancas",
            "button": "Excluir bancas",
            "action": clear_exam_boards,
        },
        {
            "title": "Limpar critérios de banca",
            "description": "Remove critérios de banca e notas vinculadas. As bancas cadastradas são preservadas.",
            "note": "Use quando quiser trocar a rubrica/grade avaliativa das bancas.",
            "confirm": "limpar criterios de banca",
            "button": "Limpar critérios de banca",
            "action": clear_exam_criteria,
        },
        {
            "title": "Limpar alunos",
            "description": "Remove alunos, orientações, assessorias, fichas, bancas, notas e atas. Preserva professores, critérios e configurações.",
            "note": "Use em troca de turma ou quando a base de alunos foi importada errada.",
            "confirm": "limpar alunos",
            "button": "Limpar alunos",
            "action": clear_students,
        },
        {
            "title": "Limpar professores",
            "description": "Remove professores e vínculos dependentes, incluindo orientações, assessorias, fichas, bancas, notas e atas. Preserva coordenação, alunos, critérios e configurações.",
            "note": "Use quando a base de professores/avaliadores precisa ser refeita.",
            "confirm": "limpar professores",
            "button": "Limpar professores",
            "action": clear_professors,
        },
        {
            "title": "Excluir orientações",
            "description": "Remove orientações, assessorias e fichas. Preserva alunos, professores, bancas e critérios.",
            "note": "Use quando quiser refazer a relação aluno-orientador do zero.",
            "confirm": "excluir orientacoes",
            "button": "Excluir orientações",
            "action": clear_orientations,
        },
        {
            "title": "Limpar critérios de assessoria",
            "description": "Remove critérios de assessoria e respostas vinculadas. Preserva alunos, professores e orientações.",
            "note": "Use quando quiser trocar a rubrica/grade das fichas de assessoria.",
            "confirm": "limpar criterios de assessoria",
            "button": "Limpar critérios de assessoria",
            "action": clear_advisory_criteria,
        },
        {
            "title": "Limpar PDFs registrados",
            "description": "Remove apenas os registros de PDFs gerados no banco. Arquivos já criados na pasta output não são apagados.",
            "note": "Use para limpar histórico de exportações sem alterar os dados acadêmicos.",
            "confirm": "limpar pdfs",
            "button": "Limpar PDFs registrados",
            "action": clear_pdf_exports,
        },
        {
            "title": "Limpar auditoria",
            "description": "Remove o histórico de auditoria. Não altera alunos, professores, fichas ou bancas.",
            "note": "Use apenas se você não precisa mais do histórico de ações administrativas.",
            "confirm": "limpar auditoria",
            "button": "Limpar auditoria",
            "action": clear_audit_log,
        },
    ]

    for index, option in enumerate(cleanup_options):
        with st.expander(option["title"], expanded=False):
            st.write(option["description"])
            st.caption(option["note"])
            confirmation = st.text_input(
                f"Digite `{option['confirm']}` para confirmar",
                key=f"cleanup_confirm_{index}",
            )
            if st.button(option["button"], disabled=confirmation.strip().lower() != option["confirm"], key=f"cleanup_button_{index}"):
                try:
                    option["action"]()
                    st.success(f"{option['title']} concluído.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    st.subheader("Auditoria")
    st.dataframe(rows_to_df(list_audit()), width="stretch")

render_footer()


