"""Valores dos placeholders: extenso pt-BR, datas por extenso, número/mês do contexto."""

import re
from datetime import date

import pytest

from prog_g2_report.builder.blocks import blocks_by_id, load_blocks
from prog_g2_report.builder.context import ReportContext
from prog_g2_report.builder.values import (
    base_values,
    closing_values,
    input_value,
    long_date_pt,
    number_words_pt,
)
from prog_g2_report.model import load_model
from prog_g2_report.report_id import ReportRef
from g2_text_support import make_rc, row, usual_rows

MASCULINE = {
    0: "zero", 1: "um", 2: "dois", 14: "quatorze", 20: "vinte", 38: "trinta e oito",
    43: "quarenta e três", 100: "cem", 101: "cento e um", 122: "cento e vinte e dois",
    149: "cento e quarenta e nove", 150: "cento e cinquenta", 165: "cento e sessenta e cinco",
    201: "duzentos e um", 212: "duzentos e doze", 500: "quinhentos",
    999: "novecentos e noventa e nove",
}
FEMININE = {
    1: "uma", 2: "duas", 42: "quarenta e duas", 43: "quarenta e três", 51: "cinquenta e uma",
    101: "cento e uma", 201: "duzentas e uma", 222: "duzentas e vinte e duas", 100: "cem",
}


@pytest.mark.parametrize(("n", "words"), MASCULINE.items())
def test_number_words_masculine(n, words):
    assert number_words_pt(n, feminine=False) == words


@pytest.mark.parametrize(("n", "words"), FEMININE.items())
def test_number_words_feminine(n, words):
    assert number_words_pt(n, feminine=True) == words


@pytest.mark.parametrize("bad", [-1, 1000, 1.5, True])
def test_number_words_rejects_out_of_range(bad):
    with pytest.raises(ValueError):
        number_words_pt(bad)


def test_number_words_match_every_example_of_the_content_model():
    # ENC_P1.numerals: exemplos observados e gerados (páginas = feminino, anexos = masculino)
    enc = blocks_by_id(load_blocks())["ENC_P1"].raw["numerals"]
    for example in enc["examples"]:
        for kind, feminine in (("pages", True), ("annexes", False)):
            number, words = re.match(r"^(\d+) \((.+)\)$", example[kind]).groups()
            assert number_words_pt(int(number), feminine) == words
    for key, words in enc["more_examples_generated"].items():
        kind, number = key.split()
        assert number_words_pt(int(number), kind == "páginas") == words


def test_long_date_matches_the_observed_signature_dates():
    observed = blocks_by_id(load_blocks())["ENC_DATE"].raw["observed"]
    assert f"Capital, {long_date_pt(date(2026, 6, 8))}" == observed["Maio/2026"]
    assert f"Capital, {long_date_pt(date(2026, 9, 9))}" == observed["Agosto/2026"]
    assert long_date_pt(date(2026, 3, 1)) == "01 de Março de 2026"


@pytest.mark.parametrize(("number", "ref", "label"),
                         [(14, "2026-08", "Agosto/2026"), (15, "2026-09", "Setembro/2026")])
def test_base_values_come_from_the_context(number, ref, label):
    report = ReportContext(ReportRef(number, ref), issue_date=date(2026, 9, 8),
                           signature_date=date(2026, 9, 9))
    model = load_model()
    values = base_values(report, model)
    assert values["report_number"] == str(number)
    assert values["month_label"] == label
    assert values["contract_ref"] == model["editorial_defaults"]["contract_ref"]["value"]
    assert values["issue_date_long"] == "08 de Setembro de 2026"
    assert values["signature_date_long"] == "09 de Setembro de 2026"


def test_report_number_has_two_digits_and_signature_is_optional():
    report = ReportContext(ReportRef(9, "2026-03"), issue_date=date(2026, 4, 2))
    values = base_values(report, load_model())
    assert values["report_number"] == "09"
    assert "signature_date_long" not in values


def test_closing_values_count_only_delivered_rows_of_the_report(tmp_path):
    rows = [*usual_rows(14), row("2.2", "PA-900.1", number=15)]
    rc = make_rc(rows=rows, page_count=43, tmp=tmp_path)
    values = closing_values(rc)
    assert values["page_count"] == "43"
    assert values["page_count_words"] == "quarenta e três"
    # 4 linhas do nº 14, uma 'Em elaboração' (fora do índice, DEC-012), uma do nº 15
    assert values["annex_count"] == "3"
    assert values["annex_count_words"] == "três"


def test_closing_values_accept_explicit_annex_count_and_unknown_page_count(tmp_path):
    rc = make_rc(page_count=None, tmp=tmp_path)
    rc.data["annex_count"] = 122
    values = closing_values(rc)
    assert "page_count" not in values
    assert values["annex_count_words"] == "cento e vinte e dois"


def test_input_value_requires_declared_input(tmp_path):
    rc = make_rc(inputs={"signatory_name": "  "}, tmp=tmp_path)
    assert input_value(rc, "signatory_name") is None
    with pytest.raises(KeyError):
        input_value(rc, "undeclared_input")
