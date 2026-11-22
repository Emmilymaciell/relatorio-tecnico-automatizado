# DEC-012 — Snapshot das fontes pelo instante de publicação, não pela data da capa

**Data:** 2026-10-01 · **Status:** ACEITA (técnica, autopilot) · **Confiança:** HIGH ·
**Revê:** DEC-008 (o critério "fim do dia da emissão" deixa de valer)

## Contexto
DEC-008 escolhia a última versão da Lista Mestra com `lastModifiedDateTime` até o fim do dia da
data de emissão da capa. A revisão adversarial mostrou que o critério falha em julho, e a
varredura de 430 versões (`docs/discovery/WAVE1_FINDINGS.md` §M) mostrou por quê: o PDF de
julho foi gerado três dias depois da data da capa. O mesmo vale para a planilha ambiental,
cuja referência é o refresh do Power BI ("Atualizado em", §B).

## Decisão
1. **Reconstrução histórica (golden test):** para cada fonte, usa-se a última versão com
   `lastModifiedDateTime <=` instante de referência da fonte:
   - Lista Mestra e planilha de projetos: `CreationDate` do PDF publicado (na falta dele,
     `dcterms:modified` do DOCX);
   - planilha ambiental: instante "Atualizado em" impresso no painel.
   Valores provados: Lista Mestra julho = v162, agosto = v331; ambiental julho = v289,
   agosto = v310.
2. **Produção mensal:** o snapshot é o estado da fonte no instante da geração. O manifesto da
   execução registra `version_id` e `lastModified` de cada fonte, para tornar o relatório
   reprodutível depois.
3. **Duas seleções sobre a Lista Mestra** (achado de julho):
   - `body_rows` = `N° Relatório == n` (todas, inclusive "Em elaboração") → Controle de
     Produtos dentro de cada produto;
   - `index_rows` = `body_rows ∧ Status Entrega == "Entregue"` → índice de ANEXOS e total de
     anexos do encerramento. Coluna do filtro: MEDIUM até um mês em que Status e Data
     Entrega divirjam.

## Consequências
- `historical_reconstruction.validated` passa a `["2026-07", "2026-08"]`; julho volta a ser
  candidato ao golden test temporal.
- O DEC-008 acertou agosto (v335) por estabilidade da planilha, não pelo critério: registrado
  como anomalia de método, não como regra.
- Os snapshots só existem no histórico de versões do SharePoint, que é finito. Persistir uma
  cópia local é download e depende de autorização da Emmily; sem ela, o golden test lê as
  versões em memória a cada execução.
