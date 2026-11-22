"""Texto do Produto 2.4: cada regra da spec do agente O (config/data_rules/p24_blocks.yaml)."""

import copy
import re
import warnings
from dataclasses import replace
from datetime import date

import pytest

from prog_g2_report.render import p24_text as pt
from prog_g2_report.sources import environmental as env
from prog_g2_report.sources import master_list as ml
from prog_g2_report.sources.master_list import MasterListRow
from golden_evidence import (
    ENV_SNAPSHOT,
    docx_paragraphs,
    facts_of,
    real_blocks,
    report_docx,
    require_golden,
    snapshot,
    soft,
    workbook_bytes_from_snapshot,
)

P24 = "2.4 GERENCIAMENTO TÉCNICO"
SEMANAL = "Relatório Semanal de Acompanhamento de Obras"


def r(n, doc, manifestation, highway, description=None, status="Entregue", period=None, product=P24):
    return MasterListRow(
        physical_row=n, product=product, company="Dynatest", document=doc,
        manifestation=manifestation, description=description, venture=highway,
        delivery_date=None, delivery_status=status, version=1, report_number=14, period=period,
    )


@pytest.fixture(scope="module")
def rules():
    return pt.load_rules()


def _swap_order(rules, name, order):
    spec = copy.deepcopy(dict(rules.spec))
    spec["common"]["highway_orders"][name] = order
    return replace(rules, spec=spec)


def _bold(paragraph):
    return [s.text for s in paragraph.segments if s.bold]


# =========================================================================== utilidades
def test_join_pt_has_no_oxford_comma():
    assert pt.join_pt(["A"]) == "A"
    assert pt.join_pt(["A", "B"]) == "A e B"
    assert pt.join_pt(["A", "B", "C"]) == "A, B e C"


def test_code_sort_key_is_numeric_seq_then_revision():
    codes = ["RI-512.1", "RI-509.2", "RI-509.1", "RI-510.1"]
    assert sorted(codes, key=pt.code_sort_key) == ["RI-509.1", "RI-509.2", "RI-510.1", "RI-512.1"]


def test_numerals_come_from_model_with_masculine_one_and_two(rules):
    assert pt.numeral(8, True, rules) == "oito"
    assert pt.numeral(1, True, rules) == "uma"
    assert pt.numeral(1, False, rules) == "um"
    assert pt.numeral(2, False, rules) == "dois"
    assert pt.numeral(4, False, rules) == "quatro"
    assert pt.numeral(21, True, rules) == "vinte e uma"
    assert pt.numeral(149, False, rules) == "cento e quarenta e nove"
    assert pt.numeral(200, True, rules) == "duzentas"


def test_markup_turns_double_asterisks_into_bold_segments():
    segs = pt.markup("a **b** c **d**")
    assert [(s.text, s.bold) for s in segs] == [("a ", False), ("b", True), (" c ", False), ("d", True)]


def test_parse_period_accepts_both_observed_formats():
    assert pt.parse_period("01/08/2026 A 07/08/2026") == (date(2026, 8, 1), date(2026, 8, 7))
    assert pt.parse_period("02/10/25 a 09/10/25") == (date(2025, 10, 2), date(2025, 10, 9))
    assert pt.parse_period("sem período") is None
    assert pt.parse_period(None) is None


# =========================================================================== RO (agente D)
def _weekly_rows():
    return [
        r(10, "RO-539.1", SEMANAL, "RD-104", period="01/08/2026 A 07/08/2026"),
        r(11, "RO-545.1", SEMANAL, "RD-103", period="01/08/2026 A 07/08/2026"),
        r(12, "RO-546.2", SEMANAL, "RD-103", period="08/08/2026 A 14/08/2026"),
        r(13, "RO-547.1", SEMANAL, "RD-103", period="22/08/2026 A 28/08/2026"),
        r(14, "RO-540.1", SEMANAL, "RD-104", period="08/08/2026 A 14/08/2026"),
        r(15, "RO-544.1", SEMANAL, "RD-101", period="01/08/2026 A 07/08/2026"),
    ]


def test_ro_period_is_min_start_max_end_and_cutoff_day_25(rules):
    block = pt.render_ro_period(_weekly_rows(), "2026-08", rules=rules)
    assert block.lines == [rules.content_block("P2.4_RO_PERIODO")["template"].replace("**", "").format(
        weekly_period_start="01/08/2026", weekly_period_end="28/08/2026", cutoff_date="25/08/2026")]
    assert _bold(block.paragraphs[0]) == ["01/08/2026 a 28/08/2026", "25/08/2026."]
    assert block.facts["cutoff"] == "2026-08-25"
    assert block.warnings == []


def test_ro_period_warns_week_started_on_25_inside_month(rules):
    rows = [*_weekly_rows(), r(20, "RO-548.1", SEMANAL, "RD-103", period="25/08/2026 A 31/08/2026")]
    block = pt.render_ro_period(rows, "2026-08", rules=rules)
    assert any(w.startswith("V_WEEK_START_25") for w in block.warnings)


def test_ro_list_uses_physical_first_and_last_with_real_revision(rules):
    block = pt.render_ro_list(_weekly_rows(), rules=rules)
    assert block.lines == ["RD-103: RO-545.1 a RO-547.1;", "RD-101: RO-544.1 a RO-544.1;",
                           "RD-104: RO-539.1 a RO-540.1;"]
    assert _bold(block.paragraphs[0]) == ["RD-103:"]
    assert {(p.numbering, p.level) for p in block.paragraphs} == {("numId_29", 0)}


def test_ro_list_order_is_read_from_model(rules):
    swapped = _swap_order(rules, "ORDER_RO", ["RD-104", "RD-101", "RD-103", "RD-102A"])
    block = pt.render_ro_list(_weekly_rows(), rules=swapped)
    assert [line.split(":")[0] for line in block.lines] == ["RD-104", "RD-101", "RD-103"]


def test_ro_blocks_are_skipped_in_a_month_without_weekly_reports(rules):
    """Revisor W4 MINOR 1: sem RO no relatório, RO_PERIODO e RO_LIST saem SKIPPED (presença
    'if existe RO no Produto 2.4'), não PENDING_HUMAN."""
    month_without_ro = [r(1, "RM-001.1", "Relatório Mensal", "RD-101")]
    for block in (pt.render_ro_list(month_without_ro, rules=rules),
                  pt.render_ro_period(month_without_ro, "2026-09", rules=rules)):
        assert block.status == "SKIPPED" and block.paragraphs == []
    for block_id in ("P2.4_RO_PERIODO", "P2.4_RO_LIST"):
        assert rules.content_block(block_id)["presence"] == "if existe RO no Produto 2.4"


def test_ro_with_illegible_period_still_needs_human(rules):
    rows = [r(1, "RO-501.1", SEMANAL, "RD-101", period="semana 1")]
    block = pt.render_ro_period(rows, "2026-09", rules=rules)
    assert block.status == "PENDING_HUMAN"
    assert pt.render_ro_list([r(1, "RO-501.1", SEMANAL, "Geral")], rules=rules).status \
        == "PENDING_HUMAN"


