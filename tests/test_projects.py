"""Leitor da planilha de projetos: cabeçalho por conteúdo, todas as linhas, normalização."""

from __future__ import annotations

import io
from datetime import date, datetime

import pytest

from _p22_synthetic import (
    EST,
    PRI,
    SEC,
    approved,
    ged,
    ged_sheet,
    in_analysis,
    late,
    panel,
    project,
    sheet,
)
from prog_g2_report.sources import projects as pj


# ------------------------------------------------------------------ normalização
@pytest.mark.parametrize("raw", ["RD-102 A", "RD-102 A", " rd-102a ", "RD - 102 A", "RD-102A"])
def test_road_normalization_removes_spaces_and_nbsp(raw):
    assert pj.normalize_road(raw) == "RD-102A"


def test_road_rd103_0_is_not_merged_with_rd103():
    assert pj.normalize_road("RD-103-0") == "RD-103-0"
    assert pj.normalize_road("RD-103") == "RD-103"


@pytest.mark.parametrize("raw", ["Sim", "sim", "SIm", "Sim ", " SIM "])
def test_acceptance_normalization(raw):
    assert pj.normalize_acceptance(raw) == "sim"


def test_order_key_is_numeric():
    assert pj.order_key("3.10") > pj.order_key("3.9")
    assert sorted(["3.10", "3.2", "1.1", "4.1", "3.9"], key=pj.order_key) == [
        "1.1", "3.2", "3.9", "3.10", "4.1"]


def test_iso_dates_from_extract_are_parsed():
    assert pj.as_date("2026-08-31") == date(2026, 8, 31)
    assert pj.as_date("2026-08-31 00:00:00") == date(2026, 8, 31)
    assert pj.as_date(datetime(2026, 8, 31, 10)) == date(2026, 8, 31)
    assert pj.as_date("Aguardando previsão") is None


# ------------------------------------------------------------------ aba Projetos
def test_header_found_by_content_after_title_rows():
    rows = [["Programa | título"], [], *sheet(approved("1.1", "RD-103", EST, "Estudos de Tráfego"))]
    parsed = pj.parse_projects(rows)
    assert len(parsed) == 1
    assert parsed[0].physical_row == 4
    assert parsed[0].discipline == "Estudos de Tráfego"


def test_header_missing_raises():
    with pytest.raises(ValueError, match="cabeçalho"):
        pj.parse_projects([["sem", "cabeçalho"], [1, 2]])


def test_rows_without_road_are_ignored_and_discipline_trimmed():
    rows = sheet(
        approved("1.1", "RD-102 A", EST, "  Estudos   de Tráfego "),
        [None] * 24,
    )
    parsed = pj.parse_projects(rows)
    assert [(r.road, r.road_raw, r.discipline) for r in parsed] == [
        ("RD-102A", "RD-102 A", "Estudos de Tráfego")]


def test_revision_delivery_is_date_or_text():
    rows = sheet(
        project("3.1", "RD-103", SEC, "Projeto A", revision_delivery="2026-09-08"),
        project("3.2", "RD-103", SEC, "Projeto B", revision_delivery="Aguardando previsão"),
        project("3.3", "RD-103", SEC, "Projeto C", revision_delivery=datetime(2026, 9, 1)),
        project("3.4", "RD-103", SEC, "Projeto D"),
    )
    values = [r.revision_delivery for r in pj.parse_projects(rows)]
    assert values == [date(2026, 9, 8), "Aguardando previsão", date(2026, 9, 1), None]


def test_zero_from_ged_formula_is_blank():
    # fórmula LET(v, INDEX(GED!...), IF(OR(v="", v=0), "", v)): 0 é vazio
    rows = sheet(project("1.1", "RD-103", EST, "Estudos X", analysis=0, evaluation=0, accepted=0))
    row = pj.parse_projects(rows)[0]
    assert row.ged_analysis_start is None
    assert row.evaluation_raw == ""
    assert row.accepted == ""


# ------------------------------------------------------------------ SITUAÇÃO recalculada
def test_situation_recalculated_with_reference_date_not_cache():
    rows = sheet(
        late("3.1", "RD-103", SEC, "Projeto A", forecast=date(2026, 9, 5), situation_cached="No prazo"),
    )
    row = pj.parse_projects(rows)[0]
    assert row.situation_cached == "No prazo"
    assert row.situation(date(2026, 9, 7)) == "Atrasado"
    assert row.situation(date(2026, 9, 5)) == "No prazo"      # E >= F: 'Faltam 0 dias'
    assert row.situation(date(2026, 9, 1)) == "No prazo"


