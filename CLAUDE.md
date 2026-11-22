# PROG_Relatorio_G2_Automacao — regras para qualquer sessão neste repositório

Retomada: ler `STATE.md` (estado atual e próximo passo exato) e `docs/decisions/` (decisões
duráveis). Não refazer descoberta já registrada em `docs/discovery/` e `data/catalog/`.

## Nomenclatura (obrigatória)
O objeto de trabalho é o **Relatório G2** (por extenso, *Relatório Mensal do G2*). Em texto,
sempre `Relatório G2 nº 14 — Agosto/2026`. **Não use "RM14", "RM11" nem "RM" como identificador**:
a sigla só aparece ao citar o nome literal de um arquivo de terceiros. Tecnicamente, a identidade
são dois campos independentes, `report_number` (14) e `reference_month` ("2026-08"), gerados e
formatados por `prog_g2_report.report_id` — não duplicar parser nem rótulo em outro lugar.

## Objetivo
Engenharia reversa do **Relatório Mensal do Grupo 2 – Gestão de Engenharia e Socioambiental**
(contrato Programa), em duas fases distintas:
- **Fase A (descoberta, uma vez):** descobrir como o relatório funciona e transformar em
  documentação, regras, linhagem de fontes, assets, código, testes e um **modelo certificado**.
- **Fase B (produção mensal):** "Gerar o Relatório G2 Nº N" produz um DOCX/PDF **novo, do zero**, a partir
  do modelo certificado + fontes daquele Relatório G2. Sem reaprender estrutura.

**Proibido como solução final:** abrir o DOCX anterior, trocar dados, salvar como novo mês.
O builder começa em `Document()` vazio: página, seções, estilos, cabeçalho/rodapé, capa, TOC,
textos, assets, imagens geradas das fontes, tabelas, anexos, campos, validação, DOCX/PDF.

