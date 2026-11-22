"""Gate B em código: o modelo vigente passa e cada invariante reprova a regressão que deve pegar."""

import copy
import shutil

import pytest
import yaml

from prog_g2_report import REPO_ROOT
from prog_g2_report.builder.values import input_value
from prog_g2_report.model import (
    _jsonl,
    anomaly_needles,
    emitted_texts,
    load_content_blocks,
    load_model,
    model_pendencies,
    resolve_key,
    validate_model,
)


@pytest.fixture(scope="module")
def model():
    return load_model()


@pytest.fixture(scope="module")
def content():
    return load_content_blocks()


def _component(model, cid):
    return next(c for c in model["components"] if c["component_id"] == cid)


def _block(content, block_id):
    return next(b for b in content["blocks"] if b["block_id"] == block_id)


def _fails(model, expected, **kw):
    errors = validate_model(model, **kw)
    assert any(expected in e for e in errors), errors


def test_current_model_passes_gate_b(model):
    assert validate_model(model) == []


def test_pending_files_are_reported_apart_not_as_violations(model):
    broken = copy.deepcopy(model)
    broken["pending_files"] = [{"path": "config/arquivo_futuro.yaml"}]
    _component(broken, "HEADER")["render"] = "config/arquivo_futuro.yaml#header"
    assert validate_model(broken) == []
    assert any("arquivo_futuro" in p and "pendente" in p for p in model_pendencies(broken))
    broken["pending_files"] = []
    _fails(broken, "arquivo citado não existe: config/arquivo_futuro.yaml")


def test_every_matrix_component_is_covered(model):
    matrix = [{"component_id": "NOVO_COMPONENTE_SEM_MODELO"}]
    _fails(model, "fora do modelo", matrix=matrix)


@pytest.mark.parametrize(
    ("cid", "field", "value", "expected"),
    [
        ("PRESENTATION_LOGO", "asset", "asset_inexistente", "STATIC_ASSET sem asset"),
        ("CONTROL_OF_PRODUCTS", "source", None, "STRUCTURED_DATA sem source"),
        ("P2.4_LICENSE_DASHBOARDS", "render", None, "RECONSTRUCTED_VISUAL"),
        ("EXECUTIVE_SUMMARY_PARECER_THEMES", "human_review", False, "AI_SYNTHESIS"),
        ("SIGNATURE_DATE", "input", "entrada_nao_declarada", "MANUAL_INPUT"),
        ("TOC", "provenance", [], "sem provenance"),
        ("TOC", "confidence", "UNKNOWN", "confidence inválida"),
        ("P2.4_DOCUMENT_CITATIONS", "source", "fonte_inventada", "não declarada em sources"),
    ],
)
def test_invariants_reject_regressions(model, cid, field, value, expected):
    broken = copy.deepcopy(model)
    _component(broken, cid)[field] = value
    _fails(broken, expected)


def test_anomaly_cannot_be_provenance(model):
    broken = copy.deepcopy(model)
    _component(broken, "PRESENTATION_PARAGRAPH")["provenance"] = ["anomaly:APRESENTACAO_NUMERO_RELATORIO"]
    _fails(broken, "anomalia histórica")


def test_orientation_must_be_portrait_landscape_portrait(model):
    broken = copy.deepcopy(model)
    broken["page"]["sections"][1]["orientation"] = "portrait"
    _fails(broken, "orientação")


def test_all_six_products_present(model):
    broken = copy.deepcopy(model)
    broken["products"] = [p for p in broken["products"] if p["code"] != "2.5"]
    _fails(broken, "2.5")


def test_reference_is_august(model):
    broken = copy.deepcopy(model)
    broken["model"]["reference"] = "Relatório G2 nº 13 — Julho/2026"
    _fails(broken, "model.reference")


# ----------------------------------------------------------------- as 7 mutações do revisor W
def test_w04_render_key_that_does_not_exist(model):
    broken = copy.deepcopy(model)
    _component(broken, "P2.4_LICENSE_DASHBOARDS")["render"] = "config/g2_render_rules.yaml: chave_que_nao_existe"
    _fails(broken, "fora do formato arquivo#chave")


def test_w04_asset_only_in_the_model_dict(model):
    broken = copy.deepcopy(model)
    broken["assets"]["asset_fantasma"] = {}
    _component(broken, "PRESENTATION_LOGO")["asset"] = "asset_fantasma"
    _fails(broken, "'asset_fantasma' não existe em config/assets_manifest.yaml")


def test_w04_block_id_missing_from_content_blocks(model):
    broken = copy.deepcopy(model)
    _component(broken, "TOC")["blocks"] = ["BLOCO_INEXISTENTE"]
    _fails(broken, "bloco inexistente em g2_content_blocks: BLOCO_INEXISTENTE")


def test_w04_anomaly_cited_without_prefix(model):
    broken = copy.deepcopy(model)
    _component(broken, "P2.4_NONCONFORMITY_PARAGRAPH")["provenance"] = [
        "anomalies.jsonl P2.4_RELATORIO_CONSOLIDADO_GRAFIA"]
    _fails(broken, "anomalia histórica citada como regra: ['P2.4_RELATORIO_CONSOLIDADO_GRAFIA']")


def test_w04_template_without_fields_blocks_or_source(model):
    broken = copy.deepcopy(model)
    broken["components"].append({"component_id": "X_MANUAL", "automation_class": "TEMPLATE",
                                 "confidence": "HIGH_CONFIDENCE", "provenance": ["x"],
                                 "note": "valor digitado todo mês"})
    _fails(broken, "X_MANUAL: TEMPLATE sem fields, blocks ou source")


def test_w04_confirmed_needs_two_months_of_evidence(model):
    broken = copy.deepcopy(model)
    _component(broken, "P2.2_EXTERNAL_STATUS")["confidence"] = "CONFIRMED"
    _fails(broken, "P2.2_EXTERNAL_STATUS: CONFIRMED exige evidence_months")
    broken = copy.deepcopy(model)
    _component(broken, "CONTROL_OF_PRODUCTS")["evidence_months"] = ["2026-08"]
    _fails(broken, "CONTROL_OF_PRODUCTS: CONFIRMED exige evidence_months")


@pytest.mark.parametrize("text", ["baseado no RM14", "baseado no RM 14", "baseado no RM-14 / Relatório Mensal 14",
                                  "baseado no RM nº 14", "RM n° 14", "arquivo RM_14", "RM n.º 14"])
def test_w04_rm_acronym_is_rejected_in_every_spelling(model, text):
    broken = copy.deepcopy(model)
    broken["model"]["note"] = text
    _fails(broken, "sigla RM")


def test_document_codes_are_not_the_rm_acronym(model):
    broken = copy.deepcopy(model)
    broken["model"]["note"] = "RM-011.1 e RM-012.1 são códigos de documento (P2.4_RM)"
    assert validate_model(broken) == []


# ----------------------------------------------------------------- blocos × componentes
def test_every_block_belongs_to_exactly_one_component(model):
    broken = copy.deepcopy(model)
    _component(broken, "FIXED_BODY_TEXT")["blocks"].remove("CH2_INTRO")
    _fails(broken, "bloco sem componente (nem FIXED_BODY_TEXT nem discontinued): CH2_INTRO")
    broken = copy.deepcopy(model)
    _component(broken, "TOC")["blocks"].append("CH2_INTRO")
    _fails(broken, "bloco CH2_INTRO em mais de um componente")


def test_discontinued_block_is_owned_by_discontinued(model):
    broken = copy.deepcopy(model)
    tce = next(d for d in broken["discontinued"] if d["component_id"] == "P2.4_TCE_BLOCK")
    tce["blocks"] = []
    _fails(broken, "bloco sem componente (nem FIXED_BODY_TEXT nem discontinued): P2.4_TCE_BLOCK")