def test_situation_formula_branches():
    ref = date(2026, 9, 7)
    rows = pj.parse_projects(sheet(
        project("1.1", "RD-103", EST, "Sem previsão", forecast=None),
        approved("1.2", "RD-103", EST, "Avaliada"),
        in_analysis("1.3", "RD-103", EST, "Em análise"),
        project("1.4", "RD-103", EST, "Recebida", received=date(2026, 9, 1)),
        late("1.5", "RD-103", EST, "Atrasada"),
    ))
    assert [r.situation(ref) for r in rows] == [
        "Aguardando previsão", "Analisada", "Em análise", "Aguardando início da análise", "Atrasado"]


# ------------------------------------------------------------------ GED e Painel
def test_ged_parse_keeps_rd103_0_separate():
    rows = ged_sheet(
        ged("RD-103", EST, "Estudos X", datetime(2026, 1, 2)),
        ged("RD-103-0", EST, "Estudos X", datetime(2025, 1, 2)),
        ged("RD-102 A", PRI, "Projeto Y", "data digitada errada"),
        [None] * 9,
    )
    parsed = pj.parse_ged(rows)
    assert [(g.road, g.received_date) for g in parsed] == [
        ("RD-103", date(2026, 1, 2)), ("RD-103-0", date(2025, 1, 2)), ("RD-102A", None)]


def test_panel_road_order_and_labels():
    order, labels = pj.parse_panel(panel("RD-103 - DELTA", "RD-102A - CLX / TRAFEX", "RD-101 - CSG"))
    assert order == ("RD-103", "RD-102A", "RD-101")
    assert labels["RD-102A"] == "RD-102A - CLX / TRAFEX"


def test_panel_without_road_row():
    assert pj.parse_panel([["nada"], [None]]) == ((), {})


# ------------------------------------------------------------------ entradas
def test_from_extract_versions_format_keeps_physical_rows():
    projetos = sheet(approved("1.1", "RD-103", EST, "Estudos X"), approved("1.2", "RD-103", EST, "Estudos Y"))
    extract = {
        "Projetos": [{"row": n, "values": v} for n, v in zip((1, 5, 9), projetos, strict=True)],
        "Painel de Controle": [{"row": i + 2, "values": v} for i, v in enumerate(panel("RD-103 - X"))],
    }
    wb = pj.from_extract(extract)
    assert [r.physical_row for r in wb.projects] == [5, 9]
    assert wb.road_order == ("RD-103",)
    assert wb.ged == ()


def test_from_extract_range_format_with_iso_dates_and_external_panel():
    projetos = sheet(approved("1.1", "RD-102 A", EST, "Estudos X", received="2026-03-01",
                              forecast="2026-02-01"))
    wb = pj.from_extract(projetos, panel=panel("RD-102A - Y"), ged=ged_sheet(
        ged("RD-102A", EST, "Estudos X", "2026-03-01")))
    row = wb.projects[0]
    assert (row.forecast_date, row.received_date) == (date(2026, 2, 1), date(2026, 3, 1))
    assert wb.ged[0].received_date == date(2026, 3, 1)
    assert wb.roads() == ["RD-102A"]


def _xlsx_bytes(hidden_row: int) -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Projetos"
    for row in sheet(
        approved("1.1", "RD-102 A", EST, "Estudos X", received=datetime(2026, 3, 1)),
        approved("1.2", "RD-102 A", EST, "Estudos Y", received=datetime(2026, 3, 1)),
        late("1.3", "RD-103", EST, "Estudos Z", forecast=datetime(2026, 5, 1)),
    ):
        ws.append(row)
    ws.auto_filter.ref = "A1:X4"
    ws.row_dimensions[hidden_row].hidden = True
    gws = wb.create_sheet("GED")
    for row in ged_sheet(ged("RD-102A", EST, "Estudos X", datetime(2026, 3, 1))):
        gws.append(row)
    pws = wb.create_sheet("Painel de Controle")
    for row in panel("RD-103 - A", "RD-102A - B"):
        pws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_load_from_bytes_reads_hidden_rows_and_ignores_autofilter():
    wb = pj.load(_xlsx_bytes(hidden_row=3))
    assert [r.discipline for r in wb.projects] == ["Estudos X", "Estudos Y", "Estudos Z"]
    assert wb.road_order == ("RD-103", "RD-102A")
    assert len(wb.ged) == 1
    assert wb.projects[2].situation(date(2026, 9, 7)) == "Atrasado"


def test_load_from_path(tmp_path):
    path = tmp_path / "sintetico.xlsx"
    path.write_bytes(_xlsx_bytes(hidden_row=2))
    assert len(pj.load(path).projects) == 3
