"""FASE 4 — matriz de reprodutibilidade e análise de lacunas.

    .venv\\Scripts\\python scripts\\11_reproducibility_matrix.py

Responde de imediato: **o que já sabemos reproduzir** e **o que ainda impede o builder**.

Saídas:
    data/catalog/reproducibility_matrix.jsonl
    data/catalog/gaps.jsonl
    state/readiness.yaml   resumo calculado a partir da matriz e dos gaps

Reexecutar reescreve tudo, de forma determinística. Cada linha reflete evidência já
registrada em `docs/discovery/` e nos demais catálogos — não repete investigação.

Rodada 2026-10-01 (Gate A): aplica `docs/discovery/WAVE1_FINDINGS.md` §A–§O e DEC-010 a
DEC-012. Regras de contagem:
    - componente descontinuado (`current_standard=False`) fica na matriz para não voltar por
      engano, mas fora de todas as contagens de prontidão;
    - componente fundido em outro sai da matriz e fica em `MERGED` (sem dupla contagem);
    - `blockers` impedem a GERAÇÃO; `validation_blockers` impedem só a validação histórica;
    - CONFIRMED exige `historical_validated`: sem ele a confiança cai para HIGH (F §12),
      exceto MANUAL_INPUT, cuja confiança qualifica a classificação "não há fonte".
Os booleanos ainda são declarados aqui, não medidos por teste (H): o readiness.yaml diz isso.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prog_g2_report import REPO_ROOT
from prog_g2_report.catalog import (
    AutomationClass,
    Confidence,
    Gap,
    GapStatus,
    ReproducibilityEntry,
)
from prog_g2_report.security import assert_write_allowed

CATALOG = REPO_ROOT / "data" / "catalog"
STATE = REPO_ROOT / "state"

AC = AutomationClass
C = Confidence
OPEN, RESOLVED = GapStatus.OPEN, GapStatus.RESOLVED
OK = {"source_known": True, "source_exact": True, "transformation_known": True}
VALIDATED_MONTHS = ["2026-07", "2026-08"]  # DEC-012: snapshots provados para julho e agosto


def entry(component_id: str, section: str, automation: AC, confidence: C, **kwargs):
    item = ReproducibilityEntry(
        component_id=component_id, section=section,
        automation_class=automation, confidence=confidence, **kwargs,
    )
    if (
        item.current_standard
        and item.confidence == C.CONFIRMED
        and not item.historical_validated
        and item.automation_class != AC.MANUAL_INPUT
    ):
        item.confidence = C.HIGH  # F §12: confiança não pode passar da evidência
    return item


MATRIX = [
    # ---------------------------------------------------- estrutura
    entry("PAGE_GEOMETRY", "documento", AC.CODE, C.CONFIRMED, **OK,
          visual_rule_known=True, historical_validated=True,
          note="A4; 3 seções retrato/paisagem/retrato; margens 2,0/1,5/2,0/1,5; na paisagem "
               "2,0/1,5/1,5/2,0 = retrato girado pelo Word (herança, reproduzir; H). Header 1,0; "
               "footer 0,0. Idêntico nos quatro meses."),
    entry("HEADER", "documento", AC.CODE, C.CONFIRMED, **OK,
          visual_rule_known=True, historical_validated=True,
          note="'PROGRAMA | CONSÓRCIO ESTRUTURADOR DO PROGRAMA' com filete; ausente na "
               "capa. XML literal das partes em tmp/agent_I/ooxml_base.yaml (I)."),
    entry("FOOTER", "documento", AC.CODE, C.CONFIRMED, **OK,
          visual_rule_known=True, historical_validated=True,
          note="'-CONFIDENCIAL-' à esquerda e campo PAGE à direita; uma parte por seção."),
    entry("SECTION_SKELETON", "documento", AC.CODE, C.CONFIRMED, **OK,
          content_rule_known=True, visual_rule_known=True, historical_validated=True,
          note="22 títulos, ordem e estilos fixos nos quatro meses; numeração numId 15 → "
               "abstractNum 23 (I). ENCERRAMENTO e ANEXOS em estilo 'Ttulo'. Quebra antes do "
               "2.6 é HIGH, não regra provada (F: pode ser coincidência de paginação)."),
    entry("TOC", "documento", AC.CODE, C.CONFIRMED, **OK,
          content_rule_known=True,
          note="Campo TOC \\o \"1-3\" \\z \\u \\h dentro de bloco SDT. Precisa do Word para "
               "atualizar os números de página na geração."),
    entry("CONTRACT_QUOTE_P2X", "produtos 2.1 a 2.6", AC.CODE, C.CONFIRMED, **OK,
          content_rule_known=True, visual_rule_known=True, historical_validated=True,
          note="SOURCE_VERBATIM (DEC-007): 24 de 24 blocos idênticos byte a byte (J); 3 "
               "parágrafos, recuo esquerdo 2832 twips, itálico. Parágrafo vazio entre citação e "
               "Ttulo3 só em 2.1/2.3/2.5/2.6."),
    entry("NO_ACTIVITY_SENTENCE", "produtos 2.3, 2.5, 2.6", AC.CODE, C.HIGH, **OK,
          content_rule_known=True, historical_validated=True,
          note="Frase idêntica em 12 de 12 ocorrências: CONFIRMED como texto, HIGH como "
               "condição (H: a ausência nunca alternou na janela). Condição: produto sem "
               "documento na Lista Mestra do relatório."),
    entry("TABLE_CALL_SENTENCE", "produtos 2.1, 2.2, 2.4", AC.CODE, C.CONFIRMED, **OK,
          content_rule_known=True, historical_validated=True,
          note="Uma ocorrência por produto com linhas, sempre antes do Controle de Produtos. "
               "Presença derivada, não 'três por relatório' (F: hardcode de agosto)."),
    entry("SIGNATURE_TABLE", "encerramento", AC.TEMPLATE, C.CONFIRMED, **OK,
          content_rule_known=True, visual_rule_known=True, inputs=["signatory_name"],
          note="Única tabela nativa do Word: 2 linhas × 1 coluna, 8,0 cm, COM texto (J): "
               "'Eng° {signatory_name}' TNR 9 / razão social TNR 6 negrito / 'Produto P2.1 – "
               "Relatório Mensal – Grupo 2.' TNR 6. O signatário mudou no nº 13 "
               "(TRUE_MODEL_CHANGE): nome é entrada."),
    # ---------------------------------------------------- derivados da Lista Mestra
    entry("CONTROL_OF_PRODUCTS", "produtos 2.1, 2.2, 2.4 e anexos", AC.STRUCTURED_DATA,
          C.CONFIRMED, **OK, representation_known=True, visual_rule_known=True,
          content_rule_known=True, historical_validated=True,
          note="Funde PRODUCT_TABLE_REPRESENTATION (G). Conteúdo: body_rows = N° Relatório == n, "
               "todas as linhas (DEC-012), por produto; rótulos do cabeçalho do snapshot. "
               "Representação: EMF vetorial pelo próprio Excel, CopyPicture(xlScreen) + "
               "CF_ENHMETAFILE, um EMF por página com linhas 1–3 repetidas, paginação gulosa "
               "até 26,2 cm, inserção OPC image/x-emf a 17,5 cm (DEC-010). Prova: 11/11 "
               "recortes do nº 14 idênticos em frame e bounds (0,001 cm) e conteúdo. Altura de "
               "linha 27,6 pt é default MEDIUM. Dependência de ambiente: Windows + Excel + "
               "Word + sessão interativa, 1920×1080 a 120 dpi."),
    entry("ANNEX_COMPOSITION", "anexos", AC.STRUCTURED_DATA, C.HIGH, **OK,
          content_rule_known=True, visual_rule_known=True, historical_validated=True,
          note="index_rows = body_rows ∧ Status Entrega == 'Entregue' (DEC-012): índice de "
               "ANEXOS e arquivos anexados. Julho: v162 exclui 6 BM 'Em elaboração' e dá 165; "
               "agosto: v331, 149 linhas (filtro neutro). Coluna do filtro (Status × Data "
               "Entrega) MEDIUM. Layout do índice tem larguras próprias (EMF, DEC-010). Pastas: "
               "Produto / Tipo renomeado / Rodovia."),
    entry("CLOSING_ANNEX_COUNT", "encerramento", AC.CODE, C.CONFIRMED, **OK,
          content_rule_known=True, historical_validated=True,
          note="COUNT(index_rows) — linhas entregues, não códigos distintos (149 linhas × 135 "
               "códigos no nº 14). Por extenso entre parênteses. Julho 165, agosto 149."),
    entry("CLOSING_PAGE_COUNT", "encerramento", AC.CODE, C.CONFIRMED, **OK,
          content_rule_known=True, historical_validated=True,
          note="Contagem de páginas do PDF final; confere nos quatro meses. 'páginas' pede "
               "numeral feminino (uma, duas), ainda não exercitado (J)."),
    entry("PRESENTATION_PARAGRAPH", "apresentação", AC.TEMPLATE, C.CONFIRMED, **OK,
          content_rule_known=True,
          note="Molde com número, mês e ano. O mesmo dado aparece no Encerramento: o builder "
               "deriva os dois do mesmo campo e valida a igualdade."),
    entry("CLOSING_PARAGRAPH", "encerramento", AC.TEMPLATE, C.CONFIRMED, **OK,
          content_rule_known=True,
          note="Molde com seis campos, todos deriváveis; '{n} ({extenso})' em minúsculas "
               "reproduz os 4 meses (J)."),
    entry("SIGNATURE_DATE", "encerramento", AC.MANUAL_INPUT, C.HIGH, **OK,
          content_rule_known=True, inputs=["signature_date"],
          note="Entrada humana: a data em que a Emmily assina. Formato 'Capital, DD de Mês de "
               "AAAA'. 'Mês seguinte ao de referência' e 'nunca coincide com a capa' são "
               "observações, não regras (F)."),
    entry("WEEKLY_REPORT_CUTOFF", "produto 2.4", AC.CODE, C.CONFIRMED, **OK,
          content_rule_known=True, historical_validated=True,
          note="'até o dia 25/MM/AAAA' é texto fixo do mês de referência (D)."),
    # ---------------------------------------------------- assets
    entry("LANDSCAPE_BLOCK", "seção paisagem", AC.STATIC_ASSET, C.CONFIRMED,
          **OK, visual_rule_known=True, historical_validated=True,
          note="8 páginas, uma imagem por página, 26,20 × 14,74 cm. Seis sha1 idênticos desde "
               "o nº 11, quatro desde o nº 12; manifesto de sha1 em config/assets_manifest.yaml "
               "(I). Organograma = slides de cargos, sem nomes nem fotos. Reutilizar."),
    entry("PRESENTATION_LOGO", "apresentação", AC.STATIC_ASSET, C.CONFIRMED,
          **OK, visual_rule_known=True, historical_validated=True,
          note="16,04 × 5,19 cm, sha1 estável nos quatro meses. Não é logotipo: é uma faixa de "
               "5 fotos com pessoas (contains_people_photos: true, I)."),
    entry("P2.2_PREDECESSOR_DIAGRAM", "produto 2.2", AC.STATIC_ASSET, C.CONFIRMED,
          **OK, visual_rule_known=True, historical_validated=True,
          note="EMF de 15,22 × 11,83 cm, sha1 idêntico nos quatro meses."),
    entry("COVER", "capa", AC.TEMPLATE, C.HIGH, **OK,
          visual_rule_known=True, content_rule_known=True,
          inputs=["report_number", "issue_date"],
          note="DEC-011 (b'): fundo estático sem texto (asset com sha1, composto das mídias do "
               "slide) com sangria total + textos da capa como parágrafos do Word em posição "
               "absoluta; seção 0 com titlePg e cabeçalho/rodapé da 1ª página vazios. Elimina a "
               "prévia OLE de 11 MB e os defeitos de julho ('11de') e agosto (data ilegível). "
               "Texto pesquisável no PDF é diferença intencional."),
    # ---------------------------------------------------- painéis reconstruídos (DEC-009)
    entry("P2.2_ROAD_DASHBOARDS", "produto 2.2", AC.RECONSTRUCTED_VISUAL, C.CONFIRMED,
          **OK, representation_known=True, visual_rule_known=True, historical_validated=True,
          note="DEC-009: reconstruir, não reproduzir a captura. Aba 'Projetos' filtrada por "
               "obra, ordenada pela ordem de disciplina; autofiltro salvo descartado. Validado "
               "em 2026-07 e 2026-08: snapshots DEC-012 v328 e v438 reproduzem 100% das linhas "
               "e células dos 8 quadros (E). Power BI é referência visual apenas (GAP-003)."),
    entry("P2.4_LICENSE_DASHBOARDS", "produto 2.4", AC.RECONSTRUCTED_VISUAL, C.HIGH,
          **OK, representation_known=True, visual_rule_known=True, content_rule_known=True,
          historical_validated=True,
          note="Fonte exata (B): '04_Acompanhamento - Licenca Ambiental.xlsx' (item "
               "01EXEMPLOITEMID000000000000000000). Painel 'Índices' (1/mês): aba 'Licenças' "
               "B:P, cab. linha 2, todas as linhas; total, emitidas (Nº Licença preenchido), "
               "pendentes (Status 'Aguardando a liberação'), barras por rodovia, fases. Painéis "
               "'Status das Condicionantes' (4/mês): aba 'Condicionantes' A:L incluindo linhas "
               "ocultas, Responsável → rodovia (aba 'Empresas'), status recalculado com data de "
               "referência explícita (nunca o cache de TODAY()). Contagens CONFIRMED nº 11–14; "
               "ordem das barras HIGH; ordem da tabela e nomes de empresa MEDIUM. Snapshots: "
               "v289 (nº 13), v310 (nº 14), pelo 'Atualizado em'."),
    # ---------------------------------------------------- texto variável
    entry("EXECUTIVE_SUMMARY", "produto 2.1", AC.TEMPLATE, C.HIGH, **OK,
          content_rule_known=True, historical_validated=True,
          note="≈90% fixo ou derivável (K): 19 afirmações em agosto, FIXED 47%, DERIVABLE 42%, "
               "INTERPRETIVE 5%. Gatilhos: produtos com linhas; cláusula das Atas ⇔ existe AT "
               "(4/4); slot de padronização só com IT/CT/POP; temas dos PA por palavra-chave "
               "(MEDIUM). EXTERNAL ocasional (POP, mesa técnica TCE-UF em maio/junho). Molde em "
               "tmp/agent_K/executive_summary_template.yaml."),
    entry("EXECUTIVE_SUMMARY_PARECER_THEMES", "produto 2.1", AC.AI_SYNTHESIS, C.MEDIUM,
          source_known=True, content_rule_known=True,
          blockers=["exige sintetizar os temas dos pareceres do período"],
          note="Único trecho do resumo (≈5%) que precisa de interpretação real."),
    entry("P2.1_MEETINGS_AGENDA", "produto 2.1", AC.TEMPLATE, C.MEDIUM, **OK,
          content_rule_known=True, inputs=["p21_meeting_hours"],
          note="Não é contagem: é agenda (rodovia, executora, dia, hora) (K). Dia da semana = "
               "moda das atas 'Reunião de alinhamento técnico' da Lista Mestra (nº 11–13); "
               "executora pela aba 'Painel de Controle'; hora é EXTERNAL (configuração estável, "
               "entrada). Agenda da RD-101 mudou na janela (TRUE_MODEL_CHANGE, J)."),
    entry("P2.2_DISCIPLINE_STATUS", "produto 2.2", AC.STRUCTURED_DATA, C.HIGH, **OK,
          representation_known=True, content_rule_known=True, historical_validated=True,
          note="Aba 'Projetos' de '03 - Acompanhamento de Projetos Executivo.xlsx'. Mapeamento "
               "rótulo→filtro validado 8/8 e 5/5; snapshots v328/v438 (DEC-012) sem contradição "
               "no nº 13 e com uma no nº 14 (anomalia). Lista de exclusão de disciplinas e "
               "normalização de 'RD-102 A'. 'Pendentes de aprovação' é hipótese MEDIUM (E). "
               "Conjunto vazio: default = forma mais frequente (GAP-014)."),
    entry("P2.2_EXTERNAL_STATUS", "produto 2.2", AC.MANUAL_INPUT, C.CONFIRMED, **OK,
          content_rule_known=True, inputs=["p22_external_status"],
          note="Entrada humana estruturada por rodovia (PROGRAMA, GDP, Casa Civil, "
               "interferências) (E): 12 termos em 4.294 itens de 196 planilhas, nenhuma "
               "planilha de acompanhamento de DUP ou interferências. GAP-009 RESOLVED."),
    entry("P2.2_EXPROPRIATION_LAYOUT", "produto 2.2", AC.TEMPLATE, C.MEDIUM, **OK,
          content_rule_known=True, inputs=["p22_external_status"],
          validation_blockers=["um único mês de evidência para o bloco de interferências "
                               "(GAP-006)"],
          note="O conteúdo de desapropriação já existia nos nº 11 e nº 12 como observação por "
               "rodovia: agosto promoveu a seção própria (reestruturação de representação). Só "
               "o bloco de interferências com a concessionária é estreia. Gera a partir da "
               "entrada p22_external_status, no layout de agosto; presença = entrada não vazia."),
    entry("P2.4_DOCUMENT_CITATIONS", "produto 2.4", AC.STRUCTURED_DATA, C.CONFIRMED, **OK,
          content_rule_known=True, historical_validated=True,
          note="8 de 8 blocos derivam da Lista Mestra (D, O). Faixa de RO por rodovia = 1º e "
               "último código de N° Relatório == n ∧ Manifestação == Relatório Semanal, na ordem "
               "física, com a revisão real; período = menor início e maior fim do Período; "
               "76/76. Ordens dos demais blocos são constantes do modelo (O). GAP-010 RESOLVED."),
    entry("P2.4_NONCONFORMITY_PARAGRAPH", "produto 2.4", AC.TEMPLATE, C.HIGH, **OK,
          content_rule_known=True, historical_validated=True,
          validation_blockers=["critério editorial de enumerar NC (GAP-013): o histórico não "
                               "enumera com 8 a 25 NC"],
          note="NC é texto, não painel (C): frase fixa (nº 05–14) + enumeração opcional dos "
               "códigos por rodovia + complemento de RNC (só nº 14, MEDIUM). Enumeração pela "
               "Lista Mestra, Manifestação == 'Notificação de não conformidade' (grafia "
               "normalizada), por Empreendimento, natureza pela Descrição: 100% nos nº 12 e 13. "
               "Default enquanto GAP-013 aberto: enumerar sempre que houver NC."),
    entry("P2.4_PENDING_LICENSES_TEXT", "produto 2.4", AC.TEMPLATE, C.CONFIRMED, **OK,
          content_rule_known=True, historical_validated=True,
          note="Contagem de licenças pendentes da aba 'Licenças' (Status == 'Aguardando a "
               "liberação') por rodovia, verbalizada; bate nos 4 meses (B). Concordância "
               "'licenças referentes' e rótulo 'recurso(s) hídrico(s)' são editoriais (O)."),
    entry("P2.4_CONDITIONS_TEXT", "produto 2.4", AC.TEMPLATE, C.CONFIRMED, **OK,
          content_rule_known=True, historical_validated=True,
          note="Por rodovia, a partir do status recalculado das condicionantes (B): 0 próximas "
               "→ 'Não apresenta condicionantes em atraso;', 1 → '…apenas uma condicionante "
               "próxima…', >1 → '…algumas…'. Bate 100%. Pendentes > 0 nunca observado "
               "(UNKNOWN, O). Data de referência do status: GAP-012 (default = instante da "
               "geração)."),
    # ---------------------------------------------------- descontinuados (fora da contagem)
    entry("P2.2_PANEL_EMF_DISCONTINUED", "produto 2.2", AC.DISCONTINUED, C.CONFIRMED,
          current_standard=False, **OK, historical_validated=True,
          note="DESCONTINUADO: recorte da aba 'Painel de Controle' em metarquivo existiu em maio "
               "e junho e sumiu a partir de julho. Registrado para não ser reintroduzido."),
    entry("P2.4_NONCONFORMITY_PANEL", "produto 2.4", AC.DISCONTINUED, C.CONFIRMED,
          current_standard=False, historical_validated=True,
          note="NUNCA EXISTIU (C): nenhum relatório, do nº 01 ao nº 14, traz painel de NC; o "
               "nº 07 prometeu um Power BI que não apareceu. A planilha '02_…NC "
               "automatizada.xlsm' não é fonte do Relatório G2. Substituído por "
               "P2.4_NONCONFORMITY_PARAGRAPH."),
]

# Componente fundido -> componente que o absorve (sem dupla contagem; G).
MERGED = {"PRODUCT_TABLE_REPRESENTATION": "CONTROL_OF_PRODUCTS"}

GAPS = [
    Gap(gap_id="GAP-001", component="CONTROL_OF_PRODUCTS",
        impact_on_report="11 páginas no nº 14; aparece todo mês em 3 produtos e nos anexos",
        what_is_missing="nada: EMF vetorial via Excel COM (xlScreen) reproduz 11/11 recortes do "
                        "nº 14",
        best_next_action="implementar conforme DEC-010",
        estimated_investigation_cost="MEDIO", blocks_builder=False, priority="P0",
        confidence=C.CONFIRMED, status=RESOLVED, resolved_by="DEC-010"),
    Gap(gap_id="GAP-002", component="COVER",
        impact_on_report="página 1",
        what_is_missing="nada: fundo estático + textos do Word em posição absoluta",
        best_next_action="implementar conforme DEC-011",
        estimated_investigation_cost="BAIXO", blocks_builder=False, priority="P3",
        confidence=C.HIGH, status=RESOLVED, resolved_by="DEC-011"),
    Gap(gap_id="GAP-003", component="POWER_BI_DASHBOARDS",
        impact_on_report="painéis do 2.2 e do 2.4 (reconstruídos a partir do dado)",
        what_is_missing="referência visual apenas (DEC-009): acesso ao Power BI publicado "
                        "serviria só para conferir cores e layout; não entra na geração",
        best_next_action="se a Emmily quiser, informar o workspace Power BI para comparação "
                         "visual; sem isso, usar os PDFs históricos como referência",
        estimated_investigation_cost="MEDIO", blocks_builder=False, priority="P3",
        confidence=C.CONFIRMED),
    Gap(gap_id="GAP-004", component="LANDSCAPE_BLOCK_MARGIN",
        impact_on_report="duas páginas do bloco institucional",
        what_is_missing="decidir se corrige: duas imagens do bloco paisagem passam da margem "
                        "direita (27,02 cm e 26,45 cm contra 26,20 cm de área útil). (STATE e o "
                        "YAML candidato usavam GAP-004 para condicionantes: a fonte ambiental "
                        "agora é GAP-011.)",
        best_next_action="decisão da Emmily; o defeito vem desde maio",
        estimated_investigation_cost="BAIXO", blocks_builder=False, priority="P3",
        confidence=C.CONFIRMED, default_if_open="reproduzir como no histórico"),
    Gap(gap_id="GAP-005", component="EXECUTIVE_SUMMARY",
        impact_on_report="cerca de 9 parágrafos, reescritos todo mês",
        what_is_missing="≈90% fixo ou derivável (K); falta só promover o molde com slots ao "
                        "modelo e tratar o ≈5% interpretativo e o EXTERNAL ocasional",
        best_next_action="levar tmp/agent_K/executive_summary_template.yaml ao modelo",
        estimated_investigation_cost="BAIXO", blocks_builder=False, priority="P1",
        confidence=C.HIGH),
    Gap(gap_id="GAP-006", component="P2.2_EXPROPRIATION_BLOCK",
        impact_on_report="cerca de 60 parágrafos, só em agosto",
        what_is_missing="o gatilho que faz o bloco existir e se ele permanece nos próximos meses",
        best_next_action="verificar no relatório nº 15, quando sair, se o bloco se repete",
        estimated_investigation_cost="BAIXO", blocks_builder=False, priority="P2",
        confidence=C.LOW, blocks_validation=True),
    Gap(gap_id="GAP-007", component="MASTER_LIST_HISTORY",
        impact_on_report="validação histórica",
        what_is_missing="nada para o golden test: julho (v162) e agosto (v331) têm snapshot "
                        "provado; maio e junho ficam sem snapshot (histórico começa em 20/07)",
        best_next_action="golden test em 2026-07 e 2026-08",
        estimated_investigation_cost="BAIXO", blocks_builder=False, priority="P3",
        confidence=C.CONFIRMED, status=RESOLVED, resolved_by="DEC-012"),
    Gap(gap_id="GAP-008", component="P2.2_DISCIPLINE_STATUS",
        impact_on_report="4 blocos por mês no produto com mais conteúdo",
        what_is_missing="nada: snapshots DEC-012 v328 e v438 reproduzem 100% dos quadros do 2.2 "
                        "nos nº 13 e 14 (E)",
        best_next_action="usar v328/v438 no golden test",
        estimated_investigation_cost="BAIXO", blocks_builder=False, priority="P1",
        confidence=C.CONFIRMED, status=RESOLVED, resolved_by="DEC-012 + WAVE1 §E"),
    Gap(gap_id="GAP-009", component="P2.2_EXTERNAL_STATUS",
        impact_on_report="cerca de 60 parágrafos em agosto",
        what_is_missing="não há planilha de GDP/Casa Civil/GFD/concessionária (12 termos em "
                        "4.294 itens, E): esses campos são entrada humana estruturada; a Análise "
                        "Programa vem da aba Projetos (schema.derived.prog, QA2-E)",
        best_next_action="declarar a entrada p22_external_status no modelo (por rodovia)",
        estimated_investigation_cost="BAIXO", blocks_builder=False, priority="P1",
        confidence=C.CONFIRMED, status=RESOLVED,
        resolved_by="WAVE1 §E (MANUAL_INPUT p22_external_status); QA2-E (prog derivado)"),
    Gap(gap_id="GAP-010", component="P2.4_WEEKLY_REPORT_RANGE",
        impact_on_report="4 faixas por mês no produto 2.4",
        what_is_missing="nada: a fonte de verdade é a Lista Mestra (76/76); a divergência do "
                        "texto vem de uma única semana (25/07–31/07) e é anomalia (D)",
        best_next_action="implementar a regra da Lista Mestra; avisar semana iniciada entre 25 "
                         "e 31 e sobreposição com o relatório anterior",
        estimated_investigation_cost="BAIXO", blocks_builder=False, priority="P1",
        confidence=C.CONFIRMED, status=RESOLVED, resolved_by="WAVE1 §D"),
    Gap(gap_id="GAP-011", component="P2.4_LICENSE_SOURCE",
        impact_on_report="5 painéis e 2 textos por mês no produto 2.4",
        what_is_missing="nada: '04_Acompanhamento - Licenca Ambiental.xlsx', abas Licenças, "
                        "Condicionantes e Empresas; contagens CONFIRMED nos nº 11–14 (B)",
        best_next_action="implementar leitura e recálculo do status",
        estimated_investigation_cost="MEDIO", blocks_builder=False, priority="P1",
        confidence=C.CONFIRMED, status=RESOLVED, resolved_by="WAVE1 §B"),
    Gap(gap_id="GAP-012", component="P2.4_CONDITIONS_REFERENCE_DATE",
        impact_on_report="status das condicionantes (4 painéis e textos por rodovia)",
        what_is_missing="decisão: qual data de referência usar para recalcular o status na "
                        "produção (o histórico usa o 'Atualizado em' do painel)",
        best_next_action="decisão da Emmily (geração, fim do mês de referência ou data de corte)",
        estimated_investigation_cost="BAIXO", blocks_builder=False, priority="P1",
        confidence=C.HIGH, default_if_open="instante da geração (registrado no manifesto)"),
    Gap(gap_id="GAP-013", component="P2.4_NC_ENUMERATION_CRITERION",
        impact_on_report="parágrafo de não conformidades do 2.4",
        what_is_missing="critério editorial de enumerar NC: o histórico enumera com 2 e 4 NC, "
                        "não com 8 a 25 (LOW)",
        best_next_action="decisão da Emmily (limiar ou sempre)",
        estimated_investigation_cost="BAIXO", blocks_builder=False, priority="P2",
        confidence=C.LOW, default_if_open="enumerar sempre que houver NC",
        blocks_validation=True),
    Gap(gap_id="GAP-014", component="P2.2_EMPTY_SET_WORDING",
        impact_on_report="linhas de conjunto vazio nos blocos de status do 2.2",
        what_is_missing="verbalização do conjunto vazio: 4 formas literais + omissão da linha (J)",
        best_next_action="decisão da Emmily; DEC-007 permite padronizar",
        estimated_investigation_cost="BAIXO", blocks_builder=False, priority="P2",
        confidence=C.CONFIRMED,
        default_if_open="forma mais frequente (16/22): 'nenhuma disciplina encontra-se em "
                        "análise no fechamento do presente relatório;' e sempre emitir a linha"),
    Gap(gap_id="GAP-015", component="SHAREPOINT_VERSION_RETENTION",
        impact_on_report="golden tests de julho e agosto",
        what_is_missing="retenção de versões do SharePoint (limite de 500): snapshots dos golden "
                        "tests serão podados (planilha de projetos já perdeu v1–v75; nº 13 v328 "
                        "≈ meados de novembro, nº 14 v438 ≈ fim de novembro; Lista Mestra e "
                        "ambiental na mesma poda)",
        best_next_action="autorização da Emmily para persistir snapshots em "
                         "tmp/historical_sources/",
        estimated_investigation_cost="BAIXO", blocks_builder=False, priority="P1",
        confidence=C.CONFIRMED, blocks_validation=True),
]


def _counts(items, key) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        value = key(item)
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items()))


def summarize() -> dict:
    ids = [e.component_id for e in MATRIX]
    assert len(ids) == len(set(ids)), "component_id duplicado na matriz"
    assert not set(MERGED) & set(ids), "componente fundido não pode continuar na matriz"
    current = [e for e in MATRIX if e.current_standard]
    ready = [e for e in current if e.ready]
    blocked = [e for e in current if not e.ready]
    gap_ids = [g.gap_id for g in GAPS]
    assert len(gap_ids) == len(set(gap_ids)), "gap_id duplicado"
    open_gaps = [g for g in GAPS if g.status == OPEN]
    return {
        "generated_by": "scripts/11_reproducibility_matrix.py",
        "measurement": "flags declaradas na matriz, ainda não medidas por teste/artefato (H)",
        "validated_months": VALIDATED_MONTHS,
        "components_in_matrix": len(MATRIX),
        "components_current_standard": len(current),
        "discontinued": [e.component_id for e in MATRIX if not e.current_standard],
        "merged": MERGED,
        "ready_for_generation": len(ready),
        "blocked_generation": [e.component_id for e in blocked],
        "blocked_validation": [e.component_id for e in current if e.validation_blockers],
        "historically_validated": len([e for e in current if e.historical_validated]),
        "require_human_input": sorted({i for e in current for i in e.inputs}),
        "by_automation_class": _counts(current, lambda e: e.automation_class.value),
        "by_confidence": _counts(current, lambda e: e.confidence.value),
        "generation_blockers": sorted({b for e in current for b in e.blockers}),
        "validation_blockers": sorted({b for e in current for b in e.validation_blockers}),
        "gaps_total": len(GAPS),
        "gaps_by_status": _counts(GAPS, lambda g: g.status.value),
        "open_gaps_by_priority": {
            p: [g.gap_id for g in open_gaps if g.priority == p] for p in ("P0", "P1", "P2", "P3")
        },
        "resolved_gaps": {g.gap_id: g.resolved_by for g in GAPS if g.status == RESOLVED},
        "open_gaps_block_builder": [g.gap_id for g in open_gaps if g.blocks_builder],
        "open_gaps_block_validation": [g.gap_id for g in open_gaps if g.blocks_validation],
        "open_gaps_with_default": {
            g.gap_id: g.default_if_open for g in open_gaps if g.default_if_open
        },
    }


def main() -> int:
    summary = summarize()

    matrix_path = assert_write_allowed(CATALOG / "reproducibility_matrix.jsonl")
    matrix_path.parent.mkdir(parents=True, exist_ok=True)
    with matrix_path.open("w", encoding="utf-8") as fh:
        for item in MATRIX:
            fh.write(item.model_dump_json(exclude_none=True) + "\n")

    gaps_path = assert_write_allowed(CATALOG / "gaps.jsonl")
    with gaps_path.open("w", encoding="utf-8") as fh:
        for gap in sorted(GAPS, key=lambda g: (g.priority, g.gap_id)):
            fh.write(gap.model_dump_json(exclude_none=True) + "\n")

    state_path = assert_write_allowed(STATE / "readiness.yaml")
    state_path.write_text(
        yaml.safe_dump(summary, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    print(
        f"matriz: {summary['components_in_matrix']} | padrão vigente: "
        f"{summary['components_current_standard']} | prontos p/ gerar: "
        f"{summary['ready_for_generation']} | bloqueiam geração: "
        f"{len(summary['blocked_generation'])} | bloqueiam validação: "
        f"{len(summary['blocked_validation'])}"
    )
    for name, count in summary["by_automation_class"].items():
        print(f"  {name}: {count}")
    print(f"\ngaps: {summary['gaps_total']} {summary['gaps_by_status']}")
    for gap in sorted(GAPS, key=lambda g: (g.priority, g.gap_id)):
        flag = "BLOQUEIA" if gap.blocks_builder else "        "
        print(f"  {gap.priority} {gap.status.value:8} {flag} {gap.gap_id} {gap.component}")
    for path in (matrix_path, gaps_path, state_path):
        print(f"  -> {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