def _rm_rows():
    return [r(5, "RM-012.1", "Relatório Mensal", "RD-101"),
            r(6, "NC-501.1", "Notificação de não conformidade", "RD-101")]


def test_rm_and_nc_cite_weekly_reports_only_with_ro_in_the_report(rules):
    """Revisor W4 MINOR 1: 'relatórios semanais' em P2.4_RM e P2.4_NC só com RO no relatório
    (slots rm_weekly_clause / nc_weekly_clause, trigger_family RO)."""
    with_ro = [*_rm_rows(), r(7, "RO-540.1", SEMANAL, "RD-101", period="01/09/2026 A 07/09/2026")]
    rm, nc = pt.render_rm(with_ro, rules=rules), pt.render_nc(with_ro, rules=rules)
    assert ("os quais consolidam as informações registradas nos relatórios semanais, atualizam o "
            "acompanhamento técnico") in rm.lines[0]
    assert nc.lines[0].startswith(
        "As notificações de não conformidade podem ser consultadas nos relatórios semanais, os "
        "quais consolidam os apontamentos referentes a cada trecho, bem como nos relatórios "
        "mensais, que compilam e atualizam")
    assert rm.facts["cites_weekly_reports"] is nc.facts["cites_weekly_reports"] is True

    rm, nc = pt.render_rm(_rm_rows(), rules=rules), pt.render_nc(_rm_rows(), rules=rules)
    for block in (rm, nc):
        assert "semana" not in block.lines[0].lower() and "  " not in block.lines[0]
        assert block.facts["cites_weekly_reports"] is False
    assert "referente à RD-101, os quais atualizam o acompanhamento técnico" in rm.lines[0]
    assert nc.lines[0].startswith(
        "As notificações de não conformidade podem ser consultadas nos relatórios mensais, que "
        "compilam e atualizam, de forma acumulada, a situação das não conformidades desde o "
        "início das obras.")


# =========================================================================== RM
def test_rm_groups_by_code_with_physical_highway_order(rules):
    rows = [
        r(5, "RM-012.1", "Relatório Mensal", "RD-101"),
        r(6, "RM-012.1", "Relatório Mensal", "RD-103"),
        r(7, "RM-011.1", "Relatório Mensal", "RD-104"),
        r(8, "RM-012.1", "Relatório Mensal", "RD-102a"),
    ]
    block = pt.render_rm(rows, rules=rules)
    text = block.lines[0]
    assert "sendo o RM-011.1 referente à RD-104 e os RM-012.1 referentes às rodovias RD-101, RD-103 e RD-102A, os quais" in text
    assert _bold(block.paragraphs[0]) == ["Relatórios Mensais de Acompanhamento de Obras"]


def test_rm_absent_is_skipped(rules):
    assert pt.render_rm([r(1, "PA-501.1", "Parecer", "RD-101")], rules=rules).status == "SKIPPED"


# =========================================================================== NC
def test_nc_without_nc_or_rnc_is_only_the_fixed_sentence(rules):
    block = pt.render_nc([], rules=rules)
    slots = rules.block("P2.4_NC")["slots"]
    base = " ".join(slots["nc_base"].split()).format(
        nc_weekly_clause=slots["nc_weekly_clause"]["value_if_false"])
    assert block.lines == [" ".join(base.split())]
    assert block.facts["enumerated"] is False


def test_nc_enumerates_by_alpha_order_with_bold_codes(rules):
    rows = [
        r(1, "NC-525.1", "Notificação de não conformidade", "RD-104"),
        r(2, "NC-525.1", "Notificação de Não Conformidade", "RD-103"),   # 2ª grafia (normalizada)
    ]
    block = pt.render_nc(rows, rules=rules)
    assert block.lines[0].endswith(
        "No período de referência, foram emitidas as Notificações de Não Conformidade NC-525.1, "
        "referente à RD-103, e a NC-525.1, referente à RD-104.")
    assert _bold(block.paragraphs[0]) == ["NC-525.1", "NC-525.1"]
    assert block.status == "OK"


def test_nc_plural_group_and_nature_clause(rules):
    rows = [r(i, f"NC-{530 + i}.1", "Notificação de não conformidade", "RD-102A") for i in (8, 3, 4, 5)]
    block = pt.render_nc(rows, rules=rules, nature_clause=", relacionadas a ocorrências de obra")
    assert ("NC-533.1, NC-534.1, NC-535.1 e NC-538.1, referentes à RD-102A, relacionadas a "
            "ocorrências de obra.") in block.lines[0]


def test_nc_enumeration_policy_comes_from_editorial_defaults(rules):
    rows = [r(i, f"NC-{510 + i}.1", "Notificação de não conformidade", "RD-101") for i in range(6)]
    # Gate B (objeção 7): default único up_to_4 (editorial_defaults.nc_enumeration.enumerate_max)
    assert pt.render_nc(rows, rules=rules).facts["enumeration_policy"] == "up_to_4"
    assert pt.render_nc(rows, rules=rules).facts["enumerated"] is False
    assert pt.render_nc(rows[:4], rules=rules).facts["enumerated"] is True
    assert pt.render_nc(rows, rules=rules, enumeration="always_when_present").facts["enumerated"] is True
    assert pt.render_nc(rows, rules=rules, enumeration="never").facts["enumerated"] is False
    custom = replace(rules, editorial={"nc_enumeration": {"value": "up_to_4"}})
    assert pt.render_nc(rows, rules=custom).facts["enumerated"] is False
    with pytest.raises(ValueError):
        pt.render_nc(rows, rules=rules, enumeration="talvez")


def test_nc_more_than_two_highways_is_unobserved(rules):
    rows = [r(i, f"NC-{500 + i}.1", "Notificação de não conformidade", hw)
            for i, hw in enumerate(["RD-101", "RD-103", "RD-104"], start=1)]
    block = pt.render_nc(rows, rules=rules)
    assert block.status == "PENDING_HUMAN"
    assert "e a NC-502.1, referente à RD-103, e a NC-503.1, referente à RD-104." in block.lines[0]


def test_nc_rnc_sentence_counts_distinct_highways_masculine(rules):
    rows = [r(i, f"RNC-00{i}.1", "Relatório de Não Conformidade", hw)
            for i, hw in enumerate(["RD-101", "RD-104", "RD-102A", "RD-103"], start=1)]
    block = pt.render_nc(rows, rules=rules)
    assert block.lines[0].endswith(
        " Além do Relatório Consolidado de Gestão das Não Conformidades (RNC) referente aos quatro trechos.")
    assert block.facts["rnc_highways"] == ["RD-101", "RD-102A", "RD-103", "RD-104"]


def test_nc_rnc_single_highway_is_provisional(rules):
    block = pt.render_nc([r(1, "RNC-001.1", "Relatório de Não Conformidade", "RD-101")], rules=rules)
    assert block.status == "PENDING_HUMAN"
    assert block.lines[0].endswith("referente ao trecho RD-101.")


# =========================================================================== ATAS
def test_atas_presence_is_derived(rules):
    assert pt.render_atas([r(1, "AT-676.1", "Ata de Reunião", "RD-104")], rules=rules).lines[0].startswith(
        "Encaminham-se, ainda, as atas de reunião")
    assert pt.render_atas([r(1, "PA-1.1", "Parecer", "RD-104")], rules=rules).status == "SKIPPED"


