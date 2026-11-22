# Linhagem de fontes (Source Lineage)

Para cada componente: **fonte primária → transformação → representação → posição**.
Registro estruturado em `data/catalog/source_lineage.jsonl` (15 entradas: 9 rastreadas,
3 parciais, 3 desconhecidas). Sem prova, `status=UNKNOWN` e a lacuna fica registrada.

Verificado na janela Maio a Agosto/2026 (Relatórios G2 nº 11 a nº 14).

---

## A Lista Mestra é o manifesto do Relatório G2 (CONFIRMED)

| Campo | Valor |
|---|---|
| Arquivo | `00_ Lista mestre.xlsx` |
| Local | `3. Desenvolvimento/G2 -  Engenharia/` |
| Identidade | `drive_id:item_id` registrado em `data/catalog/source_lineage.jsonl` |
| Aba principal | `Controle Geral`, 1439 linhas, cabeçalho na linha 3, autofiltro em `A3:O1440` |
| Outras abas | `Listas` (domínios de validação e padrão de código), `Planilha1` e `Planilha2` (rascunhos) |
| Estado | documento **vivo**, alterado no mesmo dia desta análise |

### Colunas que importam

| Coluna | Papel |
|---|---|
| `Produto` | define a pasta de primeiro nível do anexo (P2.1, P2.2, P2.4) |
| `Documento` | código `XX-NNN.V`; é a chave que casa com o arquivo anexado |
| `Manifestação` | tipo; define a pasta de segundo nível, com renomeação |
| `Descrição` | desempata Nota Técnica entre "de Aceitação" e "de Análise" |
| `Empreendimento` | rodovia; define a pasta de terceiro nível |
| `Data Entrega` | atributo, **não** seletor |
| `Status Entrega` | rastreamento operacional, **não** filtra |
| `N° Relatório` | **o seletor** |
| `Contém Anexos? (A partir do Relatório 11)` | coluna abandonada: 1 valor em 1439 linhas |

O padrão de código está documentado na própria aba `Listas`: prefixo do tipo, número
sequencial e versão.

## A regra de seleção (CONFIRMED)

```
documentos(Relatório G2 nº N) = Controle Geral onde "N° Relatório" == N
```

Sem filtro por data, por status ou por empresa.

**A data de entrega não seleciona, e há contraexemplo direto:** `PA-726.1`, entregue em
01/09/2026, pertence ao relatório nº 14; `PA-728.1`, entregue em 02/09/2026, pertence ao nº 15.
As janelas de datas de relatórios consecutivos se sobrepõem em todos os pares testados. Prever
o relatório pelo mês civil acerta apenas **90%** dos casos entre maio e agosto de 2026.

**O status não filtra:** no relatório nº 12 há quatro documentos com status "Em elaboração", e
todos estão anexados.

**O número é preenchido à mão, depois do fato.** Trinta e quatro linhas estão sem número, todas
de setembro de 2026: é a fila do próximo relatório. Cinquenta e uma têm zero, que significa
"fora do escopo de qualquer relatório" (cartas e manifestações institucionais). O gerador deve
**ler** esse campo, nunca inferi-lo.

## Validação cruzada: Lista Mestra × anexos entregues

| Relatório | Linhas na Lista Mestra | Com arquivo anexado | Sem arquivo | Anexado e fora da lista |
|---|---|---|---|---|
| nº 11 — Maio | 149 | **149 (100%)** | 0 | 1 |
| nº 12 — Junho | 122 | **122 (100%)** | 0 | 1 |
| nº 13 — Julho | 165 | **165 (100%)** | 0 | **0** |
| nº 14 — Agosto | 154 | 149 (96,8%) | 5 | 0 |

Julho é a correspondência perfeita nos dois sentidos. As cinco ausências de agosto são as notas
técnicas lançadas depois da emissão. Os arquivos que não casam por código não são órfãos: são
peças internas de pacotes documentais.

## Como um documento vira anexo

```
/G2/Anexos/<Produto>/<Tipo>/<Rodovia>/<arquivo>
```

- **Nível 1, produto:** 686 arquivos verificados, **zero divergências**. Atenção: o nome da
  pasta perde acentos e ganha sufixo, por exemplo "2.4 GERENCIAMENTO TÉCNICO" vira
  `P2.4 - Gerenciamento Tecnico de Obra`.
- **Nível 2, tipo:** o nome da pasta **não** é igual ao valor da coluna. "Parecer" vira "Parecer
  Técnico"; "Relatório Semanal de Acompanhamento de Obras" vira "Relatório Semanal de Obras".
  Uma das pastas reproduz o erro "Consolidade". O mapa muda entre meses e precisa de versão.
- **Nota Técnica se bifurca pela Descrição**, em "de Aceitação de Documentos" ou "de Análise de
  Projeto", com zero cruzamentos.
- **Nível 3, rodovia:** suprimido quando o tipo tem poucos documentos no mês.
- **Documento com peças próprias vira pasta**, com ordem explícita por prefixo numérico nos
  arquivos internos. A forma de nomear essa pasta muda todo mês.

## Onde a Lista Mestra aparece no corpo do relatório

O Controle de Produtos é um **recorte do Excel colado como EMF vetorial**, com as colunas
Documento, Manifestação (rotulada "Parecer" no relatório), Descrição, Empreendimento, Data
Entrega e Status Entrega. O autofiltro do Excel fica visível no documento final.

O rótulo da segunda coluna mudou com o tempo: **"Tipo"** nos relatórios nº 11 e nº 12,
**"Parecer"** nos nº 13 e nº 14, e hoje a planilha traz **"Manifestação"**. Três rótulos, duas
mudanças datáveis, o que reforça que a planilha evolui.

Fora isso, o corpo do relatório **não tabula documentos**: ele os cita em faixas dentro de
parágrafos, como "RD-103: RO-544.1 a RO-548.1". A ligação é narrativa.

## Contagem de anexos do Encerramento (CONFIRMED)

O número declarado é a **contagem de linhas** da Lista Mestra do relatório. Não é o número de
arquivos na pasta, sempre maior, nem o de códigos distintos, menor. Uma linha por documento
**por rodovia**: o mesmo código aparece mais de uma vez quando cobre vários empreendimentos.

## Escopo atual do Relatório G2

Apenas os produtos **2.1, 2.2 e 2.4** têm documentos nos relatórios nº 11 a nº 15. O produto 2.3
só aparece nos relatórios nº 1 a nº 5, o 2.6 nos nº 2 e nº 3, e o 2.5 nunca foi usado. Mesmo
assim, os seis produtos continuam presentes na estrutura do documento, com a frase padrão de
ausência de atividade. HIGH_CONFIDENCE.

## Lacunas (UNKNOWN)

1. **Origem dos cronogramas por rodovia do P2.2.** Provavelmente
   `03 - Acompanhamento de Projetos Executivo.xlsx`, sem prova de intervalo.
2. **Origem dos quadros de condicionantes do P2.4.** Provavelmente
   `04_Acompanhamento - Licenca Ambiental.xlsx`, sem prova.
3. **Papel de `02_Acompanhamento de NC automatizada.xlsm`** no relatório.
4. **A capa**: objeto PowerPoint embutido; onde está ancorada e o que mostra exatamente.
5. **Responsável e cadência** de atualização da Lista Mestra.
6. **Ordem apresentada** dos anexos dentro de cada pasta.
7. **Intenção da coluna "Contém Anexos?"**, que exigiria abrir o documento marcado.
8. **Relatório G2 nº 15** já tem 78 documentos atribuídos, mas a pasta de entrega está vazia.
   É o próximo teste natural da regra de seleção.
