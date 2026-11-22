"""Condições de presença do YAML traduzidas em predicados nomeados."""

import pytest

from prog_g2_report.builder.blocks import blocks_by_id, load_blocks
from prog_g2_report.builder.presence import (
    Condition,
    UntranslatableConditionError,
    document_prefix,
    evaluate,
    load_data_rule_presences,
    parse_condition,
    untranslated_conditions,
)
from g2_text_support import make_rc, row, usual_rows

EXPECTED = {
    "COVER": "always",
    "P2.2_HIGHWAY_BLOCK": "always",
    "P2.4_LAU_LIST": "always",
    "P2.1_SUMMARY_S2_PADRONIZACAO": "report_has_prefix(IT, CT, POP)",
    "P2.1_SUMMARY_S3_P22": "product_has_rows(2.2)",
    "P2.1_SUMMARY_S4_TEMAS": "product_has_prefix(2.2, PA)",
    "P2.1_SUMMARY_S5_P24": "product_has_rows(2.4)",
    "P2.1_SUMMARY_S6_MEDICOES": "report_has_prefix(BM)",
    "P2.1_TABLE_CALL": "product_has_rows(2.1)",
    "P2.2_CONTROLE_PRODUTOS": "product_has_rows(2.2)",
    "P2.3_NO_ACTIVITY": "product_has_no_rows(2.3)",
    "P2.5_NO_ACTIVITY": "product_has_no_rows(2.5)",
    "P2.6_NO_ACTIVITY": "product_has_no_rows(2.6)",
    "P2.4_RM": "report_has_prefix(RM)",
    "P2.4_ATAS": "product_has_prefix(2.4, AT)",
    "P2.4_TCE_BLOCK": "never",
    "P2.1_SUMMARY_S1_P21": "product_has_rows(2.1)",
    "P2.1_SUMMARY_S7_PARECERES_P24": "product_has_prefix(2.4, PA)",
    "P2.4_RO_INTRO": "product_has_prefix(2.4, RO)",
    "P2.4_BM_LIST": "report_has_prefix(BM)",
    "P2.4_RI": "report_has_prefix(RI)",
    "P2.4_RA": "report_has_prefix(RA)",
    # traduzidas pela forma mais específica de config/data_rules/p24_blocks.yaml
    "P2.4_PARECERES_MEDICAO": "product_description_matches(2.4, PA, controle tecnolog, eventograma, ateste)",
    "P2.4_PARECERES_MEDICAO_2": "product_description_matches(2.4, PA, controle tecnolog, eventograma, ateste)",
    "P2.4_PARECERES_AMB": "product_description_matches(2.4, PA, ambiental, sst)",
    # revisor W4 MINOR 1: blocos do RO só com RO no relatório
    "P2.4_RO_PERIODO": "product_has_prefix(2.4, RO)",
    "P2.4_RO_LIST": "product_has_prefix(2.4, RO)",
    # QA2-E (Gate D): o lead da lista de RO também (antes 'always', coincidência histórica)
    "P2.4_RO_LEAD": "product_has_prefix(2.4, RO)",
    # revisor W4 MINOR 2: as 5 presenças antes não traduzidas ('presentes por padrão')
    "P2.2_DESAPROPRIACAO": "input_present(p22_external_status)",
    "P2.2_INTERFERENCIAS": "input_present(p22_external_status)",
    "P2.4_BM_EM_ELABORACAO": "any(product_prefix_status_not(2.4, BM, entregue), "
                             "input_present(p24_bm_in_progress))",
    "P2.4_LIC_LIST": "environmental_license_status(Aguardando a liberação)",
    "P2.4_RCA_LIST": "product_has_prefix(2.4, RCA)",
}

# nenhuma condição do YAML fica sem predicado (o validador do modelo reprova a que ficar)
UNTRANSLATED: set[str] = set()


@pytest.fixture(scope="module")
def blocks():
    return blocks_by_id(load_blocks())


@pytest.fixture(scope="module")
def fallbacks():
    return load_data_rule_presences()


@pytest.mark.parametrize(("block_id", "expected"), EXPECTED.items())
def test_yaml_conditions_translate_to_named_predicates(blocks, fallbacks, block_id, expected):
    block = blocks[block_id]
    assert str(parse_condition(block.presence, block_id, block.product, fallbacks)) == expected


def test_only_the_known_conditions_remain_untranslated(fallbacks):
    remaining = {block_id for block_id, _ in untranslated_conditions(load_blocks(), fallbacks)}
    assert remaining == UNTRANSLATED