# =========================================================================== BM
def _bm_rows():
    return [
        r(1, "BM-008.1", "Boletim de Medição", "RD-104", "Boletim de Medição de Maio/2026"),
        r(2, "BM-007.1", "Boletim de Medição", "RD-104", "Boletim de Medição de Abril/2026"),
        r(3, "BM-007.1", "Boletim de Medição", "RD-102A", "Boletim de Medição de Março/2026", status="Em elaboração"),
        r(4, "BM-006.1", "Boletim de Medição", "RD-101", "Boletim de Medição de Fevereiro /2026"),
        r(5, "BM-007.1", "Boletim de Medição", "RD-101", "Boletim de Medição de Março/2026", status=" entregue "),
    ]


def test_bm_list_only_delivered_alpha_order_and_terminators(rules):
    block = pt.render_bm_list(_bm_rows(), rules=rules)
    assert block.lines == [
        "RD-101:", "BM-006.1 - Referente a Fevereiro/2026;", "BM-007.1 - Referente a Março/2026.",
        "RD-104:", "BM-007.1 - Referente a Abril/2026;", "BM-008.1 - Referente a Maio/2026.",
    ]
    assert [(p.numbering, p.level) for p in block.paragraphs[:2]] == [("numId_47", 0), ("numId_47", 1)]
    assert {p.list_key for p in block.paragraphs} == {"P2.4_BM_LIST"}
    assert not any(_bold(p) for p in block.paragraphs)


def test_bm_lead_presence_follows_list(rules):
    assert pt.render_bm_lead(_bm_rows(), rules=rules).lines == [
        "Foram realizadas as medições dos seguintes meses de cada obra:"]
    only_draft = [row for row in _bm_rows() if row.delivery_status == "Em elaboração"]
    assert pt.render_bm_lead(only_draft, rules=rules).status == "SKIPPED"
    assert pt.render_bm_list(only_draft, rules=rules).status == "SKIPPED"


def test_bm_in_progress_is_derived_plus_manual_and_needs_human(rules):
    block = pt.render_bm_in_progress(_bm_rows(), rules=rules, extra=[("RD-104", "BM-009.1", "Junho/2026")])
    assert block.lines == [
        "Paralelamente, permanecem em elaboração os seguintes boletins de medição:", "RD-102A:", "BM-007.1 - Referente a Março/2026.",
        "RD-104:", "BM-009.1 - Referente a Junho/2026.",
    ]
    assert block.status == "PENDING_HUMAN"
    assert block.paragraphs[1].list_key == "P2.4_BM_EM_ELABORACAO"      # nova instância: recomeça em a)


def test_bm_in_progress_external_item_already_derived_is_not_repeated(rules):
    """inputs.p24_bm_in_progress só acrescenta itens externos: o mesmo (rodovia, código) que já
    sai derivado da Lista Mestra não duplica (golden nº 13: transcrição × snapshot v162)."""
    extra = [("RD-102a", "BM-007.1", "Março/2026"), ("RD-104", "BM-009.1", "Junho/2026")]
    block = pt.render_bm_in_progress(_bm_rows(), rules=rules, extra=extra)
    assert block.lines == [
        "Paralelamente, permanecem em elaboração os seguintes boletins de medição:", "RD-102A:", "BM-007.1 - Referente a Março/2026.",
        "RD-104:", "BM-009.1 - Referente a Junho/2026.",
    ]
    assert block.facts["n_extra"] == 1


def test_bm_in_progress_input_is_wired_into_p24_inputs(rules):
    """inputs.p24_bm_in_progress (modelo) -> P24Inputs.bm_in_progress_extra -> renderizador."""
    extra = pt.bm_in_progress_items([{"rodovia": "RD-104", "código": "BM-009.1", "mês": "Junho/2026"},
                                     ("RD-101", "BM-010.1", "Julho/2026")])
    assert extra == (("RD-104", "BM-009.1", "Junho/2026"), ("RD-101", "BM-010.1", "Julho/2026"))
    assert pt.bm_in_progress_items(None) == ()
    with pytest.raises(ValueError, match="p24_bm_in_progress"):
        pt.bm_in_progress_items([{"rodovia": "RD-104"}])
    block = pt.P24_RENDERERS["P2.4_BM_EM_ELABORACAO"](
        pt.P24Inputs(body_rows=_bm_rows(), rules=rules, bm_in_progress_extra=extra))
    assert "BM-010.1 - Referente a Julho/2026." in block.lines
    assert block.facts["n_extra"] == 2


def test_nc_enumeration_policy_has_no_code_fallback(rules):
    """Default único em editorial_defaults.nc_enumeration; sem ele, erro (nada de fallback)."""
    assert pt.nc_enumeration_policy(rules) == "up_to_4"
    bare = pt.P24Rules(spec=rules.spec, content_blocks=rules.content_blocks, editorial={})
    with pytest.raises(KeyError, match="nc_enumeration"):
        pt.render_nc([], rules=bare)


def test_bm_month_without_prefix_falls_back_with_warning(rules):
    rows = [r(1, "BM-001.1", "Boletim de Medição", "RD-101", "BM Setembro/2025")]
    block = pt.render_bm_list(rows, rules=rules)
    assert block.lines[1] == "BM-001.1 - Referente a Setembro/2025."
    assert block.warnings


# =========================================================================== pareceres
def test_pareceres_medicao_triggered_by_keywords(rules):
    rows = [r(1, "PA-708.1", "Parecer", "RD-101", "Eventos medidos aderentes ao eventograma aprovado ")]
    block = pt.render_pareceres_medicao(rows, rules=rules)
    assert block.status == "OK" and len(block.paragraphs) == 1
    assert block.facts["trigger_codes"] == ["PA-708.1"]
    # P2.4_PARECERES_MEDICAO_2_TEMAS_SEM_SUPORTE: só eventograma não sustenta nenhum controle
    # analisado (slots.themes obrigatório, when_unsupported: SKIPPED) -> o parágrafo não sai
    block = pt.render_pareceres_medicao_2(rows, rules=rules)
    assert block.status == "SKIPPED" and block.paragraphs == []
    assert block.facts["trigger_codes"] == ["PA-708.1"] and block.facts["themes"] == {}
    other = [r(1, "PA-1.1", "Parecer", "RD-101", "Parecer Técnico Traço de CBUQ")]
    for fn in (pt.render_pareceres_medicao, pt.render_pareceres_medicao_2):
        assert fn(other, rules=rules).status == "SKIPPED"


MEDICAO_2_N13 = ("Os documentos contemplam a análise dos ensaios laboratoriais, controles "
                 "tecnológicos, topográficos e geotécnicos relacionados à execução das obras, com "
                 "destaque para as atividades de obras de arte corrente e verificação dos "
                 "controles apresentados pela executora e supervisora.")


