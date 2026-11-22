---
name: session-start
description: Protocolo oficial de ABERTURA de sessão deste projeto. Reconstrói o estado real a partir do repositório (nunca da conversa anterior), reconcilia com Git e disco, apresenta um briefing e PARA antes de qualquer implementação. Use ao abrir uma sessão nova, ao retomar o projeto depois de dias, depois de perda de contexto, ou quando a Emmily perguntar onde paramos.
allowed-tools: [Read, Glob, Grep, Bash]
---

# Abertura de sessão — reconstruir, reconciliar, reportar, PARAR

**A conversa é descartável. O repositório é a fonte canônica.** Reconstrua o estado lendo
arquivos e Git, nunca memória de conversa. Resumo textual orienta; **evidência verificável
prevalece**.

## ⛔ Proibido nesta fase

Não implementar, editar, corrigir, refatorar, instalar dependência, commitar, fazer push,
stash, reset, apagar nada, nem "aproveitar para arrumar rapidinho". Nenhuma escrita em arquivo.
Nenhuma chamada ao SharePoint (ver `.claude/rules/sharepoint-readonly.md`).

Permitido: comandos de inspeção e os testes offline do projeto, que são rápidos e seguros.

## Fluxo

Carregue na ordem abaixo e **pare assim que tiver o suficiente** para o briefing. Não leia o
repositório inteiro.

### 1. Ambiente e Git
```bash
pwd && git rev-parse --show-toplevel && git branch --show-current
git rev-parse HEAD && git rev-parse --short HEAD
git status --short && git log --oneline -5
```
Confirme que está em `PROG_Relatorio_G2_Automacao`. Se o diretório não for esse, **pare e avise**.

### 2. Regras permanentes
Leia `CLAUDE.md`. Ele já é carregado pelo harness, mas confirme as regras de SharePoint
read-only, segredos, nomenclatura e política Git. Leia `.claude/rules/` apenas se for agir em
área coberta por elas.

### 3. Estado atual
Leia `STATE.md`. É a fonte do estado operacional: fase, concluído, bloqueios P0 e P1, próxima
ação exata e último commit.

### 4. Reconciliação
Compare o que o `STATE.md` afirma com o que Git e disco mostram. O procedimento completo está
em [reconciliation.md](reconciliation.md) — **carregue esse arquivo** se houver qualquer
divergência, se a árvore não estiver limpa, ou se o último commit do STATE não bater com o HEAD.

### 5. Contexto da próxima tarefa
Só então abra o que a próxima ação exigir: a decisão em `docs/decisions/`, o catálogo em
`data/catalog/`, o resumo em `state/*.yaml` ou o documento de descoberta pertinente.
**Não leia `docs/discovery/` inteiro**: são documentos longos e já consolidados.

### 6. Baseline (opcional, se for trabalhar em código)
```bash
.venv/Scripts/python.exe -m pytest -q 2>&1 | tail -3
```
Distinga sempre **resultado registrado no STATE** de **verificação executada agora**.

## Briefing

Apresente, omitindo o que não se aplicar:

```
PROJETO · SESSÃO
Diretório · fase atual · objetivo desta sessão

GIT
Branch · HEAD · status da árvore

ÚLTIMO ESTADO VERIFICÁVEL
O que o STATE afirma e o que o Git confirma

CONCLUÍDO · EM ANDAMENTO · PENDENTE

PRÓXIMA TAREFA EXATA
Objetivo · critérios de conclusão · arquivos envolvidos · riscos

ARQUIVOS DE ALTO SINAL
Os poucos que a próxima tarefa exige

BLOQUEIOS P0 / P1

VALIDAÇÃO
Último resultado registrado × verificações executadas agora

INCONSISTÊNCIAS ENCONTRADAS
```

Se encontrar divergência entre STATE e realidade, **mostre-a**. Não corrija em silêncio.

## Parada obrigatória

Termine exatamente com:

> Contexto reconstruído. Nenhuma alteração foi realizada.

E **pare**. Não comece a próxima tarefa. Aguarde autorização explícita.
