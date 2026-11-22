# RASCUNHO — Regras de fonte do Relatório G2

**Status: CANDIDATO. Não certificado.** Só entram aqui regras `CONFIRMED` ou `HIGH_CONFIDENCE`
com evidência forte. O que continua incerto está na seção final, explícito, e **não deve ser
implementado**. Base: Relatórios G2 nº 11 a nº 14 (Maio a Agosto/2026).

---

## 1. A fonte de composição

A **Lista Mestra** (`00_ Lista mestre.xlsx`, aba `Controle Geral`) decide o que pertence ao
relatório. Identidade por `(drive_id, item_id)`, registrada em
`data/catalog/source_lineage.jsonl`.

Estrutura confirmada: 1439 linhas de dados a partir da linha 4, cabeçalho na linha 3, quatro
abas das quais **só `Controle Geral` é fonte real**. Sem intervalos nomeados, sem colunas
ocultas, sem fórmulas fora da aba de listas.

### Colunas

| Coluna | Papel | Usar? |
|---|---|---|
| D `Documento` | código `XX-NNN.V`; chave de casamento com o anexo | sim |
| E `Manifestação` | tipo do documento | sim |
| F `Descrição` | desempata Nota Técnica entre Aceitação e Análise | sim |
| G `Empreendimento` | rodovia | sim |
| H `Data Entrega` | atributo, **nunca** seletor | só exibir |
| I `Status Entrega` | rastreamento; **não filtra** | só exibir |
| B `Produto` | filtra o bloco por produto e a pasta do anexo | sim |
| K `N° Relatório` | **o seletor** | sim |
| C `Empresa` | um único valor em 1439 linhas | não |
| J `Versão` | redundante com o sufixo do código | não |
| L `Período` | preenchida em 13% das linhas | não |
| M `Contém Anexos?` | **um único valor** em 1439 linhas: criada e nunca usada | **não** |

As 1123 linhas ocultas da planilha são resíduo de um filtro manual pela coluna de tipo, não
exclusão semântica: a consistência entre linha oculta e filtro salvo foi verificada em 1437 de
1437 casos. **Ignorar o estado de ocultação.**

## 2. Seleção — CONFIRMED

```
documentos(relatório N) = Controle Geral onde "N° Relatório" == N
```

Sem filtro por data, status, empresa ou visibilidade.

**Proibido usar a data de entrega como critério de inclusão.** Contraexemplo: um parecer
entregue em 1º de setembro pertence ao relatório de agosto, e outro entregue em 2 de setembro
pertence ao de setembro. Prever pelo mês civil acerta 90% dos casos, o que significa errar um em
cada dez documentos.

O campo é preenchido **manualmente e depois do fato**. Valor zero significa "fora do escopo de
qualquer relatório"; vazio significa "ainda não classificado". Ler, nunca inferir.

## 3. Ordenação — CONFIRMED

**A ordem é a da varredura física da planilha, de cima para baixo. Nunca aplicar ordenação.**

Testado contra cerca de 17 mil pares ordenados nos quatro blocos de agosto:

| Hipótese | Acerto |
|---|---|
| **ordem física da linha** | **100%** |
| data de entrega | 94% |
| código do documento | 69% |
| rodovia | 62% |

O XML da planilha não tem estado de ordenação: ela é um log de inserção. Um `ORDER BY` no
builder produziria uma sequência diferente da histórica em todos os blocos.

## 4. Controle de Produtos — CONFIRMED

Aparece em dois papéis, com **filtros diferentes e layouts diferentes**:

```
bloco dentro do produto:  N° Relatório == N  AND  Produto começa com "2.X"
índice consolidado:       N° Relatório == N               (sem filtro de produto)
```

Seis colunas, na ordem: Documento, Manifestação, Descrição, Empreendimento, Data Entrega,
Status Entrega.

Contagens de agosto, todas conferidas contra o PDF: produto 2.1 → 3, produto 2.2 → 48,
produto 2.4 → 98, índice de anexos → 149. A união dos três blocos é o mesmo multiconjunto do
índice, mas **em sequência diferente**: o índice é uma varredura global única, com os produtos
intercalados.

Os dois layouts têm larguras de coluna distintas e o builder precisa dos dois.

**Representação:** recorte do Excel colado como metarquivo vetorial (EMF), não tabela do Word e
não imagem rasterizada. Ver bloqueio P0 na seção final.

## 5. Anexos — CONFIRMED

Uma linha da Lista Mestra vira um anexo, que pode ser um arquivo ou uma pasta com várias peças.

```
/G2/Anexos/<Produto>/<Tipo>/<Rodovia>/<arquivo>
```

- **Produto → pasta de primeiro nível**: 686 arquivos verificados, zero divergências. O nome da
  pasta perde acentos e ganha sufixo.
- **Tipo → pasta de segundo nível, com renomeação**. O nome da pasta não é o valor da coluna.
  Nota Técnica se divide em duas pastas conforme a Descrição, sem nenhum cruzamento.
- **Rodovia → terceiro nível**, suprimido quando há poucos documentos no mês.
- Peças internas de um pacote recebem prefixo numérico explícito de ordem.

Correspondência com a Lista Mestra: 100% nos relatórios nº 11, nº 12 e nº 13.

## 6. Contagens do Encerramento — CONFIRMED

| Campo | Regra |
|---|---|
| páginas | contagem do PDF final, por extenso entre parênteses |
| anexos | `COUNT` de linhas da Lista Mestra do relatório |

A contagem de anexos **não** é o número de arquivos na pasta, sempre maior, nem o de códigos
distintos, menor: é uma linha por documento **por rodovia**.

## 7. Reconstrução histórica — CONFIRMED (DEC-008)

Usar o **snapshot da Lista Mestra vigente na data de emissão**, obtido pelo histórico de versões
do SharePoint, nunca a planilha atual. Critério: a última versão anterior ou igual ao fim do dia
da emissão.

Com o snapshot correto, agosto tem correspondência perfeita: 135 códigos no relatório e 135 na
planilha da época, zero divergências nos dois sentidos. O histórico disponível começa em
20/07/2026, então **maio e junho não podem ser validados por esta via**.

## 8. Padronização — DEC-007

Citação literal de contrato ou termo de referência sai **exatamente como está**. Texto produzido
pelo relatório é **corrigido e padronizado**: rodovia com a sigla completa, uma forma única do
número do contrato, erros gramaticais corrigidos, espaços residuais removidos.

---

## O que NÃO está resolvido e não deve ser implementado

| Item | Situação |
|---|---|
| Como gerar o EMF do Controle de Produtos | **P0.** Conteúdo derivável, representação não resolvida |
| Capa | **P0.** Objeto PowerPoint embutido, sem regra de reprodução |
| Cronogramas por rodovia do produto 2.2 | **P1.** Aba e intervalo não provados |
| Quadros de condicionantes do produto 2.4 | **P1.** Aba e intervalo não provados |
| Painel de não conformidades | Fonte nem estabelecida |
| Resumo executivo | Exige síntese; proporção derivável desconhecida |
| Bloco de desapropriação | Só em agosto; gatilho desconhecido |
| Data de assinatura | Sem fonte no pacote; entrada manual |

Detalhamento e prioridades em `data/catalog/gaps.jsonl` e `state/readiness.yaml`.