# ----------------------------------------------------------------- assets × manifesto
def test_asset_sha1_must_match_the_manifest(model):
    broken = copy.deepcopy(model)
    broken["assets"]["presentation_coordination_strip"]["sha1"] = "0" * 40
    _fails(broken, "sha1 do modelo difere do manifesto")


def test_manifest_entry_without_sha1_is_rejected(model):
    manifest = [{"asset_id": k, "sha1": "a" * 40} for k in model["assets"] if k != "manifest"]
    manifest[0]["sha1"] = None
    _fails(model, "sem sha1 válido no manifesto", assets={"assets": manifest})


# ----------------------------------------------------------------- referências arquivo#chave
def test_reference_to_missing_file_or_key_is_rejected(model):
    broken = copy.deepcopy(model)
    _component(broken, "P2.2_ROAD_DASHBOARDS")["render"] = "config/g2_render_rules.yaml#p22_road_dashboard"
    _fails(broken, "chave inexistente config/g2_render_rules.yaml#p22_road_dashboard")
    broken = copy.deepcopy(model)
    _component(broken, "EXECUTIVE_SUMMARY")["render"] = "config/data_rules/p21_inexistente.yaml#paragraphs"
    _fails(broken, "arquivo citado não existe: config/data_rules/p21_inexistente.yaml")


def test_render_reference_without_key_is_rejected(model):
    broken = copy.deepcopy(model)
    _component(broken, "P2.2_DISCIPLINE_STATUS")["render"] = "config/data_rules/p22_highway_block.yaml"
    _fails(broken, "sem #chave")


def test_reference_inside_content_blocks_is_checked(model, content):
    broken = copy.deepcopy(content)
    _block(broken, "P2.4_NC")["slots"]["nc_period_sentence"]["rule"] = (
        "config/data_rules/p24_blocks.yaml#P2.4_NC/slots/nao_existe")
    _fails(model, "chave inexistente config/data_rules/p24_blocks.yaml#P2.4_NC/slots/nao_existe",
           content_blocks=broken)


def test_resolve_key_walks_mappings_and_lists_by_id(content):
    assert resolve_key(content, "P2.4_NC/slots")["nc_period_sentence"]
    assert resolve_key({"a": [{"id": "x", "v": 1}]}, "a/x/v") == 1
    assert resolve_key({"blocks": [{"block_id": "B", "k": 2}]}, "B/k") == 2


# ----------------------------------------------------------------- rodovias
def test_highway_orders_must_be_permutations_of_the_contract(model):
    broken = copy.deepcopy(model)
    broken["contract"]["highways"] = broken["contract"]["highways"][:3]
    _fails(broken, "não é permutação de contract.highways")
    broken = copy.deepcopy(model)
    broken["contract"]["highway_orders"]["ORDER_RO"]["ref"] = "config/data_rules/p24_blocks.yaml#common/highway_orders/ORDER_X"
    _fails(broken, "contract.highway_orders.ORDER_RO: chave inexistente")


def test_contract_highways_is_declared_once(model):
    broken = copy.deepcopy(model)
    broken.pop("contract")
    _fails(broken, "contract.highways ausente")


# ----------------------------------------------------------------- texto emitido × anomalias
@pytest.mark.parametrize(
    ("block_id", "anomaly"),
    [
        ("P2.1_SUMMARY_S5_P24", "P2.1_RESUMO_OFICIO_SEM_DOCUMENTO"),
        ("P2.4_NC", "P2.4_RELATORIO_CONSOLIDADO_GRAFIA"),
    ],
)
def test_observed_anomalous_text_cannot_be_emitted(model, content, block_id, anomaly):
    broken = copy.deepcopy(content)
    block = _block(broken, block_id)
    observed = block["observed"]
    old = observed.get("text_no12_no14") or observed["full_text"]["Agosto/2026"]
    block["template"] = old
    _fails(model, f"anomalia {anomaly}", content_blocks=broken)


def test_observed_value_in_fixed_text_is_rejected(model, content):
    broken = copy.deepcopy(content)
    _block(broken, "APRES_P4_OBJETO")["text"] += " Relatório Mensal N° 13"
    _fails(model, "APRES_P4_OBJETO: texto emitido contém valor observado da anomalia "
                  "APRESENTACAO_NUMERO_RELATORIO", content_blocks=broken)


def test_observed_history_is_not_emitted_text(model, content):
    # o mesmo valor guardado em `observed` (evidência) não é violação
    assert "Consolidade" in str(_block(content, "P2.4_NC")["observed"])
    assert validate_model(model, content_blocks=content) == []


def test_short_observed_values_are_ignored():
    needles = anomaly_needles([{"component": "X", "classification": "TYPO",
                                "observed_value": "fim de período '25/05'"}])
    assert all(len(n) >= 6 for _, n in needles) and "25/05" not in [n for _, n in needles]
    assert not anomaly_needles([{"component": "Y", "classification": "TRUE_MODEL_CHANGE",
                                 "observed_value": "Parecer"}])


# ----------------------------------------------------------------- dados das correções do Gate B
def test_gate_b_content_corrections(content):
    s3, s5 = _block(content, "P2.1_SUMMARY_S3_P22"), _block(content, "P2.1_SUMMARY_S5_P24")
    assert "{p22_types}" in s3["template"] and "{p22_rodovias}" in s3["template"]
    assert "{p24_types}" in s5["template"] and "{p24_rodovias}" in s5["template"]
    for block in (s3, s5):
        assert "Ofício" not in block["template"] and "RD-" not in block["template"]
    assert "desde o início das obras.{nc_period_sentence}" in _block(content, "P2.4_NC")["template"]
    assert _block(content, "P2.2_ROTINA_REUNIOES")["class"] == "TEMPLATE"
    assert "({page_count_words})** páginas" in _block(content, "ENC_P1")["template"]
    assert content["placeholders"]["annex_count"]["source"].startswith("len(index_rows) (DEC-012)")


def test_nc_enumeration_has_a_single_default(model):
    nc = model["editorial_defaults"]["nc_enumeration"]
    assert nc["value"] == "up_to_4" and nc["enumerate_max"] == 4
    rules = yaml.safe_load((REPO_ROOT / "config/data_rules/p24_blocks.yaml").read_text("utf-8"))
    p24 = resolve_key(rules, "P2.4_NC/slots/nc_enum_sentence")
    assert p24["enumerate_max"] == nc["enumerate_max"]


# ----------------------------------------------------------------- Gate B tentativa 2 (revisor W2)
def _config_copy(tmp_path):
    """Cópia de config/ fora do repo: as mutações em arquivo nunca tocam o repositório."""
    shutil.copytree(REPO_ROOT / "config", tmp_path / "config")
    return tmp_path


def _edit_yaml(root, relative, change):
    path = root / relative
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_w2_m01_anomaly_in_data_driven_block(model, content):
    broken = copy.deepcopy(content)
    _block(broken, "P2.1_SUMMARY_S6_MEDICOES")["template"] = (
        "Quanto às medições, foram elaborados os Boletins de Medição referentes às rodovias "
        "{bm_highways_enum}. Na RD-101. As análises tiveram como objetivo verificar a compatibilidade.")
    _fails(model, "P2.1_SUMMARY_S6_MEDICOES: texto emitido contém valor observado da anomalia "
                  "P2.4_FRASE_TRUNCADA_MEDICOES", content_blocks=broken)


def test_w2_m02_anomaly_in_manual_input_block(model, content):
    broken = copy.deepcopy(content)
    _block(broken, "P2.1_MEETINGS_LIST")["items"] = [
        "RD-102: reunião com o Consórcio CLX/TRAFEX às sextas, às 10h;"]
    _fails(model, "anomalia P2.1_IDENTIFICACAO_RODOVIA: 'RD-102:'", content_blocks=broken)


