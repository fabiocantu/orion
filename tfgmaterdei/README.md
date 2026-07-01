# Sistema de Avaliação de TFG

Aplicativo Streamlit para calendário de bancas, lançamento de notas/atas e dashboard de resultados.

## Banco de dados

O app usa Neon/Postgres quando uma URL de banco estiver configurada. Sem URL, ele continua usando os arquivos locais `notas_banca.csv`, `atas_banca.csv` e `rascunhos_banca.json`.

Configure uma das variáveis abaixo:

```bash
DATABASE_URL="postgresql://..."
```

ou:

```bash
NEON_DATABASE_URL="postgresql://..."
```

No Streamlit Cloud, também pode usar `secrets.toml`:

```toml
database_url = "postgresql://..."
dashboard_password = "sua-senha"
```

As tabelas `notas_banca`, `atas_banca` e `rascunhos_banca` são criadas automaticamente na primeira execução.

## Como rodar

Instale o `uv`, sincronize as dependências e rode o app:

```bash
uv sync
uv run streamlit run streamlit_app.py
```
