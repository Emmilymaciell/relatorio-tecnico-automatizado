"""P2.2_HIGHWAY_BLOCK (texto por rodovia): regras sintéticas + golden contra o nº 14 e o nº 13."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
import yaml

from _p22_synthetic import (
    EST,
    OAE,
    PRI,
    SEC,
    approved,
    ged,
    ged_sheet,
    in_analysis,
    late,
    panel,
    rejected,
    sheet,
)
from prog_g2_report.render import p22_text as t
from prog_g2_report.sources import projects as pj

REF = date(2026, 9, 7)
RULES = t.load_rules()


def _wb(*rows, panel_rows=None, ged_rows=None):
    return pj.from_rows(sheet(*rows), panel_rows, ged_rows)


def _block(*rows, road="RD-103", ref=REF, rules=RULES, **kw):
    blocks = t.build_highway_blocks(_wb(*rows, **kw), ref, rules)
    return next(b for b in blocks if b.facts["road"] == road)


def _status(block):
    return [p.text for p in block.paragraphs if p.kind == "status"]


# ------------------------------------------------------------------ regras e modelo
def test_rules_come_from_the_model_files():
    spec = yaml.safe_load(t.SPEC_PATH.read_text(encoding="utf-8"))
    model = yaml.safe_load(t.MODEL_PATH.read_text(encoding="utf-8"))
    assert RULES.empty_in_analysis == model["editorial_defaults"]["p22_empty_set"]["value"]
    assert RULES.text_exclusions == tuple(spec["exclusions"]["text"]["by_prefix_of_discipline"])
    assert RULES.road_order == tuple(spec["road_order"]["value"])


def test_renderer_registered():
    assert t.P22_RENDERERS["P2.2_HIGHWAY_BLOCK"] is t.build_highway_blocks


def test_rules_accept_raw_spec_mapping():
    spec = yaml.safe_load(t.SPEC_PATH.read_text(encoding="utf-8"))
    spec["editorial_defaults"] = {"p22_empty_set": {"value": "vazio editorial;", "always_emit_line": True}}
    block = _block(approved("1.1", "RD-103", EST, "Estudos A"),
                   late("1.2", "RD-103", EST, "Estudos B"), rules=spec)
    assert "Disciplinas em análise: vazio editorial;" in _status(block)


# ------------------------------------------------------------------ estrutura
def test_block_structure_heading_bold_and_image_slot():
    block = _block(approved("1.1", "RD-102 A", EST, "Estudos A"), road="RD-102A")
    kinds = [p.kind for p in block.paragraphs]
    assert kinds[:4] == ["spacer", "heading", "image_slot", "group"]
    heading = block.paragraphs[1]
    assert heading.text == "Referente ao acompanhamento de projeto executivo da Rodovia RD-102A:"
    assert [s.text for s in heading.segments if s.bold] == ["Rodovia RD-102A"]
    assert block.paragraphs[2].ref == "P2.2_ROAD_DASHBOARD:RD-102A"
    assert block.paragraphs[3].text == "Disciplinas da Fase de Estudos:"
    assert block.paragraphs[3].list_level == 0
    assert all(p.list_level == 1 for p in block.paragraphs if p.kind == "status")


def test_road_order_follows_panel_then_unknown_roads():
    rows = [approved("1.1", r, EST, "Estudos A") for r in ("RD-104", "RD-102 A", "RD-999", "RD-103")]
    wb = _wb(*rows, panel_rows=panel("RD-103 - X", "RD-102A - Y", "RD-101 - Z", "RD-104 - W"))
    roads = [b.facts["road"] for b in t.build_highway_blocks(wb, REF, RULES)]
    assert roads == ["RD-103", "RD-102A", "RD-104", "RD-999"]


def test_road_order_falls_back_to_model_without_panel():
    rows = [approved("1.1", r, EST, "Estudos A") for r in ("RD-104", "RD-101", "RD-102 A", "RD-103")]
    roads = [b.facts["road"] for b in t.build_highway_blocks(_wb(*rows), REF, RULES)]
    assert roads == list(RULES.road_order)


def test_group_order_by_first_ged_delivery_until_reference():
    rows = [approved("1.1", "RD-103", EST, "Estudos A"),
            approved("2.1", "RD-103", PRI, "Projeto P"),
            approved("3.1", "RD-103", SEC, "Projeto S"),
            approved("4.1", "RD-103", OAE, "Projeto de Obra de Arte Especial (OAE)")]
    deliveries = ged_sheet(
        ged("RD-103", EST, "Estudos A", "2025-12-29"),
        ged("RD-103", PRI, "Projeto P", "2026-02-25"),
        ged("RD-103", OAE, "Projeto de Obra de Arte Especial (OAE)", "2026-06-15"),
        ged("RD-103", SEC, "Projeto S", "2026-07-06"),
        ged("RD-103-0", SEC, "Projeto S", "2025-01-01"),   # não se funde com RD-103
    )
    july = _block(*rows, ged_rows=deliveries, ref=date(2026, 7, 31))
    assert july.facts["group_order"] == [EST, PRI, OAE, SEC]
    june = _block(*rows, ged_rows=deliveries, ref=date(2026, 6, 30))
    assert june.facts["group_order"] == [EST, PRI, OAE, SEC]      # SEC sem entrega: ao fim
    may = _block(*rows, ged_rows=deliveries, ref=date(2026, 5, 31))
    assert may.facts["group_order"] == [EST, PRI, SEC, OAE]       # sem entrega: Ordem Disciplina


def test_group_order_without_ged_uses_discipline_order():
    rows = [approved("3.1", "RD-103", SEC, "Projeto S"), approved("1.1", "RD-103", EST, "Estudos A")]
    assert _block(*rows).facts["group_order"] == [EST, SEC]


def test_disciplines_in_numeric_order():
    rows = [late(o, "RD-103", SEC, n) for o, n in
            (("3.10", "Projeto Dez"), ("3.2", "Projeto Dois"), ("3.9", "Projeto Nove"))]
    lines = _status(_block(*rows))
    assert lines[-1] == ("Disciplinas não entregues: ainda não foram entregues o Projeto Dois, "
                         "o Projeto Nove e o Projeto Dez.")


def test_text_exclusions():
    rows = [approved("3.1", "RD-103", SEC, "Projeto S"),
            late("3.6", "RD-103", SEC, "Memoriais Descritivos da Obra"),
            late("3.9", "RD-103", SEC, "Equipe Fixa de Projeto de Engenharia - PES"),
            late("3.10", "RD-103", SEC, "Projeto Executivo")]
    block = _block(*rows)
    assert _status(block) == [
        "Aceitação: todas as disciplinas do Viário Secundário encontram-se aceitas em 1º nível;",
        "Aprovação: Todas as disciplinas encontram-se aprovadas.",
    ]
    assert block.facts["groups"][0]["sets"]["universe"] == ["Projeto S"]


# ------------------------------------------------------------------ conjuntos e presença
def test_group_all_approved_omits_in_analysis_line():
    block = _block(approved("1.1", "RD-103", EST, "Estudos A"), approved("1.2", "RD-103", EST, "Estudos B"))
    assert _status(block) == [
        "Aceitação: todas as disciplinas da Fase de Estudos encontram-se aceitas em 1º nível;",
        "Aprovação: Todas as disciplinas encontram-se aprovadas.",
    ]


def test_empty_in_analysis_uses_editorial_default_and_is_always_emitted():
    block = _block(approved("1.1", "RD-103", EST, "Estudos A"), late("1.2", "RD-103", EST, "Estudos B"))
    assert ("Disciplinas em análise: " + RULES.empty_in_analysis) in _status(block)


def test_empty_in_analysis_can_be_omitted_by_editorial_default():
    rules = replace(RULES, always_emit_in_analysis=False)
    block = _block(approved("1.1", "RD-103", EST, "Estudos A"), late("1.2", "RD-103", EST, "Estudos B"),
                   rules=rules)
    assert not any(s.startswith("Disciplinas em análise") for s in _status(block))


def test_pending_approval_depends_on_column_w():
    rows = [
        rejected("2.1", "RD-103", PRI, "Projeto Vencido", "2026-09-04"),
        rejected("2.2", "RD-103", PRI, "Projeto Hoje", "2026-09-07"),
        rejected("2.3", "RD-103", PRI, "Projeto Futuro", "2026-09-08"),
        rejected("2.4", "RD-103", PRI, "Projeto Aguardando", "Aguardando previsão"),
        rejected("2.5", "RD-103", PRI, "Projeto Reentregue", "Em Análise"),
        rejected("2.6", "RD-103", PRI, "Projeto Não Aceito", "Aguardando previsão", accepted="Não"),
    ]
    block = _block(*rows)
    assert "Disciplinas pendentes de aprovação: Projeto Vencido, Projeto Hoje e Projeto Aguardando." in _status(block)
    sets = block.facts["groups"][0]["sets"]
    assert sets["pending_approval"] == ["Projeto Vencido", "Projeto Hoje", "Projeto Aguardando"]


def test_pending_and_not_delivered_absent_when_empty():
    block = _block(approved("2.1", "RD-103", PRI, "Projeto A"), in_analysis("2.2", "RD-103", PRI, "Projeto B"))
    labels = [s.split(":")[0] for s in _status(block)]
    assert labels == ["Aceitação", "Aprovação", "Disciplinas em análise"]


def test_not_delivered_uses_recalculated_situation():
    rows = [approved("3.1", "RD-103", SEC, "Projeto A"),
            late("3.2", "RD-103", SEC, "Projeto B", forecast=date(2026, 9, 10), situation_cached="Atrasado")]
    assert not any("não entregues" in s for s in _status(_block(*rows)))
    later = _block(*rows, ref=date(2026, 9, 11))
    assert _status(later)[-1] == "Disciplinas não entregues: ainda não foi entregue o Projeto B."


def test_empty_acceptance_and_approval_forms():
    block = _block(late("3.1", "RD-103", SEC, "Projeto A"), late("3.2", "RD-103", SEC, "Projeto B"))
    lines = _status(block)
    assert lines[0] == ("Aceitação: nenhuma disciplina dessa fase se encontra aceita em 1º nível "
                        "no fechamento do presente relatório;")
    assert lines[1] == ("Aprovação: nenhuma disciplina dessa fase se encontra aprovada no fechamento "
                        "do presente relatório;")


def test_oae_all_accepted_is_enumerated_not_universal():
    rows = [in_analysis("4.1", "RD-103", OAE, "Projeto de Obra de Arte Especial (OAE)"),
            in_analysis("4.2", "RD-103", OAE, "Memoriais de Cálculo Estrutural e Quantitativo")]
    lines = _status(_block(*rows))
    assert lines[0] == ("Aceitação: encontram-se aceitos em 1º nível o Projeto de Obra de Arte Especial "
                        "(OAE) e os Memoriais de Cálculo Estrutural e Quantitativo;")
    assert lines[2] == ("Disciplinas em análise: o Projeto de Obra de Arte Especial (OAE) e os Memoriais "
                        "de Cálculo Estrutural e Quantitativo encontram-se em análise pelo Programa.")


def test_agreement_singular_feminine_and_single_plural_noun():
    rows = [approved("1.1", "RD-103", EST, "Documentação para Declaração de Utilidade Pública (DUP)"),
            in_analysis("1.2", "RD-103", EST, "Estudos de Tráfego"),
            late("1.3", "RD-103", EST, "Relatório de Atividades Preliminares")]
    lines = _status(_block(*rows))
    assert lines[0] == ("Aceitação: encontram-se aceitos em 1º nível a Documentação para Declaração de "
                        "Utilidade Pública (DUP) e os Estudos de Tráfego;")
    assert lines[1] == ("Aprovação: a Documentação para Declaração de Utilidade Pública (DUP) "
                        "encontra-se aprovada;")
    assert lines[2] == "Disciplinas em análise: os Estudos de Tráfego encontram-se em análise pelo Programa;"
    assert lines[3] == ("Disciplinas não entregues: ainda não foi entregue o Relatório de Atividades "
                        "Preliminares.")


def test_singular_masculine_acceptance():
    rows = [in_analysis("4.1", "RD-101", OAE, "Projeto de Obra de Arte Especial (OAE)"),
            late("4.2", "RD-101", OAE, "Memoriais de Cálculo Estrutural e Quantitativo")]
    lines = _status(_block(*rows, road="RD-101"))
    assert lines[0] == ("Aceitação: o Projeto de Obra de Arte Especial (OAE) encontra-se aceito "
                        "em 1º nível;")


def test_punctuation_semicolon_and_final_period_per_road():
    rows = [approved("1.1", "RD-103", EST, "Estudos A"), late("3.1", "RD-103", SEC, "Projeto B"),
            approved("1.1", "RD-104", EST, "Estudos A")]
    for road in ("RD-103", "RD-104"):
        lines = _status(_block(*rows, road=road))
        assert all(s.endswith(";") for s in lines[:-1])
        assert lines[-1].endswith(".")


def test_no_foram_tratadas_clause_and_no_dates_in_text():
    rows = [approved("1.1", "RD-103", EST, "Estudos A"),
            rejected("2.1", "RD-103", PRI, "Projeto B", "2026-09-01")]
    text = "\n".join(_block(*rows).lines)
    assert "Foram tratadas" not in text
    assert not re.search(r"\d{2}/\d{2}", text)


# ------------------------------------------------------------------ ressalva por disciplina (DEC-015)
def _approval(block, group_index=0):
    """Linha de Aprovação do n-ésimo grupo do bloco."""
    start = [i for i, p in enumerate(block.paragraphs) if p.kind == "group"][group_index]
    after = [p.text for p in block.paragraphs[start + 1:] if p.kind == "status"]
    return next(s for s in after if s.startswith("Aprovação:"))


def test_reservation_rules_come_from_the_spec():
    spec = yaml.safe_load(t.SPEC_PATH.read_text(encoding="utf-8"))
    qualifier = spec["templates"]["approval"]["reservation_qualifier"]
    assert RULES.reservation_mode == qualifier["value"] == "per_discipline"
    assert RULES.reservation_separator == qualifier["sentence_separator"]
    assert qualifier["decision"] == "DEC-015"


def test_approval_splits_plain_and_reserved_in_own_sentence():
    rows = [approved("2.1", "RD-103", PRI, "Projeto A"),
            approved("2.2", "RD-103", PRI, "Projeto B", evaluation="Aprovado com ressalva"),
            approved("2.3", "RD-103", PRI, "Projeto C", evaluation="Aprovado com Ressalvas"),
            in_analysis("2.4", "RD-103", PRI, "Projeto D")]
    block = _block(*rows)
    assert _approval(block) == ("Aprovação: o Projeto A encontra-se aprovado. O Projeto B e o "
                                "Projeto C encontram-se aprovados com ressalva;")
    assert block.facts["groups"][0]["sets"]["approval_with_reservation"] == ["Projeto B", "Projeto C"]
    assert block.facts["groups"][0]["sets"]["approval"] == ["Projeto A", "Projeto B", "Projeto C"]


def test_approval_plain_plural_then_reserved_singular_feminine():
    rows = [approved("1.1", "RD-103", EST, "Relatório de Atividades Preliminares"),
            approved("1.2", "RD-103", EST, "Estudos de Tráfego", evaluation="Aprovada"),
            approved("1.6", "RD-103", EST, "Documentação para Declaração de Utilidade Pública (DUP)",
                     evaluation="Aprovada com ressalva"),
            late("1.8", "RD-103", EST, "Estudos Geotécnicos e Sondagens")]
    assert _approval(_block(*rows)) == (
        "Aprovação: o Relatório de Atividades Preliminares e os Estudos de Tráfego encontram-se "
        "aprovados. A Documentação para Declaração de Utilidade Pública (DUP) encontra-se aprovada "
        "com ressalva;")


def test_approval_only_reserved():
    rows = [approved("3.1", "RD-103", SEC, "Projeto S", evaluation="Aprovado com ressalvas"),
            late("3.2", "RD-103", SEC, "Projeto T")]
    assert _approval(_block(*rows)) == "Aprovação: o Projeto S encontra-se aprovado com ressalva;"
    rows.append(approved("3.3", "RD-103", SEC, "Projeto U", evaluation="Aprovada com ressalva"))
    assert _approval(_block(*rows)) == ("Aprovação: o Projeto S e o Projeto U encontram-se "
                                        "aprovados com ressalva;")


def test_approval_without_reservation_is_unchanged():
    rows = [approved("2.1", "RD-103", PRI, "Projeto A"),
            approved("2.2", "RD-103", PRI, "Projeto B", evaluation="Aprovada"),
            late("2.3", "RD-103", PRI, "Projeto C")]
    block = _block(*rows)
    assert _approval(block) == "Aprovação: o Projeto A e o Projeto B encontram-se aprovados;"
    assert block.facts["groups"][0]["sets"]["approval_with_reservation"] == []
    assert "ressalva" not in "\n".join(block.lines)


def test_universal_approval_with_some_reserved_keeps_universal_and_adds_sentence():
    rows = [approved("1.1", "RD-103", EST, "Estudos A"),
            approved("1.2", "RD-103", EST, "Estudos B", evaluation="Aprovado com ressalva")]
    assert _status(_block(*rows))[-1] == ("Aprovação: Todas as disciplinas encontram-se aprovadas. "
                                          "Os Estudos B encontram-se aprovados com ressalva.")


def test_universal_approval_all_reserved():
    rows = [approved("1.1", "RD-103", EST, "Estudos A", evaluation="Aprovado com ressalva"),
            approved("1.2", "RD-103", EST, "Estudos B", evaluation="Aprovada com ressalva")]
    assert _status(_block(*rows))[-1] == ("Aprovação: Todas as disciplinas encontram-se aprovadas "
                                          "com ressalva.")


def test_oae_all_approved_with_reservation_is_enumerated():
    rows = [approved("4.1", "RD-103", OAE, "Projeto de Obra de Arte Especial (OAE)",
                     evaluation="Aprovado com ressalva"),
            approved("4.2", "RD-103", OAE, "Memoriais de Cálculo Estrutural e Quantitativo")]
    assert _approval(_block(*rows)) == (
        "Aprovação: os Memoriais de Cálculo Estrutural e Quantitativo encontram-se aprovados. O "
        "Projeto de Obra de Arte Especial (OAE) encontra-se aprovado com ressalva.")


def test_reservation_ignores_non_approved_evaluations():
    rows = [rejected("2.1", "RD-103", PRI, "Projeto A", "2026-09-30", evaluation="Reprovado com ressalva"),
            approved("2.2", "RD-103", PRI, "Projeto B")]
    block = _block(*rows)
    assert _approval(block) == "Aprovação: o Projeto B encontra-se aprovado;"


def test_reservation_qualifier_none_restores_previous_form():
    rules = replace(RULES, reservation_mode="none")
    rows = [approved("2.1", "RD-103", PRI, "Projeto A"),
            approved("2.2", "RD-103", PRI, "Projeto B", evaluation="Aprovado com ressalva"),
            late("2.3", "RD-103", PRI, "Projeto C")]
    block = _block(*rows, rules=rules)
    assert _approval(block) == "Aprovação: o Projeto A e o Projeto B encontram-se aprovados;"
    assert block.facts["groups"][0]["sets"]["approval_with_reservation"] == []


def test_invalid_reservation_mode_raises():
    spec = yaml.safe_load(t.SPEC_PATH.read_text(encoding="utf-8"))
    spec["templates"]["approval"]["reservation_qualifier"]["value"] = "generalizar"
    with pytest.raises(ValueError, match="reservation_qualifier"):
        t.load_rules(spec)
    spec["templates"]["approval"]["reservation_qualifier"]["value"] = "per_discipline"
    del spec["templates"]["approval"]["with_reservation"]
    with pytest.raises(ValueError, match="with_reservation"):
        t.load_rules(spec)


def test_reservation_templates_do_not_reintroduce_the_anomaly():
    """Os templates novos são varridos pelo validador (DATA_RULE_TEXTS) e não contêm o trecho
    observado de P2.2_APROVADOS_COM_RESSALVA_GENERALIZADO."""
    from prog_g2_report.model import DATA_RULE_TEXTS, anomaly_needles, emitted_texts

    path = "config/data_rules/p22_highway_block.yaml"
    assert path in DATA_RULE_TEXTS
    spec = yaml.safe_load(t.SPEC_PATH.read_text(encoding="utf-8"))
    texts = [text for _, text in emitted_texts({}, {path: spec})]
    reserved = spec["templates"]["approval"]["with_reservation"]
    for key in ("universal", "plural", "singular"):
        assert reserved[key] in texts
    catalog = t.REPO_ROOT / "data" / "catalog" / "anomalies.jsonl"
    anomalies = [json.loads(line) for line in catalog.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    needles = [n for c, n in anomaly_needles(anomalies)
               if c == "P2.2_APROVADOS_COM_RESSALVA_GENERALIZADO"]
    assert needles
    assert not any(n in text for n in needles for text in texts)


def test_reservation_anomaly_expected_is_the_sheet_fact_not_the_model_rule():
    """QA3-E: o expected_value descreve o fato da planilha por disciplina (sem citar a regra)."""
    catalog = t.REPO_ROOT / "data" / "catalog" / "anomalies.jsonl"
    rows = [json.loads(line) for line in catalog.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    found = [a for a in rows if a["component"] == "P2.2_APROVADOS_COM_RESSALVA_GENERALIZADO"]
    assert len(found) == 2
    for a in found:
        assert "reservation_qualifier" not in a["expected_value"]
        assert "Status (AVALIAÇÃO)" in a["expected_value"]
        assert "Geométrico e Interseções = Aprovado (sem ressalva)" in a["expected_value"]
        assert "Terraplenagem = Aprovado com ressalva" in a["expected_value"]
        assert a["should_learn_as_rule"] is False


def test_unknown_article_is_reported_as_warning():
    block = _block(late("1.1", "RD-103", EST, "Levantamento Especial"))
    assert block.facts["warnings"]


def test_unknown_group_raises():
    with pytest.raises(ValueError, match="GRUPO"):
        _block(late("9.1", "RD-103", "Grupo Inventado", "Projeto A"))


# ------------------------------------------------------------------ golden (-m golden)
def _evidence_root() -> Path | None:
    env = os.environ.get("PROG_EVIDENCE_ROOT")
    candidates = [Path(env)] if env else []
    candidates += list(Path(__file__).resolve().parents)
    for root in candidates:
        if (root / "tmp" / "agent_N" / "projetos_range.json").exists():
            return root
    return None


EVIDENCE = _evidence_root()
golden = pytest.mark.skipif(EVIDENCE is None, reason="extratos do agente N ausentes (tmp/agent_N)")

_GROUP_TEXT = {"Disciplinas da Fase de Estudos:": "EST", "Disciplinas do Viário Principal:": "PRI",
               "Disciplinas do Viário Secundário:": "SEC", "Obras de Arte Especiais (OAE):": "OAE"}
_LABELS = {"aceitação": "acceptance", "aprovação": "approval", "disciplinas em análise": "in_analysis",
           "disciplinas pendentes de aprovação": "pending_approval",
           "disciplinas não entregues": "not_delivered", "disciplinas em revisão": "pending_approval"}
# formas curtas do texto histórico → prefixo do nome da planilha (só para medir o relatório real)
_ALIASES = [
    (r"atividades preliminares", "relatório de atividades preliminares"),
    (r"tráfego", "estudos de tráfego"), (r"topográfic", "estudos topográficos"),
    (r"geológic", "estudos geológicos"), (r"diagnóstico ambiental", "diagnóstico ambiental prévio"),
    (r"utilidade pública|[(]dup", "documentação para declaração de utilidade pública"),
    (r"hidrológic", "estudos hidrológicos"), (r"geotécnic", "estudos geotécnicos"),
    (r"geométric", "projeto geométrico"), (r"terraplenagem", "projeto de terraplenagem"),
    (r"drenagem", "projeto de drenagem"), (r"pavimentação", "projeto de pavimentação"),
    (r"sinalização", "projeto de sinalização"), (r"desapropriação", "projeto de desapropriação"),
    (r"componente ambiental", "relatório de componente ambiental"),
    (r"paisagismo", "projeto de paisagismo"), (r"interferência", "projeto de interferência"),
    (r"orçamento", "orçamento e memoriais de cálculo"),
    (r"cronograma", "cronograma e planos de execução"),
    (r"obra de arte especial", "projeto de obra de arte especial"),
    (r"memoriais de cálculo estrutural", "memoriais de cálculo estrutural"),
]


def _n(s) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(s or ""))).strip().lower()


def _report_lines(report: int) -> dict[tuple[str, str], list[str]]:
    """Linhas de status do relatório real (extrato do agente J), por (rodovia, grupo)."""
    blocks = json.loads((EVIDENCE / "tmp" / "agent_J" / f"blocks_{report}.json").read_text(encoding="utf-8"))
    out: dict[tuple[str, str], list[str]] = {}
    road = group = None
    for b in blocks:
        text = b.get("text") or ""
        m = re.match(r"Referente ao acompanhamento de projeto executivo da Rodovia (RD-[0-9A-Z]+):", text)
        if m:
            road, group = m.group(1), None
            continue
        if road and b.get("numId") and b.get("ilvl") == "0":
            group = _GROUP_TEXT.get(text.strip().lstrip("• ").strip())
            out.setdefault((road, group), [])
        elif road and group and b.get("numId") and b.get("ilvl") == "1":
            out[(road, group)].append(text)
        elif road and group and text.strip() and not b.get("numId"):
            road = group = None
    return out


def _parse_report_line(text: str, universe: list[str]) -> tuple[str, list[str]]:
    label, _, body = text.partition(":")
    key = _LABELS.get(_n(label), "?" + _n(label))
    nb = _n(body)
    if re.search(r"(^| )todas( |$)", nb):
        return key, list(universe)
    if re.search(r"(^| )nenhuma[ ;.]|^nenhuma", nb):
        return key, []
    found = sorted((m.start(), canon) for pat, canon in _ALIASES for m in re.finditer(pat, nb))
    names: list[str] = []
    for _, canon in found:
        hit = next((a for a in universe if _n(a).startswith(canon)), canon + " [fora do grupo]")
        if hit not in names:
            names.append(hit)
    return key, names


def _golden_workbook(range_version: str, panel_version: str, ref: date) -> pj.ProjectsWorkbook:
    base = EVIDENCE / "tmp" / "agent_N"
    store = json.loads((base / "projetos_range.json").read_text(encoding="utf-8"))
    versions = json.loads((base / "projetos_versions.json").read_text(encoding="utf-8"))
    wb = pj.from_extract(store[range_version]["rows"], panel=versions[panel_version]["Painel de Controle"])
    # GED: log só de acréscimo (spec group_order.rule); a cópia local atual, se existir, fornece
    # as primeiras entregas — o renderizador só conta as com data ≤ referência.
    xlsx = EVIDENCE / "tmp" / "downloads" / "fontes_de_trabalho" / "03 - acompanhamento de projetos executivo.xlsx"
    if xlsx.exists():
        wb = replace(wb, ged=pj.load(xlsx).ged)
    return wb


def _measure(report: int, wb: pj.ProjectsWorkbook, ref: date) -> dict:
    blocks = {b.facts["road"]: b for b in t.build_highway_blocks(wb, ref, RULES)}
    actual = _report_lines(report)
    res = {"lines": 0, "set_ok": 0, "extra": [], "missing": [], "diff": [], "group_order_ok": 0,
           "roads": list(blocks)}
    for road, block in blocks.items():
        for g in block.facts["groups"]:
            gkey = g["group_key"]
            lines = actual.get((road, gkey))
            if lines is None:
                res["missing"].append((road, gkey, "grupo"))
                continue
            universe = g["sets"]["universe"]
            seen = set()
            for text in lines:
                key, names = _parse_report_line(text, universe)
                seen.add(key)
                res["lines"] += 1
                if key not in g["lines"]:
                    res["extra"].append((road, gkey, key, text))
                elif set(names) == set(g["sets"][key]):
                    res["set_ok"] += 1
                else:
                    res["diff"].append((road, gkey, key, names, g["sets"][key]))
            res["missing"] += [(road, gkey, k) for k in g["lines"] if k not in seen]
        report_groups = [k[1] for k in actual if k[0] == road]
        res["group_order_ok"] += report_groups == [g["group_key"] for g in block.facts["groups"]]
    return res


@pytest.mark.golden
@golden
def test_golden_no14_text_sets_v436():
    """nº 14 × v436 (spec meta.snapshots_used.no14_text_best_fit): ≥ 44/45 conjuntos."""
    wb = _golden_workbook("436.0", "v438.0", date(2026, 9, 7))
    res = _measure(14, wb, date(2026, 9, 7))
    print("nº14 v436:", {k: (v if isinstance(v, int) else len(v)) for k, v in res.items()}, res["diff"])
    assert res["roads"] == ["RD-103", "RD-102A", "RD-101", "RD-104"]
    assert res["lines"] == 45
    assert res["set_ok"] >= 44
    assert res["extra"] == [] and res["missing"] == []
    if wb.ged:
        assert res["group_order_ok"] == 4


@pytest.mark.golden
@golden
def test_golden_no13_text_sets_v328():
    """nº 13 × v328 (spec measurement.status_set_level.no13_v328): ≥ 38/40 nas linhas presentes."""
    wb = _golden_workbook("328.0", "v328.0", date(2026, 8, 13))
    res = _measure(13, wb, date(2026, 8, 13))
    print("nº13 v328:", {k: (v if isinstance(v, int) else len(v)) for k, v in res.items()}, res["diff"],
          res["extra"])
    assert res["lines"] == 40
    assert res["set_ok"] >= 38
    if wb.ged:
        assert res["group_order_ok"] == 4


def _reserved_in_sheet(wb: pj.ProjectsWorkbook) -> set[tuple[str, str]]:
    """(rodovia, disciplina) aprovadas com ressalva na planilha, fora das exclusões do texto."""
    return {(r.road, r.discipline) for r in wb.projects
            if t.has_reservation(r, RULES) and not t.is_excluded(r.discipline, RULES.text_exclusions)}


def _check_reservation_sentences(blocks) -> set[tuple[str, str]]:
    """Confere cada linha de Aprovação gerada: só a frase 'com ressalva' cita as disciplinas com
    ressalva, e ela cita todas. Devolve (rodovia, disciplina) qualificadas."""
    out = set()
    for block in blocks:
        for i, g in enumerate(block.facts["groups"]):
            line = _approval(block, i)
            reserved = g["sets"]["approval_with_reservation"]
            plain = [d for d in g["sets"]["approval"] if d not in reserved]
            sentences = line.split(RULES.reservation_separator)
            qualified = [s for s in sentences if "com ressalva" in s]
            assert len(qualified) == (1 if reserved else 0), line
            if reserved:
                assert all(d in qualified[0] for d in reserved), line
                assert not any(d in qualified[0] for d in plain), line
            out |= {(block.facts["road"], d) for d in reserved}
    return out


@pytest.mark.golden
@golden
def test_golden_no14_reservation_per_discipline_v438():
    """DEC-015 × v438 (snapshot do golden nº 14): a ressalva sai por disciplina, igual à planilha;
    a Terraplenagem da RD-104 sai 'com ressalva' e o Geométrico não."""
    wb = _golden_workbook("438.0", "v438.0", date(2026, 9, 7))
    blocks = t.build_highway_blocks(wb, date(2026, 9, 7), RULES)
    sheet_reserved = _reserved_in_sheet(wb)
    assert len(sheet_reserved) == 10
    assert _check_reservation_sentences(blocks) == sheet_reserved
    rd104 = next(b for b in blocks if b.facts["road"] == "RD-104")
    principal = [g["group_key"] for g in rd104.facts["groups"]].index("PRI")
    assert _approval(rd104, principal) == (
        "Aprovação: o Projeto Geométrico e Interseções encontra-se aprovado. O Projeto de "
        "Terraplenagem encontra-se aprovado com ressalva;")
    text = "\n".join(line for b in blocks for line in b.lines)
    assert ("o Projeto Geométrico e Interseções e o Projeto de Terraplenagem encontram-se "
            "aprovados com ressalva") not in text


@pytest.mark.golden
@golden
def test_golden_no13_reservation_per_discipline_v328():
    """DEC-015 × v328 (golden nº 13): as 13 aprovações com ressalva saem qualificadas."""
    wb = _golden_workbook("328.0", "v328.0", date(2026, 8, 13))
    blocks = t.build_highway_blocks(wb, date(2026, 8, 13), RULES)
    assert len(_reserved_in_sheet(wb)) == 13
    assert _check_reservation_sentences(blocks) == _reserved_in_sheet(wb)
    rd104 = next(b for b in blocks if b.facts["road"] == "RD-104")
    principal = [g["group_key"] for g in rd104.facts["groups"]].index("PRI")
    line = _approval(rd104, principal)
    assert "o Projeto Geométrico e Interseções encontra-se aprovado. " in line
    assert "O Projeto de Terraplenagem encontra-se aprovado com ressalva" in line
