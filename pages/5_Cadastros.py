from __future__ import annotations

import pandas as pd
import streamlit as st

from src.auth import render_footer, require_role
from src.ui import apply_app_style, paginate_dataframe, render_kpis
from src.utils import (
    create_criterion,
    create_orientation,
    create_professor,
    create_student,
    delete_criterion,
    delete_orientation,
    delete_professor,
    delete_student,
    import_criteria_batch,
    import_orientations_batch,
    import_people_batch,
    import_professors_batch,
    import_students_batch,
    list_advisors,
    list_all_students,
    list_criteria_admin,
    list_orientations_full,
    list_students_simple,
    list_students_without_orientation,
    rows_to_df,
    update_criterion,
    update_student_plan_partials,
    update_student_ra,
)


st.set_page_config(page_title="Cadastros", layout="wide")
apply_app_style()
user = require_role("coordenacao")


def to_dicts(rows) -> list[dict]:
    return [dict(row) for row in rows]


@st.cache_data(ttl=20, show_spinner=False)
def cached_advisors() -> list[dict]:
    return to_dicts(list_advisors())


@st.cache_data(ttl=20, show_spinner=False)
def cached_all_students() -> list[dict]:
    return to_dicts(list_all_students())


@st.cache_data(ttl=20, show_spinner=False)
def cached_students_simple() -> list[dict]:
    return to_dicts(list_students_simple())


@st.cache_data(ttl=20, show_spinner=False)
def cached_students_without_orientation() -> list[dict]:
    return to_dicts(list_students_without_orientation())


@st.cache_data(ttl=20, show_spinner=False)
def cached_orientations() -> list[dict]:
    return to_dicts(list_orientations_full())


@st.cache_data(ttl=20, show_spinner=False)
def cached_criteria() -> list[dict]:
    return to_dicts(list_criteria_admin())


def clear_read_cache() -> None:
    cached_advisors.clear()
    cached_all_students.clear()
    cached_students_simple.clear()
    cached_students_without_orientation.clear()
    cached_orientations.clear()
    cached_criteria.clear()


st.title("Cadastros")
render_kpis(
    [
        ("Professores", len(cached_advisors()), "orientadores e convidados"),
        ("Alunos", len(cached_students_simple()), "cadastrados"),
        ("Sem orientação", len(cached_students_without_orientation()), "aguardando vínculo"),
        ("Vínculos", len(cached_orientations()), "orientações ativas"),
        ("Critérios", len(cached_criteria()), "rubricas de assessoria"),
    ]
)
section = st.radio(
    "Área",
    ["Professores", "Alunos", "Orientações", "Importação em lote", "Critérios"],
    horizontal=True,
    label_visibility="collapsed",
)

