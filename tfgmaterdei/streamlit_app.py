import json
import re
import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

try:
    from fpdf import FPDF
except ModuleNotFoundError:
    FPDF = None

try:
    import plotly.express as px
except ModuleNotFoundError:
    px = None

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Json
except ModuleNotFoundError:
    psycopg = None
    dict_row = None
    Json = None

st.set_page_config(page_title="Avaliação de TFG - Bancas", layout="wide", page_icon="🏛️")

BASE_DIR = Path(__file__).resolve().parent

ETAPAS = ["Pré-Banca", "Banca Final", "Plano de Ocupação"]
NOTAS_COLUMNS = ['Data_Hora', 'Etapa', 'Professor_Avaliador', 'Aluno_Avaliado', 'Criterio', 'Nota', 'Observacao']
ATAS_COLUMNS = ['Data_Hora', 'Etapa', 'Professor_Avaliador', 'Aluno_Avaliado', 'Ata']
ALUNOS_REQUIRED_COLUMNS = {'Nome', 'Tema', 'Orientador', 'Etapa'}
CRITERIOS_REQUIRED_COLUMNS = {'Etapa', 'Criterio', 'Descricao'}

# Dicionário com escalas máximas por etapa
ESCALAS_ETAPAS = {
    "Pré-Banca": 10.0,
    "Banca Final": 10.0,
    "Plano de Ocupação": 10.0
}


def get_data_file(filename: str) -> Path:
    candidates = [BASE_DIR / filename, Path.cwd() / filename]
    for path in candidates:
        if path.exists():
            return path
    return BASE_DIR / filename


def load_google_sheet_config() -> dict:
    config_path = get_data_file('google_sheet_config.json')
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def save_google_sheet_config(config: dict) -> None:
    config_path = get_data_file('google_sheet_config.json')
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')


def get_google_sheet_export_url(sheet_url: str, sheet_name: str) -> str | None:
    if not sheet_url:
        return None
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', sheet_url)
    if not match:
        return None
    sheet_id = match.group(1)
    return f'https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={quote(sheet_name)}'


def read_google_sheet_sheet(sheet_url: str, sheet_name: str) -> pd.DataFrame:
    export_url = get_google_sheet_export_url(sheet_url, sheet_name)
    if not export_url:
        raise ValueError('URL do Google Sheets inválida.')
    return pd.read_csv(export_url)


def get_dashboard_password() -> str:
    try:
        secret_password = st.secrets.get('dashboard_password')
    except Exception:
        secret_password = None
    return os.getenv('TFG_DASHBOARD_PASSWORD') or secret_password or 'banca2026'


def get_database_url() -> str:
    try:
        secret_url = st.secrets.get('database_url') or st.secrets.get('neon_database_url')
    except Exception:
        secret_url = None
    return (os.getenv('DATABASE_URL') or os.getenv('NEON_DATABASE_URL') or secret_url or '').strip()


def missing_columns(df: pd.DataFrame, required_columns: set[str]) -> list[str]:
    return sorted(required_columns - set(df.columns))


def load_csv_database(path: Path, columns: list[str], numeric_columns: list[str] | None = None) -> pd.DataFrame:
    if path.exists():
        try:
            df = pd.read_csv(path)
        except Exception:
            df = pd.DataFrame(columns=columns)
    else:
        df = pd.DataFrame(columns=columns)
        df.to_csv(path, index=False, encoding='utf-8')

    for column in columns:
        if column not in df.columns:
            df[column] = None

    if numeric_columns:
        for column in numeric_columns:
            df[column] = pd.to_numeric(df[column], errors='coerce')

    return df[columns]


def database_enabled() -> bool:
    return bool(globals().get('DATABASE_ENABLED', False))


def database_label() -> str:
    if database_enabled():
        return "Neon/Postgres"
    return "Arquivos locais CSV/JSON"


def db_connect():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_database() -> None:
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS notas_banca (
                    id BIGSERIAL PRIMARY KEY,
                    data_hora TEXT NOT NULL,
                    etapa TEXT NOT NULL,
                    professor_avaliador TEXT NOT NULL,
                    aluno_avaliado TEXT NOT NULL,
                    criterio TEXT NOT NULL,
                    nota NUMERIC,
                    observacao TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (professor_avaliador, aluno_avaliado, etapa, criterio)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS atas_banca (
                    id BIGSERIAL PRIMARY KEY,
                    data_hora TEXT NOT NULL,
                    etapa TEXT NOT NULL,
                    professor_avaliador TEXT NOT NULL,
                    aluno_avaliado TEXT NOT NULL,
                    ata TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (professor_avaliador, aluno_avaliado, etapa)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS rascunhos_banca (
                    professor_avaliador TEXT NOT NULL,
                    aluno_avaliado TEXT NOT NULL,
                    etapa TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    notas JSONB NOT NULL DEFAULT '{}'::jsonb,
                    observacoes JSONB NOT NULL DEFAULT '{}'::jsonb,
                    PRIMARY KEY (professor_avaliador, aluno_avaliado, etapa)
                )
            """)


def load_database_table(table_name: str, columns: list[str]) -> pd.DataFrame:
    column_map = {
        'Data_Hora': 'data_hora',
        'Etapa': 'etapa',
        'Professor_Avaliador': 'professor_avaliador',
        'Aluno_Avaliado': 'aluno_avaliado',
        'Criterio': 'criterio',
        'Nota': 'nota',
        'Observacao': 'observacao',
        'Ata': 'ata',
    }
    select_columns = ', '.join(f'{column_map[column]} AS "{column}"' for column in columns)
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT {select_columns} FROM {table_name} ORDER BY data_hora')
            rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=columns)
    for column in columns:
        if column not in df.columns:
            df[column] = None
    if 'Nota' in df.columns:
        df['Nota'] = pd.to_numeric(df['Nota'], errors='coerce')
    return df[columns]


def save_notes_submission(professor: str, aluno: str, etapa: str, rows: list[dict]) -> None:
    if not database_enabled():
        df_novas = pd.DataFrame(rows)
        df_base = df_notas[
            ~(
                (df_notas['Professor_Avaliador'] == professor) &
                (df_notas['Aluno_Avaliado'] == aluno) &
                (df_notas['Etapa'] == etapa)
            )
        ]
        df_total = pd.concat([df_base, df_novas], ignore_index=True)
        df_total.to_csv(ARQUIVO_NOTAS, index=False, encoding='utf-8')
        return

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM notas_banca
                WHERE professor_avaliador = %s AND aluno_avaliado = %s AND etapa = %s
                """,
                (professor, aluno, etapa),
            )
            cur.executemany(
                """
                INSERT INTO notas_banca (
                    data_hora, etapa, professor_avaliador, aluno_avaliado, criterio, nota, observacao
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (professor_avaliador, aluno_avaliado, etapa, criterio)
                DO UPDATE SET
                    data_hora = EXCLUDED.data_hora,
                    nota = EXCLUDED.nota,
                    observacao = EXCLUDED.observacao,
                    updated_at = now()
                """,
                [
                    (
                        row['Data_Hora'], row['Etapa'], row['Professor_Avaliador'],
                        row['Aluno_Avaliado'], row['Criterio'], row['Nota'], row['Observacao']
                    )
                    for row in rows
                ],
            )


def save_ata_submission(professor: str, aluno: str, etapa: str, ata_text: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not database_enabled():
        nova_ata = pd.DataFrame([{
            'Data_Hora': timestamp,
            'Etapa': etapa,
            'Professor_Avaliador': professor,
            'Aluno_Avaliado': aluno,
            'Ata': ata_text
        }])
        df_atas_base = df_atas[
            ~(
                (df_atas['Professor_Avaliador'] == professor) &
                (df_atas['Aluno_Avaliado'] == aluno) &
                (df_atas['Etapa'] == etapa)
            )
        ]
        df_total = pd.concat([df_atas_base, nova_ata], ignore_index=True)
        df_total.to_csv(ARQUIVO_ATAS, index=False, encoding='utf-8')
        return

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO atas_banca (data_hora, etapa, professor_avaliador, aluno_avaliado, ata)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (professor_avaliador, aluno_avaliado, etapa)
                DO UPDATE SET
                    data_hora = EXCLUDED.data_hora,
                    ata = EXCLUDED.ata,
                    updated_at = now()
                """,
                (timestamp, etapa, professor, aluno, ata_text),
            )


def reset_assessments() -> None:
    if not database_enabled():
        pd.DataFrame(columns=NOTAS_COLUMNS).to_csv(ARQUIVO_NOTAS, index=False, encoding='utf-8')
        pd.DataFrame(columns=ATAS_COLUMNS).to_csv(ARQUIVO_ATAS, index=False, encoding='utf-8')
        save_drafts(ARQUIVO_RASCUNHOS, {})
        return

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute('TRUNCATE TABLE notas_banca, atas_banca, rascunhos_banca RESTART IDENTITY')


def delete_notes_submission(data_hora: str, etapa: str, professor: str, aluno: str) -> None:
    if not database_enabled():
        mask = (
            (df_notas['Data_Hora'] == data_hora) &
            (df_notas['Etapa'] == etapa) &
            (df_notas['Professor_Avaliador'] == professor) &
            (df_notas['Aluno_Avaliado'] == aluno)
        )
        df_notas.loc[~mask, NOTAS_COLUMNS].to_csv(ARQUIVO_NOTAS, index=False, encoding='utf-8')
        return

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM notas_banca
                WHERE data_hora = %s AND etapa = %s AND professor_avaliador = %s AND aluno_avaliado = %s
                """,
                (data_hora, etapa, professor, aluno),
            )


def delete_ata_submission(data_hora: str, etapa: str, professor: str, aluno: str) -> None:
    if not database_enabled():
        mask = (
            (df_atas['Data_Hora'] == data_hora) &
            (df_atas['Etapa'] == etapa) &
            (df_atas['Professor_Avaliador'] == professor) &
            (df_atas['Aluno_Avaliado'] == aluno)
        )
        df_atas.loc[~mask, ATAS_COLUMNS].to_csv(ARQUIVO_ATAS, index=False, encoding='utf-8')
        return

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM atas_banca
                WHERE data_hora = %s AND etapa = %s AND professor_avaliador = %s AND aluno_avaliado = %s
                """,
                (data_hora, etapa, professor, aluno),
            )


def load_drafts(path: Path) -> dict:
    if database_enabled():
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT professor_avaliador, aluno_avaliado, etapa, updated_at, notas, observacoes
                    FROM rascunhos_banca
                """)
                rows = cur.fetchall()
        return {
            get_draft_key(row['professor_avaliador'], row['aluno_avaliado'], row['etapa']): {
                'updated_at': row['updated_at'],
                'notas': row['notas'] or {},
                'observacoes': row['observacoes'] or {},
            }
            for row in rows
        }

    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def save_drafts(path: Path, drafts: dict) -> None:
    if database_enabled():
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM rascunhos_banca')
                for key, draft in drafts.items():
                    professor, aluno, etapa = key.split('|||', 2)
                    cur.execute(
                        """
                        INSERT INTO rascunhos_banca (
                            professor_avaliador, aluno_avaliado, etapa, updated_at, notas, observacoes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (professor_avaliador, aluno_avaliado, etapa)
                        DO UPDATE SET
                            updated_at = EXCLUDED.updated_at,
                            notas = EXCLUDED.notas,
                            observacoes = EXCLUDED.observacoes
                        """,
                        (
                            professor, aluno, etapa,
                            draft.get('updated_at', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                            Json(draft.get('notas', {})),
                            Json(draft.get('observacoes', {})),
                        ),
                    )
        return

    path.write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding='utf-8')


