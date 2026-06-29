from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from .database import execute, get_connection, init_db, query_one, using_postgres


def reset_database() -> None:
    init_db()
    with get_connection() as conn:
        if using_postgres():
            conn.executescript(
                """
                TRUNCATE TABLE
                    exam_minutes,
                    exam_grades,
                    exam_board_members,
                    exam_boards,
                    exam_criteria,
                    pdf_exports,
                    advisory_answers,
                    advisory_records,
                    advisory_sessions,
                    orientations,
                    advisors,
                    students,
                    criteria,
                    audit_log,
                    settings,
                    users
                RESTART IDENTITY CASCADE;
                """
            )
        else:
            conn.executescript(
                """
                DELETE FROM pdf_exports;
                DELETE FROM exam_minutes;
                DELETE FROM exam_grades;
                DELETE FROM exam_board_members;
                DELETE FROM exam_boards;
                DELETE FROM exam_criteria;
                DELETE FROM advisory_answers;
                DELETE FROM advisory_records;
                DELETE FROM advisory_sessions;
                DELETE FROM orientations;
                DELETE FROM advisors;
                DELETE FROM students;
                DELETE FROM criteria;
                DELETE FROM audit_log;
                DELETE FROM settings;
                DELETE FROM users;
                DELETE FROM sqlite_sequence;
                """
            )
    seed_initial_data(force=True)


def reset_academic_data() -> None:
    """Limpa dados acadêmicos importados, preservando coordenação e settings."""
    init_db()
    with get_connection() as conn:
        conn.executescript(
            """
            DELETE FROM pdf_exports;
            DELETE FROM exam_minutes;
            DELETE FROM exam_grades;
            DELETE FROM exam_board_members;
            DELETE FROM exam_boards;
            DELETE FROM exam_criteria;
            DELETE FROM advisory_answers;
            DELETE FROM advisory_records;
            DELETE FROM advisory_sessions;
            DELETE FROM orientations;
            DELETE FROM advisors;
            DELETE FROM students;
            DELETE FROM criteria;
            DELETE FROM audit_log;
            DELETE FROM users WHERE role = 'professor';
            """
        )


