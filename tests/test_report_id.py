"""Vocabulario canonico: numero + mes de referencia, e o rotulo 'Relatório G2'."""

from __future__ import annotations

import pytest

from prog_g2_report.report_id import (
    ReportRef,
    format_report,
    month_label,
    parse_monthly_folder,
    parse_report_filename,
    reference_month,
)


def test_reference_month_is_iso_year_month():
    assert reference_month(2026, 8) == "2026-08"
    assert reference_month(2025, 7) == "2025-07"


@pytest.mark.parametrize(
    "ref, expected",
    [("2026-08", "Agosto/2026"), ("2026-03", "Março/2026"), ("2025-07", "Julho/2025")],
)
def test_month_label_is_portuguese(ref, expected):
    assert month_label(ref) == expected


def test_format_report_is_the_canonical_label():
    assert format_report(14, "2026-08") == "Relatório G2 nº 14 — Agosto/2026"
    assert format_report(11, "2026-05") == "Relatório G2 nº 11 — Maio/2026"
    assert format_report(14) == "Relatório G2 nº 14"
    assert format_report(None) == "Relatório G2"


def test_label_never_uses_the_rm_abbreviation():
    for number, ref in [(1, "2025-07"), (14, "2026-08")]:
        assert "RM" not in format_report(number, ref)


@pytest.mark.parametrize(
    "folder, number, ref",
    [
        ("14. Agosto 2026", 14, "2026-08"),
        ("09. Março 2026", 9, "2026-03"),
        ("01. Julho 2025", 1, "2025-07"),
        ("7. Janeiro 2026", 7, "2026-01"),
    ],
)
def test_parse_monthly_folder(folder, number, ref):
    parsed = parse_monthly_folder(folder)
    assert parsed == ReportRef(number, ref)


@pytest.mark.parametrize("folder", ["00. Modelos e Templates", "Para prestação de contas", "G2"])
def test_parse_monthly_folder_rejects_non_monthly(folder):
    assert parse_monthly_folder(folder) is None


@pytest.mark.parametrize(
    "filename, number, ref",
    [
        ("Programa - Relatório Grupo 2 - Relatório Mensal N°14 - 08 2026.docx", 14, "2026-08"),
        ("Programa - Relatório Grupo 2 - Relatório Mensal N°01 - 07 2025.docx", 1, "2025-07"),
        ("PROG_-_Relatorio_Grupo_2_-_Relatorio_Mensal_NB012_-_06_2026_assinado.pdf", 12, "2026-06"),
        ("Programa - Relatório Grupo 2 - Relatório Mensal N°09 - 03 2026 - sem anexos.pdf", 9, "2026-03"),
    ],
)
def test_parse_report_filename(filename, number, ref):
    parsed = parse_report_filename(filename)
    assert parsed == ReportRef(number, ref)


def test_parse_report_filename_ignores_unrelated_files():
    assert parse_report_filename("00_ Lista mestre.xlsx") is None
    assert parse_report_filename("MA-001.1 - Memória de Ata - RD103.docx") is None


def test_report_ref_str_and_dict():
    ref = ReportRef(14, "2026-08")
    assert str(ref) == "Relatório G2 nº 14 — Agosto/2026"
    assert ref.as_dict() == {"report_number": 14, "reference_month": "2026-08"}
