# RASCUNHO — Regras de conteúdo do Relatório G2

**Status: CANDIDATO.** Classificação por origem da informação.

## Texto literalmente fixo (vira código)

- **Citação contratual dos seis produtos**: `SOURCE_VERBATIM` (DEC-007). Verificação
  programática: **24 de 24 blocos idênticos byte a byte**, seis produtos × quatro meses.
  Preservar com erros e tudo. O cabeçalho que introduz a citação é texto gerado e se padroniza.
- **Frase de ausência de atividade**, para os produtos 2.3, 2.5 e 2.6:
  `No período de referência do presente relatório não houve atividades relacionadas ao produto 2.X.`
  Doze de doze ocorrências idênticas. Condição: produto sem documento na Lista Mestra.
- **Chamada da tabela**, três vezes por relatório, ao fim dos produtos 2.1, 2.2 e 2.4.
- Apresentação, bloco institucional, lista de atividades e os processos ambientais das quatro
  rodovias: idênticos nos quatro meses.

## Moldes com campos

| Molde | Campos | Derivável? |
|---|---|---|
| Apresentação | número, mês, ano | sim |
| Encerramento | número, mês, ano, páginas, anexos | sim, ambas as contagens |
| Data de assinatura | dia, mês, ano | **não**: entrada manual |
| Período dos relatórios semanais | data inicial, final, corte | corte = dia 25 do mês de referência |
| Licenças pendentes | quantidade por extenso | sim |
| Reuniões por rodovia | rodovia, executora, dia, hora | dado estável, fonte desconhecida |

**Número e mês aparecem duas vezes** (apresentação e encerramento) e **divergiram em dois dos
quatro meses**. O builder deriva os dois do mesmo campo e **valida a igualdade** antes de fechar.

## Texto derivado de dado estruturado
Sete de oito blocos que citam documentos no produto 2.4 derivam 100% da Lista Mestra, agrupada
por tipo e rodovia: relatórios mensais de obra, boletins de medição, inspeções de alojamento,
relatórios ambientais, análises de controle ambiental e não conformidades.

Os blocos de status por disciplina do produto 2.2 derivam da aba `Projetos`, com mapeamento
rótulo para filtro validado 8 de 8 e 5 de 5. Exige **lista de exclusão** de disciplinas
administrativas e normalização da grafia da rodovia.

## Resumo executivo
**Não é síntese livre.** Cinco dos nove parágrafos são byte a byte idênticos aos de junho e
julho. É uma sequência de slots, com variação enumerativa. Gatilho validado nos quatro meses: o
slot de documentos de padronização só existe se houver documento com prefixo IT, CT ou POP.
Apenas o parágrafo de temas dos pareceres exige interpretação.

## Entrada humana
Desapropriação e interferências com a concessionária: busca por GDP, Casa Civil, GFD e
EnergiaX em todas as células das planilhas deu **zero**. É informação externa, registrada
manualmente. O conteúdo de desapropriação já existia em maio e junho embutido por rodovia:
agosto promoveu a seção própria. Só o bloco de interferências é estreia real.

## Ordem das rodovias é por bloco, não global
Reuniões: 104, 103, 102, 101. Acompanhamento: 103, 102A, 101, 104. Processos ambientais:
102A, 103, 104, 101. Cada ordem é estável nos quatro meses. **Não impor ordenação única.**

## Padronização (DEC-007)
Citação literal sai exatamente como está. Texto gerado é corrigido: sigla completa da rodovia,
forma única do número do contrato, concordância, crase, espaços residuais.

## UNRESOLVED
- Verbalização do conjunto vazio no produto 2.2: **quatro formas diferentes no mesmo relatório**.
- Fonte de verdade da faixa de relatórios semanais: texto e planilha discordam em um documento
  por rodovia em julho e agosto, e batem 100% em maio e junho.
- Rótulo correto da segunda coluna do Controle de Produtos, hoje "Parecer", que é um valor.
