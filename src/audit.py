from __future__ import annotations

from .database import execute, query


def log_action(
    user_id: int,
    action: str,
    table_name: str,
    record_id: int | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    justification: str | None = None,
) -> None:
    execute(
        """
        INSERT INTO audit_log
            (user_id, action, table_name, record_id, old_value, new_value, justification)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, action, table_name, record_id, old_value, new_value, justification),
    )


def list_audit(limit: int = 100):
    return query(
        """
        SELECT audit_log.*, users.name AS user_name
        FROM audit_log
        JOIN users ON users.id = audit_log.user_id
        ORDER BY audit_log.created_at DESC
        LIMIT ?
        """,
        (limit,),
    )
