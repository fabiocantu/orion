from __future__ import annotations

import json
from calendar import monthrange
from datetime import date, timedelta

import pandas as pd

from .audit import log_action
from .database import execute, get_connection, query, query_one
from .security import hash_password
from .seed import ensure_sessions_for_all_orientations
from .timezone import today_local


ANSWERS = ["Sim", "Não", "Parcial"]
RATINGS = [
    "INSUFICIENTE (abaixo de 50%)",
    "PARCIAL (50% a 70%)",
    "SUFICIENTE (70% a 90%)",
    "EXCELENTE (90% a 100%)",
]
NOT_APPLICABLE = "NÃO COMPETE A ETAPA"




def rows_to_df(rows) -> pd.DataFrame:
    return pd.DataFrame([dict(row) for row in rows])


def create_professor(name: str, email: str, password: str = "professor123") -> int:
    name = clean_optional(name)
    email = clean_optional(email)
    if not name and not email:
        raise ValueError("Informe nome ou e-mail/login do professor.")
    if not name:
        name = email
    if not email:
        email = name.lower().replace(" ", "_")
    existing = query_one("SELECT advisors.id FROM advisors WHERE lower(advisors.email) = lower(?)", (email,))
    if existing:
        return existing["id"]
    with get_connection() as conn:
        user = conn.execute("SELECT id FROM users WHERE lower(email) = lower(?)", (email,)).fetchone()
        if user:
            user_id = user["id"]
            conn.execute("UPDATE users SET name = ?, role = 'professor' WHERE id = ?", (name, user_id))
        else:
            user_id = conn.execute(
                "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, 'professor')",
                (name, email, hash_password(password.strip() or "professor123")),
            ).lastrowid
        advisor_id = conn.execute(
            "INSERT INTO advisors (user_id, name, email) VALUES (?, ?, ?)",
            (user_id, name, email),
        ).lastrowid
    return int(advisor_id)


def create_student(
    name: str,
    email: str,
    tfg_stage: str,
    theme: str,
    year: int,
    semester: int,
    ra: str = "",
) -> int:
    if tfg_stage not in ("TFG I", "TFG II"):
        raise ValueError("Etapa deve ser TFG I ou TFG II.")
    if int(semester) not in (1, 2):
        raise ValueError("Semestre deve ser 1 ou 2.")
    cleaned_ra = clean_optional(ra)
    if cleaned_ra:
        existing_ra = query_one("SELECT id FROM students WHERE lower(ra) = lower(?)", (cleaned_ra,))
        if existing_ra:
            raise ValueError("Ja existe um aluno cadastrado com este RA.")
    return execute(
        """
        INSERT INTO students (name, ra, email, tfg_stage, theme, year, semester)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (name.strip(), cleaned_ra, email.strip(), tfg_stage, theme.strip(), int(year), int(semester)),
    )


def create_orientation(student_id: int, advisor_id: int, year: int, semester: int) -> int:
    existing = query_one(
        "SELECT id FROM orientations WHERE student_id = ? AND advisor_id = ? AND year = ? AND semester = ?",
        (student_id, advisor_id, int(year), int(semester)),
    )
    if existing:
        return existing["id"]
    orientation_id = execute(
        """
        INSERT INTO orientations (student_id, advisor_id, year, semester)
        VALUES (?, ?, ?, ?)
        """,
        (student_id, advisor_id, int(year), int(semester)),
    )
    ensure_sessions_for_all_orientations()
    return orientation_id


def list_advisors():
    return query("SELECT advisors.*, users.password FROM advisors JOIN users ON users.id = advisors.user_id ORDER BY advisors.name")


def list_students_without_orientation():
    return query(
        """
        SELECT students.*
        FROM students
        LEFT JOIN orientations ON orientations.student_id = students.id
        WHERE orientations.id IS NULL
        ORDER BY students.name
        """
    )


def list_students_simple():
    return query("SELECT * FROM students ORDER BY name")


def list_orientations_full():
    return query(
        """
        SELECT orientations.*, students.name AS student_name, students.tfg_stage,
               advisors.name AS advisor_name, advisors.email AS advisor_email
        FROM orientations
        JOIN students ON students.id = orientations.student_id
        JOIN advisors ON advisors.id = orientations.advisor_id
        ORDER BY advisors.name, students.name
        """
    )


def list_criteria_admin():
    return query(
        """
        SELECT *
        FROM criteria
        ORDER BY tfg_stage, phase, id
        """
    )


def create_criterion(
    tfg_stage: str,
    phase: str,
    group_name: str,
    description: str,
    active: bool = True,
    required_comment_when_not_yes: bool = True,
) -> int:
    if tfg_stage not in ("TFG I", "TFG II"):
        raise ValueError("Etapa deve ser TFG I ou TFG II.")
    if not phase.strip() or not group_name.strip() or not description.strip():
        raise ValueError("Preencha fase, critério e descrição.")
    return execute(
        """
        INSERT INTO criteria
            (tfg_stage, phase, group_name, description, required_comment_when_not_yes, active)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            tfg_stage,
            phase.strip(),
            group_name.strip(),
            description.strip(),
            1 if required_comment_when_not_yes else 0,
            1 if active else 0,
        ),
    )


