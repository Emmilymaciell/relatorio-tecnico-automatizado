# Produção mensal do Relatório G2 — runbook

Para gerar, revisar e entregar o **Relatório G2 nº N — Mês/AAAA** sozinha, todo mês, sem
sessão do Claude. Nos comandos, troque os marcadores:

| Marcador | Significa | Formato |
|---|---|---|
| `<N>` | número do relatório | inteiro (`9`, `21`) |
| `<NN>` | o mesmo número com 2 dígitos | `09`, `21` |
| `<AAAA-MM>` | mês de referência | `AAAA-MM` |
| `<EMISSAO>` | data da capa (vai no YAML de entradas, `issue_date`) | `AAAA-MM-DD` |
| `<ASSINATURA>` | data do Encerramento ("Capital, …"; YAML, `signature_date`) | `AAAA-MM-DD` |
| `<V_LM>`, `<V_PROJ>`, `<V_AMB>` | versão de uma planilha no SharePoint (só se quiser fixar uma; o padrão é a vigente) | `442.0` |

Pasta do projeto: `C:\caminho\exemplo\PROG_Relatorio_G2_Automacao` (todos os comandos rodam
nela, no PowerShell).

> **Estado do modelo:** `G2_REPORT_MODEL` v0.14, `BUILDER_READY` (ainda não `CERTIFIED`; ver
> `docs/qa/CERTIFICACAO_PACOTE.md`). Enquanto não for certificado, confira o relatório com mais
> cuidado (seção 4) antes de entregar.

---

## 1. Pré-requisitos da máquina (uma vez, e conferir se trocar de computador)

1. **Windows 11** com **Microsoft Excel e Word** (desktop, Office 365) instalados e ativados.
2. **Fontes Arial Nova** (família usada no corpo, títulos e capa: "Arial Nova Light" e
   "Arial Nova Cond"). Vêm pelo Office como fontes da nuvem: abra o Word, escreva qualquer
   texto, aplique "Arial Nova Light" e depois "Arial Nova Cond"; se aparecer o ícone de nuvem
   ao lado do nome, clique para baixar. Sem elas o Word troca a fonte e a paginação muda.
3. **Sessão interativa com tela**: o Controle de Produtos é copiado do Excel como desenho
   vetorial pela área de transferência (DEC-010). Por isso:
   - tela em **1920 × 1080**, escala **125 %** (= 120 dpi) — Configurações › Sistema › Tela;
   - não rodar por área de trabalho remota minimizada, tela bloqueada ou tarefa agendada;
   - **um build por vez** e **não copiar/colar nada** enquanto ele roda.
