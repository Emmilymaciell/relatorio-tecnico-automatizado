"""Fundação do documento (foundation.py + config/ooxml_base.yaml), lida no XML gerado."""

from __future__ import annotations

import copy
import zipfile
from pathlib import Path

import pytest

docx = pytest.importorskip("docx")
from lxml import etree  # noqa: E402

from prog_g2_report.builder import foundation as fd  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"w": W, "a": A, "r": R}
TWIP_CM = 1440 / 2.54
CONFIDENCES = {"CONFIRMED", "HIGH", "MEDIUM", "LOW", "UNKNOWN"}


def w(attr: str) -> str:
    return f"{{{W}}}{attr}"


@pytest.fixture(scope="module")
def cfg():
    return fd.load_base_config()


@pytest.fixture(scope="module")
def built(cfg, tmp_path_factory):
    """Documento com sumário, títulos de 3 níveis e as 3 seções."""
    doc = fd.new_document(cfg)
    fd.add_toc(doc, cfg)
    fd.add_heading(doc, "Apresentação", 1, cfg)
    fd.add_heading(doc, "Produto exemplo", 2, cfg)
    fd.add_heading(doc, "Descrição das atividades", 3, cfg)
    fd.add_section(doc, 1, cfg)
    doc.add_paragraph("paisagem")
    fd.add_section(doc, 2, cfg)
    fd.add_heading(doc, "ENCERRAMENTO", 0, cfg)
    path = tmp_path_factory.mktemp("foundation") / "foundation.docx"
    doc.save(path)
    return path


def part(path: Path, name: str):
    with zipfile.ZipFile(path) as z:
        return etree.fromstring(z.read(name))


def rels(path: Path) -> dict[str, str]:
    root = part(path, "word/_rels/document.xml.rels")
    return {r.get("Id"): r.get("Target") for r in root}


def sect_prs(path: Path):
    body = part(path, "word/document.xml").find("w:body", NS)
    inner = body.findall("w:p/w:pPr/w:sectPr", NS)
    return [*inner, body.find("w:sectPr", NS)]


# ----------------------------------------------------------------------------- config
def test_every_config_block_has_provenance_and_confidence(cfg):
    for key, block in cfg.items():
        if key == "_meta":
            continue
        assert block.get("provenance"), key
        assert block.get("confidence") in CONFIDENCES, key


def test_typography_follows_review_h(cfg):
    assert cfg["theme"]["minor_latin"] == "Arial Nova Light"     # corpo
    assert cfg["theme"]["major_latin"] == "Arial Nova Cond"      # títulos e cabeçalho
    assert cfg["doc_defaults"]["rPr"]["rFonts"]["asciiTheme"] == "minorHAnsi"
    assert cfg["doc_defaults"]["rPr"]["sz"] == 22                 # 11 pt


def test_landscape_margins_are_portrait_rotated(cfg):
    portrait = fd.section_config(cfg, 0)["pgMar"]
    landscape = fd.section_config(cfg, 1)["pgMar"]
    cm = {k: round(v / TWIP_CM, 1) for k, v in landscape.items() if k in {"top", "right", "bottom", "left"}}
    assert cm == {"top": 2.0, "right": 2.0, "bottom": 1.5, "left": 1.5}
    assert sorted([portrait["top"], portrait["left"]]) == sorted([landscape["top"], landscape["right"]])


# ----------------------------------------------------------------------------- seções
def test_three_sections_geometry_and_orientation(built, cfg):
    sects = sect_prs(built)
    assert len(sects) == 3
    for index, sect in enumerate(sects):
        spec = fd.section_config(cfg, index)
        pg_sz = sect.find("w:pgSz", NS)
        assert int(pg_sz.get(w("w"))) == spec["pgSz"]["w"]
        assert int(pg_sz.get(w("h"))) == spec["pgSz"]["h"]
        landscape = pg_sz.get(w("orient")) == "landscape"
        assert landscape == (spec["orientation"] == "landscape")
        pg_mar = sect.find("w:pgMar", NS)
        for side, value in spec["pgMar"].items():
            assert int(pg_mar.get(w(side))) == value, (index, side)
        assert sect.find("w:type", NS) is None            # nextPage (padrão)
    assert [s.find("w:pgSz", NS).get(w("orient")) for s in sects] == [None, "landscape", None]


