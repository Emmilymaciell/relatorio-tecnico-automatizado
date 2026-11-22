# DEC-005 — Duas árvores mensais: qual é autoridade para quê

**Data:** 2026-09-22 · **Status:** ACEITA

## Contexto
O inventário da Fase 2 (ver `docs/discovery/INVENTORY.md`) mostrou que o acervo do G2 tem duas
árvores mensais paralelas, com conteúdos diferentes e cobertura diferente:

| Árvore | Caminho | Conteúdo | Meses |
|---|---|---|---|
| produção | `3. Desenvolvimento/G2 -  Engenharia/_Produto/NN. Mês AAAA/` | DOCX de trabalho, PDF, assinados | nº 01 a nº 14 |
| entregas | `4. Produtos/NN. Mês AAAA/G2/` | PDF entregue + `Anexos/` por produto | nº 07 a nº 18 |

Alguns Relatórios G2 têm o mesmo relatório nas duas árvores, e alguns têm mais de um arquivo por extensão
(nº 13 com dois DOCX, nº 09/nº 10/nº 12 com PDF duplicado ou "assinado"). Sem uma regra explícita,
cada análise futura escolheria um arquivo diferente e os resultados não seriam comparáveis.

## Decisão
1. **Evidência estrutural** (seções, estilos, geometria, âncoras de imagem, campos) vem do
   **DOCX da árvore de produção**. É a única fonte que cobre nº 01 a nº 14.
2. **Referência visual** (o que o leitor vê, paginação, render) vem do **PDF**, preferindo o da
   árvore de **entregas**, que é o que foi efetivamente entregue. Onde não houver PDF de entrega
   (nº 01 a nº 06), usa-se o PDF de produção; onde não houver PDF nenhum (nº 01 a nº 05), a análise
   visual daquele mês fica registrada como indisponível, não é substituída pelo DOCX.
3. **Anexos e a composição do Relatório G2** vêm da árvore de **entregas** (`G2/Anexos/`), que só existe de
   nº 07 em diante. Para nº 01 a nº 06 a composição de anexos é UNKNOWN por esta via.
4. Quando houver mais de um arquivo candidato no mesmo papel, a ordem é: **assinado > sem sufixo
   de revisão > mais recente por `lastModifiedDateTime`**. A escolha efetiva de cada Relatório G2 fica
   registrada em `data/catalog/report_corpus.jsonl`, não embutida em código.
5. O número do Relatório G2 é lido do **nome do arquivo** e conferido contra o **prefixo da pasta**. Hoje
   batem em 14 de 14; se divergirem no futuro, o registro guarda os dois e a divergência vira
   anomalia, sem que o código escolha sozinho.

## Evidência
- `state/inventory_summary.yaml` e `state/corpus_summary.yaml` (gerados em 2026-09-22).
- `data/catalog/report_corpus.jsonl`: 14 registros, todos com DOCX; `without_pdf` = nº 01 a nº 05;
  `folder_name_mismatch` = vazio.

## Alternativas consideradas
- **Usar só a árvore de entregas.** Rejeitada: perde nº 01 a nº 06 inteiros e todo o DOCX, que é a
  evidência estrutural.
- **Usar só a árvore de produção.** Rejeitada: os anexos, que definem a composição do Relatório G2, só
  existem em entregas.
- **Escolher por caminho fixo em código.** Rejeitada: caminho é mutável (DEC-003); a escolha
  fica em catálogo, por `(drive_id, item_id)`.

## Consequências
- Toda análise da Fase 3 declara de qual árvore veio cada evidência.
- A comparação DOCX × PDF de um mesmo Relatório G2 é ela própria uma verificação (o DOCX declara, o PDF
  mostra); divergência entre eles é achado, não erro de método.
- Qualquer leitura de conteúdo desses arquivos exige autorização da Emmily se for persistir em
  disco; leitura em memória é permitida (DEC-001).