4. **Python do projeto** em `.venv\` (já existe). Teste rápido:
   ```powershell
   .venv\Scripts\python --version          # Python 3.12.x
   ```
5. **Credencial** em `.env` na raiz do projeto, preenchida por você (nunca em conversa, nunca
   no Git). Só estas 3 variáveis de autenticação, sem aspas:
   ```
   AZURE_TENANT_ID=
   AZURE_CLIENT_ID=
   AZURE_CLIENT_SECRET=
   ```
   (`.env.example` mostra o modelo completo.) Teste somente leitura:
   ```powershell
   .venv\Scripts\python scripts\01_verify_readonly_access.py
   ```
   Deve resolver o site e listar as bibliotecas, sem erro. O segredo expira: se aparecer erro de
   autenticação (`AADSTS7000222` ou parecido), gere um novo segredo no Entra ID e atualize o
   `.env`.
6. **Imagens institucionais** em `assets\discovered\raw\` (16 arquivos, fora do Git porque têm
   fotos de pessoas). Se a pasta estiver vazia (máquina nova), o build para com `AssetError`;
   peça a uma sessão do Claude para regenerá-las com `scripts/13_extract_static_assets.py`.

---

## 2. Antes de gerar

### 2.1 O que precisa estar pronto no SharePoint (só conferir; o builder nunca escreve lá)

**Lista Mestra** (`00_ Lista mestre.xlsx`, aba `Controle Geral`) — é o manifesto do relatório
(DEC-006):
- todo documento do mês com **`N° Relatório` = `<N>`** (é esse filtro que define o que entra no
  Controle de Produtos de cada produto e na contagem);
- **`Status Entrega`** atualizado: só os "Entregue" entram nos ANEXOS e no total de anexos do
  Encerramento; os "Em elaboração" aparecem no Controle de Produtos (e os BM em elaboração no 2.4);
- **`Data Entrega`** de nenhum documento depois da data de emissão (o build avisa:
  `V_NO_DELIVERY_AFTER_ISSUE`, seção 4.3);
- **Descrição** clara: ela alimenta os temas citados no resumo, nas atas e nos pareceres;
- RO com o **Período** legível ("dd/mm/aaaa a dd/mm/aaaa").

**Planilha de projetos** (`03 - Acompanhamento de Projetos Executivo.xlsx`): abas `GED`,
`Projetos` (coluna S = Status AVALIAÇÃO, por disciplina, inclusive "Aprovado com ressalva") e
`Painel de Controle` atualizadas no fechamento do mês.

**Planilha ambiental** (`04_Acompanhamento - Licenca Ambiental.xlsx`): abas `Licenças`,
`Condicionantes` e `Empresas` atualizadas; anote a data **"Atualizado em"** do painel do Power BI.

Depois de conferir, **peça que ninguém edite as três planilhas** até você terminar o passo 3:
o relatório sai do estado delas naquele instante (DEC-012).

### 2.2 Baixar a Lista Mestra (a única cópia local)

O comando único (seção 3.2) lê a **planilha de projetos** e a **planilha ambiental** direto do
SharePoint, em memória, na **versão vigente** (a mais recente do Histórico de versões), e grava
no manifesto o número e a data dessa versão. Nada dessas duas vai para o disco.

A **Lista Mestra** é a exceção: o Controle de Produtos é desenhado pelo Excel a partir do
ARQUIVO (DEC-010), então ela precisa de cópia local, que **você** baixa. O builder nunca grava a
planilha por conta própria.

1. Crie a pasta do mês (fora do Git; `tmp\` é ignorada):
   ```powershell
   New-Item -ItemType Directory -Force "tmp\producao\<NN>_<AAAA-MM>"
   ```
2. No SharePoint, Lista Mestra: `…` › **Baixar**, e salve em
   `tmp\producao\<NN>_<AAAA-MM>\lista_mestre.xlsx`. Nunca salve nem leia de
   `C:\caminho\exemplo\Dynatest Engenharia\` (sincronização do SharePoint; o projeto recusa
   essa pasta). Não abra a cópia no Excel durante o build.
3. Não precisa anotar versão: o comando confere a cópia contra a versão vigente lida em memória
   e **para** (`erro: a cópia local … não é a versão …`) se alguém editou a Lista Mestra depois
   do download. Nesse caso, baixe de novo.

Para ver o histórico (só leitura, sai só na tela; a 1ª linha é a versão vigente):
```powershell
.venv\Scripts\python scripts\16_list_versions.py --source master_list --last 5
.venv\Scripts\python scripts\16_list_versions.py --source projects --last 5
.venv\Scripts\python scripts\16_list_versions.py --source environmental --last 5
```
**Nunca** clique em "Restaurar" nem "Excluir" no Histórico de versões do SharePoint (são escritas).

O `manifest.json` de saída registra, de cada fonte, versão, data (lastModified), sha1 e, em
`source_resolution`, que versão foi pedida (`current`) e qual foi usada — é a prova de qual
estado das planilhas gerou o relatório.

### 2.3 Entradas humanas do mês (arquivo YAML fora do Git)

Crie `tmp\producao\<NN>_<AAAA-MM>\entradas_<NN>.yaml` (UTF-8). O formato completo está em
`tests\fixtures\golden_inputs_example.yaml` e em `config\g2_report_model.yaml` › `inputs`.
O arquivo tem o nome do signatário (dado pessoal): **nunca** versionar. Guarde-o junto com a
saída do mês; o manifesto registra caminho e sha1 dele.

| Chave | Obrigatória | Para quê | Se faltar |
|---|---|---|---|
| `issue_date` | **sim** | data da capa (emissão) | o comando não gera (erro antes de começar) |
| `signature_date` | **sim** | "Capital, …" | o comando não gera |
| `signatory_name` | **sim** (todo mês; nunca herdado do relatório anterior) | Encerramento ("Eng° …") | o comando não gera |
| `ai_review` | **sim** quando há rascunho (os 2 slots do resumo) | textos interpretativos aprovados (seção 4.2) | slot PENDING_HUMAN + pauta `review_brief_<slot>.md` |
| `environmental_reference_date` | recomendada | "Atualizado em" dos painéis e status das licenças | usa a data de emissão, com aviso |
| `p22_status_reference_date` | recomendada | "Atualizado em" dos quadros do 2.2 e cálculo de pendentes/atrasados | usa a data ambiental, senão a de emissão, com aviso |
| `p22_external_status` | quando houver | matrizes de DUP, desapropriação e interferências do 2.2 | bloco não sai |
| `meetings_agenda` | não | agenda de reuniões do 2.1 | agenda estável do modelo |
| `p24_bm_in_progress` | não | BM em elaboração **de fora** da Lista Mestra | só os BM "Em elaboração" da Lista Mestra |

As datas de emissão e de assinatura vão no YAML (o `scripts\15_build_report.py` ainda aceita
`--issue-date`/`--signature-date`, que prevalecem).

Exemplo **sintético** (valores inventados; rodovias são as do contrato):

```yaml
# Entradas humanas — Relatório G2 nº <N> — <Mês>/<AAAA>. NÃO VERSIONAR.
issue_date: 2099-01-11                  # capa
signatory_name: "Fulano de Tal"
signature_date: 2099-01-12              # Encerramento ("Capital, …")
environmental_reference_date: 2099-01-08
p22_status_reference_date: 2099-01-08

