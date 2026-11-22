# DEC-008 — Golden test histórico usa o snapshot da Lista Mestra, não a planilha de hoje

**Data:** 2026-09-27 · **Status:** ACEITA · **Confiança:** CONFIRMED

## Contexto
A DEC-006 estabeleceu que a Lista Mestra é o manifesto do Relatório G2. A Fase 3 observou que
ela é editada retroativamente, e registrou como limitação que um relatório reconstruído poderia
não reproduzir o original. O sprint de 2026-09-27 testou isso contra o histórico de versões do
SharePoint, em leitura pura.

## Achado
O SharePoint guarda **464 versões** da Lista Mestra, a mais antiga de 2026-07-20.

Comparando a versão vigente na data de emissão de cada relatório com a planilha atual:

| Relatório | Emitido | Versão usada | Documentos então | Hoje | Veredito |
|---|---|---|---|---|---|
| nº 13 — Julho/2026 | 11/08/2026 | v134.0, de 11/08 | 148 | 148 | **idêntico** |
| nº 14 — Agosto/2026 | 08/09/2026 | v335.0, de 08/09 | **135** | 140 | 5 entraram depois |
| nº 11 — Maio/2026 | 09/06/2026 | — | — | — | sem versão anterior |
| nº 12 — Junho/2026 | 07/07/2026 | — | — | — | sem versão anterior |

As cinco que entraram depois são exatamente `NT-798.1`, `NT-799.1`, `NT-800.1`, `NT-805.1` e
`NT-806.1`, as mesmas já identificadas na Fase 3.

**A prova decisiva:** cruzando os códigos do Controle de Produtos do PDF de agosto com a Lista
Mestra **na versão de 08/09**, o resultado é 135 contra 135, **zero divergências nos dois
sentidos**. Com o snapshot correto, agosto tem a mesma correspondência perfeita de julho.

## Decisão
1. **Reconstrução histórica usa o snapshot da Lista Mestra vigente na data de emissão**, obtido
   pelo histórico de versões, nunca a planilha atual.
2. O critério de associação é: **a última versão cujo `lastModifiedDateTime` seja anterior ou
   igual ao fim do dia da emissão**, sendo a data de emissão a que consta na capa do relatório.
3. A leitura de versões é feita por `GraphReadOnlyClient.read_version_bytes()`, acrescentada à
   allowlist como operação de leitura. **Nada é restaurado**: a versão atual do arquivo não muda.
4. Snapshots ficam em `tmp/historical_sources/`, fora do Git, e são descartáveis.
5. Metadados das versões em `data/catalog/master_list_versions.jsonl`; comparação em
   `state/history_comparison.yaml`.

## Consequências
- **A limitação registrada na DEC-006 está resolvida para julho e agosto.** A divergência não
  era da planilha nem do relatório: era de método, por comparar com a versão errada.
- **Maio e junho não podem ser validados por esta via**: o histórico começa em 20/07/2026. As
  divergências daqueles meses (documentos publicados que hoje estão atribuídos ao relatório
  seguinte) permanecem `UNRESOLVED`, com causa provável idêntica.
- **O golden test deve preferir julho ou agosto**, que têm snapshot verificável. Reconstruir
  maio ou junho carrega incerteza que não vem do gerador.
- O histórico é finito. Se o SharePoint podar versões antigas, a janela de validação encolhe.
  Vale extrair os snapshots relevantes enquanto existem.
