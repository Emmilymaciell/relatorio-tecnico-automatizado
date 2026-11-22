# STATE — estado atual do projeto

**CURRENT_PHASE:** Fase 10 — Certificação. Aguardando decisões da Emmily (ver P1). Nada em
execução. Produção mensal (Fase 11) já pronta para uso.
**PRIORIDADE ATUAL (2026-10-05):** produção assistida do **Relatório G2 nº 15 — Setembro/2026**
com v0.14 (BUILDER_READY, revisão humana obrigatória; certificação v1.0 em paralelo, não bloqueia).
Branch `production/report-g2-15-sep-2026` (base `cf42593`, sem commit: só quando a Emmily disser
"essa rodada está aprovada"). DRAFT_01 em `output/15_2026-09/DRAFT_01/` (run_manifest.yaml,
changelog em `output/15_2026-09/CHANGELOG_DRAFTS.md`, QA em `tmp/producao/15_2026-09/qa/`).
Lista Mestra v547 (snapshot 13:40:49, ainda em edição pela Pessoa A): regerar com a vigente
quando a Emmily pedir.
**G2 REPORT TRIBUNAL (2026-10-05/06, só diagnóstico, nada corrigido):** comparação do nosso
DRAFT_01 (CANDIDATE_A) com o nº 15 feito à mão pelo engenheiro (CANDIDATE_B, benchmark humano,
não verdade; cópias + sha256 em `tmp/review/report15/candidates/`). Briefing comum
`tmp/review/report15/BRIEF.md`; 10 especialistas → `tmp/review/report15/findings/`; CHIEF JUDGE
consolida em `docs/review/REPORT15_TRIBUNAL.md`, `docs/review/REPORT15_SCORECARD.md` e
`data/review/report15_candidate_comparison.jsonl`. **Rodada 1 CONCLUÍDA (2026-10-06):** 53
diferenças (0 CRITICAL, 8 HIGH); documento de hoje = empate técnico; método = automático; 14
perguntas (Q1–Q14) no §10 do TRIBUNAL.
**REMEDIAÇÃO + DRAFT_02 (2026-10-06):** revisão da Emmily estruturada (33 itens,
`data/review/report15_user_feedback.jsonl`, `docs/review/REPORT15_USER_REVIEW.md`); veredito
`docs/review/REPORT15_CONSOLIDATED_VERDICT.md`; backlog `data/review/report15_remediation_backlog.jsonl`;
perguntas ao engenheiro `docs/review/ENGINEER_QUESTIONS_REPORT15.md` (EQ-01..22). Modelo 0.15 (só no
branch, pendente de aprovação). Snapshot estável congelado: Lista Mestra v559 (sha1 0ec44b96,
`tmp/downloads/producao_15_2026-09/draft02_snapshot/`), projetos v593, ambiental v358. DRAFT_02 em
`output/15_2026-09/DRAFT_02/` (46 págs; ok=False só pelos 3 rascunhos do Claude S1/S2/S4 aguardando
aprovação). Estado pré-remediação salvo em `tmp/review/report15/pre_remediation_git_diff.patch`.
**Próximo passo:** revisão da Emmily do DRAFT_02. Sem commit até "essa rodada está aprovada".
**Modo:** autopilot (orquestrador + subagentes). Histórico completo dos gates: `docs/qa/GATES.md`.
**INFRA (programa vNext da plataforma, 2026-10-11; não muda o relatório):** remoto privado
(repositório privado de origem) com todas as branches e tags (a linha "sem remoto"
abaixo está superada). `e42998a` declara `matplotlib` nos extras `discovery` (já usado por
`render/visuals/_canvas.py`; achado pela restauração certificada). `947418e` commitou só este
STATE.md (edições de 06/10, verbatim, autorizado pela Emmily). O código da rodada nº 15 (59 itens
modificados/novos) continua **fora do commit**, protegido pelo backup WIP da plataforma.

| | |
|---|---|
| **LAST_COMMIT** | ver `git log -1` (checkpoint antes da compactação de contexto) |
| **Branch** | `main`, sem remoto; worktrees de agentes em `.claude/worktrees/` (gitignored) |

## MODEL
- **G2_REPORT_MODEL v0.14 — status `BUILDER_READY` — ainda NÃO CERTIFIED.**
- Arquivos: `config/g2_report_model.yaml` (+ `g2_content_blocks.yaml`, `data_rules/`,
  `g2_render_rules.yaml`, `ooxml_base.yaml`, `assets_manifest.yaml`, `golden_allowances.yaml`).
  `config/report_spec_draft.yaml` está superado.
- Decisões: `docs/decisions/DEC-001` a `DEC-015`.

## BUILDER
- Completo. Gera o Relatório G2 a partir de `Document()` vazio (nunca abre o DOCX histórico).
- **Comando mensal:**
  `scripts/17_generate_report.py --report-number N --reference-month AAAA-MM --inputs <yaml> --master-list <xlsx>`
  (projetos e ambiental lidos por versão em memória via `graph_ro`, `current` por padrão;
  Lista Mestra em arquivo local fornecido pela Emmily — exigência do Excel COM; validações
  V_*; pauta de revisão dos slots de IA; DOCX final com campos atualizados).
  Runbook: `docs/PRODUCAO_MENSAL.md`. Ambiente: Windows + Excel + Word + família Arial Nova.
- Versão do builder = commit do `main` (pacote `prog_g2_report`); comparador do golden v4.1.

