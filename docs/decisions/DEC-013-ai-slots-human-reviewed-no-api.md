# DEC-013 — Slots de síntese: texto revisado por humano, rascunho determinístico, sem API

**Data:** 2026-10-01 · **Status:** ACEITA (técnica, autopilot) · **Confiança:** HIGH

## Contexto
O resumo executivo do 2.1 é ≈90% fixo ou derivável da Lista Mestra (`WAVE1_FINDINGS.md` §K).
Sobram dois slots interpretativos: temas dos pareceres do 2.2 e padronização (IT/CT/POP). A
Regra nº 4 do projeto reserva a IA para isso, mas chamar um provedor de IA exigiria uma
credencial nova, e segredo novo é decisão da Emmily.

## Decisão
1. O componente `EXECUTIVE_SUMMARY_PARECER_THEMES` usa, nesta ordem:
   a. o texto aprovado em `inputs.ai_review[slot_id]`, quando existir;
   b. senão, um **rascunho determinístico** a partir das Descrições dos documentos do relatório
      (mapa de palavras-chave versionado em `config/data_rules/p21_executive_summary.yaml`),
      com status `PENDING_HUMAN` e uma pauta de revisão (documentos, descrições, pergunta).
2. Nenhuma chamada a API de IA nesta versão do builder. A interface do slot aceita um provedor
   plugável no futuro, sem mudar o restante do builder.
3. Um relatório com algum slot `PENDING_HUMAN` é gerado normalmente, mas o `BuildResult` fica
   com `ok == False` até a revisão: não sai como entrega final.

## Consequências
- O pipeline mensal não depende de credencial nova.
- A revisão humana desses slots faz parte do fluxo de produção (Fase 11), não é exceção.
