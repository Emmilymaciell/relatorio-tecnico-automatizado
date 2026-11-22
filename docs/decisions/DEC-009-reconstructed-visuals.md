# DEC-009 — Quadros do relatório são visuais reconstruídos, não capturas de tela

**Data:** 2026-09-27 · **Status:** ACEITA (instrução direta da Emmily) · **Confiança:** CONFIRMED

## Contexto
A Fase 4 provou que os quatro quadros por rodovia do produto 2.2 são **capturas de tela manuais**
de um painel Power BI, e que o dado por trás está integralmente na aba `Projetos` de
`03 - Acompanhamento de Projetos Executivo.xlsx`. As capturas trazem imperfeições acidentais:
largura variando de 1407 a 1566 pixels, ordenação trocada em junho porque o operador clicou num
cabeçalho antes do print, duas imagens redimensionadas fora do padrão, e até elementos de
interface capturados sem querer.

## Decisão
1. O builder **não reproduz a captura**. Ele parte do dado canônico e **reconstrói o visual**:

   ```
   dado canônico da planilha → transformação determinística → componente visual reproduzível
   ```

2. Classe de automação: **`RECONSTRUCTED_VISUAL`** (dado estruturado mais render próprio), nunca
   `STATIC_ASSET`. Isso distingue esses quadros dos assets institucionais, que são arquivos
   prontos e devem ser reutilizados byte a byte.
3. **Filtros salvos no arquivo não são verdade.** O estado vivo da planilha tem autofiltro por
   uma rodovia e centenas de linhas ocultas. O gerador lê os dados completos e aplica os
   próprios filtros, explicitamente. Ler respeitando a ocultação daria resultado errado.
4. **A ordenação por revisão de junho é anomalia histórica, não regra.** A ordem canônica é pela
   coluna de ordem de disciplina, confirmada em maio, julho e agosto.
5. As variações de largura (17,38 e 17,47 cm em junho) são imprecisão manual. O padrão é a
   largura útil do texto, 17,50 cm.

## Como medir fidelidade
A comparação visual da Fase 9 avalia **função informacional e aparência institucional**:

| Avaliar | Ignorar |
|---|---|
| conteúdo e completude dos dados | largura exata do recorte em pixels |
| estrutura e hierarquia visual | ruído de interface capturado sem querer |
| posição e dimensões no documento | antialiasing e diferença de renderizador |
| cores, legenda e proporções | ordenação acidental de um mês |
| tipografia e comportamento | imprecisão de redimensionamento manual |

**Um quadro reconstruído que esteja mais correto que o histórico não é uma falha do gerador.**
O comparador precisa dessa distinção para não perseguir defeito.

## Alcance
Vale para os quatro quadros por rodovia do produto 2.2 e para os cinco painéis ambientais do
produto 2.4, todos capturas de Power BI. **Não** vale para os assets institucionais (bloco
paisagem, logotipo, diagrama de disciplinas predecessoras), que continuam `STATIC_ASSET` e são
reutilizados sem regeração.

O Controle de Produtos é caso à parte: é recorte vetorial do Excel, com o dado 100% derivável.
Continua como `STRUCTURED_DATA`, e a decisão de como gerar o metarquivo é o gap P0 aberto.

## Consequência
- O painel Power BI deixa de ser dependência de geração. Continua útil como referência visual.
- O componente descontinuado da aba `Painel de Controle`, que existiu em maio e junho, **não
  volta**: o padrão vigente desde julho tem um único quadro por rodovia.