# Agenda (opcional). Ordem do modelo: RD-104, RD-103, RD-102A, RD-101.
meetings_agenda:
  - {highway: RD-104, executora: "Consórcio Exemplo", weekday: quintas, hour: "10h"}
  - {highway: RD-103, executora: "Construtora Exemplo", weekday: quintas, hour: "11h"}
  - {highway: RD-102A, executora: "Consórcio Exemplo 2", weekday: sextas, hour: "10h"}
  - {highway: RD-101, executora: "Construtora Exemplo 2", weekday: segundas, hour: "14h"}

# Status externos do 2.2, por rodovia (opcional; GAP-009). Campos por matriz:
#   dup:                   gdp, casa_civil
#   expropriation_project: gdp, started
#   interferences:         gfd, utility (concessionária), started (início dos processos)
# Sem pontuação final (o builder põe ';' e '.'). "Análise PROGRAMA" NÃO se informa: sai da aba
# Projetos. Campo sem informação: nunca "" — use {null_reason: "<motivo>"}, que sai como
# "Sem informação até o fechamento do presente relatório".
p22_external_status:
  RD-101:
    dup: {gdp: "Status sintético A",
          casa_civil: {null_reason: "sem retorno da Casa Civil até o fechamento"}}
    interferences: {gfd: "Status sintético B", utility: "Status sintético C",
                    started: "Status sintético D"}
  RD-103:
    dup: {gdp: "Status sintético E", casa_civil: "Status sintético F"}

# BM em elaboração externos (opcional): só itens que NÃO estão na Lista Mestra.
p24_bm_in_progress:
  - {rodovia: RD-104, código: BM-999.1, mês: "Janeiro/2099"}

# Textos interpretativos aprovados (DEC-013). Preencha DEPOIS da 1ª rodada (seção 4.2).
ai_review:
  P2.1_SUMMARY_S2_PADRONIZACAO:
    text: "a **Instrução de Trabalho Exemplo** e a **Circular Técnica nº 99/2099**"
    documents: [IT-999.1, CT-999.1]
  P2.1_SUMMARY_S4_TEMAS:
    text: "drenagem, pavimentação e sinalização"
    documents: [PA-998.1, PA-999.1]
  P2.4_NC: "de natureza documental e de segurança do trabalho"   # opcional
