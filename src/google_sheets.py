"""Integração simples com Google Sheets público/compartilhado por link.

O MVP lê as abas "Alunos" e "Critérios" via exportação CSV do Google Sheets.
Não usa API paga nem autenticação. A planilha precisa estar acessível para
"qualquer pessoa com o link".
"""

from __future__ import annotations

import re
from urllib.parse import quote

import pandas as pd

from .database import execute, get_connection, query_one
from .seed import ensure_sessions_for_all_orientations


def get_google_sheet_url() -> str:
    row = query_one("SELECT value FROM settings WHERE key = ?", ("google_sheet_url",))
    return row["value"] if row and row["value"] else ""


def save_google_sheet_url(url: str) -> None:
    execute(
        """
        INSERT INTO settings (key, value)
        VALUES ('google_sheet_url', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (url.strip(),),
    )


def import_from_google_sheets() -> dict:
    sheet_url = get_google_sheet_url()
    if not sheet_url:
        return {"ok": False, "message": "Informe e salve o link da planilha antes de importar."}

    spreadsheet_id = extract_spreadsheet_id(sheet_url)
    if not spreadsheet_id:
        return {"ok": False, "message": "Não consegui identificar o ID da planilha no link informado."}

    try:
        alunos_df = read_sheet(spreadsheet_id, "Alunos")
        criterios_df = read_first_available_sheet(spreadsheet_id, ["Criterios", "Critérios"])
        result = replace_academic_data(alunos_df, criterios_df)
    except Exception as exc:
        return {
            "ok": False,
            "message": (
                "Falha ao importar. Confira se a planilha está compartilhada para "
                f"'qualquer pessoa com o link' e se as abas se chamam Alunos e Criterios. Detalhe: {exc}"
            ),
        }
    return {
        "ok": True,
        "message": (
            f"Importação concluída: {result['students']} alunos, "
            f"{result['criteria']} critérios e {result['sessions']} assessorias criadas."
        ),
    }


def extract_spreadsheet_id(value: str) -> str | None:
    value = value.strip()
    if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", value):
        return value
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", value)
    return match.group(1) if match else None


def read_sheet(spreadsheet_id: str, sheet_name: str) -> pd.DataFrame:
    url = (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq"
        f"?tqx=out:csv&sheet={quote(sheet_name)}"
    )
    df = pd.read_csv(url, dtype=str).fillna("")
    df.columns = [normalize_header(col) for col in df.columns]
    return df


def read_first_available_sheet(spreadsheet_id: str, sheet_names: list[str]) -> pd.DataFrame:
    last_error = None
    for sheet_name in sheet_names:
        try:
            return read_sheet(spreadsheet_id, sheet_name)
        except Exception as exc:
            last_error = exc
    raise ValueError(f"Não consegui ler nenhuma destas abas: {', '.join(sheet_names)}. Último erro: {last_error}")


def normalize_header(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace(" ", "_")
        .replace("ç", "c")
        .replace("ã", "a")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )


def replace_academic_data(alunos_df: pd.DataFrame, criterios_df: pd.DataFrame) -> dict:
    required_alunos = {"nome", "email", "etapa_tfg", "tema", "ano", "semestre", "professor", "email_professor"}
    required_criterios = {"etapa_tfg", "fase", "criterio", "descricao", "comentario_obrigatorio_quando_nao_sim", "ativo"}
    missing_alunos = required_alunos - set(alunos_df.columns)
    missing_criterios = required_criterios - set(criterios_df.columns)
    if missing_alunos:
        raise ValueError(f"Aba Alunos sem colunas: {', '.join(sorted(missing_alunos))}")
    if missing_criterios:
        raise ValueError(f"Aba Critérios sem colunas: {', '.join(sorted(missing_criterios))}")

    alunos_df = alunos_df[alunos_df["nome"].str.strip() != ""]
    criterios_df = criterios_df[criterios_df["criterio"].str.strip() != ""]
    alunos_df = alunos_df.copy()
    criterios_df = criterios_df.copy()
    alunos_df["etapa_tfg"] = alunos_df["etapa_tfg"].apply(normalize_tfg_stage)
    criterios_df["etapa_tfg"] = criterios_df["etapa_tfg"].apply(normalize_tfg_stage)
    validate_tfg_stages(alunos_df, "Alunos")
    validate_tfg_stages(criterios_df, "Criterios")

    with get_connection() as conn:
        conn.executescript(
            """
            DELETE FROM pdf_exports;
            DELETE FROM advisory_answers;
            DELETE FROM advisory_records;
            DELETE FROM advisory_sessions;
            DELETE FROM orientations;
            DELETE FROM students;
            DELETE FROM criteria;
            """
        )

        for _, row in criterios_df.iterrows():
            conn.execute(
                """
                INSERT INTO criteria
                    (tfg_stage, phase, group_name, description, required_comment_when_not_yes, active)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["etapa_tfg"],
                    clean(row["fase"]),
                    clean(row["criterio"]),
                    clean(row["descricao"]),
                    yes_no_to_int(row["comentario_obrigatorio_quando_nao_sim"]),
                    yes_no_to_int(row["ativo"]),
                ),
            )

        for _, row in alunos_df.iterrows():
            advisor_id = ensure_advisor(conn, clean(row["professor"]), clean(row["email_professor"]))
            student_id = conn.execute(
                """
                INSERT INTO students (name, ra, email, tfg_stage, theme, year, semester)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean(row["nome"]),
                    clean(row.get("ra", "")),
                    clean(row["email"]),
                    row["etapa_tfg"],
                    clean(row["tema"]),
                    int(clean(row["ano"]) or 2026),
                    int(clean(row["semestre"]) or 1),
                ),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO orientations (student_id, advisor_id, year, semester)
                VALUES (?, ?, ?, ?)
                """,
                (
                    student_id,
                    advisor_id,
                    int(clean(row["ano"]) or 2026),
                    int(clean(row["semestre"]) or 1),
                ),
            )

    ensure_sessions_for_all_orientations()
    sessions = query_one("SELECT COUNT(*) AS total FROM advisory_sessions")
    return {
        "students": len(alunos_df),
        "criteria": len(criterios_df),
        "sessions": sessions["total"] if sessions else 0,
    }


