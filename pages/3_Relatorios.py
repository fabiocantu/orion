from __future__ import annotations

import streamlit as st

from src.auth import render_footer, require_login
from src.database import query
from src.utils import rows_to_df


st.set_page_config(page_title="Relatórios", layout="wide")
user = require_login()

st.title("Relatórios")
stage = st.selectbox("Filtrar por etapa", ["Todas", "TFG I", "TFG II"])
phase = st.selectbox(
    "Filtrar por fase",
    [
        "Todas",
        "Relatório Científico – Fundamentação Teórica",
        "Estudo de Viabilidade – Plano de Ocupação",
        "Estudo Preliminar",
        "Anteprojeto",
    ],
)

where = []
params = []
if stage != "Todas":
    where.append("students.tfg_stage = ?")
    params.append(stage)
if phase != "Todas":
    where.append("advisory_sessions.phase = ?")
    params.append(phase)
where_sql = "WHERE " + " AND ".join(where) if where else ""

by_professor = query(
    """
    SELECT advisors.name AS professor, COUNT(students.id) AS alunos
    FROM advisors
    LEFT JOIN orientations ON orientations.advisor_id = advisors.id
    LEFT JOIN students ON students.id = orientations.student_id
    GROUP BY advisors.id
    ORDER BY advisors.name
    """
)
st.subheader("Alunos por professor")
st.dataframe(rows_to_df(by_professor), width="stretch")

summary = query(
    f"""
    SELECT advisory_sessions.status, COUNT(*) AS quantidade
    FROM advisory_sessions
    JOIN orientations ON orientations.id = advisory_sessions.orientation_id
    JOIN students ON students.id = orientations.student_id
    {where_sql}
    GROUP BY advisory_sessions.status
    """,
    tuple(params),
)
st.subheader("Assessorias feitas e pendentes")
st.dataframe(rows_to_df(summary), width="stretch")

evaluations = query(
    f"""
    SELECT COALESCE(advisory_records.final_evaluation, 'Sem avaliação') AS avaliacao, COUNT(*) AS quantidade
    FROM advisory_sessions
    JOIN orientations ON orientations.id = advisory_sessions.orientation_id
    JOIN students ON students.id = orientations.student_id
    LEFT JOIN advisory_records ON advisory_records.session_id = advisory_sessions.id
    {where_sql}
    GROUP BY COALESCE(advisory_records.final_evaluation, 'Sem avaliação')
    """,
    tuple(params),
)
st.subheader("Avaliações finais")
st.dataframe(rows_to_df(evaluations), width="stretch")

detail = query(
    f"""
    SELECT students.name AS aluno, advisors.name AS professor, students.tfg_stage AS etapa,
           advisory_sessions.phase AS fase, advisory_sessions.session_number AS assessoria,
           advisory_sessions.status, COALESCE(advisory_records.final_evaluation, '-') AS avaliacao
    FROM advisory_sessions
    JOIN orientations ON orientations.id = advisory_sessions.orientation_id
    JOIN students ON students.id = orientations.student_id
    JOIN advisors ON advisors.id = orientations.advisor_id
    LEFT JOIN advisory_records ON advisory_records.session_id = advisory_sessions.id
    {where_sql}
    ORDER BY professor, aluno, assessoria
    """,
    tuple(params),
)
df = rows_to_df(detail)
st.subheader("Relatório detalhado")
st.dataframe(df, width="stretch")
st.download_button("Exportar CSV", df.to_csv(index=False).encode("utf-8-sig"), "relatorio_tfg.csv", "text/csv")

render_footer()