def test_w2_m03_report_number_and_month_hardcoded(model, content):
    broken = copy.deepcopy(content)
    block = _block(broken, "ENC_P1")
    block["template"] = block["template"].replace("{month_label}", "Agosto/2026").replace(
        "{report_number}", "14")
    errors = validate_model(model, content_blocks=broken)
    assert any("ENC_P1: mês/ano literal" in e and "Agosto/2026" in e for e in errors), errors
    assert any("ENC_P1: número de relatório literal" in e and "N° 14" in e for e in errors), errors


@pytest.mark.parametrize("months", [["2030-01", "2030-02"], ["2026-08", "2026-09"]])
def test_w2_m04_evidence_months_outside_the_window(model, months):
    broken = copy.deepcopy(model)
    comp = _component(broken, "P2.4_CONDITIONS_TEXT")
    comp["confidence"], comp["evidence_months"] = "CONFIRMED", months
    _fails(broken, "P2.4_CONDITIONS_TEXT: evidence_months fora de model.evidence_window")


def test_w2_m05_confidence_above_block_evidence(model):
    broken = copy.deepcopy(model)
    comp = _component(broken, "P2.4_CONDITIONS_TEXT")
    comp["confidence"], comp["evidence_months"] = "CONFIRMED", ["2026-07", "2026-08"]
    _fails(broken, "P2.4_CONDITIONS_TEXT: confidence CONFIRMED acima da evidência declarada em "
                   "bloco P2.4_LAU_LEAD (MEDIUM)")


@pytest.mark.parametrize("source", ["not_sources", "02_Acompanhamento de NC automatizada.xlsm"])
def test_w2_m06_source_cannot_be_a_not_source(model, source):
    broken = copy.deepcopy(model)
    _component(broken, "P2.4_PENDING_LICENSES_TEXT")["source"] = source
    _fails(broken, "P2.4_PENDING_LICENSES_TEXT: source")


@pytest.mark.parametrize("value", ["false", "true", 1, None])
def test_w2_m07_human_review_must_be_boolean_true(model, value):
    broken = copy.deepcopy(model)
    _component(broken, "EXECUTIVE_SUMMARY_PARECER_THEMES")["human_review"] = value
    _fails(broken, "EXECUTIVE_SUMMARY_PARECER_THEMES: AI_SYNTHESIS precisa de allowed_sources e "
                   "human_review: true")


def test_w2_m08_vague_render(model):
    broken = copy.deepcopy(model)
    _component(broken, "P2.2_ROAD_DASHBOARDS")["render"] = "a definir"
    errors = validate_model(broken)
    assert any("RECONSTRUCTED_VISUAL com render sem referência arquivo#chave" in e for e in errors)
    assert any("P2.2_ROAD_DASHBOARDS.render: texto vago" in e for e in errors), errors


def test_w2_m09_manual_input_block_hidden_in_code_component(model):
    broken = copy.deepcopy(model)
    _component(broken, "P2.1_MEETINGS_AGENDA")["blocks"] = []
    _component(broken, "FIXED_BODY_TEXT")["blocks"].append("P2.1_MEETINGS_LIST")
    _fails(broken, "FIXED_BODY_TEXT: bloco MANUAL_INPUT P2.1_MEETINGS_LIST em componente CODE")


def test_w2_m10_ooxml_base_orientation_must_match_the_model(model, tmp_path):
    root = _config_copy(tmp_path)

    def portrait(data):
        for section in data["page"]["sections"]:
            section["orientation"] = "portrait"
    _edit_yaml(root, "config/ooxml_base.yaml", portrait)
    _fails(model, "config/ooxml_base.yaml#page/sections: orientação", root=root)


def test_w2_m10b_ooxml_base_margins_must_match_the_model(model, tmp_path):
    root = _config_copy(tmp_path)
    _edit_yaml(root, "config/ooxml_base.yaml",
               lambda data: data["page"]["sections"][1]["pgMar"].update(left=1701))
    _fails(model, "config/ooxml_base.yaml#page/sections/1: margem left", root=root)


def test_w2_m11_anomaly_reintroduced_in_data_rules(model, tmp_path):
    root = _config_copy(tmp_path)

    def oficio(data):
        para = next(p for p in data["paragraphs"] if p["id"] == "p24_overview")
        para["text"] = para["text"].replace(
            "{p24_types}", "Notificações de Não Conformidade, Ofício, Pareceres Técnicos, Boletins de Medição")
    _edit_yaml(root, "config/data_rules/p21_executive_summary.yaml", oficio)
    _fails(model, "config/data_rules/p21_executive_summary.yaml#paragraphs/p24_overview: texto "
                  "emitido contém valor observado da anomalia P2.1_RESUMO_OFICIO_SEM_DOCUMENTO",
           root=root)


def test_w2_m12_nc_limits_must_agree_between_files(model, tmp_path):
    root = _config_copy(tmp_path)
    path = root / "config/data_rules/p24_blocks.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("enumerate_max: 4", "enumerate_max: 30"),
                    encoding="utf-8")
    _fails(model, "enumerate_max 4 difere de config/data_rules/p24_blocks.yaml#P2.4_NC/slots/"
                  "nc_enum_sentence (30)", root=root)
    broken = copy.deepcopy(model)
    broken["editorial_defaults"]["nc_enumeration"]["value"] = "always_when_present"
    _fails(broken, "always_when_present com enumerate_max 4")
    broken["editorial_defaults"]["nc_enumeration"]["value"] = "up_to_6"
    _fails(broken, "up_to_6 diverge de enumerate_max 4")


def test_w2_m13_reference_golden_must_be_the_reference_report(model):
    broken = copy.deepcopy(model)
    broken["model"]["golden_tests"][0] = {"report_number": 13, "reference_month": "2026-07",
                                          "role": "reference"}
    _fails(broken, "golden 'reference' (Relatório G2 nº 13 — Julho/2026) difere de model.reference")


def test_w2_m14_annex_count_is_len_index_rows(model, content):
    broken = copy.deepcopy(model)
    next(v for v in broken["validations"] if v["id"] == "V_ANNEX_COUNT")["rule"] = (
        "annex_count == len(body_rows)")
    _component(broken, "CLOSING_ANNEX_COUNT")["render"] = "len(body_rows), numeral por extenso"
    errors = validate_model(broken)
    assert any(e.startswith("validations.V_ANNEX_COUNT: contagem de anexos") for e in errors)
    assert any(e.startswith("CLOSING_ANNEX_COUNT.render: contagem de anexos") for e in errors)
    other = copy.deepcopy(content)
    other["placeholders"]["annex_count"]["source"] = "len(body_rows)"
    _fails(model, "placeholders.annex_count: contagem de anexos", content_blocks=other)


def test_w2_m15_model_asset_needs_sha1(model):
    broken = copy.deepcopy(model)
    broken["assets"]["cover_logo_prog"] = {}
    _fails(broken, "asset 'cover_logo_prog' sem sha1 no modelo")


def test_w2_m15b_asset_file_on_disk_must_match_sha1(model, tmp_path):
    root = _config_copy(tmp_path)
    entry = yaml.safe_load((root / "config/assets_manifest.yaml").read_text("utf-8"))["assets"][0]
    target = root / entry["file"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"arquivo sintetico que nao e o asset")
    _fails(model, f"asset {entry['asset_id']!r}: sha1 do arquivo", root=root)