def get_draft_key(professor: str, aluno: str, etapa: str) -> str:
    return f'{professor}|||{aluno}|||{etapa}'


def save_grade_draft(path: Path, professor: str, aluno: str, etapa: str, notas: dict, observacoes: dict) -> None:
    if database_enabled():
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO rascunhos_banca (
                        professor_avaliador, aluno_avaliado, etapa, updated_at, notas, observacoes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (professor_avaliador, aluno_avaliado, etapa)
                    DO UPDATE SET
                        updated_at = EXCLUDED.updated_at,
                        notas = EXCLUDED.notas,
                        observacoes = EXCLUDED.observacoes
                    """,
                    (
                        professor, aluno, etapa,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        Json(notas),
                        Json(observacoes),
                    ),
                )
        return

    drafts = load_drafts(path)
    drafts[get_draft_key(professor, aluno, etapa)] = {
        'updated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'notas': notas,
        'observacoes': observacoes,
    }
    save_drafts(path, drafts)


def delete_grade_draft(path: Path, professor: str, aluno: str, etapa: str) -> None:
    if database_enabled():
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM rascunhos_banca
                    WHERE professor_avaliador = %s AND aluno_avaliado = %s AND etapa = %s
                    """,
                    (professor, aluno, etapa),
                )
        return

    drafts = load_drafts(path)
    drafts.pop(get_draft_key(professor, aluno, etapa), None)
    save_drafts(path, drafts)


def get_submission_key(professor: str, aluno: str, etapa: str) -> tuple[str, str, str]:
    return (str(professor).strip(), str(aluno).strip(), str(etapa).strip())


def calculate_average(values) -> float | None:
    numeric_values = pd.to_numeric(list(values), errors='coerce')
    numeric_values = pd.Series(numeric_values).dropna()
    if numeric_values.empty:
        return None
    return round(float(numeric_values.mean()), 2)


def parse_date_value(value):
    if value is None:
        return None
    if pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, 'date') and not isinstance(value, str):
        try:
            return value.date()
        except Exception:
            pass

    if isinstance(value, (int, float)):
        try:
            parsed = pd.to_datetime(value, unit='d', origin='1899-12-30')
            return None if pd.isna(parsed) else parsed.date()
        except Exception:
            pass

    value_str = str(value).strip()
    if not value_str:
        return None

    try:
        return datetime.strptime(value_str, '%d/%m/%Y').date()
    except Exception:
        pass

    try:
        return datetime.strptime(value_str, '%Y-%m-%d').date()
    except Exception:
        pass

    try:
        parsed = pd.to_datetime(value_str, dayfirst=True, errors='coerce')
        return None if pd.isna(parsed) else parsed.date()
    except Exception:
        return None


