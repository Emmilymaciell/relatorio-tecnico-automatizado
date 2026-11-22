# RASCUNHO — Especificação do Relatório G2

**Status: CANDIDATO. Não certificado.** Só regras `CONFIRMED` ou `HIGH_CONFIDENCE` com evidência
forte. Base: Relatórios G2 nº 11 a nº 14 (Maio a Agosto/2026), referência Agosto.
Machine-readable em `config/report_spec_draft.yaml`.

## Documento

| Aspecto | Valor |
|---|---|
| Papel | A4, 21,0 × 29,7 cm |
| Seções | 3: retrato → paisagem → retrato, quebra `nextPage` |
| Margens retrato | 2,0 / 1,5 / 2,0 / 1,5 cm |
| Margens paisagem | 2,0 / 1,5 / **1,5 / 2,0** cm (laterais espelhadas) |
| Cabeçalho / rodapé | 1,0 cm / 0,0 cm da borda |
| Páginas | 43 no padrão vigente (38 em maio, antes do bloco paisagem crescer) |

## Estrutura fixa — 22 títulos, sem uma mudança nos quatro meses

```
Apresentação                                      Ttulo1
gestão de engenharia e socioambiental             Ttulo1
  Produto 2.1 … 2.6                               Ttulo2   (2.6 com quebra de página forçada)
    Descrição das atividades atribuídas           Ttulo3
    Produtos desenvolvidos no período             Ttulo3
ENCERRAMENTO                                      Ttulo
ANEXOS                                            Ttulo
```

**Os seis produtos aparecem sempre**, inclusive os que não têm atividade desde maio (2.3, 2.5 e
2.6), com a frase padrão de ausência. A numeração é campo automático do Word.

## Cabeçalho, rodapé e capa

- Cabeçalho: `PROGRAMA | CONSÓRCIO ESTRUTURADOR DO PROGRAMA`, uma parte por seção,
  ausente na capa. Sem imagem: é texto e borda.
- Rodapé: `-CONFIDENCIAL-` à esquerda, campo `PAGE` à direita. Capa sem numeração.
- Capa: um slide A4 de PowerPoint embutido como objeto OLE no parágrafo 0, renderizado por VML
  em posição absoluta com sangria total. **Só dois campos variam**: número do relatório e data
  de emissão. As quatro mídias internas são byte-idênticas nos quatro meses.
- Data da capa e data de assinatura são **campos independentes** e nunca coincidem.

## Sumário
Campo TOC com níveis 1 a 3, dentro de bloco SDT. Exige o Word para atualizar a paginação.

## Tipografia
Corpo Arial Nova Cond 11 e Arial Nova Light 11; títulos Arial Nova Cond Bold 13; tabelas em
imagem 6,8; marcadores SymbolMT 10.

## Composição por produto
Cada produto tem citação contratual literal (`SOURCE_VERBATIM`) seguida da narrativa do período.
Produtos com atividade fecham com a frase de chamada da tabela e o Controle de Produtos.
Produtos sem atividade trazem apenas a frase de ausência.

## O que NÃO reproduzir
Ver `data/catalog/anomalies.jsonl` (23 registros, todos com `should_learn_as_rule=false`) e
DEC-007. Em especial: o número errado do relatório na apresentação de agosto, o mês errado em
julho, a data de assinatura anterior ao período, o rótulo "Parecer" na segunda coluna do
Controle de Produtos, e as imperfeições de captura manual (DEC-009).
