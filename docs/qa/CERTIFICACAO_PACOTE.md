# Pacote de certificação do G2_REPORT_MODEL

**Preparado em:** 2026-10-04 · **Modelo:** v0.14 (`BUILDER_READY`) · **Reconstrução avaliada:**
Relatório G2 nº 14 — Agosto/2026 (`output/reconstruction/14_v6`)

## 1. O que está sendo pedido

Sua aprovação para promover o modelo do Relatório G2 (v0.14) a **CERTIFIED**. A prova é o
Relatório G2 nº 14 — Agosto/2026 gerado **do zero** (documento Word vazio + modelo + fontes do mês),
comparado com o PDF publicado. As diferenças estão listadas e justificadas abaixo; as escolhas
editoriais que o builder fez por padrão técnico são suas para confirmar ou trocar (seção 5).

## 2. Como conferir em 15 minutos

Abra os dois PDFs lado a lado. Os dois têm 43 páginas e a mesma paginação, então o número de
página é o mesmo nos dois.

- **Gerado:** `C:\caminho\exemplo\PROG_Relatorio_G2_Automacao\output\reconstruction\14_v6\relatorio_g2_n14_2026-08.pdf`
- **Publicado:** `C:\caminho\exemplo\PROG_Relatorio_G2_Automacao\tmp\downloads\relatorios_11_14\prog - relatório grupo 2 - relatório mensal n°14 - 08 2026.pdf`

| Pág. | Onde | O que olhar |
|---|---|---|
| 1 | Capa | Texto da capa agora legível e pesquisável (no publicado a prévia saiu ilegível). Fonte da capa difere (única diferença visual sinalizada, de baixa gravidade). |
| 3 | Apresentação | Publicado diz "Relatório Mensal N° 13"; o gerado diz "N° 14". |
| 15–16 | 2.1.2, resumo executivo | Frases que citavam temas sem documento no mês foram enxugadas (reuniões, "Ofício", "interferências identificadas em campo", condicionantes, desapropriação). A frase órfã "Na RD-101." virou a frase completa das medições (BM 07, 08 e 09 da RD-104). |
| 18–21 | 2.2.2, status por rodovia | Linhas de "Aprovação": a ressalva aparece por disciplina, como na planilha. Ex.: RD-104, Viário Principal (p. 21–22). Pavimentação da RD-101 em análise (p. 20). |
| 22–24 | 2.2.2, matrizes de DUP, desapropriação e interferências | "Análise Programa: Aprovado com ressalva" (6 casos); "Não aprovado" → "Em análise" (3 casos); "Publicação pela Casa Civil" da RD-101 com "Sem informação até o fechamento do presente relatório" (p. 23). |
| 24 | Controle de Produtos do 2.2 | NT-734.1 com a descrição inteira (o publicado corta "…e Projeto de"); 2ª coluna rotulada "Manifestação". |
| 27–28 | 2.4.2 | Faixa dos relatórios semanais começa em 01/08/2026 e os RO começam uma semana depois (publicado repetiu a semana 25/07–31/07 do nº 13). Atas e pareceres só com temas que têm documento; "Consolidade" → "Consolidado". |
| 37 | Encerramento | 43 páginas e 149 anexos, iguais ao publicado. O gerado não tem a imagem de assinatura (ela é aplicada depois, ver seção 6). |

Para ver todas as diferenças palavra a palavra: `docs\qa\approved_hunks\n14.yaml` (113 itens,
cada um com o texto publicado, o texto gerado e a justificativa).

## 3. Resultado

Critério do projeto (CLAUDE.md): ≥ 95% de fidelidade visual estrutural e 100% em fatos, fontes,
anexos, numeração, mês, rodovias, documentos e ordem.

