# RASCUNHO — Regras de anexos do Relatório G2

**Status: CANDIDATO.** Evidência: Relatórios G2 nº 11 a nº 14.

## Composição
Uma linha da Lista Mestra vira um anexo. Um documento pode virar **um arquivo ou uma pasta**
com várias peças; peças internas recebem prefixo numérico explícito de ordem.

```
documentos(relatório N) = Controle Geral onde "N° Relatório" == N
```

Correspondência com os arquivos entregues: **100%** nos relatórios nº 11, nº 12 e nº 13
(149/149, 122/122, 165/165). Em agosto, 149 de 154 na planilha de hoje — e **135 de 135 contra
o snapshot da data de emissão** (DEC-008).

## Hierarquia de pastas

```
/G2/Anexos/<Produto>/<Tipo>/<Rodovia>/<arquivo>
```

| Nível | Origem | Observação |
|---|---|---|
| 1 | coluna `Produto` | 686 arquivos verificados, **zero divergências**. O nome perde acentos e ganha sufixo |
| 2 | coluna `Manifestação`, **renomeada** | o nome da pasta não é o valor da coluna |
| 3 | coluna `Empreendimento` | suprimido quando o tipo tem poucos documentos no mês |

`Nota Técnica` se divide em duas pastas conforme a `Descrição` começar por "de Aceitação" ou
"de Análise", com zero cruzamentos em 128 arquivos.

## Índice consolidado
Aparece nas últimas páginas, filtrado só por `N° Relatório`, **sem** filtro de produto, com
layout de colunas diferente dos blocos por produto. É o mesmo conjunto da união dos três
blocos, mas em **sequência diferente**: varredura global única, com os produtos intercalados.

## Ordenação
**Ordem física da linha na planilha.** Explica 100% de cerca de 17 mil pares ordenados. Nunca
aplicar ordenação por data, código ou rodovia.

## Contagem declarada no encerramento
`COUNT` de linhas da Lista Mestra do relatório. Não é o número de arquivos na pasta, sempre
maior, nem o de códigos distintos, menor: há uma linha por documento **por rodovia**.

## Exceções comprovadas
- Documentos com status diferente de "Entregue" **são anexados** (quatro casos em junho).
- Um documento anexado em dois relatórios (maio e junho) — anomalia registrada.
- Uma divergência de rodovia entre planilha e pasta em 686 arquivos.
- `Contém Anexos?`: **coluna abandonada**, um único valor em 1439 linhas. Não usar.
