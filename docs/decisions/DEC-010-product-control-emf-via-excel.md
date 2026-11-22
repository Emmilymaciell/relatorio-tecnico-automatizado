# DEC-010 — Controle de Produtos gerado como EMF pelo Excel (xlScreen)

**Data:** 2026-10-01 · **Status:** ACEITA (técnica, autopilot) · **Confiança:** CONFIRMED

## Contexto
GAP-001 era o único bloqueio total do builder: o conteúdo do Controle de Produtos é 100%
derivável da Lista Mestra, mas a representação histórica é um metarquivo vetorial (EMF) colado
do Excel. A prova de 2026-10-01 (`scripts/12_probe_emf_export.py`, achados em
`docs/discovery/WAVE1_FINDINGS.md` §A) reproduziu os 11 recortes do Relatório G2 nº 14 —
Agosto/2026 com frame e bounds idênticos ao histórico (tolerância 0,001 cm).

## Decisão
1. **Representação:** EMF vetorial obtido pelo próprio Excel: `Range.CopyPicture(Appearance=xlScreen,
   Format=xlPicture)` e leitura de `CF_ENHMETAFILE` (`win32clipboard.GetClipboardData(14)`).
   `xlPrinter` não reproduz o histórico. `Chart.Export("EMF")` não funciona (gera 0 bytes).
2. **Fonte:** cópia somente leitura da Lista Mestra no snapshot do relatório; o filtro salvo é
   descartado e substituído pelo filtro explícito do modelo (DEC-006, DEC-009). A planilha
   nunca é salva. Instância própria do Excel (`DispatchEx`), sempre fechada.
3. **Recorte:** um EMF por página; cada recorte repete as linhas 1–3 (título e cabeçalho).
   Paginação: número mínimo de páginas que cabem na altura útil (26,2 cm a 17,5 cm; até 37
   linhas por página), com as linhas distribuídas por igual (`balance`), para não deixar um
   recorte de uma linha só. O histórico quebra à mão (31–34 linhas); é padronização (DEC-007),
   não divergência de conteúdo.
   **1º recorte (revisão de 2026-10-01, QA-D do Gate D):** o 1º recorte começa na página da
   frase de chamada ("A relação dos produtos…"), como no nº 14 p24 (frase e 25 linhas na mesma
   página), nº 13 p16/p22 e nº 12. Regra (`CONTROL_OF_PRODUCTS.render_params.first_slice_*`):
   - a 1ª passada do Word gera o PDF; nele se localiza a frase (texto + ordem de ocorrência,
     `render.pdf_layout`) e mede-se o espaço livre até a base do corpo da página, menos a folga
     `first_slice_gap_cm` (0,3 cm: espaçamento de 6 pt após a frase + arredondamento; medido
     0,11 cm entre a base da frase e o topo do recorte no nº 14);
   - se nesse espaço couberem `first_slice_min_rows` (3) linhas, o 1º recorte é dimensionado
     para ele; senão desce para a página seguinte junto com a frase, com a altura útil menos a
     altura da frase. Nos dois casos a frase recebe keep-with-next
     (`positioning.keep_with_next.before_product_control`);
   - os demais recortes seguem a paginação balanceada acima, em páginas inteiras; se sobrarem
     menos de `first_slice_min_rows` linhas para depois, o 1º recorte cede linhas à cauda;
   - a medição é feita uma vez (a posição da frase só depende do que vem antes dela na mesma
     seção, e cada produto abre página); as passadas seguintes só confirmam a contagem de
     páginas. Os ANEXOS não têm frase de chamada e não mudam.
   Histórico misto (nº 11 sempre na página seguinte; nº 13 p30 deixou 19 cm em branco): a
   regra é padronização, confiança MEDIUM no limiar de 3 linhas.
4. **Altura de linha (revisão de 2026-10-02, builder MM):** cada linha selecionada tem
   `max(27,6 pt, altura do AutoFit do Excel)` (`render_params.row_height_pt` = mínimo,
   `row_height_mode: min_autofit`). 27,6 pt continua o padrão do nº 14 (MEDIUM: o nº 13
   variava); a regra anterior (uniforme 27,6 pt) cortava descrições de 3 linhas: no nº 13
   NT-688.1 e PA-672.1 (2.2, 2.4 e ANEXOS) e no nº 14 NT-734.1 ("…e Projeto de", o publicado
   também corta — anomalia `CONTROLE_PRODUTOS_DESCRICAO_CORTADA`) e NT-765.1 (3ª linha cortada
   pela borda). Regra:
   - o AutoFit roda só sobre as células `columns` (D:I) de cada linha, na cópia em memória, com
     a tipografia do desenho (`normalize_data_font` aplicado antes); alturas e negrito são
     restaurados e a planilha nunca é salva (`ExcelEmfRenderer.measure_row_heights`);
   - a medição é feita na 1ª passada do montador e memorizada (`CachingEmfRenderer`); as
     passadas seguintes reusam as mesmas alturas, aplicadas linha a linha antes do `CopyPicture`;
   - a paginação (§3) usa as alturas reais por linha: gulosa por soma de alturas; `balance`
     mantém o nº de páginas e reparte as linhas o mais igual possível que caiba (com altura
     uniforme o resultado é o mesmo de antes); o 1º recorte conta as primeiras linhas reais;
   - offline (sem Excel: testes e fallback) as alturas vêm de um estimador por nº de linhas do
     texto (`render_params.row_height_estimate`: quebra por palavra com caracteres por linha
     por coluna e 13,8 pt por linha), calibrado contra o AutoFit real de 2513 linhas (v134.0 e
     v335.0): 2510 iguais, 3 superestimadas, nenhuma subestimada.
   Prova: teste `office` com descrição longa sintética (nenhum EXTTEXTOUTW fora do retângulo da
   linha no EMF) e testes offline de paginação com alturas variáveis.
5. **Inserção no DOCX:** parte OPC `image/x-emf` + relação de imagem + `wp:inline`, largura
   17,5 cm; altura pelo aspecto de `rclFrame` convertido para pixels do dispositivo (erro ≤ 0,12%
   contra o `wp:extent` histórico; `rclBounds` erra ~1,7% quando o texto passa da borda). Puro
   python-docx/lxml.
6. **Rótulos das colunas** vêm do cabeçalho da Lista Mestra no snapshot ("Parecer" em julho,
   "Manifestação" em agosto): é dado, não escolha editorial.
7. **Formatação das linhas de dados** (`render_params.normalize_data_font`, DEC-007): antes do
   `CopyPicture`, `Font.Bold = False` nas células das linhas de dados selecionadas, só na cópia
   em memória (restaurado depois; a planilha nunca é salva). Título e cabeçalho mantêm o
   negrito. O negrito herdado da planilha não é dado: o QA-D do nº 14 achou 194 spans em
   negrito na 2ª coluna do gerado e 0 na referência. Prova: teste `office` que lê os registros
   EXTCREATEFONTINDIRECTW/EXTTEXTOUTW do EMF (`render.docx_emf.emf_text_runs`).

## Consequências
- GAP-001 → RESOLVED. O builder passa a ter dependência de ambiente: **Windows + Excel + Word +
  sessão interativa com tela**. xlScreen depende de DPI e resolução (referência: 1920×1080,
  120 dpi lógicos); o QA mede o frame do EMF gerado e acusa desvio.
- Testes offline cobrem seleção, recorte, paginação e inserção OPC com EMF sintético; os
  testes que abrem Excel/Word ficam sob o marcador `office`.
- A área de transferência é recurso exclusivo: só um processo do builder por vez.
