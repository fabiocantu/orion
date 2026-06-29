# Todo

## Agora

- Validar no uso real se o novo layout da ficha ficou confortavel.
- Validar no uso real se o PDF ficou sem sobreposicao em todos os casos.
- Confirmar se os criterios oficiais de TFG I e TFG II estao completos.

## Proximos passos

- Melhorar a edicao e visualizacao de criterios dentro do proprio sistema.
- Refinar o layout do PDF para ficar mais institucional.
- Melhorar mensagens de sucesso e erro em cadastro/importacao.
- Revisar a pagina de relatorios com indicadores mais uteis para coordenacao.

## Ideias futuras

- Exportacao mais completa de dados.
- Envio real por e-mail.
- Auditoria mais detalhada nas edicoes.
- Backup/restauracao do banco.
- Tela de gerenciamento de professores sem orientandos.

## Quando mudar de computador

1. Abrir `context.md`
2. Ler `changelog.md`
3. Ver `todo.md`
4. Subir o app com:

```powershell
cd "E:\OneDrive\Documentos\# PYTHON - GESTOR DE ASSESSORIA\gestor-tfg"
streamlit run app.py
```

5. Se der comportamento estranho, parar instancias antigas:

```powershell
Get-Process -Name streamlit,python -ErrorAction SilentlyContinue | Stop-Process -Force
```
