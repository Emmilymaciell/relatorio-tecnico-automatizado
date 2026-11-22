# Wave 1 — achados consolidados (Fase 4, 2026-10-01)

Registro do orquestrador. Cada item vira mudança em catálogo, spec ou DEC na consolidação do
Gate A; este arquivo guarda a evidência resumida para não depender da conversa.

## G — reprodutibilidade (32 componentes)
- Totais do `readiness.yaml` batem com a matriz, mas "10 bloqueados" conta o
  `P2.2_PANEL_EMF_DISCONTINUED` (descontinuado, não bloqueado): são 9 reais, e o GAP-001 conta em
  dobro (`CONTROL_OF_PRODUCTS` e `PRODUCT_TABLE_REPRESENTATION` → fundir).
- **GAP-003 obsoleto como bloqueio**: DEC-009 tirou o Power BI da geração; o catálogo ainda tem
  `blocks_builder=true`.
- `P2.4_DOCUMENT_CITATIONS` sem o blocker GAP-010; GAP-008 mistura "não gera" com "não valida".
- Sem módulo no BUILDER_PLAN: painéis ambientais, entradas manuais (datas, status externo),
  passo Word/PDF.

## F — auditoria das specs (5 BLOCKER, 10 MAJOR, 5 MINOR)
- **IDs de gap divergentes**: GAP-004 é margem do bloco paisagem em `gaps.jsonl`, mas
  condicionantes/ambiental no YAML e no STATE; GAP-003 = todos os painéis no catálogo, só
  cronogramas no YAML. A fonte ambiental não tem gap próprio.
- O YAML candidato não tem `components:` com posição, classe, fonte e presença; nenhum código o lê.
- Nenhum asset no repositório e nenhum manifesto de sha1.
- Controle de Produtos sem regra de render (nem o layout do índice de anexos).
- **Unidade de contagem misturada**: 149 = linhas da Lista Mestra (encerramento e índice);
  135 = códigos distintos no snapshot. Verificado agora: o leitor do pacote, sobre o snapshot
  v335.0, dá 2.1=3, 2.2=48, 2.4=98, total 149 para o nº 14.
- "100% de correspondência em maio e junho" não vale nos dois sentidos (1 anexo fora da lista por mês).
- Confiança acima da evidência: EMF CONFIRMED com só 2 meses (→ HIGH); "datas nunca coincidem",
  quebra antes do 2.6 e processos ambientais fixos são coincidência, não regra provada.
- Hardcodes de agosto no YAML (`august_counts`, `occurrences_per_report: 3`, 43 páginas).
- Faltam no modelo: `inputs:` (datas, status externo), `validations:`, mapa de pastas de anexo,
  domínio de rodovias; componentes `P2.1_MEETINGS_BY_ROAD` e `P2.4_PENDING_LICENSES_COUNT`.

## C — não conformidade e controle tecnológico no 2.4
- **Não existe painel de NC em nenhum relatório, do nº 01 ao nº 14** (CONFIRMED). O nº 07
  prometia um Power BI que nunca apareceu. `P2.4_NONCONFORMITY_PANEL` sai do modelo.
- NC é texto: frase fixa (nº 05–14; truncada em nº 13–14, anomalia já registrada) + enumeração
  opcional dos códigos por rodovia + complemento de RNC (só nº 14, MEDIUM).
- **Fonte da enumeração é a Lista Mestra** (`Manifestação == 'Notificação de não conformidade'`,
  por `Empreendimento`, natureza pela `Descrição`), 100% nos nº 12 e 13. A planilha
  `02_…NC automatizada.xlsm` **não** alimenta o relatório (preenchimento parou em jan/2026,
  nomenclatura e status divergem).
- Quando enumerar é editorial (enumera com 2 e 4 NC, não com 8 a 25): LOW → decisão humana.
- Controle tecnológico: texto + anexos (pareceres PA); genérico e idêntico nos nº 13 e 14.
- Anomalia nova: nº 12 diz PA-633.1 a 135.1 "em elaboração", mas a Lista Mestra os atribui ao nº 12.