def seed_initial_data(force: bool = False) -> None:
    init_db()
    from .boards import seed_exam_criteria

    if not force and query_one("SELECT id FROM users LIMIT 1"):
        criteria_count = query_one("SELECT COUNT(*) AS total FROM criteria")
        exam_criteria_count = query_one("SELECT COUNT(*) AS total FROM exam_criteria")
        settings_count = query_one("SELECT COUNT(*) AS total FROM settings")
        missing_sessions = query_one(
            """
            SELECT COUNT(*) AS total
            FROM orientations
            WHERE NOT EXISTS (
                SELECT 1
                FROM advisory_sessions
                WHERE advisory_sessions.orientation_id = orientations.id
            )
            """
        )
        if not criteria_count or int(criteria_count["total"]) == 0:
            seed_criteria()
        if not exam_criteria_count or int(exam_criteria_count["total"]) == 0:
            seed_exam_criteria()
        seed_settings()
        if missing_sessions and int(missing_sessions["total"]) > 0:
            ensure_sessions_for_all_orientations()
        return

    users = [
        ("Coordenacao", "coord", "coord123", "coordenacao"),
        ("Fabio", "fabio", "fabio123", "professor"),
        ("Professor 2", "professor2", "professor123", "professor"),
        ("Professor 3", "professor3", "professor123", "professor"),
    ]
    for name, email, password, role in users:
        user_id = execute(
            "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
            (name, email, password, role),
        )
        if role == "professor":
            execute(
                "INSERT INTO advisors (user_id, name, email) VALUES (?, ?, ?)",
                (user_id, name, email),
            )

    students = [
        ("Ana Beatriz", "ana@materdei.edu", "TFG I", "Habitação social em área central", 2026, 1),
        ("Bruno Lima", "bruno@materdei.edu", "TFG I", "Centro cultural de bairro", 2026, 1),
        ("Carla Souza", "carla@materdei.edu", "TFG I", "Requalificação de vazio urbano", 2026, 1),
        ("Diego Martins", "diego@materdei.edu", "TFG II", "Biblioteca parque municipal", 2026, 1),
        ("Elisa Rocha", "elisa@materdei.edu", "TFG II", "Clínica escola interdisciplinar", 2026, 1),
        ("Fernanda Alves", "fernanda@materdei.edu", "TFG II", "Terminal urbano integrado", 2026, 1),
    ]
    student_ids = []
    for item in students:
        student_ids.append(
            execute(
                """
                INSERT INTO students (name, email, tfg_stage, theme, year, semester)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                item,
            )
        )
    for index, student_id in enumerate(student_ids, start=1):
        execute("UPDATE students SET ra = ? WHERE id = ?", (f"202600{index}", student_id))

    advisor_ids = [row["id"] for row in get_connection().execute("SELECT id FROM advisors ORDER BY id")]
    assignments = [advisor_ids[0], advisor_ids[0], advisor_ids[1], advisor_ids[1], advisor_ids[2], advisor_ids[2]]
    for student_id, advisor_id in zip(student_ids, assignments):
        execute(
            """
            INSERT INTO orientations (student_id, advisor_id, year, semester)
            VALUES (?, ?, 2026, 1)
            """,
            (student_id, advisor_id),
        )

    seed_criteria()
    seed_exam_criteria()
    ensure_sessions_for_all_orientations()
    seed_settings()


def seed_settings() -> None:
    settings = {
        "institution": "Centro Universitário Mater Dei",
        "course": "Arquitetura e Urbanismo",
        "current_year": "2026",
        "current_semester": "1",
        "google_sheet_url": "",
        "public_exam_calendar_enabled": "0",
    }
    for key, value in settings.items():
        execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING", (key, value))


def seed_criteria() -> None:
    criteria = official_criteria()
    for tfg_stage, phase, group_name, description in criteria:
        exists = query_one(
            """
            SELECT id FROM criteria
            WHERE tfg_stage = ? AND phase = ? AND group_name = ? AND description = ?
            """,
            (tfg_stage, phase, group_name, description),
        )
        if exists:
            continue
        execute(
            """
            INSERT INTO criteria
                (tfg_stage, phase, group_name, description, required_comment_when_not_yes, active)
            VALUES (?, ?, ?, ?, 1, 1)
            """,
            (tfg_stage, phase, group_name, description),
        )


def official_criteria() -> list[tuple[str, str, str, str]]:
    tfg_i_items = [
        ("1. DOMÍNIO DO CONTEÚDO", "Apresentação (oral e visual) do trabalho escrito."),
        ("2. DELIMITAÇÃO DA PESQUISA", "Tema, justificativa, pertinência do problema de pesquisa voltado a Arquitetura e Urbanismo, objetivos gerais e específicos. Caracterização do objeto e usuários."),
        ("3. FUNDAMENTAÇÃO TEÓRICA", "Assuntos voltados para Arquitetura e Urbanismo, relação com os objetivos da pesquisa."),
        ("4. METODOLOGIA E PARÂMETROS DA ABNT", "Descrição dos processos realizados (como fez?), dos principais autores e arquitetos estudados, formatação, uso de citações diretas e indiretas, lista de referências, títulos de figuras, tabelas e gráficos."),
        ("5. REFERÊNCIAS ARQUITETÔNICAS", "Correlatos e/ou estudo de caso (pertinência das informações e relação com os objetivos da pesquisa)."),
        ("6. ELEMENTOS DO PROJETO ARQUITETÔNICO", "Programa de necessidades, organograma, fluxograma, pré-dimensionamento."),
        ("7. ANÁLISES URBANÍSTICAS", "Caracterização e contextualização urbana em suas escalas macro, meso e micro (dados estatísticos, índices, mapas temáticos e demais informações sensíveis à realidade em estudo)."),
        ("8. SOLUÇÃO ADOTADA", "Representação gráfica da solução adotada para a ocupação do terreno. Plantas, cortes e volumetrias esquemáticas. Indicações de acesso, soluções de circulação e setorização."),
        ("9. CONSIDERAÇÕES FINAIS SOBRE A PESQUISA", "Os objetivos propostos correspondem aos resultados obtidos."),
        ("10. DESENVOLVIMENTO DO ALUNO CONFORME INSTRUÇÕES PRÉVIAS", "Avaliação do orientador do desempenho do aluno desde a última assessoria realizada."),
    ]
    tfg_ii_base = [
        ("1.1 Conceituação", "Premissas projetuais e às relações da temática escolhida."),
        ("1.2 Memorial justificativo e conceitual", "Compreendendo informações gerais e referências teórico-conceituais sobre o partido adotado."),
        ("1.3 Implantação", "Considerando análise e diagnóstico na escala meso, macro e micro os aspectos regionais, urbanísticos, paisagísticos e fisiográficos."),
        ("1.4 Aspectos funcionais", "Atendendo ao programa de necessidades proposto (ou reformulado) e à respectiva setorização e dimensionamento dos espaços."),
        ("1.5 Conforto ambiental", "Características ou estratégias projetuais, capazes de resolver questões térmicas, lumínicas e acústicas em contribuição à qualidade do espaço."),
        ("1.6 Aspectos técnico-construtivos", "Resolução técnico-construtiva e de sistemas estruturais e complementares, entre outras."),
        ("1.7 Aspectos Formais/Espaciais", "Resolução plástica e formal, com especificações gerais de tratamento e solução dos espaços."),
        ("2.1 Gráfica", "Expressão e representação técnica projetual, considerando a capacidade de comunicação e a qualidade técnica da informação."),
        ("2.2 Defesa", "Capacidade oral de apresentação e defesa."),
    ]
    rows: list[tuple[str, str, str, str]] = []
    for phase in ["Relatório Científico – Fundamentação Teórica", "Estudo de Viabilidade – Plano de Ocupação"]:
        rows.extend(("TFG I", phase, title, description) for title, description in tfg_i_items)
    for phase in ["Estudo Preliminar", "Anteprojeto"]:
        rows.extend(("TFG II", phase, title, description) for title, description in tfg_ii_base)
    rows.append(("TFG II", "Anteprojeto", "2.3 Maquete Física", "Maquete."))
    return rows


def ensure_sessions_for_all_orientations() -> None:
    rows = get_connection().execute(
        """
        SELECT orientations.id AS orientation_id, students.tfg_stage, students.year, students.semester
        FROM orientations
        JOIN students ON students.id = orientations.student_id
        """
    ).fetchall()
    base_date = date(2026, 3, 10)
    for row in rows:
        total = 4 if row["tfg_stage"] == "TFG I" else 10
        for number in range(1, total + 1):
            phase = phase_for_session(row["tfg_stage"], number)
            planned = planned_date_for_session(
                int(row["year"]),
                int(row["semester"]),
                row["tfg_stage"],
                number,
                base_date,
            )
            execute(
                """
                INSERT INTO advisory_sessions
                    (orientation_id, session_number, tfg_stage, phase, planned_date)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(orientation_id, session_number) DO NOTHING
                """,
                (row["orientation_id"], number, row["tfg_stage"], phase, planned.isoformat()),
            )


def phase_for_session(tfg_stage: str, number: int) -> str:
    if tfg_stage == "TFG I":
        phases = []
        for stage, phase, _, _ in official_criteria():
            if stage == "TFG I" and phase not in phases:
                phases.append(phase)
        return phases[0] if number <= 2 else phases[1]
    return "Estudo Preliminar" if number <= 5 else "Anteprojeto"


def planned_date_for_session(year: int, semester: int, tfg_stage: str, number: int, fallback_start: date) -> date:
    stage_key = "tfg1" if tfg_stage == "TFG I" else "tfg2"
    setting = query_one("SELECT value FROM settings WHERE key = ?", (f"calendar_{year}_{semester}_{stage_key}_{number}",))
    if setting and setting["value"]:
        try:
            return date.fromisoformat(setting["value"])
        except ValueError:
            pass
    start = date(year, 3 if semester == 1 else 8, 10)
    if tfg_stage == "TFG I":
        return add_months(start, number - 1)
    return start + timedelta(days=(number - 1) * 7)


def add_months(value: date, months: int) -> date:
    target_month = value.month - 1 + months
    target_year = value.year + target_month // 12
    target_month = target_month % 12 + 1
    target_day = min(value.day, monthrange(target_year, target_month)[1])
    return date(target_year, target_month, target_day)