def ensure_advisor(conn, name: str, email: str) -> int:
    email = email or name.lower().replace(" ", "_")
    row = conn.execute("SELECT id FROM advisors WHERE lower(email) = lower(?)", (email,)).fetchone()
    if row:
        return row["id"]

    user = conn.execute("SELECT id FROM users WHERE lower(email) = lower(?)", (email,)).fetchone()
    if user:
        user_id = user["id"]
    else:
        user_id = conn.execute(
            "INSERT INTO users (name, email, password, role) VALUES (?, ?, 'professor123', 'professor')",
            (name, email),
        ).lastrowid
    return conn.execute(
        "INSERT INTO advisors (user_id, name, email) VALUES (?, ?, ?)",
        (user_id, name, email),
    ).lastrowid


def clean(value: object) -> str:
    return str(value).strip()


def yes_no_to_int(value: object) -> int:
    return 1 if clean(value).lower() in {"sim", "s", "yes", "1", "true", "ativo"} else 0


def normalize_tfg_stage(value: object) -> str:
    text = clean(value).upper().replace("º", "").replace("°", "")
    text = re.sub(r"\s+", " ", text)
    aliases = {
        "TFG I": "TFG I",
        "TFGI": "TFG I",
        "TFG 1": "TFG I",
        "TFG1": "TFG I",
        "I": "TFG I",
        "1": "TFG I",
        "TFG II": "TFG II",
        "TFGII": "TFG II",
        "TFG 2": "TFG II",
        "TFG2": "TFG II",
        "II": "TFG II",
        "2": "TFG II",
    }
    return aliases.get(text, clean(value))


def validate_tfg_stages(df: pd.DataFrame, sheet_name: str) -> None:
    invalid = sorted(set(df.loc[~df["etapa_tfg"].isin(["TFG I", "TFG II"]), "etapa_tfg"]))
    if invalid:
        raise ValueError(
            f"Aba {sheet_name}: valores inválidos em etapa_tfg: {', '.join(invalid)}. "
            "Use TFG I ou TFG II."
        )