def test_pareceres_medicao_2_cites_only_supported_controls(rules):
    """QA2-C / P2.4_PARECERES_MEDICAO_2_TEMAS_SEM_SUPORTE: com PA de cada tema a frase é a
    observada nos nº 13–14; sem PA geotécnico nem de OAC (os PA reais do mês) nada disso sai."""
    controle = r(1, "PA-691.1", "Parecer", "RD-101", "Parecer Técnico - Análise e Consolidação "
                 "do Controle Tecnológico e Topográfico (Mar/26)")
    geo = r(2, "PA-900.1", "Parecer", "RD-101", "Parecer Técnico - Análise Geotécnica do aterro")
    oac = r(3, "PA-901.1", "Parecer", "RD-101", "Parecer Técnico - Obras de Arte Corrente")
    assert pt.render_pareceres_medicao_2([controle, geo, oac], rules=rules).lines == [MEDICAO_2_N13]
    block = pt.render_pareceres_medicao_2([controle], rules=rules)
    assert block.lines == [
        "Os documentos contemplam a análise dos ensaios laboratoriais, controles tecnológicos e "
        "topográficos relacionados à execução das obras, com destaque para a verificação dos "
        "controles apresentados pela executora e supervisora."]
    assert "geotécn" not in block.text and "obras de arte" not in block.text
    assert block.facts["themes"] == {
        "ensaios laboratoriais e controles tecnológicos": ["PA-691.1"],
        "controles topográficos": ["PA-691.1"]}
    only_geo = pt.render_pareceres_medicao_2(
        [r(1, "PA-637.1", "Parecer", "RD-101", "Ateste de Documentação do Processo de Medição"),
         geo], rules=rules)
    assert only_geo.lines[0].startswith("Os documentos contemplam a análise dos controles "
                                        "geotécnicos relacionados")


ATAS_N14 = ("Encaminham-se, ainda, as atas de reunião referentes ao acompanhamento realizado pela "
            "equipe técnica junto às empresas executoras, contemplando as tratativas de avanço "
            "físico, qualidade dos serviços, pendências documentais, controle tecnológico, "
            "licenciamento ambiental, segurança do trabalho, planejamento das frentes de serviço, "
            "medições, eventogramas e acompanhamento das ocorrências registradas em campo.")
ATAS_FRAME = ("Encaminham-se, ainda, as atas de reunião referentes ao acompanhamento realizado "
              "pela equipe técnica junto às empresas executoras.")


def test_atas_cite_only_themes_in_the_description_of_the_minutes(rules):
    """QA2-C / P2.4_ATAS_TEMAS_SEM_SUPORTE: com a Descrição real das AT (nº 12–14) sai só a
    moldura factual; temas só com AT que os cite."""
    generic = "Reunião de alinhamento da obra e acompanhamento dos serviços"
    rows = [r(1, "AT-676.1", "Ata de Reunião", "RD-104", generic),
            r(2, "AT-677.1", "Ata de Reunião", "RD-103", generic)]
    block = pt.render_atas(rows, rules=rules)
    assert block.status == "OK" and block.lines == [ATAS_FRAME]
    assert block.facts["themes"] == {} and block.facts["codes"] == ["AT-676.1", "AT-677.1"]
    two = [*rows, r(3, "AT-678.1", "Ata de Reunião", "RD-101", "Reunião de medição e eventograma")]
    assert pt.render_atas(two, rules=rules).lines == [
        ATAS_FRAME[:-1] + ", contemplando as tratativas de medições e eventogramas."]
    full = "avanço físico, qualidade, pendências documentais, controle tecnológico, licenças, " \
           "segurança do trabalho, frentes de serviço, medição, eventograma, ocorrências"
    every = [*rows, r(3, "AT-678.1", "Ata de Reunião", "RD-101", full)]
    assert pt.render_atas(every, rules=rules).lines == [ATAS_N14]
    assert pt.render_atas([], rules=rules).status == "SKIPPED"


MEDICAO_N13 = ("Em complementação às medições subsequentes e ao acompanhamento da documentação de "
               "suporte das obras, foram emitidos pareceres técnicos referentes à Análise e "
               "Consolidação do Controle Tecnológico e Topográfico, assim como o Ateste de "
               "Documentação do Processo de Medição e Eventos medidos aderentes ao Eventograma "
               "aprovado, dos boletins de medição processados.")


def test_pareceres_medicao_themes_follow_the_pa_of_the_month(rules):
    """QA-C / P2.4_PARECERES_MEDICAO_ATESTE_SEM_PA: cada tema só com PA que o sustente; com os
    três (nº 13) a frase é a observada; sem PA de ateste (nº 14) o Ateste não é citado."""
    controle = r(1, "PA-691.1", "Parecer", "RD-101", "Parecer Técnico - Análise e Consolidação do "
                 "Controle Tecnológico e Topográfico (Mar/26)")
    ateste = r(2, "PA-637.1", "Parecer", "RD-101", "Parecer Técnico - Ateste de Documentação do "
               "Processo de Medição")
    evento = r(3, "PA-708.1", "Parecer", "RD-101", "Eventos medidos aderentes ao eventograma aprovado")
    block = pt.render_pareceres_medicao([controle, ateste, evento], rules=rules)
    assert block.lines == [MEDICAO_N13]
    block = pt.render_pareceres_medicao([controle, evento], rules=rules)
    assert "Ateste" not in block.text
    assert block.lines == [MEDICAO_N13.replace(
        "assim como o Ateste de Documentação do Processo de Medição e Eventos",
        "assim como os Eventos")]
    only_ateste = pt.render_pareceres_medicao([ateste], rules=rules).text
    assert "referentes ao Ateste de Documentação do Processo de Medição, dos boletins" in only_ateste
    assert block.facts["themes"] == {
        "Análise e Consolidação do Controle Tecnológico e Topográfico": ["PA-691.1"],
        "Eventos medidos aderentes ao Eventograma aprovado": ["PA-708.1"]}


def test_pareceres_amb_cites_only_supported_themes(rules):
    """P2.4_PARECERES_AMB_TEMAS_SEM_SUPORTE: sem PA de condicionantes/ocorrência, nada disso."""
    rows = [r(1, "PA-686.1", "Parecer", "RD-104", "Parecer Técnico Avaliação de conformidade sst e ambiental"),
            r(2, "PA-706.1", "Parecer", "RD-103", "Parecer Técnico Avaliação de Conformidade Obra")]
    text = pt.render_pareceres_amb(rows, rules=rules).lines[0]
    assert text == ("Adicionalmente, no mês de referência, foram emitidos pareceres técnicos "
                    "relacionados à avaliação de conformidade ambiental, saúde e segurança do "
                    "trabalho, conformidade de obra e demais manifestações correlatas aos "
                    "empreendimentos acompanhados.")
    assert "condicionantes" not in text and "ocorrências" not in text


def test_pareceres_without_any_supported_theme_need_a_human(rules):
    rows = [r(1, "PA-1.1", "Parecer", "RD-101", "Relatório ambiental genérico")]
    block = pt.render_pareceres_amb(rows, rules=rules)
    assert block.status == "PENDING_HUMAN" and block.paragraphs == []


