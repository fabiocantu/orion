# Context

## Projeto

- Nome: Gestor de Assessoria de TFG
- Curso: Arquitetura e Urbanismo - Centro Universitario Mater Dei
- Stack: Python, Streamlit, SQLite, ReportLab
- Pasta principal: `gestor-tfg/`

## Objetivo atual

- Gerenciar professores, alunos, orientacoes e fichas de assessoria de TFG I e TFG II.
- Permitir cadastro manual e importacao em lote.
- Gerar PDF da ficha apos salvar.

## Estrutura importante

- `app.py`: entrada do Streamlit
- `pages/1_Professor.py`: area do professor
- `pages/2_Coordenacao.py`: area da coordenacao
- `pages/4_Config.py`: configuracoes, reset e senha
- `pages/5_Cadastros.py`: professores, alunos, orientacoes e importacao em lote
- `src/database.py`: conexao e inicializacao do SQLite
- `src/seed.py`: seeds, criterios oficiais e resets
- `src/utils.py`: regras de negocio
- `src/pdf_generator.py`: geracao do PDF

## Regras de negocio atuais

- TFG I:
  - 4 assessorias
  - fases:
    - Relatorio Cientifico - Fundamentacao Teorica
    - Estudo de Viabilidade - Plano de Ocupacao
- TFG II:
  - 10 assessorias
  - fases:
    - Estudo Preliminar
    - Anteprojeto

## Ficha de orientacao

- Ordem atual da ficha:
  - Data realizada
  - Situacao atual e recomendacoes gerais
  - Criterios com slider
  - Observacoes gerais
  - Avaliacao final
- Cada criterio tem:
  - slider de 1 a 4
  - checkbox "Nao compete a etapa"
  - observacao ao lado
- Botoes:
  - Salvar
  - Salvar e enviar
  - Gerar PDF
  - Baixar PDF

## Cuidados conhecidos

- Se o Streamlit ficar estranho, pode haver mais de uma instancia rodando.
- Para parar tudo:

```powershell
Get-Process -Name streamlit,python -ErrorAction SilentlyContinue | Stop-Process -Force
```

- Para subir de novo:

```powershell
cd "E:\OneDrive\Documentos\# PYTHON - GESTOR DE ASSESSORIA\gestor-tfg"
streamlit run app.py
```

## Como usar este arquivo

- Atualizar este arquivo quando a estrutura, fluxo ou decisoes importantes mudarem.
- Manter aqui o retrato mais fiel do estado atual do projeto.

## Banco remoto

- O projeto agora suporta SQLite local e Neon/PostgreSQL.
- Sem `DATABASE_URL`, usa `data/tfg_assessorias.db`.
- Com `DATABASE_URL` em `.streamlit/secrets.toml`, usa Neon/PostgreSQL.
- A migracao SQLite -> Neon fica em `migrate_sqlite_to_neon.py`.
- Nao registrar a connection string em arquivos versionados.
