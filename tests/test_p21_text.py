"""Produto 2.1 em texto puro: slots S0–S8, chamada da tabela, agenda e slots AI_SYNTHESIS.

Fixtures sintéticas (nenhum dado corporativo). O teste `golden` lê as Listas Mestras históricas
de `tmp/historical_sources/` e os dumps do agente K (`tmp/agent_K/`), fora do Git; pula se não
existirem.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from prog_g2_report import REPO_ROOT
from prog_g2_report.render import p21_text as t
from prog_g2_report.sources.master_list import MasterListRow

RULES = t.load_rules()
_counter = iter(range(10, 10_000))


def row(doc, product="2.1", desc="", venture="Geral", day=None, status="Entregue"):
    return MasterListRow(
        physical_row=next(_counter),
        product=f"{product} PRODUTO SINTETICO",
        company="Sintética",
        document=doc,
        manifestation=None,
        description=desc,
        venture=venture,
        delivery_date=day,
        delivery_status=status,
        version=1,
        report_number=99,
    )


def render(block_id, rows, inputs=None):
    return t.render_block(block_id, rows, inputs or {}, RULES)


def bold(block):
    return [s.text for p in block.paragraphs for s in p.segments if s.bold]


# --------------------------------------------------------------------------------- utilitários
def test_enumerate_pt():
    assert t.enumerate_pt(["A"]) == "A"
    assert t.enumerate_pt(["A", "B"]) == "A e B"
    assert t.enumerate_pt(["A", "B", "C"]) == "A, B e C"
    assert t.enumerate_pt(["A", "B"], serial_comma=True) == "A, e B"


def test_bold_markup_round_trip():
    segs = t.parse_bold_markup("as **CT-501.1**, e o **POP-002.1**")
    assert [s.bold for s in segs] == [False, True, False, True]
    assert t.segments_to_markup(segs) == "as **CT-501.1**, e o **POP-002.1**"


def test_registry_covers_model_blocks():
    from prog_g2_report.model import load_model

    model = load_model()
    wanted = set()
    for comp in model["components"]:
        if comp["component_id"] in {
            "EXECUTIVE_SUMMARY", "EXECUTIVE_SUMMARY_PARECER_THEMES", "P2.1_MEETINGS_AGENDA"
        }:
            wanted |= set(comp["blocks"])
    assert wanted <= set(t.P21_RENDERERS)
    rows = [row("AT-501.1", venture="RD-010")]
    for block_id, renderer in t.P21_RENDERERS.items():
        block = renderer(rows, {}, RULES)
        assert isinstance(block, t.BlockText) and block.block_id == block_id
        assert block.status in {"OK", "SKIPPED", "PENDING_HUMAN"}
        assert block.rule_keys, f"{block_id} sem chave de regra"


def test_to_component_result():
    block = render(t.S8, [row("AT-1.1")])
    result = block.to_component_result("EXECUTIVE_SUMMARY")
    assert result.component_id == "EXECUTIVE_SUMMARY" and result.status == "OK"
    assert result.facts["text"].startswith("De forma geral")


# ---------------------------------------------------------------------------------------- S0
def test_s0_lists_only_products_with_rows_with_final_period():
    rows = [row("AT-1.1", "2.1"), row("RO-1.1", "2.4"), row("EL-1.1", "2.6"), row("RO-2.1", "2.4")]
    block = render(t.S0, rows)
    assert block.text.endswith("itens P2.1, P2.4 e P2.6.")  # P2.1_RESUMO_PONTO_FINAL corrigido
    assert block.facts["products"] == ["P2.1", "P2.4", "P2.6"]


def test_s0_single_product_and_empty_report():
    assert render(t.S0, [row("NT-1.1", "2.2")]).text.endswith("itens P2.2.")
    assert render(t.S0, []).status == "SKIPPED"


# ---------------------------------------------------------------------------------------- S1
def test_s1_atas_clause_present_iff_at_in_p21():
    with_at = render(t.S1, [row("AT-501.1", desc="Reunião de alinhamento técnico")])
    assert "executoras, formalizadas por meio das Atas de Reunião emitidas no período, as quais" in (
        with_at.text
    )
    assert bold(with_at) == ["No Produto P2.1,", "das Atas de Reunião"]
    assert ("emitidas no período, as quais contemplaram tratativas relacionadas ao alinhamento "
            "das atividades técnicas. Ademais") in with_at.text
    without = render(t.S1, [row("PA-501.1"), row("AT-502.1", product="2.4")])
    assert "conduzidas com as empresas executoras. Ademais" in without.text
    assert "Atas de Reunião" not in without.text and "  " not in without.text
    assert without.facts["atas_clause"] is False


S1_OBSERVED_TOPICS = ("as quais contemplaram tratativas relacionadas ao acompanhamento das entregas "
                      "de projeto executivo, alinhamento das atividades técnicas, registro de "
                      "pendências, pactuação de prazos, devolutivas das análises realizadas e "
                      "suporte técnico às demandas de engenharia e gerenciamento contratual.")


def test_s1_meeting_topics_only_with_minutes_that_cite_them():
    """P2.1_S1_TEMAS_REUNIOES_SEM_SUPORTE (varredura do QA2-C): cada tratativa só com AT do 2.1
    que a cite na Descrição; com todas, a frase é a observada nos nº 12–14; sem AT, nenhuma."""
    generic = [row("AT-641.1", desc="Reunião de alinhamento técnico ")]
    block = render(t.S1, generic)
    assert "relacionadas ao alinhamento das atividades técnicas. Ademais" in block.text
    assert "pendências" not in block.text and "devolutivas" not in block.text
    assert block.facts["meeting_topics"] == {"alinhamento das atividades técnicas": ["AT-641.1"]}
    every = [*generic, row("AT-642.1", desc="Reunião sobre entregas de projeto executivo, "
                           "pendências, prazos, devolutivas e suporte técnico contratual")]
    assert S1_OBSERVED_TOPICS in render(t.S1, every).text
    nothing = render(t.S1, [row("PA-501.1"), row("AT-502.1", desc="Reunião de obra")])
    assert "as quais contemplaram" not in nothing.text and nothing.facts["meeting_topics"] == {}


def test_s1_highways_come_from_model_config():
    block = render(t.S1, [row("PA-501.1")])
    expected = t.enumerate_pt(RULES["config"]["rodovias_gerenciadas"])
    assert f"empreendimentos {expected}." in block.text


def test_s1_absent_in_a_month_without_p21_rows():
    """QA-E: 'No Produto P2.1, foram realizadas…' só com linhas do 2.1 (presença do bloco)."""
    month_without_p21 = [row("RO-1.1", "2.4", venture="RD-010"), row("NT-1.1", "2.2")]
    block = render(t.S1, month_without_p21)
    assert block.status == "SKIPPED" and block.paragraphs == []
    assert RULES["content_blocks"][t.S1]["presence"] == "if Produto 2.1 tem documentos"


# ---------------------------------------------------------------------------------------- S2
def test_s2_skipped_without_standardization_docs():
    assert render(t.S2, [row("AT-1.1"), row("CT-9.1", product="2.4")]).status == "SKIPPED"


def test_s2_draft_is_pending_with_review_brief():
    rows = [
        row("CT-502.1", desc="CIRCULAR TÉCNICA N°. 02/2026"),
        row("CT-503.1", desc="CIRCULAR TÉCNICA N°. 03/2026"),
        row("CT-504.1", desc="CIRCULAR TÉCNICA N°. 04/2026"),
        row("POP-009.1", desc="Procedimento Operacional Padrão Gestão de Não Conformidade"),
    ]
    block = render(t.S2, rows)
    assert block.status == "PENDING_HUMAN"
    assert block.text.startswith("Foram formalizados documentos voltados à padronização")
    assert (
        "foram entregues as Circulares Técnicas CT-502.1 a CT-504.1 e o POP-009.1, referente ao "
        "Procedimento Operacional Padrão de Gestão de Não Conformidade." in block.text
    )
    assert bold(block) == ["Circulares Técnicas CT-502.1 a CT-504.1", "POP-009.1"]
    brief = block.review_brief
    assert brief is not None and brief.slot_id == t.S2
    assert [d["document"] for d in brief.documents] == ["CT-502.1", "CT-503.1", "CT-504.1", "POP-009.1"]
    assert "Circulares Técnicas" in " ".join(brief.notes)


def test_s2_single_ct_pop_and_it_derive_titles():
    rows = [
        row("CT-501.1", desc="CIRCULAR TÉCNICA Nº. 01/2026"),
        row("POP-007.1", desc="Procedimento Operacional Padrão Fiscalização e Gestão Ambiental."),
        row("IT-006.1", desc="Instrução Técnica Inspeção em Alojamentos"),
    ]
    text = render(t.S2, rows).text
    assert (
        "foram entregues a Circular Técnica CT-501.1, referente à Circular Técnica nº 01/2026, "
        "o POP-007.1, referente ao Procedimento Operacional Padrão de Fiscalização e Gestão "
        "Ambiental, e a IT-006.1, referente à Instrução Técnica de Inspeção em Alojamentos."
    ) in text


def test_s2_non_consecutive_cts_are_listed():
    rows = [row("CT-501.1", desc="x"), row("CT-505.1", desc="y")]
    assert "as Circulares Técnicas CT-501.1 e CT-505.1." in render(t.S2, rows).text


def test_s2_uses_approved_review_text():
    rows = [row("CT-502.1", desc="CIRCULAR TÉCNICA N°. 02/2026")]
    approved = {t.S2: {"text": "a **CT-502.1**, referente a tema aprovado.", "documents": ["CT-502.1"]}}
    block = render(t.S2, rows, {"ai_review": approved})
    assert block.status == "OK" and block.review_brief is None
    assert block.text.endswith("foram entregues a CT-502.1, referente a tema aprovado.")
    assert bold(block) == ["CT-502.1"]


def test_s2_stale_approval_from_other_report_is_not_used():
    rows = [row("CT-507.1", desc="CIRCULAR TÉCNICA N°. 07/2026")]
    stale = {t.S2: {"text": "a **CT-502.1**, aprovada em outro mês", "documents": ["CT-502.1"]}}
    block = render(t.S2, rows, {"ai_review": stale})
    assert block.status == "PENDING_HUMAN"
    assert "CT-502.1" not in block.text and "CT-507.1" in block.text
    assert "outro relatório" in " ".join(block.review_brief.notes)


# ---------------------------------------------------------------------------------------- S3
def test_s3_types_and_highways_without_geral():
    rows = [
        row("NT-1.1", "2.2", venture="RD-020"),
        row("PA-2.1", "2.2", venture="RD-010"),
        row("NT-3.1", "2.2", venture="Geral"),
        row("PA-4.1", "2.4", venture="RD-999"),
    ]
    block = render(t.S3, rows)
    assert "foram emitidas Notas Técnicas e Pareceres Técnicos relacionados" in block.text
    assert "das rodovias RD-010 e RD-020." in block.text
    assert "Geral" not in block.text and "RD-999" not in block.text
    assert bold(block) == ["Produto P2.2", "Notas Técnicas e Pareceres Técnicos"]
    assert "Foram tratadas disciplinas" not in block.text   # P2.1_RESUMO_DISCIPLINAS_P22
    assert not block.text.endswith(" ")


def test_s3_only_pareceres_agrees_verb_and_inactive_product_skips():
    block = render(t.S3, [row("PA-2.1", "2.2", venture="RD-010")])
    assert "foram emitidos Pareceres Técnicos relacionados" in block.text
    assert render(t.S3, [row("AT-1.1")]).status == "SKIPPED"


# ---------------------------------------------------------------------------------------- S4
P22_PAS = [
    row("PA-601.1", "2.2", "Parecer Técnico - Complemento de Documentação de Utilidade Pública"),
    row("PA-602.1", "2.2", "Parecer Técnico - Eventograma"),
    row("PA-603.1", "2.2", "Parecer Técnico Projeto de Pavimentação"),
    row("PA-604.1", "2.2", "Assunto sem tema"),
]


def test_s4_without_review_is_draft_pending_with_brief(tmp_path):
    block = render(t.S4, P22_PAS)
    assert block.status == "PENDING_HUMAN"
    assert "abrangendo temas como complementação da DUP, eventograma e pavimentação. Esses" in (
        block.text
    )
    brief = block.review_brief
    assert brief.question and brief.draft == "complementação da DUP, eventograma e pavimentação"
    assert any("PA-604.1" in n for n in brief.notes)
    path = t.write_review_brief(brief, tmp_path)
    content = path.read_text(encoding="utf-8")
    assert path.name == f"review_{t.S4}.md" and "| PA-604.1 |" in content and t.S4 in content


def test_s4_with_review_uses_approved_text():
    block = render(t.S4, P22_PAS, {"ai_review": {t.S4: "complementação da DUP"}})
    assert block.status == "OK" and block.facts["slot_source"] == "ai_review"
    assert "abrangendo temas como complementação da DUP. Esses documentos" in block.text


def test_s4_skipped_without_pa_in_p22():
    assert render(t.S4, [row("NT-1.1", "2.2"), row("PA-1.1", "2.4")]).status == "SKIPPED"


def test_ai_slot_accepts_plugged_provider():
    class Fake:
        name = "fake_llm"

        def draft(self, slot_id, documents, rules):
            return f"tema sintético de {len(documents)} pareceres", ("nota",)

    slot = t.ai_slot(t.S4, {}, P22_PAS, rules=RULES, provider=Fake())
    assert slot.status == "PENDING_HUMAN" and slot.source == "fake_llm"
    assert slot.text == "tema sintético de 4 pareceres"
    assert slot.review_brief.provider == "fake_llm"


# ---------------------------------------------------------------------------------------- S5
def test_s5_types_follow_prefixes_and_omit_oficio_without_of():
    rows = [
        row("RO-1.1", "2.4", venture="RD-010"),
        row("NC-1.1", "2.4", venture="RD-020"),
        row("BM-1.1", "2.4", venture="RD-010"),
        row("RNC-1.1", "2.4", venture="Geral"),
    ]
    block = render(t.S5, rows)
    assert "obras dos trechos RD-010 e RD-020, por meio da elaboração dos" in block.text
    assert (
        "dos Relatórios Semanais de Acompanhamento de Obras, Notificações de Não Conformidade e "
        "Boletins de Medição. Paralelamente" in block.text
    )
    assert "Ofício" not in block.text   # P2.1_RESUMO_OFICIO_SEM_DOCUMENTO
    assert bold(block)[0] == "No âmbito do Gerenciamento Técnico (P2.4),"
    assert block.facts["not_cited"] == ["RNC"]


def test_s5_cites_oficio_when_of_exists_and_skips_inactive_product():
    rows = [row("RO-1.1", "2.4", venture="RD-010"), row("OF-1.1", "2.4", venture="RD-010")]
    assert "Ofício" in render(t.S5, rows).text
    assert render(t.S5, [row("AT-1.1")]).status == "SKIPPED"


@pytest.mark.parametrize(
    ("prefixes", "expected"),
    [
        (["RO", "NC"], "elaboração dos Relatórios Semanais"),
        (["NC", "BM"], "elaboração das Notificações de Não Conformidade"),     # mês sem RO
        (["AT", "PA"], "elaboração das Atas de Reunião"),
        (["OF"], "elaboração do Ofício"),
        (["RCA"], "elaboração das análises de Relatórios"),
    ],
)
def test_s5_article_agrees_with_the_first_cited_type(prefixes, expected):
    """QA-E: sem RO o S5 saía 'dos Notificações'; o artigo segue o 1º tipo (render_maps)."""
    rows = [row(f"{p}-1.1", "2.4", venture="RD-010") for p in prefixes]
    text = render(t.S5, rows).text
    assert expected in text
    assert "dos Notificações" not in text and "dos Atas" not in text


def test_s5_single_highway_agrees_in_the_singular():
    """Revisor W4 (B): 'das obras dos trechos RD-104' -> 'do trecho RD-104'
    (render_maps.highway_forms.p24_rodovias, mesmo one/many do S6)."""
    one = render(t.S5, [row("RO-1.1", "2.4", venture="RD-104"), row("BM-1.1", "2.4",
                                                                    venture="RD-104")])
    assert "acompanhamento técnico das obras do trecho RD-104, por meio" in one.text
    assert "trechos" not in one.text
    many = render(t.S5, [row("RO-1.1", "2.4", venture="RD-104"),
                         row("RO-2.1", "2.4", venture="RD-101")])
    assert "das obras dos trechos RD-101 e RD-104, por meio" in many.text


def test_every_highway_list_slot_agrees_with_one_highway():
    """Todo slot de lista de rodovias dos parágrafos tem forma 1 × 2+ (highway_forms) e o
    literal trocado existe no texto-base: S1 (contrato), S3 (2.2), S5 (2.4)."""
    forms = RULES["render_maps"]["highway_forms"]
    assert set(forms) == {"rodovias_gerenciadas", "p22_rodovias", "p24_rodovias"}
    texts = {p["id"]: p["text"] for p in RULES["paragraphs"] if "text" in p}
    for slot, pid in (("rodovias_gerenciadas", "p21_coordination"),
                      ("p22_rodovias", "p22_overview"), ("p24_rodovias", "p24_overview")):
        assert forms[slot]["literal"] in texts[pid]
        assert "{" + slot + "}" in forms[slot]["literal"]
    s3 = render(t.S3, [row("NT-1.1", "2.2", venture="RD-020"), row("NT-2.1", "2.2", venture="Geral")])
    assert "projetos executivos da rodovia RD-020." in s3.text and "rodovias" not in s3.text
    rules = dict(RULES)
    rules["config"] = {**RULES["config"], "rodovias_gerenciadas": ["RD-010"]}
    s1 = t.render_block(t.S1, [row("PA-501.1")], {}, rules)
    assert "equipes envolvidas no empreendimento RD-010. Destacam-se" in s1.text


def test_highway_clause_is_the_single_one_many_mechanism():
    forms = RULES["render_maps"]["measurements"]["highways_clause"]
    assert t.highway_clause(forms, ["RD-1"]) == forms["one_highway"].format(highway="RD-1")
    assert t.highway_clause(forms, ["RD-1", "RD-2"]) == forms["many_highways"].format(
        highways="RD-1 e RD-2")


def test_s5_activities_need_a_document_of_the_month():
    """Revisor W4 MINOR 4: a frase 'Paralelamente…' só cita atividade com documento do 2.4 que
    a sustente (render_maps.p24_activities), como o S7."""
    only_bm = render(t.S5, [row("BM-1.1", "2.4", "Boletim de Medição de Maio/2026", "RD-010")])
    assert only_bm.text.endswith(
        "Boletins de Medição. Paralelamente, foram desenvolvidas atividades relacionadas ao "
        "suporte técnico às medições.")
    assert list(only_bm.facts["activities"]) == ["suporte técnico às medições"]
    mixed = render(t.S5, [
        row("NC-1.1", "2.4", "Notificação de Natureza Obra", "RD-010"),
        row("RA-1.1", "2.4", "Relatório Consolidado Mensal", "RD-010"),
        row("PA-1.1", "2.4", "Parecer Técnico - interferência com rede de água", "RD-010"),
    ])
    assert ("relacionadas ao acompanhamento ambiental, interferências identificadas em campo e "
            "controle de não conformidades.") in mixed.text
    for absent in ("controle tecnológico", "medições", "contratual", "segurança do trabalho"):
        assert absent not in mixed.text.partition("Paralelamente")[2]
    first_feminine = render(t.S5, [row("RO-1.1", "2.4", "Relatório semanal", "RD-010"),
                                   row("RI-1.1", "2.4", "Relatório de inspeção", "RD-010")])
    assert "relacionadas à conformidade de saúde e segurança do trabalho." in first_feminine.text
    nothing = render(t.S5, [row("AT-1.1", "2.4", "Reunião de alinhamento da obra", "RD-010")])
    assert "Paralelamente" not in nothing.text
    assert nothing.text.endswith("Atas de Reunião de alinhamento das obras.")


def test_s5_paragraph_text_has_no_literal_activity():
    """O texto-base não traz atividade literal: todas saem do mapa (validador _thematic_errors)."""
    text = next(p for p in RULES["paragraphs"] if p["id"] == "p24_overview")["text"]
    for theme in RULES["render_maps"]["p24_activities"]["themes"]:
        assert theme["bare"] not in text


# ---------------------------------------------------------------------------------------- S6
def test_s6_skipped_without_bm_or_with_only_in_progress():
    assert render(t.S6, [row("RO-1.1", "2.4")]).status == "SKIPPED"
    in_progress = row("BM-001.1", "2.4", "Boletim de Medição de Maio/2026", "RD-010",
                      status="Em elaboração")
    assert render(t.S6, [in_progress]).status == "SKIPPED"


def test_s6_highways_and_detail_per_highway_never_truncated():
    rows = [
        row("BM-005.1", "2.4", "Boletim de Medição de Fevereiro/2026", "RD-020"),
        row("BM-004.1", "2.4", "Boletim de Medição de Janeiro/2026", "RD-020"),
        row("BM-010.2", "2.4", "Boletim de Medição de Julho/2026", "RD-010"),
        row("BM-011.1", "2.4", "Boletim de Medição de Agosto/2026", "RD-030", status="Em elaboração"),
    ]
    text = render(t.S6, rows).text
    assert "referentes às rodovias RD-010 e RD-020. " in text
    assert (
        "Na RD-010, foi avaliado o Boletim de Medição 10, referente ao mês de julho/2026. "
        "Na RD-020, foram avaliados os Boletins de Medição 04 e 05, referentes aos meses de "
        "janeiro/2026 e fevereiro/2026. As análises tiveram" in text
    )
    assert "RD-030" not in text
    assert not re.search(r"Na RD-\w+\.", text)   # P2.4_FRASE_TRUNCADA_MEDICOES


def test_s6_single_highway_uses_the_singular_form():
    """P2.1_RESUMO_BM_CONCORDANCIA: uma rodovia só -> 'referentes à RD-x' (one_highway)."""
    rows = [row(f"BM-00{i}.1", "2.4", f"Boletim de Medição de {m}/2026", "RD-040")
            for i, m in ((7, "Abril"), (8, "Maio"), (9, "Junho"))]
    text = render(t.S6, rows).text
    one = RULES["render_maps"]["measurements"]["highways_clause"]["one_highway"]
    assert f"Boletins de Medição {one.format(highway='RD-040')}. Na RD-040, foram avaliados" in text
    assert "às rodovias" not in text


# ---------------------------------------------------------------------------------------- S7
def _s7_rules(mode):
    rules = dict(RULES)
    editorial = dict(rules["editorial_defaults"])
    editorial["p21_s7_mode"] = {**editorial["p21_s7_mode"], "value": mode}
    rules["editorial_defaults"] = editorial
    return rules


def test_s7_default_is_the_single_model_default():
    from prog_g2_report.model import load_model

    model_mode = load_model()["editorial_defaults"]["p21_s7_mode"]["value"]
    assert t.s7_mode(RULES) == model_mode == "keyword_map"            # QA-C: default técnico
    assert "mode" not in RULES["render_maps"]["p24_pa_themes"]       # um default só (Gate B F3)
    with pytest.raises(KeyError, match="p21_s7_mode"):
        t.s7_mode({**RULES, "editorial_defaults": {}})


def test_s7_default_never_claims_a_theme_without_a_pa():
    """P2.1_S7_TEMAS_SEM_SUPORTE: com o default, tema sem PA do 2.4 não sai (mês sintético só
    com PA de obra: nada de condicionantes, desapropriação, SST…)."""
    block = render(t.S7, [row("PA-1.1", "2.4", "Parecer Técnico Avaliação de conformidade obra")])
    assert block.status == "OK"
    assert block.text.endswith("contemplando avaliação de conformidade técnica de obra.")
    for theme in RULES["render_maps"]["p24_pa_themes"]["themes"]:
        if theme["label"] != "avaliação de conformidade técnica de obra":
            assert theme["label"] not in block.text


def test_s7_fixed_option_emits_the_whole_sentence_of_n12_to_n14():
    """Opção editorial `fixed`: a frase INTEIRA dos nº 12–14 (observada no bloco), qualquer que
    seja a Descrição dos PA do 2.4."""
    expected = RULES["content_blocks"][t.S7]["observed"]["text_no12_no14"]
    for rows in ([row("PA-1.1", "2.4", "conformidade obra")],
                 [row("PA-2.1", "2.4", "Assunto inédito")]):
        block = t.render_block(t.S7, rows, {}, _s7_rules("fixed"))
        assert block.status == "OK" and block.text == expected
    assert render(t.S7, [row("NC-1.1", "2.4")]).status == "SKIPPED"


def test_s7_themes_by_keyword_map_in_fixed_order():
    rows = [
        row("PA-1.1", "2.4", "Parecer Técnico Avaliação de Conformidade Obra"),
        row("PA-2.1", "2.4", "Parecer Técnico Avaliação de conformidade sst e ambiental"),
        row("PA-3.1", "2.4", "Parecer Técnico - Análise e Consolidação do Controle Tecnológico"),
        row("PA-4.1", "2.4", "Assunto inédito"),
        row("PA-5.1", "2.2", "Parecer Técnico - Projeto de Desapropriação"),
    ]
    block = t.render_block(t.S7, rows, {}, _s7_rules("keyword_map"))
    assert block.text == (
        "Adicionalmente, foram emitidos pareceres técnicos no âmbito do Produto P2.4, "
        "contemplando avaliação de conformidade ambiental, saúde e segurança do trabalho e "
        "avaliação de conformidade técnica de obra."
    )
    assert "desapropriação" not in block.text       # PA do 2.2 não conta
    assert block.facts["covered_elsewhere"] == {"controle tecnológico": ["PA-3.1"]}
    assert block.facts["unmatched"] == ["PA-4.1"] and "PA-4.1" in block.detail


def test_s7_keyword_map_pending_when_no_theme_and_skipped_without_pa():
    rules = _s7_rules("keyword_map")
    assert t.render_block(t.S7, [row("PA-1.1", "2.4", "Assunto inédito")], {},
                          rules).status == "PENDING_HUMAN"
    assert t.render_block(t.S7, [row("NC-1.1", "2.4")], {}, rules).status == "SKIPPED"


# ----------------------------------------------------------------------------- S8, tabela
def _s8_full_rows():
    """Um documento por atuação do fecho (paragraphs.closing.slots.closing_themes)."""
    return [row("AT-1.1", "2.1"), row("NT-1.1", "2.2"), row("RO-1.1", "2.4"),
            row("BM-1.1", "2.4", status="Em elaboração"), row("RCA-1.1", "2.4"),
            row("RI-1.1", "2.4"), row("NC-1.1", "2.4"), row("PA-1.1", "2.4", "Assunto")]


def test_s8_with_every_theme_reproduces_the_fixed_text_of_n12_n14():
    from prog_g2_report.builder.blocks import blocks_by_id, load_blocks

    observed = blocks_by_id(load_blocks())[t.S8].raw["observed"]["text_no12_no14"]
    block = render(t.S8, _s8_full_rows())
    assert block.status == "OK" and block.text == observed
    assert block.facts["unsupported"] == []


def test_s8_never_claims_a_theme_without_document():
    """paragraphs.closing.slots.closing_themes (QA2-E): mês sintético sem BM, sem RI/SST e sem 2.1 — o fecho
    não afirma controle de medições, segurança do trabalho nem coordenação setorial."""
    rows = [r for r in _s8_full_rows() if t.doc_prefix(r) not in {"AT", "BM", "RI"}]
    block = render(t.S8, rows)
    assert block.status == "OK"
    for theme in ("na coordenação setorial", "no controle de medições",
                  "na verificação da segurança do trabalho"):
        assert theme not in block.text
        assert theme in block.facts["unsupported"]
    assert block.text == (
        "De forma geral, os produtos desenvolvidos no período demonstram a continuidade da "
        "atuação do Programa no acompanhamento das entregas de projeto executivo, no gerenciamento "
        "técnico das obras, no monitoramento ambiental, na gestão de não conformidades e no "
        "suporte técnico às decisões administrativas necessárias ao avanço dos empreendimentos.")
    # a palavra-chave da Descrição sustenta a atuação, como no S5 ('medic', 'sst')
    by_desc = render(t.S8, [row("PA-2.1", "2.4", "Parecer do processo de medição"),
                            row("PA-3.1", "2.4", "Inspeção de SST no canteiro")])
    assert "no controle de medições" in by_desc.text
    assert "na verificação da segurança do trabalho" in by_desc.text
    assert render(t.S8, []).status == "SKIPPED"


def test_s8_unsupported_follows_required_and_when_unsupported():
    """slots.closing_themes: obrigatório + when_unsupported (SKIPPED no modelo; PENDING_HUMAN
    por padrão) ou `required: false` com `empty`, como os mapas `slots.<nome>` do 2.4."""
    import copy

    spec = t.closing_spec(RULES)
    assert spec["required"] is True and spec["when_unsupported"] == "SKIPPED"
    rules = copy.deepcopy(RULES)
    slot = t.closing_spec(rules)
    slot.pop("when_unsupported")
    assert t.render_block(t.S8, [], {}, rules).status == "PENDING_HUMAN"
    slot.update(required=False, empty="nas atividades do período")
    block = t.render_block(t.S8, [], {}, rules)
    assert block.status == "OK" and block.text.endswith("do Programa nas atividades do período.")


def test_s8_text_has_no_literal_theme():
    """O tema só sai pelo mapa (validação de afirmação temática do modelo)."""
    template = t._paragraph_rule(RULES, "closing")["text"]
    for theme in t.closing_spec(RULES)["themes"]:
        assert theme["label"] not in template


def test_s8_and_table_call_trigger():
    assert render(t.TABLE_CALL, [row("NT-1.1", "2.2")]).status == "SKIPPED"
    assert render(t.TABLE_CALL, [row("NT-1.1", "2.1")]).text.startswith("A relação dos produtos")


def test_executive_summary_order():
    blocks = t.render_executive_summary([row("AT-1.1")], {}, RULES)
    assert [b.block_id for b in blocks] == list(t.SUMMARY_ORDER)


# ---------------------------------------------------------------------------------- reuniões
ORDER = [t.highway(m["rodovia"]) for m in RULES["config"]["meetings"]]


def _atas(hw, *days):
    return [row(f"AT-{hw}-{i}.1", "2.1", "Reunião de alinhamento técnico ", hw, d)
            for i, d in enumerate(days)]


def test_meetings_from_input_agenda():
    agenda = [
        {"highway": hw, "executora": f"Consórcio X{i}" if i == 0 else f"Empresa {i}",
         "weekday": "quintas", "hour": "10h"}
        for i, hw in enumerate(reversed(ORDER))
    ]
    block = render(t.MEETINGS, [], {"meetings_agenda": agenda})
    assert block.status == "OK"
    assert [p.text.split(":")[0] for p in block.paragraphs] == ORDER     # ordem do modelo
    first = ORDER[-1]
    assert block.paragraphs[-1].text == f"{first}: reunião com o Consórcio X0 às quintas, às 10h;"
    assert block.paragraphs[0].text.startswith(f"{ORDER[0]}: reunião com a Empresa")
    assert all(p.style == "PargrafodaLista" and p.list_style == "bullet" for p in block.paragraphs)
    assert all(not p.text.startswith("RD-102:") for p in block.paragraphs)  # P2.1_IDENTIFICACAO_RODOVIA


def test_meetings_without_input_derive_weekday_and_mark_hour_pending():
    hw_a, hw_b = ORDER[0], ORDER[1]
    rows = (
        _atas(hw_a, date(2026, 8, 6), date(2026, 8, 13), date(2026, 8, 17))  # qui, qui, seg
        + _atas(hw_b, date(2026, 8, 7), date(2026, 8, 10))                   # sex, seg: empate
        + [row("AT-x.1", "2.4", "Reunião de alinhamento técnico", hw_b, date(2026, 8, 11))]
    )
    agenda = [{"highway": hw_a, "executora": "DELTA"}]
    block = render(t.MEETINGS, rows, {"meetings_agenda": agenda})
    assert block.status == "PENDING_HUMAN"
    assert block.paragraphs[0].text == f"{hw_a}: reunião com a DELTA às quintas, às [PENDENTE];"
    assert f"{hw_a}.hour" in block.facts["pending"]
    assert f"{hw_b}.weekday" in block.facts["pending"]                       # empate -> pendente
    assert f"{hw_b}.executora" in block.facts["pending"]
    item = block.facts["items"][0]
    assert item["weekday_source"] == "atas" and item["weekday_from_atas"] == "quintas"


def test_meetings_input_weekday_is_checked_against_atas():
    rows = _atas(ORDER[0], date(2026, 8, 6), date(2026, 8, 13))
    agenda = [{"highway": ORDER[0], "executora": "CSG", "weekday": "sextas", "hour": "9h"}]
    item = render(t.MEETINGS, rows, {"meetings_agenda": agenda}).facts["items"][0]
    assert item["weekday"] == "sextas" and item["weekday_matches_atas"] is False


# ------------------------------------------------------------------------------------ golden
def _find(relative: str) -> Path | None:
    for base in (REPO_ROOT, REPO_ROOT.parents[2] if len(REPO_ROOT.parents) > 2 else REPO_ROOT):
        candidate = base / relative
        if candidate.exists():
            return candidate
    return None


def _dump(name: str) -> dict[int, str]:
    path = _find(f"tmp/agent_K/{name}")
    if path is None:
        pytest.skip(f"dump do agente K ausente: {name}")
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[0].isdigit():
            out[int(parts[0])] = parts[2].strip()
    return out


def _rows(name: str, number: int):
    from prog_g2_report.sources import master_list as ml

    path = _find(f"tmp/historical_sources/{name}")
    if path is None:
        pytest.skip(f"Lista Mestra histórica ausente: {name}")
    return ml.select(ml.load(path), number)


_SENT = re.compile(r"(?<=\.)\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text) if s.strip()]


def _supported_themes(rows) -> set[str]:
    themes = RULES["render_maps"]["p24_pa_themes"]["themes"]
    pas = [t.fold(r.description) for r in rows if r.product_code == "2.4"
           and t.doc_prefix(r) == "PA"]
    return {x["label"] for x in themes if any(t._match_any(x["any"], d) for d in pas)}


def _supported_meeting_topics(rows) -> set[str]:
    cfg = RULES["render_maps"]["p21_meeting_topics"]
    ats = [t.fold(r.description) for r in rows if r.product_code == cfg["trigger"]["product"]
           and t.doc_prefix(r) == cfg["trigger"]["prefix"]]
    return {x["bare"] for x in cfg["themes"] if any(t._match_any(x["any"], d) for d in ats)}


def _supported_activities(rows) -> set[str]:
    cfg = RULES["render_maps"]["p24_activities"]["themes"]
    p24 = [r for r in rows if r.product_code == "2.4"]
    return {x["bare"] for x in cfg if any(
        t.doc_prefix(r) in (x.get("prefixes") or ()) or t._match_any(x["any"], t.fold(r.description))
        for r in p24)}


def _claims(hist: dict[int, str], n: int, rows=()):
    """Afirmações do resumo executivo do relatório (dump K, parágrafos 63–71/72), classificadas.

    FIXED/DERIVABLE contam na meta; ANOMALY não pode ser reproduzida; INTERPRETIVE é do slot
    AI_SYNTHESIS; UNSUPPORTED = afirmação sem PA do 2.4 que a sustente na Descrição (candidata a
    anomalia nova, não catalogada).
    """
    themes = [x["label"] for x in RULES["render_maps"]["p24_pa_themes"]["themes"]]
    claims = []
    paras = {63 + i: hist[63 + i] for i in range(10) if 63 + i in hist}
    idx = 63
    claims.append(("DERIVABLE", paras[idx]))                                    # S0
    s1 = _sentences(paras[64])
    claims += [("FIXED", s1[0]), ("FIXED", s1[2])]                              # S1
    # reuniões: moldura FIXED; cláusula das Atas DERIVABLE (AT no 2.1); cada tratativa é
    # DERIVABLE se uma AT do 2.1 a cita, senão S1_UNSUPPORTED (P2.1_S1_TEMAS_REUNIOES_SEM_SUPORTE)
    head, _, topics_text = s1[1].partition(" as quais contemplaram tratativas relacionadas ")
    claims.append(("FIXED", "Destacam-se as reuniões periódicas conduzidas com as empresas "
                            "executoras"))
    if "formalizadas" in head:
        claims.append(("DERIVABLE", head.rstrip(",")))
    topics = [x["bare"] for x in RULES["render_maps"]["p21_meeting_topics"]["themes"]]
    for topic in topics:
        assert topic in topics_text
    supported = _supported_meeting_topics(rows)
    claims += [("DERIVABLE" if x in supported else "S1_UNSUPPORTED", x) for x in topics]
    idx = 65
    if paras[65].startswith("Foram formalizados"):                              # S2 (nº 13)
        s2 = paras[65]
        claims.append(("FIXED", _sentences(s2)[0]))
        claims.append(("DERIVABLE", "as Circulares Técnicas CT-502.1 a CT-504.1"))
        claims.append(("INTERPRETIVE", "referentes às informações de aspectos ambientais"))
        claims.append(
            ("DERIVABLE", "e o POP-009.1, referente ao Procedimento Operacional Padrão de Gestão "
             "de Não Conformidade.")
        )
        idx = 66
    s3 = _sentences(paras[idx])
    claims += [("DERIVABLE", s3[0]), ("FIXED", s3[1])]                          # S3
    claims += [("ANOMALY", s) for s in s3[2:]]               # disciplinas copiadas (nº 13)
    s4 = paras[idx + 1]
    head, _, rest = s4.partition("abrangendo temas como ")
    claims += [("FIXED", head + "abrangendo temas como"), ("INTERPRETIVE", rest.split(". ")[0])]
    claims.append(("FIXED", _sentences(s4)[-1]))
    s5 = _sentences(paras[idx + 2])
    claims.append(("DERIVABLE", s5[0].replace("Ofício, ", "")))
    claims.append(("ANOMALY", "Ofício"))                     # P2.1_RESUMO_OFICIO_SEM_DOCUMENTO
    # frase 'Paralelamente…' (render_maps.p24_activities): moldura FIXED; cada atividade é
    # DERIVABLE se um documento do 2.4 a sustenta, senão UNSUPPORTED
    # (P2.1_S5_ATIVIDADES_SEM_SUPORTE: 'interferências identificadas em campo' nos nº 12–14)
    activities = [x["bare"] for x in RULES["render_maps"]["p24_activities"]["themes"]]
    for activity in activities:
        assert activity in s5[1]
    claims.append(("FIXED", s5[1].partition(" relacionadas ")[0] + " relacionadas"))
    supported = _supported_activities(rows)
    claims += [("DERIVABLE" if a in supported else "S5_UNSUPPORTED", a) for a in activities]
    assert "interferências identificadas em campo" not in supported
    s6 = _sentences(paras[idx + 3])
    claims.append(("ANOMALY", s6[0]))      # nº 13 P2.1_RESUMO_BM_RODOVIAS; nº 14 _CONCORDANCIA
    if n == 14:                            # uma rodovia só: forma singular (one_highway)
        claims.append(("DERIVABLE", s6[0].replace("referentes às rodovias", "referentes à")))
    claims += [("ANOMALY", "Na RD-101."), ("FIXED", s6[-1])]
    s7 = paras[idx + 4]
    for theme in themes:
        assert theme in s7
    # default editorial_defaults.p21_s7_mode = keyword_map: moldura FIXED; cada tema é
    # DERIVABLE se um PA do 2.4 o sustenta, senão UNSUPPORTED (P2.1_S7_TEMAS_SEM_SUPORTE: nº 14
    # sem condicionantes e desapropriação; nº 13 sem condicionantes e evidências de encerramento)
    claims.append(("FIXED", s7.partition("contemplando ")[0] + "contemplando"))
    supported = _supported_themes(rows)
    claims += [("DERIVABLE" if theme in supported else "UNSUPPORTED", theme) for theme in themes]
    assert {c for k, c in claims if k == "UNSUPPORTED"}, "a frase fixa tinha tema sem PA"
    claims += [("FIXED", paras[idx + 5]), ("FIXED", paras[idx + 6])]           # S8, tabela
    return claims


def _score(claims, generated: dict[str, str]):
    text = "\n".join(generated.values())
    s5 = generated[t.S5]
    result = {"FIXED+DERIVABLE": [0, 0], "ANOMALY": [0, 0], "UNSUPPORTED": [0, 0]}
    missing = []
    for kind, claim in claims:
        if kind in {"FIXED", "DERIVABLE"}:
            result["FIXED+DERIVABLE"][1] += 1
            ok = claim in text
            result["FIXED+DERIVABLE"][0] += ok
            if not ok:
                missing.append(claim)
        elif kind == "ANOMALY":
            result["ANOMALY"][1] += 1
            haystack = s5 if claim == "Ofício" else text
            result["ANOMALY"][0] += claim not in haystack       # conta as NÃO reproduzidas
        elif kind in {"UNSUPPORTED", "S5_UNSUPPORTED", "S1_UNSUPPORTED"}:
            result["UNSUPPORTED"][1] += 1
            haystack = {"S5_UNSUPPORTED": s5, "S1_UNSUPPORTED": generated[t.S1]}.get(kind, text)
            result["UNSUPPORTED"][0] += claim in haystack
    return result, missing


GOLDEN = [
    (14, "lista_mestre_v335.0.xlsx", "14_-_08_2026.txt"),
    (13, "lista_mestre_v134.0.xlsx", "13_-_07_2026.txt"),
]


@pytest.mark.golden
@pytest.mark.parametrize(("number", "workbook", "dump"), GOLDEN, ids=["n14", "n13"])
def test_golden_executive_summary(number, workbook, dump):
    hist = _dump(dump)
    rows = _rows(workbook, number)
    blocks = t.render_executive_summary(rows, {}, RULES)
    generated = {b.block_id: b.text for b in blocks}
    claims = _claims(hist, number, rows)
    result, missing = _score(claims, generated)
    got, total = result["FIXED+DERIVABLE"]
    print(f"\nRelatório G2 nº {number}: FIXED+DERIVABLE {got}/{total}; anomalias não reproduzidas "
          f"{result['ANOMALY'][0]}/{result['ANOMALY'][1]}; sem sustentação reproduzidas "
          f"{result['UNSUPPORTED'][0]}/{result['UNSUPPORTED'][1]}")
    assert missing == [], missing
    assert result["ANOMALY"][0] == result["ANOMALY"][1]
    assert result["UNSUPPORTED"][0] == 0
    # slots AI_SYNTHESIS sem revisão ficam pendentes; com a revisão aprovada, o parágrafo é o real
    status = {b.block_id: b.status for b in blocks}
    assert status[t.S4] == "PENDING_HUMAN"
    s4_hist = next(v for v in hist.values() if v.startswith("Também foram emitidos pareceres"))
    themes = s4_hist.partition("abrangendo temas como ")[2].split(". ")[0]
    approved = t.render_block(t.S4, rows, {"ai_review": {t.S4: themes}}, RULES)
    assert approved.status == "OK" and approved.text == s4_hist


@pytest.mark.golden
def test_golden_n13_standardization_and_meetings():
    hist = _dump("13_-_07_2026.txt")
    rows = _rows("lista_mestre_v134.0.xlsx", 13)
    s2_hist = hist[65]
    enumeration = s2_hist.partition("foram entregues ")[2]
    approved = t.render_block(t.S2, rows, {"ai_review": {t.S2: enumeration}}, RULES)
    assert approved.status == "OK" and approved.text == s2_hist
    fix = {"RD-102": "RD-102A"}                              # P2.1_IDENTIFICACAO_RODOVIA
    weekdays = {}
    for line in (hist[i] for i in (42, 43, 44, 45)):
        hw = line.split(":")[0]
        weekdays[fix.get(hw, hw)] = re.search(r"às (\w+), às", line).group(1)
    block = t.render_block(t.MEETINGS, rows, {}, RULES)
    derived = {i["highway"]: i["weekday"] for i in block.facts["items"]}
    assert derived == weekdays


@pytest.mark.golden
def test_golden_n12_long_measurement_form_and_theme_draft():
    hist = _dump("12_-_06_2026.txt")
    rows = _rows("lista_mestre_v335.0.xlsx", 12)
    s6 = t.render_block(t.S6, rows, {}, RULES)
    assert s6.text == hist[70]
    s4 = t.render_block(t.S4, rows, {}, RULES)
    assert s4.status == "PENDING_HUMAN" and s4.text == hist[67]
    s2 = t.render_block(t.S2, rows, {}, RULES)
    assert s2.text in hist[65]  # sem a frase EXTERNAL "encontra-se em elaboração"
