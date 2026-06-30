from __future__ import annotations

from datetime import date

import pandas as pd

from .audit import log_action
from .database import execute, get_connection, query, query_one, using_postgres


EXAM_STAGES = ["Pré-Banca", "Banca Final", "Plano de Ocupação"]


DEFAULT_EXAM_CRITERIA = {
    "Pré-Banca": [
        ("Domínio do conteúdo", "Clareza, segurança e domínio da pesquisa apresentada."),
        ("Delimitação da pesquisa", "Tema, problema, justificativa, objetivos e aderência ao campo de Arquitetura e Urbanismo."),
        ("Fundamentação teórica", "Pertinência dos autores, conceitos e referências usados na pesquisa."),
        ("Metodologia e normas", "Coerência metodológica, organização textual, citações, referências e parâmetros da ABNT."),
        ("Referências arquitetônicas", "Uso crítico de correlatos, estudos de caso e repertório projetual."),
        ("Elementos do projeto", "Programa, organograma, fluxograma, pré-dimensionamento e partido inicial."),
        ("Análises urbanísticas", "Leitura macro, meso e micro da área, com dados, mapas e diagnóstico."),
        ("Solução adotada", "Coerência da proposta de ocupação, setorização, acessos e volumetria inicial."),
        ("Considerações finais", "Relação entre objetivos, resultados e encaminhamentos da pesquisa."),
    ],
    "Banca Final": [
        ("Conceituação", "Premissas projetuais e relação com a temática escolhida."),
        ("Memorial justificativo", "Clareza do partido, referências conceituais e justificativas de projeto."),
        ("Implantação", "Relação com o terreno, entorno, paisagem, acessos e condicionantes urbanos."),
        ("Aspectos funcionais", "Programa, setorização, fluxos, dimensionamento e desempenho dos espaços."),
        ("Conforto ambiental", "Soluções térmicas, lumínicas, acústicas e estratégias ambientais."),
        ("Aspectos técnico-construtivos", "Estrutura, sistemas complementares, materialidade e viabilidade construtiva."),
        ("Aspectos formais e espaciais", "Qualidade plástica, espacial, volumétrica e compositiva da proposta."),
        ("Representação gráfica", "Qualidade técnica, legibilidade e comunicação das peças projetuais."),
        ("Defesa oral", "Clareza, domínio, argumentação e resposta aos questionamentos da banca."),
        ("Síntese final", "Coerência geral entre pesquisa, conceito, solução arquitetônica e apresentação."),
    ],
    "Plano de Ocupação": [
        ("Leitura do terreno", "Compreensão das condicionantes físicas, ambientais, urbanas e legais."),
        ("Diretrizes de implantação", "Coerência das estratégias de ocupação, acessos, fluxos e permanências."),
        ("Programa e pré-dimensionamento", "Compatibilidade entre necessidades, áreas e relações funcionais."),
        ("Setorização", "Organização espacial, hierarquias, conexões e compatibilidade de usos."),
        ("Relação urbana", "Articulação com entorno, paisagem, mobilidade e espaços públicos."),
        ("Sustentabilidade", "Estratégias ambientais, conforto e uso responsável de recursos."),
        ("Viabilidade", "Compatibilidade técnica, construtiva e operacional da ocupação proposta."),
        ("Representação", "Clareza dos diagramas, plantas, esquemas, mapas e desenhos apresentados."),
        ("Argumentação", "Capacidade de justificar escolhas e responder aos objetivos do trabalho."),
        ("Consistência geral", "Coerência entre diagnóstico, diretrizes e solução de ocupação."),
    ],
}


def seed_exam_criteria() -> None:
    # Critérios de banca agora são controlados apenas por cadastro/importação manual.
    return


def list_exam_criteria(stage: str, active_only: bool = True):
    sql = "SELECT * FROM exam_criteria WHERE stage = ?"
    params: list[object] = [stage]
    if active_only:
        sql += " AND active = 1"
    sql += " ORDER BY id"
    return query(sql, tuple(params))


def create_exam_criterion(stage: str, criterion: str, description: str, active: bool = True) -> int:
    validate_stage(stage)
    if not criterion.strip() or not description.strip():
        raise ValueError("Preencha critério e descrição.")
    return execute(
        """
        INSERT INTO exam_criteria (stage, criterion, description, active)
        VALUES (?, ?, ?, ?)
        """,
        (stage, criterion.strip(), description.strip(), 1 if active else 0),
    )