def update_criterion(
    criterion_id: int,
    tfg_stage: str,
    phase: str,
    group_name: str,
    description: str,
    active: bool,
    required_comment_when_not_yes: bool,
) -> None:
    if tfg_stage not in ("TFG I", "TFG II"):
        raise ValueError("Etapa deve ser TFG I ou TFG II.")
    if not phase.strip() or not group_name.strip() or not description.strip():
        raise ValueError("Preencha fase, critério e descrição.")
    execute(
        """
        UPDATE criteria
        SET tfg_stage = ?, phase = ?, group_name = ?, description = ?,
            required_comment_when_not_yes = ?, active = ?
        WHERE id = ?
        """,
        (
            tfg_stage,
            phase.strip(),
            group_name.strip(),
            description.strip(),
            1 if required_comment_when_not_yes else 0,
            1 if active else 0,
            criterion_id,
        ),
    )


def delete_criterion(criterion_id: int) -> None:
    used = query_one("SELECT id FROM advisory_answers WHERE criteria_id = ? LIMIT 1", (criterion_id,))
    if used:
        raise ValueError("Este critério já foi usado em fichas. Desative-o em vez de excluir.")
    execute("DELETE FROM criteria WHERE id = ?", (criterion_id,))


def delete_orientation(orientation_id: int) -> None:
    with get_connection() as conn:
        session_ids = [
            row["id"]
            for row in conn.execute("SELECT id FROM advisory_sessions WHERE orientation_id = ?", (orientation_id,)).fetchall()
        ]
        for session_id in session_ids:
            record = conn.execute("SELECT id FROM advisory_records WHERE session_id = ?", (session_id,)).fetchone()
            if record:
                conn.execute("DELETE FROM pdf_exports WHERE record_id = ?", (record["id"],))
                conn.execute("DELETE FROM advisory_answers WHERE record_id = ?", (record["id"],))
                conn.execute("DELETE FROM advisory_records WHERE id = ?", (record["id"],))
        conn.execute("DELETE FROM advisory_sessions WHERE orientation_id = ?", (orientation_id,))
        conn.execute("DELETE FROM orientations WHERE id = ?", (orientation_id,))


def delete_student(student_id: int) -> None:
    orientations = query("SELECT id FROM orientations WHERE student_id = ?", (student_id,))
    for orientation in orientations:
        delete_orientation(orientation["id"])
    execute("DELETE FROM students WHERE id = ?", (student_id,))


def update_student_ra(student_id: int, ra: str) -> None:
    cleaned_ra = clean_optional(ra)
    if cleaned_ra:
        existing_ra = query_one(
            "SELECT id FROM students WHERE lower(ra) = lower(?) AND id <> ?",
            (cleaned_ra, student_id),
        )
        if existing_ra:
            raise ValueError("Ja existe outro aluno cadastrado com este RA.")
    execute("UPDATE students SET ra = ? WHERE id = ?", (cleaned_ra, student_id))