## B — painéis ambientais do 2.4 (linhagem provada)
- Fonte: `04_Acompanhamento - Licenca Ambiental.xlsx` (item `01EXEMPLOITEMID000000000000000000`),
  346 versões desde 2025-12-08, lida só em memória. Abas `Licenças` (cab. linha 2, B:P),
  `Condicionantes` (cab. linha 2, A:L), `Empresas` (empresa → rodovia: CSG=RD-101, CLX=RD-102a,
  Delta=RD-103, Tetra=RD-104). A aba `Dashboard` é legada e **não** é o painel do relatório.
- **Painel "Índices de Acompanhamento Ambiental"** (1/mês), aba `Licenças`, todas as linhas:
  total = linhas; emitidas = `Nº Licença` preenchido; pendentes = `Status == "Aguardando a
  liberação"`; pizza vigente/pendente; barras por rodovia (decrescente, empate alfabético);
  fases por `Fase da licença`; tabela Rodovia/Empresa/Processo/Licença/Fase/Validade/Status/Link.
- **Painéis "Status das Condicionantes"** (4/mês, um por rodovia), aba `Condicionantes`:
  contagem `Responsável → rodovia × Status`; 0 aparece como "--". Só batem **incluindo** as linhas
  ocultas pelo autofiltro (confirma DEC-009 §3).
- O `Status` é fórmula com `TODAY()`: recalculado com a data "Atualizado em" do painel dá 0
  divergências (nº 13 v289, nº 14 v310). Regra: Observações "Finalizada" → Finalizada;
  "Atendida" → usa Próxima entrega (K); senão Data da entrega (F); dias ≤ 0 → Pendente,
  ≤ 30 → Próximo do vencimento, senão No prazo. **O gerador recalcula o status com data de
  referência explícita; nunca usa o valor em cache.**
- Texto do 2.4 sobre licenças e condicionantes bate 100%: 0 próximas → "Não apresenta
  condicionantes em atraso;", 1 → "…apenas uma condicionante próxima…", >1 → "…algumas…".
- Contagens CONFIRMED nos 4 meses (nº 11–14); ordem das barras HIGH; ordem da tabela e nomes de
  exibição das empresas MEDIUM (o mapa vem do modelo Power BI, não da planilha).
- **DEC-008 refutado para esta fonte em agosto**: a versão da data de emissão (v311) diverge em
  RD-103 por edição de 08/09; a certa é a última antes do refresh "Atualizado em" (v310).
  Snapshot desta fonte = última versão com `lastModified <=` instante "Atualizado em".
- Anomalias candidatas: painel do nº 13 datado depois da emissão; nº 12 "24 emitidas" com 23
  vigentes; nº 11 frase de abertura contradiz os 4 itens; ruído de interface no nº 11; nº de
  licença da CLX divergente entre abas; `Empresas!M` "RD 102a".

## H — revisão adversarial (o que caiu)
- **Ordem física**: os "~17 mil pares" saem de 4 sequências de um mês (o índice é a união das
  outras três). Acerto por data estrito é 89,5%, não 94%. **Maio contradiz**: o índice do nº 11
  está perfeitamente ordenado por código. Agosto sustenta: as 4 sequências do PDF são idênticas
  às do snapshot v335. → regra CONFIRMED só para julho/agosto (padrão vigente); maio é
  `HISTORICAL_PATTERN` (ordem por código).
- **DEC-008 em julho cai**: o v134 tem 168 linhas com N=13; o encerramento de julho declara
  165, que bate com o estado atual e com o v335. O 2.4 de julho (111 linhas) não bate com
  nenhuma das três versões. Julho foi montado com estados diferentes da planilha no corpo e no
  índice. → `historical_reconstruction.validated = ["2026-08"]` até achar a versão de julho.
- **135 contra 135 sobrevive** (códigos); linhas são 149. A redação precisa separar as unidades.
- **"100%" maio–julho enfraquece**: 1 anexo fora da lista (AT-632.1) em maio e junho; risco de
  causalidade inversa (lista preenchida depois do anexo).
