---
name: session-close
description: Protocolo oficial de ENCERRAMENTO de sessão deste projeto. Interrompe desenvolvimento, reconcilia o estado real, persiste no repositório tudo que só existe na conversa, roda as validações, atualiza STATE.md e o log de sessões, aplica a política Git do projeto e PARA. Use ao encerrar uma sessão, antes de fechar o Claude, ou quando a Emmily pedir para fechar o trabalho.
disable-model-invocation: true
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
---

# Encerramento de sessão — reconciliar, persistir, validar, PARAR

**Se esta conversa desaparecer agora, nenhum conhecimento importante pode desaparecer junto.**

## ⛔ Proibido nesta fase

Não comece funcionalidade nova, não inicie a próxima tarefa, não refatore por oportunidade, não
aumente escopo, não corrija coisa não relacionada. Nunca descarte, esconda ou resete trabalho:
sem `stash`, sem `reset`, sem `checkout --`. Nunca declare teste que não rodou, nem transforme
investigação em implementação ou hipótese em fato.

## Fluxo

### 1. Reconciliar o estado real
```bash
pwd && git branch --show-current && git rev-parse --short HEAD
git status --short --untracked-files=all && git diff --stat
git log --oneline -10
```
Compare com o que o `STATE.md` afirma hoje. A realidade verificável prevalece.

### 2. Auditar a sessão

Pergunta obrigatória: **"existe informação importante que só está nesta conversa?"**

Se sim, persista **antes** de encerrar. Classifique corretamente cada coisa: concluído,
parcialmente concluído, investigado mas não implementado, decisão, descoberta, hipótese,
hipótese descartada, limitação, risco, bloqueio, pergunta aberta.

O mapa de onde cada tipo de informação pertence está em
[persistence.md](persistence.md) — **carregue esse arquivo** sempre que houver algo a persistir
além do `STATE.md`.

### 3. Validar

Rode apenas o que corresponde ao trabalho feito, nesta ordem:

```bash
.venv/Scripts/python.exe -m pytest -q 2>&1 | tail -3
.venv/Scripts/ruff.exe check . --output-format concise | tail -3
.venv/Scripts/python.exe scripts/check_secrets.py
```

Registre **o comando exato e o resultado real**. Se algo não puder ser executado, registre que
não foi executado, o motivo e o risco residual. Nunca escreva "testes passaram" sem execução.

### 4. Atualizar o estado

`STATE.md` representa **apenas o estado atual**, nunca um diário. Mantenha as seções que já
existem: `CURRENT_PHASE`, `LAST_COMPLETED`, `CRITICAL_FINDINGS`, `P0_BLOCKERS`, `P1_BLOCKERS`,
`NEXT_EXACT_ACTION`, `LAST_COMMIT`. Remova o que ficou obsoleto em vez de acumular.

O `NEXT_EXACT_ACTION` tem de ser uma ação executável, com arquivo e comando quando couber.
Nunca "continuar a análise".

### 5. Registrar a sessão

Acrescente **uma entrada curta** ao fim de `docs/sessions/LOG.md`, no formato que o próprio
arquivo define. É histórico; o estado atual continua sendo o `STATE.md`.

### 6. Git

Política do projeto (`CLAUDE.md`): repositório local, branch `main`, **sem remoto**. Commit
**só em marco lógico ou checkpoint de fase**, depois de revisar o diff, rodar
`check_secrets.py` e os testes.

- **Não commite só porque a sessão terminou.** Se o trabalho está pela metade, deixe não
  commitado e descreva isso no `STATE.md`.
- **Nunca** `push`, `force`, `reset --hard`, `rebase`, `amend` ou troca de branch.
- Mensagem em pt-BR ou inglês técnico curto, prefixo convencional, terminando com o trailer
  `Co-Authored-By:` do modelo que está rodando a sessão.
- Confirme no fim: branch, HEAD, e se a árvore ficou limpa ou não.

### 7. Definir a próxima sessão

Uma única unidade concreta: objetivo, critérios de conclusão, arquivos de alto sinal, riscos,
verificações esperadas e, se útil, qual subagente de `.claude/agents/` ajuda.

## Relatório final

```
SESSÃO · objetivo
REPOSITÓRIO · branch · HEAD · árvore limpa?
CONCLUÍDO · PARCIAL · INVESTIGADO MAS NÃO IMPLEMENTADO
DESCOBERTAS · DECISÕES DURÁVEIS · HIPÓTESES EM ABERTO
VALIDAÇÕES  (comando exato → resultado real)
ALTERAÇÕES NÃO COMMITADAS
DOCUMENTAÇÃO ATUALIZADA
INCONSISTÊNCIAS ENCONTRADAS
PRÓXIMO PASSO EXATO
ARQUIVOS DE ALTO SINAL PARA A PRÓXIMA SESSÃO
RISCOS / BLOQUEIOS
GIT FINAL
```

## Parada obrigatória

Termine exatamente com:

> Handoff concluído. Nenhuma nova implementação foi iniciada.

E **pare**.
