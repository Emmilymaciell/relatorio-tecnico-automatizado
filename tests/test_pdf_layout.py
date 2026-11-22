"""Posição de parágrafos no PDF de uma passada (DEC-010 §3, 1º recorte): PDF sintético."""

import pytest

pymupdf = pytest.importorskip("pymupdf")

from prog_g2_report.render.pdf_layout import (  # noqa: E402
    PT_PER_CM,
    locate_paragraphs,
    normalize_for_match,
)

LEAD = "A relação dos produtos desenvolvidos no período se encontra na tabela apresentada a seguir."
BAND = {"body_top_cm": 2.0, "body_bottom_cm": 28.2}


def _pdf(path, pages):
    """pages = [[(y_cm da linha de base, texto), ...], ...]"""
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page(width=21 * PT_PER_CM, height=29.7 * PT_PER_CM)
        for y_cm, text in lines:
            page.insert_text((2 * PT_PER_CM, y_cm * PT_PER_CM), text, fontsize=11)
    doc.save(str(path))
    doc.close()
    return path


def test_normalize_ignores_spaces_and_ligatures():
    assert normalize_for_match("a  ﬁ b\n c") == "afibc"


def test_finds_each_occurrence_in_order_and_skips_header(tmp_path):
    pdf = _pdf(tmp_path / "x.pdf", [
        [(1.3, LEAD), (5.0, "Outro parágrafo qualquer."), (10.0, LEAD)],     # 1.3 = cabeçalho
        [(4.0, "A relação dos produtos desenvolvidos no período"),
         (4.6, "se encontra na tabela apresentada a seguir.")],
    ])
    first, second, third = locate_paragraphs(pdf, [(LEAD, 0), (LEAD, 1), (LEAD, 2)], **BAND)
    assert first.page == 1 and 9.4 < first.bottom_cm < 10.4
    assert second.page == 2 and second.lines == 2
    assert 4.0 < second.bottom_cm < 5.0 and second.top_cm < 4.0
    assert second.height_cm > first.height_cm
    assert third is None                                   # só há duas no corpo


def test_missing_text_is_none(tmp_path):
    pdf = _pdf(tmp_path / "y.pdf", [[(5.0, "nada aqui")]])
    assert locate_paragraphs(pdf, [(LEAD, 0), ("", 0)], **BAND) == [None, None]