def generate_student_report_pdf(aluno: str, df_notas: pd.DataFrame, df_atas: pd.DataFrame, df_alunos: pd.DataFrame) -> bytes:
    dados_aluno = df_alunos[df_alunos['Nome'] == aluno]
    if not dados_aluno.empty:
        row = dados_aluno.iloc[0]
        aluno_info = {
            'Nome': row.get('Nome', ''),
            'Tema': row.get('Tema', ''),
            'Orientador': row.get('Orientador', ''),
            'Etapa': row.get('Etapa', ''),
        }
    else:
        aluno_info = {'Nome': aluno, 'Tema': '', 'Orientador': '', 'Etapa': ''}

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(left=15, top=15, right=15)
    pdf.set_auto_page_break(auto=True, margin=15)
    df_aluno_notas = df_notas[df_notas['Aluno_Avaliado'] == aluno].copy()
    df_aluno_atas = df_atas[df_atas['Aluno_Avaliado'] == aluno].copy() if not df_atas.empty else pd.DataFrame()

    def pdf_safe_text(text) -> str:
        if text is None:
            return ''
        if pd.isna(text):
            return ''
        if not isinstance(text, str):
            text = str(text)
        text = text.replace('\r', '').replace('\t', ' ')
        text = re.sub(r'\S{70,}', lambda match: ' '.join(
            match.group(0)[i:i + 70] for i in range(0, len(match.group(0)), 70)
        ), text)
        return text.encode('latin-1', 'replace').decode('latin-1')

    def format_observacao(value) -> str:
        if value is None or pd.isna(value) or not str(value).strip():
            return 'Não há observações'
        return str(value).strip()

    def criterio_sort_key(value) -> tuple[int, str]:
        text = '' if value is None or pd.isna(value) else str(value).strip()
        match = re.match(r'^(\d+)', text)
        return (int(match.group(1)) if match else 9999, text.lower())

    def usable_width() -> float:
        return pdf.w - pdf.l_margin - pdf.r_margin

    def ensure_space(height: float = 12) -> None:
        if pdf.get_y() + height > pdf.page_break_trigger:
            pdf.add_page()

    def add_page(title: str) -> None:
        pdf.add_page()
        pdf.set_font('Helvetica', 'B', 16)
        pdf.cell(usable_width(), 10, pdf_safe_text(title), 0, 1, 'C')
        pdf.ln(4)

    def add_paragraph(text, h: float = 5.5, font_size: int = 10) -> None:
        text = pdf_safe_text(text)
        pdf.set_font('Helvetica', '', font_size)
        if not text.strip():
            pdf.ln(h)
            return
        for paragraph in text.split('\n'):
            ensure_space(h)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(usable_width(), h, paragraph)

    def add_section_title(title: str) -> None:
        ensure_space(14)
        pdf.ln(2)
        pdf.set_font('Helvetica', 'B', 12)
        pdf.set_fill_color(235, 235, 235)
        pdf.set_x(pdf.l_margin)
        pdf.cell(usable_width(), 8, pdf_safe_text(title), border=0, ln=1, fill=True)
        pdf.ln(1)

    def add_field(label: str, value) -> None:
        pdf.set_font('Helvetica', 'B', 10)
        add_paragraph(f"{label}: {pdf_safe_text(value)}", h=5.5)
        pdf.set_font('Helvetica', '', 10)

    def etapa_media(etapa: str):
        df_etapa = df_aluno_notas[df_aluno_notas['Etapa'] == etapa]
        if df_etapa.empty:
            return None
        media_por_professor = df_etapa.groupby('Professor_Avaliador')['Nota'].mean()
        if media_por_professor.empty:
            return None
        return round(float(media_por_professor.mean()), 2)

    medias = {etapa: etapa_media(etapa) for etapa in ETAPAS}
    pre_banca = medias.get('Pré-Banca') or 0
    banca_final = medias.get('Banca Final') or 0
    nota_final = round((pre_banca * 0.3) + (banca_final * 0.7), 2)

    def add_summary_table() -> None:
        pdf.set_font('Helvetica', 'B', 10)
        col_widths = [70, 35, 45]
        headers = ['Etapa', 'Média', 'Peso no TFG']
        for width, header in zip(col_widths, headers):
            pdf.cell(width, 8, pdf_safe_text(header), border=1, align='C')
        pdf.ln()

        pdf.set_font('Helvetica', '', 10)
        rows = [
            ('Pré-Banca', medias.get('Pré-Banca'), '30%'),
            ('Banca Final', medias.get('Banca Final'), '70%'),
            ('Plano de Ocupação', medias.get('Plano de Ocupação'), 'Separado'),
            ('Nota Final TFG', nota_final, 'Resultado'),
        ]
        for etapa, media, peso in rows:
            media_text = '-' if media is None else f'{media:.2f}'
            pdf.cell(col_widths[0], 8, pdf_safe_text(etapa), border=1)
            pdf.cell(col_widths[1], 8, media_text, border=1, align='C')
            pdf.cell(col_widths[2], 8, pdf_safe_text(peso), border=1, align='C')
            pdf.ln()

    def add_observation_list(title: str, rows: pd.DataFrame, empty_text: str) -> None:
        add_section_title(title)
        if rows.empty:
            add_paragraph(empty_text)
            return
        for _, obs_row in rows.iterrows():
            criterio = obs_row.get('Criterio', '')
            etapa = obs_row.get('Etapa', '')
            nota = obs_row.get('Nota', '')
            observacao = obs_row.get('Observacao', '')
            add_paragraph(f"- {etapa} | {criterio} | Nota: {nota}")
            add_paragraph(f"  Observação: {format_observacao(observacao)}", font_size=9)
            pdf.ln(1)

    def render_criterios_page(etapa: str) -> None:
        add_page(etapa.upper())
        df_etapa = df_aluno_notas[df_aluno_notas['Etapa'] == etapa]

        add_section_title('Resumo da Etapa')
        media = medias.get(etapa)
        add_field('Média da etapa', '-' if media is None else f'{media:.2f}')
        add_field('Quantidade de registros', len(df_etapa))

        add_section_title('Critérios')
        if df_etapa.empty:
            add_paragraph('Nenhum critério registrado para esta etapa.')
            return

        criterios_ordenados = sorted(df_etapa['Criterio'].drop_duplicates().tolist(), key=criterio_sort_key)
        for criterio in criterios_ordenados:
            df_criterio = df_etapa[df_etapa['Criterio'] == criterio]
            ensure_space(24)
            media_criterio = pd.to_numeric(df_criterio['Nota'], errors='coerce').mean()
            media_text = '-' if pd.isna(media_criterio) else f'{media_criterio:.2f}'
            pdf.set_font('Helvetica', 'B', 11)
            pdf.cell(usable_width(), 7, pdf_safe_text(f'{criterio} | Média: {media_text}'), 0, 1)

            pdf.set_font('Helvetica', '', 9)
            for _, nota_row in df_criterio.iterrows():
                avaliador = nota_row.get('Professor_Avaliador', '')
                nota = nota_row.get('Nota', '')
                observacao = nota_row.get('Observacao', '')
                add_paragraph(f"Avaliador: {avaliador} | Nota: {nota}", font_size=9)
                add_paragraph(f"Observação: {format_observacao(observacao)}", font_size=9)
                pdf.ln(1)

    def render_ata_page() -> None:
        add_page('ATA')
        if df_aluno_atas.empty:
            add_paragraph('Nenhuma ata registrada para este aluno.')
            return

        for _, ata_row in df_aluno_atas.sort_values('Data_Hora', ascending=False).iterrows():
            ensure_space(18)
            pdf.set_font('Helvetica', 'B', 11)
            add_paragraph(f"Etapa: {ata_row.get('Etapa', '')} | Professor: {ata_row.get('Professor_Avaliador', '')} | Data: {ata_row.get('Data_Hora', '')}")
            add_paragraph(ata_row.get('Ata', ''), font_size=10)
            pdf.ln(3)

    add_page('RELATÓRIO')
    add_section_title('Dados do Aluno')
    add_field('Nome', aluno_info['Nome'])
    add_field('Tema', aluno_info['Tema'])
    add_field('Orientador', aluno_info['Orientador'])
    add_field('Etapa', aluno_info['Etapa'])
    pdf.ln(4)

    add_section_title('Resumo')
    add_paragraph('Relatório consolidado das avaliações registradas pela banca para o aluno selecionado.')

    add_section_title('Médias')
    if df_aluno_notas.empty:
        add_paragraph('Nenhuma nota registrada para este aluno.')
    else:
        add_summary_table()

    if df_aluno_notas.empty:
        pontos_fortes = pd.DataFrame()
        pontos_melhorar = pd.DataFrame()
    else:
        df_rank = df_aluno_notas.copy()
        df_rank['Nota'] = pd.to_numeric(df_rank['Nota'], errors='coerce')
        df_rank = df_rank.dropna(subset=['Nota'])
        pontos_fortes = df_rank.sort_values('Nota', ascending=False).head(5)
        pontos_melhorar = df_rank.sort_values('Nota', ascending=True).head(5)

    add_observation_list('Pontos Fortes', pontos_fortes, 'Nenhum ponto forte identificado pelas notas registradas.')
    add_observation_list('Pontos a Melhorar', pontos_melhorar, 'Nenhum ponto a melhorar identificado pelas notas registradas.')

    for etapa in ETAPAS:
        render_criterios_page(etapa)

    render_ata_page()

    pdf_output = pdf.output(dest='S')
    if isinstance(pdf_output, str):
        return pdf_output.encode('latin-1', 'replace')
    return bytes(pdf_output)

# 1. Carregamento Seguro das Abas do Arquivo Excel (.xls)
ARQUIVO_CONFIG = get_data_file('config_tfg.xls')

GS_CONFIG = load_google_sheet_config()
GOOGLE_SHEET_URL = GS_CONFIG.get('google_sheet_url', '').strip()
BLOQUEIO_DATA_BANCAS = bool(GS_CONFIG.get('bloqueio_data_bancas', True))
BLOQUEIO_REENVIO_BANCAS = bool(GS_CONFIG.get('bloqueio_reenvio_bancas', True))