def test_untranslatable_condition_fails_loudly():
    with pytest.raises(UntranslatableConditionError):
        parse_condition("desde Agosto/2026; 1 mês de evidência", "P2.2_INTERFERENCIAS")


def test_model_short_names_are_accepted():
    assert str(parse_condition("product_has_rows", product="2.3")) == "product_has_rows(2.3)"
    assert str(parse_condition("p22_external_status_present")) == (
        "input_present(p22_external_status)")
    with pytest.raises(UntranslatableConditionError):
        parse_condition("product_has_no_rows")   # sem produto


def test_product_rows_respect_report_number(tmp_path):
    rows = [*usual_rows(14), row("2.3", "OF-001.1", number=15)]
    rc = make_rc(rows=rows, tmp=tmp_path)
    assert evaluate(Condition("product_has_rows", ("2.1",)), rc)
    assert evaluate(Condition("product_has_no_rows", ("2.3",)), rc)   # linha é do nº 15
    assert not evaluate(Condition("product_has_no_rows", ("2.4",)), rc)


def test_prefix_predicates(tmp_path):
    rows = [row("2.1", "POP-007.1"), row("2.4", "AT-510.1"), row("2.2", "PA-501.1")]
    rc = make_rc(rows=rows, tmp=tmp_path)
    assert document_prefix("POP-007.1") == "POP"
    assert evaluate(Condition("report_has_prefix", ("IT", "CT", "POP")), rc)
    assert not evaluate(Condition("report_has_prefix", ("BM",)), rc)
    assert evaluate(Condition("product_has_prefix", ("2.4", "AT")), rc)
    assert not evaluate(Condition("product_has_prefix", ("2.1", "AT")), rc)


def test_description_keywords_ignore_accents_and_case(tmp_path, blocks, fallbacks):
    block = blocks["P2.4_PARECERES_MEDICAO_2"]
    cond = parse_condition(block.presence, block.block_id, block.product, fallbacks)
    hit = make_rc(rows=[row("2.4", "PA-691.1", description="Análise do CONTROLE TECNOLÓGICO")],
                  tmp=tmp_path)
    miss = make_rc(rows=[row("2.4", "PA-691.1", description="Conformidade de SST"),
                         row("2.2", "PA-692.1", description="controle tecnológico")],
                   tmp=tmp_path)
    assert evaluate(cond, hit)
    assert not evaluate(cond, miss)   # a do 2.2 não conta


def test_input_present(tmp_path):
    rc = make_rc(inputs={"p22_external_status": {"RD-103": {}}}, tmp=tmp_path)
    assert evaluate(Condition("input_present", ("p22_external_status",)), rc)
    rc.data["inputs"] = {}
    assert not evaluate(Condition("input_present", ("p22_external_status",)), rc)


# ------------------------------------------------- QA-E: defeitos que agosto esconde (nº 15 sintético)
def test_month_without_ro_drops_ro_intro_and_without_p21_drops_s1(tmp_path, blocks, fallbacks):
    """Mês sintético sem RO e sem linhas do 2.1: P2.4_RO_INTRO e o S1 não são emitidos."""
    rows = [row("2.4", "NC-501.1", number=15), row("2.4", "BM-002.1", number=15),
            row("2.2", "PA-503.1", number=15)]
    rc = make_rc(number=15, ref="2026-09", rows=rows, tmp=tmp_path)
    for block_id in ("P2.4_RO_INTRO", "P2.1_SUMMARY_S1_P21"):
        block = blocks[block_id]
        cond = parse_condition(block.presence, block_id, block.product, fallbacks)
        assert not evaluate(cond, rc), block_id
    rows += [row("2.4", "RO-504.1", number=15), row("2.1", "AT-505.1", number=15)]
    rc = make_rc(number=15, ref="2026-09", rows=rows, tmp=tmp_path)
    for block_id in ("P2.4_RO_INTRO", "P2.1_SUMMARY_S1_P21"):
        block = blocks[block_id]
        assert evaluate(parse_condition(block.presence, block_id, block.product, fallbacks), rc)


# ------------------------------------------------- revisor W4: presenças antes 'presentes por padrão'
def _cond(blocks, fallbacks, block_id):
    block = blocks[block_id]
    return parse_condition(block.presence, block_id, block.product, fallbacks)


