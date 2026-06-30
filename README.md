# Gestor de Assessoria de TFG

Sistema em Python + Streamlit para gestão de fichas de assessoria e bancas de TFG do curso de Arquitetura e Urbanismo.

O app permite que professores e coordenação cadastrem alunos, orientações, fichas de assessoria, bancas, notas, atas e PDFs. Também oferece consulta pública para alunos por RA.

## Como instalar

```powershell
py -m pip install -r requirements.txt
```

No Linux/Codespaces:

```bash
python -m pip install -r requirements.txt
```

## Como rodar

```powershell
streamlit run app.py
```

No Linux/Codespaces:

```bash
streamlit run app.py
```

## Acesso inicial

O sistema cria dados iniciais para desenvolvimento quando o banco está vazio. Por segurança, senhas padrão não são documentadas aqui.

Para redefinir a senha da coordenação, use:

```bash
python scripts/reset_coord_password.py
```

Se estiver usando Neon/PostgreSQL, confirme antes que o terminal aponta para o banco correto:

```bash
python -c "from src.database import database_label; print(database_label())"
```

O resultado esperado em produção é:

```text
Neon/PostgreSQL
```

## Banco e arquivos

- SQLite local: `data/tfg_assessorias.db`
- PDFs gerados: `output/pdfs/`
- Secrets locais: `.streamlit/secrets.toml`

O SQLite é criado automaticamente ao iniciar o sistema. O arquivo `.streamlit/secrets.toml` deve ficar fora do Git.

## Neon/PostgreSQL

O app usa SQLite local quando não existe configuração de Neon. Em produção, configure `DATABASE_URL` e `DATABASE_BACKEND` nos secrets do Streamlit ou em variáveis de ambiente.

Exemplo de `.streamlit/secrets.toml` local, sem credenciais reais:

```toml
DATABASE_BACKEND = "neon"
DATABASE_URL = "postgresql://USUARIO:SENHA@HOST/neondb?sslmode=require"
```

Nunca publique a `DATABASE_URL` real no GitHub.

Para migrar o SQLite local para o Neon:

```powershell
py migrate_sqlite_to_neon.py --confirm
```

Atenção: o script de migração limpa as tabelas do Neon antes de copiar os dados locais.

## Funcionalidades principais

- Login por perfil de professor e coordenação.
- Cadastro e importação de alunos, professores e orientações.
- Geração de assessorias por etapa de TFG.
- Preenchimento de fichas com rascunho e envio/finalização.
- Gestão de bancas, membros avaliadores, notas e atas.
- Geração de PDFs de fichas e relatórios/atas de banca.
- Consulta pública por RA para fichas e atas disponíveis.
- Calendário público de bancas com visualização em cards ou tabela.

## Critérios de assessoria

Os critérios iniciais estão em `src/seed.py`, na função `seed_criteria()`. Eles podem ser substituídos pelos critérios oficiais do curso.

Na importação por planilha, a aba `Critérios` deve usar este formato:

```text
etapa_tfg | fase | criterio | descricao | comentario_obrigatorio_quando_nao_sim | ativo
```

Fases previstas:

- TFG I: `Relatório Científico - Fundamentação Teórica`
- TFG I: `Estudo de Viabilidade - Plano de Ocupação`
- TFG II: `Estudo Preliminar`
- TFG II: `Anteprojeto`

Escala usada nas fichas:

- `EXCELENTE (90% a 100%)`
- `SUFICIENTE (70% a 90%)`
- `PARCIAL (50% a 70%)`
- `INSUFICIENTE (abaixo de 50%)`
- `NÃO COMPETE A ETAPA`

## Google Sheets

O módulo `src/google_sheets.py` concentra a integração/importação por planilhas. Não publique arquivos de configuração ou credenciais de Google no repositório.

## E-mail

O módulo `src/email_sender.py` simula envio. O envio real pode ser integrado futuramente por provedor externo ou API de e-mail.

## PDF

A geração de PDF usa ReportLab e inclui dados institucionais, dados do aluno, orientador, critérios, respostas, comentários, composição de banca, notas e ata, conforme o tipo de documento.

## Segurança

- Não publique `.streamlit/secrets.toml`.
- Não publique `DATABASE_URL` real.
- Não publique senhas padrão ou credenciais de usuários.
- Troque a senha da coordenação antes de usar em produção.
- Verifique se o app está apontando para `Neon/PostgreSQL` antes de executar scripts que alteram senha em produção.
