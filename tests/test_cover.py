"""Capa (cover.py, DEC-011 b'): fundo ancorado com sangria + textos do contexto em quadros.

Fixtures sintéticas: foto e logos gerados aqui (nenhum asset corporativo). Os números e datas
de teste são deliberadamente diferentes do nº 14.
"""

from __future__ import annotations

import copy
import faulthandler
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("docx")
pytest.importorskip("pymupdf")
Image = pytest.importorskip("PIL.Image")
from lxml import etree  # noqa: E402

from prog_g2_report.builder import cover as cv  # noqa: E402
from prog_g2_report.builder import foundation as fd  # noqa: E402
from prog_g2_report.builder.context import (  # noqa: E402
    RenderContext,
    ReportContext,
    SourceManifest,
)
from prog_g2_report.report_id import ReportRef  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
NS = {"w": W, "wp": WP}

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
       '<rect x="2" y="2" width="{iw}" height="{ih}" fill="#ffffff"/></svg>')


def w(attr: str) -> str:
    return f"{{{W}}}{attr}"


@pytest.fixture(scope="module")
def cfg():
    base = copy.deepcopy(fd.load_base_config())
    base["cover"]["background"]["dpi"] = 30        # rápido; a regra não depende do DPI
    return base


@pytest.fixture(scope="module")
def assets(tmp_path_factory, cfg):
    """Assets sintéticos com os nomes de arquivo que o modelo espera."""
    root = tmp_path_factory.mktemp("assets")
    files = {layer["kind"]: [] for layer in cfg["cover"]["background"]["layers"]}
    for layer in cfg["cover"]["background"]["layers"]:
        files[layer["kind"]].append(layer.get("file"))
    photo = Image.new("RGB", (371, 247))
    for x in range(371):
        for y in range(0, 247, 13):
            photo.putpixel((x, y), (x % 255, (x * 3) % 255, 90))
    photo.save(root / files["photo"][0], format="JPEG")
    for i, name in enumerate(files["svg"]):
        (root / name).write_text(SVG.format(w=100 + 10 * i, h=60, iw=90, ih=50), encoding="utf-8")
    return root


def make_report(number: int, issue: date, month: str) -> ReportContext:
    return ReportContext(ReportRef(number, month), issue_date=issue)


def build(cfg, assets, work: Path, report: ReportContext) -> tuple[Path, object]:
    doc = fd.new_document(cfg)
    ctx = RenderContext(report=report, model={}, sources=SourceManifest(), document=doc,
                        assets_dir=assets, work_dir=work, data={"ooxml_base": cfg})
    result = cv.build_cover(ctx)
    fd.add_toc(doc, cfg)
    fd.add_heading(doc, "Apresentação", 1, cfg)
    path = work / "cover.docx"
    doc.save(path)
    return path, result


def document_xml(path: Path):
    with zipfile.ZipFile(path) as z:
        return etree.fromstring(z.read("word/document.xml"))


# ------------------------------------------------------------------------------ textos
@pytest.mark.parametrize(
    ("issue", "expected"),
    [(date(2027, 3, 5), "05 de Março de 2027"), (date(2028, 12, 31), "31 de Dezembro de 2028")],
)
def test_issue_date_format_pt_br(cfg, issue, expected):
    template = next(t for t in cfg["cover"]["texts"] if t["id"] == "issue_date")["template"]
    assert cv.format_issue_date(issue, template) == expected


CASES = [
    (7, date(2027, 3, 5), "2027-02", "Relatório Mensal N° 7", "05 de Março de 2027"),
    (23, date(2028, 1, 9), "2027-12", "Relatório Mensal N° 23", "09 de Janeiro de 2028"),
]


@pytest.mark.parametrize(("number", "issue", "month", "number_text", "date_text"), CASES)
def test_cover_variable_fields_come_from_context(cfg, assets, tmp_path, number, issue, month,
                                                 number_text, date_text):
    path, result = build(cfg, assets, tmp_path, make_report(number, issue, month))
    texts = ["".join(p.itertext()) for p in document_xml(path).iter(w("p"))]
    assert number_text in texts
    assert date_text in texts
    assert not any("N° 14" in t or "Setembro de 2026" in t for t in texts)
    assert result.status == "OK" and result.component_id == "COVER"
    assert result.facts["texts"]["report_number"] == number_text
    assert result.facts["texts"]["issue_date"] == date_text


