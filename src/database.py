from __future__ import annotations

import os
import re
import sqlite3
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "tfg_assessorias.db"
PDF_DIR = BASE_DIR / "output" / "pdfs"
SECRETS_PATH = BASE_DIR / ".streamlit" / "secrets.toml"
RUNTIME_SETTINGS_PATH = DATA_DIR / "runtime_settings.json"


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def _load_secrets_file() -> dict[str, Any]:
    if not SECRETS_PATH.exists():
        return {}
    try:
        return tomllib.loads(SECRETS_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _load_runtime_settings() -> dict[str, Any]:
    ensure_directories()
    if not RUNTIME_SETTINGS_PATH.exists():
        return {}
    try:
        import json

        return json.loads(RUNTIME_SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


@lru_cache(maxsize=1)
def get_database_backend() -> str:
    value = os.getenv("DATABASE_BACKEND", "").strip().lower()
    if value in {"sqlite", "neon"}:
        return value

    secrets_value = str(_load_secrets_file().get("DATABASE_BACKEND", "")).strip().lower()
    if secrets_value in {"sqlite", "neon"}:
        return secrets_value

    try:
        import streamlit as st

        streamlit_value = str(st.secrets.get("DATABASE_BACKEND", "")).strip().lower()
        if streamlit_value in {"sqlite", "neon"}:
            return streamlit_value
    except Exception:
        pass

    if get_database_url().lower().startswith(("postgres://", "postgresql://")):
        return "neon"

    runtime_value = str(_load_runtime_settings().get("database_backend", "")).strip().lower()
    if runtime_value in {"sqlite", "neon"}:
        return runtime_value

    return "sqlite"


@lru_cache(maxsize=1)
def get_database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if value:
        return value

    file_value = str(_load_secrets_file().get("DATABASE_URL", "")).strip()
    if file_value:
        return file_value

    try:
        import streamlit as st

        return str(st.secrets.get("DATABASE_URL", "")).strip()
    except Exception:
        return ""


def set_database_backend(backend: str) -> None:
    normalized = str(backend).strip().lower()
    if normalized not in {"sqlite", "neon"}:
        raise ValueError("Backend inválido. Use 'sqlite' ou 'neon'.")
    ensure_directories()
    import json

    payload = _load_runtime_settings().copy()
    payload["database_backend"] = normalized
    RUNTIME_SETTINGS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _load_runtime_settings.cache_clear()
    get_database_backend.cache_clear()
    get_database_url.cache_clear()


def using_postgres() -> bool:
    return get_database_backend() == "neon" and get_database_url().lower().startswith(("postgres://", "postgresql://"))


def database_label() -> str:
    if get_database_backend() == "neon":
        if using_postgres():
            return "Neon/PostgreSQL"
        return "Neon/PostgreSQL (não configurado)"
    if using_postgres():
        return "Neon/PostgreSQL"
    return f"SQLite: {DB_PATH}"


class CursorAdapter:
    def __init__(self, cursor: Any, lastrowid: int = 0) -> None:
        self._cursor = cursor
        self.lastrowid = lastrowid

    @property
    def rowcount(self) -> int:
        return int(getattr(self._cursor, "rowcount", 0) or 0)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class DatabaseConnection:
    def __init__(
        self,
        conn: Any,
        backend: str,
        context_manager: Any | None = None,
        close_on_exit: bool = False,
    ) -> None:
        self.conn = conn
        self.backend = backend
        self._context_manager = context_manager
        self._close_on_exit = close_on_exit

    def __enter__(self):
        if self._context_manager is None:
            self.conn.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._context_manager is not None:
            return self._context_manager.__exit__(exc_type, exc, tb)
        result = self.conn.__exit__(exc_type, exc, tb)
        if self._close_on_exit:
            self.conn.close()
        return result

    def commit(self) -> None:
        self.conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> CursorAdapter:
        if self.backend == "postgres":
            return self._execute_postgres(sql, params)
        cursor = self.conn.execute(sql, params)
        return CursorAdapter(cursor, int(getattr(cursor, "lastrowid", 0) or 0))

    def executescript(self, script: str) -> None:
        if self.backend == "sqlite":
            self.conn.executescript(script)
            return
        for statement in _split_sql_script(script):
            self.execute(statement)

    def _execute_postgres(self, sql: str, params: tuple = ()) -> CursorAdapter:
        converted = _convert_placeholders(sql)
        converted, should_capture_id = _add_returning_id(converted)
        cursor = self.conn.execute(converted, params)
        lastrowid = 0
        if should_capture_id:
            row = cursor.fetchone()
            if row:
                lastrowid = int(row["id"])
        return CursorAdapter(cursor, lastrowid)


def _split_sql_script(script: str) -> list[str]:
    return [part.strip() for part in script.split(";") if part.strip()]


def _convert_placeholders(sql: str) -> str:
    return sql.replace("?", "%s")


def _add_returning_id(sql: str) -> tuple[str, bool]:
    stripped = sql.strip().rstrip(";")
    lower = stripped.lower()
    if not lower.startswith("insert ") or " returning " in lower:
        return sql, False
    return f"{stripped} RETURNING id", True


@lru_cache(maxsize=1)
def _get_postgres_pool(database_url: str) -> Any | None:
    try:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
    except ImportError:
        return None

    pool = ConnectionPool(
        conninfo=database_url,
        kwargs={"row_factory": dict_row},
        min_size=1,
        max_size=int(os.getenv("DATABASE_POOL_MAX_SIZE", "5")),
        max_idle=float(os.getenv("DATABASE_POOL_MAX_IDLE", "60")),
        check=ConnectionPool.check_connection,
        open=False,
    )
    pool.open()
    return pool


def get_connection() -> DatabaseConnection:
    ensure_directories()
    if get_database_backend() == "neon":
        if not using_postgres():
            raise RuntimeError(
                "O backend Neon está selecionado, mas a DATABASE_URL não está configurada em variável de ambiente ou .streamlit/secrets.toml."
            )
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "Para usar Neon/PostgreSQL, instale as dependencias com: py -m pip install -r requirements.txt"
            ) from exc
        pool = _get_postgres_pool(get_database_url())
        if pool is not None:
            context_manager = pool.connection()
            conn = context_manager.__enter__()
            return DatabaseConnection(conn, "postgres", context_manager=context_manager)
        conn = psycopg.connect(get_database_url(), row_factory=dict_row)
        return DatabaseConnection(conn, "postgres", close_on_exit=True)

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    return DatabaseConnection(conn, "sqlite", close_on_exit=True)


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('professor', 'coordenacao')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    ra TEXT,
    email TEXT,
    tfg_stage TEXT NOT NULL CHECK (tfg_stage IN ('TFG I', 'TFG II')),
    theme TEXT NOT NULL,
    year INTEGER NOT NULL,
    semester INTEGER NOT NULL,
    plan_partial_1 REAL,
    plan_partial_2 REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS advisors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS orientations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    advisor_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    semester INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (advisor_id) REFERENCES advisors(id)
);