try:
    if GOOGLE_SHEET_URL:
        try:
            df_alunos = read_google_sheet_sheet(GOOGLE_SHEET_URL, 'Alunos')
            df_criterios = read_google_sheet_sheet(GOOGLE_SHEET_URL, 'Criterios')
        except Exception as exc:
            st.warning(f"Não foi possível carregar o Google Sheets: {exc}. Tentando carregar o arquivo local... ")
            if not ARQUIVO_CONFIG.exists():
                raise FileNotFoundError
            df_alunos = pd.read_excel(ARQUIVO_CONFIG, sheet_name='Alunos')
            df_criterios = pd.read_excel(ARQUIVO_CONFIG, sheet_name='Criterios')
    else:
        if not ARQUIVO_CONFIG.exists():
            raise FileNotFoundError
        df_alunos = pd.read_excel(ARQUIVO_CONFIG, sheet_name='Alunos')
        df_criterios = pd.read_excel(ARQUIVO_CONFIG, sheet_name='Criterios')
    
    # Limpando espaços em branco nos nomes das colunas
    df_alunos.columns = df_alunos.columns.str.strip()
    df_criterios.columns = df_criterios.columns.str.strip()
    
    if df_alunos.empty or df_criterios.empty:
        raise ValueError('As abas Alunos e Criterios precisam ter ao menos uma linha.')

    missing_alunos = missing_columns(df_alunos, ALUNOS_REQUIRED_COLUMNS)
    missing_criterios = missing_columns(df_criterios, CRITERIOS_REQUIRED_COLUMNS)
    missing_data = not ({'Data Banca', 'DataBanca'} & set(df_alunos.columns))

    if missing_alunos or missing_criterios or missing_data:
        mensagens = []
        if missing_alunos:
            mensagens.append(f"Aba Alunos sem colunas obrigatórias: {', '.join(missing_alunos)}.")
        if missing_criterios:
            mensagens.append(f"Aba Criterios sem colunas obrigatórias: {', '.join(missing_criterios)}.")
        if missing_data:
            mensagens.append("Aba Alunos precisa ter a coluna 'Data Banca' ou 'DataBanca'.")
        raise ValueError(' '.join(mensagens))

    for column in ['Nome', 'Tema', 'Orientador', 'Etapa', 'Avaliador 2', 'Avaliador 3']:
        if column not in df_alunos.columns:
            df_alunos[column] = ''
        df_alunos[column] = df_alunos[column].fillna('').astype(str).str.strip()

    for column in ['Etapa', 'Criterio', 'Descricao']:
        df_criterios[column] = df_criterios[column].fillna('').astype(str).str.strip()
except Exception as exc:
    st.error("Erro: Não foi possível carregar os dados de configuração. Verifique o Google Sheets ou o arquivo 'config_tfg.xls'.")
    if 'mensagens' in locals():
        for mensagem in mensagens:
            st.error(mensagem)
    else:
        st.caption(f"Detalhe técnico: {exc}")
    st.stop()

# 2. Inicialização do Banco de Notas
ARQUIVO_NOTAS = get_data_file('notas_banca.csv')
ARQUIVO_ATAS = get_data_file('atas_banca.csv')
ARQUIVO_RASCUNHOS = get_data_file('rascunhos_banca.json')
DATABASE_URL = get_database_url()
DATABASE_ENABLED = bool(DATABASE_URL)

if DATABASE_ENABLED and psycopg is None:
    st.error("DATABASE_URL/NEON_DATABASE_URL foi configurada, mas o pacote psycopg não está instalado. Rode `uv sync` ou instale `psycopg[binary]`.")
    st.stop()

if DATABASE_ENABLED:
    try:
        init_database()
        df_notas = load_database_table('notas_banca', NOTAS_COLUMNS)
        df_atas = load_database_table('atas_banca', ATAS_COLUMNS)
    except Exception as exc:
        st.error("Erro ao conectar ou inicializar o banco Neon/Postgres.")
        st.caption(f"Detalhe técnico: {exc}")
        st.stop()
else:
    df_notas = load_csv_database(ARQUIVO_NOTAS, NOTAS_COLUMNS, numeric_columns=['Nota'])
    df_atas = load_csv_database(ARQUIVO_ATAS, ATAS_COLUMNS)

if df_notas.empty:
    NOTAS_ENVIADAS_KEYS = set()
    NOTA_MEDIA_POR_ENVIO = {}
else:
    notas_por_envio = (
        df_notas.groupby(['Professor_Avaliador', 'Aluno_Avaliado', 'Etapa'])['Nota']
        .mean()
        .round(2)
    )
    NOTA_MEDIA_POR_ENVIO = {
        get_submission_key(professor, aluno, etapa): media
        for (professor, aluno, etapa), media in notas_por_envio.items()
    }
    NOTAS_ENVIADAS_KEYS = set(NOTA_MEDIA_POR_ENVIO.keys())

if df_atas.empty:
    ATAS_ENVIADAS_KEYS = set()
else:
    ATAS_ENVIADAS_KEYS = {
        get_submission_key(row['Professor_Avaliador'], row['Aluno_Avaliado'], row['Etapa'])
        for _, row in df_atas.iterrows()
    }

st.title("🏛️ Sistema de Avaliação de TFG - Painel da Banca")
st.write("---")

menu = st.sidebar.radio(
    "Selecione o Painel:",
    ["📅 Calendário da Semana", "📝 Lançar Notas (Banca)", "🔒 Painel de Resultados (Dashboard)"]
)

# ==================== ABA 0: CALENDÁRIO DA SEMANA ====================
if menu == "📅 Calendário da Semana":
    st.header("Calendário de Bancas da Semana")

    coluna_data_calendario = 'Data Banca' if 'Data Banca' in df_alunos.columns else 'DataBanca'
    data_referencia = st.date_input("Semana de referência:", value=datetime.now().date(), format="DD/MM/YYYY")

    inicio_semana = data_referencia - timedelta(days=data_referencia.weekday())
    fim_semana = inicio_semana + timedelta(days=6)

    with st.expander(
        f"Exibir calendário de {inicio_semana.strftime('%d/%m/%Y')} a {fim_semana.strftime('%d/%m/%Y')}",
        expanded=False
    ):
        st.info(f"Mostrando bancas de {inicio_semana.strftime('%d/%m/%Y')} a {fim_semana.strftime('%d/%m/%Y')}.")

        calendario = df_alunos.copy()
        calendario['Data_Banca_Parsed'] = calendario[coluna_data_calendario].apply(parse_date_value)
        calendario = calendario[calendario['Data_Banca_Parsed'].notna()].copy()
        calendario = calendario[
            (calendario['Data_Banca_Parsed'] >= inicio_semana) &
            (calendario['Data_Banca_Parsed'] <= fim_semana)
        ].copy()

        horario_coluna = next((col for col in ['Horário', 'Horario', 'Hora Banca', 'Hora'] if col in calendario.columns), None)
        dias_semana = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

        if calendario.empty:
            st.warning("Nenhuma banca encontrada para esta semana.")
        else:
            calendario['Data'] = calendario['Data_Banca_Parsed'].apply(lambda data: data.strftime('%d/%m/%Y'))
            calendario['Dia'] = calendario['Data_Banca_Parsed'].apply(lambda data: dias_semana[data.weekday()])
            calendario['Banca'] = calendario.apply(
                lambda row: " | ".join([
                    f"Orientador: {row.get('Orientador', '')}",
                    f"Avaliador 2: {row.get('Avaliador 2', '') or '-'}",
                    f"Avaliador 3: {row.get('Avaliador 3', '') or '-'}",
                ]),
                axis=1
            )

            colunas_resumo = ['Data', 'Dia']
            if horario_coluna:
                colunas_resumo.append(horario_coluna)
            colunas_resumo.extend(['Etapa', 'Nome', 'Tema', 'Banca'])

            st.subheader("Resumo da Semana")
            df_resumo_semana = calendario.sort_values(['Data_Banca_Parsed', horario_coluna or 'Nome'])[colunas_resumo]
            df_resumo_semana = df_resumo_semana.style.set_table_styles([
                {'selector': 'thead th', 'props': [('background-color', '#e5e7eb'), ('color', '#111827'), ('font-weight', '700')]},
                {'selector': 'tbody tr:nth-child(even)', 'props': [('background-color', '#f8fafc')]},
                {'selector': 'tbody tr:nth-child(odd)', 'props': [('background-color', '#ffffff')]},
                {'selector': 'tbody td', 'props': [('border-bottom', '1px solid #e5e7eb')]},
            ])
            st.dataframe(
                df_resumo_semana,
                use_container_width=True,
                hide_index=True
            )

            st.subheader("Bancas por Dia")
            abas_dias = st.tabs(dias_semana)
            for offset, aba in enumerate(abas_dias):
                data_dia = inicio_semana + timedelta(days=offset)
                df_dia = calendario[calendario['Data_Banca_Parsed'] == data_dia].copy()
                with aba:
                    st.markdown(f"### {dias_semana[offset]} - {data_dia.strftime('%d/%m/%Y')}")
                    if df_dia.empty:
                        st.info("Sem bancas agendadas.")
                    else:
                        sort_cols = [horario_coluna] if horario_coluna else []
                        sort_cols.append('Nome')
                        for _, banca in df_dia.sort_values(sort_cols).iterrows():
                            horario = f"**Horário:** {banca.get(horario_coluna, '')}  \n" if horario_coluna else ""
                            st.markdown(
                                f"""
                                **Orientando:** {banca.get('Nome', '')}  
                                **Etapa:** {banca.get('Etapa', '')}  
                                {horario}**Tema:** {banca.get('Tema', '')}  
                                **Orientador:** {banca.get('Orientador', '')}  
                                **Avaliador 2:** {banca.get('Avaliador 2', '') or '-'}  
                                **Avaliador 3:** {banca.get('Avaliador 3', '') or '-'}
                                """
                            )
                            st.divider()