def test_cover_fixed_title_and_fonts(cfg, assets, tmp_path):
    path, _ = build(cfg, assets, tmp_path, make_report(9, date(2027, 1, 4), "2026-12"))
    root = document_xml(path)
    framed = [p for p in root.iter(w("p")) if p.find("w:pPr/w:framePr", NS) is not None]
    assert len(framed) == len(cfg["cover"]["texts"])
    by_text = {"".join(p.itertext()): p for p in framed}
    title = by_text["RELATÓRIO PROGRAMAGrupo 2 - Gestão de Engenharia e Socioambiental"]
    assert title.find(".//w:br", NS) is not None
    fonts = {t: p.find("w:r/w:rPr/w:rFonts", NS).get(w("ascii")) for t, p in by_text.items()}
    assert fonts["Relatório Mensal N° 9"] == "Arial Nova Cond"
    assert fonts["04 de Janeiro de 2027"] == "Arial Nova Cond Light"
    for p in framed:
        frame = p.find("w:pPr/w:framePr", NS)
        assert frame.get(w("hAnchor")) == "page" and frame.get(w("vAnchor")) == "page"
        assert p.find("w:r/w:rPr/w:color", NS).get(w("val")) == "FFFFFF"
    ys = [int(p.find("w:pPr/w:framePr", NS).get(w("y"))) for p in framed]
    assert ys == sorted(ys)                         # título, número, data de cima para baixo
    assert all(0 < y < 16838 for y in ys)


def test_background_anchored_behind_text_with_bleed(cfg, assets, tmp_path):
    path, _ = build(cfg, assets, tmp_path, make_report(9, date(2027, 1, 4), "2026-12"))
    body = document_xml(path).find("w:body", NS)
    first = body.find("w:p", NS)
    anchor = first.find(".//wp:anchor", NS)
    assert anchor is not None and anchor.get("behindDoc") == "1"
    assert first.find(".//wp:inline", NS) is None
    bleed = cfg["cover"]["bleed_twips"] * 635
    page = fd.section_config(cfg, 0)["pgSz"]
    for axis in ("positionH", "positionV"):
        node = anchor.find(f"wp:{axis}", NS)
        assert node.get("relativeFrom") == "page"
        assert int(node.find("wp:posOffset", NS).text) == -bleed
    extent = anchor.find("wp:extent", NS)
    assert int(extent.get("cx")) == page["w"] * 635 + 2 * bleed
    assert int(extent.get("cy")) == page["h"] * 635 + 2 * bleed
    assert anchor.find("wp:wrapNone", NS) is not None
    breaks = [br for br in body.iter(w("br")) if br.get(w("type")) == "page"]
    assert len(breaks) == 1                         # capa termina com quebra de página


def test_cover_page_has_no_header_or_footer(cfg, assets, tmp_path):
    path, _ = build(cfg, assets, tmp_path, make_report(9, date(2027, 1, 4), "2026-12"))
    sect = document_xml(path).find("w:body/w:sectPr", NS)
    assert sect.find("w:titlePg", NS) is not None
    types = {r.get(w("type")) for r in sect if r.tag in (w("headerReference"), w("footerReference"))}
    assert types == {"default"}