def update_exam_criterion(criterion_id: int, stage: str, criterion: str, description: str, active: bool) -> None:
    validate_stage(stage)
    if not criterion.strip() or not description.strip():
        raise ValueError("Preencha critério e descrição.")
    execute(
        """
        UPDATE exam_criteria
        SET stage = ?, criterion = ?, description = ?, active = ?
        WHERE id = ?
        """,
        (stage, criterion.strip(), description.strip(), 1 if active else 0, criterion_id),
    )


def delete_exam_criterion(criterion_id: int) -> None:
    used = query_one("SELECT id FROM exam_grades WHERE criterion_id = ? LIMIT 1", (criterion_id,))
    if used:
        raise ValueError("Este critério já possui notas lançadas. Desative-o em vez de excluir.")
    execute("DELETE FROM exam_criteria WHERE id = ?", (criterion_id,))


def delete_exam_criteria_by_stage(stage: str) -> int:
    validate_stage(stage)
    used = query_one(
        """
        SELECT COUNT(*) AS total
        FROM exam_grades
        JOIN exam_criteria ON exam_criteria.id = exam_grades.criterion_id
        WHERE exam_criteria.stage = ?
        """,
        (stage,),
    )
    if used and int(used["total"] or 0) > 0:
        raise ValueError("Existem critérios desta etapa com notas lançadas. Desative-os ou exclua apenas critérios sem uso.")
    before = query_one("SELECT COUNT(*) AS total FROM exam_criteria WHERE stage = ?", (stage,))
    execute("DELETE FROM exam_criteria WHERE stage = ?", (stage,))
    return int(before["total"] if before else 0)


