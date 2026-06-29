# Changelog

## 2026-06-27

- Criados arquivos de continuidade:
  - `context.md`
  - `changelog.md`
  - `todo.md`

## 2026-06-26

- Criado MVP em Streamlit + SQLite.
- Adicionado login para professor e coordenacao.
- Criadas paginas:
  - Professor
  - Coordenacao
  - Relatorios
  - Configuracoes
  - Cadastros
- Adicionado cadastro manual de:
  - professores
  - alunos
  - orientacoes
- Adicionada importacao em lote por CSV/XLSX.
- Ajustado lote para aceitar apenas:
  - `nome`
  - `etapa_tfg`
  - `tema`
- Adicionados botoes de exclusao para:
  - professor
  - aluno
  - orientacao
- Adicionada troca de senha para usuarios logados.
- Restringido Google Sheets para coordenacao.
- Ajustado menu para esconder paginas por perfil.
- Alterada ficha de orientacao:
  - rascunho em `session_state`
  - slider de 1 a 4
  - checkbox "Nao compete a etapa"
  - observacao ao lado do criterio
  - ordem nova dos blocos
  - botoes Salvar e Salvar e enviar
- Ajustado PDF para evitar sobreposicao em campos longos.

## Como usar este arquivo

- Adicionar uma linha curta por mudanca relevante.
- Registrar data e resumir o que foi alterado.

## 2026-06-27

- Adicionado suporte a Neon/PostgreSQL via `DATABASE_URL`.
- Mantido SQLite como fallback quando `DATABASE_URL` nao estiver configurada.
- Criado script `migrate_sqlite_to_neon.py` para migrar dados locais.
- Adicionado `.gitignore` protegendo `.streamlit/secrets.toml`.
- Adicionado `psycopg[binary]` ao `requirements.txt`.