def delete_professor(advisor_id: int) -> None:
    advisor = query_one("SELECT * FROM advisors WHERE id = ?", (advisor_id,))
    if not advisor:
        return
    orientations = query("SELECT id FROM orientations WHERE advisor_id = ?", (advisor_id,))
    for orientation in orientations:
        delete_orientation(orientation["id"])
    with get_connection() as conn:
        conn.execute("DELETE FROM advisors WHERE id = ?", (advisor_id,))
        conn.execute("DELETE FROM users WHERE id = ? AND role = 'professor'", (advisor["user_id"],))


def import_people_batch(df: pd.DataFrame) -> dict:
    required = {"nome", "etapa_tfg", "tema"}
    df = df.copy().fillna("")
    df.columns = [str(col).strip().lower() for col in df.columns]
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Colunas ausentes: {', '.join(sorted(missing))}")
    optional_defaults = {
        "ra": "",
        "email": "",
        "ano": 2026,
        "semestre": 1,
        "professor": "",
        "email_professor": "",
    }
    for column, default in optional_defaults.items():
        if column not in df.columns:
            df[column] = default
    if "professor" not in df.columns:
        df["professor"] = ""
    if "email_professor" not in df.columns:
        df["email_professor"] = ""

    created_students = 0
    created_professors = set()
    created_orientations = 0
    students_without_advisor = 0
    for _, row in df.iterrows():
        if not clean_optional(row["nome"]):
            continue
        professor_name = clean_optional(row["professor"])
        professor_email = clean_optional(row["email_professor"])
        advisor_id = None
        if professor_name or professor_email:
            advisor_id = create_professor(professor_name or professor_email, professor_email or professor_name)
            created_professors.add((professor_email or professor_name).strip().lower())
        year = int(clean_optional(row["ano"]) or 2026)
        semester = int(clean_optional(row["semestre"]) or 1)
        student_id = create_student(
            str(row["nome"]),
            clean_optional(row["email"]),
            normalize_stage(str(row["etapa_tfg"])),
            str(row["tema"]),
            year,
            semester,
            clean_optional(row["ra"]),
        )
        created_students += 1
        if advisor_id:
            create_orientation(student_id, advisor_id, year, semester)
            created_orientations += 1
        else:
            students_without_advisor += 1
    return {
        "students": created_students,
        "professors": len(created_professors),
        "orientations": created_orientations,
        "without_advisor": students_without_advisor,
    }