| Critério | Exigido | Resultado no nº 14 |
|---|---|---|
| Páginas | iguais | 43 = 43 |
| Fidelidade estrutural | ≥ 95% | **99,01%** — 59/59 unidades de estrutura (seções, títulos, orientação, cabeçalho, rodapé); 41/42 de geometria (a que difere é a fonte da capa) |
| Sumário e títulos | 100% | 23/23, mesma ordem, mesmas páginas |
| Fatos | 100% | **567/567** unidades de conteúdo do comparador; conferência independente contra as planilhas: 180/181 fatos OK, 1 observação de rastreabilidade (caminho do arquivo de fundo da capa), sem efeito no texto |
| Controle de Produtos | 100% | 2.1: 3 · 2.2: 48 · 2.4: 98 linhas, mesma ordem; todas iguais, exceto NT-734.1 (cortada no publicado) |
| Anexos | 100% | 149 = 149, mesma ordem; 148 idênticas + NT-734.1 (idem) |
| Número, mês, rodovias, documentos | 100% | N° 14 e Agosto/2026 em capa, Apresentação e Encerramento; rodovias e códigos iguais aos da Lista Mestra |
| Texto palavra a palavra | toda diferença justificada | 113 diferenças, **113 aprovadas com justificativa**, 0 sem justificativa |
| Comparador | PASS | **PASS** (versão 4.1, reexecutado em 2026-10-04) |