CREATE TABLE IF NOT EXISTS criteria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tfg_stage TEXT NOT NULL,
    phase TEXT NOT NULL,
    group_name TEXT NOT NULL,
    description TEXT NOT NULL,
    required_comment_when_not_yes INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS advisory_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orientation_id INTEGER NOT NULL,
    session_number INTEGER NOT NULL,
    tfg_stage TEXT NOT NULL,
    phase TEXT NOT NULL,
    planned_date TEXT NOT NULL,
    actual_date TEXT,
    locked INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'Pendente',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (orientation_id, session_number),
    FOREIGN KEY (orientation_id) REFERENCES orientations(id)
);

CREATE TABLE IF NOT EXISTS advisory_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL UNIQUE,
    advisor_id INTEGER NOT NULL,
    general_notes TEXT,
    referrals TEXT,
    pending_issues TEXT,
    final_evaluation TEXT CHECK (final_evaluation IN ('Sim', 'Não', 'Parcial')),
    final_comment TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES advisory_sessions(id),
    FOREIGN KEY (advisor_id) REFERENCES advisors(id)
);

CREATE TABLE IF NOT EXISTS advisory_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    criteria_id INTEGER NOT NULL,
    answer TEXT NOT NULL,
    comment TEXT,
    UNIQUE (record_id, criteria_id),
    FOREIGN KEY (record_id) REFERENCES advisory_records(id) ON DELETE CASCADE,
    FOREIGN KEY (criteria_id) REFERENCES criteria(id)
);

