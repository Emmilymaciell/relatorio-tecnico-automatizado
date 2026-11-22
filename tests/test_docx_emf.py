"""Inserção OPC de EMF inline (DEC-010 §5) com EMF sintético; sem Word nem Excel."""

import zipfile

import pytest
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT

from prog_g2_report.render.docx_emf import (
    EMU_PER_CM,
    add_emf_picture,
    emf_bounds,
    emf_display_height_cm,
)
from emf_synth import make_emf

WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"


def test_emf_bounds_reads_header():
    h = emf_bounds(make_emf())
    assert (h.left, h.top, h.right, h.bottom) == (0, 1, 1232, 280)
    assert h.frame_cm == (22.091, 5.048)
    assert h.device_px == (1920, 1080) and h.device_mm == (344, 194)


@pytest.mark.parametrize("junk", [b"", b"\x00" * 120, b"\x01\x00\x00\x00" + b"\x00" * 120])
def test_emf_bounds_rejects_non_emf(junk):
    with pytest.raises(ValueError):
        emf_bounds(junk)


def test_aspect_modes():
    h = emf_bounds(make_emf())
    assert h.aspect("bounds") == pytest.approx(280 / 1233)
    # frame em pixels do dispositivo de referência (px/mm diferentes em x e y)
    assert h.aspect("frame") == pytest.approx((5048 * 1080 / 194) / (22091 * 1920 / 344))
    with pytest.raises(ValueError):
        h.aspect("other")


@pytest.mark.parametrize(
    ("bounds", "frame", "hist_cx", "hist_cy"),
    [  # wp:extent do DOCX histórico do Relatório G2 nº 14 (números, não o documento)
        ((0, 1, 1232, 280), (0, 0, 22091, 5048), 6301105, 1434465),
        ((0, 1, 1232, 1200), (0, 0, 22091, 21574), 6301105, 6135370),
        ((0, 1, 1253, 1614), (0, 0, 22091, 29010), 6301105, 8251190),  # texto vaza à direita
        ((0, 1, 1253, 1936), (0, 0, 22091, 34794), 6006465, 9431655),
    ],
)
def test_frame_aspect_matches_historical_extent(bounds, frame, hist_cx, hist_cy):
    h = emf_bounds(make_emf(bounds, frame))
    assert h.aspect("frame") == pytest.approx(hist_cy / hist_cx, rel=2e-3)


def test_bounds_aspect_misses_when_text_overflows():
    h = emf_bounds(make_emf((0, 1, 1253, 1614), (0, 0, 22091, 29010)))
    assert abs(h.aspect("bounds") / (8251190 / 6301105) - 1) > 0.01


def test_add_emf_picture_part_rel_extent_and_reopen(tmp_path):
    emf_a = make_emf()
    emf_b = make_emf((0, 1, 1232, 1200), (0, 0, 22091, 21574))
    doc = Document()
    add_emf_picture(doc.add_paragraph(), emf_a, 17.5)
    add_emf_picture(doc.add_paragraph(), emf_b, 17.5)
    out = tmp_path / "emf.docx"
    doc.save(out)

    with zipfile.ZipFile(out) as z:
        content_types = z.read("[Content_Types].xml").decode("utf-8")
        media = sorted(n for n in z.namelist() if n.startswith("word/media/"))
    assert "image/x-emf" in content_types
    assert media == ["word/media/emf1.emf", "word/media/emf2.emf"]

    reopened = Document(out)
    parts = [r.target_part for r in reopened.part.rels.values() if r.reltype == RT.IMAGE]
    assert sorted(p.content_type for p in parts) == ["image/x-emf", "image/x-emf"]
    assert sorted(p.blob for p in parts) == sorted([emf_a, emf_b])

    extents = reopened.element.body.findall(f".//{WP}inline/{WP}extent")
    cx = round(17.5 * EMU_PER_CM)
    assert [int(e.get("cx")) for e in extents] == [cx, cx]
    expected = [round(cx * emf_bounds(e).aspect("frame")) for e in (emf_a, emf_b)]
    assert [int(e.get("cy")) for e in extents] == expected
    doc_pr_ids = [d.get("id") for d in reopened.element.body.iter(f"{WP}docPr")]
    assert len(set(doc_pr_ids)) == 2


def test_add_emf_picture_bounds_mode_and_width():
    doc = Document()
    emf = make_emf()
    add_emf_picture(doc.add_paragraph(), emf, 10.0, aspect="bounds")
    extent = doc.element.body.find(f".//{WP}extent")
    assert int(extent.get("cx")) == 3_600_000
    assert int(extent.get("cy")) == round(3_600_000 * 280 / 1233)
    with pytest.raises(ValueError):
        add_emf_picture(doc.add_paragraph(), emf, 0)


def test_display_height_cm():
    emf = make_emf()
    assert emf_display_height_cm(emf, 17.5) == pytest.approx(17.5 * emf_bounds(emf).aspect(), abs=1e-5)


def test_emf_text_runs_follow_the_selected_font():
    from prog_g2_report.render.docx_emf import emf_text_runs
    from emf_synth import font_record, make_text_emf, select_record, text_record

    emf = make_text_emf([
        font_record(1, 700), font_record(2, 400, "Arial"),
        select_record(1), text_record("Documento", 10, 5),
        select_record(2), text_record("NT-725.1", 10, 40), text_record("Nota Técnica", 80, 40),
        select_record(0x8000000D),                       # fonte de estoque: peso desconhecido
        text_record("x"),
    ])
    runs = emf_text_runs(emf)
    assert [(r.text, r.bold) for r in runs] == [("Documento", True), ("NT-725.1", False),
                                                 ("Nota Técnica", False), ("x", False)]
    assert runs[0].face == "Arial Nova Cond" and runs[1].face == "Arial"
    assert (runs[2].x, runs[2].y) == (80, 40) and runs[3].weight == 0
