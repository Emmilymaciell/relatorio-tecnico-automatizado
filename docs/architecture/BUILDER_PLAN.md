# Plano de implementação do builder (Fase 7)

**Não implementar ainda.** Decomposição derivada da Fase 4, para que a Fase 7 comece direto.
Regra de ouro: começar de `Document()` vazio. Nunca abrir o relatório anterior.

## Entradas globais

| Entrada | Origem | Observação |
|---|---|---|
| `report_number`, `reference_month` | parâmetro da execução | `prog_g2_report.report_id` |
| Lista Mestra | SharePoint, leitura | snapshot da data de emissão em reconstrução (DEC-008) |
| Planilha de projetos | SharePoint, leitura | abas `GED`, `Projetos`, `Painel de Controle` |
| Assets estáticos | repositório | identidade por sha1 |
| Data de emissão e de assinatura | entrada manual | campos independentes |

## Módulos

| Módulo | Entrada | Saída | Fonte | Depende de | Testes |
|---|---|---|---|---|---|
| `build_document` | spec | documento vazio com 3 seções e estilos | `report_spec` | — | geometria, margens, orientação por seção |
| `build_cover` | número, data de emissão | capa | slide PowerPoint embutido | `build_document` | dois campos substituídos; sangria total |
| `build_header_footer` | — | cabeçalho e rodapé por seção | constantes | `build_document` | texto, campo PAGE, ausência na capa |
| `build_toc` | — | campo TOC | constante | `build_document` | níveis 1 a 3; atualização exige Word |
| `build_presentation` | número, mês | seção de abertura | molde + asset | `build_document` | igualdade com o encerramento |
| `build_landscape_block` | — | 8 páginas | assets estáticos | `build_document` | sha1 de cada asset; sem sangria |
| `build_p21` … `build_p26` | dados do mês | seção do produto | citação literal + narrativa | `render_product_control` | citação byte a byte; frase de ausência |
| `render_product_control` | linhas da Lista Mestra, produto | quadro do Controle de Produtos | Lista Mestra | **GAP-001** | contagem, ordem física, colunas |
| `render_structured_visual` | linhas da aba `Projetos`, rodovia | quadro por rodovia | planilha de projetos | DEC-009 | conteúdo, ordem, completude |
| `build_closing` | número, mês, contagens | encerramento e assinatura | derivado | todos os anteriores | páginas do PDF; anexos = COUNT |
| `build_annex_index` | linhas da Lista Mestra | índice consolidado | Lista Mestra | `render_product_control` | união dos blocos; layout próprio |
| `validate_content` | documento | relatório de checagem | catálogos | todos | número e mês iguais nos dois lugares; nenhum documento fora da Lista Mestra |
| `validate_visual` | PDF gerado e referência | diferenças classificadas | DEC-009 | `validate_content` | separar estrutural de acidental |

## Ordem de construção
1. `build_document` e estilos.
2. `build_cover`, `build_header_footer`, `build_toc`.
3. `build_presentation` e bloco institucional.
4. `build_landscape_block`.
5. Produtos 2.1 a 2.6, cada um chamando os renderizadores.
6. `build_closing` (depende da contagem final de páginas).
7. `build_annex_index`.
8. Atualização de campos pelo Word, depois validação.

## Riscos já conhecidos
- **GAP-001 bloqueia `render_product_control`.** É o único bloqueio total.
- `build_closing` depende da paginação final: precisa de duas passadas ou do Word.
- Ler a planilha **ignorando** o autofiltro salvo; o estado vivo filtra uma rodovia só.
- `build_toc` e a contagem de páginas exigem o Word; registrar como dependência de ambiente.