## ⛔ Regra nº 1 — SharePoint é FONTE, somente leitura
Detalhes em `.claude/rules/sharepoint-readonly.md`. Resumo: ler, listar, pesquisar, consultar
metadados e conteúdo em memória é livre. **Qualquer** escrita, cópia, upload, criação, renomeação,
exclusão ou **download persistente** exige autorização explícita da Emmily nesta conversa.
Código: só `prog_g2_report.sharepoint.graph_ro` (allowlist fechada, só GET;
`SharePointWriteBlockedError` para o resto; `tests/test_graph_ro_guard.py` lê a AST).
A sincronização OneDrive local `C:\caminho\exemplo\Dynatest Engenharia\` é o mesmo SharePoint:
não é fonte deste projeto e `security.assert_write_allowed()` recusa escrita lá.
Permissão técnica da credencial ≠ autorização funcional.

## ⛔ Regra nº 2 — Segredos
Autenticação é service principal por **client secret** (DEC-004): `AZURE_TENANT_ID`,
`AZURE_CLIENT_ID` e `AZURE_CLIENT_SECRET`, só no `.env` (nunca versionado), nada hardcoded.
Certificado está fora do escopo. Nunca pedir o valor do segredo em conversa — a Emmily preenche o
`.env` sozinha. Nunca imprimir, logar, commitar ou colocar em exceção, STATE ou docs: token ou
segredo, nem parcialmente para diagnóstico. Autenticação é testada com operação read-only.
`python scripts/check_secrets.py` antes de todo commit. Detalhes em `.claude/rules/secrets-and-git.md`.

## Regra nº 3 — Investigar antes de afirmar
Toda regra do relatório tem `evidence` e `confidence` (CONFIRMED / HIGH / MEDIUM / LOW / UNKNOWN).
Coincidência histórica não é regra. Erro histórico (copy-forward, typo) vira anomalia em
`data/catalog/anomalies.jsonl` com `should_learn_as_rule=false`, nunca vira código.
**Referência do padrão vigente: o Relatório G2 nº 14 — Agosto/2026.** É o estágio mais atual e
recebeu elementos que os anteriores não têm. Ordem de prioridade: instrução da Emmily > regra
contratual > modelo confirmado > nº 14 > nº 13 > nº 12 > nº 11 > nº 06 a nº 10 > nº 01 a nº 05.
Mas agosto **também erra** (copy-forward, exceção do mês), e a hierarquia não é automática: uma
regra que se repete em maio, junho, julho e agosto é **evidência mais forte** que um detalhe
isolado de agosto. Registrar sempre o conflito.
Não perguntar o que se descobre no repo, no SharePoint, na Lista Mestra ou nos relatórios.
Quando perguntar: o que encontrei / evidência / o que segue ambíguo / por que preciso / interpretação provisória.

## Regra nº 4 — Código primeiro, IA por último
Tudo determinístico é código: geometria, estilos, cabeçalho/rodapé, TOC, filtros, ordenação,
contagens, assets, frases fixas, validações. IA só para compreender documentos, interpretar
eventos, sintetizar e redigir narrativa variável. Nada de hardcode do nº 14: ele é evidência e
teste, não o algoritmo. CONTEÚDO, REPRESENTAÇÃO e POSICIONAMENTO são três coisas distintas.

## Modelo certificado
`G2_REPORT_MODEL` com `version` e `status` (NONE → CANDIDATE → FROZEN → CERTIFIED). CERTIFIED
só após aprovação da Emmily de uma reconstrução histórica do zero (golden test: fontes do Relatório G2 +
modelo → novo DOCX/PDF → comparação com o PDF real; ≥95% fidelidade visual estrutural e 100%
em fatos, fontes, anexos, numeração, mês, rodovias, documentos, ordem). Mudança permanente de
padrão = nova versão do modelo.

## Convenções
- pt-BR em docs, commits e mensagens. Código com nomes em inglês.
- Python 3.12 em `.venv/` (`.venv\Scripts\python`). Pacote em `src/prog_g2_report/`.
- Testes: `.venv\Scripts\python -m pytest` (offline por padrão; `-m network` exige `.env`).
- Lint: `.venv\Scripts\ruff check .`
- Scripts em `scripts/`, numerados por ordem de execução. Temporários em `tmp/` (limpar depois).
- Catálogos JSONL em `data/catalog/` seguem `prog_g2_report.catalog`. Identidade de arquivo no
  SharePoint é `(drive_id, item_id)`; caminho é atributo mutável.
- Decisões duráveis: `docs/decisions/DEC-NNN-*.md`. Estado: `STATE.md` (curto, atual, sem diário).
- `.py` sempre com Write/Edit (heredoc do Bash pode colapsar `\\`).
- Subagentes em `.claude/agents/` (read-only; resultados voltam resumidos e são registrados em
  artefatos do repo). Sem Agent Teams nesta fase.

## Git
Local, `main`, sem remoto. Commit só em marco lógico/checkpoint, após `git status`, revisão do
diff, `check_secrets.py` e testes. Nunca push, force, reset --hard, rebase, amend, troca de
branch, sem autorização explícita. Terminar a mensagem com o trailer `Co-Authored-By:` do modelo
que está rodando a sessão (o harness informa qual é; não fixar um nome de modelo aqui).

## Checkpoint de fase
Atualizar `STATE.md`, registrar DEC se houver decisão durável, rodar testes, `git status`,
commit lógico, registrar HEAD e próximo passo exato. Nunca deixar contexto crítico só no chat.

## Ciclo de sessão (protocolo oficial)
**A conversa é descartável; o repositório é a fonte canônica.**

- `/session-start` — abre a sessão: reconstrói o estado pelo repositório, reconcilia com Git e
  disco, apresenta o briefing e **para** antes de qualquer implementação.
- `/session-close` — encerra a sessão: para o desenvolvimento, persiste o que só existe na
  conversa, valida, atualiza `STATE.md` e `docs/sessions/LOG.md`, aplica a política Git e **para**.

Onde cada informação mora: estado atual em `STATE.md`; histórico em `docs/sessions/LOG.md`;
decisões em `docs/decisions/`; descobertas em `docs/discovery/`; catálogos em `data/catalog/`
(gerados por script, nunca editados à mão).
