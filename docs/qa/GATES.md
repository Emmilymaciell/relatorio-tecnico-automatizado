# Registro de gates do autopilot

Cada gate registra critério, evidência e veredito. O detalhe está nos artefatos citados.

## Gate A — Fase 4 (linhagem de fontes) · 2026-10-01 · **PASS**

| Critério | Resultado | Evidência |
|---|---|---|
| P0 == 0 | PASS | GAP-001 RESOLVED (DEC-010); `data/catalog/gaps.jsonl` sem P0 aberto |
| nenhuma fonte factual crítica UNKNOWN | PASS | `source_lineage.jsonl`: 25 TRACED, 2 PARTIAL, 1 UNKNOWN não crítico, 1 NOT_A_SOURCE; desapropriação/interferências = entrada humana confirmada (WAVE1 §E) |
| Lista Mestra modelada | PASS | `sources/master_list.py` + DEC-006/DEC-012; corpo × índice; snapshots v162/v331 provados |
| linhagem do 2.2 suficiente | PASS | quadros por rodovia 100% células nos nº 13 e 14 com v328/v438 (WAVE1 §E) |
| linhagem do 2.4 suficiente | PASS | painéis ambientais (§B), NC (§C), semanais (§D), listas (§O): fatos 100% |
| regras de anexos modeladas | PASS | DEC-010 (EMF por página), DEC-012 (índice = entregues), 149 = 149 em agosto |

Revisão adversarial (agente H) feita antes do gate; as objeções foram resolvidas por M (snapshot
de julho), E (GAP-009) e pelas correções de tipografia e confiança aplicadas no modelo v0.9.
Abertos e não bloqueantes: GAP-005, 012, 015 (P1); 006, 013, 014 (P2); 003, 004 (P3).

## Gate B — modelo pronto para o builder · tentativa 1 · 2026-10-01 · **FAIL**

Revisor independente W (não participou da escrita) sobre o HEAD `76cd304`:
- BLOCKS_GATE: (1) texto fixo do resumo executivo carregava a anomalia "Ofício" e rodovias fixas;
  (2) referências quebradas (chaves de render, `config/ooxml_base.yaml` e
  `config/golden_allowances.yaml` inexistentes); (3) regra de contagem de anexos inconsistente
  entre arquivos e o rascunho antigo ainda lido por teste.
- MAJOR: (4) o validador passava 7/7 mutações (verificava o modelo contra ele mesmo); (5) 54
  blocos fixos sem componente e duas entradas manuais escondidas; (6) confiança acima da
  evidência e a mesma evidência de julho usada como regra e como defeito; (7) dois defaults
  conflitantes para enumerar NC; (8) evidência validada contra snapshots do critério antigo.
- MINOR: rodovias fixadas em vários lugares; negrito com espaço final; regex de "RM"; assets
  gitignored impedem gerar a partir de um clone limpo.
Correções delegadas ao agente Z; nova revisão independente depois.

## Gate B — tentativa 2 · 2026-10-01 · **FAIL**

Revisor independente W2 sobre `f2fcb3c`. Das 10 objeções anteriores, 6 fechadas (1, 2, 3, 7, 9,
10) e 3 abertas (4, 5, 6); 8 fechada só por registro. Novos achados:
- BLOCKS_GATE F1: entradas humanas/IA fora de `model.inputs` (`p22_status_reference_date`;
  cláusula de natureza das NC via `ai_review` dentro de componente TEMPLATE).
- MAJOR F2: a checagem de anomalias varre só o content_blocks, não os data_rules que o builder
  emite; trechos de busca amplos demais. F3: S7 com dois defaults (fixed × keyword_map) e teste
  golden truncado. F4: confiança do componente acima da dos seus blocos.
- 16/16 mutações novas passaram pelo validador (hardcode do nº 14, CONFIRMED com meses futuros,
  `source` apontando para not_sources, `human_review: "false"`, seção 2.6 removida do ooxml_base…).
- MINOR F5: modelo × código (discontinued não lido, `p24_bm_in_progress` não ligado, defaults
  divergentes, âncoras dos visuais só no código, anomalia citada fora do catálogo).
Correções delegadas ao agente CC (worktree); BB segue o loop do golden em paralelo.