def test_title_page_and_header_references_per_section(built):
    sects = sect_prs(built)
    refs = [
        sorted((r.tag.split("}")[1], r.get(w("type")))
               for r in s if r.tag in (w("headerReference"), w("footerReference")))
        for s in sects
    ]
    assert refs[0] == [("footerReference", "default"), ("headerReference", "default")]
    assert sects[0].find("w:titlePg", NS) is not None    # capa: 1ª página sem cabeçalho/rodapé
    assert refs[1] == [("footerReference", "default"), ("footerReference", "first"),
                       ("headerReference", "default"), ("headerReference", "first")]
    assert sects[1].find("w:titlePg", NS) is not None
    assert refs[2] == [("footerReference", "default"), ("headerReference", "default")]
    assert sects[2].find("w:titlePg", NS) is None


def _ref_part(path: Path, sect, kind: str, ref_type: str):
    ref = next(r for r in sect.findall(f"w:{kind}Reference", NS) if r.get(w("type")) == ref_type)
    target = rels(path)[ref.get(f"{{{R}}}id")]
    return part(path, f"word/{target}")


def test_header_text_border_and_widths(built, cfg):
    header = cfg["header"]
    plan = {0: ("default", "portrait"), 1: ("default", "landscape"), 2: ("default", "portrait")}
    sects = sect_prs(built)
    for index, (ref_type, layout) in plan.items():
        hdr = _ref_part(built, sects[index], "header", ref_type)
        assert "".join(hdr.itertext()) == header["text"]
        tbl = hdr.find("w:tbl", NS)
        assert int(tbl.find("w:tblPr/w:tblW", NS).get(w("w"))) == header["layouts"][layout]["width"]
        grid = [int(c.get(w("w"))) for c in tbl.findall("w:tblGrid/w:gridCol", NS)]
        assert grid == header["layouts"][layout]["grid"]
        bottom = tbl.find(".//w:tc/w:tcPr/w:tcBorders/w:bottom", NS)
        assert bottom.get(w("val")) == "single"
        assert tbl.find(".//w:p/w:pPr/w:pStyle", NS).get(w("val")) == "Cabealho"
        assert hdr[-1].tag == w("p")                        # termina com parágrafo
    first = _ref_part(built, sects[1], "header", "first")
    assert int(first.find("w:tbl/w:tblPr/w:tblW", NS).get(w("w"))) == header["layouts"]["landscape_first"]["width"]
    rest = _ref_part(built, sects[1], "header", "default")
    ind = rest.find(".//w:tc/w:p/w:pPr/w:ind", NS)
    assert int(ind.get(w("left"))) == header["layouts"]["landscape"]["text_ind"]["left"]


def test_footer_confidential_and_page_field(built, cfg):
    footer = cfg["footer"]
    sects = sect_prs(built)
    for sect, ref_type in ((sects[0], "default"), (sects[1], "default"), (sects[1], "first"), (sects[2], "default")):
        ftr = _ref_part(built, sect, "footer", ref_type)
        texts = [t.text for t in ftr.iter(w("t"))]
        assert footer["text"] in texts
        instr = [i.text for i in ftr.iter(w("instrText"))]
        assert instr == [footer["page_field"]]
        assert instr[0].split()[0] == "PAGE"
        kinds = [f.get(w("fldCharType")) for f in ftr.iter(w("fldChar"))]
        assert kinds == ["begin", "separate", "end"]
        assert len(list(ftr.iter(w("ptab")))) == footer["leading_ptabs"]


