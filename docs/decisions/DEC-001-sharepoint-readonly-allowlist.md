# DEC-001 — SharePoint via Graph, somente leitura, com allowlist fechada de operações

**Data:** 2026-09-21 · **Status:** ACEITA

## Contexto
O SharePoint corporativo (`contoso.sharepoint.com/sites/exemplo`) é a fonte de todo o material
do relatório. A credencial de aplicativo pode tecnicamente permitir escrita. O briefing exige
que este projeto seja **read-only por construção**, não por disciplina. Existe também uma
sincronização OneDrive local da mesma biblioteca (`C:\caminho\exemplo\Dynatest Engenharia\`),
usada por projetos irmãos antigos e depois abandonada como fonte pelo `PROG_Cerebro_Documental`.

## Decisão
1. A única porta para o SharePoint é `prog_g2_report.sharepoint.graph_ro.GraphReadOnlyClient`.
2. Segurança em três camadas: **allowlist fechada de operações** (nome + padrão de caminho),
   **um único verbo HTTP** (`httpx.Client.get`), e **bloqueio por nome de endpoint** mesmo em GET
   (`createUploadSession`, `/copy`, `/createLink`, `/invite`, `/checkout`, `/checkin`, `/restore`,
   `/permissions/`, `/subscriptions`, `/workbook/`, `/thumbnails`).
3. Violação → `SharePointWriteBlockedError`. `tests/test_graph_ro_guard.py` lê a AST do módulo
   e falha se surgir verbo de escrita, endpoint proibido ou método com nome de escrita.
4. A pasta sincronizada local **não é fonte** e é tratada como o próprio SharePoint:
   `security.assert_write_allowed()` recusa escrita lá.
5. Download persistente exige `DownloadAuthorization` (registrada em
   `state/download_authorizations.jsonl`) e destino em `tmp/downloads/`. Leitura em memória
   (`read_bytes`) é permitida para análise pontual.
6. Ferramentas MCP `sharepoint_*` de escrita são vetadas em `.claude/rules/sharepoint-readonly.md`.

## Evidência
- Briefing, seções 7 e 9.
- `PROG_Cerebro_Documental/scripts/graph_ro.py` e `tests/test_graph_ro.py`: precedente de guarda
  por AST que funcionou; aqui foi estendido para allowlist de operações, pois bloquear só o
  verbo não cobre endpoints de efeito colateral acessíveis por GET/POST.

## Alternativas consideradas
- Bloquear apenas verbos não-GET: insuficiente (pesquisa e alguns efeitos colaterais usam POST;
  alguns GETs têm efeito remoto). Rejeitada como única defesa.
- Usar a pasta OneDrive local como fonte: descarta identidade `(drive_id, item_id)`, sofre com
  MAX_PATH e hidratação, e escreve de volta por engano com facilidade. Rejeitada.
- SDK oficial `msgraph-sdk`: expõe métodos de escrita por padrão; superfície maior. Rejeitada.

## Consequências
- Pesquisa via `POST /search/query`, se necessária, exige nova DEC com endpoint fixo.
- Todo script que grava em disco chama `assert_write_allowed()`.