## Golden nº 14 — build do `main` (`4d3666d`) · 2026-10-01 · comparador **PASS**
44 páginas (referência 43; ALW-14-005 cobre ±2 pela paginação do Controle de Produtos);
estrutural 1,0000; conteúdo 1,0000; CRITICAL 0, MAJOR 0, MINOR 0, ALLOWED 39 (allowances v1.2).
Controle de Produtos 3/48/98/149 em ordem. Build `ok=True`, nada pendente. Ainda **não é o
Gate D**: falta o QA independente em paralelo (QA-C fontes/conteúdo, QA-D estrutural/visual,
QA-E adversarial).

## Golden nº 13 — 1º build do `main` · **FAIL**
Lista Mestra v134.0 (a v162 do DEC-012 não está em disco; persistir depende do GAP-015).
Estrutural 0,8333; conteúdo 0,8125; 21 CRITICAL. Causas em diagnóstico (agente EE): versão da
Lista Mestra, anomalias do nº 13 sem allowance (faixas RO, BM RD-103, "RD-102", assinatura),
entradas humanas do mês não transcritas, e possíveis regras do builder (NC-525.1, ordens).

## Gate B — tentativa 3 · 2026-10-01 · **FAIL** (1 BLOCKS_GATE, 2 MAJOR)
Revisor W3 sobre `4d3666d`, gerando os textos com `render/*` sobre a Lista Mestra (nº 11–15):
- BLOCKS_GATE: `P2.2_DESAPROPRIACAO` emite o rótulo sem valor da anomalia
  `P2.2_DUP_RD101_SEM_VALOR` com status OK, e o esquema da entrada descreve isso como regra; o
  golden passa porque a entrada transcrita reproduz o defeito.
- MAJOR: S6 com plural fixo ("às rodovias RD-104" com uma rodovia); validador cego fora de
  `components`/blocos (12/12 mutações novas passaram: editorial_defaults, ooxml_base,
  positioning, confiança fora de componentes, defaults duplicados, `review_key`).
- MINOR: trecho de busca de `P2.1_RESUMO_PONTO_FINAL` invertido; artigo fixo no S5; frases
  editoriais no código do 2.4; validação de anexos só textual.

**Critério de convergência adotado pelo orquestrador.** Cada revisão amplia a superfície de
mutação; o validador é defesa em profundidade, não prova de correção (o golden e o QA
independente cobrem o documento gerado). A tentativa 4 corrige o BLOCKS_GATE, os 2 MAJOR e as
mutações listadas, e é verificada por um revisor independente **focado** nesses itens. Se ele
não achar BLOCKS_GATE novo, o Gate B passa; MAJORs residuais viram pendência registrada.

## Gate D (nº 14) — QA-D estrutural/visual · **FAIL** (STRUCTURAL_CRITICAL 0, VISUAL_MAJOR 3)
Estrutura, sumário atualizado, cabeçalho/rodapé, margens e fontes embutidas (Arial Nova) OK.
MAJOR que o comparador não enxerga:
1. 2.2.2 p24: o 1º recorte do Controle de Produtos não usa o espaço livre (16,7 cm em branco) e
   a frase de chamada fica separada da tabela — é a causa da página a mais; ALW-14-005/007
   estavam encobrindo isso.
2. 2.4.2 p30: no painel de licenças reconstruído, a coluna Empresa invade Rodovia e Nº Processo
   (ilegível); ALW-14-017 aprovava só a geometria.
3. 2.4.2 e ANEXOS: valores da 2ª coluna do Controle de Produtos em negrito (194 spans) —
   formatação herdada da planilha.
MINOR: "RD-101:"/"RD-104:" separadas dos painéis. Correções: agente GG (builder) e extensão do
comparador (negrito por coluna, página > 50% em branco, texto sobreposto em figura reconstruída).

## Gate D (nº 14) — QA-C fontes/conteúdo · **CONTENT_100: NÃO · ANNEX_100: SIM**
Recalculado com código próprio (sem importar builder/render): 99 de 100 fatos estruturados OK —
identidade, produtos ativos, Controle de Produtos 3/48/98 e índice 149 (ordem e cobertura),
encerramento (44 páginas, 149 anexos, extensos), RO, RM/BM/RI/RA/RCA/NC, licenças e
condicionantes × v310, status do 2.2 × v436, entradas humanas.
- DIVERGENTE: quadro da RD-101 desenhado com a v436 (versão do texto) em vez da v438 (versão do
  painel); só essa linha difere entre as versões → bug de ligação de fonte (agente GG).