# --------------------------------------------------------------- afirmação temática no texto emitido
THEMED_BLOCKS = ["P2.4_ATAS", "P2.4_PARECERES_MEDICAO", "P2.4_PARECERES_MEDICAO_2",
                 "P2.4_PARECERES_AMB"]


def _unsupported_theme_claims(blocks, rows, rules):
    """(bloco, tema) citado no texto EMITIDO sem documento do 2.4 da família do mapa cuja
    Descrição o sustente (`slots.<nome>.themes[].any`). Independe de como o texto foi montado:
    pega também tema escrito literalmente na moldura (QA-C, QA2-C)."""
    bad = []
    for block_id in THEMED_BLOCKS:
        text = blocks[block_id].text.casefold()
        for _, slot in pt._theme_slots(rules.block(block_id)):
            family = str(slot.get("family", "PA")).upper()
            docs = [env.norm(x.description) for x in rows
                    if x.product_code == "2.4" and pt.code_family(x.document) == family]
            for theme in slot["themes"]:
                forms = {str(theme[f]).strip(" ,").casefold() for f in ("follow", "bare")}
                cited = any(f in text for f in forms)
                if cited and not any(re.search(p, d) for p in theme["any"] for d in docs):
                    bad.append((block_id, theme["label"]))
    return bad


def _month_rows():
    """Mês sintético com as Descrições reais de AT e PA (sem geotécnico, OAC nem tema de ata)."""
    generic = "Reunião de alinhamento da obra e acompanhamento dos serviços"
    return [r(1, "AT-676.1", "Ata de Reunião", "RD-104", generic),
            r(2, "PA-691.1", "Parecer", "RD-101", "Parecer Técnico - Análise e Consolidação do "
              "Controle Tecnológico e Topográfico (Mar/26)"),
            r(3, "PA-708.1", "Parecer", "RD-101", "Eventos medidos aderentes ao eventograma aprovado"),
            r(4, "PA-686.1", "Parecer", "RD-104", "Parecer Técnico Avaliação de conformidade sst e "
              "ambiental")]


def test_emitted_text_never_claims_a_theme_without_document(rules):
    rows = _month_rows()
    blocks = pt.render_all(pt.P24Inputs(rows, "2026-09", rules=rules))
    assert all(blocks[b].present for b in THEMED_BLOCKS)
    assert _unsupported_theme_claims(blocks, rows, rules) == []


@pytest.mark.parametrize(("block_id", "observed"), [
    ("P2.4_ATAS", ATAS_N14), ("P2.4_PARECERES_MEDICAO_2", MEDICAO_2_N13),
    ("P2.4_PARECERES_MEDICAO", MEDICAO_N13)])
def test_old_fixed_sentence_is_caught_as_unsupported_claim(rules, block_id, observed):
    """A frase fixa publicada (nº 12–14) de volta na moldura: o teste do texto emitido reprova
    (P2.4_ATAS_TEMAS_SEM_SUPORTE, P2.4_PARECERES_MEDICAO_2_TEMAS_SEM_SUPORTE,
    P2.4_PARECERES_MEDICAO_ATESTE_SEM_PA)."""
    spec = copy.deepcopy(dict(rules.spec))
    next(b for b in spec["blocks"] if b["block_id"] == block_id)["text"] = observed
    broken = replace(rules, spec=spec)
    rows = _month_rows()
    blocks = pt.render_all(pt.P24Inputs(rows, "2026-09", rules=broken))
    assert blocks[block_id].lines == [observed]
    assert any(b == block_id for b, _ in _unsupported_theme_claims(blocks, rows, broken))


def test_nc_nature_clause_key_is_read_from_the_model():
    """N10 (W3): a chave de inputs.ai_review vem de P2.4_NC_NATURE.review_key, não do código."""
    from prog_g2_report.model import load_model

    model = copy.deepcopy(load_model())
    comp = next(c for c in model["components"] if c["component_id"] == "P2.4_NC_NATURE")
    key = comp["review_key"]
    assert pt.nc_nature_clause({key: {"text": ", natureza X"}}, model) == ", natureza X"
    comp["review_key"] = "OUTRA_CHAVE"
    assert pt.nc_nature_clause({key: ", natureza X"}, model) == ""
    assert pt.nc_nature_clause({"OUTRA_CHAVE": ", natureza Y"}, model) == ", natureza Y"
    assert pt.nc_nature_clause(None, model) == ""


def test_editorial_phrases_come_from_p24_blocks(rules):
    """Frases editoriais (', e a ', 'da rodovia {highway}', 'ao trecho') vivem em p24_blocks.yaml."""
    spec = copy.deepcopy(dict(rules.spec))
    nc = next(b for b in spec["blocks"] if b["block_id"] == "P2.4_NC")
    nc["slots"]["nc_enum_sentence"]["group_forms"]["next_one_code"] = " + "
    ri = next(b for b in spec["blocks"] if b["block_id"] == "P2.4_RI")
    ri["single_highway"]["singular_part"] = "do trecho {highway}"
    changed = replace(rules, spec=spec)
    rows = [r(1, "NC-501.1", "Notificação de não conformidade", "RD-101"),
            r(2, "NC-502.1", "Notificação de não conformidade", "RD-103")]
    nc_text = pt.render_nc(rows, rules=changed, enumeration="always_when_present").lines[0]
    assert "NC-501.1, referente à RD-101 + NC-502.1, referente à RD-103" in nc_text
    ri_rows = [r(1, "RI-501.1", "Relatório de inspeção do alojamento", "RD-101")]
    assert "alojamentos do trecho RD-101" in pt.render_ri(ri_rows, rules=changed).text


def test_pareceres_amb_two_paragraphs_triggered_by_sst_or_ambiental(rules):
    rows = [r(1, "PA-717.1", "Parecer", "RD-103", "Parecer Técnico Avaliação de Conformidade SST")]
    block = pt.render_pareceres_amb(rows, rules=rules)
    assert len(block.paragraphs) == 2
    assert block.lines[1].startswith("Os pareceres emitidos tiveram como objetivo")
    assert pt.render_pareceres_amb([r(1, "AT-1.1", "Ata", "RD-103", "ambiental")], rules=rules).status == "SKIPPED"


# =========================================================================== RI
def test_ri_range_and_feminine_count(rules):
    rows = [r(i, f"RI-{500 + i}.1", "Relatório de inspeção do alojamento ", hw)
            for i, hw in zip((12, 9, 10, 11), ["RD-101", "RD-104", "RD-102A", "RD-103"], strict=True)]
    block = pt.render_ri(rows, rules=rules)
    assert block.lines == ["Foram realizadas inspeções nos alojamentos das quatro rodovias, conforme "
                           "apresentado nos Relatórios de inspeção do alojamento RI-509.1 a RI-512.1."]
    assert _bold(block.paragraphs[0]) == ["RI-509.1 a RI-512.1."]


def test_ri_gap_or_single_highway_needs_human(rules):
    gap = [r(1, "RI-509.1", "Relatório de inspeção do alojamento", "RD-101"),
           r(2, "RI-511.1", "Relatório de inspeção do alojamento", "RD-103")]
    assert pt.render_ri(gap, rules=rules).status == "PENDING_HUMAN"
    single = pt.render_ri(gap[:1], rules=rules)
    assert single.status == "PENDING_HUMAN"
    assert "nos alojamentos da rodovia RD-101," in single.lines[0]


