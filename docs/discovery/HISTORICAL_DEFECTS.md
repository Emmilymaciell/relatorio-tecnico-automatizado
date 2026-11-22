# Defeitos históricos dos relatórios G2

Relatórios históricos **não são autoridade absoluta**. Este documento registra erros humanos
observados nos Relatórios G2 (copy-forward, typo, data incompatível etc.) para que o gerador **nunca**
aprenda um erro como regra. Registro estruturado: `data/catalog/anomalies.jsonl`
(modelo `Anomaly`, sempre `should_learn_as_rule=false`).

## Classificação
| Classe | Significado |
|---|---|
| `HISTORICAL_DEFECT` | Erro no relatório publicado, causa não específica |
| `COPY_FORWARD_ERROR` | Valor herdado do mês anterior sem atualização (nº do Relatório G2, mês, ano, data) |
| `TYPO` | Erro de digitação/ortografia |
| `FORMAT_VARIATION` | Variação de forma sem mudança de modelo (espaçamento, maiúsculas, pontuação) |
| `TRUE_MODEL_CHANGE` | Não é defeito: mudança intencional de padrão a partir de um Relatório G2 |
| `UNRESOLVED` | Não foi possível decidir com a evidência disponível |

## Hipóteses fornecidas pela Emmily (a verificar independentemente)
Observadas por ela em análise externa; **nenhuma confirmada ainda por este projeto**:
- ano anterior aparecendo no encerramento;
- número do relatório anterior aparecendo na apresentação;
- mês incorreto em texto;
- data de assinatura incompatível com o período;
- número declarado de páginas incompatível com o real.

## Registro
| Relatório G2 | Página | Componente | Observado | Esperado | Classe | Confiança | Evidência |
|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | (nenhum registro ainda; Fase 3) |

## Regra de uso
1. Uma anomalia só entra aqui com evidência citada (Relatório G2, página, trecho).
2. Se um valor divergente se repetir em **todos** os Relatórios G2 recentes de forma consistente, avaliar
   `TRUE_MODEL_CHANGE` antes de chamar de defeito — e vice-versa.
3. O gerador lê `components.jsonl` e `specs/`; **nunca** lê `anomalies.jsonl` como fonte de regra.