def test_w2_m16_product_removed_from_content_blocks(model, content):
    broken_content = copy.deepcopy(content)
    broken_content["blocks"] = [b for b in broken_content["blocks"]
                                if not str(b["block_id"]).startswith("P2.6")]
    broken = copy.deepcopy(model)
    for cid in ("FIXED_BODY_TEXT", "CONTRACT_QUOTE_P2X", "NO_ACTIVITY_SENTENCE"):
        comp = _component(broken, cid)
        comp["blocks"] = [b for b in comp["blocks"] if not b.startswith("P2.6")]
    _fails(broken, "produto 2.6: sem bloco de título P2.6_TITLE", content_blocks=broken_content)


# ----------------------------------------------------------------- controles positivos (w2_03)
def test_w2_controls_anomaly_detected_in_any_class_but_legit_s6_passes(model, content):
    broken = copy.deepcopy(content)
    block = _block(broken, "P2.1_SUMMARY_S6_MEDICOES")
    block["class"] = "TEMPLATE"
    block["template"] = ("Quanto às medições, ... Na RD-101. As análises tiveram como objetivo "
                         "verificar.")
    _fails(model, "anomalia P2.4_FRASE_TRUNCADA_MEDICOES", content_blocks=broken)
    # o prefixo legítimo 'Quanto às medições' não é trecho anômalo: o S6 vigente passa
    needles = [n for _, n in anomaly_needles(_jsonl("anomalies.jsonl"))]
    assert not any(n.startswith("Quanto às medições") for n in needles)
    s6 = _block(content, "P2.1_SUMMARY_S6_MEDICOES")["template"]
    assert s6.startswith("Quanto às medições") and validate_model(model) == []


def test_data_rule_texts_are_scanned(content):
    rules = {path: yaml.safe_load((REPO_ROOT / path).read_text("utf-8")) for path in (
        "config/data_rules/p21_executive_summary.yaml", "config/data_rules/p24_blocks.yaml",
        "config/data_rules/p22_highway_block.yaml")}
    where = {w.split("#")[0] for w, _ in emitted_texts(content, rules)}
    assert {"config/data_rules/p21_executive_summary.yaml", "config/data_rules/p24_blocks.yaml",
            "config/data_rules/p22_highway_block.yaml", "P2.1_MEETINGS_LIST",
            "P2.1_SUMMARY_S6_MEDICOES"} <= where
    texts = [t for _, t in emitted_texts(content, rules)]
    assert any(t.startswith("Aprovação: Todas as disciplinas") for t in texts)   # p22 templates
    assert not any("universal_condition" in t or "NÃO OBSERVADO" in t for t in texts)  # notas


def _all_emitted(model, content):
    import re

    rules = {f"config/data_rules/{p.name}": yaml.safe_load(p.read_text("utf-8"))
             for p in (REPO_ROOT / "config" / "data_rules").glob("*.yaml")}
    ooxml = yaml.safe_load((REPO_ROOT / "config" / "ooxml_base.yaml").read_text("utf-8"))
    return emitted_texts(content, rules, model, ooxml), re


def test_no_emitted_text_writes_referente_a_feminine_without_crase(model, content):
    """DEC-007 (texto gerado, nunca SOURCE_VERBATIM), anomalia CRASE_REFERENTE_AS (QA4-H):
    'referente(s) as' nunca; depois de 'referente(s) a' só 'cada' ou um slot ({mês}/{rodovia}
    são preenchidos por formas já com ou sem crase conforme o caso: 'Referente a Abril/2026')."""
    texts, re = _all_emitted(model, content)
    bad = [(w, m.group(0)) for w, t in texts
           for m in re.finditer(r"\breferentes?\s+a(s)?\s+(?!cada\b|\{)(\S+)", t, re.IGNORECASE)]
    assert bad == []
    assert any(w == "P2.1_CRONO_LEAD" and t.startswith("Referente às atividades")
               for w, t in texts)
    assert any(w == "P2.4_GAMB" and t.startswith("Ainda referente às Condicionantes")
               for w, t in texts)
    # a forma histórica fica como evidência (text_historical), não é emitida
    assert _block(content, "P2.1_CRONO_LEAD")["text_historical"].startswith("Referente as ")
    broken = copy.deepcopy(content)
    _block(broken, "P2.1_CRONO_LEAD")["text_standardized"] = "Referente as atividades x."
    _fails(model, "anomalia CRASE_REFERENTE_AS", content_blocks=broken)


def test_catalog_records_the_qa4h_findings():
    """QA4-H: crase (nº 11–14, FORMAT_VARIATION); cláusula de disciplinas do nº 13 como
    mudança de modelo (TRUE_MODEL_CHANGE, não a anomalia P2.1_RESUMO_DISCIPLINAS_P22); ressalva
    omitida na Análise Programa do nº 14."""
    rows = _jsonl("anomalies.jsonl")
    crase = [a for a in rows if a["component"] == "CRASE_REFERENTE_AS"]
    assert {a["report_id"] for a in crase} == {
        "Relatório G2 nº 11 — Maio/2026", "Relatório G2 nº 12 — Junho/2026",
        "Relatório G2 nº 13 — Julho/2026", "Relatório G2 nº 14 — Agosto/2026"}
    assert {a["classification"] for a in crase} == {"FORMAT_VARIATION"}
    clause = [a for a in rows if a["component"] == "P2.1_CLAUSULA_DISCIPLINAS_REMOVIDA"]
    assert [(a["report_id"], a["classification"]) for a in clause] == [
        ("Relatório G2 nº 13 — Julho/2026", "TRUE_MODEL_CHANGE")]
    omitted = [a for a in rows if a["component"] == "P2.2_EXTERNAL_PROG_RESSALVA_OMITIDA"]
    assert [a["report_id"] for a in omitted] == ["Relatório G2 nº 14 — Agosto/2026"]
    assert not any(a["should_learn_as_rule"] for a in crase + clause + omitted)


@pytest.mark.parametrize(
    ("observed", "expected", "needle"),
    [
        ("Relatório Mensal N° 13", "Relatório Mensal N° 14", "Mensal N° 13"),
        ("Relatório Consolidade de Gestão", "Relatório Consolidado de Gestão", "Consolidade"),
        ("'RD-102: reunião com a executora'", "'RD-102A'", "RD-102:"),
        ("'RD-104 RA-509.1;'", "'RD-104: RA-509.1.'", "RD-104 RA-509.1;"),
        ("Quanto às medições, ... Na RD-101. As análises", "frase completa", "Na RD-101. As análises"),
        ("'..., Ofício, Pareceres Técnicos, ...' na lista", "tipo citado só se houver OF",
         "Ofício, Pareceres Técnicos"),
    ],
)
def test_needle_is_the_divergent_part_not_the_legit_prefix(observed, expected, needle):
    needles = anomaly_needles([{"component": "X", "classification": "TYPO",
                                "observed_value": observed, "expected_value": expected}])
    assert [n for _, n in needles] == [needle]


def test_single_quoted_term_in_a_description_is_not_a_needle():
    assert anomaly_needles([{"component": "X", "classification": "COPY_FORWARD_ERROR",
                             "observed_value": "'aceito' da OAE cita uma das duas disciplinas",
                             "expected_value": "as duas disciplinas aceitas"}]) == []


def test_needle_ending_with_colon_is_anchored_at_the_end(model, content):
    broken = copy.deepcopy(content)
    _block(broken, "APRES_P4_OBJETO")["text"] += " Publicação pela Casa Civil: concluída."
    assert validate_model(model, content_blocks=broken) == []
    _block(broken, "APRES_P4_OBJETO")["text"] += " Publicação pela Casa Civil:"
    _fails(model, "anomalia P2.2_DUP_RD101_SEM_VALOR", content_blocks=broken)