# =========================================================================== licenças
CSG, CLX, DELTA, TETRA = "CSG", "CLX", "DELTA", "TETRA"
COMPANIES = [(None, "Empresa", None, "Rodovia"), (None, CLX, None, "RD-102a"), (None, DELTA, None, "RD-103"),
             (None, CSG, None, "RD-101"), (None, TETRA, None, "RD-104")]
LIC_HEADER = ("Nº Licença", "Empresa", "Fase da licença", "Status")
COND_HEADER = ("Item", "Data da entrega", "Status", "Observações", "Responsável", "Próxima entrega")
PEND = "Aguardando a liberação"
OUTORGA = "Outorga de uso de recurso hídrico"


def _env(pending, near=None, overdue=None, ref=date(2026, 9, 7)):
    lic = [LIC_HEADER, (1, CSG, "Licença Ambiental Única", "Vigente")]
    lic += [(None, company, phase, PEND) for company, phase in pending]
    cond = [COND_HEADER]
    for company in (CSG, CLX, DELTA, TETRA):
        cond.append((1, date(2027, 1, 1), "No prazo", None, company, None))
        for _ in range((near or {}).get(company, 0)):
            cond.append((2, date(2026, 9, 20), "No prazo", None, company, None))
        for _ in range((overdue or {}).get(company, 0)):
            cond.append((3, date(2026, 9, 1), "No prazo", None, company, None))
    return env.aggregate(env.parse_workbook_rows(lic, cond, COMPANIES), ref)


AUGUST_PENDING = [(CLX, "Licença Ambiental - Canteiro de obra"), (TETRA, OUTORGA), (TETRA, OUTORGA),
                  (DELTA, OUTORGA), (DELTA, OUTORGA), (DELTA, "Licença Ambiental - Usina"),
                  (DELTA, OUTORGA), (DELTA, OUTORGA)]


def test_lic_lead_counts_pending_feminine_and_left_aligned(rules):
    block = pt.render_lic_lead(_env(AUGUST_PENDING), rules=rules)
    assert block.lines == ["Conforme pode ser observado na imagem a seguir, encontram-se pendentes oito "
                           "licenças, a saber:"]
    assert block.paragraphs[0].align == "left"


@pytest.mark.parametrize("pending", [[], [(CLX, OUTORGA)]])
def test_lic_lead_zero_or_one_is_unobserved(rules, pending):
    assert pt.render_lic_lead(_env(pending), rules=rules).status == "PENDING_HUMAN"


def test_lic_list_order_by_count_then_gamb_and_phase_labels(rules):
    block = pt.render_lic_list(_env(AUGUST_PENDING), rules=rules)
    assert block.lines == [
        "RD-102A: uma licença referente à licença ambiental do canteiro de obras;",
        "RD-104: duas licenças referente à outorga de uso de recursos hídricos;",
        "RD-103: cinco licenças/autorização aguardando liberação, sendo quatro referentes à outorga de "
        "uso de recurso hídrico e uma referente à licença ambiental da usina.",
    ]
    assert _bold(block.paragraphs[0]) == ["RD-102A:"]


def test_lic_list_tie_is_broken_by_gamb_order_from_model(rules):
    pending = [(CSG, OUTORGA), (CLX, OUTORGA)]
    assert [x[:7] for x in pt.render_lic_list(_env(pending), rules=rules).lines] == ["RD-102A", "RD-101:"]
    swapped = _swap_order(rules, "ORDER_GAMB", ["RD-101", "RD-102A", "RD-103", "RD-104"])
    assert [x[:7] for x in pt.render_lic_list(_env(pending), rules=swapped).lines] == ["RD-101:", "RD-102A"]


def test_lic_list_standardize_fixes_agreement(rules):
    lines = pt.render_lic_list(_env([(TETRA, OUTORGA), (TETRA, OUTORGA)]), rules=rules, standardize=True).lines
    assert lines == ["RD-104: duas licenças referentes à outorga de uso de recursos hídricos."]


def test_lic_list_unknown_phase_needs_human(rules):
    block = pt.render_lic_list(_env([(CSG, "Licença Nova"), (CSG, "Licença Nova")]), rules=rules)
    assert block.status == "PENDING_HUMAN"


def test_environmental_blocks_without_source_need_human(rules):
    for fn in (pt.render_lic_lead, pt.render_lic_list, pt.render_lau_lead, pt.render_lau_list):
        assert fn(None, rules=rules).status == "PENDING_HUMAN"


# =========================================================================== condicionantes
def test_lau_lead_clause_by_totals(rules):
    zero = pt.render_lau_lead(_env([]), rules=rules).lines[0]
    assert "não há condicionantes pendentes ou próximas ao vencimento no período de referência. Dessa" in zero
    some = pt.render_lau_lead(_env([], near={CSG: 1}), rules=rules).lines[0]
    assert "não há condicionantes pendentes no período de referência. Dessa forma, tem-se:" in some
    assert pt.render_lau_lead(_env([], overdue={CSG: 1}), rules=rules).status == "PENDING_HUMAN"


def test_lau_list_zero_one_many_alpha_order_all_highways(rules):
    block = pt.render_lau_list(_env([], near={CSG: 34, CLX: 1}), rules=rules)
    assert block.lines == [
        "RD-101: Não apresenta condicionantes em atraso, contudo, encontram-se algumas condicionantes "
        "próximas ao vencimento a serem apresentadas pela empresa executora;",
        "RD-102A: Não apresenta condicionantes em atraso, e apenas uma condicionante próxima ao "
        "vencimento a ser apresentada pela empresa executora;",
        "RD-103: Não apresenta condicionantes em atraso;",
        "RD-104: Não apresenta condicionantes em atraso;",
    ]
    assert block.facts["near_due_by_highway"] == {"RD-101": 34, "RD-102A": 1, "RD-103": 0, "RD-104": 0}


def test_lau_list_overdue_highway_needs_human(rules):
    block = pt.render_lau_list(_env([], overdue={DELTA: 2}), rules=rules)
    assert block.status == "PENDING_HUMAN"
    assert len(block.lines) == 3


# =========================================================================== RCA, RA
RCA = "Análise do relatório de controle ambiental"
RA = "Relatório Ambiental Consolidado"


def test_rca_only_highways_with_rca_in_gamb_order_with_typed_letters(rules):
    rows = [r(1, "RCA-513.1", RCA, "RD-101"), r(2, "RCA-512.1", RCA, "RD-104")]
    block = pt.render_rca_list(rows, rules=rules)
    assert [line[:11] for line in block.lines] == ["a) RD-104: ", "b) RD-101: "]
    assert block.lines[1].endswith("conforme RCA-513.1, referente à Análise do Relatório de Controle "
                                   "Ambiental da rodovia RD-101;")
    assert _bold(block.paragraphs[1]) == ["RD-101:", "RCA-513.1"]
    assert pt.render_rca_head(rows, rules=rules).lines == ["Referente aos Relatórios de Controle Ambiental:"]
    assert pt.render_rca_head([], rules=rules).status == "SKIPPED"
    assert pt.render_rca_list([], rules=rules).status == "SKIPPED"