def import_exam_criteria_batch(df: pd.DataFrame) -> dict:
    df = df.copy().fillna("")
    df.columns = [str(col).strip().lower() for col in df.columns]
    rename_map = {
        "etapa": "stage",
        "critério": "criterion",
        "criterio": "criterion",
        "descrição": "description",
        "descricao": "description",
        "ativo?": "active",
        "ativo": "active",
    }
    df = df.rename(columns={key: value for key, value in rename_map.items() if key in df.columns})
    required = {"stage", "criterion", "description"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Colunas ausentes: {', '.join(sorted(missing))}")
    if "active" not in df.columns:
        df["active"] = "1"

    created = 0
    for _, row in df.iterrows():
        stage = normalize_exam_stage(str(row["stage"]))
        criterion = str(row["criterion"]).strip()
        description = str(row["description"]).strip()
        if not criterion or not description:
            continue
        active = str(row.get("active", "1")).strip().lower() not in {"0", "nao", "não", "false", "inativo"}
        create_exam_criterion(stage, criterion, description, active)
        created += 1
    return {"criteria": created}


def normalize_exam_stage(value: str) -> str:
    text = str(value or "").strip().lower()
    normalized = (
        text.replace("á", "a")
        .replace("ã", "a")
        .replace("ç", "c")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    aliases = {
        "pre banca": "Pré-Banca",
        "pre-banca": "Pré-Banca",
        "previa": "Pré-Banca",
        "banca final": "Banca Final",
        "final": "Banca Final",
        "plano de ocupacao": "Plano de Ocupação",
        "plano ocupacao": "Plano de Ocupação",
        "ocupacao": "Plano de Ocupação",
    }
    if value.strip() in EXAM_STAGES:
        return value.strip()
    if normalized in aliases:
        return aliases[normalized]
    raise ValueError(f"Etapa de banca inválida: {value}")


def list_exam_boards(filters: dict | None = None):
    filters = filters or {}
    where = []
    params = []
    if filters.get("advisor_id"):
        where.append(
            """
            EXISTS (
                SELECT 1
                FROM exam_board_members
                WHERE exam_board_members.board_id = exam_boards.id
                  AND exam_board_members.advisor_id = ?
            )
            """
        )
        params.append(filters["advisor_id"])
    if filters.get("stage"):
        where.append("exam_boards.stage = ?")
        params.append(filters["stage"])
    if filters.get("status"):
        where.append("exam_boards.status = ?")
        params.append(filters["status"])
    if filters.get("year"):
        where.append("students.year = ?")
        params.append(filters["year"])
    if filters.get("semester"):
        where.append("students.semester = ?")
        params.append(filters["semester"])

    where_sql = "WHERE " + " AND ".join(where) if where else ""
    return query(
        f"""
        SELECT exam_boards.*, students.name AS student_name, students.theme,
               students.tfg_stage, students.year, students.semester
        FROM exam_boards
        JOIN students ON students.id = exam_boards.student_id
        {where_sql}
        ORDER BY exam_boards.scheduled_date, exam_boards.scheduled_time, students.name
        """,
        tuple(params),
    )


def get_exam_board(board_id: int):
    return query_one(
        """
        SELECT exam_boards.*, students.name AS student_name, students.theme,
               students.email AS student_email, students.ra, students.tfg_stage,
               students.year, students.semester
        FROM exam_boards
        JOIN students ON students.id = exam_boards.student_id
        WHERE exam_boards.id = ?
        """,
        (board_id,),
    )


def get_board_for_student_stage(student_id: int, stage: str):
    return query_one("SELECT * FROM exam_boards WHERE student_id = ? AND stage = ?", (student_id, stage))


def save_exam_board(
    student_id: int,
    stage: str,
    scheduled_date: date,
    scheduled_time: str,
    location: str,
    orientador_id: int,
    evaluator_ids: list[int],
    user_id: int,
) -> int:
    validate_stage(stage)
    if not orientador_id:
        raise ValueError("Selecione o orientador da banca.")
    evaluator_ids = [int(value) for value in evaluator_ids if int(value) != int(orientador_id)]
    if not evaluator_ids:
        raise ValueError("Selecione pelo menos um avaliador.")

    existing = get_board_for_student_stage(student_id, stage)
    with get_connection() as conn:
        if existing:
            board_id = int(existing["id"])
            conn.execute(
                """
                UPDATE exam_boards
                SET scheduled_date = ?, scheduled_time = ?, location = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (scheduled_date.isoformat(), scheduled_time.strip(), location.strip(), board_id),
            )
            conn.execute("DELETE FROM exam_board_members WHERE board_id = ?", (board_id,))
        else:
            board_id = int(
                conn.execute(
                    """
                    INSERT INTO exam_boards
                        (student_id, stage, scheduled_date, scheduled_time, location, created_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (student_id, stage, scheduled_date.isoformat(), scheduled_time.strip(), location.strip(), user_id),
                ).lastrowid
            )

        conn.execute(
            """
            INSERT INTO exam_board_members
                (board_id, advisor_id, member_role, can_grade, can_record_minutes)
            VALUES (?, ?, 'orientador', 0, 1)
            """,
            (board_id, orientador_id),
        )
        for evaluator_id in evaluator_ids:
            conn.execute(
                """
                INSERT INTO exam_board_members
                    (board_id, advisor_id, member_role, can_grade, can_record_minutes)
                VALUES (?, ?, 'avaliador', 1, 0)
                """,
                (board_id, evaluator_id),
            )

    log_action(user_id, "Salvou banca", "exam_boards", board_id, None, f"student={student_id}; stage={stage}", None)
    return board_id


def delete_exam_board(board_id: int, user_id: int) -> None:
    execute("DELETE FROM exam_boards WHERE id = ?", (board_id,))
    log_action(user_id, "Excluiu banca", "exam_boards", board_id, None, None, None)


def list_board_members(board_id: int):
    return query(
        """
        SELECT exam_board_members.*, advisors.name, advisors.email, advisors.user_id
        FROM exam_board_members
        JOIN advisors ON advisors.id = exam_board_members.advisor_id
        WHERE exam_board_members.board_id = ?
        ORDER BY exam_board_members.member_role DESC, advisors.name
        """,
        (board_id,),
    )


def get_member(board_id: int, advisor_id: int):
    return query_one(
        "SELECT * FROM exam_board_members WHERE board_id = ? AND advisor_id = ?",
        (board_id, advisor_id),
    )


def save_grades(board_id: int, advisor_id: int, grades: dict[int, dict]) -> None:
    member = get_member(board_id, advisor_id)
    if not member or not member["can_grade"]:
        raise ValueError("Este usuário não está habilitado para lançar notas nesta banca.")
    with get_connection() as conn:
        for criterion_id, item in grades.items():
            grade = float(item["grade"])
            if grade < 0 or grade > 10:
                raise ValueError("As notas devem ficar entre 0 e 10.")
            conn.execute(
                """
                INSERT INTO exam_grades (board_id, advisor_id, criterion_id, grade, observation)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(board_id, advisor_id, criterion_id)
                DO UPDATE SET grade = excluded.grade,
                              observation = excluded.observation,
                              updated_at = CURRENT_TIMESTAMP
                """,
                (board_id, advisor_id, criterion_id, grade, item.get("observation", "")),
            )
    refresh_board_status(board_id)


def list_grades(board_id: int, advisor_id: int | None = None):
    sql = """
        SELECT exam_grades.*, exam_criteria.criterion, advisors.name AS advisor_name
        FROM exam_grades
        JOIN exam_criteria ON exam_criteria.id = exam_grades.criterion_id
        JOIN advisors ON advisors.id = exam_grades.advisor_id
        WHERE exam_grades.board_id = ?
    """
    params: list[object] = [board_id]
    if advisor_id is not None:
        sql += " AND exam_grades.advisor_id = ?"
        params.append(advisor_id)
    sql += " ORDER BY advisors.name, exam_criteria.id"
    return query(sql, tuple(params))


def save_minutes(board_id: int, advisor_id: int, minutes_text: str) -> None:
    member = get_member(board_id, advisor_id)
    if not member or not member["can_record_minutes"]:
        raise ValueError("Este usuário não está habilitado para registrar ata nesta banca.")
    if not minutes_text.strip():
        raise ValueError("A ata não pode ficar em branco.")
    execute(
        """
        INSERT INTO exam_minutes (board_id, advisor_id, minutes_text)
        VALUES (?, ?, ?)
        ON CONFLICT(board_id)
        DO UPDATE SET advisor_id = excluded.advisor_id,
                      minutes_text = excluded.minutes_text,
                      updated_at = CURRENT_TIMESTAMP
        """,
        (board_id, advisor_id, minutes_text.strip()),
    )
    refresh_board_status(board_id)


def get_minutes(board_id: int):
    return query_one(
        """
        SELECT exam_minutes.*, advisors.name AS advisor_name
        FROM exam_minutes
        JOIN advisors ON advisors.id = exam_minutes.advisor_id
        WHERE exam_minutes.board_id = ?
        """,
        (board_id,),
    )


def board_status(board_id: int) -> dict:
    members = list_board_members(board_id)
    evaluators = [member for member in members if member["can_grade"]]
    criteria_count = query_one(
        """
        SELECT COUNT(*) AS total
        FROM exam_criteria
        WHERE stage = (SELECT stage FROM exam_boards WHERE id = ?) AND active = 1
        """,
        (board_id,),
    )
    total_criteria = int(criteria_count["total"] if criteria_count else 0)
    sent = []
    pending = []
    for evaluator in evaluators:
        row = query_one(
            """
            SELECT COUNT(*) AS total
            FROM exam_grades
            WHERE board_id = ? AND advisor_id = ?
            """,
            (board_id, evaluator["advisor_id"]),
        )
        if total_criteria > 0 and int(row["total"] if row else 0) >= total_criteria:
            sent.append(evaluator["name"])
        else:
            pending.append(evaluator["name"])
    minutes = get_minutes(board_id)
    complete = len(pending) == 0 and bool(minutes) and total_criteria > 0
    partial = bool(sent) or bool(minutes)
    status = "Completa" if complete else "Parcial" if partial else "Pendente"
    return {
        "status": status,
        "sent": sent,
        "pending": pending,
        "minutes": bool(minutes),
        "total_evaluators": len(evaluators),
        "total_criteria": total_criteria,
    }


def refresh_board_status(board_id: int) -> str:
    status = board_status(board_id)["status"]
    execute("UPDATE exam_boards SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, board_id))
    return status


def board_grade_summary(board_id: int):
    return query(
        """
        SELECT advisors.name AS advisor_name, AVG(exam_grades.grade) AS average_grade,
               COUNT(exam_grades.id) AS grades_count
        FROM exam_grades
        JOIN advisors ON advisors.id = exam_grades.advisor_id
        WHERE exam_grades.board_id = ?
        GROUP BY advisors.id, advisors.name
        ORDER BY advisors.name
        """,
        (board_id,),
    )


def board_partial_grade(board_id: int):
    return query_one(
        """
        SELECT AVG(grade) AS average_grade, COUNT(*) AS grades_count
        FROM exam_grades
        WHERE board_id = ?
        """,
        (board_id,),
    )


def consolidated_results(advisor_id: int | None = None):
    where_sql = ""
    params: tuple = ()
    if advisor_id is not None:
        where_sql = """
        WHERE EXISTS (
            SELECT 1
            FROM exam_board_members
            WHERE exam_board_members.board_id = exam_boards.id
              AND exam_board_members.advisor_id = ?
        )
        """
        params = (advisor_id,)
    return query(
        f"""
        SELECT exam_boards.id AS board_id, students.name AS student_name, exam_boards.stage,
               exam_boards.status, AVG(exam_grades.grade) AS average_grade,
               COUNT(DISTINCT exam_grades.advisor_id) AS evaluators_with_grade,
               COUNT(exam_grades.id) AS grades_count,
               CASE WHEN exam_minutes.id IS NULL THEN 'Pendente' ELSE 'Registrada' END AS minutes_status
        FROM exam_boards
        JOIN students ON students.id = exam_boards.student_id
        LEFT JOIN exam_grades ON exam_grades.board_id = exam_boards.id
        LEFT JOIN exam_minutes ON exam_minutes.board_id = exam_boards.id
        {where_sql}
        GROUP BY exam_boards.id, students.name, exam_boards.stage, exam_boards.status, exam_minutes.id
        ORDER BY students.name, exam_boards.stage
        """,
        params,
    )


def public_exam_calendar_enabled() -> bool:
    row = query_one("SELECT value FROM settings WHERE key = ?", ("public_exam_calendar_enabled",))
    return bool(row and str(row["value"]).strip() == "1")


def set_public_exam_calendar_enabled(enabled: bool) -> None:
    execute(
        """
        INSERT INTO settings (key, value)
        VALUES ('public_exam_calendar_enabled', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        ("1" if enabled else "0",),
    )


def list_public_exam_boards(start_date: date, end_date: date):
    if using_postgres():
        members_sql = """
            COALESCE(STRING_AGG(advisors.name, ', ' ORDER BY advisors.name)
                     FILTER (WHERE exam_board_members.can_record_minutes = 1), '-') AS orientador,
            COALESCE(STRING_AGG(advisors.name, ', ' ORDER BY advisors.name)
                     FILTER (WHERE exam_board_members.can_grade = 1), '-') AS avaliadores
        """
    else:
        members_sql = """
            COALESCE(GROUP_CONCAT(CASE WHEN exam_board_members.can_record_minutes = 1 THEN advisors.name END, ', '), '-') AS orientador,
            COALESCE(GROUP_CONCAT(CASE WHEN exam_board_members.can_grade = 1 THEN advisors.name END, ', '), '-') AS avaliadores
        """

    return query(
        f"""
        SELECT exam_boards.*, students.name AS student_name, students.theme,
               students.tfg_stage,
               {members_sql}
        FROM exam_boards
        JOIN students ON students.id = exam_boards.student_id
        LEFT JOIN exam_board_members ON exam_board_members.board_id = exam_boards.id
        LEFT JOIN advisors ON advisors.id = exam_board_members.advisor_id
        WHERE exam_boards.scheduled_date >= ?
          AND exam_boards.scheduled_date <= ?
        GROUP BY exam_boards.id, students.name, students.theme, students.tfg_stage
        ORDER BY exam_boards.scheduled_date, exam_boards.scheduled_time, students.name
        """,
        (start_date.isoformat(), end_date.isoformat()),
    )

def list_student_public_exam_boards(student_id: int):
    if using_postgres():
        members_sql = """
            COALESCE(STRING_AGG(advisors.name, ', ' ORDER BY advisors.name)
                     FILTER (WHERE exam_board_members.can_record_minutes = 1), '-') AS orientador,
            COALESCE(STRING_AGG(advisors.name, ', ' ORDER BY advisors.name)
                     FILTER (WHERE exam_board_members.can_grade = 1), '-') AS avaliadores
        """
    else:
        members_sql = """
            COALESCE(GROUP_CONCAT(CASE WHEN exam_board_members.can_record_minutes = 1 THEN advisors.name END, ', '), '-') AS orientador,
            COALESCE(GROUP_CONCAT(CASE WHEN exam_board_members.can_grade = 1 THEN advisors.name END, ', '), '-') AS avaliadores
        """

    return query(
        f"""
        SELECT exam_boards.id, exam_boards.stage, exam_boards.scheduled_date,
               exam_boards.scheduled_time, exam_boards.location, exam_boards.status,
               students.name AS student_name, students.theme, students.tfg_stage,
               exam_minutes.updated_at AS minutes_updated_at,
               {members_sql}
        FROM exam_boards
        JOIN students ON students.id = exam_boards.student_id
        JOIN exam_minutes ON exam_minutes.board_id = exam_boards.id
        LEFT JOIN exam_board_members ON exam_board_members.board_id = exam_boards.id
        LEFT JOIN advisors ON advisors.id = exam_board_members.advisor_id
        WHERE exam_boards.student_id = ?
        GROUP BY exam_boards.id, exam_boards.stage, exam_boards.scheduled_date,
                 exam_boards.scheduled_time, exam_boards.location, exam_boards.status,
                 students.name, students.theme, students.tfg_stage, exam_minutes.updated_at
        ORDER BY exam_boards.scheduled_date, exam_boards.scheduled_time, exam_boards.stage
        """,
        (student_id,),
    )


def advisor_id_for_user(user_id: int) -> int | None:
    row = query_one("SELECT id FROM advisors WHERE user_id = ?", (user_id,))
    return int(row["id"]) if row else None


def validate_stage(stage: str) -> None:
    if stage not in EXAM_STAGES:
        raise ValueError("Etapa de banca inválida.")
