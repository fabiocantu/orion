from __future__ import annotations

import argparse
import sqlite3
import tomllib
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from src.database import DB_PATH, INDEXES_SQL, POSTGRES_SCHEMA, SECRETS_PATH, set_database_backend


TABLES = [
    "users",
    "students",
    "advisors",
    "orientations",
    "criteria",
    "advisory_sessions",
    "advisory_records",
    "advisory_answers",
    "exam_boards",
    "exam_board_members",
    "exam_criteria",
    "exam_grades",
    "exam_minutes",
    "pdf_exports",
    "audit_log",
    "settings",
]


def load_database_url() -> str:
    if not SECRETS_PATH.exists():
        return ""
    payload = tomllib.loads(SECRETS_PATH.read_text(encoding="utf-8-sig"))
    return str(payload.get("DATABASE_URL", "")).strip()


def split_sql(script: str) -> list[str]:
    return [statement.strip() for statement in script.split(";") if statement.strip()]


def sqlite_rows(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()


def clear_postgres(conn: psycopg.Connection) -> None:
    table_list = ", ".join(TABLES)
    conn.execute(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE")


def ensure_postgres_schema(conn: psycopg.Connection) -> None:
    for statement in split_sql(POSTGRES_SCHEMA):
        conn.execute(statement)
    for statement in split_sql(INDEXES_SQL):
        conn.execute(statement)


def copy_table(sqlite_conn: sqlite3.Connection, pg_conn: psycopg.Connection, table: str) -> int:
    rows = sqlite_rows(sqlite_conn, table)
    if not rows:
        return 0

    columns = rows[0].keys()
    column_sql = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    insert_sql = f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})"

    for row in rows:
        pg_conn.execute(insert_sql, tuple(row[column] for column in columns))
    return len(rows)


def reset_sequence(pg_conn: psycopg.Connection, table: str) -> None:
    pg_conn.execute(
        """
        SELECT setval(
            pg_get_serial_sequence(%s, 'id'),
            COALESCE((SELECT MAX(id) FROM """ + table + """), 1),
            (SELECT COUNT(*) > 0 FROM """ + table + """)
        )
        """,
        (table,),
    )


def migrate(activate: bool) -> None:
    database_url = load_database_url()
    if not database_url:
        raise SystemExit("DATABASE_URL nao encontrada em .streamlit/secrets.toml.")
    if not DB_PATH.exists():
        raise SystemExit(f"SQLite local nao encontrado: {DB_PATH}")

    with sqlite3.connect(DB_PATH) as sqlite_conn:
        sqlite_conn.row_factory = sqlite3.Row
        with psycopg.connect(database_url, row_factory=dict_row) as pg_conn:
            ensure_postgres_schema(pg_conn)
            clear_postgres(pg_conn)

            totals: dict[str, int] = {}
            for table in TABLES:
                totals[table] = copy_table(sqlite_conn, pg_conn, table)
            for table in TABLES:
                reset_sequence(pg_conn, table)
            pg_conn.commit()

    if activate:
        set_database_backend("neon")

    print("Migracao SQLite -> Neon concluida.")
    for table, total in totals.items():
        print(f"- {table}: {total}")
    print("Backend ativo: Neon" if activate else "Backend ativo nao foi alterado.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migra o SQLite local para Neon/PostgreSQL.")
    parser.add_argument("--confirm", action="store_true", help="Confirma limpar o Neon antes de copiar os dados.")
    parser.add_argument("--activate", action="store_true", help="Ativa o backend Neon apos migrar com sucesso.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.confirm:
        raise SystemExit("Use --confirm para autorizar a limpeza do Neon e a migracao dos dados.")
    migrate(activate=args.activate)


if __name__ == "__main__":
    main()
