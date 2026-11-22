# DEC-015 — A ressalva da aprovação é fato da planilha, qualificada por disciplina

**Data:** 2026-10-02 · **Status:** ACEITA (técnica, orquestrador; revisável pela Emmily) ·
**Confiança:** HIGH · **Modelo:** G2_REPORT_MODEL 0.12 → 0.13 (`model.changelog`)

## Contexto
O QA3-E (Gate D, 3ª rodada; `docs/qa/GATES.md`) mostrou que o ALW-14-031 era circular: a
anomalia `P2.2_APROVADOS_COM_RESSALVA_GENERALIZADO` usava como `expected_value` a própria regra
do modelo (`templates.approval.reservation_qualifier`: "não qualificar"), e com isso o golden
aceitava perder um fato verdadeiro (o "com ressalva" da Terraplenagem da RD-104 na v438).

Evidência:
- **Planilha:** `Projetos!S` (Status AVALIAÇÃO) distingue a ressalva por disciplina nas 128
  versões lidas (v290 a v442): "Aprovado com ressalva", "Aprovada com ressalva", "Aprovado com
  ressalvas", "Aprovado com Ressalvas". v438 (golden do nº 14) = 10 disciplinas com ressalva nas 4
  rodovias; v328 (golden do nº 13) = 13. Na RD-104, Viário Principal, o Geométrico é "Aprovado" e
  a Terraplenagem "Aprovado com ressalva" nas duas versões.
- **Relatório G2 nº 12 — Junho/2026:** 6 de 6 linhas de Aprovação com disciplinas com ressalva a
  qualificam por disciplina, em frase própria ("Aprovação: encontram-se aprovados o … . Os …
  encontram-se aprovados com ressalva"; "… encontra-se aprovado com ressalva"); nas 4 linhas
  mistas, as aprovadas vêm antes; qualificador "com ressalva" no singular em 6 de 6.
- **Relatório G2 nº 11 — Maio/2026:** 1 ocorrência, também por disciplina ("o qual se encontra
  aprovado parcialmente com ressalvas").
- **Relatórios G2 nº 13 e nº 14:** uma só frase qualifica, idêntica nos dois meses, estendida ao
  Geométrico (que não tem ressalva); as demais aprovações com ressalva (12 na v328, 9 na v438)
  saem sem qualificador, inclusive sob "Todas as disciplinas encontram-se aprovadas".

Não há snapshot da planilha dos nº 11 e nº 12 (a 1ª versão lida é de 06/08/2026): a **forma** é
medida no texto dos nº 11–12; o **fato** é medido na planilha.

## Decisão
1. `templates.approval.reservation_qualifier.value = per_discipline`
   (`config/data_rules/p22_highway_block.yaml`). Uma disciplina aprovada é "com ressalva" quando
   o Status (AVALIAÇÃO) normalizado começa com "aprovad" e contém `marker` ("ressalva").
2. Redação (padronizada, DEC-007), em `templates.approval.with_reservation`:
   - sem ressalva no grupo: as formas da v0.12, sem mudança;
   - mistas: aprovadas (universal, plural ou singular) + `". "` + as com ressalva, com inicial
     maiúscula — ex.: "Aprovação: o Projeto Geométrico e Interseções encontra-se aprovado. O
     Projeto de Terraplenagem encontra-se aprovado com ressalva;";
   - só com ressalva: "Aprovação: o … encontra-se aprovado com ressalva;" / "… encontram-se
     aprovados com ressalva;";
   - grupo todo aprovado, parte com ressalva (fora da OAE): "Aprovação: Todas as disciplinas
     encontram-se aprovadas. A … encontra-se aprovada com ressalva;";
   - grupo todo aprovado e todo com ressalva (não observado): "Aprovação: Todas as disciplinas
     encontram-se aprovadas com ressalva;".
3. A generalização dos nº 13–14 é a anomalia `P2.2_APROVADOS_COM_RESSALVA_GENERALIZADO`
   (`should_learn_as_rule=false`), com `expected_value` = fato da planilha por disciplina
   (`scripts/08_record_anomalies.py`), sem citar regra do modelo.
4. Mudança de regra dentro de componente MEDIUM (`P2.2_DISCIPLINE_STATUS`): o modelo vai a 0.13
   e mantém `BUILDER_READY`.

## Pontos para a revisão da Emmily
- **Grupo todo aprovado com ressalva parcial:** adotado "Todas … aprovadas" + frase da ressalva
  (padrão vigente do grupo todo aprovado, 4 ocorrências no nº 13 e 5 no nº 14). Alternativa medida
  no nº 12 (RD-102A, Fase de Estudos, 8 de 8): enumerar as aprovadas e depois as com ressalva.
- **"aprovado parcialmente com ressalvas"** (nº 11 e nº 12, Estudos Geotécnicos): não é valor de
  `Projetos!S` em nenhuma versão lida; não reproduzido.
- **Matriz da Análise Programa** (`inputs.p22_external_status.schema.derived.prog`): na v0.13
  continuava "Aprovado" para "Aprovado com ressalva(s)". **Estendida no modelo 0.14** (adendo
  abaixo).

## Adendo 2026-10-02 — matriz da Análise Programa (modelo 0.13 → 0.14, QA4-H)
O QA4-H achou uma inconsistência interna do gerado: a matriz dizia "Aprovado" onde o corpo do 2.2
dizia "aprovado com ressalva" para a mesma disciplina. O campo `prog` ganha o conjunto
`approval_with_reservation` (1º de `status_text`), calculado pela **mesma** regra do bloco por
rodovia (`templates.approval.reservation_qualifier`; com `value: none` nenhum dos dois qualifica):
"Aprovado com ressalva"; nas interferências, "Aprovado com ressalva e encaminhado a GFD" — na
v438 as 2 interferências aprovadas (RD-103, RD-101) são "Aprovado com ressalvas" e o nº 14 as dá
por encaminhadas, logo o encaminhamento independe da ressalva. O "Aprovado" publicado para as 6
aprovações com ressalva das matrizes da v438 é a anomalia `P2.2_EXTERNAL_PROG_RESSALVA_OMITIDA`.
Teste de coerência: `tests/test_p22_external.py::test_matrix_and_body_give_the_same_status_to_the_same_discipline`
(sintético) e o golden v438 do mesmo arquivo.

## Consequências
- O golden de texto do 2.2 com a v438 tem a ressalva nas 10 disciplinas da planilha, e só nelas;
  o comparador estrito (QA v4) vê hunks novos nas linhas de Aprovação do nº 13 e do nº 14, que
  devem ser justificados por esta DEC e pela anomalia (conjunto de hunks aprovados: QA, fora
  deste builder).
- `reservation_qualifier.value = none` restaura a forma v0.12 (só para comparação).