# --------------------------------------------------------------------- estilos e tema
def test_styles_keep_ids_and_fonts(built, cfg):
    styles = part(built, "word/styles.xml")
    ids = {s.get(w("styleId")) for s in styles.findall("w:style", NS)}
    assert ids == set(cfg["styles"]["definitions"])
    for required in ("Ttulo", "Ttulo1", "Ttulo2", "Ttulo3", "Normal", "PargrafodaLista",
                     "Sumrio1", "Sumrio2", "Sumrio3", "CabealhodoSumrio", "Cabealho", "Rodap"):
        assert required in ids
    defaults = styles.find("w:docDefaults/w:rPrDefault/w:rPr", NS)
    assert defaults.find("w:rFonts", NS).get(w("asciiTheme")) == "minorHAnsi"
    assert defaults.find("w:sz", NS).get(w("val")) == "22"
    by_id = {s.get(w("styleId")): s for s in styles.findall("w:style", NS)}
    assert by_id["Normal"].get(w("default")) == "1"
    assert by_id["Ttulo1"].find("w:rPr/w:rFonts", NS).get(w("asciiTheme")) == "majorHAnsi"
    assert by_id["Cabealho"].find("w:rPr/w:rFonts", NS).get(w("asciiTheme")) == "majorHAnsi"
    assert by_id["CabealhodoSumrio"].find("w:aliases", NS).get(w("val")) == "Sumário"


def test_style_children_follow_schema_order(built):
    styles = part(built, "word/styles.xml")
    t2 = next(s for s in styles.findall("w:style", NS) if s.get(w("styleId")) == "Ttulo2")
    order = [c.tag.split("}")[1] for c in t2.find("w:pPr", NS)]
    assert order == ["keepNext", "keepLines", "numPr", "spacing", "outlineLvl"]
    top = [c.tag.split("}")[1] for c in t2]
    assert top == sorted(top, key=fd.STYLE_ORDER.index)


def test_heading_numbering_multilevel(built, cfg):
    numbering = part(built, "word/numbering.xml")
    spec = cfg["numbering"]["headings"]
    num = numbering.find("w:num", NS)
    assert num.get(w("numId")) == str(spec["num_id"])
    assert num.find("w:abstractNumId", NS).get(w("val")) == str(spec["abstract_num_id"])
    levels = numbering.findall("w:abstractNum/w:lvl", NS)
    assert [lv.find("w:lvlText", NS).get(w("val")) for lv in levels] == ["%1", "%1.%2", "%1.%2.%3"]
    assert [lv.find("w:pStyle", NS).get(w("val")) for lv in levels] == ["Ttulo1", "Ttulo2", "Ttulo3"]
    styles = part(built, "word/styles.xml")
    for style_id, ilvl in (("Ttulo1", None), ("Ttulo2", "1"), ("Ttulo3", "2")):
        style = next(s for s in styles.findall("w:style", NS) if s.get(w("styleId")) == style_id)
        num_pr = style.find("w:pPr/w:numPr", NS)
        assert num_pr.find("w:numId", NS).get(w("val")) == str(spec["num_id"])
        node = num_pr.find("w:ilvl", NS)
        assert (node.get(w("val")) if node is not None else None) == ilvl


def test_theme_is_rewritten(built, cfg):
    theme = part(built, "word/theme/theme1.xml")
    clr = theme.find(".//a:clrScheme", NS)
    assert clr.get("name") == cfg["theme"]["color_scheme_name"]
    assert clr.find("a:accent1/a:srgbClr", NS).get("val") == "1C5560"
    assert clr.find("a:dk2/a:srgbClr", NS).get("val") == "8CC3E1"
    fonts = theme.find(".//a:fontScheme", NS)
    assert fonts.find("a:majorFont/a:latin", NS).get("typeface") == "Arial Nova Cond"
    assert fonts.find("a:minorFont/a:latin", NS).get("typeface") == "Arial Nova Light"
    assert b"Calibri" not in etree.tostring(fonts.find("a:minorFont/a:latin", NS))


def test_settings_fonts_compat_and_update_fields(built):
    settings = part(built, "word/settings.xml")
    for tag in ("embedTrueTypeFonts", "saveSubsetFonts", "updateFields"):
        assert settings.find(f"w:{tag}", NS) is not None, tag
    assert settings.find("w:savePreviewPicture", NS) is None
    mode = settings.find("w:compat/w:compatSetting[@w:name='compatibilityMode']", NS)
    assert mode.get(w("val")) == "15"
    assert settings.find("w:compat/w:useFELayout", NS) is None
    assert settings.find("w:decimalSymbol", NS).get(w("val")) == ","
    assert settings.find("w:themeFontLang", NS).get(w("val")) == "pt-BR"
    known = [c.tag.split("}")[1] for c in settings if c.tag.startswith(f"{{{W}}}")]
    positions = [fd.SETTINGS_ORDER.index(t) for t in known if t in fd.SETTINGS_ORDER]
    assert positions == sorted(positions)


