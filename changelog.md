# Changelog

## 2026-06-30

- Adicionado autosave de rascunhos nas fichas de assessoria do professor:
  - salva alterações como `Rascunho` sem bloquear a ficha;
  - evita gravação a cada tecla usando intervalo mínimo.
- Adicionado autosave em bancas:
  - notas salvas automaticamente quando alteradas;
  - ata salva automaticamente quando preenchida;
  - mantidos os botões manuais de salvar.
- Corrigidos problemas de encoding/mojibake em arquivos tocados, preservando textos com acentos em UTF-8.
- Melhorada a tela inicial pública de bancas:
  - adicionada alternância entre visualização em Cards e Tabela;
  - Cards mostram apenas bancas de hoje;
  - Tabela mostra a semana selecionada;
  - Cards exibem dia da semana e data completa;
  - ambas as visualizações mostram orientador e avaliadores.
- Otimizada a consulta pública de bancas:
  - orientador e avaliadores retornam na mesma consulta;
  - adicionado cache curto para reduzir chamadas ao Neon;
  - cache é limpo ao salvar, importar ou excluir bancas e ao alterar configuração do calendário público.
- Aumentada a resiliência da conexão com Neon/PostgreSQL:
  - pool passa a checar conexão antes de entregar;
  - leituras simples tentam reconectar uma vez em `psycopg.OperationalError`.
- Adicionada consulta pública de atas de banca por RA:
  - aluno pode ver bancas com ata registrada;
  - aluno pode gerar e baixar o PDF da ata/relatório da banca;
  - acesso segue restrito ao aluno localizado pelo RA.
- Mantido o fluxo de reset de senha da coordenação por script, com orientação para apontar explicitamente para Neon antes de executar.

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