Observação: os arquivos `golden.md`/`golden.json` gravados em `output\reconstruction\14_v6\` são
de uma rodada anterior do comparador (4.0), feita antes de os 8 últimos itens serem aprovados, e
mostram FAIL por esses 8 itens. A reexecução com o comparador 4.1 sobre o mesmo PDF dá PASS.
Atualizar esses arquivos faz parte do registro do Gate D.

### Gates

| Gate | O que verifica | Data | Veredito |
|---|---|---|---|
| A — linhagem das fontes | de onde vem cada número, texto, tabela e anexo | 2026-10-01 | **PASS** |
| B — modelo pronto para o builder | modelo coerente, sem regra copiada de erro histórico | 2026-10-01 a 02 | 3 reprovações corrigidas; **PASS** na 4ª tentativa (2026-10-02) |
| D — reconstrução do nº 14 | comparação automática + revisões independentes de conteúdo, visual e ataque (alteração proposital do PDF) | 2026-10-01 a 02 | 4 rodadas. Visual: PASS (0 problema maior). Fontes: PASS (100% dos fatos e anexos). Auditoria dos 105 primeiros itens aprovados: 0 errados, 0 sem base, 11 são decisão editorial sua. A última falha (ressalva podia ser movida de uma rodovia para outra sem ser detectada) foi corrigida no comparador 4.1. **PASS em 2026-10-04 (verificação final QA5: nenhum bloqueio novo).** |
| Golden temporal — nº 13 | o mesmo modelo reproduz julho | 2026-10-02 | Reprova só por 23 itens explicados pela versão da Lista Mestra disponível em disco (seção 7) |
| E — certificação | sua aprovação | — | **Este pacote** |

## 4. Diferenças em relação ao publicado (113, agrupadas)

Nenhuma diferença foi aprovada sem justificativa catalogada: cada item cita uma anomalia
registrada em `data/catalog/anomalies.jsonl` (erro do publicado, marcado para nunca virar regra)
ou uma decisão `DEC-NNN`. O comparador recusa qualquer diferença fora deste conjunto, e o conjunto
é congelado (alterar o arquivo sem nova versão faz o comparador recusá-lo).

| # | Grupo | Qtd. | Por quê | Exemplo (publicado → gerado) |
|---|---|---|---|---|
| 1 | Padronização de redação | 58 | DEC-007 (sua instrução): texto produzido pelo relatório é corrigido e padronizado; citação de contrato fica literal | 2.2, RD-103: "as disciplinas da Fase de Estudos **foram** aceitas em 1º nível" → "…**encontram-se** aceitas em 1º nível" |
| 2 | Ressalva por disciplina | 17 | DEC-015: a ressalva é fato da planilha de projetos; o publicado generaliza numa frase e omite as demais (11 no corpo do 2.2 + 6 nas matrizes "Análise Programa") | RD-104, Viário Principal: "o Projeto Geométrico e Interseções e o Projeto de Terraplenagem encontram-se aprovados com ressalva" → "o Projeto Geométrico e Interseções encontra-se aprovado. O Projeto de Terraplenagem encontra-se aprovado com ressalva" |
| 3 | Status do 2.2 conforme a planilha | 7 | O publicado contradiz a planilha de projetos na versão do instante da publicação (DEC-012): Análise Programa (3), Pavimentação da RD-101 (2), OAE da RD-101 (2) | Matriz RD-104: "Análise Programa: Não aprovado" → "Análise Programa: Em análise" (o próprio publicado diz "em análise pelo Programa" nos itens) |
| 4 | Temas sem documento no mês | 9 | Frase fixa copiada mês a mês que afirma temas sem nenhum documento que os sustente (resumo S1, S5, S7; atas; pareceres de medição e ambientais) | S7: "…saúde e segurança do trabalho, atendimento de condicionantes ambientais, tratativas relacionadas às áreas sujeitas à desapropriação, análise de evidências…" → "…saúde e segurança do trabalho, análise de evidências…" |
| 5 | Erro de fato do publicado | 8 | Copiado do mês anterior ou frase truncada: número do relatório (1), faixa de RO (5), frase das medições (1), frase das NC (1) | 2.4.2: "no período de 25/07/2026 a 28/08/2026" → "01/08/2026 a 28/08/2026"; RD-103 "RO-544.1 a RO-548.1" → "RO-545.1 a RO-548.1" |
| 6 | Grafia e concordância do publicado | 7 | "RD-102" → "RD-102A", predicado duplicado, "Consolidade", dois-pontos faltando, crase em "Referente às" (2), "às rodovias RD-104" → "à RD-104" | "Relatório Consolidade de Gestão das Não Conformidades" → "Relatório Consolidado…" |
| 7 | Controle de Produtos | 6 | Rótulo da 2ª coluna = cabeçalho da Lista Mestra no snapshot (DEC-010) (4); descrição de NT-734.1 que o publicado corta (2) | 2.2, NT-734.1: "…Projeto de Pavimentação e Projeto de" → "…Projeto de Pavimentação e Projeto de Interferência" |
| 8 | Valor vazio | 1 | Campo publicado com rótulo e sem valor | RD-101, DUP: "Publicação pela Casa Civil:" (vazio) → "Publicação pela Casa Civil: Sem informação até o fechamento do presente relatório;" |
| | **Total** | **113** | | |

Os grupos 2 (em parte), 4 e 8 contêm as escolhas editoriais da seção 5: a auditoria
independente marcou 11 itens como "decisão editorial" (HNK-14-005, 007, 010, 058–060, 074, 090,
092, 093, 095), nenhum como errado.

## 5. Decisões que são suas

Para cada uma: o que o builder faz hoje (padrão técnico), a alternativa, a evidência e como mudar.
"Nova versão do modelo" significa: ajuste no builder ou no modelo, reconstrução do nº 14 e nova
conferência das diferenças antes de certificar.

1. **Temas citados no resumo, atas e pareceres (S1, S5, S7, S8, atas, pareceres de medição e
   ambientais).**
   - Hoje: só cita um tema quando há documento do mês que o sustente (pela Descrição na Lista
     Mestra). No nº 14 saem do texto: os temas das reuniões (S1), "Ofício", "interferências
     identificadas em campo" (S5), condicionantes e desapropriação (S7), os dez temas das atas, o
     Ateste, geotécnicos e obras de arte corrente (pareceres). O S8 reproduz o publicado (as 8
     atuações têm documento).
   - Alternativa: frase fixa, idêntica aos nº 12–14, todo mês.
   - Evidência: no nº 14, os pareceres sustentam 4 dos 6 temas do S7; nenhuma ata sustenta os 10
     temas; a frase é idêntica nos nº 12, 13 e 14, independente dos documentos. Risco do padrão
     atual: documento com Descrição genérica pode fazer um tema real sumir.
   - Como mudar: S7 → `config/g2_report_model.yaml`, `editorial_defaults.p21_s7_mode: fixed`
     (sem código). Demais blocos → nova versão do modelo.

2. **Ressalva por disciplina (DEC-015).**
   - Hoje: cada disciplina aprovada com ressalva na planilha sai qualificada, em frase própria,
     depois das aprovadas sem ressalva; a matriz "Análise Programa" segue a mesma regra.
   - Alternativa: a forma dos nº 13–14 (uma frase genérica), que perde fato e qualifica disciplina
     sem ressalva; ou não qualificar nunca.
   - Evidência: a planilha distingue a ressalva em todas as 128 versões lidas; os nº 11 e 12
     qualificavam por disciplina (6 de 6 no nº 12); a v438 tem 10 disciplinas com ressalva. Custo:
     ≈ 10 linhas a mais por mês.
   - Como mudar: `config/data_rules/p22_highway_block.yaml`,
     `templates.approval.reservation_qualifier` (`per_discipline` | `none`). Nova versão do modelo.

3. **Grupo todo aprovado, parte com ressalva** (caso particular do item 2; HNK-14-058 a 060).
   - Hoje: "Todas as disciplinas encontram-se aprovadas. A Documentação para Declaração de
     Utilidade Pública (DUP) encontra-se aprovada com ressalva;".
   - Alternativa (forma do nº 12, 8 de 8): enumerar as aprovadas e depois as com ressalva.
   - Evidência: "Todas … aprovadas" é a forma vigente do grupo todo aprovado (4 vezes no nº 13, 5
     no nº 14).
   - Como mudar: mesmo arquivo, `templates.approval.with_reservation`. Nova versão do modelo.

4. **Frase para valor vazio nas matrizes do 2.2** (HNK-14-074).
   - Hoje: campo sem valor nunca sai como rótulo vazio. Ou você informa o status, ou declara que
     não há informação e sai "Sem informação até o fechamento do presente relatório", ou o
     relatório fica pendente com marcador visível.
   - Alternativa: outra redação, ou omitir o item.
   - Evidência: o publicado tem "Publicação pela Casa Civil:" sem valor (RD-101); a redação segue o
     vocabulário do relatório ("fechamento do presente relatório").
   - Como mudar: `config/g2_report_model.yaml`, `inputs.p22_external_status.schema.no_information.text`.

5. **Enumeração das NC no 2.4.**
   - Hoje: lista os códigos das NC quando há até 4; acima disso, não enumera.
   - Alternativa: sempre, nunca, ou outro limite.
   - Evidência (fraca): reproduz os 4 meses observados — enumerou com 4 (nº 12) e 2 (nº 13), não
     enumerou com 8 a 25 (nº 11 e 14). O limite é escolha editorial.
   - Como mudar: `editorial_defaults.nc_enumeration.value` (`always_when_present` | `never` |
     `up_to_N`). Sem código.

6. **Conjunto vazio do 2.2.**
   - Hoje: sempre emite "nenhuma disciplina encontra-se em análise no fechamento do presente
     relatório;".
   - Alternativa: omitir a linha, ou uma das outras 3 formas históricas.
   - Evidência: forma mais frequente, 16 de 22 ocorrências.
   - Como mudar: `editorial_defaults.p22_empty_set`. Sem código.

7. **Capa como fundo + texto do Word (DEC-011).**
   - Hoje: imagem de fundo sem texto + número e data como texto do Word; legível e pesquisável.
   - Alternativa: reinserir o slide do PowerPoint embutido (edição com duplo clique), com a
     prévia regenerada; exige PowerPoint na geração.
   - Evidência: a prévia do slide saiu errada em julho ("11de Agosto") e ilegível no PDF de agosto.
   - Como mudar: nova versão do modelo.

8. **Painéis ambientais reconstruídos (DEC-009): tabela de licenças completa e fundo sólido.**
   - Hoje: o painel de índices mostra as 33 licenças (painel com 17,3 cm em vez da janela de
     rolagem de 9,84 cm capturada; os painéis seguintes descem); fundo em cor sólida (#275559) no
     lugar da foto da obra.
   - Alternativa: mostrar só as primeiras N linhas como a captura; fundo com a foto, se houver
     acesso ao arquivo do Power BI.
   - Evidência: a captura do Power BI é uma janela de rolagem; não há cópia limpa da foto de fundo.
   - Como mudar: `config/g2_render_rules.yaml`. Nova versão do modelo.

9. **Paginação do Controle de Produtos (DEC-010).**
   - Hoje: menor número de páginas, linhas repartidas por igual entre elas; o 1º recorte começa na
     página da frase de chamada se couberem 3 linhas; a altura da linha cresce quando a descrição
     tem 3 linhas (nenhuma célula cortada).
   - Alternativa: quebra manual como no histórico (31–34 linhas por página) e altura fixa de
     27,6 pt (que corta descrições, como NT-734.1 no publicado).
   - Evidência: com esta regra o nº 14 sai com 43 páginas, igual ao publicado.
   - Como mudar: `components[CONTROL_OF_PRODUCTS].render_params` no modelo. Nova versão.

10. **RD-102 → RD-102A** (DEC-007, sua instrução de 2026-09-27).
    - Hoje: "RD-102A" em todo texto gerado, inclusive na agenda de reuniões do 2.1 (HNK-14-003).
    - Alternativa: manter "RD-102" onde o histórico usava a forma curta.
    - Confirme só que vale também para a agenda.

11. **Nomes das disciplinas no 2.2.**
    - Hoje: nome completo da planilha ("Projeto de Drenagem e Obra de Arte Corrente (OAC)",
      "Projeto Geométrico e Interseções", "Estudos Geotécnicos e Sondagens").
    - Alternativa: as formas curtas do histórico nesses 3 casos ("Projeto de Drenagem", "Projeto
      Geométrico", "Estudos Geotécnicos").
    - Como mudar: `config/data_rules/p22_highway_block.yaml`, `templates.status_line.display_name`
      (tabela de nomes curtos). Nova versão do modelo.

12. **"Análise Programa" vem da planilha, não é digitada.**
    - Hoje: o status Programa das matrizes sai da aba Projetos; se for informado na entrada mensal, é
      ignorado com aviso.
    - Alternativa: aceitar o valor digitado.
    - Evidência: 9 de 12 iguais à planilha; os 3 diferentes ("Não aprovado") contradizem o
      próprio texto do publicado ("em análise pelo Programa").

13. **Número do contrato.** Hoje uma forma única, "Contrato N° 00/0000-PARC" (a Apresentação
    usa essa forma; o Encerramento publicado usa "N°01"). Como mudar:
    `editorial_defaults.contract_ref`.

14. **Data de referência do status ambiental** (GAP-012). Hoje: a data "Atualizado em" que você
    informa; sem ela, a data de emissão (com aviso). Alternativas: instante da geração, fim do mês
    de referência. Como mudar: informar `environmental_reference_date` a cada mês.

15. **Bloco paisagem** (GAP-004). Duas imagens passam da margem direita desde maio (27,02 e
    26,45 cm contra 26,20 cm úteis). Hoje: reproduz o histórico. Alternativa: reduzir para caber.

16. **Bloco de desapropriação e interferências do 2.2** (GAP-006). Só apareceu em agosto. Hoje:
    sai quando você informa os status externos do mês; sem entrada, não sai. Confirmar no nº 15 se
    o bloco se repete.

## 6. Entradas que você fornece todo mês

O builder lê sozinho a Lista Mestra, a planilha de projetos e a planilha ambiental (estado no
instante da geração; a versão de cada uma fica registrada no manifesto). O resto é seu:

| Entrada | Obrigatória | Uso | Se faltar |
|---|---|---|---|
| Data de emissão | sim | capa | não gera |
| Data de assinatura | sim | Encerramento ("Capital, …"); independente da capa | não gera |
| Signatário | sim | Encerramento | obrigatório; o build para se faltar (sem padrão automático) |
| Agenda de reuniões | não | 2.1.2 | padrão: agenda estável do modelo (horários são externos) |
| Status externos do 2.2, por rodovia | não | matrizes de DUP, desapropriação e interferências: GDP, Casa Civil, GFD, concessionária, início dos processos | matriz não sai; campo vazio = pendência com marcador visível (ou "sem informação", item 4 da seção 5) |
| Data "Atualizado em" do 2.2 | não | quadros do 2.2 e cálculo de "pendentes de aprovação" | usa a data ambiental, senão a de emissão (com aviso) |
| Data "Atualizado em" ambiental | não | painéis e textos de licenças e condicionantes | usa a data de emissão (com aviso) |
| BM em elaboração externos | não | 2.4 | derivado da Lista Mestra; a entrada só acrescenta itens de fora |
| Revisão dos textos interpretativos (DEC-013) | sim para os 2 do resumo; natureza das NC: opcional | padronização (IT/CT/POP) e temas dos pareceres no resumo; natureza das NC no 2.4 | resumo: o builder gera um rascunho a partir das descrições, grava a pauta de revisão e marca o relatório como **não pronto** até a revisão; natureza das NC: sem texto aprovado a cláusula não sai (sem rascunho nem pendência) |

Sem chamada a serviço de IA: os textos interpretativos são rascunho determinístico + sua revisão.

**Assinatura digital (DEC-014):** o builder entrega DOCX e PDF **sem assinatura**. Quem assina
aplica a assinatura digital no PDF depois, com a própria credencial. O builder não guarda nem
reproduz a imagem da assinatura.

## 7. Limitações conhecidas

- **Painéis em imagem sem leitura de texto (OCR).** Os quadros do 2.2 e os painéis ambientais do
  2.4 são imagens. O comparador verifica presença, posição, que não estão em branco nem trocados
  (13 de 18 com selo verificado, 5 não verificáveis), mas não lê uma célula dentro deles. O
  conteúdo dos painéis foi conferido por leitura visual na conferência de fontes (3ª rodada).
  Alterar um número dentro de um painel não é detectado automaticamente.
- **Ambiente.** Exige Windows + Excel + Word, em sessão interativa com tela (o Controle de
  Produtos sai do Excel como desenho vetorial), resolução de referência 1920×1080 a 120 dpi e a
  família Arial Nova instalada. Um build por vez (usa a área de transferência).
- **Golden do nº 14 com Lista Mestra v335**, não a v331 indicada pela DEC-012. A planilha ficou
  estável entre v326 e v414, mas a prova exata depende da autorização da seção 8.
- **Golden temporal do nº 13 bloqueado (GAP-015).** O gerado usa a Lista Mestra v134 (a que está
  em disco); o publicado saiu da v162. Lendo a v162 em memória, textos e total de anexos fecham,
  mas o Controle de Produtos precisa do arquivo para o Excel. Os 23 itens que reprovam:

  | Onde | Itens | Publicado (v162) × gerado (v134) |
  |---|---|---|
  | Encerramento | 2 | 165 × 163 anexos (número e extenso) |
  | Controle 2.2 | 5 | NT-679.1, NT-680.1, NT-692.1, NT-696.1, NT-702.1: "Aceitação de Projeto Executivo" × "Aceitação de Documentos" |
  | Controle 2.4 | 2 | PA-640.1 e PA-677.1: "Entregue" × "Em elaboração" |
  | Controle 2.4 | 3 | PA-683.1, PA-684.1, PA-685.1: descrição completa × truncada |
  | Controle 2.4 | 1 | BM-007.1, BM-008.1 e BM-009.1 da RD-104 ausentes no gerado |
  | ANEXOS | 5 | as mesmas 5 NT da descrição |
  | ANEXOS | 2 | PA-640.1 e PA-677.1 ausentes no gerado |
  | ANEXOS | 3 | PA-683.1, PA-684.1, PA-685.1 truncadas |
  | **Total** | **23** | todos explicados pela versão da Lista Mestra |

  O nº 13 gerado tem 44 páginas (publicado 43) pela ressalva por disciplina (mais linhas no 2.2);
  diferença de paginação aceita e registrada.
- **Poda de versões do SharePoint.** O histórico guarda no máximo 500 versões; a planilha de
  projetos já perdeu as v1–v75. Previsão de perda: v127 (nº 11) ≈ 10/10/2026; v161 (nº 12)
  ≈ 16/10/2026; v328 (nº 13) meados de novembro; v438 (nº 14) fim de novembro. Lista Mestra e
  planilha ambiental entram na mesma poda.
- **Integridade das diferenças aprovadas.** O conjunto é congelado por hash, mas quem edita o
  arquivo e o hash juntos passa na conferência; a garantia final é o histórico do Git e esta sua
  revisão.
- **Evidência de um mês só.** O bloco de desapropriação e interferências e o formato das matrizes
  só existem no nº 14 (confiança média/baixa até o nº 15).
- **Imagens institucionais com fotos de pessoas** não ficam no Git; são regeneradas do DOCX do
  nº 14 (com hash conferido).

## 8. Pedido de autorização pendente (GAP-015)

> **Você autoriza copiar para `tmp\historical_sources\` as versões abaixo, lidas do histórico de
> versões do SharePoint (somente leitura; nada é alterado no SharePoint)? Sim ou não.**

- **O quê:** Lista Mestra v162 e v331; planilha de projetos v127, v161, v328 e v438; planilha
  ambiental v289 e v310. A Lista Mestra tem ≈ 130–150 KB por versão.
- **Por quê:** sem a v162 o golden temporal do nº 13 não fecha (os 23 itens da seção 7) e a
  certificação fica sem prova de que o modelo reproduz outro mês; a v331 torna exato o golden do
  nº 14; as demais preservam a prova depois da poda.
- **Prazo:** antes da poda. As primeiras a cair são v127 (≈ 10/10/2026) e v161 (≈ 16/10/2026);
  v328 em meados de novembro. Recomendação: autorizar agora.
- **Onde:** `C:\caminho\exemplo\PROG_Relatorio_G2_Automacao\tmp\historical_sources\` — pasta
  ignorada pelo Git (nunca commitada), fora da sincronização OneDrive da Dynatest. Ficam guardadas
  enquanto forem prova dos golden tests; só são apagadas se você pedir.
- **Registro:** uma linha por arquivo em `state\download_authorizations.jsonl` (identificador do
  arquivo no SharePoint, versão, finalidade, data e quem autorizou) e o hash de cada cópia no
  manifesto da reconstrução.

Com o "sim", o passo seguinte é refazer o nº 13 com a v162 e o nº 14 com a v331 e anexar o
resultado a este pacote.

## 9. Como aprovar

Responda com uma destas três formas:

1. **"Aprovo."**
   O modelo passa a `CERTIFIED`, versão **1.0** (`config/g2_report_model.yaml`, com registro no
   changelog e nos gates), commit e tag de versão no Git (só local). A partir daí "Gerar o
   Relatório G2 nº N" usa este modelo sem reaprender estrutura; mudança permanente de padrão vira
   nova versão (1.1, 2.0…). Os padrões da seção 5 ficam valendo como estão.

2. **"Aprovo com mudanças: …"** (cite os itens da seção 5 e a opção escolhida).
   - Mudanças só de configuração (itens 1/S7, 4, 5, 6, 13): aplicadas, nº 14 reconstruído,
     diferenças revisadas, e certificado como 1.0 sem nova rodada completa.
   - Mudanças de regra ou de visual (itens 1/demais, 2, 3, 7, 8, 9, 11): nova versão do modelo
     (0.15), reconstrução do nº 14, conjunto de diferenças refeito e conferência focada; volta para
     você só a lista do que mudou; com seu ok, `CERTIFIED` 1.0.

3. **"Não aprovo: …"** (diga o motivo).
   O modelo fica em `BUILDER_READY`. Cada objeção vira item registrado, é corrigida numa nova
   versão e volta para você com novo pacote.

Independente da resposta: a seção 8 (sim/não) tem prazo próprio. O Gate D foi registrado como
PASS em 2026-10-04 (`docs/qa/GATES.md`).
