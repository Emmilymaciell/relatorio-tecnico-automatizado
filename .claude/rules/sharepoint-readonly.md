# Regra absoluta: SharePoint é FONTE, somente leitura

Vale para o agente principal e para todo subagente deste repositório.

## Permitido sem autorização
Autenticar, resolver site/drive, navegar, listar, consultar metadados, IDs, hashes,
datas, tamanhos, pesquisar, ler conteúdo em memória (streaming) para análise.

## Proibido sem autorização explícita da Emmily nesta conversa
Editar, substituir, renomear, mover, excluir, criar pasta/arquivo, upload, alterar
metadados ou permissões, compartilhar, copiar dentro do SharePoint, sincronizar
biblioteca inteira, **persistir cópia local de arquivo bruto**.

## Ferramentas MCP vetadas neste projeto
`sharepoint_upload_file`, `sharepoint_update_file`, `sharepoint_delete_item`,
`sharepoint_move_item`, `sharepoint_rename_item`, `sharepoint_copy_item`,
`sharepoint_create_folder`. Não invocar. Se um plano exigir uma delas, parar e perguntar.

## Download para disco (quando indispensável)
Parar e informar: arquivo, origem, motivo, o que será feito, onde ficará (sempre `tmp/`),
se será apagado. Aguardar autorização. Registrar em `state/download_authorizations.jsonl`.

## Sincronização OneDrive local
`C:\caminho\exemplo\Dynatest Engenharia\` é a mesma biblioteca sincronizada.
**Não é fonte deste projeto e é igualmente proibido escrever lá.**
`prog_g2_report.security.assert_write_allowed()` levanta erro para esse caminho.

## Código
`graph_ro.py` só executa operações da allowlist. Qualquer outra levanta
`SharePointWriteBlockedError`. `tests/test_graph_ro_guard.py` lê a AST e falha se
aparecer método/endpoint de escrita. Permissão técnica da credencial ≠ autorização funcional.
