# Reconciliação — estado persistido × realidade

Carregue este arquivo quando a árvore não estiver limpa, quando o `LAST_COMMIT` do `STATE.md`
não bater com o HEAD, ou quando qualquer afirmação do estado parecer não corresponder ao disco.

**Regra única:** o resumo textual orienta, a evidência verificável decide. Divergência se
**mostra**, nunca se corrige em silêncio.

## 1. O commit declarado existe e é o HEAD?

```bash
git log --oneline -5
grep -n "LAST_COMMIT" STATE.md
```

| Situação | Leitura |
|---|---|
| Batem | estado confiável |
| HEAD está à frente | houve trabalho commitado sem atualizar o STATE. Liste os commits a mais |
| HEAD está atrás | o STATE cita commit inexistente. Suspeite de edição manual ou de reset |
| Commit do STATE não existe | **inconsistência grave**: relate e não presuma qual está certo |

## 2. Há trabalho não commitado?

```bash
git status --short --untracked-files=all
git diff --stat
git diff --cached --stat
```

Classifique o que aparecer, **sem alterar nada**:

- alterações que pertencem ao trabalho descrito no STATE;
- alterações da Emmily, não relacionadas — **preservar e apenas apontar**;
- arquivos gerados que deveriam estar ignorados.

Nunca faça stash, reset ou checkout para "limpar". Trabalho não commitado é trabalho.

## 3. O que o STATE afirma como concluído é verificável?

Para cada item relevante de `LAST_COMPLETED`, confirme que o artefato existe:

```bash
ls docs/decisions/ docs/specs/ && wc -l data/catalog/*.jsonl && ls state/
```

Se o STATE cita um documento, catálogo ou script que não existe, isso é inconsistência.

## 4. Estado de processamento incremental

Este projeto processa lotes (relatórios, documentos, anexos). Antes de retomar, leia os
resumos — são curtos e dizem exatamente onde o trabalho parou:

| Arquivo | O que responde |
|---|---|
| `state/readiness.yaml` | quantos componentes são reproduzíveis, quais bloqueiam |
| `data/catalog/gaps.jsonl` | lacunas priorizadas P0 a P3 |
| `data/catalog/reproducibility_matrix.jsonl` | situação por componente |
| `state/inventory_summary.yaml` | pastas mensais inventariadas |
| `state/corpus_summary.yaml` | corpus de relatórios localizado |
| `state/history_comparison.yaml` | snapshots históricos comparados |
| `state/download_authorizations.jsonl` | o que já foi baixado, e por qual autorização |

**Nunca reinicie silenciosamente trabalho já concluído, nem pule pendências.**

## 5. O que existe fora do Git

Três coisas de que o trabalho depende **não são versionadas** e podem não existir — num clone
novo, em outra máquina, ou depois de uma limpeza. Verifique antes de prometer qualquer passo:

```bash
ls .venv/Scripts/python.exe 2>/dev/null || echo "AMBIENTE AUSENTE"
ls .env 2>/dev/null || echo "CREDENCIAL AUSENTE"
ls tmp/downloads/*/ tmp/extracted/ 2>/dev/null | head -20 || echo "TMP VAZIO"
```

| Ausente | Consequência | O que reportar |
|---|---|---|
| `.venv/` | nenhum comando de teste, lint ou script roda | reconstruir: `python -m venv .venv` e `pip install -e ".[dev,discovery]"` |
| `.env` | nenhum acesso ao SharePoint | **só a Emmily preenche**; nunca pedir o valor do segredo na conversa |
| `tmp/` | as extrações e downloads sumiram | baixar de novo **exige autorização**; é bloqueio, não detalhe |

Se o próximo passo do `STATE.md` depende de algo que não está mais lá, **isso é um bloqueio a
reportar no briefing**, não algo a resolver por conta própria.

## 6. Semântica que não pode ser corrompida

Ao resumir o estado, preserve as distinções do projeto. Nunca converta:

- hipótese em fato;
- `MEDIUM_CONFIDENCE` ou `UNKNOWN` em regra;
- anomalia histórica em padrão (`should_learn_as_rule` é sempre `false`);
- investigação em implementação;
- resultado de teste registrado em teste recém-executado;
- rascunho de especificação (`CANDIDATE`) em modelo certificado.

## 7. Como relatar divergências

Para cada uma: **o que o STATE diz**, **o que a evidência mostra**, **qual é a leitura mais
provável** e **o que precisa de decisão da Emmily**. Não escolha sozinho qual versão vale.
