# DEC-011 — Capa = fundo estático + textos do Word em posição absoluta

**Data:** 2026-10-01 · **Status:** ACEITA (técnica, autopilot; revisável pela Emmily) ·
**Confiança:** HIGH

## Contexto
A capa histórica é um slide PowerPoint embutido como objeto OLE, exibido pela prévia EMF
guardada no DOCX (`docs/discovery/WAVE1_FINDINGS.md` §I). Só dois campos variam (número e data
de emissão). O Word exporta a prévia guardada; como a fonte da data não estava disponível para
quem editou, a prévia saiu errada em julho ("11de Agosto") e **ilegível no PDF de agosto**.
Regenerar a prévia fielmente exigiria PowerPoint COM.

## Decisão
1. O builder gera a capa como **(b')**: imagem de fundo sem texto (composta uma vez a partir
   das mídias internas do slide e registrada como asset com sha1) ancorada atrás do texto com
   sangria total, mais os textos da capa como parágrafos do Word em posição absoluta.
2. Número e data são campos do contexto (`report_number`, `issue_date`); o restante do texto
   da capa é fixo do modelo.
3. A seção 0 mantém `titlePg` com cabeçalho/rodapé da primeira página vazios, como no histórico.

## Consequências
- Elimina a prévia de 11 MB, os defeitos de julho e agosto e a dependência de PowerPoint.
- O texto da capa passa a ser pesquisável no PDF: **diferença intencional** em relação ao
  histórico, que o QA visual classifica como `HISTORICAL_DEFECT` corrigido (DEC-009).
- Se a Emmily quiser poder editar o slide com duplo clique, a alternativa (a) — reinserir o
  OLE com os dois campos trocados e prévia regenerada — continua possível.