# ==================== ABA 1: ÁREA DE LANÇAMENTO DE NOTAS ====================
elif menu == "📝 Lançar Notas (Banca)":
    st.header("Lançamento de Avaliações por Etapa")
    
    etapa_selecionada = st.selectbox("Selecione a Etapa de Avaliação:", ETAPAS)
    
    # Usa apenas alunos com etapa válida para esta seleção
    if 'Etapa' in df_alunos.columns:
        df_alunos_etapa = df_alunos[df_alunos['Etapa'].astype(str).str.strip() == etapa_selecionada].copy()
    else:
        df_alunos_etapa = df_alunos.copy()

    # Cria a lista única de professores apenas para a etapa selecionada
    todos_profs = set()
    todos_profs.update(df_alunos_etapa['Orientador'].dropna().tolist())
    todos_profs.update(df_alunos_etapa['Avaliador 2'].dropna().tolist())
    todos_profs.update(df_alunos_etapa['Avaliador 3'].dropna().tolist())
    todos_profs.discard('')
    
    lista_professores = ["-- Selecione Seu Nome --"] + sorted(list(todos_profs))
    prof_nome = st.selectbox("Identifique-se (Professor Avaliador):", lista_professores)
    
    if prof_nome and prof_nome != "-- Selecione Seu Nome --":
        
        # Filtrar apenas os alunos vinculados a este professor nessa etapa
        df_alunos_filtrados = df_alunos_etapa[
            (df_alunos_etapa['Orientador'] == prof_nome) | 
            (df_alunos_etapa['Avaliador 2'] == prof_nome) | 
            (df_alunos_etapa['Avaliador 3'] == prof_nome)
        ]
        
        if df_alunos_filtrados.empty:
            st.warning("Você não está vinculado a nenhum aluno nesta planilha.")
        else:
            df_alunos_filtrados_exibir = df_alunos_filtrados[['Nome']].copy()
            df_alunos_filtrados_exibir.insert(0, 'Etapa', etapa_selecionada)
            df_alunos_filtrados_exibir.index = range(1, len(df_alunos_filtrados_exibir) + 1)
            st.write("### Alunos disponíveis")
            st.dataframe(df_alunos_filtrados_exibir, use_container_width=True)

            lista_alunos = ["-- Selecione o Aluno --"] + df_alunos_filtrados['Nome'].apply(lambda n: f"{etapa_selecionada} - {n}").tolist()
            aluno_selecionado_label = st.selectbox("Selecione o aluno para avaliar:", lista_alunos)
            
            if aluno_selecionado_label != "-- Selecione o Aluno --":
                aluno_selecionado = aluno_selecionado_label.split(" - ", 1)[1]
                dados_aluno = df_alunos[
                    (df_alunos['Nome'] == aluno_selecionado) &
                    (df_alunos['Etapa'].astype(str).str.strip() == etapa_selecionada)
                ].iloc[0]
                tema_projeto = dados_aluno['Tema']
                orientador_projeto = dados_aluno['Orientador']
                
                # Sempre usa 'Data Banca' para qualquer etapa
                coluna_data = 'Data Banca' if 'Data Banca' in df_alunos.columns else 'DataBanca'

                data_agendada_val = dados_aluno[coluna_data]
                data_agendada = parse_date_value(data_agendada_val)
                hoje = datetime.now().date()
                
                data_agendada_str = data_agendada.strftime('%d/%m/%Y') if data_agendada else str(data_agendada_val).strip()
                hoje_str = hoje.strftime('%d/%m/%Y')
                
                st.info(f"📋 **Projeto/Tema:** {tema_projeto}  \n👨‍🏫 **Orientador:** {orientador_projeto}  \n📅 **Data Agendada para {etapa_selecionada}:** {data_agendada_str}")
                
                # REGRA EXTRA: Validação da Data da Banca
                if not BLOQUEIO_DATA_BANCAS:
                    st.warning("Bloqueio por data das bancas desativado no Dashboard. A avaliação pode ser feita fora da data agendada.")

                acesso_bloqueado = False
                if BLOQUEIO_DATA_BANCAS and data_agendada is None:
                    st.error(f"🛑 **Erro de leitura:** Não foi possível interpretar a data agendada para a etapa {etapa_selecionada}. Verifique o valor na coluna {coluna_data}.")
                    acesso_bloqueado = True
                elif BLOQUEIO_DATA_BANCAS and data_agendada != hoje:
                    st.error(f"🛑 **Acesso Bloqueado:** Hoje é {hoje_str}, mas a avaliação da **{etapa_selecionada}** para este aluno está agendada exclusivamente para o dia **{data_agendada_str}**.")
                    acesso_bloqueado = True
                
                # REGRA: Professor Orientador não distribui nota quantitativa
                if acesso_bloqueado:
                    st.stop()
                elif prof_nome == orientador_projeto:
                    st.warning("Você está mapeado como **Orientador** deste projeto. Use este formulário para registrar a ata da banca.")
                    st.subheader("Notas parciais dos avaliadores")

                    avaliadores_banca = [
                        dados_aluno.get('Avaliador 2', ''),
                        dados_aluno.get('Avaliador 3', ''),
                    ]
                    avaliadores_banca = [avaliador for avaliador in avaliadores_banca if str(avaliador).strip()]
                    drafts = load_drafts(ARQUIVO_RASCUNHOS)
                    notas_parciais = []

                    for avaliador in avaliadores_banca:
                        envio_key = get_submission_key(avaliador, aluno_selecionado, etapa_selecionada)

                        if envio_key in NOTAS_ENVIADAS_KEYS:
                            media_avaliador = NOTA_MEDIA_POR_ENVIO.get(envio_key)
                            status = 'Enviada'
                        else:
                            draft = drafts.get(get_draft_key(avaliador, aluno_selecionado, etapa_selecionada), {})
                            media_avaliador = calculate_average(draft.get('notas', {}).values()) if draft else None
                            status = 'Rascunho' if draft else 'Pendente'

                        notas_parciais.append({
                            'Avaliador': avaliador,
                            'Status': status,
                            'Nota parcial': '-' if media_avaliador is None else f'{media_avaliador:.2f}',
                        })

                    if notas_parciais:
                        st.dataframe(pd.DataFrame(notas_parciais), use_container_width=True, hide_index=True)
                    else:
                        st.info("Nenhum avaliador 2 ou avaliador 3 foi encontrado para este aluno.")

                    st.subheader("📝 Ata da Banca")
                    ata_key = f"ata_{aluno_selecionado}_{etapa_selecionada}"
                    ata_existente = df_atas[
                        (df_atas['Professor_Avaliador'] == prof_nome) &
                        (df_atas['Aluno_Avaliado'] == aluno_selecionado) &
                        (df_atas['Etapa'] == etapa_selecionada)
                    ].copy()
                    ata_registrada = not ata_existente.empty

                    if ata_registrada:
                        ata_existente = ata_existente.sort_values('Data_Hora', ascending=False).iloc[0]
                        if ata_key not in st.session_state:
                            st.session_state[ata_key] = str(ata_existente.get('Ata', ''))
                        if BLOQUEIO_REENVIO_BANCAS:
                            st.success("A ata desta banca já foi enviada e está bloqueada para novo envio.")
                        else:
                            st.info("Já existe uma ata registrada para esta banca. Você pode revisar e atualizar o mesmo texto sem criar duplicidade.")
                    elif ata_key not in st.session_state:
                        st.session_state[ata_key] = ''

                    ata_text = st.text_area(
                        "Escreva aqui a ata da banca:",
                        placeholder="Descreva as decisões, comentários e encaminhamentos da banca...",
                        height=300,
                        max_chars=10000,
                        key=ata_key,
                        disabled=ata_registrada and BLOQUEIO_REENVIO_BANCAS
                    ).strip()
                    ata_button_label = "Atualizar Ata da Banca" if ata_registrada else "Salvar Ata da Banca"
                    pode_salvar_ata = not (ata_registrada and BLOQUEIO_REENVIO_BANCAS)
                    if pode_salvar_ata and st.button(ata_button_label, key=f"salvar_ata_{aluno_selecionado}_{etapa_selecionada}"):
                        if not ata_text:
                            st.error("A ata não pode ficar em branco. Escreva o documento antes de salvar.")
                        else:
                            save_ata_submission(prof_nome, aluno_selecionado, etapa_selecionada, ata_text)
                            st.success("Ata da banca salva com sucesso.")
                            st.balloons()
                            st.rerun()
                
                else:
                    # REGRA: Evitar duplicidade de nota do mesmo professor para o mesmo aluno na mesma etapa
                    ja_avaliou = get_submission_key(prof_nome, aluno_selecionado, etapa_selecionada) in NOTAS_ENVIADAS_KEYS
                    
                    if ja_avaliou and BLOQUEIO_REENVIO_BANCAS:
                        st.error(f"Você já submeteu as suas notas para a **{etapa_selecionada}** do aluno {aluno_selecionado}!")
                    else:
                        if ja_avaliou and not BLOQUEIO_REENVIO_BANCAS:
                            st.warning("Este avaliador já enviou notas anteriormente, mas o reenvio está liberado no Dashboard. O novo envio substituirá a versão anterior.")
                        st.subheader(f"Formulário de Notas - {etapa_selecionada}")
                        
                        df_crit_filtrados = df_criterios[df_criterios['Etapa'] == etapa_selecionada]
                        
                        if df_crit_filtrados.empty:
                            st.warning(f"Nenhum critério foi localizado para a etapa: {etapa_selecionada}")
                        else:
                            escala_max = ESCALAS_ETAPAS.get(etapa_selecionada, 10.0)
                            st.write(f"Atribua uma nota de 0.0 a {escala_max} (Sua nota final nesta etapa será a média simples destes {len(df_crit_filtrados)} itens):")
                            
                            notas_banca = {}
                            obs_banca = {}
                            drafts = load_drafts(ARQUIVO_RASCUNHOS)
                            draft = drafts.get(get_draft_key(prof_nome, aluno_selecionado, etapa_selecionada), {})
                            draft_notas = draft.get('notas', {})
                            draft_observacoes = draft.get('observacoes', {})

                            if draft:
                                st.info(f"Rascunho recuperado automaticamente. Última atualização: {draft.get('updated_at', 'sem data registrada')}.")
                            
                            for idx, row in df_crit_filtrados.iterrows():
                                crit = row['Criterio']
                                desc = row['Descricao']
                                nota_key = f"n_{aluno_selecionado}_{etapa_selecionada}_{crit}"
                                obs_key = f"o_{aluno_selecionado}_{etapa_selecionada}_{crit}"
                                if nota_key not in st.session_state:
                                    draft_nota = float(draft_notas.get(crit, min(6.0, float(escala_max))))
                                    st.session_state[nota_key] = max(0.0, min(draft_nota, float(escala_max)))
                                if obs_key not in st.session_state:
                                    st.session_state[obs_key] = str(draft_observacoes.get(crit, ''))
                                
                                with st.container():
                                    st.markdown(f"##### **{crit}**")
                                    st.caption(f"_{desc}_")
                                    
                                    col_nota, col_obs = st.columns([1, 2])
                                    with col_nota:
                                        notas_banca[crit] = st.slider(
                                            "Nota:", 0.0, float(escala_max), min(6.0, float(escala_max)), step=1.0,
                                            key=nota_key, help=desc
                                        )
                                    with col_obs:
                                        obs_banca[crit] = st.text_input(
                                            "Observação / Justificativa:", 
                                            placeholder="Adicione um comentário para este item...", 
                                            key=obs_key
                                        ).strip()
                                    st.markdown("---")

                            save_grade_draft(ARQUIVO_RASCUNHOS, prof_nome, aluno_selecionado, etapa_selecionada, notas_banca, obs_banca)
                            st.caption("Rascunho salvo automaticamente neste dispositivo.")
                            nota_parcial_atual = calculate_average(notas_banca.values())
                            if nota_parcial_atual is not None:
                                st.metric("Nota final desta avaliação (prévia)", f"{nota_parcial_atual:.2f}")
                                st.info("Esta é a média simples dos critérios preenchidos até agora. Ela só será oficial depois de clicar em Finalizar e Gravar Notas da Banca.")
                                
                            if st.button("Finalizar e Gravar Notas da Banca", key=f"salvar_notas_{aluno_selecionado}_{etapa_selecionada}"):
                                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                novas_linhas = []
                                
                                for crit in df_crit_filtrados['Criterio'].tolist():
                                    novas_linhas.append({
                                        'Data_Hora': timestamp,
                                        'Etapa': etapa_selecionada,
                                        'Professor_Avaliador': prof_nome,
                                        'Aluno_Avaliado': aluno_selecionado,
                                        'Criterio': crit,
                                        'Nota': notas_banca[crit],
                                        'Observacao': obs_banca[crit]
                                    })
                                    
                                save_notes_submission(prof_nome, aluno_selecionado, etapa_selecionada, novas_linhas)
                                
                                # Limpa o rascunho desta avaliação do session_state, já que foi gravada
                                for crit in df_crit_filtrados['Criterio'].tolist():
                                    st.session_state.pop(f"n_{aluno_selecionado}_{etapa_selecionada}_{crit}", None)
                                    st.session_state.pop(f"o_{aluno_selecionado}_{etapa_selecionada}_{crit}", None)
                                delete_grade_draft(ARQUIVO_RASCUNHOS, prof_nome, aluno_selecionado, etapa_selecionada)
                                
                                st.balloons()
                                st.success(f"Notas da {etapa_selecionada} enviadas com sucesso para o aluno {aluno_selecionado}!")
                                st.rerun()

