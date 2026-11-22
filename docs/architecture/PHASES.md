# Fases do projeto

Fonte: briefing inicial da Emmily (2026-09-21). Situação atualizada em `STATE.md`.

| # | Fase | Entregas principais | Saída de fase |
|---|---|---|---|
| 0 | Bootstrap | repo, Git, estrutura, CLAUDE/README/STATE, `.gitignore`, `.env.example`, pyproject, config, subagentes, proteções, testes | commit `chore: bootstrap ...` |
| 1 | Acesso read-only | auth por client secret (DEC-004), resolver site/drive, operação read-only verificada, enumeração mínima, testes | `state/sharepoint_ids.yaml` |
| 2 | Inventário | pastas G2 por mês, relatórios históricos, Lista Mestra, famílias de documentos, catálogo por metadados (sem interpretar) | `data/catalog/inventory*.jsonl` |
| 3 | Arqueologia | nº 01 a nº 14: estrutura, evolução, componentes, anomalias, regras candidatas, modelo atual | `docs/discovery/*`, `components.jsonl`, `anomalies.jsonl`, `pages.jsonl` |
| 4 | Linhagem de fontes | para cada componente variável: fonte, transformação, regra de seleção, evidência, confiança | `SOURCE_LINEAGE.md`, `source_lineage.jsonl` |
| 5 | Especificação | `docs/specs/` (REPORT, VISUAL, CONTENT_RULES, SOURCE_RULES, IMAGE_RULES, ANNEX_RULES, TEXT_PATTERNS) + machine-readable (`config/report_spec.yaml` ou equivalente, decidido após descoberta) | modelo `CANDIDATE` |
| 6 | Revisão com a Emmily | descobertas, lacunas, perguntas agrupadas, confirmação | modelo `FROZEN` |
| 7 | Builder | gerador do zero (`Document()` vazio), determinístico onde possível, IA só onde necessária; tecnologia escolhida após análise dos DOCX (DEC) | `src/prog_g2_report/builder/` |
| 8 | Reconstrução histórica | reconstruir um Relatório G2 existente do zero com as fontes daquele mês; DOCX + PDF | `output/reconstruction/nº NN/` |
| 9 | QA iterativo | QA estrutural, conteúdo, fontes, visual (render, overlay, diff), anexos; métricas + diagnóstico; correções | `docs/qa/` |
| 10 | Certificação | aprovação da Emmily → `G2_REPORT_MODEL version 1.0 status CERTIFIED` | tag |
| 11 | Produção mensal | novo Relatório G2 usa modelo certificado; só investiga informações novas; mudança permanente = nova versão do modelo | `output/nº NN/` |

## Portões
- Nada de builder antes da Fase 6 concluída.
- Subagentes `docx-engineer` e `qa-critic` só são criados quando a Fase 7 começar.
- Golden test (Fase 8/9): o Relatório G2 de referência **nunca** é aberto como template; só comparado no fim.

## Metas de QA (Fase 9)
- Fidelidade visual estrutural ≥ 95% (divergência ≤ 5%), separando antialiasing/renderizador de erro estrutural.
- Fatos, fontes, anexos, número do Relatório G2, mês, rodovias, documentos e ordem estrutural: 100%.
- Métricas + diagnóstico, nunca só um score.