def test_allowed_literal_is_explicit_and_never_a_window_report(model, content):
    block = _block(content, "P2.1_ATAS_REALOC")
    assert "N° 09" in block["text"] and block["allowed_literals"][0]["reason"]
    broken = copy.deepcopy(content)
    _block(broken, "P2.1_ATAS_REALOC")["allowed_literals"] = [{"literal": "N° 09"}]
    _fails(model, "P2.1_ATAS_REALOC: allowed_literals 'N° 09' sem reason", content_blocks=broken)
    broken = copy.deepcopy(content)
    _block(broken, "APRES_P4_OBJETO")["text"] += " Relatório N° 14"
    _block(broken, "APRES_P4_OBJETO")["allowed_literals"] = [{"literal": "N° 14", "reason": "x"}]
    _fails(model, "allowed_literals 'N° 14' é número ou mês de relatório da janela",
           content_blocks=broken)


# ----------------------------------------------------------------- F1: entradas humanas e IA
def test_f1_status_reference_date_and_nc_nature_are_declared(model):
    p22 = model["inputs"]["p22_status_reference_date"]
    assert p22["type"] == "date"
    assert set(p22["used_by"]) == {"P2.2_DISCIPLINE_STATUS", "P2.2_ROAD_DASHBOARDS"}
    nature = _component(model, "P2.4_NC_NATURE")
    assert nature["automation_class"] == "AI_SYNTHESIS" and nature["human_review"] is True
    assert nature["input"] == "ai_review"
    assert "P2.4_NC_NATURE" in model["inputs"]["ai_review"]["used_by"]


def test_f1_hidden_manual_input_in_data_rules_is_rejected(model):
    broken = copy.deepcopy(model)
    broken["inputs"].pop("p22_status_reference_date")
    _fails(broken, "config/data_rules/p22_highway_block.yaml#inputs/status_reference_date: nó "
                   "MANUAL_INPUT sem entrada em model.inputs")


def test_f1_hidden_ai_clause_is_rejected(model):
    broken = copy.deepcopy(model)
    broken["components"] = [c for c in broken["components"] if c["component_id"] != "P2.4_NC_NATURE"]
    broken["inputs"]["ai_review"]["used_by"].remove("P2.4_NC_NATURE")
    errors = validate_model(broken)
    assert any("P2.4_NC/slots/nc_enum_sentence/nc_nature_clause: nó AI_SYNTHESIS" in e
               for e in errors), errors
    assert any("P2.4_NC/slots/nc_period_sentence: nó AI_SYNTHESIS" in e for e in errors), errors


def test_f1_ai_and_manual_components_are_listed_in_their_input(model):
    broken = copy.deepcopy(model)
    broken["inputs"]["ai_review"]["used_by"].remove("P2.4_NC_NATURE")
    _fails(broken, "P2.4_NC_NATURE: inputs.ai_review.used_by não lista o componente")
    broken = copy.deepcopy(model)
    broken["inputs"]["signature_date"]["used_by"].append("COMPONENTE_FANTASMA")
    _fails(broken, "inputs.signature_date.used_by: componente inexistente COMPONENTE_FANTASMA")


def test_f1_input_value_refuses_undeclared_inputs(model):
    inputs = {"signatory_name": "Fulano", "entrada_escondida": "x"}
    assert input_value(inputs, "signatory_name", model) == "Fulano"
    assert input_value(inputs, "p22_status_reference_date", model) is None
    with pytest.raises(KeyError, match=r"não declarada em model\.inputs: entrada_escondida"):
        input_value(inputs, "entrada_escondida", model)
    with pytest.raises(TypeError):
        input_value(inputs, "signatory_name")


def test_f1_assemble_reads_inputs_only_through_input_value():
    source = (REPO_ROOT / "src/prog_g2_report/builder/assemble.py").read_text(encoding="utf-8")
    assert "inputs.get(" not in source and "inputs[" not in source


# ----------------------------------------------------------------- F3/F4/F5
def test_f3_s7_has_a_single_default(model, tmp_path):
    s7 = model["editorial_defaults"]["p21_s7_mode"]
    # QA-C: default técnico keyword_map (só tema com documento); fixed é opção editorial
    assert s7["value"] == "keyword_map" and "fixed" in s7["alternative"]
    root = _config_copy(tmp_path)
    _edit_yaml(root, "config/data_rules/p21_executive_summary.yaml",
               lambda data: data["render_maps"]["p24_pa_themes"].update(mode="keyword_map"))
    _fails(model, "declara 'mode': o default do S7 é único", root=root)
    broken = copy.deepcopy(model)
    broken["editorial_defaults"]["p21_s7_mode"]["value"] = "todos"
    _fails(broken, "editorial_defaults.p21_s7_mode: valor inválido 'todos'")


@pytest.mark.parametrize(
    ("cid", "level"),
    [
        ("P2.4_NC_ENUMERATION", "MEDIUM_CONFIDENCE"),
        ("P2.4_NONCONFORMITY_PARAGRAPH", "HIGH_CONFIDENCE"),
        ("P2.4_PENDING_LICENSES_TEXT", "HIGH_CONFIDENCE"),
        ("P2.4_RCA_CITATIONS", "HIGH_CONFIDENCE"),
        ("P2.2_DISCIPLINE_STATUS", "HIGH_CONFIDENCE"),
        ("P2.4_LICENSE_DASHBOARDS", "MEDIUM_CONFIDENCE"),
    ],
)
def test_f4_component_confidence_is_bounded_by_its_blocks_and_rules(model, cid, level):
    broken = copy.deepcopy(model)
    _component(broken, cid)["confidence"] = level
    _fails(broken, f"{cid}: confidence {level} acima da evidência declarada")


def test_f5_environmental_reference_date_default_matches_the_builder(model):
    # o montador usa a data de emissão quando a entrada falta (assemble._reference_date)
    assert model["inputs"]["environmental_reference_date"]["default"] == "issue_date"
    assert model["inputs"]["p22_status_reference_date"]["default"].endswith("issue_date")


def test_anomaly_deviation_must_exist_in_the_catalog(model, content):
    broken = copy.deepcopy(content)
    _block(broken, "APRES_P3_IDENTIFICACAO")["deviations"][2]["ref"] = "NEW_CANDIDATE FMT_X"
    _fails(model, "APRES_P3_IDENTIFICACAO: desvio ANOMALY sem anomalia do catálogo",
           content_blocks=broken)


# ----------------------------------------------------------------- Gate B tentativa 3 (revisor W3)
def test_w3_n01_anomaly_in_editorial_default_text(model):
    broken = copy.deepcopy(model)
    broken["editorial_defaults"]["contract_ref"]["value"] = (
        "Contrato N° 00/0000-PARC — Relatório Mensal N° 13")
    _fails(broken, "editorial_defaults.contract_ref: texto emitido contém valor observado da "
                   "anomalia APRESENTACAO_NUMERO_RELATORIO")


def test_w3_n02_hardcoded_month_in_editorial_default(model):
    broken = copy.deepcopy(model)
    broken["editorial_defaults"]["p22_empty_set"]["value"] = (
        "nenhuma disciplina em análise em Agosto/2026;")
    _fails(broken, "editorial_defaults.p22_empty_set: mês/ano literal")


@pytest.mark.parametrize(
    ("literal", "expected"),
    [
        ("referente a agosto de 2026", "mês/ano literal por extenso"),
        ("referente ao mês 08/2026", "mês/ano numérico literal"),
        ("referente a 2026-08", "mês de referência literal AAAA-MM"),
        ("décimo quarto relatório", "número de relatório por extenso"),
    ],
)
def test_w3_n03_hardcoded_month_or_number_in_other_spellings(model, content, literal, expected):
    broken = copy.deepcopy(content)
    block = _block(broken, "ENC_P1")
    block["template"] = f"{block['template']} {literal}"
    _fails(model, f"ENC_P1: {expected}", content_blocks=broken)