def test_ra_lead_and_items_in_ro_order_level_one(rules):
    rows = [r(1, "RA-505.1", RA, "RD-104"), r(2, "RA-503.1", RA, "RD-104"), r(3, "RA-501.1", RA, "RD-103")]
    block = pt.render_ra(rows, rules=rules)
    assert block.lines == ["Adicionalmente, foram emitidos os relatórios consolidados mensais de "
                           "acompanhamento ambiental:", "RD-103: RA-501.1;", "RD-104: RA-503.1 e RA-505.1;"]
    assert [(p.numbering, p.level) for p in block.paragraphs] == [(None, None), ("numId_29", 1), ("numId_29", 1)]
    assert pt.render_ra([], rules=rules).status == "SKIPPED"


# =========================================================================== filtros gerais
def test_rows_of_other_products_and_non_highways_are_ignored(rules):
    rows = [r(1, "RA-501.1", RA, "RD-103", product="2.2 PROJETOS"), r(2, "RA-502.1", RA, "Geral"),
            r(3, "RA-503.1", RA, "RD-101")]
    block = pt.render_ra(rows, rules=rules)
    assert block.lines[1:] == ["RD-101: RA-503.1;"]
    assert any("Geral" in w for w in block.warnings)


def test_registry_covers_every_spec_block_and_returns_its_id(rules):
    spec_ids = {b["block_id"] for b in rules.spec["blocks"]}
    assert spec_ids <= set(pt.P24_RENDERERS)
    assert {"P2.4_RO_PERIODO", "P2.4_RO_LIST", "P2.4_BM_EM_ELABORACAO"} <= set(pt.P24_RENDERERS)
    inputs = pt.P24Inputs(body_rows=_weekly_rows() + _bm_rows(), reference_month="2026-08",
                          environmental=_env(AUGUST_PENDING), rules=rules)
    for block_id, block in pt.render_all(inputs).items():
        assert block.block_id == block_id
        assert block.status in {"OK", "SKIPPED", "PENDING_HUMAN"}


def test_registry_ro_period_requires_reference_month(rules):
    with pytest.raises(ValueError, match="reference_month"):
        pt.P24_RENDERERS["P2.4_RO_PERIODO"](pt.P24Inputs(body_rows=[], rules=rules))


# =========================================================================== golden
# Unidade de comparação do agente O (24 linhas no nº 14, 36 no nº 13): linhas de RM, NC, BM_LIST,
# RI, RCA_LIST, itens do RA, LIC (lead + lista), LAU (lead + lista) + presença de ATAS, PA_MED, PA_AMB.
O_LINE_BLOCKS = ["P2.4_RM", "P2.4_NC", "P2.4_BM_LIST", "P2.4_RI", "P2.4_RCA_LIST", "P2.4_RA",
                 "P2.4_LIC_LEAD", "P2.4_LIC_LIST", "P2.4_LAU_LEAD", "P2.4_LAU_LIST"]
O_PRESENCE_BLOCKS = ["P2.4_ATAS", "P2.4_PARECERES_MEDICAO", "P2.4_PARECERES_AMB"]
COMPARED = [*O_LINE_BLOCKS, *O_PRESENCE_BLOCKS, "P2.4_RO_PERIODO", "P2.4_RO_LIST", "P2.4_BM_LEAD",
            "P2.4_PARECERES_MEDICAO_2", "P2.4_RCA_HEAD"]

# Linhas que divergem do original e por quê (nenhuma é regra errada). (bloco, índice) -> anomalia.
RO_14 = "RO nº 14: faixa e período copiados do nº 13 (WAVE1 §D COPY_FORWARD_ERROR; P2.4_FAIXA_RO_SEMANA_REPETIDA)"
RO_13 = "RO nº 13: semana 25/07–31/07 omitida do texto (WAVE1 §D INTERNAL_INCONSISTENCY)"
NC_TRUNC = "NC base truncada / 'Consolidade' (P2.4_RELATORIO_CONSOLIDADO_GRAFIA)"
RA_461 = "RA 'RD-104 RA-…' sem dois-pontos (P2.4_RA_RD104_SEM_DOIS_PONTOS)"
BM_DASH = "BM separador misto '–' (anomalia de pontuação, nº 13)"
BM_180 = "BM RD-103 códigos do nº 12 (P2.4_BM_CODIGOS_RD103, COPY_FORWARD_ERROR)"
# Temas dos pareceres por palavra-chave (DEC-007; QA-C do Gate D; pendência A do Gate B;
# config/data_rules/p24_blocks.yaml#P2.4_PARECERES_MEDICAO/slots.themes e #P2.4_PARECERES_AMB/
# slots.themes): o publicado repete a frase fixa e cita temas sem PA que os sustente. O gerado
# omite esses temas — diferença legítima, não regressão (builder FF, Gate B tentativa 4).
PAR_MED_ATESTE = ("tema do Ateste sem PA de ateste no mês omitido "
                  "(P2.4_PARECERES_MEDICAO_ATESTE_SEM_PA; DEC-007, keyword_map)")
PAR_AMB_TEMAS = ("'condicionantes'/'ocorrências ambientais' sem PA que os sustente omitidos "
                 "(P2.4_PARECERES_AMB_TEMAS_SEM_SUPORTE; DEC-007, keyword_map)")
# QA2-C (Gate D, 2ª rodada): mais dois textos fixos com temas sem documento do mês (mapas de
# config/data_rules/p24_blocks.yaml#P2.4_PARECERES_MEDICAO_2/slots e #P2.4_ATAS/slots/themes).
PAR_MED2_TEMAS = ("'geotécnicos' e 'obras de arte corrente' sem PA que os sustente omitidos "
                  "(P2.4_PARECERES_MEDICAO_2_TEMAS_SEM_SUPORTE; DEC-007, keyword_map)")
ATAS_TEMAS = ("dez temas sem AT que os cite omitidos; só a moldura factual "
              "(P2.4_ATAS_TEMAS_SEM_SUPORTE; DEC-007, keyword_map)")
