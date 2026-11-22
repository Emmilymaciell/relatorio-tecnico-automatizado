# DEC-003 — Identidade canônica `(drive_id, item_id)` e catálogos JSONL com evidência obrigatória

**Data:** 2026-09-21 · **Status:** ACEITA

## Contexto
Pastas mensais e arquivos do SharePoint são renomeados e movidos. Caminho textual quebra.
A descoberta vai produzir milhares de afirmações (componentes, linhagem, anomalias, páginas) que
precisam ser rastreáveis, revisáveis por humano e legíveis por código.

## Decisão
- Identidade de qualquer arquivo/pasta do SharePoint é `(drive_id, item_id)`. Caminho, nome e
  URL são atributos descritivos; nenhuma chave, filtro ou regra depende deles.
- Catálogos em `data/catalog/*.jsonl` (uma linha = um registro pydantic de
  `prog_g2_report.catalog`): `components`, `source_lineage`, `anomalies`, `pages`.
  JSONL porque é append-only, diff-ável no Git e legível sem ferramenta.
- Todo registro carrega `evidence` (Relatório G2, página, `source_ref`, trecho) e `confidence`
  (CONFIRMED / HIGH / MEDIUM / LOW / UNKNOWN). `Anomaly.should_learn_as_rule` é `False` por
  padrão e nada no gerador poderá ler anomalias como regra.
- Esquemas JSON para validação externa serão exportados dos modelos pydantic para
  `data/schemas/` quando a Fase 3 começar a popular os catálogos (não antes, para não criar
  arquivo sem uso).

## Evidência
- Briefing, seções 10, 13, 16, 17, 28.
- Precedente: `PROG_Cerebro_Documental` DEC-015 (identidade por `drive_id + item_id`).

## Alternativas consideradas
- SQLite/DuckDB desde já: mais poder de consulta, pior diff no Git e pior leitura humana na
  fase de descoberta. Pode entrar como *derived* mais tarde, gerado a partir dos JSONL.
- YAML por componente: bom para leitura, ruim para milhares de registros. Rejeitado para catálogo;
  continua adequado para configuração (`config/*.yaml`, `state/sharepoint_ids.yaml`).

## Consequências
- Scripts de inventário gravam `drive_id`/`item_id` sempre; caminho vai junto só para leitura.
- Revisar um catálogo é ler um diff.