- **Tipografia errada no YAML**: corpo = `minorHAnsi` = **Arial Nova Light 11**; Arial Nova Cond
  é cabeçalho/títulos. O tamanho do texto da tabela não é 6,8 fixo: é consequência da escala do
  EMF (7,2/6,9/6,8 em agosto). Maio já era vetorial: o JPG de junho é a exceção.
- **Margens da paisagem** 2,0/1,5/1,5/2,0 = retrato girado pelo Word (herança). Reproduzir, sem
  chamar de "espelhado".
- **Desapropriação/interferência não é ausência total**: a aba `Projetos` tem linhas "Projeto de
  Desapropriação" e "Projeto de Interferência" por rodovia; `GED!T990` cita GFD/RD-104.
  GAP-009 reaberto.
- **Prontidão "22/32" não é medida**: flags booleanas digitadas à mão; `historical_validated` nem
  entra. Deve passar a ser calculada por teste/artefato.
- **Frases "12/12" e "24/24"**: identidade esperada num documento copiado mês a mês; a condição de
  ausência nunca alternou na janela. CONFIRMED como texto, HIGH como condição.
- **Golden test sem comparador**: congelar o comparador e os desvios permitidos (por anomalia)
  antes de comparar, com extração factual independente do builder.

## K — resumo executivo do 2.1 (GAP-005)
- 19 afirmações em agosto: **FIXED 47%, DERIVABLE 42%** (da Lista Mestra do relatório),
  INTERPRETIVE 5% (temas dos pareceres do 2.2), anomalia 5%, EXTERNAL 0% (em maio/junho houve
  "POP em elaboração" e "mesa técnica TCE-UF"). → GAP-005 vira "≈90% fixo ou derivável".
- Gatilhos derivados: produtos com linhas; cláusula das Atas ⇔ existe AT no 2.1 (4/4); tipos e
  rodovias do 2.2 e do 2.4; rodovias dos BM; temas dos PA do 2.4 por palavras-chave (MEDIUM).
- Anomalias: "Ofício" nos nº 13/14 sem nenhum OF; rodovias dos BM do nº 13 (copy-forward de
  junho); fragmento truncado "Na RD-101." nos nº 13/14; frases de disciplinas do 2.2 do nº 13
  copiadas do nº 12.
- Reuniões por rodovia: não há contagem; é uma agenda (rodovia, executora, dia, hora). Dia da
  semana derivável pela moda das atas "Reunião de alinhamento técnico" (nº 11–13); executora pela
  aba `Painel de Controle`; **hora é EXTERNAL** (configuração estável).
- Bug corrigido no leitor: na v134.0 a coluna de manifestação chama-se "Parecer" (teste novo).
- Template proposto com slots: `tmp/agent_K/executive_summary_template.yaml`.
- **Consequência para a decisão "rótulo da 2ª coluna do Controle de Produtos"**: a própria Lista
  Mestra renomeou a coluna de "Parecer" (v134.0, julho) para "Manifestação" (v335.0, agosto). O
  quadro é recorte do Excel, então o rótulo é **o cabeçalho da fonte no snapshot**, não escolha
  editorial. Deixa de ser decisão humana (a confirmar quando A comparar o EMF de julho).

## J — modelo de conteúdo textual (118 blocos)
- Catálogo gerado em `tmp/agent_J/content_model.yaml` (gerador `j05_build_content_model.py`):
  118 blocos na ordem do documento — FIXED_TEXT 78, DATA_DRIVEN 14, TEMPLATE 12,
  SOURCE_VERBATIM 6, MANUAL_INPUT 6, AI_SYNTHESIS 2. Textos fixos copiados do XML do nº 14 por
  programa (byte a byte), conferidos contra nº 11–13.
- Citações 2.1–2.6: 24/24 idênticas; 3 parágrafos cada (dois com 4 tabs, corpo com recuo
  esquerdo 2832 twips, itálico). Parágrafo vazio entre citação e Ttulo3 só em 2.1/2.3/2.5/2.6.
