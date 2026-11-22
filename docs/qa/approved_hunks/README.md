# Hunks de texto aprovados (comparador 4.1)

O golden test compara o texto do PDF gerado com o do publicado **token a token** (seções,
CAPA, SUMÁRIO, títulos e células do Controle de Produtos), normalizando só o leiaute: espaços,
hífen de fim de linha, aspas e travessões. Caixa, acento e pontuação contam. Cada trecho
divergente é um *hunk* e sai **CRITICAL**, a menos que esteja aqui.

| arquivo | relatório | controle | versão | hunks |
|---|---|---|---|---|
| `n14.yaml` | Relatório G2 nº 14 — Agosto/2026 | `output/reconstruction/14_v6` (modelo v0.14) | 1.2 | 113 |
| `n13.yaml` | Relatório G2 nº 13 — Julho/2026 | `output/reconstruction/13_v6` (modelo v0.14) | 1.2 | 117 |

O que vale para cada hunk:

- É **exato**. Ele traz a unidade (`section`), a âncora do parágrafo (sha256[:12] do parágrafo
  de referência normalizado), 6 tokens de contexto de cada lado e os textos dos dois lados.
- É **posicional** (comparador 4.1, QA4-E). `position` traz o bloco estrutural do parágrafo de
  referência (rodovia > grupo no 2.2, rodovia nas listas do 2.4, código da linha no Controle
  de Produtos; `''` fora de bloco), o índice do parágrafo no bloco, o intervalo de tokens na
  unidade de referência e o bloco do parágrafo gerado. O hunk só cobre a diferença no mesmo
  lugar. O mesmo texto em outra rodovia é hunk novo e sai CRITICAL. Por isso `occurrence` saiu.
- Tem **justificativa**: `reference` cita uma anomalia catalogada do mesmo relatório
  (`data/catalog/anomalies.jsonl`) ou uma DEC existente. Sem isso, o parser recusa o hunk.
- O arquivo é **congelado**. O sha256 fica registrado em `config/golden_allowances.yaml`
  (`approved_hunks`). Uma edição sem nova versão das allowances faz o conjunto ser recusado,
  também quando o arquivo é passado por caminho (`--approved-hunks`).
- **Limitação:** quem edita o arquivo e as allowances juntos passa na conferência do sha256.
  Quem garante a integridade final é o Git (histórico e diff revisado) e a revisão humana do
  conjunto na certificação.
- Se um hunk aprovado não ocorre mais, o relatório dá o aviso "aprovação órfã". Se o gerado
  voltou ao texto publicado naquele bloco (reproduz a anomalia que o hunk corrige), a
  diferença é CRITICAL `reverted`.
- As diferenças v3 derivadas do texto (fatos, códigos, rodovias, parágrafos) são julgadas
  pelo seu próprio hunk. Uma diferença só sai ALLOWED se um hunk aprovado do mesmo lugar a
  explicar (para o status por rodovia ou grupo, o mesmo bloco). Um hunk em aberto não derruba
  as outras diferenças da seção.
- `pending` marca um hunk esperado de um builder que ainda não entrou: o hunk real no mesmo
  parágrafo do mesmo bloco sai CRITICAL e marcado como pendente. Hoje nenhum hunk está
  pendente.

Para regenerar o rascunho, rode `scripts/14_golden_compare.py ... --draft-hunks rascunho.yaml`.
Ele traz os hunks já aprovados com a referência e os novos com `reference: null`. Cada novo
hunk é classificado por anomalia ou DEC, ou listado como defeito, e o conjunto é congelado em
nova versão, com o novo sha256 nas allowances. **O nº 13 não aprova o resíduo da Lista Mestra
v134 × v162** (GAP-015): esses 23 hunks continuam CRITICAL de propósito. Eles estão listados
no cabeçalho de `n13.yaml`.
