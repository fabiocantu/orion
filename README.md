# Gestor de Assessoria de TFG

MVP em Python + Streamlit para substituir fichas de assessoria de TFG do curso de Arquitetura e Urbanismo do Centro Universitário Mater Dei.

O sistema cria automaticamente um banco SQLite local, cadastra dados mockados e permite que professores e coordenação preencham, consultem e exportem fichas de assessoria em PDF.

## Como instalar

```powershell
py -m pip install -r requirements.txt
```

## Como rodar

```powershell
streamlit run app.py
```

## Usuários mockados

- Coordenação: `coord` / `coord123`
- Professor 1: `fabio` / `fabio123`
- Professor 2: `professor2` / `professor123`
- Professor 3: `professor3` / `professor123`

## Banco e arquivos

- Banco SQLite: `data/tfg_assessorias.db`
- PDFs gerados: `output/pdfs/`

O banco é criado automaticamente ao iniciar o sistema. O usuário final não precisa criar o SQLite manualmente.

## Critérios provisórios

Os critérios estão em `src/seed.py`, na função `seed_criteria()`. Eles são provisórios e devem ser substituídos pelos critérios oficiais do curso quando disponíveis.

Na planilha Google, a aba `Critérios` deve usar este formato:

```text
etapa_tfg | fase | criterio | descricao | comentario_obrigatorio_quando_nao_sim | ativo
```

Fases previstas:

- TFG I: `Relatório Científico – Fundamentação Teórica`
- TFG I: `Estudo de Viabilidade – Plano de Ocupação`
- TFG II: `Estudo Preliminar`
- TFG II: `Anteprojeto`

Cada critério é avaliado por escala:

- `EXCELENTE (90 a 100%)`
- `SUFICIENTE (70 a 90%)`
- `PARCIAL (50% a 70%)`
- `INSUFICIENTE (<50%)`
- `NÃO COMPETE A ETAPA`

Os comentários dos critérios ficam sempre abertos e opcionais. Ao final da ficha há o campo `Situação atual e recomendações gerais` e o campo `Comentário geral`.

## Google Sheets

O módulo `src/google_sheets.py` está preparado como ponto de integração futura. No MVP ele não executa sincronização externa, mantendo o sistema sem dependência de internet ou serviços pagos.

## E-mail

O módulo `src/email_sender.py` simula o envio. Ele pode ser substituído futuramente por integração real com SMTP ou outro provedor.

## PDF

A geração de PDF usa ReportLab para evitar dependências de sistema operacional. O PDF inclui identificação institucional, dados do aluno/orientador, critérios, respostas, comentários e espaço reservado para logo.

## Neon/PostgreSQL

O app usa SQLite quando nao existe `DATABASE_URL`. Para usar Neon/PostgreSQL, crie o arquivo local `.streamlit/secrets.toml` com:

```toml
DATABASE_URL = "postgresql://usuario:senha@host/neondb?sslmode=require"
```

Esse arquivo fica fora do controle de versao via `.gitignore`.

Para migrar o SQLite local para o Neon:

```powershell
py migrate_sqlite_to_neon.py --confirm
```

O script limpa as tabelas do Neon e copia os dados atuais de `data/tfg_assessorias.db`, preservando IDs e vinculos.