- SEM_FONTE: texto fixo do resumo (S7) e dos pareceres afirma temas sem documento no mês
  ("condicionantes", "desapropriação", "ocorrências ambientais", "Ateste"); processos GAMB fixos
  sem planilha → default passa a `keyword_map`, anomalia P2.1_S7_TEMAS_SEM_SUPORTE, GAMB como
  constante de contrato (agente FF).
- Proveniência: manifest sem drive_id/item_id/versão por fonte e sem versão por componente
  (agente GG).

## Gate D (nº 14) — QA-E adversarial · **FAIL** (BLOCKS_GATE)
O "conteúdo 1,0" do golden não prova o que diz: o comparador v1 compara sequências de códigos,
rodovias do texto e identidade, e aprova PDFs com datas, status, rodovia ou descrição trocados
nas linhas do Controle de Produtos, números da narrativa alterados, página de texto apagada com
total coerente, painéis em branco ou trocados. Sobreviveram: independência do comparador (não
importa o builder) e ausência de hardcode do nº 14 (build sintético nº 15 sem nada de agosto).
Enfraquecidos: allowances (ALW-14-003 "Tipo" sem base; 008/009/012 não usadas, 012 curinga;
005/007 largas demais; 004 antecipa decisão pendente); golden com Lista Mestra v335 (não v331)
e texto do 2.2 da v436 (reproduz anomalia); entradas transcritas fazem `cover_date`,
`signature_date` e agenda passarem por construção; o nº 15 sintético revelou S1 afirmando
atividade sem linhas, "dos Notificações" e RO_INTRO sem RO.
Correções: comparador v2.0 (agente HH), allowances v1.3 e textos condicionais (FF), snapshot
único por fonte e proveniência (GG). Nova rodada de QA independente depois.

## Golden nº 13 (temporal) — loop do EE · **FAIL só por versão da Lista Mestra**
Com a v134 e a proposta de allowances v1.3: estrutural 1,0; conteúdo 0,9062; 6 CRITICAL, todos
provados como diferença v134 × v162 (lendo a v162 em memória): BM-007/008/009.1 da RD-104 no
2.4, PA-640.1 e PA-677.1 no índice, total de anexos 163 × 165. Com a v162 em memória os textos e
o total (165) fecham; o Controle de Produtos fica PENDING porque o Excel exige arquivo e
persistir a v162 depende da autorização da Emmily (GAP-015). NC-525.1 "a mais" era erro do
extrator (quebra de linha), corrigido. nº 14 continua PASS no código do EE.

## Comparador v2.0 integrado (`33e7690`) e rebuild do nº 14 (DD2) · **FAIL por bug**
O comparador v2.0 (HH) reprova as 15 mutações que o v1 aprovava: linha inteira do Controle de
Produtos (6 campos), fatos da narrativa por seção, cobertura de texto, painéis em branco ou
trocados (identidade não verificável nos painéis ambientais sem OCR). No PDF antigo acusou 12
`narrative_facts`, todos anomalias catalogadas ainda sem allowance.
O rebuild com as correções (DD2) gerou 39 páginas com 2.2 e 2.4 do Controle de Produtos FAILED:
na 2ª passada (1º recorte dimensionado pelo espaço livre) o workbook do Excel em cache estava
desconectado (`com_error -2147220995`). Correção e golden v2 com o agente JJ.

## Gate B — tentativa 4 · 2026-10-02 · **PASS** → modelo v0.12 `BUILDER_READY`
Verificação focada W4 (critério de convergência): BLOCKS_GATE da tentativa 3 fechado (rótulo sem
valor vira PENDING_HUMAN; sentinela `null_reason` emite texto padronizado), S6 com concordância,
validador reprova W 7/7, W2 16/16, W3 12/12; nenhum BLOCKS_GATE novo; sem hardcode.
**Pendências registradas (MAJOR residual):**
- A. S7 e pareceres do 2.4 passaram de frase fixa (idêntica nº 12–14) a temas por palavra-chave
  (DEC-007/QA-C); decisão editorial a confirmar pela Emmily; risco de falso negativo com PA genérico.
- B. S5 com uma rodovia: "das obras dos trechos RD-104" (concordância não generalizada).
- MINOR: sem RO, P2.4_RM/NC ainda citam "relatórios semanais" e RO_PERIODO fica PENDING_HUMAN;
  5 presenças não traduzidas tratadas como presentes; validador não guarda `empty_value`.

