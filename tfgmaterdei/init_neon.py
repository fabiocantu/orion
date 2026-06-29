import tomllib
from pathlib import Path

import psycopg


def main() -> None:
    secrets_path = Path(".streamlit/secrets.toml")
    if not secrets_path.exists():
        raise SystemExit("Arquivo .streamlit/secrets.toml não encontrado.")

    secrets = tomllib.loads(secrets_path.read_text(encoding="utf-8-sig"))
    database_url = secrets.get("database_url") or secrets.get("neon_database_url")
    if not database_url:
        raise SystemExit("Configure database_url ou neon_database_url em .streamlit/secrets.toml.")

    with psycopg.connect(database_url) as conn:
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
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('notas_banca', 'atas_banca', 'rascunhos_banca')
                ORDER BY table_name
            """)
            tables = [row[0] for row in cur.fetchall()]

    print("Tabelas prontas:", ", ".join(tables))


if __name__ == "__main__":
    main()