def test_document_numbers_are_not_month_literals(model):
    # 'nº 00/0000' (Instrumento de Convocação) e '00/0000-PARC' são números de documento
    assert validate_model(model) == []


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda m: m["products"][4].update(page_break_before={
            "value": True, "confidence": "CONFIRMED", "evidence_months": ["2026-09"]}),
         "products[2.5].page_break_before: CONFIRMED exige evidence_months"),
        (lambda m: m["products"][4].update(page_break_before={
            "value": True, "confidence": "CONFIRMED", "evidence_months": ["2026-09"]}),
         "products[2.5].page_break_before: evidence_months fora de model.evidence_window"),
        (lambda m: m["positioning"]["visual_anchors"].update(
            confidence="CONFIRMED", evidence_months=["2026-08"]),
         "positioning.visual_anchors: CONFIRMED exige evidence_months"),
        (lambda m: m["editorial_defaults"]["p21_s7_mode"].update(
            evidence_months=["2026-08", "2026-12"]),
         "editorial_defaults.p21_s7_mode: evidence_months fora de model.evidence_window"),
        (lambda m: m["page"].pop("evidence_months"), "page: CONFIRMED exige evidence_months"),
        (lambda m: m["contract"]["environmental_processes"].update(confidence="QUASE"),
         "contract.environmental_processes: confidence inválida"),
    ],
)
def test_w3_n04_confirmed_rule_applies_to_every_node_with_confidence(model, change, expected):
    broken = copy.deepcopy(model)
    change(broken)
    _fails(broken, expected)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda p: p["spacers"]["between"].append(
            {"after": "BLOCO_FANTASMA", "before": "P2.6_TITLE", "count": 9}),
         "bloco inexistente em g2_content_blocks (after: 'BLOCO_FANTASMA')"),
        (lambda p: p["spacers"]["between"].append(
            {"after": "TOC", "before": "APRES_TITLE", "count": 0}),
         "count deve ser inteiro ≥ 1"),
        (lambda p: p["visual_anchors"]["anchors"].append(
            {"block": "P2.4_INEXISTENTE", "mode": "after", "ref": "P2.4_ENV_INDICES_PANEL"}),
         "bloco inexistente em g2_content_blocks ('P2.4_INEXISTENTE')"),
        (lambda p: p["visual_anchors"]["anchors"].append(
            {"block": "P2.4_LIC_LIST", "mode": "befor", "ref": "P2.4_ENV_INDICES_PANEL"}),
         "modo inválido 'befor'"),
        (lambda p: p["visual_anchors"]["anchors"].append(
            {"block": "P2.4_LIC_LIST", "mode": "after", "ref": "PAINEL_FANTASMA"}),
         "não é visual de config/g2_render_rules.yaml"),
        (lambda p: p["static_assets"].update(asset_fantasma={"align": "center"}),
         "positioning.static_assets.asset_fantasma: asset não registrado no modelo"),
        (lambda p: p["static_assets"]["p22_predecessor_disciplines_diagram"].update(
            align="diagonal"), "align inválido 'diagonal'"),
        (lambda p: p["landscape_width"].update(value="larga"),
         "positioning.landscape_width: valor inválido 'larga'"),
    ],
)
def test_w3_n05_positioning_cites_existing_blocks_assets_and_modes(model, change, expected):
    broken = copy.deepcopy(model)
    change(broken["positioning"])
    _fails(broken, expected)


def test_w3_n06_ooxml_landscape_needs_landscape_page_size(model, tmp_path):
    root = _config_copy(tmp_path)
    _edit_yaml(root, "config/ooxml_base.yaml",
               lambda d: d["page"]["sections"][1]["pgSz"].update(w=11906, h=16838))
    _fails(model, "config/ooxml_base.yaml#page/sections/1: orientation landscape com pgSz retrato",
           root=root)
    root2 = _config_copy(tmp_path / "b")
    _edit_yaml(root2, "config/ooxml_base.yaml",
               lambda d: d["page"]["sections"][0]["pgSz"].update(w=12240, h=15840))  # Letter
    _fails(model, "pgSz 12240×15840 difere de model.page", root=root2)


def test_w3_n07_anomaly_in_ooxml_header_text(model, tmp_path):
    root = _config_copy(tmp_path)
    _edit_yaml(root, "config/ooxml_base.yaml", lambda d: d["header"].update(
        text=d["header"]["text"].replace("DO PROGRAMA", "DO P R OGRAMA")))
    _fails(model, "config/ooxml_base.yaml#header: texto emitido contém valor observado da "
                  "anomalia CABECALHO_ESPACAMENTO", root=root)


def test_w3_n08_reclassified_anomaly_cannot_hide_a_deviation(model, tmp_path):
    anomalies = _jsonl("anomalies.jsonl")
    for item in anomalies:
        if item["component"] == "P2.4_RELATORIO_CONSOLIDADO_GRAFIA":
            item["classification"] = "TRUE_MODEL_CHANGE"
    root = _config_copy(tmp_path)
    _edit_yaml(root, "config/data_rules/p24_blocks.yaml", lambda d: resolve_key(
        d, "P2.4_NC/slots/rnc_sentence").update(
            text=" Além do Relatório Consolidade de Gestão das Não Conformidades (RNC)."))
    _fails(model, "P2.4_NC: desvio ANOMALY P2.4_RELATORIO_CONSOLIDADO_GRAFIA classificado só "
                  "como ['TRUE_MODEL_CHANGE']", anomalies=anomalies, root=root)
    # controle: com o catálogo intacto, o mesmo texto é o trecho anômalo
    _fails(model, "anomalia P2.4_RELATORIO_CONSOLIDADO_GRAFIA: 'Consolidade'", root=root)


def test_w3_n09_one_default_per_parameter(model):
    assert "product_control_row_height_pt" not in model["editorial_defaults"]
    assert _component(model, "CONTROL_OF_PRODUCTS")["render_params"]["row_height_pt"] == 27.6
    for value in (40.0, 27.6):                          # conflitante ou igual: duplicado
        broken = copy.deepcopy(model)
        broken["editorial_defaults"]["product_control_row_height_pt"] = {"value": value}
        _fails(broken, "default duplicado: editorial_defaults.product_control_row_height_pt "
                       "repete CONTROL_OF_PRODUCTS.render_params.row_height_pt")


def test_w3_n10_review_key_is_a_cited_block_and_read_by_the_builder(model):
    broken = copy.deepcopy(model)
    _component(broken, "P2.4_NC_NATURE")["review_key"] = "P2.4_NC_NATUREZA"
    _fails(broken, "P2.4_NC_NATURE.review_key 'P2.4_NC_NATUREZA': bloco inexistente")
    broken = copy.deepcopy(model)
    _component(broken, "P2.4_NC_NATURE")["review_key"] = "P2.4_RM"
    _fails(broken, "P2.4_NC_NATURE.review_key 'P2.4_RM' não é o bloco citado no render")
    source = (REPO_ROOT / "src/prog_g2_report/builder/assemble.py").read_text(encoding="utf-8")
    assert '"P2.4_NC"' not in source and "nc_nature_clause(" in source


def test_w3_n11_template_fields_must_exist(model):
    broken = copy.deepcopy(model)
    _component(broken, "CLOSING_PARAGRAPH")["fields"] = ["report_numbr", "mes_ref"]
    _fails(broken, "CLOSING_PARAGRAPH.fields: campo inexistente 'report_numbr'")


@pytest.mark.parametrize("expr", ["len(index_rows) + 1", "len(index_rows)-1", "2 * len(index_rows)"])
def test_w3_n12_annex_count_is_len_index_rows_without_arithmetic(model, expr):
    broken = copy.deepcopy(model)
    next(v for v in broken["validations"] if v["id"] == "V_ANNEX_COUNT")["rule"] = (
        f"annex_count == {expr} (DEC-012)")
    _fails(broken, "validations.V_ANNEX_COUNT: contagem de anexos é len(index_rows) sem aritmética")
    broken = copy.deepcopy(model)
    _component(broken, "CLOSING_ANNEX_COUNT")["render"] = f"{expr}, numeral por extenso"
    _fails(broken, "CLOSING_ANNEX_COUNT.render: contagem de anexos é len(index_rows) sem aritmética")