def test_composite_is_deterministic_and_bleeds(cfg, assets, tmp_path):
    mapping = cv.slide_mapping(cfg)
    a = cv.compose_background(assets, cfg["cover"], tmp_path / "a.png", mapping)
    b = cv.compose_background(assets, cfg["cover"], tmp_path / "b.png", mapping)
    assert cv.sha1_of(a) == cv.sha1_of(b)
    dpi = cfg["cover"]["background"]["dpi"]
    slide_w, slide_h = cfg["cover"]["slide_size_emu"]
    sw, sh = round(slide_w / 914400 * dpi), round(slide_h / 914400 * dpi)
    with Image.open(a) as im:
        width, height = im.size
        assert width > sw and height > sh            # bordas estendidas pela sangria
        r, g, bl = im.getpixel((width // 2, height // 2))
        assert (r, g, bl) != (255, 255, 255)        # véu accent1 sobre a foto


def test_mapping_stretches_slide_to_page(cfg):
    mapping = cv.slide_mapping(cfg)
    slide_w, slide_h = cfg["cover"]["slide_size_emu"]
    page = fd.section_config(cfg, 0)["pgSz"]
    assert mapping.x(slide_w) == page["w"]
    assert mapping.y(slide_h) == page["h"]
    assert round(mapping.sx, 3) == 1.102 and round(mapping.sy, 3) == 1.079


def test_registered_composite_is_preferred_only_with_current_layers(cfg, assets, tmp_path):
    from PIL import PngImagePlugin

    registered = tmp_path / "assets"
    registered.mkdir()
    for src in assets.iterdir():
        (registered / src.name).write_bytes(src.read_bytes())
    name = cfg["cover"]["background"]["file"]
    info = PngImagePlugin.PngInfo()
    info.add_text(cv.SIGNATURE_KEY, cv.layers_signature(cfg["cover"], cv.slide_mapping(cfg)))
    Image.new("RGB", (20, 30), (1, 2, 3)).save(registered / name, pnginfo=info)
    assert cv.resolve_background(registered, cfg, tmp_path / "work") == registered / name
    # fundo pré-composto antigo (sem assinatura): recomposto no work_dir com as camadas atuais
    Image.new("RGB", (20, 30), (1, 2, 3)).save(registered / name)
    fresh = cv.resolve_background(registered, cfg, tmp_path / "work")
    assert fresh == tmp_path / "work" / name
    with Image.open(fresh) as im:
        assert im.text[cv.SIGNATURE_KEY] == cv.layers_signature(cfg["cover"], cv.slide_mapping(cfg))


def test_second_rule_has_the_first_rule_width(cfg):
    """QA2-D (c): a prévia publicada desenha os dois filetes da capa com a mesma espessura."""
    rules = [layer for layer in cfg["cover"]["background"]["layers"] if layer["kind"] == "hline"]
    assert len(rules) == 2 and rules[0]["width"] == rules[1]["width"]


def test_page_size_overrides_slide_scale(cfg, assets, tmp_path):
    path, _ = build(cfg, assets, tmp_path, make_report(9, date(2027, 1, 4), "2026-12"))
    root = document_xml(path)
    framed = [p for p in root.iter(w("p")) if p.find("w:pPr/w:framePr", NS) is not None]
    sizes = {"".join(p.itertext()): int(p.find("w:r/w:rPr/w:sz", NS).get(w("val")))
             for p in framed}
    specs = {s["id"]: s for s in cfg["cover"]["texts"]}
    title = sizes["RELATÓRIO PROGRAMAGrupo 2 - Gestão de Engenharia e Socioambiental"]
    assert title == round(specs["title"]["page_size_pt"] * 2)
    assert sizes["Relatório Mensal N° 9"] == round(specs["report_number"]["page_size_pt"] * 2)
    if specs["issue_date"].get("page_size_pt") is None:      # sem medida: escala do slide
        mapping = cv.slide_mapping(cfg)
        expected = round(specs["issue_date"]["size_pt"] * mapping.sy * 2)
        assert sizes["04 de Janeiro de 2027"] == expected


def test_cover_must_be_first_content(cfg, tmp_path):
    doc = fd.new_document(cfg)
    doc.add_paragraph("antes")
    with pytest.raises(ValueError):
        cv.add_cover(doc, make_report(1, date(2027, 1, 1), "2026-12"), cfg, tmp_path / "x.png")


def test_build_cover_requires_base_config(assets, tmp_path, cfg):
    ctx = RenderContext(report=make_report(2, date(2027, 1, 1), "2026-12"), model={},
                        sources=SourceManifest(), document=fd.new_document(cfg),
                        assets_dir=assets, work_dir=tmp_path)
    with pytest.raises(KeyError):
        cv.build_cover(ctx)


# ------------------------------------------------------------------------------ Word
@pytest.mark.office
@pytest.mark.skipif(sys.platform != "win32", reason="Word COM só no Windows")
def test_word_renders_cover_without_header_and_page_two_with_header(cfg, assets, tmp_path):
    from prog_g2_report.builder.word_pdf import export_pdf, word_available

    if not word_available():
        pytest.skip("pywin32 ausente")
    pymupdf = pytest.importorskip("pymupdf")
    report = make_report(31, date(2029, 4, 2), "2029-03")
    doc = fd.new_document(cfg)
    ctx = RenderContext(report=report, model={}, sources=SourceManifest(), document=doc,
                        assets_dir=assets, work_dir=tmp_path, data={"ooxml_base": cfg})
    cv.build_cover(ctx)
    fd.add_toc(doc, cfg)
    fd.add_heading(doc, "Apresentação", 1, cfg)
    doc.add_paragraph("Corpo da seção 0.")
    fd.add_section(doc, 1, cfg)
    doc.add_paragraph("Seção paisagem.")
    fd.add_section(doc, 2, cfg)
    fd.add_heading(doc, "Produto de teste", 2, cfg)
    docx_path, pdf_path = tmp_path / "office.docx", tmp_path / "office.pdf"
    doc.save(docx_path)
    # o Word se desconecta após exportar documentos com SDT de sumário (ver word_pdf); a exceção
    # COM é tratada, mas o faulthandler do pytest a imprimiria como "fatal"
    was_enabled = faulthandler.is_enabled()
    faulthandler.disable()
    try:
        pages = export_pdf(docx_path, pdf_path)
    finally:
        if was_enabled:
            faulthandler.enable()
    pdf = pymupdf.open(pdf_path)
    try:
        assert pages == len(pdf) >= 5
        header = cfg["header"]["text"]
        cover_text = pdf[0].get_text()
        assert header not in cover_text and cfg["footer"]["text"] not in cover_text
        assert "Relatório Mensal N° 31" in cover_text
        assert "02 de Abril de 2029" in cover_text
        second = pdf[1].get_text()
        assert header in second and cfg["footer"]["text"] in second
        assert "2" in second.split()                # campo PAGE calculado
        assert "SUMÁRIO" in second and "APRESENTAÇÃO" in second   # TOC atualizado pelo Word
        orientations = [p.rect.width > p.rect.height for p in pdf]
        assert True in orientations and orientations[0] is False and orientations[-1] is False
        land = next(i for i, o in enumerate(orientations) if o)
        assert header in pdf[land].get_text()
        image = pdf[0].get_image_info()[0]["bbox"]
        assert image[0] <= 0 and image[1] <= 0
        assert image[2] >= pdf[0].rect.width and image[3] >= pdf[0].rect.height
    finally:
        pdf.close()
