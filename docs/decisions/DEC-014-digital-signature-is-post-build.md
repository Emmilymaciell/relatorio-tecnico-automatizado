# DEC-014 — Assinatura digital do PDF é etapa humana posterior ao builder

**Data:** 2026-10-01 · **Status:** ACEITA (técnica, autopilot) · **Confiança:** CONFIRMED

## Contexto
O PDF publicado tem uma imagem raster depois do ENCERRAMENTO. O loop do golden test mostrou que
ela não existe no DOCX: é a aparência de uma assinatura digital do PDF (campo `Signature1`,
`SigFlags 3`), presente nos nº 11 a 14.

## Decisão
1. O builder entrega DOCX e PDF **não assinados**. A assinatura digital é feita depois, por
   quem assina, com a própria credencial.
2. O builder não extrai, guarda nem reproduz a imagem da assinatura (dado pessoal).
3. No golden test, a ausência dessa imagem no gerado é desvio permitido (`ALW-14-015`).

## Consequências
- O fluxo de produção termina em "PDF pronto para assinatura"; a entrega final é humana.
- `positioning.post_build_signature` no modelo registra o lugar onde a assinatura entra.