- Encerramento: `"{n} ({extenso})"`, minúsculas, reproduz os 4 meses; "páginas" pede numeral
  feminino (não exercitado).
- **Tabela de assinatura tem texto** (a matriz estava errada): "Eng° {nome}" TNR 9 / razão social
  TNR 6 negrito / "Produto P2.1 – Relatório Mensal – Grupo 2." TNR 6. Signatário mudou no nº 13
  (TRUE_CHANGE) → `signatory_name` é entrada.
- ANEXOS: só os EMFs do Controle de Produtos consolidado (5 desenhos num parágrafo no nº 14).
- Conjunto vazio no 2.2: 4 formas literais + omissão da linha. Forma mais frequente (16/22):
  "nenhuma disciplina encontra-se em análise no fechamento do presente relatório;".
- 9 anomalias candidatas novas (copy-forward de BM no nº 13, RCA-512.1 com rodovia errada,
  pontuação, realce residual, parágrafos vazios como espaçamento) e TRUE_CHANGEs (agenda da
  RD-101, organograma, saída do bloco TCE em julho, "pendentes de aprovação" em agosto).
- Decisões editoriais com default técnico: forma do conjunto vazio (default: a mais frequente),
  número do contrato (`N° 00/0000-PARC`), correções gramaticais DEC-007, emitir sempre a linha.

## A — GAP-001 fechado (Controle de Produtos)
- Cadeia provada por `scripts/12_probe_emf_export.py`: Lista Mestra (snapshot) → filtro explícito
  → linhas por recorte → `CopyPicture(xlScreen, xlPicture)` → `GetClipboardData(14)`
  (CF_ENHMETAFILE já devolve os bytes do EMF) → parte OPC `image/x-emf` inline → Word → PDF.
- EMF **vetorial** (EMR_EXTTEXTOUTW; só as setas do autofiltro são bitmap, como no histórico).
- **xlScreen reproduz o histórico**: mesmo dispositivo de referência, frame de 22,091 cm, fontes
  Arial Nova Cond. xlPrinter não serve. Com altura de linha 27,6 pt, **11/11 recortes do nº 14
  idênticos** ao histórico em frame e bounds (0,001 cm) e conteúdo.
- **Um EMF por página**, linhas 1–3 (título + cabeçalho) repetidas em cada recorte. nº 14:
  2.1=3; 2.2=25+23; 2.4=32+34+32; anexos=31+31+39+33+15 — 0 divergências contra o v335. A quebra
  histórica é manual (31–34 linhas por página).
- No PDF gerado pelo Word: 51 códigos extraíveis, Arial Nova Cond 7,23 pt (histórico 7,24 pt).
- Contagens: **149 = linhas** do filtro (3+48+98); **135 = códigos distintos**.
- Dependência de ambiente: Windows + Excel + Word + sessão interativa; xlScreen depende de DPI e
  resolução (aqui 1920×1080 a 120 dpi lógicos, igual ao histórico).
- Anomalias: dois recortes de anexos do nº 14 encolhidos à mão.
- Reclassificado (METHOD_ERROR, §M): as "3 linhas BM RD-104 duplicadas no 2.4" e as "3 BM
  RD-102A omitidas nos anexos" do nº 13 não são anomalias do relatório — eram leitura do
  snapshot errado. Na v162 (DEC-012) as linhas BM-007/008/009.1 existem (corpo = body_rows) e
  estão "Em elaboração" (o índice as exclui). Catálogo: `DIAGNOSTICO_CONTROLE_PRODUTOS_BM_RD104`
  e `DIAGNOSTICO_INDICE_ANEXOS_BM_RD102A`, ambos METHOD_ERROR.
- Defaults técnicos: altura de linha uniforme 27,6 pt (padrão de agosto; MEDIUM); paginação
  gulosa até a altura útil de 26,2 cm.