def import_professors_batch(df: pd.DataFrame, default_password: str = "professor123") -> dict:
    df = df.copy().fillna("")
    df.columns = [str(col).strip().lower() for col in df.columns]
    if "nome" not in df.columns and "professor" in df.columns:
        df["nome"] = df["professor"]
    if "email" not in df.columns and "email_professor" in df.columns:
        df["email"] = df["email_professor"]
    if "senha" not in df.columns:
        df["senha"] = default_password
    required = {"nome"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Colunas ausentes: {', '.join(sorted(missing))}")

    created = 0
    for _, row in df.iterrows():
        name = clean_optional(row.get("nome"))
        email = clean_optional(row.get("email"))
        if not name and not email:
            continue
        before = query_one("SELECT id FROM advisors WHERE lower(email) = lower(?)", (email or name,))
        advisor_id = create_professor(name or email, email or name, clean_optional(row.get("senha")) or default_password)
        if not before and advisor_id:
            created += 1
    return {"professors": created}


def import_students_batch(df: pd.DataFrame) -> dict:
    df = df.copy().fillna("")
    df.columns = [str(col).strip().lower() for col in df.columns]
    required = {"nome", "etapa_tfg", "tema"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Colunas ausentes: {', '.join(sorted(missing))}")
    for column, default in {"ra": "", "email": "", "ano": 2026, "semestre": 1}.items():
        if column not in df.columns:
            df[column] = default

    created = 0
    for _, row in df.iterrows():
        if not clean_optional(row.get("nome")):
            continue
        create_student(
            str(row["nome"]),
            clean_optional(row.get("email")),
            normalize_stage(str(row["etapa_tfg"])),
            str(row["tema"]),
            int(clean_optional(row.get("ano")) or 2026),
            int(clean_optional(row.get("semestre")) or 1),
            clean_optional(row.get("ra")),
        )
        created += 1
    return {"students": created}


def import_orientations_batch(df: pd.DataFrame) -> dict:
    df = df.copy().fillna("")
    df.columns = [str(col).strip().lower() for col in df.columns]
    required = {"aluno", "orientador"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Colunas ausentes: {', '.join(sorted(missing))}")
    if "ano" not in df.columns:
        df["ano"] = 2026
    if "semestre" not in df.columns:
        df["semestre"] = 1

    students = list_students_simple()
    advisors = list_advisors()
    student_by_name = {clean_optional(row["name"]).lower(): row for row in students}
    student_by_ra = {clean_optional(row["ra"]).lower(): row for row in students if clean_optional(row["ra"])}
    advisor_by_name = {clean_optional(row["name"]).lower(): row for row in advisors}
    advisor_by_email = {clean_optional(row["email"]).lower(): row for row in advisors if clean_optional(row["email"])}

    created = 0
    for _, row in df.iterrows():
        student_ref = clean_optional(row.get("aluno"))
        advisor_ref = clean_optional(row.get("orientador"))
        if not student_ref or not advisor_ref:
            continue
        student = student_by_ra.get(student_ref.lower()) or student_by_name.get(student_ref.lower())
        if not student:
            raise ValueError(f"Aluno não encontrado: {student_ref}")
        advisor = advisor_by_email.get(advisor_ref.lower()) or advisor_by_name.get(advisor_ref.lower())
        if not advisor:
            raise ValueError(f"Orientador não encontrado: {advisor_ref}")
        create_orientation(
            student["id"],
            advisor["id"],
            int(clean_optional(row.get("ano")) or student["year"] or 2026),
            int(clean_optional(row.get("semestre")) or student["semester"] or 1),
        )
        created += 1
    return {"orientations": created}


def import_criteria_batch(df: pd.DataFrame) -> dict:
    df = df.copy().fillna("")
    df.columns = [str(col).strip().lower() for col in df.columns]
    rename_map = {
        "etapa": "etapa_tfg",
        "critério": "criterio",
        "critério ": "criterio",
        "descrição": "descricao",
    }
    df = df.rename(columns={key: value for key, value in rename_map.items() if key in df.columns})
    required = {"etapa_tfg", "fase", "criterio", "descricao"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Colunas ausentes: {', '.join(sorted(missing))}")
    if "ativo" not in df.columns:
        df["ativo"] = "1"
    if "comentario_obrigatorio" not in df.columns:
        df["comentario_obrigatorio"] = "1"

    created = 0
    for _, row in df.iterrows():
        tfg_stage = normalize_stage(str(row["etapa_tfg"]))
        phase = str(row["fase"]).strip()
        group_name = str(row["criterio"]).strip()
        description = str(row["descricao"]).strip()
        active = clean_optional(row.get("ativo")).lower() not in {"0", "nao", "não", "false", "inativo"}
        required_comment = clean_optional(row.get("comentario_obrigatorio")).lower() not in {"0", "nao", "não", "false"}
        create_criterion(tfg_stage, phase, group_name, description, active, required_comment)
        created += 1
    return {"criteria": created}


def normalize_stage(value: str) -> str:
    text = value.strip().upper().replace(" ", "")
    if text in {"TFGI", "TFG1", "1", "I"}:
        return "TFG I"
    if text in {"TFGII", "TFG2", "2", "II"}:
        return "TFG II"
    if value.strip() in {"TFG I", "TFG II"}:
        return value.strip()
    raise ValueError(f"Etapa inválida: {value}. Use TFG I ou TFG II.")


def clean_optional(value: object) -> str:
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "null", "-", "sem professor", "sem orientador"}:
        return ""
    return text


def format_date_br(value: object, empty: str = "-") -> str:
    text = clean_optional(value)
    if not text:
        return empty
    try:
        return date.fromisoformat(text[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return text


def calendar_setting_key(year: int, semester: int, tfg_stage: str, session_number: int) -> str:
    stage_key = "tfg1" if tfg_stage == "TFG I" else "tfg2"
    return f"calendar_{year}_{semester}_{stage_key}_{session_number}"


def calendar_phase(tfg_stage: str, session_number: int) -> str:
    if tfg_stage == "TFG I":
        return "Relatório Científico – Fundamentação Teórica" if session_number <= 2 else "Estudo de Viabilidade – Plano de Ocupação"
    return "Estudo Preliminar" if session_number <= 5 else "Anteprojeto"


def default_calendar_dates(start_date: date, tfg_stage: str) -> list[date]:
    total = 4 if tfg_stage == "TFG I" else 10
    if tfg_stage == "TFG I":
        return [add_months(start_date, index) for index in range(total)]
    return [start_date + timedelta(days=7 * index) for index in range(total)]


def add_months(value: date, months: int) -> date:
    target_month = value.month - 1 + months
    target_year = value.year + target_month // 12
    target_month = target_month % 12 + 1
    target_day = min(value.day, monthrange(target_year, target_month)[1])
    return date(target_year, target_month, target_day)


def get_advisory_calendar(year: int, semester: int, tfg_stage: str) -> list[dict]:
    total = 4 if tfg_stage == "TFG I" else 10
    rows = []
    for number in range(1, total + 1):
        key = calendar_setting_key(year, semester, tfg_stage, number)
        setting = query_one("SELECT value FROM settings WHERE key = ?", (key,))
        planned_date = setting["value"] if setting and setting["value"] else ""
        if not planned_date:
            existing = query_one(
                """
                SELECT advisory_sessions.planned_date
                FROM advisory_sessions
                JOIN orientations ON orientations.id = advisory_sessions.orientation_id
                JOIN students ON students.id = orientations.student_id
                WHERE students.year = ?
                  AND students.semester = ?
                  AND students.tfg_stage = ?
                  AND advisory_sessions.session_number = ?
                ORDER BY advisory_sessions.planned_date
                LIMIT 1
                """,
                (year, semester, tfg_stage, number),
            )
            planned_date = existing["planned_date"] if existing else ""
        rows.append(
            {
                "session_number": number,
                "phase": calendar_phase(tfg_stage, number),
                "planned_date": planned_date,
            }
        )
    return rows


def save_advisory_calendar(year: int, semester: int, tfg_stage: str, dates: dict[int, date], user_id: int) -> int:
    updated = 0
    with get_connection() as conn:
        for session_number, planned_date in dates.items():
            value = planned_date.isoformat()
            key = calendar_setting_key(year, semester, tfg_stage, session_number)
            conn.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            cur = conn.execute(
                """
                UPDATE advisory_sessions
                SET planned_date = ?
                WHERE session_number = ?
                  AND tfg_stage = ?
                  AND orientation_id IN (
                      SELECT orientations.id
                      FROM orientations
                      JOIN students ON students.id = orientations.student_id
                      WHERE students.year = ?
                        AND students.semester = ?
                        AND students.tfg_stage = ?
                  )
                """,
                (value, session_number, tfg_stage, year, semester, tfg_stage),
            )
            updated += cur.rowcount
    log_action(
        user_id,
        "Atualizou calendário de assessorias",
        "advisory_sessions",
        None,
        None,
        json.dumps(
            {
                "year": year,
                "semester": semester,
                "tfg_stage": tfg_stage,
                "dates": {str(number): value.isoformat() for number, value in dates.items()},
            },
            ensure_ascii=False,
        ),
        "Calendário geral do semestre",
    )
    return updated


def get_advisor_by_user(user_id: int):
    return query_one("SELECT * FROM advisors WHERE user_id = ?", (user_id,))


def list_professor_students(user_id: int):
    return query(
        """
        SELECT students.*, orientations.id AS orientation_id, advisors.name AS advisor_name
        FROM students
        JOIN orientations ON orientations.student_id = students.id
        JOIN advisors ON advisors.id = orientations.advisor_id
        WHERE advisors.user_id = ?
        ORDER BY students.name
        """,
        (user_id,),
    )


def list_all_students(filters: dict | None = None):
    filters = filters or {}
    where = []
    params = []
    if filters.get("advisor_id"):
        where.append("advisors.id = ?")
        params.append(filters["advisor_id"])
    if filters.get("tfg_stage"):
        where.append("students.tfg_stage = ?")
        params.append(filters["tfg_stage"])
    if filters.get("year"):
        where.append("students.year = ?")
        params.append(filters["year"])
    if filters.get("semester"):
        where.append("students.semester = ?")
        params.append(filters["semester"])
    sql = """
        SELECT students.*, orientations.id AS orientation_id, advisors.id AS advisor_id,
               advisors.name AS advisor_name
        FROM students
        JOIN orientations ON orientations.student_id = students.id
        JOIN advisors ON advisors.id = orientations.advisor_id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY advisors.name, students.name"
    return query(sql, tuple(params))


def list_sessions(orientation_id: int):
    return query(
        """
        SELECT advisory_sessions.*,
               advisory_records.id AS record_id,
               advisory_records.final_evaluation,
               advisory_records.updated_at
        FROM advisory_sessions
        LEFT JOIN advisory_records ON advisory_records.session_id = advisory_sessions.id
        WHERE advisory_sessions.orientation_id = ?
        ORDER BY advisory_sessions.session_number
        """,
        (orientation_id,),
    )


def get_student_context_by_session(session_id: int):
    return query_one(
        """
        SELECT students.*, advisory_sessions.id AS session_id, advisory_sessions.session_number,
               advisory_sessions.phase, advisory_sessions.planned_date, advisory_sessions.actual_date,
               advisory_sessions.locked, advisory_sessions.status,
               orientations.id AS orientation_id, advisors.id AS advisor_id,
               advisors.name AS advisor_name, advisors.email AS advisor_email
        FROM advisory_sessions
        JOIN orientations ON orientations.id = advisory_sessions.orientation_id
        JOIN students ON students.id = orientations.student_id
        JOIN advisors ON advisors.id = orientations.advisor_id
        WHERE advisory_sessions.id = ?
        """,
        (session_id,),
    )


def get_student_by_ra(ra: str):
    cleaned_ra = clean_optional(ra)
    if not cleaned_ra:
        return None
    return query_one(
        """
        SELECT *
        FROM students
        WHERE lower(coalesce(ra, '')) = lower(?)
        """,
        (cleaned_ra,),
    )


def list_student_public_sessions(student_id: int):
    return query(
        """
        SELECT advisory_sessions.*,
               advisory_records.id AS record_id,
               advisory_records.final_evaluation,
               advisory_records.final_comment,
               advisory_records.general_notes,
               advisory_records.referrals,
               advisory_records.pending_issues,
               advisory_records.updated_at,
               advisors.name AS advisor_name
        FROM advisory_sessions
        JOIN orientations ON orientations.id = advisory_sessions.orientation_id
        JOIN advisors ON advisors.id = orientations.advisor_id
        LEFT JOIN advisory_records ON advisory_records.session_id = advisory_sessions.id
        WHERE orientations.student_id = ?
          AND advisory_sessions.status = 'Preenchida'
          AND advisory_records.id IS NOT NULL
        ORDER BY advisory_sessions.session_number
        """,
        (student_id,),
    )


def list_criteria(tfg_stage: str, phase: str):
    return query(
        """
        SELECT * FROM criteria
        WHERE tfg_stage = ? AND phase = ? AND active = 1
        ORDER BY group_name, id
        """,
        (tfg_stage, phase),
    )


def get_record(session_id: int):
    return query_one("SELECT * FROM advisory_records WHERE session_id = ?", (session_id,))


def get_answers(record_id: int) -> dict[int, dict]:
    rows = query("SELECT * FROM advisory_answers WHERE record_id = ?", (record_id,))
    return {row["criteria_id"]: dict(row) for row in rows}


def validate_record(criteria_rows, answers: dict, final_evaluation: str, final_comment: str) -> list[str]:
    errors = []
    for criterion in criteria_rows:
        item = answers.get(criterion["id"], {})
        if item.get("answer") not in RATINGS + [NOT_APPLICABLE]:
            errors.append(f"Selecione uma avaliação para: {criterion['description']}")
    return errors


def normalize_rating_value(value: str | None) -> str:
    if value in RATINGS:
        return value
    legacy = {
        "1 - INSUFICIENTE (<50%)": "INSUFICIENTE (abaixo de 50%)",
        "2 - PARCIAL (50% a 70%)": "PARCIAL (50% a 70%)",
        "3 - SUFICIENTE (70 a 90%)": "SUFICIENTE (70% a 90%)",
        "4 - EXCELENTE (90 a 100%)": "EXCELENTE (90% a 100%)",
        "INSUFICIENTE (<50%)": "INSUFICIENTE (abaixo de 50%)",
        "PARCIAL (50% a 70%)": "PARCIAL (50% a 70%)",
        "SUFICIENTE (70 a 90%)": "SUFICIENTE (70% a 90%)",
        "EXCELENTE (90 a 100%)": "EXCELENTE (90% a 100%)",
        NOT_APPLICABLE: "SUFICIENTE (70% a 90%)",
    }
    return legacy.get(value or "", "SUFICIENTE (70% a 90%)")


def save_record(
    session_id: int,
    advisor_id: int,
    payload: dict,
    user: dict,
    justification: str | None = None,
    lock_record: bool = True,
) -> int:
    old_record = get_record(session_id)
    old_snapshot = snapshot_record(session_id) if old_record else None
    actual_date = payload.get("actual_date") or today_local().isoformat()
    with get_connection() as conn:
        if old_record:
            record_id = old_record["id"]
            conn.execute(
                """
                UPDATE advisory_records
                SET general_notes = ?, referrals = ?, pending_issues = ?, final_evaluation = ?,
                    final_comment = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    payload.get("general_notes"),
                    payload.get("referrals"),
                    payload.get("pending_issues"),
                    payload.get("final_evaluation"),
                    payload.get("final_comment"),
                    record_id,
                ),
            )
            conn.execute("DELETE FROM advisory_answers WHERE record_id = ?", (record_id,))
        else:
            cur = conn.execute(
                """
                INSERT INTO advisory_records
                    (session_id, advisor_id, general_notes, referrals, pending_issues,
                     final_evaluation, final_comment)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    advisor_id,
                    payload.get("general_notes"),
                    payload.get("referrals"),
                    payload.get("pending_issues"),
                    payload.get("final_evaluation"),
                    payload.get("final_comment"),
                ),
            )
            record_id = int(cur.lastrowid)
        for criteria_id, answer_data in payload["answers"].items():
            conn.execute(
                """
                INSERT INTO advisory_answers (record_id, criteria_id, answer, comment)
                VALUES (?, ?, ?, ?)
                """,
                (record_id, criteria_id, answer_data["answer"], answer_data.get("comment", "")),
            )
        conn.execute(
            """
            UPDATE advisory_sessions
            SET actual_date = ?, status = ?, locked = ?
            WHERE id = ?
            """,
            (actual_date, "Preenchida" if lock_record else "Rascunho", 1 if lock_record else 0, session_id),
        )
    if old_record and user["role"] == "coordenacao":
        log_action(
            user["id"],
            "Edição de ficha preenchida",
            "advisory_records",
            old_record["id"],
            json.dumps(old_snapshot, ensure_ascii=False),
            json.dumps(snapshot_record(session_id), ensure_ascii=False),
            justification,
        )
    return record_id


def snapshot_record(session_id: int) -> dict:
    record = get_record(session_id)
    if not record:
        return {}
    return {
        "record": dict(record),
        "answers": [dict(row) for row in query("SELECT * FROM advisory_answers WHERE record_id = ?", (record["id"],))],
    }


def unlock_session(session_id: int, user_id: int, justification: str) -> None:
    before = dict(query_one("SELECT * FROM advisory_sessions WHERE id = ?", (session_id,)))
    execute("UPDATE advisory_sessions SET locked = 0 WHERE id = ?", (session_id,))
    after = dict(query_one("SELECT * FROM advisory_sessions WHERE id = ?", (session_id,)))
    log_action(user_id, "Destravou assessoria", "advisory_sessions", session_id, json.dumps(before), json.dumps(after), justification)


def update_planned_date(session_id: int, planned_date: str, user_id: int, justification: str) -> None:
    before = dict(query_one("SELECT * FROM advisory_sessions WHERE id = ?", (session_id,)))
    execute("UPDATE advisory_sessions SET planned_date = ? WHERE id = ?", (planned_date, session_id))
    after = dict(query_one("SELECT * FROM advisory_sessions WHERE id = ?", (session_id,)))
    log_action(user_id, "Alterou data prevista", "advisory_sessions", session_id, json.dumps(before), json.dumps(after), justification)


def list_pdf_exports(record_id: int):
    return query("SELECT * FROM pdf_exports WHERE record_id = ? ORDER BY generated_at DESC", (record_id,))
