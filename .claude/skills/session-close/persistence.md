# Onde cada tipo de informação pertence

Carregue este arquivo quando houver algo a persistir além do `STATE.md`. **Reutilize as
estruturas que já existem; não crie arquitetura paralela.** Nunca duplique a mesma informação
em dois lugares: escolha o canônico e, se necessário, aponte para ele.

| Tipo de informação | Onde vai | Formato |
|---|---|---|
| Estado atual do projeto | `STATE.md` | seções fixas; só o presente, sem diário |
| Histórico da sessão | `docs/sessions/LOG.md` | uma entrada curta, append-only |
| **Decisão durável** | `docs/decisions/DEC-NNN-*.md` | contexto, decisão, evidência, alternativas, consequências |
| Descoberta sobre o relatório | `docs/discovery/*.md` | com evidência e nível de confiança |
| Regra candidata do modelo | `docs/specs/DRAFT_*.md` e `config/report_spec_draft.yaml` | só `CONFIRMED` ou `HIGH_CONFIDENCE` |
| Componente, linhagem, anomalia, página | `data/catalog/*.jsonl` | via os scripts que os geram, nunca à mão |
| Lacuna que bloqueia o builder | `data/catalog/gaps.jsonl` | com prioridade P0 a P3 |
| Situação de reprodutibilidade | `data/catalog/reproducibility_matrix.jsonl` | gerado por `scripts/11_*` |
| Resumo operacional | `state/*.yaml` | gerado por script, não editado à mão |
| Autorização de download | `state/download_authorizations.jsonl` | gravado pelo próprio fluxo de download |
| Regra permanente de trabalho | `CLAUDE.md` ou `.claude/rules/` | só se for regra, não se for estado |

## Regras de classificação

**Decisão durável merece um `DEC-NNN`** quando muda como o projeto trabalha dali em diante,
quando fecha uma alternativa, ou quando a próxima sessão erraria sem ela. Não crie DEC só para
preencher documentação; o número é sequencial e não se reaproveita.

**Catálogos são gerados, não editados.** Se o conteúdo de um `.jsonl` precisa mudar, edite o
script que o gera (`scripts/08_record_anomalies.py`, `09_record_lineage.py`,
`11_reproducibility_matrix.py`) e execute de novo. Assim a próxima sessão reproduz o mesmo
resultado.

**Confiança não se infla.** `CONFIRMED` exige evidência direta ou repetição inequívoca.
Hipótese permanece hipótese. `UNKNOWN` registrado é melhor que um palpite com cara de regra.

**Anomalia nunca vira regra.** Todo registro em `anomalies.jsonl` leva
`should_learn_as_rule=false`. O gerador nunca lê esse arquivo como fonte de padrão.

## Processamento incremental

Se a sessão avançou em lotes (relatórios analisados, documentos cruzados, versões comparadas),
persista o suficiente para retomar sem refazer: o que foi processado, o que falta, qual foi o
último lote, o que falhou e por quê. Os resumos em `state/*.yaml` existem para isso.

Se arquivos em `tmp/` foram usados, lembre que `tmp/` **não é versionado**: registre o que foi
baixado e sob qual autorização, para que a próxima sessão saiba se precisa baixar de novo.

## Segurança ao persistir

Antes de qualquer commit, `scripts/check_secrets.py` precisa passar. Nunca registre valor de
segredo, token ou senha em `STATE.md`, em documentação, em log de sessão ou em mensagem de
commit. Nunca versione binário corporativo: o conteúdo de `tmp/` fica fora do Git.