## I — capa, assets estáticos e OOXML de base
- **Capa** = `body[0]`: `w:object` + `v:shape` absoluto (z-index na frente) + `o:OLEObject`
  `PowerPoint.Show.12` embutido; prévia `image1.emf` de 11 MB (EMF+ com JPEG + fallback DIB).
  Não há seção própria: a seção 0 tem `titlePg` e só referências `default`, por isso a capa sai
  sem cabeçalho e rodapé. Slide de 19,05 × 27,517 cm; os dois campos variáveis são `sp id=41`
  (`Relatório Mensal N° {n}`) e `sp id=42` (`DD de Mês de AAAA`); mídias e layout byte-idênticos
  nos 4 meses.
- **Defeito histórico novo**: a fonte da data (Arial Nova Cond Light, do tema) não estava
  disponível para quem editou; a substituta mudou todo mês. "11de Agosto" (julho) é defeito de
  renderização da prévia, não typo. **No PDF nº 14 a data da capa está ilegível** (MuPDF e
  pdfium). O Word exporta a prévia guardada, não re-renderiza o slide.
- Protótipos do zero (a) OLE + prévia regenerada, (b) imagem de página inteira, (b') fundo sem
  texto + 4 parágrafos do Word com posição absoluta. Recomendação: **(b')** (ver DEC-011).
- **15 assets** extraídos para `assets/discovered/raw/` (gitignored), com manifesto em
  `tmp/agent_I/assets_manifest.yaml` (sha1, formato, cm). Correções de spec: o "logotipo da
  apresentação" é uma **faixa de 5 fotos com pessoas** (`contains_people_photos: true`); as
  "fotos de organograma" são slides de cargos, sem nomes nem fotos. Seis assets estáveis desde
  o nº 11; quatro desde o nº 12.
- **OOXML de base** (`tmp/agent_I/ooxml_base.yaml`): 25 estilos com herança; numeração dos
  títulos numId 15 → abstractNum 23 (`%1`, `%1.%2`, `%1.%2.%3`); 3 seções e 10 partes de
  cabeçalho/rodapé com XML literal; TOC `TOC \o "1-3" \z \u \h` em SDT; `embedTrueTypeFonts`,
  `saveSubsetFonts`, `compatibilityMode` 15; tema Arial Nova Cond (títulos) / Arial Nova Light
  (corpo), esquema de cores "Programa". O builder reescreve `theme1.xml` (o default é Calibri).
- Anomalias: larguras inconsistentes das tabelas de cabeçalho/rodapé entre seções; `titlePg` e
  referências `first` sem uso nas seções 1 e 2; realce amarelo em parágrafos de imagem.
- Dependência de ambiente: família Arial Nova (inclusive Cond Light) disponível no Office.

## D — relatórios semanais do 2.4 (GAP-010 fechado)
- Origem: um relatório semanal por rodovia (Dynatest, Manifestação "Relatório Semanal de
  Acompanhamento de Obras", produto 2.4); semana sábado→sexta na coluna `Período`; `RO-NNN.V`
  sequencial e independente por rodovia; `.V` = revisão (ambas anexadas).
- A divergência vem de **uma única semana** (25/07–31/07) nas **4 rodovias**: Lista Mestra e
  anexos põem no nº 13; o texto do nº 13 a omite; o nº 14 a cita de novo (continuou do texto do
  nº 13). Hipóteses "entregue após a emissão" e "linha adicionada depois" descartadas (o v134 de
  11/08 já tinha N° Relatório = 13).
- Regra pela Lista Mestra reproduz 76/76 da Lista Mestra e dos anexos; o texto só diverge
  quando a semana começa no dia 25 de um mês de 31 dias (ocorreu só em julho/2026).
- **Regra (CODE, CONFIRMED)**: faixa por rodovia = 1º e último código de
  `N° Relatório == N ∧ Manifestação == Relatório Semanal`, na ordem física, com a revisão real;
  período = menor início e maior fim do `Período`; "até o dia 25/MM/AAAA" é texto fixo do mês.
  Nunca inferir faixa por data nem por continuidade com o mês anterior.
- Os RO são anexo + citação estruturada; nada de dentro deles entra no texto.
- Anomalias: nº 13 `INTERNAL_INCONSISTENCY` (lista × período × anexos, 4 rodovias); nº 14
  `COPY_FORWARD_ERROR` (lista e período iniciado em 25/07); fim de período "25/05" no nº 11;
  Data Entrega 2026-05-08 anterior ao início da semana em 3 RO.
- Validação não bloqueante: avisar semana iniciada entre 25 e 31 que termina em M, e
  sobreposição com o período do relatório anterior.

## M — snapshot de julho achado (DEC-008 revisto → DEC-012)
- Varridas 430 versões da Lista Mestra (05/08 a 29/09), em memória. **Uma versão reproduz os 4
  blocos de julho: v162** (14/08 17:24:37Z) — e qualquer uma de v155 a v293.
- **O índice de anexos tem filtro**: `N° Relatório == n ∧ Status Entrega == "Entregue"`. O corpo
  (Controle de Produtos por produto) lista **todas** as linhas do relatório, inclusive "Em
  elaboração"; o índice e o total do encerramento ("165 anexos") só as entregues. Em julho as 6
  linhas excluídas são BM-007/008/009.1 de RD-102A e RD-104, "Em elaboração" e sem data. Em
  agosto todas as 149 estão "Entregue" (filtro neutro). Coluna do filtro (Status × Data Entrega
  preenchida): MEDIUM — as duas coincidem em v162 e v331.
- **Critério de snapshot**: última versão com `lastModified <=` CreationDate do PDF publicado
  (julho: PDF 14/08 17:26:35Z → v162, 2 min antes, mesmo autor do docx; agosto: PDF 08/09
  18:51:16Z → v331, que reproduz 3/48/98/149). A data da capa não é o instante da montagem.
  O v335 do DEC-008 original acertou agosto por estabilidade da planilha, não pelo critério.
- Em v294 (04/09) as 6 linhas foram movidas para N=14: reatribuição retroativa (anomalia).
- Produção mensal (Fase B) não tem PDF prévio: o snapshot é o estado da fonte **no instante da
  geração**, registrado no manifesto (versão + lastModified); o critério histórico só serve ao
  golden test.
- Risco: o histórico de versões do SharePoint é finito (464 versões em 25/09). Os snapshots dos
  golden tests (Lista Mestra v162/v331; ambiental v289/v310) só existem lá; persistir cópia local
  exige autorização da Emmily.

## E — histórico da planilha de projetos (GAP-008 fechado) e desapropriação (GAP-009)
- 501 versões (v76 a v576, 22/04 a 01/10/2026), contíguas: **v1–v75 já foram podadas** — o
  limite de 500 versões do SharePoint foi atingido. Ritmo ≈ 5,6 versões/dia em setembro.
  Estimativa de perda: nº 11 (v127) ≈ 10/10; nº 12 (v161) ≈ 16/10; nº 13 (v328) meados de
  novembro; nº 14 (v438) fim de novembro. A Lista Mestra (464 versões em 25/09) entra na mesma
  poda em breve.
- 8 quadros Power BI do 2.2 transcritos (84 linhas, 504 células) e comparados com as versões em
  memória: cópia atual 40,5%/58,3% das linhas; DEC-008 85,7%/98,8%; **DEC-012 (CreationDate do
  PDF) v328 e v438: 100% linhas e células nos dois meses** (vizinhas dão menos). O critério
  "fim do dia do 'Atualizado em'" chega às mesmas versões.
- Blocos de status por disciplina: nº 13 sem contradição (só omissões); nº 14 com uma: a
  Pavimentação da RD-101 sai "pendente" no texto e "em análise" na v438 — o texto foi redigido
  com v429–v436, horas antes da última atualização (anomalia).
- Hipótese MEDIUM para "pendentes de aprovação" (100% no nº 14): aceita = Sim, avaliação
  Reprovado e "Entrega da Revisão" = "Aguardando previsão" ou data vencida no corte.
- Anomalia: "aceito" da OAE da RD-101 cita uma das duas disciplinas, copiado do mês anterior.
- **GAP-009**: 12 termos em 4.294 itens (196 planilhas): não existe planilha de acompanhamento
  de DUP, GDP, Casa Civil ou interferências. Há entregas das projetistas e logs do G1 sem
  campos de status. → **entrada humana confirmada**, estruturada por rodovia (PROGRAMA, GDP,
  Casa Civil, interferências).

## O — blocos data-driven do 2.4 (spec implementável)
- Spec em `tmp/agent_O/p24_blocks_spec.yaml` (16 blocos), provada por renderizador
  (`o04_render_compare.py`): nº 14 22/24 linhas (resíduo = 2 anomalias), nº 13 30/36 (resíduo =
  6 anomalias), **fatos 100%**; nº 12 100% em RM, BM e RA. Nenhuma "regra errada" no padrão nº 13–14.
- BM "realizadas" exige `Status Entrega == 'Entregue'`; "Em elaboração" vai para "permanecem em
  elaboração". Mês vem da Descrição sem "Boletim de Medição de "; separador " - ".
- **Ordens são constantes do modelo** (não a ordem física): alfabética para BM, LAU e NC;
  RD-103/102A/101/104 para RA; RD-102A/103/104/101 para RCA e GAMB; RM por código crescente.
- Numeração: numId 29 (bullet / lowerLetter "%2)") e numId 47 ("%1)" / upperRoman "%2.",
  romano reinicia por rodovia). Builder: uma instância `<w:num>` nova por lista.
- LIC idêntico nos nº 12–14 é dado estável, não copy-forward. Rótulos de fase por dicionário.
- Presença: RM desde nº 12, RI e RA desde nº 13; pareceres de medição/ambientais por palavra-chave
  na Descrição dos PA (texto fixo genérico).
- Anomalias: BM RD-103 trocados no nº 13; RCA-512.1 com rodovia errada; "RD-104 RA-…" sem
  dois-pontos; separador misto; "..". Decisões editoriais com default: limiar de NC (default:
  enumerar até 4 — `up_to_4`, Gate B), concordância "licenças referentes", rótulo "recurso(s) hídrico(s)".

## L — regras de render dos visuais reconstruídos (DEC-009)
- Spec em `config/g2_render_rules.yaml` (promovida de `tmp/agent_L/render_rules.yaml`).
- Os 13 painéis PNG dos nº 13–14: inline, sem crop, 17,50 cm (x = 2,00–19,50 cm). Proporções:
  quadro por rodovia 1,781; Índices 1,779; Condicionantes 2,49.
- P2.2: moldura #0E1A77; donut com cores do tema Power BI (#118DFF, #12239E, #E66C37), início às
  12h, horário, Analisada → Atrasado → Em análise; tabela de 7 colunas, zebra #EEEDED, datas dd/mm/aa.
- P2.4 Índices: cor fixa por rodovia; pizza alfabética com Pendente em 158,5°; fases com escala
  fixa (corta a maior barra — defeito); tabela #19444D/#1C5560.
- P2.4 Condicionantes: 4 cards #2A6975; zero = "--"; barra proporcional ao maior das 4 rodovias;
  percentuais 0–100% com categoria zero omitida.
- Controle de Produtos (EMF): faixa de título 39,84 pt #1C5560, cabeçalho 9,26 pt #1F4993,
  linha 18,51 pt; colunas 56,7/92,6/170,2/61,2/53,9/61,4 pt; bordas só horizontais pontilhadas.
- Defaults técnicos (DEC-009, DEC-007; revisáveis): fundo sólido #275559 no lugar da foto dos
  painéis ambientais (não há cópia limpa); tabela de Índices **completa** (a captura era janela de
  rolagem); slicer "Disciplina: Todos" omitido (ruído de interface); "Próximo à vencer" →
  "Próximo a vencer"; números do donut inteiros; canvas 2067 px (300 dpi) a 17,50 cm.
- Anomalias: datas M/D/AAAA em "Entrega da Revisão"; Segoe UI só na RD-102A; rótulos do donut
  inconsistentes; "RD-102a"; barra de fase cortada; EMF encolhido; 3ª linha cortada no nº 14.
- Ambiente: Arial Nova não está instalada nesta máquina (só embutida nos PDF); matplotlib ausente.

## N — bloco por rodovia do 2.2 (spec implementável)
- Spec em `config/data_rules/p22_highway_block.yaml` (promovida de `tmp/agent_N/`). Fonte: aba
  `Projetos` inteira (100 linhas, ignorando autofiltro e 74 ocultas); o texto não usa a Lista Mestra.
- Ordem das rodovias: RD-103, RD-102A, RD-101, RD-104 (colunas do `Painel de Controle`).
- **Ordem dos grupos = data da primeira entrega no GED** por rodovia e grupo (sem entrega → fim,
  pela `Ordem Disciplina`): 16/16 casos; `Ordem Disciplina` erra 3, Painel erra 5.
- Disciplinas por `Ordem Disciplina`; texto exclui Equipe Fixa, Projeto Executivo e Memoriais
  Descritivos da Obra (o quadro só as duas primeiras). Normalização 'RD-102 A' → 'RD-102A'
  (espaços e NBSP); 'RD-103-0' do GED não se funde com RD-103.
- Status: Aceitação = `ACEITA?` sim; Aprovação = `AVALIAÇÃO` começa com "aprovad"; Em análise =
  `SITUAÇÃO` em análise (linha omitida se o grupo está todo aprovado: 30/30); Não entregues =
  `SITUAÇÃO` atrasado; Pendentes = sim + Reprovado + coluna W "Aguardando…" ou data ≤ referência
  (15/15 no nº 14, MEDIUM). A cláusula "Foram tratadas disciplinas como…" saiu em agosto → não emitir.
- Quadro: colunas Disciplina, Previsão, Entrega, REV, 1º Nível, 2º Nível, Entrega da Revisão,
  pela `Ordem Disciplina`; rosca pela `SITUAÇÃO`.
- Medida: nº 14 contra v436 = 44/45 linhas de status (63/64 com títulos); a única divergência é a
  OAE da RD-101 copiada (anomalia). **O texto saiu da v436 e o quadro da v437+.** Texto literal
  21/45 idêntico com templates canônicos — diferença de redação, padronização DEC-007.
- Defaults técnicos: ordem dos grupos pela primeira entrega; nomes de disciplina da planilha;
  datas dd/mm/aa no quadro.
- Anomalias: "aprovados com ressalva" generalizado na RD-104; ordem herdada no Secundário;
  Paisagismo omitido no nº 13; datas M/D/AAAA; cláusula de julho copiada de junho.

## Integração do builder (2026-10-01)
Integrados no `main`: P (Controle de Produtos), Q (fundação, `config/ooxml_base.yaml`, capa
DEC-011, `builder/word_pdf.py`), R (comparador `qa/`, `config/golden_allowances.yaml` FROZEN
v1.0, `scripts/14_golden_compare.py`), T (motor de blocos), U (2.4), V (visuais PNG), X (2.2),
Y (2.1 e slots de IA DEC-013). Medidas declaradas pelos builders nos testes `-m golden`:
- X: nº 14 × v436 44/45 conjuntos de status; quadros 504/504 células (nº 13 e 14).
- Y: nº 14 19/19 e nº 13 21/21 afirmações fixas/deriváveis; anomalias não reproduzidas.
- U: painéis ambientais exatos nos nº 13 e 14; 2.4 nº 14 22/24 linhas (resíduo = anomalias).
- R: extração do PDF real do nº 14 = 43 páginas, 3/48/98/149; comparar o nº 14 consigo mesmo
  reprova só em `expected_report_number` (a Apresentação histórica diz 13) — comportamento certo.
Pendências registradas pelos builders: unificar `BlockText` (montador AA); calibrar o corpo de
texto dos painéis (`em_px` 17 × `pbi_pt` 10); tema S7 do resumo não sustentado pelas Descrições
em 2 de 6 temas (decidir `keyword_map` × `fixed`); extra de dependências `render`/`builder` no
pyproject (python-docx, Pillow, PyMuPDF, matplotlib).