CREATE TABLE IF NOT EXISTS exam_boards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    stage TEXT NOT NULL CHECK (stage IN ('Pré-Banca', 'Banca Final', 'Plano de Ocupação')),
    scheduled_date TEXT NOT NULL,
    scheduled_time TEXT,
    location TEXT,
    status TEXT NOT NULL DEFAULT 'Pendente',
    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (student_id, stage),
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS exam_board_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id INTEGER NOT NULL,
    advisor_id INTEGER NOT NULL,
    member_role TEXT NOT NULL CHECK (member_role IN ('orientador', 'avaliador')),
    can_grade INTEGER NOT NULL DEFAULT 1,
    can_record_minutes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (board_id, advisor_id),
    FOREIGN KEY (board_id) REFERENCES exam_boards(id) ON DELETE CASCADE,
    FOREIGN KEY (advisor_id) REFERENCES advisors(id)
);

CREATE TABLE IF NOT EXISTS exam_criteria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage TEXT NOT NULL CHECK (stage IN ('Pré-Banca', 'Banca Final', 'Plano de Ocupação')),
    criterion TEXT NOT NULL,
    description TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (stage, criterion)
);

CREATE TABLE IF NOT EXISTS exam_grades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id INTEGER NOT NULL,
    advisor_id INTEGER NOT NULL,
    criterion_id INTEGER NOT NULL,
    grade REAL NOT NULL,
    observation TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (board_id, advisor_id, criterion_id),
    FOREIGN KEY (board_id) REFERENCES exam_boards(id) ON DELETE CASCADE,
    FOREIGN KEY (advisor_id) REFERENCES advisors(id),
    FOREIGN KEY (criterion_id) REFERENCES exam_criteria(id)
);

CREATE TABLE IF NOT EXISTS exam_minutes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id INTEGER NOT NULL UNIQUE,
    advisor_id INTEGER NOT NULL,
    minutes_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (board_id) REFERENCES exam_boards(id) ON DELETE CASCADE,
    FOREIGN KEY (advisor_id) REFERENCES advisors(id)
);

CREATE TABLE IF NOT EXISTS pdf_exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (record_id) REFERENCES advisory_records(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    table_name TEXT NOT NULL,
    record_id INTEGER,
    old_value TEXT,
    new_value TEXT,
    justification TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT
);
"""

POSTGRES_SCHEMA = SQLITE_SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")

INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_students_ra ON students(ra);
CREATE INDEX IF NOT EXISTS idx_users_email_name ON users(email, name);
CREATE INDEX IF NOT EXISTS idx_students_stage_period ON students(tfg_stage, year, semester);
CREATE INDEX IF NOT EXISTS idx_orientations_student ON orientations(student_id);
CREATE INDEX IF NOT EXISTS idx_orientations_advisor_period ON orientations(advisor_id, year, semester);
CREATE INDEX IF NOT EXISTS idx_sessions_orientation_number ON advisory_sessions(orientation_id, session_number);
CREATE INDEX IF NOT EXISTS idx_sessions_stage_status ON advisory_sessions(tfg_stage, status);
CREATE INDEX IF NOT EXISTS idx_records_session ON advisory_records(session_id);
CREATE INDEX IF NOT EXISTS idx_answers_record ON advisory_answers(record_id);
CREATE INDEX IF NOT EXISTS idx_exam_boards_student_stage ON exam_boards(student_id, stage);
CREATE INDEX IF NOT EXISTS idx_exam_boards_date ON exam_boards(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_exam_members_board ON exam_board_members(board_id);
CREATE INDEX IF NOT EXISTS idx_exam_members_advisor ON exam_board_members(advisor_id);
CREATE INDEX IF NOT EXISTS idx_exam_criteria_stage ON exam_criteria(stage, active);
CREATE INDEX IF NOT EXISTS idx_exam_grades_board_advisor ON exam_grades(board_id, advisor_id);
CREATE INDEX IF NOT EXISTS idx_exam_minutes_board ON exam_minutes(board_id);
CREATE INDEX IF NOT EXISTS idx_pdf_exports_record_date ON pdf_exports(record_id, generated_at);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_log(created_at);
"""


