# DEC-006 — A Lista Mestra é o manifesto; a seleção é pelo campo `N° Relatório`

**Data:** 2026-09-22 · **Status:** ACEITA

## Contexto
O briefing levantou como hipótese central que a inclusão de um documento no Relatório G2 não é
decidida pela data de entrega, e proibiu explicitamente usar "data dentro do mês" como critério.
A Fase 3 testou isso contra os Relatórios G2 nº 11 a nº 14 (Maio a Agosto/2026).

## Decisão
1. A **Lista Mestra** (`00_ Lista mestre.xlsx`, aba `Controle Geral`) é o **manifesto** do
   Relatório G2. Nada entra no relatório que não esteja nela.
2. A regra de seleção é, e será implementada como, exatamente isto:
   `documentos(relatório N) = linhas onde "N° Relatório" == N`.
   Sem filtro por data, por `Status Entrega` ou por empresa.
3. O campo é **lido**, nunca inferido. Ele é preenchido manualmente e a posteriori.
4. A contagem de anexos do Encerramento é `COUNT(linhas)` com esse mesmo filtro — não o número
   de arquivos na pasta.
5. A data de fechamento entra como **validação**, não como seleção: nenhum documento deveria ter
   data de entrega posterior à emissão do relatório. Essa checagem teria detectado as cinco
   notas técnicas anômalas de agosto.
6. Identidade da Lista Mestra por `(drive_id, item_id)`, como manda a DEC-003. O nome do arquivo
   é "Lista mestre", não "Lista Mestra".

## Evidência
- **Correspondência perfeita** entre linhas da Lista Mestra e arquivos anexados: 149/149 no
  relatório nº 11, 122/122 no nº 12, 165/165 no nº 13. No nº 14, 149 de 154.
- **Contraexemplo direto contra a regra de data:** `PA-726.1`, entregue em 01/09/2026, pertence
  ao relatório nº 14; `PA-728.1`, entregue em 02/09/2026, pertence ao nº 15. Prever pelo mês
  civil acerta apenas 90% dos casos.
- **Contraexemplo contra o filtro de status:** quatro documentos "Em elaboração" no relatório
  nº 12 estão anexados.
- **Contagem de anexos:** junho declara 122 e a lista tem 122; julho declara 165 e tem 165;
  agosto declara 149, e a lista tem 154 menos as 5 lançadas após a emissão.
- Detalhamento em `docs/discovery/SOURCE_LINEAGE.md` e `data/catalog/source_lineage.jsonl`.

Confiança: **CONFIRMED**.

## Alternativas consideradas
- **Selecionar por mês da data de entrega.** Rejeitada por contraexemplo: em agosto, 30 dos 154
  documentos foram entregues em setembro. Perderia um quinto do relatório.
- **Filtrar por `Status Entrega = Entregue`.** Rejeitada: documentos "Em elaboração" foram
  anexados no relatório nº 12.
- **Contar anexos pelos arquivos da pasta.** Rejeitada: o número físico é sempre maior, porque
  um documento pode virar uma pasta com várias peças.

## Consequências
- O gerador precisa de acesso de leitura à Lista Mestra em toda execução mensal.
- **A Lista Mestra é um documento vivo e editado retroativamente.** O relatório é um instantâneo
  dela na data de emissão. Reconstruir um relatório antigo do zero (Fase 8) pode não reproduzir
  o original, e a diferença deve ser tratada como limitação conhecida, não como defeito do
  gerador. Se a fidelidade histórica for exigida, será preciso recuperar a versão da planilha
  daquela data pelo histórico de versões do SharePoint.
- A grafia da coluna `Manifestação` tem duas variantes de caixa, o que afeta qualquer
  agrupamento por tipo. Normalizar na leitura.
