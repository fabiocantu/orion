from __future__ import annotations

from datetime import date

from .timezone import today_local
from typing import Any

from .boards import advisor_id_for_user
from .database import query, query_one
from .utils import format_date_br


def _total(row: Any | None, key: str = "total") -> int:
    if not row:
        return 0
    return int(row[key] or 0)


def dashboard_snapshot(user: dict) -> dict:
    advisor_id = advisor_id_for_user(user["id"]) if user["role"] == "professor" else None
    session_filter, session_params = _session_scope(user, advisor_id)
    board_filter, board_params = _board_scope(user, advisor_id)
    today = today_local().isoformat()

    students_total = _total(
        query_one(
            f"""
            SELECT COUNT(DISTINCT students.id) AS total
            FROM students
            JOIN orientations ON orientations.student_id = students.id
            JOIN advisors ON advisors.id = orientations.advisor_id
            {session_filter}
            """,
            tuple(session_params),
        )
    )
    pending_sessions = _total(
        query_one(
            f"""
            SELECT COUNT(*) AS total
            FROM advisory_sessions
            JOIN orientations ON orientations.id = advisory_sessions.orientation_id
            JOIN advisors ON advisors.id = orientations.advisor_id
            JOIN students ON students.id = orientations.student_id
            {session_filter}
              {_and_clause(session_filter)} advisory_sessions.status IN ('Pendente', 'Rascunho')
            """,
            tuple(session_params),
        )
    )
    late_sessions = _total(
        query_one(
            f"""
            SELECT COUNT(*) AS total
            FROM advisory_sessions
            JOIN orientations ON orientations.id = advisory_sessions.orientation_id
            JOIN advisors ON advisors.id = orientations.advisor_id
            JOIN students ON students.id = orientations.student_id
            {session_filter}
              {_and_clause(session_filter)} advisory_sessions.status IN ('Pendente', 'Rascunho')
              AND advisory_sessions.planned_date < ?
            """,
            tuple(session_params + [today]),
        )
    )
    today_boards = _total(
        query_one(
            f"""
            SELECT COUNT(*) AS total
            FROM exam_boards
            JOIN students ON students.id = exam_boards.student_id
            {board_filter}
              {_and_clause(board_filter)} exam_boards.scheduled_date = ?
            """,
            tuple(board_params + [today]),
        )
    )
    pending_boards = _total(
        query_one(
            f"""
            SELECT COUNT(*) AS total
            FROM exam_boards
            JOIN students ON students.id = exam_boards.student_id
            {board_filter}
              {_and_clause(board_filter)} exam_boards.status <> 'Completa'
            """,
            tuple(board_params),
        )
    )

    return {
        "advisor_id": advisor_id,
        "kpis": [
            ("Alunos", students_total, "com vínculo ativo"),
            ("Fichas pendentes", pending_sessions, f"{late_sessions} vencida(s)"),
            ("Bancas hoje", today_boards, "agenda do dia"),
            ("Bancas pendentes", pending_boards, "nota ou ata em aberto"),
        ],
        "pending_sessions": pending_advisory_sessions(user, advisor_id),
        "today_boards": dashboard_boards(user, advisor_id, only_today=True),
        "upcoming_boards": dashboard_boards(user, advisor_id, only_today=False),
    }


def pending_advisory_sessions(user: dict, advisor_id: int | None, limit: int = 8) -> list[dict]:
    where_sql, params = _session_scope(user, advisor_id)
    rows = query(
        f"""
        SELECT students.name AS student_name, students.tfg_stage, students.theme,
               advisors.name AS advisor_name, advisory_sessions.session_number,
               advisory_sessions.phase, advisory_sessions.planned_date,
               advisory_sessions.status
        FROM advisory_sessions
        JOIN orientations ON orientations.id = advisory_sessions.orientation_id
        JOIN advisors ON advisors.id = orientations.advisor_id
        JOIN students ON students.id = orientations.student_id
        {where_sql}
          {_and_clause(where_sql)} advisory_sessions.status IN ('Pendente', 'Rascunho')
        ORDER BY advisory_sessions.planned_date, students.name, advisory_sessions.session_number
        LIMIT ?
        """,
        tuple(params + [limit]),
    )
    return [
        {
            "title": f"{row['student_name']} - assessoria {row['session_number']}",
            "meta": f"{row['tfg_stage']} | {row['phase']} | prevista {format_date_br(row['planned_date'])} | {row['advisor_name']}",
            "status": row["status"],
        }
        for row in rows
    ]


def dashboard_boards(user: dict, advisor_id: int | None, only_today: bool, limit: int = 8) -> list[dict]:
    where_sql, params = _board_scope(user, advisor_id)
    today = today_local().isoformat()
    date_filter = "exam_boards.scheduled_date = ?" if only_today else "exam_boards.scheduled_date >= ?"
    rows = query(
        f"""
        SELECT exam_boards.stage, exam_boards.scheduled_date, exam_boards.scheduled_time,
               exam_boards.location, exam_boards.status, students.name AS student_name,
               students.theme
        FROM exam_boards
        JOIN students ON students.id = exam_boards.student_id
        {where_sql}
          {_and_clause(where_sql)} {date_filter}
        ORDER BY exam_boards.scheduled_date, exam_boards.scheduled_time, students.name
        LIMIT ?
        """,
        tuple(params + [today, limit]),
    )
    return [
        {
            "title": f"{row['student_name']} - {row['stage']}",
            "meta": " | ".join(
                part
                for part in [
                    format_date_br(row["scheduled_date"]),
                    row["scheduled_time"] or "",
                    row["location"] or "",
                    row["theme"] or "",
                ]
                if part
            ),
            "status": row["status"],
        }
        for row in rows
    ]


def _session_scope(user: dict, advisor_id: int | None) -> tuple[str, list[object]]:
    if user["role"] == "professor":
        return "WHERE advisors.id = ?", [advisor_id or -1]
    return "", []


def _board_scope(user: dict, advisor_id: int | None) -> tuple[str, list[object]]:
    if user["role"] == "professor":
        return (
            """
            WHERE EXISTS (
                SELECT 1
                FROM exam_board_members
                WHERE exam_board_members.board_id = exam_boards.id
                  AND exam_board_members.advisor_id = ?
            )
            """,
            [advisor_id or -1],
        )
    return "", []


def _and_clause(where_sql: str) -> str:
    return "AND" if where_sql.strip() else "WHERE"