def init_db() -> None:
    ensure_directories()
    with get_connection() as conn:
        conn.executescript(POSTGRES_SCHEMA if conn.backend == "postgres" else SQLITE_SCHEMA)
        _migrate_student_partial_grades(conn)
        if conn.backend == "sqlite":
            _migrate_students_ra(conn)
            _migrate_answer_scale(conn)
        _ensure_indexes(conn)



def _migrate_student_partial_grades(conn: DatabaseConnection) -> None:
    if conn.backend == "postgres":
        conn.execute("ALTER TABLE students ADD COLUMN IF NOT EXISTS plan_partial_1 REAL")
        conn.execute("ALTER TABLE students ADD COLUMN IF NOT EXISTS plan_partial_2 REAL")
        return

    columns = [row["name"] for row in conn.execute("PRAGMA table_info(students)").fetchall()]
    if "plan_partial_1" not in columns:
        conn.execute("ALTER TABLE students ADD COLUMN plan_partial_1 REAL")
    if "plan_partial_2" not in columns:
        conn.execute("ALTER TABLE students ADD COLUMN plan_partial_2 REAL")

def _migrate_students_ra(conn: DatabaseConnection) -> None:
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(students)").fetchall()]
    if "ra" not in columns:
        conn.execute("ALTER TABLE students ADD COLUMN ra TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_students_ra ON students(ra)")


def _ensure_indexes(conn: DatabaseConnection) -> None:
    conn.executescript(INDEXES_SQL)


def _migrate_answer_scale(conn: DatabaseConnection) -> None:
    table_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'advisory_answers'"
    ).fetchone()
    if not table_sql or "CHECK (answer IN" not in table_sql["sql"]:
        return
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;
        ALTER TABLE advisory_answers RENAME TO advisory_answers_old;
        CREATE TABLE advisory_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            criteria_id INTEGER NOT NULL,
            answer TEXT NOT NULL,
            comment TEXT,
            UNIQUE (record_id, criteria_id),
            FOREIGN KEY (record_id) REFERENCES advisory_records(id) ON DELETE CASCADE,
            FOREIGN KEY (criteria_id) REFERENCES criteria(id)
        );
        INSERT INTO advisory_answers (id, record_id, criteria_id, answer, comment)
        SELECT id, record_id, criteria_id, answer, comment
        FROM advisory_answers_old;
        DROP TABLE advisory_answers_old;
        PRAGMA foreign_keys = ON;
        """
    )


def _is_postgres_operational_error(exc: Exception) -> bool:
    try:
        import psycopg
    except ImportError:
        return False
    return isinstance(exc, psycopg.OperationalError)


def _reset_postgres_pool() -> None:
    if not using_postgres():
        return
    try:
        pool = _get_postgres_pool(get_database_url())
    except Exception:
        pool = None
    if pool is not None:
        try:
            pool.close(timeout=1)
        except TypeError:
            pool.close()
        except Exception:
            pass
    _get_postgres_pool.cache_clear()


def _read_with_reconnect(operation):
    try:
        return operation()
    except Exception as exc:
        if get_database_backend() == "neon" and _is_postgres_operational_error(exc):
            _reset_postgres_pool()
            return operation()
        raise


def query(sql: str, params: tuple = ()) -> list[Any]:
    def operation():
        with get_connection() as conn:
            return conn.execute(sql, params).fetchall()

    return _read_with_reconnect(operation)


def query_one(sql: str, params: tuple = ()) -> Any | None:
    def operation():
        with get_connection() as conn:
            return conn.execute(sql, params).fetchone()

    return _read_with_reconnect(operation)


def execute(sql: str, params: tuple = ()) -> int:
    with get_connection() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return int(cur.lastrowid)