```

Regras do `ai_review`:
- chaves: `P2.1_SUMMARY_S2_PADRONIZACAO` (padronização IT/CT/POP do resumo),
  `P2.1_SUMMARY_S4_TEMAS` (temas dos pareceres do 2.2 no resumo), `P2.4_NC` (natureza das NC,
  **opcional**: sem texto aprovado a cláusula simplesmente não sai — não há rascunho nem
  pendência; só aparece junto com a enumeração das NC);
- valor: texto simples, ou `{text: …, documents: [códigos]}`; `**negrito**` é aceito;
- **use `documents`**: se os códigos não forem exatamente os do mês, o builder entende que é a
  aprovação de outro relatório, ignora o texto e volta ao rascunho. É a proteção contra copiar o
  texto do mês anterior.

---

## 3. Gerar

### 3.1 Antes de rodar
- Feche Word e Excel (o builder abre instâncias próprias e invisíveis; documentos seus abertos
  não atrapalham, mas um travamento é mais fácil de resolver sem eles).
- Não use a área de transferência e não bloqueie a tela até o fim.

### 3.2 Comando único (PowerShell, na pasta do projeto)

```powershell
.venv\Scripts\python scripts\17_generate_report.py --report-number <N> --reference-month <AAAA-MM> `
  --inputs "tmp\producao\<NN>_<AAAA-MM>\entradas_<NN>.yaml" `
  --master-list "tmp\producao\<NN>_<AAAA-MM>\lista_mestre.xlsx"