# ----------------------------------------------------------------- MINOR e QA-C
def test_missing_final_period_needle_is_anchored_at_the_end(model, content):
    """P2.1_RESUMO_PONTO_FINAL: o trecho anômalo é a FALTA do ponto; a forma correta passa."""
    needles = [n for c, n in anomaly_needles(_jsonl("anomalies.jsonl"))
               if c == "P2.1_RESUMO_PONTO_FINAL"]
    assert needles == ["e P2.4"]
    broken = copy.deepcopy(content)
    _block(broken, "APRES_P4_OBJETO")["text"] += " Itens P2.1, P2.2 e P2.4."
    assert validate_model(model, content_blocks=broken) == []
    _block(broken, "APRES_P4_OBJETO")["text"] += " Itens P2.1, P2.2 e P2.4"
    _fails(model, "anomalia P2.1_RESUMO_PONTO_FINAL", content_blocks=broken)


def test_needle_with_locator_only_counts_in_its_paragraph():
    anomalies = [{"component": "X", "classification": "TYPO",
                  "observed_value": "'a) RD-104: ... da rodovia RD-102A'",
                  "expected_value": "'... da rodovia RD-104'"}]
    from prog_g2_report.model import _anomaly_text_errors
    assert _anomaly_text_errors([("b", "b) RD-102A: Análise da rodovia RD-102A;")], anomalies) == []
    assert _anomaly_text_errors([("a", "a) RD-104: Análise da rodovia RD-102A;")], anomalies)


@pytest.mark.parametrize(
    ("path", "change", "where"),
    [
        ("config/data_rules/p21_executive_summary.yaml",
         lambda d: next(p for p in d["paragraphs"] if p["id"] == "p24_pareceres_themes").update(
             text="Adicionalmente, foram emitidos pareceres técnicos no âmbito do Produto P2.4, "
                  "contemplando atendimento de condicionantes ambientais e {p24_pa_themes}."),
         "config/data_rules/p21_executive_summary.yaml#paragraphs/p24_pareceres_themes"),
        ("config/data_rules/p24_blocks.yaml",
         lambda d: resolve_key(d, "P2.4_PARECERES_MEDICAO").update(
             text="Foram emitidos pareceres referentes {themes}, assim como o Ateste de "
                  "Documentação do Processo de Medição."),
         "config/data_rules/p24_blocks.yaml#P2.4_PARECERES_MEDICAO/text"),
        # QA2-C (varredura): S1 do 2.1 (P2.1_S1_TEMAS_REUNIOES_SEM_SUPORTE)
        ("config/data_rules/p21_executive_summary.yaml",
         lambda d: next(p for p in d["paragraphs"] if p["id"] == "p21_coordination").update(
             text="Destacam-se as reuniões{atas_clause}{p21_meeting_topics}, com devolutivas das "
                  "análises realizadas."),
         "config/data_rules/p21_executive_summary.yaml#paragraphs/p21_coordination"),
        # QA2-C: P2.4_PARECERES_MEDICAO_2 e P2.4_ATAS (anomalias *_TEMAS_SEM_SUPORTE)
        ("config/data_rules/p24_blocks.yaml",
         lambda d: resolve_key(d, "P2.4_PARECERES_MEDICAO_2").update(
             text="Os documentos contemplam a análise {themes} e geotécnicos relacionados à "
                  "execução das obras, com destaque para {highlight}verificação."),
         "config/data_rules/p24_blocks.yaml#P2.4_PARECERES_MEDICAO_2/text"),
        ("config/data_rules/p24_blocks.yaml",
         lambda d: resolve_key(d, "P2.4_PARECERES_MEDICAO_2").update(
             text="Os documentos contemplam a análise {themes}, com destaque para as atividades "
                  "de obras de arte corrente e verificação dos controles."),
         "config/data_rules/p24_blocks.yaml#P2.4_PARECERES_MEDICAO_2/text"),
        ("config/data_rules/p24_blocks.yaml",
         lambda d: resolve_key(d, "P2.4_ATAS").update(
             text="Encaminham-se, ainda, as atas de reunião{themes}, contemplando as tratativas "
                  "de licenciamento ambiental."),
         "config/data_rules/p24_blocks.yaml#P2.4_ATAS/text"),
    ],
)
def test_qa_c_thematic_claim_without_document_is_rejected(model, tmp_path, path, change, where):
    """QA-C: texto fixo não afirma tema; o tema só sai pelo mapa, com documento que o sustente."""
    root = _config_copy(tmp_path)
    _edit_yaml(root, path, change)
    _fails(model, f"{where}: afirmação temática sem documento", root=root)


def test_qa_c_old_fixed_s7_sentence_is_rejected(model, content):
    broken = copy.deepcopy(content)
    block = _block(broken, "P2.1_SUMMARY_S7_PARECERES_P24")
    block["template"] = block["observed"]["text_no12_no14"]
    _fails(model, "config/g2_content_blocks.yaml#P2.1_SUMMARY_S7_PARECERES_P24: afirmação "
                  "temática sem documento", content_blocks=broken)


def test_qa2e_old_fixed_s8_sentence_is_rejected(model, content):
    """QA2-E: o fecho (S8) não afirma 'controle de medições'/'segurança do trabalho' sem
    documento; a frase fixa dos nº 12–14 de volta ao template reprova o modelo."""
    broken = copy.deepcopy(content)
    block = _block(broken, "P2.1_SUMMARY_S8_FECHO")
    block["template"] = block["observed"]["text_no12_no14"]
    _fails(model, "config/g2_content_blocks.yaml#P2.1_SUMMARY_S8_FECHO: afirmação "
                  "temática sem documento", content_blocks=broken)


@pytest.mark.parametrize(("block_id", "observed"), [
    ("P2.4_ATAS", "text_no12_no14"), ("P2.4_PARECERES_MEDICAO_2", "text_no13_no14"),
    ("P2.1_SUMMARY_S1_P21", "text_observed_no14")])
def test_qa2_c_old_fixed_p24_sentence_is_rejected(model, content, block_id, observed):
    """QA2-C: a frase fixa publicada de volta no template do bloco reprova o validador
    (P2.4_ATAS_TEMAS_SEM_SUPORTE, P2.4_PARECERES_MEDICAO_2_TEMAS_SEM_SUPORTE)."""
    broken = copy.deepcopy(content)
    block = _block(broken, block_id)
    block["template"] = block["observed"][observed]
    _fails(model, f"config/g2_content_blocks.yaml#{block_id}: afirmação temática sem documento",
           content_blocks=broken)


def test_qa_c_theme_map_must_declare_what_it_fills(model, tmp_path):
    root = _config_copy(tmp_path)
    _edit_yaml(root, "config/data_rules/p21_executive_summary.yaml",
               lambda d: d["render_maps"]["p24_pa_themes"].pop("fills"))
    _fails(model, "p24_pa_themes: mapa de temas sem `fills`", root=root)


def test_qa_c_environmental_processes_are_declared_contract_constants(model):
    spec = model["contract"]["environmental_processes"]
    assert spec["field"] == "gamb_process" and spec["confidence"] == "HIGH_CONFIDENCE"
    assert all(h.get("gamb_process") for h in model["contract"]["highways"])
    broken = copy.deepcopy(model)
    broken["contract"]["highways"][0].pop("gamb_process")
    _fails(broken, "contract.highways[RD-101]: sem gamb_process")