## Golden nº 14 com comparador v2.0 — build JJ (`7e60551`) · **PASS**
Bug do Excel desconectado corrigido (causa: `CoUninitialize` do Word derrubava o apartamento COM
da thread; `office/com_apartment.py` equilibra a contagem; o renderizador reconecta). Build com
**43 páginas = referência**, `ok=True`, nada PENDING; 1º recorte do 2.2 na página da frase de
chamada; negrito só em título/cabeçalho. Comparador v2.0: estrutural 1,0000; conteúdo
1,0000 (440/440 unidades); 0 CRITICAL/MAJOR/MINOR; 48 ALLOWED; Controle de Produtos 3/48/98/149
com todas as linhas iguais; 18 pares de figuras sem branco/troca. Allowances v1.4: +3 exatas
(ALW-14-021 `pending_decision`, -022, -023), todas com anomalia catalogada.
Pendente: rebuild com as mudanças do KK (agente LL) e 2ª rodada do QA independente.
## Golden nº 14 e nº 13 — builder LL (main `7e60551` + JJ + KK) · 2026-10-02
- `pytest -m golden`: os 3 casos de `test_golden_reproduction_against_published_text` falhavam
  por P2.4_PARECERES_MEDICAO (nº 14) e P2.4_PARECERES_AMB (nº 13 e 14): temas por palavra-chave
  (DEC-007, pendência A), não regressão; residuais citam P2.4_PARECERES_MEDICAO_ATESTE_SEM_PA e
  P2.4_PARECERES_AMB_TEMAS_SEM_SUPORTE.
- nº 14 (`14_v4`, v335/v438/v310, emissão 2026-09-08): build `ok=True`, 43 = 43 páginas,
  comparador 2.0 **PASS** (estrutural 1,0; conteúdo 1,0; 0 CRITICAL/MAJOR/MINOR; 48 ALLOWED).
  Allowances **v1.5**: ALW-14-005/-006/-007 removidas (sem uso); nenhuma nova.
- nº 13 (`13_v4`, v134/v328/v289, emissão 2026-08-11): **FAIL**, 66 CRITICAL + 1 MAJOR no
  comparador 2.0. Resíduo além dos 6 CRITICAL da v134 × v162: (a) 18 linhas do Controle de
  Produtos também da versão (descrições NT, status PA-640.1/677.1, PA-683..685.1 sem quebra de
  linha na v134) — provado lendo a v162 em memória; (b) 34 `narrative_facts` + 1
  `narrative_coverage` de anomalias catalogadas do nº 13 → proposta
  `docs/qa/proposals/golden_allowances_v1.6_n13.yaml` (ALW-13-022..026, não congelada);
  (c) **novo, sem anomalia:** NT-688.1 e PA-672.1 cortados (descrição de 3 linhas na altura
  uniforme de 27,6 pt, DEC-010 §4) e ordem do P2.4_BM_EM_ELABORACAO (publicado RD-104 antes de
  RD-102A; modelo ORDER_ALPHA). Com a proposta: 32 CRITICAL = 6 + 18 (versão) + 4 (corte) + 4 (ordem).

## Gate D (nº 14) — 2ª rodada · QA2-D estrutural/visual · **PASS** (STRUCTURAL_CRITICAL 0, VISUAL_MAJOR 0)
Sobre `output/reconstruction/14_v4` (main `4364079`): 43 = 43 páginas; orientação, 22 títulos
(±0,01 cm, exceto o 2.6 que segue o padrão — defeito histórico), sumário (0,00% de diferença),
cabeçalho, rodapé, margens e fontes embutidas idênticos. Os 4 achados da 1ª rodada corrigidos.
MINOR: espessura do 2º filete e tamanhos de fonte da capa; parágrafos introdutórios sozinhos no
pé de página (2.4.2 p29; 2.2 p19/20, este também na referência); células de 3 linhas cortadas
(NT-765.1, NT-734.1 — igual à referência; correção de altura com o MM). Risco registrado:
ALW-14-010/017 não limitam o desvio vertical (a checagem de sobreposição do comparador cobre).