def test_package_has_no_styles_with_effects_and_lists_fonts(built):
    with zipfile.ZipFile(built) as z:
        names = z.namelist()
    assert "word/stylesWithEffects.xml" not in names
    fonts = part(built, "word/fontTable.xml")
    names = {f.get(w("name")) for f in fonts.findall("w:font", NS)}
    assert {"Arial Nova Light", "Arial Nova Cond", "Arial Nova Cond Light"} <= names


# ------------------------------------------------------------------------ TOC e títulos
def test_toc_sdt_and_instruction(built, cfg):
    body = part(built, "word/document.xml").find("w:body", NS)
    sdts = body.findall("w:sdt", NS)
    assert len(sdts) == 1
    sdt = sdts[0]
    assert sdt.find("w:sdtPr/w:docPartObj/w:docPartGallery", NS).get(w("val")) == "Table of Contents"
    assert sdt.find("w:sdtPr/w:docPartObj/w:docPartUnique", NS) is not None
    instr = [i.text for i in sdt.iter(w("instrText"))]
    assert instr == [cfg["toc"]["instruction"]]
    assert instr[0] == 'TOC \\o "1-3" \\z \\u \\h'
    title = sdt.find("w:sdtContent/w:p", NS)
    assert title.find("w:pPr/w:pStyle", NS).get(w("val")) == cfg["toc"]["title_style"]
    assert "".join(title.itertext()) == cfg["toc"]["title"]
    children = list(body)
    first_heading = next(i for i, c in enumerate(children)
                         if c.find("w:pPr/w:pStyle", NS) is not None
                         and c.find("w:pPr/w:pStyle", NS).get(w("val")) == "Ttulo1")
    assert children.index(sdt) < first_heading


def test_headings_use_level_styles(built):
    body = part(built, "word/document.xml").find("w:body", NS)
    styled = {"".join(p.itertext()): p.find("w:pPr/w:pStyle", NS).get(w("val"))
              for p in body.findall("w:p", NS) if p.find("w:pPr/w:pStyle", NS) is not None}
    assert styled["Apresentação"] == "Ttulo1"
    assert styled["Produto exemplo"] == "Ttulo2"
    assert styled["Descrição das atividades"] == "Ttulo3"
    assert styled["ENCERRAMENTO"] == "Ttulo"


def test_heading_without_cfg_resolves_by_builtin_name(cfg):
    doc = fd.new_document(cfg)
    assert fd.heading_style_id(doc, 2) == "Ttulo2"
    assert fd.heading_style_id(doc, 0) == "Ttulo"
    with pytest.raises(ValueError):
        fd.add_heading(doc, "x", 7, cfg)


def test_round_trip_with_python_docx(built):
    doc = docx.Document(str(built))
    assert len(doc.sections) == 3
    assert doc.sections[1].page_width > doc.sections[1].page_height
    assert doc.styles["heading 1"].style_id == "Ttulo1"


# --------------------------------------------------------------------------- guardas
def test_sections_must_be_created_in_order(cfg):
    doc = fd.new_document(cfg)
    with pytest.raises(ValueError):
        fd.add_section(doc, 2, cfg)


def test_unknown_child_is_rejected():
    with pytest.raises(fd.OoxmlConfigError):
        fd.build_element("pPr", {"inventado": True})


def test_first_page_layout_requires_title_page(cfg):
    broken = copy.deepcopy(cfg)
    spec = next(s for s in broken["page"]["sections"] if s["index"] == 2)
    spec["header_footer"]["first"] = {"header": "portrait", "footer": "portrait_s2"}
    with pytest.raises(fd.OoxmlConfigError):
        doc = fd.new_document(broken)
        fd.add_section(doc, 1, broken)
        fd.add_section(doc, 2, broken)


def test_build_element_conventions():
    el = fd.build_element("rPr", {"b": True, "i": False, "sz": 26, "color": {"val": "1C5560"}})
    tags = [c.tag.split("}")[1] for c in el]
    assert tags == ["b", "i", "color", "sz"]
    assert el[0].get(w("val")) is None
    assert el[1].get(w("val")) == "0"
    assert el[2].get(w("val")) == "1C5560"
