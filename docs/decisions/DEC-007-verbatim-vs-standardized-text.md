# DEC-007 — Texto citado literalmente × texto produzido pelo relatório

**Data:** 2026-09-27 · **Status:** ACEITA (instrução direta da Emmily)

## Contexto
A Fase 3 encontrou formas que se repetem nos quatro meses e portanto não são erro de um mês,
mas parecem descuido: `RD-102` sem o "A", `N° 00/0000-PARC` com espaço num lugar e sem espaço
em outro, "é assim **descrita**" concordando no feminino com "O Produto", "Referente **as**
Condicionantes" sem crase. Perguntar caso a caso ao gerar cada relatório não escala.

## Decisão
Todo bloco de texto recebe uma de duas classes, e o tratamento decorre dela:

| Classe | O que é | Tratamento |
|---|---|---|
| `SOURCE_VERBATIM` | citação literal de contrato, Termo de Referência, Termo Aditivo ou outra fonte oficial | **preservar exatamente**, com erros e tudo. Nunca corrigir em silêncio |
| `GENERATED_STANDARDIZED_TEXT` | texto produzido pelo próprio Relatório G2 | **corrigir e padronizar** |

Aplicações imediatas:

- **`RD-102` → `RD-102A`** quando se refere à rodovia deste contrato e não está dentro de
  citação literal. Afeta o bloco de reuniões do P2.1.
- **Número do contrato**: uma forma única e oficial em todo o texto gerado. Hoje a Apresentação
  escreve `N° 00/0000-PARC` e o Encerramento `N°00/0000-PARC`.
- **Erros gramaticais do texto gerado se corrigem**: "é assim descrita" → "é assim descrito";
  "Referente as Condicionantes" → "Referente às Condicionantes"; "Consolidade" → "Consolidado".
- **Espaços residuais** como `ANEXOS` com cinco espaços à direita desaparecem.

A citação contratual dos seis produtos é `SOURCE_VERBATIM` por definição: o bloco entre aspas
que cita "3.7. GESTÃO DE ENGENHARIA E SOCIOAMBIENTAL" e "3.8.2. Produtos a serem desenvolvidos"
sai idêntico ao original, mesmo que o original tenha problema. **O cabeçalho que introduz a
citação ("O Produto 2.X, referente ao …, é assim descrita no …") é texto gerado**, e portanto
se corrige.

## Consequência para o golden test
Um relatório reconstruído **não será byte a byte igual** ao histórico nos pontos padronizados.
Essas diferenças são **esperadas e corretas**, não defeito. O comparador da Fase 9 precisa de
uma lista de divergências aceitas, alimentada por esta decisão e por
`data/catalog/anomalies.jsonl`, e deve distinguir "diferente porque corrigimos" de "diferente
porque erramos".

## Evidência
- `data/catalog/anomalies.jsonl`, classe `FORMAT_VARIATION`.
- `docs/discovery/ANATOMY_2026-05_TO_2026-08.md`, seção sobre formas consolidadas.