RESIDUALS = {
    14: {
        ("P2.4_RO_PERIODO", 0): RO_14, ("P2.4_RO_LIST", 0): RO_14, ("P2.4_RO_LIST", 1): RO_14,
        ("P2.4_RO_LIST", 2): RO_14, ("P2.4_RO_LIST", 3): RO_14,
        ("P2.4_NC", 0): NC_TRUNC + " + enumeração editorial (editorial_defaults.nc_enumeration)",
        ("P2.4_RA", 4): RA_461,
        ("P2.4_PARECERES_MEDICAO", 0): PAR_MED_ATESTE,
        ("P2.4_PARECERES_MEDICAO_2", 0): PAR_MED2_TEMAS,
        ("P2.4_PARECERES_AMB", 0): PAR_AMB_TEMAS,
        ("P2.4_ATAS", 0): ATAS_TEMAS,
    },
    13: {
        ("P2.4_RO_LIST", 0): RO_13, ("P2.4_RO_LIST", 1): RO_13, ("P2.4_RO_LIST", 2): RO_13,
        ("P2.4_RO_LIST", 3): RO_13,
        ("P2.4_NC", 0): NC_TRUNC,
        **{("P2.4_BM_LIST", i): BM_DASH for i in (5, 6, 7, 8, 9, 15)},
        **{("P2.4_BM_LIST", i): BM_180 for i in (12, 13, 14)},
        ("P2.4_PARECERES_MEDICAO", 0): "'processados..' (P2.4_PONTO_DUPLO)",
        ("P2.4_PARECERES_MEDICAO_2", 0): PAR_MED2_TEMAS,
        ("P2.4_PARECERES_AMB", 0): PAR_AMB_TEMAS,
        ("P2.4_ATAS", 0): ATAS_TEMAS,
        ("P2.4_RCA_LIST", 0): "RCA-512.1 'da rodovia RD-102A' (P2.4_RCA_RODOVIA_DIVERGENTE)",
        ("P2.4_RA", 4): RA_461,
    },
}
# fatos (códigos, rodovias, datas, meses, numerais) que o original afirma errado: só nas linhas acima
FACT_RESIDUALS = {
    14: {k for k in RESIDUALS[14] if k[0] in {"P2.4_RO_PERIODO", "P2.4_RO_LIST", "P2.4_NC"}},
    13: {k for k in RESIDUALS[13] if k[0] in {"P2.4_RO_LIST"}}
    | {("P2.4_BM_LIST", i) for i in (12, 13, 14)} | {("P2.4_RCA_LIST", 0)},
}


def _golden_blocks(root, number, version):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rows = ml.select(ml.load(root / "historical_sources" / f"lista_mestre_{version}.xlsx"), number, "2.4")
    snap_version, reference = ENV_SNAPSHOT[number]
    agg = env.aggregate(env.load(workbook_bytes_from_snapshot(snapshot(root, snap_version))), reference)
    month = {13: "2026-07", 14: "2026-08"}[number]
    generated = pt.render_all(pt.P24Inputs(rows, month, agg))
    real = real_blocks(docx_paragraphs(report_docx(root, number)))
    return generated, real


def _compare(generated, real):
    exact, soft_ok, facts_bad, o_unit = set(), set(), set(), [0, 0, 0, 0]
    total = []
    for block_id in COMPARED:
        gen, rl = generated[block_id].lines, real[block_id]
        for i in range(max(len(gen), len(rl))):
            a = gen[i] if i < len(gen) else None
            b = rl[i] if i < len(rl) else None
            key = (block_id, i)
            total.append(key)
            if a == b:
                exact.add(key)
            if a is not None and b is not None and soft(a) == soft(b):
                soft_ok.add(key)
            if facts_of(a) != facts_of(b):
                facts_bad.add(key)
        if block_id in O_PRESENCE_BLOCKS:
            o_unit[2] += 1
            ok = generated[block_id].present == bool(rl)
            o_unit[0] += ok
            o_unit[1] += ok
            o_unit[3] += ok
        elif block_id in O_LINE_BLOCKS:
            start = 1 if block_id == "P2.4_RA" else 0    # O não conta o lead do RA
            keys = [k for k in total if k[0] == block_id and k[1] >= start]
            o_unit[2] += len(keys)
            o_unit[0] += sum(k in exact for k in keys)
            o_unit[1] += sum(k in soft_ok for k in keys)
            o_unit[3] += sum(k not in facts_bad for k in keys)
    return total, exact, soft_ok, facts_bad, o_unit


@pytest.mark.golden
@pytest.mark.parametrize(("number", "version", "o_exact", "o_soft", "o_total"),
                         [(14, "v335.0", 22, 22, 24), (13, "v134.0", 23, 30, 36), (13, "v335.0", 23, 30, 36)])
def test_golden_reproduction_against_published_text(request, number, version, o_exact, o_soft, o_total):
    root = require_golden(request)
    generated, real = _golden_blocks(root, number, version)
    total, exact, soft_ok, facts_bad, o_unit = _compare(generated, real)
    residual = {k for k in total if k not in exact}
    print(f"\nnº {number} @ {version}: {len(exact)}/{len(total)} linhas exatas, "
          f"{len(soft_ok)}/{len(total)} tolerantes, fatos {len(total) - len(facts_bad)}/{len(total)}; "
          f"unidade do agente O: exatas {o_unit[0]}/{o_unit[2]}, tolerantes {o_unit[1]}/{o_unit[2]}, "
          f"fatos {o_unit[3]}/{o_unit[2]}")
    for key in sorted(residual):
        print("  ", key, "->", RESIDUALS[number].get(key, "SEM EXPLICAÇÃO"))
    assert residual == set(RESIDUALS[number])            # todo desvio explicado por anomalia
    assert facts_bad <= FACT_RESIDUALS[number]           # fatos 100% fora das linhas anômalas
    assert o_unit[2] == o_total
    assert o_unit[0] >= o_exact and o_unit[1] >= o_soft  # igual ou melhor que o agente O


@pytest.mark.golden
@pytest.mark.parametrize(("number", "version"), [(14, "v335.0"), (13, "v134.0"), (13, "v335.0")])
def test_golden_no_theme_without_document_and_published_text_had_them(request, number, version):
    """Com a Lista Mestra real: o gerado não cita tema sem documento nos blocos com mapa de
    temas; o publicado citava (P2.4_ATAS_TEMAS_SEM_SUPORTE, P2.4_PARECERES_MEDICAO_2_TEMAS_SEM_
    SUPORTE, P2.4_PARECERES_AMB_TEMAS_SEM_SUPORTE e, no nº 14, P2.4_PARECERES_MEDICAO_ATESTE_SEM_PA)."""
    root = require_golden(request)
    rules = pt.default_rules()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rows = ml.select(ml.load(root / "historical_sources" / f"lista_mestre_{version}.xlsx"),
                         number, "2.4")
    generated, real = _golden_blocks(root, number, version)
    assert _unsupported_theme_claims(generated, rows, rules) == []
    published = {b: pt.BlockText(b, [pt._para(" ".join(real[b]))], {}) for b in THEMED_BLOCKS}
    bad = {b for b, _ in _unsupported_theme_claims(published, rows, rules)}
    expected = {"P2.4_ATAS", "P2.4_PARECERES_MEDICAO_2", "P2.4_PARECERES_AMB"}
    assert bad == (expected | {"P2.4_PARECERES_MEDICAO"} if number == 14 else expected)


@pytest.mark.golden
def test_golden_nc_facts_match_when_enumeration_threshold_is_observed_one(request):
    """No nº 14 a única divergência de fato do NC é a política editorial (13 NC não enumeradas):
    com o limiar observado ('up_to_4', LOW) os fatos do NC batem 100% com o publicado."""
    root = require_golden(request)
    real = real_blocks(docx_paragraphs(report_docx(root, 14)))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        body = ml.select(ml.load(root / "historical_sources" / "lista_mestre_v335.0.xlsx"), 14, "2.4")
    nc = pt.render_nc(body, enumeration="up_to_4")
    assert facts_of(nc.lines[0]) == facts_of(real["P2.4_NC"][0])