# ==================== ABA 2: PAINEL DE RESULTADOS (DASHBOARD) ====================
elif menu == "🔒 Painel de Resultados (Dashboard)":
    st.header("Consolidação de Desempenho dos TFGs")
    
    senha_acesso = st.sidebar.text_input("Senha de Acesso ao Painel:", type="password")
    
    if senha_acesso == get_dashboard_password():
        st.sidebar.success("Acesso Autorizado")
        st.sidebar.info(f"Banco atual: {database_label()}")
        st.info(f"Banco de dados em uso no momento: **{database_label()}**")
        
        with st.sidebar.expander("Configuração do Google Sheets", expanded=False):
            st.write("Cole abaixo o link do Google Sheets com as abas 'Alunos' e 'Criterios'.")
            sheet_url_input = st.text_input("Link do Google Sheets:", value=GOOGLE_SHEET_URL)
            if st.button("Salvar link do Google Sheets"):
                if sheet_url_input.strip():
                    GS_CONFIG['google_sheet_url'] = sheet_url_input.strip()
                    save_google_sheet_config(GS_CONFIG)
                    st.success("Link salvo. Recarregue o app para aplicar a configuração.")
                else:
                    st.error("O link não pode ficar em branco.")

        with st.sidebar.expander("🗓️ Bloqueio por data das bancas", expanded=False):
            st.write("Quando ligado, a banca só pode lançar nota ou ata na data agendada.")
            bloqueio_data_input = st.toggle(
                "Bloquear lançamentos fora da data agendada",
                value=BLOQUEIO_DATA_BANCAS,
            )
            if st.button("Salvar bloqueio por data"):
                GS_CONFIG['bloqueio_data_bancas'] = bool(bloqueio_data_input)
                save_google_sheet_config(GS_CONFIG)
                if bloqueio_data_input:
                    st.success("Bloqueio por data ativado. Recarregue o app para aplicar.")
                else:
                    st.warning("Bloqueio por data desativado. Recarregue o app para aplicar.")

        with st.sidebar.expander("🔒 Bloqueio de reenvio", expanded=False):
            st.write("Quando ligado, após enviar a nota ou a ata o usuário fica bloqueado para novo envio.")
            bloqueio_reenvio_input = st.toggle(
                "Bloquear reenvio de notas e atas",
                value=BLOQUEIO_REENVIO_BANCAS,
            )
            if st.button("Salvar bloqueio de reenvio"):
                GS_CONFIG['bloqueio_reenvio_bancas'] = bool(bloqueio_reenvio_input)
                save_google_sheet_config(GS_CONFIG)
                if bloqueio_reenvio_input:
                    st.success("Bloqueio de reenvio ativado. Recarregue o app para aplicar.")
                else:
                    st.warning("Bloqueio de reenvio desativado. Recarregue o app para aplicar.")
        
        # Seção de Reset do Sistema
        with st.sidebar.expander("⚠️ Resetar Avaliações", expanded=False):
            st.warning("Esta ação irá apagar todos os dados de avaliações (notas e atas).")
            confirmar_reset = st.checkbox("☑️ Tenho certeza que quero apagar todos os dados")
            
            if confirmar_reset:
                if st.button("🔴 Resetar Avaliações", type="primary"):
                    try:
                        reset_assessments()
                        st.success("✅ Avaliações resetadas com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao resetar: {e}")

        with st.sidebar.expander("🧹 Apagar registro específico", expanded=False):
            st.warning("Use apenas para corrigir lançamento feito por engano.")
            tipo_exclusao = st.radio("O que deseja apagar?", ["Notas de um avaliador", "Ata"], key="tipo_exclusao_registro")

            if tipo_exclusao == "Notas de um avaliador":
                if df_notas.empty:
                    st.info("Não há notas registradas para apagar.")
                else:
                    envios_notas = (
                        df_notas[['Data_Hora', 'Etapa', 'Professor_Avaliador', 'Aluno_Avaliado']]
                        .drop_duplicates()
                        .sort_values(['Data_Hora', 'Aluno_Avaliado', 'Etapa'], ascending=[False, True, True])
                        .reset_index(drop=True)
                    )
                    opcoes_notas = [
                        f"{row['Data_Hora']} | {row['Etapa']} | {row['Aluno_Avaliado']} | {row['Professor_Avaliador']}"
                        for _, row in envios_notas.iterrows()
                    ]
                    envio_idx = st.selectbox(
                        "Selecione o envio de notas:",
                        range(len(opcoes_notas)),
                        format_func=lambda idx: opcoes_notas[idx],
                        key="excluir_envio_notas",
                    )
                    confirmar_exclusao_notas = st.checkbox("Confirmo que quero apagar este envio de notas", key="confirmar_exclusao_notas")

                    if confirmar_exclusao_notas and st.button("Apagar envio de notas", type="primary", key="btn_excluir_notas"):
                        envio = envios_notas.iloc[envio_idx]
                        delete_notes_submission(
                            envio['Data_Hora'],
                            envio['Etapa'],
                            envio['Professor_Avaliador'],
                            envio['Aluno_Avaliado'],
                        )
                        st.success("Envio de notas apagado com sucesso.")
                        st.rerun()

            else:
                if df_atas.empty:
                    st.info("Não há atas registradas para apagar.")
                else:
                    atas_excluir = (
                        df_atas.reset_index()
                        .sort_values(['Data_Hora', 'Aluno_Avaliado', 'Etapa'], ascending=[False, True, True])
                        .reset_index(drop=True)
                    )
                    opcoes_atas = [
                        f"{row['Data_Hora']} | {row['Etapa']} | {row['Aluno_Avaliado']} | {row['Professor_Avaliador']}"
                        for _, row in atas_excluir.iterrows()
                    ]
                    ata_idx = st.selectbox(
                        "Selecione a ata:",
                        range(len(opcoes_atas)),
                        format_func=lambda idx: opcoes_atas[idx],
                        key="excluir_ata",
                    )
                    confirmar_exclusao_ata = st.checkbox("Confirmo que quero apagar esta ata", key="confirmar_exclusao_ata")

                    if confirmar_exclusao_ata and st.button("Apagar ata", type="primary", key="btn_excluir_ata"):
                        ata = atas_excluir.iloc[ata_idx]
                        delete_ata_submission(
                            ata['Data_Hora'],
                            ata['Etapa'],
                            ata['Professor_Avaliador'],
                            ata['Aluno_Avaliado'],
                        )
                        st.success("Ata apagada com sucesso.")
                        st.rerun()

        st.subheader("✅ Status das Bancas")
        drafts_dashboard = load_drafts(ARQUIVO_RASCUNHOS)
        status_rows = []

        for _, aluno_row in df_alunos.iterrows():
            aluno_status = aluno_row.get('Nome', '')
            etapa_status = aluno_row.get('Etapa', '')
            orientador_status = aluno_row.get('Orientador', '')
            avaliadores_esperados = [
                aluno_row.get('Avaliador 2', ''),
                aluno_row.get('Avaliador 3', ''),
            ]
            avaliadores_esperados = [avaliador for avaliador in avaliadores_esperados if str(avaliador).strip()]

            avaliadores_enviados = []
            avaliadores_rascunho = []
            avaliadores_pendentes = []

            for avaliador in avaliadores_esperados:
                enviou_nota = get_submission_key(avaliador, aluno_status, etapa_status) in NOTAS_ENVIADAS_KEYS
                tem_rascunho = get_draft_key(avaliador, aluno_status, etapa_status) in drafts_dashboard

                if enviou_nota:
                    avaliadores_enviados.append(avaliador)
                elif tem_rascunho:
                    avaliadores_rascunho.append(avaliador)
                else:
                    avaliadores_pendentes.append(avaliador)

            ata_registrada = get_submission_key(orientador_status, aluno_status, etapa_status) in ATAS_ENVIADAS_KEYS

            total_esperado = len(avaliadores_esperados)
            total_enviado = len(avaliadores_enviados)
            tem_algum_registro = total_enviado > 0 or bool(avaliadores_rascunho) or ata_registrada

            pendencias = []
            if avaliadores_pendentes:
                pendencias.append(f"Notas pendentes: {', '.join(avaliadores_pendentes)}")
            if avaliadores_rascunho:
                pendencias.append(f"Notas em rascunho: {', '.join(avaliadores_rascunho)}")
            if not ata_registrada:
                pendencias.append("Ata pendente")

            if total_esperado == total_enviado and ata_registrada:
                status = "Completo"
            elif tem_algum_registro:
                status = "Parcial"
            else:
                status = "Pendente"

            status_rows.append({
                'Status': status,
                'Aluno': aluno_status,
                'Etapa': etapa_status,
                'Notas enviadas': f"{total_enviado}/{total_esperado}",
                'Ata': 'Registrada' if ata_registrada else 'Pendente',
                'Pendências': '; '.join(pendencias) if pendencias else '-',
            })

        df_status_bancas = pd.DataFrame(status_rows)
        if df_status_bancas.empty:
            st.info("Nenhum aluno encontrado na configuração.")
        else:
            status_ordem = {'Pendente': 0, 'Parcial': 1, 'Completo': 2}
            df_status_bancas['Ordem'] = df_status_bancas['Status'].map(status_ordem).fillna(99)
            df_status_bancas = df_status_bancas.sort_values(['Ordem', 'Etapa', 'Aluno']).drop(columns=['Ordem'])

            resumo_status = df_status_bancas['Status'].value_counts()
            col_pendente, col_parcial, col_completo = st.columns(3)
            col_pendente.metric("Pendentes", int(resumo_status.get('Pendente', 0)))
            col_parcial.metric("Parciais", int(resumo_status.get('Parcial', 0)))
            col_completo.metric("Completas", int(resumo_status.get('Completo', 0)))

            def highlight_status(row):
                colors = {
                    'Pendente': 'background-color: #fee2e2; color: #111827',
                    'Parcial': 'background-color: #fef3c7; color: #111827',
                    'Completo': 'background-color: #dcfce7; color: #111827',
                }
                return [colors.get(row['Status'], '')] * len(row)

            st.dataframe(
                df_status_bancas.style.apply(highlight_status, axis=1),
                use_container_width=True,
                hide_index=True
            )

            df_alertas = df_status_bancas[df_status_bancas['Status'] != 'Completo'].copy()
            with st.expander(f"⚠️ Alertas de bancas incompletas ({len(df_alertas)})", expanded=not df_alertas.empty):
                if df_alertas.empty:
                    st.success("Todas as bancas estão completas.")
                else:
                    st.dataframe(df_alertas[['Status', 'Aluno', 'Etapa', 'Pendências']], use_container_width=True, hide_index=True)

        st.write("---")

        if df_notas.empty:
            st.info("Nenhuma avaliação foi computada no banco de dados até o momento.")
        else:
            # Informação sobre as escalas e cálculos
            with st.expander("📋 Metodologia de Cálculo", expanded=False):
                st.markdown("""
                **Escalas de Avaliação por Etapa:**
                - **Pré-Banca**: 9 itens de avaliação, escala 0-10 (incremento de 1 em 1)
                - **Banca Final**: 10 itens de avaliação, escala 0-10 (incremento de 1 em 1)
                - **Plano de Ocupação**: 10 itens de avaliação, escala 0-10 (incremento de 1 em 1) - etapa separada em semestre diferente
                
                **Cálculo da Nota Final TFG:**
                - **(Pré-Banca × 0.3) + (Banca Final × 0.7)**
                - O Plano de Ocupação é registrado separadamente e não entra na ponderação
                """)
            
            media_por_professor = df_notas.groupby(['Aluno_Avaliado', 'Etapa', 'Professor_Avaliador'])['Nota'].mean().reset_index()
            media_por_professor.columns = ['Aluno', 'Etapa', 'Professor', 'Media_Simples_Prof']
            
            media_da_banca = media_por_professor.groupby(['Aluno', 'Etapa'])['Media_Simples_Prof'].mean().reset_index()
            media_da_banca.columns = ['Aluno', 'Etapa', 'Media_Banca_Etapa']
            
            df_consolidado = media_da_banca.pivot(index='Aluno', columns='Etapa', values='Media_Banca_Etapa').reset_index()
            
            if 'Pré-Banca' not in df_consolidado.columns:
                df_consolidado['Pré-Banca'] = None
            if 'Banca Final' not in df_consolidado.columns:
                df_consolidado['Banca Final'] = None
                
            df_consolidado['Pré-Banca'] = pd.to_numeric(df_consolidado['Pré-Banca'], errors='coerce').fillna(0)
            df_consolidado['Banca Final'] = pd.to_numeric(df_consolidado['Banca Final'], errors='coerce').fillna(0)

            pre_calculo = df_consolidado['Pré-Banca']
            final_calculo = df_consolidado['Banca Final']
            
            # Garantir que a coluna "Plano de Ocupação" exista e esteja arredondada (o pivot já a cria, se houver dados)
            if 'Plano de Ocupação' in df_consolidado.columns:
                df_consolidado['Plano de Ocupação'] = pd.to_numeric(df_consolidado['Plano de Ocupação'], errors='coerce').apply(lambda x: round(x, 2) if pd.notna(x) else None)
            
            df_consolidado['Nota Final TFG'] = ((pre_calculo * 0.3) + (final_calculo * 0.7)).round(2)
            df_consolidado['Pré-Banca'] = df_consolidado['Pré-Banca'].apply(lambda x: round(x, 2) if pd.notna(x) else 0)
            df_consolidado['Banca Final'] = df_consolidado['Banca Final'].apply(lambda x: round(x, 2) if pd.notna(x) else 0)
            
            st.subheader("📋 Relatório Consolidado de Notas Finais")
            st.dataframe(df_consolidado.sort_values(by='Nota Final TFG', ascending=False), use_container_width=True)
            
            if px is not None:
                # Determinar quais colunas incluir no gráfico
                colunas_grafico = ['Pré-Banca', 'Banca Final', 'Nota Final TFG']
                if 'Plano de Ocupação' in df_consolidado.columns:
                    colunas_grafico.append('Plano de Ocupação')
                
                df_melt = df_consolidado.melt(id_vars=['Aluno'], value_vars=colunas_grafico, 
                                              var_name='Métrica', value_name='Nota')
                df_melt = df_melt.dropna()
                
                fig = px.bar(df_melt, x='Aluno', y='Nota', color='Métrica', barmode='group',
                             title="Comparativo de Desempenho: Pré-Banca, Banca Final e Plano de Ocupação",
                             color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig, use_container_width=True)
            
            st.write("---")
            st.subheader("📝 Atas da Banca")
            aluno_filtro = st.selectbox("Selecione um aluno para ver as atas e feedbacks:", df_alunos['Nome'].tolist())

            if aluno_filtro:
                if FPDF is not None:
                    pdf_bytes = generate_student_report_pdf(aluno_filtro, df_notas, df_atas, df_alunos)
                    st.download_button(
                        label="Baixar relatório em PDF",
                        data=pdf_bytes,
                        file_name=f"relatorio_banca_{aluno_filtro.replace(' ', '_')}.pdf",
                        mime="application/pdf",
                    )
                else:
                    st.info('Instale o pacote fpdf2 no ambiente para habilitar exportação em PDF.')

                df_filtrado_aluno = df_notas[df_notas['Aluno_Avaliado'] == aluno_filtro].copy()
                df_filtrado_atas = df_atas[df_atas['Aluno_Avaliado'] == aluno_filtro].copy() if not df_atas.empty else pd.DataFrame()

                if df_filtrado_atas.empty:
                    st.info("Este aluno ainda não possui atas registradas.")
                else:
                    for _, ata_row in df_filtrado_atas.sort_values('Data_Hora', ascending=False).iterrows():
                        with st.expander(f"{ata_row['Etapa']} - {ata_row['Professor_Avaliador']} ({ata_row['Data_Hora']})"):
                            st.markdown(ata_row['Ata'])
                            st.write("---")

                st.subheader("💬 Feedbacks de Critérios e Observações da Banca")
                if df_filtrado_aluno.empty:
                    st.info("Este aluno ainda não recebeu avaliações detalhadas.")
                else:
                    for etapa in ETAPAS:
                        df_etapa_sub = df_filtrado_aluno[df_filtrado_aluno['Etapa'] == etapa]
                        if not df_etapa_sub.empty:
                            with st.expander(f"Justificativas na {etapa}"):
                                st.dataframe(df_etapa_sub[['Professor_Avaliador', 'Criterio', 'Nota', 'Observacao']], use_container_width=True)

            st.write("---")
            st.subheader("📊 Estatísticas dos Avaliadores")
            st.caption("Média das notas atribuídas por cada professor avaliador, em todas as etapas e alunos. Útil para identificar avaliadores sistematicamente mais rígidos ou mais generosos.")

            df_stats_avaliadores = df_notas.groupby('Professor_Avaliador')['Nota'].agg(['mean', 'count']).reset_index()
            df_stats_avaliadores.columns = ['Avaliador', 'Média das Notas', 'Qtd. de Avaliações']
            df_stats_avaliadores['Média das Notas'] = df_stats_avaliadores['Média das Notas'].round(2)
            df_stats_avaliadores = df_stats_avaliadores.sort_values(by='Média das Notas', ascending=False)

            st.dataframe(df_stats_avaliadores, use_container_width=True)

            if px is not None and not df_stats_avaliadores.empty:
                fig_avaliadores = px.bar(
                    df_stats_avaliadores, x='Avaliador', y='Média das Notas',
                    title="Média das Notas Atribuídas por Avaliador",
                    color_discrete_sequence=px.colors.qualitative.Pastel,
                    text='Média das Notas'
                )
                fig_avaliadores.update_traces(texttemplate='%{text:.2f}', textposition='outside')
                st.plotly_chart(fig_avaliadores, use_container_width=True)

            with st.expander("📊 Detalhar por Etapa"):
                df_stats_etapa = df_notas.groupby(['Professor_Avaliador', 'Etapa'])['Nota'].agg(['mean', 'count']).reset_index()
                df_stats_etapa.columns = ['Avaliador', 'Etapa', 'Média das Notas', 'Qtd. de Avaliações']
                df_stats_etapa['Média das Notas'] = df_stats_etapa['Média das Notas'].round(2)
                st.dataframe(df_stats_etapa.sort_values(by=['Etapa', 'Média das Notas'], ascending=[True, False]), use_container_width=True)

    elif senha_acesso != "":
        st.error("Chave de acesso incorreta. Verifique os dados.")
