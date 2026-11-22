# Descoberta da especificação visual

O PDF é a **referência visual**; o DOCX é a **evidência estrutural**. Registro por página em
`data/catalog/pages.jsonl` (modelo `PageRecord`). Este documento consolida o que foi medido.

## Método (Fase 3)
- Extração estrutural de PDF com texto vetorial (PyMuPDF/pdfplumber) + render de página para
  comparação. OCR só como último recurso.
- DOCX: `document.xml`, `styles.xml`, `settings.xml`, headers/footers, `_rels`, `media/`.
  Comparar o que o DOCX declara com o que o PDF mostra.
- Diferença de renderizador/antialiasing ≠ diferença estrutural.

## Geometria de página
| Aspecto | nº 12 | nº 13 | nº 14 | Observação |
|---|---|---|---|---|
| Tamanho da página | — | — | — | |
| Orientação por seção | — | — | — | bloco P2.1 paisagem? (hipótese) |
| Margens | — | — | — | |
| Distância cabeçalho / rodapé | — | — | — | |
| Numeração de página | — | — | — | |

## Tipografia
| Elemento | Família | Tamanho | Peso | Cor | Espaçamento | Evidência |
|---|---|---|---|---|---|---|
| — | — | — | — | — | — | |

## Imagens e tabelas
| Componente | Tipo (imagem/tabela nativa) | Dimensões no Word | Crop | Âncora | Alinhamento | Evidência |
|---|---|---|---|---|---|---|
| — | — | — | — | — | — | |

## Estrutura
Capa · TOC · seções e quebras · retrato/paisagem · assinatura · anexos/índice — a preencher.

## Hipóteses a verificar (fornecidas pela Emmily)
- nº 11 inicia mudança visual importante no P2.1; nº 12 a nº 14 são o padrão visual atual e estável.
- Existe bloco P2.1 de páginas paisagem com conteúdo institucional recorrente.
- Há assets visuais reutilizados exatamente entre meses.