## Gate D (nº 14) — 2ª rodada · QA2-C fontes/conteúdo · **FAIL estrito** (1 descrição truncada)
Recalculado com código próprio: identidade, produtos, Controle de Produtos (6 campos por linha:
2.1 e 2.4 100%; 2.2 47/48), índice 149 (contagem e cobertura 100%; 148/149 descrições), RO/RM/
BM/RI/RA/RCA/NC, resumo, licenças e condicionantes, status do 2.2 × v438, DUP/desapropriação/
interferências — OK. Achados da 1ª rodada: quadro RD-101 corrigido; textos sem fonte e
proveniência corrigidos em parte.
- DIVERGENTE: NT-734.1 com descrição cortada (altura de linha fixa; também no publicado) → MM.
- SEM_FONTE: P2.4_PARECERES_MEDICAO_2 e P2.4_ATAS afirmam temas sem documento → NN.
- Proveniência: GED da cópia local de 22/09 (não v438); inputs humanos fora do manifest;
  caminhos do worktree no manifest → OO (planilha de projetos por versão em memória).

## Gate D (nº 14) — 2ª rodada · QA2-E adversarial · **FAIL**
Todas as 26 mutações da rodada 1 e 42/42 "corpo da página apagado" reprovam; allowances bem
pinadas (nenhuma CONTENT ampla). Mas 19 mutações novas de conteúdo PASSAM: status por extenso no
2.2 ("Aprovado"↔"Não aprovado", "Aprovação"↔"Aceitação", "1º"→"2º nível"), cardinais por
extenso no 2.4 ("oito"→"nove"), negação ("não há"→"há", "não houve"→"houve"), parágrafo < 40
palavras apagado, executora/dia trocados, signatário, e conteúdo de rasters (KPI, "Atualizado
em", célula, troca de painéis 30↔31). Causa: fatos = só dígitos/datas/meses/rodovias; rasters só
por miniatura.
Outros achados: `pending_decision` ignorado pelo parser (ALW-14-004/021 — a decisão RD-102 →
RD-102A já está tomada pela DEC-007: a flag sai e a allowance cita a DEC); ALW-14-013/014/016/
017/018 removíveis; os campos `prog` de `p22_external_status` repetem a planilha de projetos
(3 divergem) → derivar da planilha, não da entrada humana; no nº 15 sintético, P2.4_RO_LEAD sem
RO, P2.1_NO_ACTIVITY contraditório com a agenda e S8 afirmando atividades sem BM.
Correções: comparador v3 (PP), textos (NN: RO_LEAD; QQ: 2.1 e S8; QQ: `prog` derivado).

## Golden nº 14 e nº 13 — builder MM (main `c85959a` + MM) · 2026-10-02
- DEC-010 §4 revista: altura de linha = max(27,6 pt, AutoFit do Excel) (`row_height_mode:
  min_autofit`), paginação pelas alturas reais por linha. Acima do mínimo: nº 14 NT-765.1
  39,6 pt e NT-734.1 41,4 pt (fecha o DIVERGENTE do QA2-C); nº 13 NT-688.1 e PA-672.1 41,4 pt.
  Nenhuma célula corta (teste `office` lê os EXTTEXTOUTW do EMF).
- QA2-D (b): keepNext em P2.4_LAU_HEAD/LEAD e nos títulos de lista do 2.2 (`list_titles`);
  (c) capa: 2º filete com a espessura do 1º (1,31 mm × 1,65 mm na referência; nº 13 1,27 mm),
  título 20,64 pt (ref. 20,66), número 16,68 pt (ref. 16,53).
- nº 14 (`14_mm3`, v335 / projetos v438 em memória / v310, emissão 2026-09-08): `ok=True`,
  **43 = 43 páginas**, comparador 2.0 **PASS** (estrutural 1,0; conteúdo 1,0; 50 ALLOWED). Nova:
  ALW-14-024 (NT-734.1 cortado no publicado, anomalia CONTROLE_PRODUTOS_DESCRICAO_CORTADA).
- nº 13 (`13_mm1`, v134 / projetos v328 em memória / v289, emissão 2026-08-11): 43 = 43
  páginas, **FAIL só pelo resíduo v134 × v162 (GAP-015)**: 24 CRITICAL = 6 (BM-007/008/009.1 da
  RD-104 no 2.4; PA-640.1 e PA-677.1 no índice; anexos 165 × 163) + 18 linhas do Controle de
  Produtos (NT-679/680/692/696/702.1 "Aceitação de Documentos" no 2.2 e ANEXOS; status de
  PA-640.1 e PA-677.1 no 2.4; PA-683/684/685.1 sem quebra de linha no 2.4 e ANEXOS).
  Allowances **v1.6**: ALW-13-022..026 (proposta do LL) + ALW-13-027 (ordem do
  P2.4_BM_EM_ELABORACAO, anomalia P2.4_BM_EM_ELABORACAO_ORDEM; o modelo mantém ORDER_ALPHA).
  ALW-13-004/005/006/007 ficam sem uso (43 = 43).

## Comparador v3.0 integrado (`18268dd`)
Fatos ampliados (status com vocabulário fechado por campo, negação, ordinais/cardinais por
extenso, dia da semana, executoras), cobertura e duplicação por parágrafo, signatário por hash,
rasters por mapa de tinta e grade. 18 das 19 mutações do QA2-E agora reprovam; célula de tabela
dentro de quadro raster continua não verificável sem OCR (xfail estrito; coberta pelo QA de
fonte). `pending_decision` recusada; ALW-14-004/021 citam DEC-007. Controle 14_mm3: PASS
(estrutural 0,9901; conteúdo 1,0). Diferenças reais sem sinalização a tratar no golden final
(agente RR): "aprovados com ressalva" na RD-104; Pavimentação RD-101 de grupo (v436 × v438);
nº 13 com allowances a repinar no formato v3.
## Golden nº 14 e nº 13 — builder RR (main `18268dd`) · 2026-10-02 · nº 14 **PASS**, nº 13 só resíduo v134 × v162
Régua: comparador 3.0 com extrator **3.1** e allowances **v1.8**.
- Extrator 3.1: "aprovado com ressalva(s)" é status próprio (`APROVADO_COM_RESSALVA`) e as
  disciplinas citadas no valor dos campos do 2.2 são fato, como conjunto por campo
  (`discipline:PAVIMENTACAO@DISCIPLINAS PENDENTES DE APROVACAO`). Comparador: `order` só dentro
  do mesmo bloco de rodovia (o "aprovados" a mais da RD-104 era emparelhado com o predicado
  repetido da RD-101).
- (a) Ressalva: a Projetos v438 distingue por disciplina (10 "Aprovado com ressalva(s)"; RD-104
  Geométrico "Aprovado", Terraplenagem com ressalva), mas o texto do nº 13 e do nº 14 só
  qualifica na frase da RD-104, aplicada também ao Geométrico; nos nº 11–12 o texto qualificava.
  O modelo mantém `templates.approval.reservation_qualifier` (não qualificar; o 2º nível está no
  quadro). Anomalia P2.2_APROVADOS_COM_RESSALVA_GENERALIZADO (nº 13 e 14) + par exato
  (ALW-14-031, ALW-13-037). **Decisão pendente da Emmily:** qualificar por disciplina é mudança
  de padrão (nova versão do modelo; ≈10 linhas a mais por mês).
- (b) Pavimentação da RD-101: ALW-14-032 (P2.2_PAVIMENTACAO_RD101_STATUS_DEFASADO, 2 itens).
- (c) Os 3 "Em análise" da ALW-14-029 casam como pares.
- nº 14 (`14_final`, v335 / projetos v438 em memória / v310, emissão 2026-09-08): `ok=True`,
  43 = 43 páginas, **PASS** (estrutural 0,9901; conteúdo 1,0000; 66 ALLOWED; 2 MINOR das fontes
  da capa).
- nº 13 (`13_final`, v134 / v328 em memória / v289, emissão 2026-08-11): 43 = 43 páginas,
  estrutural 1,0000, conteúdo 0,9602, **24 CRITICAL = só o resíduo v134 × v162** (GAP-015),
  nenhuma allowance sem uso. ALW-13-022..027 repinadas para itens/pares; TRUE_MODEL_CHANGE
  "em revisão" -> "pendentes de aprovação" e linhas de pendentes/não entregues catalogadas.

## Gate D (nº 14) — 3ª rodada · QA3-D estrutural/visual · **PASS** (STRUCTURAL_CRITICAL 0, VISUAL_MAJOR 0)
Sobre `output/reconstruction/14_final` (`dd5377a`): 43 = 43 páginas, sumário, 22 títulos,
cabeçalho, rodapé, margens, orientação idênticos; recortes do Controle de Produtos com largura,
fonte e passo constantes, 3/48/98/149 linhas, nenhuma célula cortada (a referência tinha 4);
filetes da capa com a mesma espessura; parágrafos introdutórios presos ao item seguinte.
MINOR: novo órfão "Referente aos Relatórios de Controle Ambiental:" (P2.4_RCA_HEAD, p31);
largura da 2ª linha do título da capa (+0,40 cm). Risco: `figure_bbox` sem número de página
(ALW-14-017 larga) — melhoria do comparador registrada.

## Gate D (nº 14) — 3ª rodada · QA3-C fontes/conteúdo · **PASS** (CONTENT_100 SIM · ANNEX_100 SIM)
181 fatos recalculados com código próprio (sem importar builder/render/sources; v438 lida em
memória): 180 OK e 1 MINOR de proveniência (fundo da capa referenciado por caminho efêmero do
worktree; sha1 registrado). Controle de Produtos 3/48/98 (6 campos por linha) e índice 149 100%;
encerramento; RO/RM/BM/RI/RA/RCA/NC; resumo (cada tema com documento); licenças e condicionantes
× v310; status do 2.2 15/15 × v438; Análise Programa 12/12; painéis por leitura visual. Todos os
achados das rodadas 1 e 2 corrigidos. 45 frases novas em relação ao publicado, todas com fonte.
Divergências do publicado = 15 anomalias catalogadas, corrigidas no gerado.
Risco registrado: golden com Lista Mestra v335 (DEC-012 pede v331, estado estável v326–v414).

## Gate D (nº 14) — 3ª rodada · QA3-E adversarial · **FAIL**
59/60 mutações antigas e 84/84 varreduras reprovam (a restante é a célula de raster, xfail
documentado). Das 49 mutações novas, 13 de conteúdo crítico passam: valores de status externos
do 2.2 fora do vocabulário ("Aguardando aceite"→"Publicada", GDP "Solicitado"→"Dispensado"),
quantificadores ("Todas"→"Nem todas", "algumas"↔"apenas uma"), verbos de estado ("analisado"→
"devolvido", "semanais"→"quinzenais"), item de lista curto apagado, sumário alterado. ALW-14-031
é circular (a anomalia descreve a própria regra do modelo) e permite perder um fato verdadeiro
("com ressalva" da Terraplenagem RD-104 na v438). Vazamento nº 15: nenhum.

**Mudança de abordagem do orquestrador.** Três rodadas mostraram que comparar "fatos
reconhecidos" por vocabulário sempre deixa lacunas. O comparador v4 passa a fazer **diff de
texto estrito por parágrafo** (normalizado), em que TODA palavra divergente é diferença; as
diferenças legítimas (padronização DEC-007, anomalias corrigidas) ficam num conjunto de
**hunks aprovados**, congelado, cada hunk com a anomalia ou DEC que o justifica. Qualquer
mutação gera hunk novo e reprova. O conjunto de hunks é o que a Emmily revisa na certificação.
A ressalva passa a ser qualificada por disciplina (fato da planilha; padrão dos nº 11–12),
modelo v0.13, com a generalização de agosto catalogada como anomalia.

## Comparador v4.0 integrado (`7a815de`) — diff de texto estrito + hunks aprovados
Diff token a token por seção (capa, sumário, títulos, corpo, células do Controle de Produtos);
`toc_consistency` não permitível; hunk que volta ao texto publicado num ponto aprovado =
CRITICAL `reverted`. Hunks aprovados congelados (sha256) em `docs/qa/approved_hunks/`:
nº 14 = 105 (58 DEC-007; 11 ressalva DEC-015; demais por anomalia catalogada), 0 sem
justificativa; nº 13 = 115. Allowances v1.9 só de geometria/estrutura. 207 mutações do
catálogo reprovam (3 pinturas dentro de raster: xfail estrito, sem OCR); varredura de 200
palavras trocadas: 100% reprovam. Controle 14_v5: PASS. 13_v5: reprova só pelos 23 hunks do
resíduo v134×v162 (não aprovados). Página a mais do nº 13 = paginação legítima pela ressalva
(ALW-13-039/040/041, DEC-015). Pendente: 4ª rodada de QA independente.

## Gate D (nº 14) — 4ª rodada · QA4-H auditoria dos hunks aprovados · **PASS com ressalvas**
nº 14: 105 hunks → 94 OK, 0 gerado errado, 0 justificativa inadequada, 0 perda de informação,
11 DECISÃO_EDITORIAL (corte de narrativa sem documento: HNK-14-005/007/010/090/092/093/095;
ressalva parcial em grupo todo aprovado: 058–060; frase de valor vazio: 074). Conferidos contra
v331/v438: ressalvas 10/10, pendentes, RO, BM, RA, NT-734.1.
nº 13 (amostra 30): 23 OK; HNK-13-020 PERDA (cláusula "Foram tratadas disciplinas…" — a regra
vigente de agosto é não emitir: justificativa deve ser TRUE_MODEL_CHANGE, não a anomalia
citada); família HNK-13-002–013/114–115 (paginação de 44 páginas) com justificativa
inadequada (DEC-015 não trata de paginação) → allowance de leiaute própria.
Fora dos hunks (iguais nos dois lados, a corrigir no gerado): "Referente as" sem crase (DEC-007);
a matriz da Análise Programa diz "Aprovado" onde o corpo diz "aprovado com ressalva" (inconsistência
interna do gerado — mapeamento do `prog` derivado).

## Gate D (nº 14) — 4ª rodada · QA4-E adversarial · **FAIL** (1 BLOCKS_GATE)
Catálogo: 207/207 mutações reprovam (3 xfail de raster documentados), varredura 100%, controle
14_v5 PASS. Ataques novos: dentro de hunk (gerado exato), trocas entre rodovias de dias,
condicionantes, desapropriação e RO, figuras, sumário/rodapé, YAML editado, cabeçalho/rodapé,
assinatura, texto do EMF — todos reprovam.
- BLOCKS_GATE: mover a ressalva da DUP entre rodovias (RD-103 → RD-102A) passa — a âncora do
  hunk é o hash do parágrafo, idêntico nas 3 rodovias, e `_cover_by_hunks` rebaixa os
  `narrative_facts` do v3 que acusavam a troca.
- MAJOR (registrado): texto coberto/branqueado no PDF (o extraído não muda); integridade dos
  hunks depende do Git (sha editável junto); `--approved-hunks` sem conferência de sha;
  conteúdo de rasters coberto só pelo QA de fonte (leitura visual).
Correções: agente WW (âncora posicional, v3 não suprimido por hunk, sha no CLI); XX (achados do
QA4-H fora dos hunks). Pelo critério de convergência, a verificação seguinte é focada.

## Comparador v4.1 integrado (`17e0f0d`) e controles v6
Âncora posicional dos hunks (bloco, índice do parágrafo, tokens) — fecha o BLOCKS_GATE do QA4-E
(ressalva movida entre rodovias reprova; varredura de realocação 154/154); diferenças julgadas
pelo próprio hunk (sem cascata por seção); `--approved-hunks` confere sha; checagem de
visibilidade do texto (branqueado/coberto reprova; 0 falso positivo nos controles). Hunks v1.2:
nº 14 = 113 (105 + 8 do v6: crase e Análise Programa com ressalva), nº 13 = 117. Allowances v1.10.
Build 14_v6 (modelo 0.14): 43 = 43 páginas, ok, nada pendente; comparador v4.1 **PASS**.
13_v6: reprova só pelo resíduo v134×v162. Próximo: verificação focada (critério de convergência).

## Gate D (nº 14) — verificação focada QA5 · 2026-10-04 · **PASS**
Sobre o controle `output/reconstruction/14_v6` (modelo 0.14, comparador v4.1, 113 hunks):
1. BLOCKS_GATE do QA4-E fechado: 11/11 realocações (ressalva RD-103/RD-104 → RD-102A, trocas
   novas na matriz Programa) e 3/3 movimentos intra-bloco reprovam; varredura 154/154.
2. Hunks HNK-14-106..113 corretos contra a v438 (lida em memória); matriz Programa coerente com o
   corpo do 2.2 nas 12 entradas.
3. Sem cascata: remover um hunk gera só a diferença dele; 1 palavra injetada = 1 CRITICAL.
4. Visibilidade: 9/9 ocultações reprovam; 0 falso positivo no controle.
5. `test_qa_golden_mutations` verde; `test_qa_golden_v4` sem F/E (realocação 154/154, palavras
   200/200, 3 xfail de raster) — linha de resumo truncada pelo tempo do processo (MEDIUM-HIGH).
6. 14_v5 → 14_v6: exatamente os 8 hunks novos; 43 = 43 páginas.
Nenhum BLOCKS_GATE novo. **Gate D PASS para o Relatório G2 nº 14 — Agosto/2026.**
Pendências MAJOR registradas: cobertura parcial de palavra (um dígito/sílaba) não detectada;
isenção "invisível também na referência" permite cobrir a data da capa; ordem de códigos
empatados em `themes` do manifest não determinística (MINOR). Gate D do nº 13 (temporal)
continua bloqueado pela Lista Mestra v162 (GAP-015).
