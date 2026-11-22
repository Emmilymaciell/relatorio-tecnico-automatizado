# RASCUNHO — Especificação visual do Relatório G2

**Status: CANDIDATO.** O PDF é a referência visual; o DOCX é a evidência estrutural (DEC-005).

## Regras de imagem

| # | Regra | Confiança |
|---|---|---|
| V1 | Toda imagem do corpo é **inline**, em parágrafo próprio, **sem wrap e sem crop** | CONFIRMED (30/30 usos) |
| V2 | Largura padrão em retrato = **17,50 cm** = largura útil exata. Exceções só para preservar proporção | HIGH (27/30) |
| V3 | Sem legenda "Figura N" e sem nota de fonte em nenhum caso | CONFIRMED |
| V4 | Nenhuma imagem em cabeçalho ou rodapé: a faixa é texto e borda | CONFIRMED |
| V5 | Único objeto flutuante do documento é a capa, em VML absoluto com sangria total | CONFIRMED |

## Três representações distintas, que não se substituem

| Forma | Formato | Onde | Tratamento |
|---|---|---|---|
| Página institucional | JPG / PNG, 26,20 × 14,74 cm | bloco paisagem | `STATIC_ASSET`: reutilizar byte a byte |
| Tabela vinda do Excel | **EMF vetorial** | Controle de Produtos | `STRUCTURED_DATA`; o texto sobrevive no PDF |
| Painel de indicadores | PNG raster | produtos 2.2 e 2.4 | `RECONSTRUCTED_VISUAL` (DEC-009) |

O documento tem **uma única tabela nativa do Word**: a de assinatura, 2 linhas × 1 coluna, 8,0 cm.

## Bloco paisagem
Oito páginas (7 a 14), uma imagem por página, topo em y = 2,19 cm, **nunca sangrando**. Seis
imagens têm sha1 idêntico nos quatro meses; quatro são idênticas desde junho. Em maio eram cinco
páginas: o bloco cresceu para oito em junho e não mudou mais.

**Anomalia herdada:** duas imagens passam da margem direita (27,02 cm e 26,45 cm contra 26,20 cm
de área útil). Vem desde maio. Corrigir ou preservar é decisão da Emmily.

## Assets estáticos (reutilizar, nunca regerar)
Logotipo da apresentação (16,04 × 5,19 cm), quatro diagramas do bloco paisagem, quatro fotos de
organograma, diagrama de disciplinas predecessoras (EMF, 15,22 × 11,83 cm), e as quatro mídias
internas do slide de capa.

## Evolução de representação
Junho colava as tabelas de produtos como **JPG**; julho passou a **EMF vetorial**. Consequência
mensurável: o texto das tabelas de junho **não é extraível** do PDF. O padrão vigente exige
vetor. HIGH.

## Como medir fidelidade (DEC-009)
Avaliar conteúdo, estrutura, posição, dimensões, hierarquia, cores, proporções e tipografia.
**Ignorar** largura exata do recorte, ruído de interface capturado sem querer, antialiasing e
imprecisão de redimensionamento manual.