```

O que ele faz, nesta ordem:
1. lê o YAML de entradas e confere `issue_date`, `signature_date` e `signatory_name` (faltou =
   para com `erro: entrada obrigatória ausente`, código 2);
2. resolve a **versão vigente** (`current`) de cada planilha no SharePoint (só leitura);
3. confere a sua cópia da Lista Mestra contra a versão vigente (diferente = para, código 2);
4. lê projetos e ambiental dessa versão **em memória** e gera DOCX e PDF (Excel e Word);
5. roda as validações do modelo e imprime o resumo.

Opções:
- `--out <pasta>`: saída (padrão `output\<NN>_<AAAA-MM>\`). Rodar de novo sobrescreve.
- `--master-list-version`, `--projects-version`, `--environmental-version <V>`: fixam uma
  versão em vez da vigente (reconstrução de um mês passado; ver `16_list_versions.py`).
- `--no-office`: rodada rápida só de texto (sem Excel/Word, ~1 min). Sai só o DOCX, com
  Controle de Produtos e contagem de páginas pendentes. Útil para colher os rascunhos da seção
  4.2 antes da rodada final; **nunca** é entrega.

Opções avançadas (extratos, cópias locais, overrides de uma aba) continuam no
`scripts\15_build_report.py` (ver o cabeçalho do script); não são o fluxo mensal.

### 3.3 O que sai

Em `output\<NN>_<AAAA-MM>\` (fora do Git):
- `relatorio_g2_n<NN>_<AAAA-MM>.docx` — o DOCX gerado (campos provisórios; o Word pergunta se
  deseja atualizá-los ao abrir);
- `relatorio_g2_n<NN>_<AAAA-MM>_final.docx` — **cópia salva pelo Word com sumário e campos já
  atualizados**; abre sem perguntar nada. É esta que se edita, se precisar (seção 5);
- `relatorio_g2_n<NN>_<AAAA-MM>.pdf` (sem assinatura);
- `manifest.json` (fontes e versões, validações, componentes, pendências, avisos);
- `review_brief_<slot>.md` — uma pauta de revisão por texto interpretativo sem aprovação
  (seção 4.2); some quando o texto é aprovado e o comando roda de novo;
- `_work\` (intermediários; pode ignorar).

No terminal sai o resumo:
```
Relatório G2 nº <N> — <Mês>/<AAAA> · modelo 0.14 · ok=True
páginas: <total do PDF>
fonte master_list / projects / environmental: versão, lastModified, origem
validação V_…: pass | warning | error | pending | skipped
pendências/falhas: …        avisos: …        pauta de revisão …: <arquivo>
DOCX / DOCX final / PDF / manifesto: <caminhos>
```
Código de saída 0 = pronto (`ok=True`); 1 = há pendência, falha ou validação com erro;
2 = entrada obrigatória ausente ou cópia da Lista Mestra diferente da versão vigente.

### 3.4 Quanto tempo leva
Cerca de **5 minutos** (o nº 14 levou ~4 min: leitura das fontes + 3 passadas no Word para
acertar páginas e o 1º recorte do Controle de Produtos), mais o tempo de leitura do SharePoint.

### 3.5 Se o Excel ou o Word travar
1. Espere 10 minutos sem mexer na máquina (uma passada do Word pode demorar).
2. Se nada mudar, `Ctrl+C` no PowerShell.
3. Gerenciador de Tarefas › Detalhes: finalize os `EXCEL.EXE` e `WINWORD.EXE` que sobraram
   (os do build não têm janela). Salve seus documentos abertos antes.
4. Confira tela (1920×1080, 125 %), tela desbloqueada, nada usando a área de transferência.
5. Rode o mesmo comando de novo. Se travar duas vezes no mesmo ponto, gere com `--no-office`
   para isolar (se o DOCX sai, o problema é Office/ambiente, não dado) e abra uma sessão do
   Claude (seção 6).

Erros que **não** são travamento:
- `erro: entrada obrigatória ausente: …` — complete o YAML (seção 2.3).
- `erro: a cópia local … não é a versão …` — a Lista Mestra mudou depois do download: baixe de
  novo (seção 2.2).
- `versão … não existe mais no histórico do SharePoint` — versão fixada à mão digitada errada
  (ou podada); confira com `16_list_versions.py`.
- `AssetError` — falta `assets\discovered\raw\` (seção 1, item 6).
- Erro de autenticação — `.env` (seção 1, item 5).

---

## 4. Revisar

### 4.1 Ler o manifesto

```powershell
$m = Get-Content "output\<NN>_<AAAA-MM>\manifest.json" -Raw -Encoding UTF8 | ConvertFrom-Json
$m.ok; $m.pending; $m.failed; $m.warnings
$m.validations | Select-Object id, severity, outcome, detail
$m.sources | Select-Object key, version_id, last_modified, local_path, sha1
$m.source_resolution
$m.components | Where-Object { $_.status -notin 'OK','SKIPPED' } | Select-Object component_id, status, detail
```

Confira:
- `report`: número, mês, data de emissão e de assinatura corretos;
- `sources`: uma versão por planilha, com data (`last_modified`) do fechamento do mês;
  `source_resolution` mostra `requested: current` e a versão usada; `deviations` vazio;
- `validations`: nenhuma com `error` (erro já deixa `ok=False`); leia as `warning`;
- `ok`: só entrega com `True`.

### 4.2 Componentes PENDING_HUMAN e como resolver

| Componente | Causa | Como resolver |
|---|---|---|
| `P2.1_SUMMARY_S2_PADRONIZACAO` | rascunho de padronização (IT/CT/POP) sem revisão | ver abaixo |
| `P2.1_SUMMARY_S4_TEMAS` | rascunho dos temas dos pareceres do 2.2 sem revisão | ver abaixo |
| `P2.2_DESAPROPRIACAO` / `P2.2_INTERFERENCIAS` | campo vazio ou ausente numa rodovia informada | preencher o status ou `{null_reason: …}` |
| matriz "Análise Programa" | disciplina sem linha (ou com mais de uma) na aba Projetos, ou status fora dos conjuntos | corrigir a planilha de projetos (é fonte); se o status for novo, sessão do Claude |
| blocos do 2.4 de RO | Período ilegível na Lista Mestra | corrigir a Lista Mestra e baixar de novo |

**Slots interpretativos (DEC-013).** O builder escreve um rascunho a partir das Descrições da
Lista Mestra, marca o relatório como não pronto e grava a **pauta de revisão**
`output\<NN>_<AAAA-MM>\review_brief_<slot>.md` (o manifesto aponta para ela em
`review_briefs`). Abra o arquivo: tem a pergunta, o rascunho, a tabela dos documentos (código,
produto, empreendimento, Descrição) e o formato da resposta.

- O rascunho e os códigos que ele cobre também estão no manifesto (`facts.text`,
  `facts.documents` do componente). A pergunta de cada slot:
  - S2: confirme a enumeração dos documentos de padronização entregues no período, o tema de
    cada Circular Técnica e se há documento "em elaboração" a citar;
  - S4: quais temas dos Pareceres Técnicos do Produto 2.2 citar em "abrangendo temas como …".
- Confira as Descrições da pauta (vêm da Lista Mestra do mês).
- Grave o texto aprovado em `ai_review` (seção 2.3) **com** a lista `documents` igual à da
  pauta e rode o comando da seção 3.2 de novo (a pauta antiga é apagada).

**Agenda de reuniões.** Sem `meetings_agenda`, sai a agenda estável do modelo (executora, dia e
hora). Se mudou dia ou horário no mês, informe a agenda inteira.

**BM em elaboração.** Os BM com `N° Relatório` = `<N>` e `Status Entrega` ≠ "Entregue" já saem
sozinhos no 2.4. Se algum aparecer errado, corrija a Lista Mestra (é fonte). Use
`p24_bm_in_progress` só para BM que não estão na Lista Mestra.

Status `PENDING` (sem "_HUMAN") ou `FAILED` = ambiente ou defeito: rodou com `--no-office`,
Office travou, ou contagem de páginas/anexos não fechou (`CLOSING_PAGE_COUNT`, `V_ANNEX_COUNT`).
Rode de novo sem `--no-office`; se persistir, sessão do Claude.

### 4.3 Avisos (`warnings`)

Não bloqueiam (`ok` pode ser `True`), mas leia todos:
- `2.2: sem p22_status_reference_date …` / `2.4: sem environmental_reference_date …` — informe as
  datas "Atualizado em";
- `desvio de snapshot (DEC-012)` — alguma fonte saiu de versão diferente da combinada; não deve
  acontecer com o comando da seção 3.2;
- `V_WEEK_START_25` — RO com semana começando entre 25 e 31 e terminando no mês (semana de
  fronteira entre relatórios): confira se a semana não é a mesma do relatório anterior;
- `V_NO_DELIVERY_AFTER_ISSUE` — documento com `Data Entrega` depois da data de emissão: corrija
  a Lista Mestra (é fonte) ou confirme que é intencional;
- `V_EMF_FRAME` — o Controle de Produtos saiu com largura/dispositivo fora do histórico (tela
  diferente de 1920×1080 a 125 %): ajuste a tela e gere de novo;
- `… frase de chamada não encontrada no PDF …` — o 1º recorte do Controle de Produtos caiu no
  padrão; confira visualmente a página.

### 4.4 Abrir e conferir o relatório

Abra o **PDF** ou o `…_final.docx` (os dois têm sumário e números de página atualizados).

**Automático** (validações do modelo, em `$m.validations` e no resumo; erro deixa `ok=False`):
número e mês iguais na capa, Apresentação e Encerramento (`V_NUMBER_MONTH_CONSISTENT`); todo
código citado está na Lista Mestra do mês (`V_ALL_DOCS_IN_MASTER_LIST`); total de páginas
(`V_PAGE_COUNT`) e de anexos (`V_ANNEX_COUNT`); `Data Entrega` depois da emissão
(`V_NO_DELIVERY_AFTER_ISSUE`, aviso); frame do Controle de Produtos (`V_EMF_FRAME`, aviso).

Confira à mão:
- [ ] data da capa = `<EMISSAO>`; "Capital, …" = `<ASSINATURA>`; signatário correto;
- [ ] sumário com as páginas certas;
- [ ] Controle de Produtos: tabelas nítidas, largura de página, nenhuma descrição cortada,
      fonte igual à do mês anterior (se estiver diferente, a escala da tela não estava em 125 %);
- [ ] 2.2: status por rodovia e linhas de "Aprovação" batem com a aba Projetos (ressalva por
      disciplina, DEC-015); matrizes com os status que você informou;
- [ ] 2.4: faixa dos relatórios semanais começa no mês certo (não repete a do mês anterior);
      painéis ambientais com a data "Atualizado em" certa;
- [ ] nenhum marcador `[PENDENTE` no texto (Ctrl+F "PENDENTE" no PDF; o rascunho dos slots não tem marcador: ele aparece só no manifesto).

Os painéis (quadros do 2.2 e ambientais do 2.4) são imagens: o builder não confere número dentro
deles. Olhe cada um contra a planilha.

### 4.5 Quando o build sai `ok=False`

O DOCX e o PDF saem mesmo assim, mas **não são entrega**. Liste o que falta (`$m.pending`,
`$m.failed`), resolva pela tabela 4.2 (entrada no YAML ou correção na fonte), e rode de novo.
Repita até `ok=True`. Não conserte no Word o que se resolve na entrada ou na fonte: a correção
manual não fica no manifesto e se perde no mês seguinte.

---

## 5. Entregar

1. **PDF final** = o `relatorio_g2_n<NN>_<AAAA-MM>.pdf` do build com `ok=True`. Não precisa
   reexportar.
2. **Só se precisar editar à mão no Word** (exceção; registre o motivo):
   - abra o `relatorio_g2_n<NN>_<AAAA-MM>_final.docx` (campos já atualizados), edite;
   - `Ctrl+A`, `F9`; no sumário, botão direito › Atualizar campo › Atualizar o índice inteiro;
   - se a edição mudou o total de páginas, corrija o número no Encerramento;
   - Arquivo › Salvar como › PDF › Opções › "Criar indicadores usando: Títulos";
   - salve com outro nome (ex.: `…_editado.pdf`) para não confundir com o do manifesto.
3. **Assinatura digital (DEC-014)**: depois do PDF pronto, quem assina abre o PDF no Adobe
   Acrobat/Reader e aplica a assinatura digital com a própria credencial, logo após o
   ENCERRAMENTO (lugar das assinaturas dos nº 11 a 14). O builder não guarda nem reproduz a
   imagem da assinatura. Depois de assinado, não edite mais o PDF (invalida a assinatura).
4. **Publicar**: você decide onde e como (pasta mensal do SharePoint, e-mail etc.), pela
   interface do SharePoint. O builder e as sessões do Claude **nunca** escrevem no SharePoint.
5. **Guardar a prova**: mantenha `output\<NN>_<AAAA-MM>\` (DOCX, PDF, `manifest.json`) e
   `tmp\producao\<NN>_<AAAA-MM>\` (entradas e cópias) pelo menos até o relatório seguinte. As
   cópias das planilhas podem ser apagadas depois; o manifesto guarda versão e sha1.

---

## 6. Quando algo muda de padrão

**Muda só neste mês** (exceção do mês): resolva pela entrada (YAML) ou pela fonte. Não é mudança
de modelo.

**Muda de vez** (nova seção, nova rodovia, nova coluna na Lista Mestra, frase que passa a ser
outra, novo status na planilha, outra forma de paginação, contrato novo…): é **nova versão do
modelo** (CLAUDE.md, "Modelo certificado"). Algumas escolhas editoriais se trocam só no
`config\g2_report_model.yaml` › `editorial_defaults`, sem código (frase do conjunto vazio do 2.2,
enumeração das NC, modo do S7, número do contrato) — mesmo assim, faça por uma sessão, para ficar
registrado. O resto exige código, reconstrução do nº 14 e conferência.

Como pedir:
1. Abra o Claude Code na pasta do projeto e rode **`/session-start`**. A sessão reconstrói o
   estado pelo repositório e para antes de implementar.
2. Escreva o pedido assim:
   > Mudança permanente de padrão a partir do Relatório G2 nº `<N>` — `<Mês/AAAA>`:
   > **o que mudou:** … **evidência:** (arquivo, página, aba/coluna) … **vale para:** todos os
   > meses seguintes. Quero nova versão do modelo.
3. A sessão registra a decisão (`docs/decisions/DEC-NNN`), sobe a versão do modelo
   (`model.changelog`), refaz o golden do nº 14 (`scripts\14_golden_compare.py`), e só então
   você gera o mês com a versão nova.
4. Ao terminar, peça **`/session-close`** (atualiza `STATE.md` e o log; commit só quando você
   pedir "salva essa versão").

Leve para a sessão também: build que trava sempre no mesmo ponto, `FAILED` que não some,
status de planilha que vira PENDING_HUMAN na matriz "Análise Programa", troca de máquina.

---

## Limitações atuais do fluxo (para não se surpreender)

- **Lista Mestra em arquivo local.** O Controle de Produtos é desenhado pelo Excel a partir do
  arquivo (DEC-010): a cópia que você baixa continua obrigatória (o comando confere que é a
  versão vigente). Projetos e ambiental não precisam de cópia.
- **Painéis em imagem.** O builder não confere números dentro dos quadros do 2.2 e dos painéis
  ambientais (seção 4.4).
- **Sessão interativa.** Excel e Word precisam de tela desbloqueada a 1920×1080, 125 %, e da
  área de transferência livre durante o build.

## Checklist do mês (1 página)

**Máquina**
- [ ] Excel e Word abrem; Arial Nova Light e Arial Nova Cond instaladas
- [ ] Tela 1920×1080, escala 125 %, sessão desbloqueada
- [ ] `scripts\01_verify_readonly_access.py` sem erro
- [ ] `assets\discovered\raw\` com 16 arquivos

**Fontes (SharePoint, só leitura)**
- [ ] Lista Mestra: `N° Relatório` = `<N>` em todos os documentos do mês; `Status Entrega` e
      `Data Entrega` certos; Descrições claras; Período dos RO legível
- [ ] Planilha de projetos (GED, Projetos, Painel de Controle) atualizada
- [ ] Planilha ambiental atualizada; data "Atualizado em" anotada
- [ ] Pedido de não editar as planilhas até o build terminar
- [ ] Lista Mestra baixada para `tmp\producao\<NN>_<AAAA-MM>\lista_mestre.xlsx`

**Entradas** (`tmp\producao\<NN>_<AAAA-MM>\entradas_<NN>.yaml`)
- [ ] `issue_date`, `signature_date`, `signatory_name`
- [ ] `environmental_reference_date`, `p22_status_reference_date`
- [ ] `p22_external_status` (campos sem informação com `null_reason`)
- [ ] `meetings_agenda` (se mudou), `p24_bm_in_progress` (se houver BM externo)

**Gerar**
- [ ] Word/Excel fechados; sem copiar/colar durante o build
- [ ] `17_generate_report.py --report-number <N> --reference-month <AAAA-MM> --inputs … --master-list …`
- [ ] Se PENDING_HUMAN nos slots: ler `review_brief_<slot>.md`, gravar `ai_review` com `text` +
      `documents`; gerar de novo

**Revisar**
- [ ] `ok=True`; `pending` e `failed` vazios
- [ ] `sources`/`source_resolution` com uma versão por planilha; `deviations` vazio
- [ ] `validations` sem `error`; `warning` lidas
- [ ] Todos os `warnings` lidos e resolvidos ou aceitos
- [ ] Checklist manual da seção 4.4 no PDF (datas, signatário, sumário, Controle de
      Produtos, 2.2, 2.4, painéis, sem `[PENDENTE`)

**Entregar**
- [ ] PDF do build (ou reexportado após edição registrada, com campos atualizados)
- [ ] Assinatura digital aplicada por quem assina, depois do PDF final
- [ ] Publicado por você onde decidir (o builder não publica)
- [ ] `output\<NN>_<AAAA-MM>\` e `tmp\producao\<NN>_<AAAA-MM>\` guardados até o próximo mês
- [ ] Mudança permanente percebida? → `/session-start` e pedido de nova versão do modelo