if section == "Professores":
    st.subheader("Cadastrar professor ou convidado externo")
    with st.form("create_professor_form"):
        name = st.text_input("Nome")
        email = st.text_input("E-mail ou login")
        password = st.text_input("Senha inicial", value="professor123")
        submitted = st.form_submit_button("Cadastrar")
    if submitted:
        try:
            create_professor(name, email, password)
            clear_read_cache()
            st.success("Professor cadastrado.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    st.subheader("Professores e convidados cadastrados")
    advisors = cached_advisors()
    advisors_df = rows_to_df(advisors)
    st.dataframe(paginate_dataframe(advisors_df, "advisors"), width="stretch")

    st.subheader("Excluir professor ou convidado")
    if advisors:
        advisor_delete_options = {f"{item['name']} ({item['email']})": item for item in advisors}
        selected_delete = st.selectbox("Professor/convidado", list(advisor_delete_options.keys()), key="delete_professor_select")
        confirm_delete_professor = st.checkbox(
            "Confirmo que quero excluir este professor e suas orientações/fichas.",
            key="confirm_delete_professor",
        )
        if st.button("Excluir professor", disabled=not confirm_delete_professor):
            delete_professor(advisor_delete_options[selected_delete]["id"])
            clear_read_cache()
            st.success("Professor excluído.")
            st.rerun()

elif section == "Alunos":
    st.subheader("Cadastrar aluno")
    with st.form("create_student_form"):
        col1, col2 = st.columns(2)
        name = col1.text_input("Nome do aluno")
        ra = col2.text_input("RA")
        email = col1.text_input("E-mail do aluno")
        tfg_stage = col1.selectbox("Etapa", ["TFG I", "TFG II"])
        theme = col2.text_input("Tema")
        partial_1 = col1.text_input("Parcial 1 - Plano de Ocupação", help="Opcional. Use apenas para TFG I.")
        partial_2 = col2.text_input("Parcial 2 - Plano de Ocupação", help="Opcional. Use apenas para TFG I.")
        year = col1.number_input("Ano", min_value=2020, max_value=2100, value=2026)
        semester = col2.selectbox("Semestre", [1, 2])
        submitted = st.form_submit_button("Cadastrar aluno")
    if submitted:
        try:
            create_student(name, email, tfg_stage, theme, int(year), int(semester), ra, partial_1, partial_2)
            clear_read_cache()
            st.success("Aluno cadastrado.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    st.subheader("Alunos cadastrados")
    all_students = cached_students_simple()
    students_df = rows_to_df(all_students)
    if students_df.empty:
        st.info("Nenhum aluno cadastrado.")
    else:
        editor_columns = [
            "id",
            "name",
            "ra",
            "email",
            "tfg_stage",
            "theme",
            "year",
            "semester",
            "plan_partial_1",
            "plan_partial_2",
        ]
        editor_df = students_df[[col for col in editor_columns if col in students_df.columns]].rename(
            columns={
                "id": "ID",
                "name": "Nome",
                "ra": "RA",
                "email": "E-mail",
                "tfg_stage": "Etapa",
                "theme": "Tema",
                "year": "Ano",
                "semester": "Semestre",
                "plan_partial_1": "Parcial 1",
                "plan_partial_2": "Parcial 2",
            }
        )
        for grade_col in ("Parcial 1", "Parcial 2"):
            if grade_col in editor_df.columns:
                editor_df[grade_col] = pd.to_numeric(editor_df[grade_col], errors="coerce")

        with st.form("students_table_form"):
            edited_df = st.data_editor(
                editor_df,
                hide_index=True,
                num_rows="fixed",
                width="stretch",
                disabled=["ID", "Nome", "E-mail", "Etapa", "Tema", "Ano", "Semestre"],
                column_config={
                    "ID": st.column_config.NumberColumn("ID", disabled=True, width="small"),
                    "RA": st.column_config.TextColumn("RA"),
                    "Parcial 1": st.column_config.NumberColumn(
                        "Parcial 1",
                        min_value=0.0,
                        max_value=10.0,
                        step=0.1,
                        format="%.2f",
                        help="Nota opcional do Plano de Ocupação - TFG I.",
                    ),
                    "Parcial 2": st.column_config.NumberColumn(
                        "Parcial 2",
                        min_value=0.0,
                        max_value=10.0,
                        step=0.1,
                        format="%.2f",
                        help="Nota opcional do Plano de Ocupação - TFG I.",
                    ),
                },
                key="students_editor",
            )
            save_table = st.form_submit_button("Salvar alterações da tabela")

        if save_table:
            try:
                original_by_id = editor_df.set_index("ID")
                edited_by_id = edited_df.set_index("ID")
                updates = 0
                for student_id, row in edited_by_id.iterrows():
                    original = original_by_id.loc[student_id]
                    old_ra = "" if pd.isna(original.get("RA")) else str(original.get("RA")).strip()
                    new_ra = "" if pd.isna(row.get("RA")) else str(row.get("RA")).strip()
                    old_partial_1 = original.get("Parcial 1")
                    old_partial_2 = original.get("Parcial 2")
                    new_partial_1 = row.get("Parcial 1")
                    new_partial_2 = row.get("Parcial 2")
                    partials_changed = not (
                        (pd.isna(old_partial_1) and pd.isna(new_partial_1) or old_partial_1 == new_partial_1)
                        and (pd.isna(old_partial_2) and pd.isna(new_partial_2) or old_partial_2 == new_partial_2)
                    )
                    if new_ra != old_ra:
                        update_student_ra(int(student_id), new_ra)
                        updates += 1
                    if partials_changed:
                        update_student_plan_partials(int(student_id), new_partial_1, new_partial_2)
                        updates += 1
                clear_read_cache()
                if updates:
                    st.success("Alterações salvas.")
                else:
                    st.info("Nenhuma alteração para salvar.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.subheader("Excluir aluno")
    if all_students:
        student_delete_options = {f"{item['name']} - {item['tfg_stage']} - {item['year']}/{item['semester']}": item for item in all_students}
        selected_delete = st.selectbox("Aluno", list(student_delete_options.keys()), key="delete_student_select")
        confirm_delete_student = st.checkbox(
            "Confirmo que quero excluir este aluno e suas orientações/fichas.",
            key="confirm_delete_student",
        )
        if st.button("Excluir aluno", disabled=not confirm_delete_student):
            delete_student(student_delete_options[selected_delete]["id"])
            clear_read_cache()
            st.success("Aluno excluído.")
            st.rerun()

elif section == "Orientações":
    st.subheader("Vincular alunos a orientador")
    advisors = cached_advisors()
    students = cached_students_without_orientation()
    if not advisors:
        st.warning("Cadastre pelo menos um professor.")
    elif not students:
        st.info("Todos os alunos já possuem orientação.")
    else:
        advisor_options = {f"{item['name']} ({item['email']})": item for item in advisors}
        student_options = {
            f"{item['name']} - {item['tfg_stage']} - {item['year']}/{item['semester']}": item
            for item in students
        }
        with st.form("orientation_form"):
            left, middle, right = st.columns([2, 1, 2])
            selected_students = left.multiselect(
                "Alunos disponíveis",
                list(student_options.keys()),
                help="Selecione um ou mais alunos para vincular ao professor escolhido.",
            )
            selected_advisor = middle.selectbox("Professor orientador", list(advisor_options.keys()))
            right.markdown("**Alunos selecionados**")
            if selected_students:
                for label in selected_students:
                    right.write(label)
            else:
                right.caption("Nenhum aluno selecionado.")
            submitted = st.form_submit_button("Vincular selecionados e criar assessorias")
        if submitted:
            if not selected_students:
                st.error("Selecione pelo menos um aluno.")
                st.stop()
            advisor = advisor_options[selected_advisor]
            count = 0
            for selected_student in selected_students:
                student = student_options[selected_student]
                create_orientation(student["id"], advisor["id"], student["year"], student["semester"])
                count += 1
            clear_read_cache()
            st.success(f"{count} orientação(ões) cadastrada(s) e assessorias criadas.")
            st.rerun()

    st.subheader("Alunos sem orientação")
    students_without_orientation_df = rows_to_df(students)
    st.dataframe(paginate_dataframe(students_without_orientation_df, "students_without_orientation"), width="stretch")

    st.subheader("Excluir vínculo de orientação")
    orientations = cached_orientations()
    if orientations:
        orientation_options = {
            f"{item['student_name']} -> {item['advisor_name']} ({item['year']}/{item['semester']})": item
            for item in orientations
        }
        selected_orientation = st.selectbox("Vínculo", list(orientation_options.keys()))
        confirm_delete_orientation = st.checkbox(
            "Confirmo que quero excluir este vínculo e as assessorias/fichas dele.",
            key="confirm_delete_orientation",
        )
        if st.button("Excluir vínculo", disabled=not confirm_delete_orientation):
            delete_orientation(orientation_options[selected_orientation]["id"])
            clear_read_cache()
            st.success("Vínculo excluído.")
            st.rerun()
    else:
        st.caption("Nenhum vínculo cadastrado.")

elif section == "Importação em lote":
    st.subheader("Importações em lote")
    import_area = st.radio(
        "Tipo",
        ["Alunos", "Alunos + orientadores", "Professores", "Orientações", "Critérios"],
        horizontal=True,
        label_visibility="collapsed",
    )
    required_columns = {
        "Alunos": "Colunas obrigatórias: nome, etapa_tfg, tema. Campos opcionais: parcial_1, parcial_2.",
        "Alunos + orientadores": "Colunas obrigatórias: nome, etapa_tfg, tema. Professor, e-mail do professor, parcial_1 e parcial_2 são opcionais.",
        "Professores": "Coluna obrigatória: nome. E-mail e senha são opcionais.",
        "Orientações": "Colunas obrigatórias: aluno, orientador.",
        "Critérios": "Colunas obrigatórias: etapa_tfg, fase, criterio, descricao.",
    }
    st.caption(required_columns[import_area])

    templates = {
        "Alunos + orientadores": (
            pd.DataFrame(
                [
                    {
                        "ra": "2026001",
                        "nome": "Ana Souza",
                        "email": "ana@materdei.edu",
                        "etapa_tfg": "TFG I",
                        "tema": "Centro Cultural",
                        "ano": 2026,
                        "semestre": 1,
                        "parcial_1": "",
                        "parcial_2": "",
                        "professor": "Fabio Cantu",
                        "email_professor": "fabio@materdei.edu",
                    }
                ]
            ),
            import_people_batch,
            "modelo_alunos_orientadores.csv",
        ),
        "Professores": (
            pd.DataFrame([{"nome": "Fabio Cantu", "email": "fabio@materdei.edu", "senha": "professor123"}]),
            import_professors_batch,
            "modelo_professores.csv",
        ),
        "Alunos": (
            pd.DataFrame(
                [
                    {
                        "ra": "2026002",
                        "nome": "Bruno Lima",
                        "email": "bruno@materdei.edu",
                        "etapa_tfg": "TFG II",
                        "tema": "Biblioteca de bairro",
                        "ano": 2026,
                        "semestre": 1,
                        "parcial_1": "",
                        "parcial_2": "",
                    }
                ]
            ),
            import_students_batch,
            "modelo_alunos.csv",
        ),
        "Orientações": (
            pd.DataFrame([{"aluno": "Ana Souza", "orientador": "Fabio Cantu", "ano": 2026, "semestre": 1}]),
            import_orientations_batch,
            "modelo_orientacoes.csv",
        ),
        "Critérios": (
            pd.DataFrame(
                [
                    {
                        "etapa_tfg": "TFG I",
                        "fase": "Relatório Científico – Fundamentação Teórica",
                        "criterio": "Domínio do conteúdo",
                        "descricao": "Clareza, segurança e domínio do tema.",
                        "ativo": 1,
                        "comentario_obrigatorio": 1,
                    }
                ]
            ),
            import_criteria_batch,
            "modelo_criterios.csv",
        ),
    }
    template, importer, filename = templates[import_area]
    st.download_button("Baixar modelo CSV", template.to_csv(index=False).encode("utf-8-sig"), filename, "text/csv")
    uploaded = st.file_uploader("Arquivo CSV ou XLSX", type=["csv", "xlsx"], key=f"upload_{import_area}")
    if uploaded:
        try:
            if uploaded.name.lower().endswith(".csv"):
                df = pd.read_csv(uploaded, dtype=str).fillna("")
            else:
                df = pd.read_excel(uploaded, dtype=str).fillna("")
            st.dataframe(df, width="stretch")
            if st.button("Importar arquivo", key=f"import_button_{import_area}"):
                result = importer(df)
                clear_read_cache()
                message_map = {
                    "Alunos + orientadores": (
                        f"Importação concluída: {result['students']} alunos, "
                        f"{result['professors']} professores referenciados, "
                        f"{result['orientations']} vínculos criados e "
                        f"{result['without_advisor']} aluno(s) sem orientador."
                    ),
                    "Professores": f"Importação concluída: {result['professors']} professor(es) criado(s).",
                    "Alunos": f"Importação concluída: {result['students']} aluno(s) criado(s).",
                    "Orientações": f"Importação concluída: {result['orientations']} vínculo(s) criado(s).",
                    "Critérios": f"Importação concluída: {result['criteria']} critério(s) criado(s).",
                }
                st.success(message_map[import_area])
                st.rerun()
        except Exception as exc:
            st.error(str(exc))

elif section == "Critérios":
    st.subheader("Cadastrar critério")
    with st.form("create_criterion_form"):
        col1, col2 = st.columns(2)
        tfg_stage = col1.selectbox("Etapa", ["TFG I", "TFG II"], key="criterion_stage_create")
        phase = col2.text_input("Fase", key="criterion_phase_create")
        group_name = st.text_input("Critério", key="criterion_name_create")
        description = st.text_area("Descrição", key="criterion_description_create", height=120)
        active = st.checkbox("Ativo", value=True, key="criterion_active_create")
        required_comment = st.checkbox("Comentário obrigatório quando não for positivo", value=True, key="criterion_required_create")
        submitted = st.form_submit_button("Cadastrar critério")
    if submitted:
        try:
            create_criterion(tfg_stage, phase, group_name, description, active, required_comment)
            clear_read_cache()
            st.success("Critério cadastrado.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    criteria = cached_criteria()
    st.subheader("Critérios cadastrados")
    criteria_df = rows_to_df(criteria)
    st.dataframe(paginate_dataframe(criteria_df, "advisory_criteria"), width="stretch")

    st.subheader("Editar critério")
    if criteria:
        criterion_options = {f"{item['tfg_stage']} | {item['phase']} | {item['group_name']}": item for item in criteria}
        selected_label = st.selectbox("Critério para editar", list(criterion_options.keys()))
        selected = criterion_options[selected_label]
        with st.form(f"edit_criterion_form_{selected['id']}"):
            col1, col2 = st.columns(2)
            edit_stage = col1.selectbox("Etapa", ["TFG I", "TFG II"], index=0 if selected["tfg_stage"] == "TFG I" else 1)
            edit_phase = col2.text_input("Fase", value=selected["phase"])
            edit_group = st.text_input("Critério", value=selected["group_name"])
            edit_description = st.text_area("Descrição", value=selected["description"], height=120)
            edit_active = st.checkbox("Ativo", value=bool(selected["active"]))
            edit_required = st.checkbox(
                "Comentário obrigatório quando não for positivo",
                value=bool(selected["required_comment_when_not_yes"]),
            )
            edit_submitted = st.form_submit_button("Salvar alterações")
        if edit_submitted:
            try:
                update_criterion(selected["id"], edit_stage, edit_phase, edit_group, edit_description, edit_active, edit_required)
                clear_read_cache()
                st.success("Critério atualizado.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        st.subheader("Excluir critério")
        confirm_delete_criterion = st.checkbox("Confirmo que quero excluir este critério.", key=f"confirm_delete_criterion_{selected['id']}")
        if st.button("Excluir critério", disabled=not confirm_delete_criterion):
            try:
                delete_criterion(selected["id"])
                clear_read_cache()
                st.success("Critério excluído.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    else:
        st.caption("Nenhum critério cadastrado.")

render_footer()