def test_month_without_ro_drops_ro_period_and_ro_list(tmp_path, blocks, fallbacks):
    """Mês sintético sem RO: nenhum bloco do RO sai — inclusive o P2.4_RO_LEAD ('… contempla
    os seguintes relatórios semanais de cada obra:'), que antes saía sem lista (QA2-E)."""
    ro_blocks = ("P2.4_RO_INTRO", "P2.4_RO_PERIODO", "P2.4_RO_LEAD", "P2.4_RO_LIST")
    rows = [row("2.4", "NC-501.1", number=15), row("2.4", "RM-002.1", number=15)]
    rc = make_rc(number=15, ref="2026-09", rows=rows, tmp=tmp_path)
    for block_id in ro_blocks:
        assert not evaluate(_cond(blocks, fallbacks, block_id), rc), block_id
    rc = make_rc(number=15, ref="2026-09", rows=[*rows, row("2.4", "RO-503.1", number=15)],
                 tmp=tmp_path)
    for block_id in ro_blocks:
        assert evaluate(_cond(blocks, fallbacks, block_id), rc), block_id


def test_bm_in_progress_is_derived_or_human_input(tmp_path, blocks, fallbacks):
    cond = _cond(blocks, fallbacks, "P2.4_BM_EM_ELABORACAO")
    delivered = [row("2.4", "BM-001.1", status="Entregue")]
    assert not evaluate(cond, make_rc(rows=delivered, inputs={}, tmp=tmp_path))
    in_progress = [*delivered, row("2.4", "BM-002.1", status="Em Elaboração")]
    assert evaluate(cond, make_rc(rows=in_progress, inputs={}, tmp=tmp_path))
    external = {"p24_bm_in_progress": [{"rodovia": "RD-010", "código": "BM-009.1",
                                        "mês": "Julho/2026"}]}
    assert evaluate(cond, make_rc(rows=delivered, inputs=external, tmp=tmp_path))


def test_rca_list_and_external_status_presence(tmp_path, blocks, fallbacks):
    rca = _cond(blocks, fallbacks, "P2.4_RCA_LIST")
    assert evaluate(rca, make_rc(rows=[row("2.4", "RCA-513.1")], tmp=tmp_path))
    assert not evaluate(rca, make_rc(rows=[row("2.4", "RA-513.1")], tmp=tmp_path))
    for block_id in ("P2.2_DESAPROPRIACAO", "P2.2_INTERFERENCIAS"):
        cond = _cond(blocks, fallbacks, block_id)
        assert not evaluate(cond, make_rc(inputs={}, tmp=tmp_path))
        assert evaluate(cond, make_rc(inputs={"p22_external_status": {"RD-010": {}}},
                                      tmp=tmp_path))


class _Lic:
    def __init__(self, statuses):
        self.statuses = statuses

    def pending_licenses(self, status):
        return tuple(s for s in self.statuses if s == status)


def test_license_list_presence_reads_the_environmental_aggregates(tmp_path, blocks, fallbacks):
    from prog_g2_report.render import p24_text

    cond = _cond(blocks, fallbacks, "P2.4_LIC_LIST")
    # o status do predicado é o mesmo da consulta do P2.4_LIC_LEAD (p24_blocks.yaml)
    lead_query = p24_text.load_rules().block("P2.4_LIC_LEAD")["query"]
    assert f"'{cond.args[0]}'" in lead_query
    rc = make_rc(tmp=tmp_path)
    rc.data["environmental"] = _Lic(["Vigente", cond.args[0]])
    assert evaluate(cond, rc)
    rc.data["environmental"] = _Lic(["Vigente"])
    assert not evaluate(cond, rc)
    rc.data["environmental"] = None
    with pytest.raises(KeyError):                 # sem planilha: erro explícito, não presença
        evaluate(cond, rc)


def test_or_only_splits_when_no_whole_rule_matches():
    """'contém 'a' OR 'b'' é uma regra só (data_rules); 'c1 OR c2' com parte sem tradução não
    vira presença parcial."""
    whole = parse_condition("existe PA no 2.4 cuja Descrição normalizada contém 'x' OR 'y'")
    assert whole.name == "product_description_matches"
    with pytest.raises(UntranslatableConditionError):
        parse_condition("if existe RO no Produto 2.4 OR quando fizer sentido")


def test_discontinued_tce_block_does_not_depend_on_the_report_number(blocks):
    presence = blocks["P2.4_TCE_BLOCK"].presence
    assert presence == "never" and not any(ch.isdigit() for ch in presence)


def test_missing_master_list_is_an_explicit_error(tmp_path):
    rc = make_rc(tmp=tmp_path)
    del rc.data["master_list_rows"]
    with pytest.raises(KeyError):
        evaluate(Condition("product_has_rows", ("2.1",)), rc)
    assert evaluate(Condition("always"), rc)