## GATES
- Gate A (linhagem de fontes): **PASS** (2026-10-01).
- Gate B (modelo pronto para o builder): **PASS** na 4ª tentativa (2026-10-02).
- Gate D / Relatório G2 nº 14: **PASS** (2026-10-04, verificação focada QA5 após 5 rodadas).
- Gate E (certificação): **pendente da Emmily**.

## GOLDEN Nº 14 (Agosto/2026) — PASS
- Reconstrução pelo pipeline real (fontes + modelo + builder), sem editar o Word histórico.
- 43/43 páginas; fatos críticos 100% (QA de fontes: 180/181 fatos, o restante MINOR de
  proveniência); anexos 100% (149); visual 0 MAJOR.
- Comparador v4.1 (diff de texto estrito): 113 diferenças em relação ao publicado, todas
  aprovadas e justificadas (anomalia catalogada ou DEC) em `docs/qa/approved_hunks/n14.yaml`.
- Controle: `output/reconstruction/14_v6/` (gitignored); prova pelo comando único em
  `.claude/worktrees/agent-a778ff4087f8bc761/output/reconstruction/14_ab/` (43 págs, 7/7 validações).

## GOLDEN Nº 13 (Julho/2026) — NÃO concluído
- Reprova só pelos 23 itens da diferença Lista Mestra **v134 × v162** (DEC-012 exige a v162,
  última versão antes da publicação; a v162 não está em disco). Lista dos 23 em
  `docs/qa/CERTIFICACAO_PACOTE.md` §7. Controle: `output/reconstruction/13_v6/`.
- Depende da captura das fontes históricas corretas (GAP-015).

## GAPS
- **P0 = 0.**
- **GAP-015 (P1, crítico no tempo):** o SharePoint guarda só 500 versões; os snapshots dos
  golden tests serão podados (projetos v127 ≈ 10/10/2026, v161 ≈ 16/10, v328 meados de
  novembro, v438 fim de novembro). Snapshots necessários: **Lista Mestra v162 e v331; projetos
  v127, v161, v328, v438; ambiental v289, v310.** Persistir em `tmp/historical_sources/` exige
  autorização da Emmily (download persistente; regra `.claude/rules/sharepoint-readonly.md`).
- Abertos não bloqueantes (catálogo `data/catalog/gaps.jsonl`): GAP-005 (slots de IA com
  revisão humana), GAP-012 (data de referência ambiental), GAP-013/014 (defaults editoriais),
  GAP-003, GAP-004, GAP-006.

## P1 / DECISÕES HUMANAS ABERTAS (Emmily)
1. **Certificação:** aprovo / aprovo com mudanças (quais) / não aprovo — `docs/qa/CERTIFICACAO_PACOTE.md` §9.
2. **16 decisões editoriais** com default técnico — `docs/qa/CERTIFICACAO_PACOTE.md` §5
   (temas por documento; ressalva por disciplina; grupo todo aprovado com ressalva; frase de
   valor vazio; enumeração de NC; conjunto vazio do 2.2; capa; painéis ambientais; paginação
   do Controle de Produtos; RD-102A; nomes de disciplina; Análise Programa da planilha; número do
   contrato; data de referência ambiental; bloco paisagem; bloco de desapropriação).
3. **GAP-015:** autorizar (sim/não) a gravação dos 8 snapshots — `CERTIFICACAO_PACOTE.md` §8.

## CERTIFICATION
- **NÃO promover para v1.0. NÃO criar tag.** A certificação depende das decisões acima e do
  golden temporal do nº 13.

## DO NOT REDO
Descoberta de fontes e linhagem (Wave 1: `docs/discovery/WAVE1_FINDINGS.md`), Gates A/B/D,
comparador do golden (v4.1), pacote de certificação, runbook mensal. Resultados e evidências
estão em `docs/qa/GATES.md` e nos catálogos `data/catalog/` (101 anomalias).

## NEXT_EXACT_ACTION
Uma sessão nova começa com `/session-start` e então:
1. **Não agir antes das respostas da Emmily** sobre os três itens de P1.
2. Se ela autorizar o GAP-015: baixar em memória e gravar os 8 snapshots em
   `tmp/historical_sources/` (registrar cada um em `state/download_authorizations.jsonl`);
   rodar o golden temporal do nº 13 com Lista Mestra v162, projetos v328, ambiental v289
   (`scripts/17_generate_report.py` com `--master-list tmp/historical_sources/<v162>.xlsx`
   e versões explícitas; inputs `tmp/golden_inputs_13.yaml`; emissão 2026-08-11) e comparar com
   `scripts/14_golden_compare.py --report-number 13`; resíduo esperado = 0 ou só itens com
   anomalia catalogada (aprovar como hunks em `docs/qa/approved_hunks/n13.yaml`).
3. Aplicar as decisões editoriais que ela mudar (cada mudança: modelo → nova versão,
   reconstrução do nº 14, nova conferência dos hunks).
4. Com aprovação dela e o nº 13 fechado: modelo `version: "1.0"`, `status: CERTIFIED`;
   registrar evidências, golden, tolerâncias, limitações e o commit do builder; propor a tag
   `g2-model-v1.0` e **pedir confirmação antes de criá-la**.

## Testes
Última verificação (2026-10-04, `7175e4d`): suíte offline verde (>1000 testes), `-m golden` de
texto e `-m network` verdes, `-m golden` do comparador verde com xfails documentados (rasters
sem OCR), `ruff` e `scripts/check_secrets.py` limpos.