# ----------------------------------------------------------------- render sobre fixture sintética
def _synthetic_rows():
    """Mês sintético (rodovias RD-0x0, nenhum dado corporativo) que exercita os blocos."""
    from prog_g2_report.sources.master_list import MasterListRow

    def r(n, product, doc, manifestation, venture, description="", status="Entregue",
          period=None):
        names = {"2.1": "2.1 COORDENAÇÃO", "2.2": "2.2 PROJETOS", "2.4": "2.4 GERENCIAMENTO"}
        return MasterListRow(physical_row=n, product=names[product], company="Sintética",
                             document=doc, manifestation=manifestation, description=description,
                             venture=venture, delivery_date=None, delivery_status=status,
                             version=1, report_number=99, period=period)

    return [
        r(1, "2.1", "AT-501.1", "Ata de Reunião", "RD-010", "Reunião de alinhamento técnico"),
        r(2, "2.2", "PA-502.1", "Parecer", "RD-010", "Parecer Técnico - DUP"),
        r(3, "2.4", "RO-503.1", "Relatório Semanal de Acompanhamento de Obras", "RD-010",
          period="01/09/2026 a 07/09/2026"),
        r(4, "2.4", "RM-004.1", "Relatório Mensal", "RD-010"),
        r(5, "2.4", "NC-505.1", "Notificação de não conformidade", "RD-010"),
        r(6, "2.4", "RNC-006.1", "Relatório de Não Conformidade", "RD-010"),
        r(7, "2.4", "RNC-007.1", "Relatório de Não Conformidade", "RD-020"),
        r(8, "2.4", "BM-008.1", "Boletim de Medição", "RD-020", "Boletim de Medição de Julho/2026"),
        r(9, "2.4", "PA-509.1", "Parecer", "RD-010", "Parecer Técnico - Análise e Consolidação "
          "do Controle Tecnológico e Topográfico"),
        r(10, "2.4", "PA-510.1", "Parecer", "RD-020", "Avaliação de conformidade sst e ambiental"),
        r(11, "2.4", "RI-511.1", "Relatório de inspeção do alojamento", "RD-010"),
        r(12, "2.4", "RI-512.1", "Relatório de inspeção do alojamento", "RD-020"),
        r(13, "2.4", "RCA-513.1", "Análise do relatório de controle ambiental", "RD-020"),
        r(14, "2.4", "RA-514.1", "Relatório Ambiental Consolidado", "RD-010"),
    ]


def _rendered_texts():
    from prog_g2_report.render import p21_text, p24_text
    from prog_g2_report.render.p22_external import render_external_block

    rows = _synthetic_rows()
    texts = [(b.block_id, b.text) for b in p21_text.render_executive_summary(rows, {})]
    p24 = p24_text.render_all(p24_text.P24Inputs(body_rows=rows, reference_month="2026-09"))
    texts += [(bid, b.text) for bid, b in p24.items()]
    model = load_model()
    schema = model["inputs"]["p22_external_status"]["schema"]
    key = schema["no_information"]["key"]
    status = {"RD-010": {"dup": {"prog": "Status A", "gdp": "", "casa_civil": {key: "motivo"}}}}
    content = load_content_blocks()
    block = next(b for b in content["blocks"] if b["block_id"] == "P2.2_DESAPROPRIACAO")
    texts.append(("P2.2_DESAPROPRIACAO", render_external_block(
        "P2.2_DESAPROPRIACAO", block, status, ["RD-010"], schema,
        model["contract"]["highways"]).text))
    return [(w, t) for w, t in texts if t]


def test_rendered_blocks_over_synthetic_month_carry_no_anomalous_snippet():
    """Os renderizadores (p21, p24, p22 externo) sobre fixture sintética não emitem trecho de
    anomalia: a varredura do validador vale também para o texto GERADO, não só para o YAML."""
    from prog_g2_report.model import _anomaly_text_errors

    texts = _rendered_texts()
    assert len(texts) >= 15
    assert _anomaly_text_errors(texts, _jsonl("anomalies.jsonl")) == []
    joined = "\n".join(t for _, t in texts)
    assert "Publicação pela Casa Civil: Sem informação até o fechamento" in joined
    assert "Análise GDP: [PENDENTE:" in joined          # '' nunca vira rótulo sem valor


def test_rendered_scan_catches_an_anomaly_reintroduced_in_the_rules(monkeypatch):
    """Controle positivo: 'Consolidade' devolvido à frase de RNC aparece no texto GERADO e a
    varredura acusa."""
    from prog_g2_report.model import _anomaly_text_errors
    from prog_g2_report.render import p24_text

    rules = p24_text.load_rules()
    spec = copy.deepcopy(dict(rules.spec))
    nc = next(b for b in spec["blocks"] if b["block_id"] == "P2.4_NC")
    nc["slots"]["rnc_sentence"]["text"] = nc["slots"]["rnc_sentence"]["text"].replace(
        "Consolidado", "Consolidade")
    from dataclasses import replace as dc_replace

    block = p24_text.render_nc(_synthetic_rows(), rules=dc_replace(rules, spec=spec))
    errors = _anomaly_text_errors([("P2.4_NC", block.text)], _jsonl("anomalies.jsonl"))
    assert any("P2.4_RELATORIO_CONSOLIDADO_GRAFIA" in e for e in errors), errors


# ----------------------------------------------------------------- pendências do Gate B (revisor W4)
@pytest.mark.parametrize("presence", [
    "rodovias com licença pendente",                       # texto antigo do P2.4_LIC_LIST
    "opcional; observado nº 11–13 (formas diferentes), ausente nº 14",
    "if existe RO no Produto 2.4 OR quando houver",       # OR com parte sem tradução
])
def test_w4_minor2_untranslated_presence_is_a_validation_error(model, content, presence):
    """Presença sem predicado não pode virar 'presente por padrão' em silêncio."""
    broken = copy.deepcopy(content)
    _block(broken, "P2.4_LIC_LIST")["presence"] = presence
    _fails(model, "P2.4_LIC_LIST: presença não traduzida em predicado", content_blocks=broken)


def test_w4_minor2_every_current_presence_translates(content):
    from prog_g2_report.model import _presence_errors

    assert _presence_errors(content, REPO_ROOT) == []


@pytest.mark.parametrize(("change", "expected"), [
    (lambda s: s["no_information"].update(text=""), "no_information.text: texto padronizado"),
    (lambda s: s["no_information"].update(text=" . "), "no_information.text: texto padronizado"),
    (lambda s: s["no_information"].pop("text"), "no_information.text: texto padronizado"),
    (lambda s: s["no_information"].pop("key"), "no_information.key: chave do sentinela"),
    (lambda s: s.pop("no_information"), "no_information: sentinela de 'sem informação' ausente"),
    (lambda s: s.update(empty_value="'' vira texto vazio"), "empty_value: deve declarar"),
    (lambda s: s.pop("empty_value"), "empty_value: deve declarar"),
    (lambda s: s.pop("missing_field"), "missing_field: deve declarar"),
    (lambda s: s["no_information"].update(status="PENDING_HUMAN"), "no_information.status"),
])
def test_w4_minor3_validator_guards_the_p22_external_sentinel(model, change, expected):
    """Mudança que tira o texto (ou a chave) do sentinela, ou a regra de pendência do campo
    vazio, reprova o modelo (inputs.p22_external_status.schema)."""
    broken = copy.deepcopy(model)
    change(broken["inputs"]["p22_external_status"]["schema"])
    _fails(broken, f"inputs.p22_external_status.schema.{expected}")


def test_w4_minor3_schema_cannot_be_dropped(model):
    broken = copy.deepcopy(model)
    broken["inputs"]["p22_external_status"].pop("schema")
    _fails(broken, "inputs.p22_external_status.schema: ausente")
