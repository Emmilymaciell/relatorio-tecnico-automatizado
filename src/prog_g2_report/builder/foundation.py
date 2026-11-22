"""Fundação do documento do Relatório G2, construída a partir de `Document()` vazio.

Tudo o que é fixo do formato (tema, estilos, numeração dos títulos, settings, geometria das 3
seções, cabeçalho/rodapé, TOC) vem de `config/ooxml_base.yaml` — este módulo só serializa.
Componentes do modelo (config/g2_report_model.yaml) que este módulo realiza:

    PAGE_GEOMETRY     ooxml_base.page.sections[*].pgSz/pgMar/orientation
    SECTION_SKELETON  ooxml_base.page.sections, ooxml_base.styles, ooxml_base.numbering
    HEADER            ooxml_base.header (+ page.sections[*].header_footer)
    FOOTER            ooxml_base.footer (campo PAGE)
    TOC               ooxml_base.toc

Funções públicas:
    load_base_config(path)               lê o YAML
    new_document(cfg)                    Document() + tema, estilos, numeração, settings, seção 0
    add_section(doc, index, cfg)         cria/configura a seção `index` (em ordem: 0, 1, 2)
    apply_header_footer(section, cfg, index)
    add_toc(doc, cfg)                    SDT "Table of Contents" com o campo TOC
    add_heading(doc, text, level, cfg)   parágrafo com o estilo do nível (0 = Título sem número)
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml
from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Twips
from lxml import etree

from prog_g2_report import REPO_ROOT

BASE_CONFIG_PATH = REPO_ROOT / "config" / "ooxml_base.yaml"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
COMPAT_URI = "http://schemas.microsoft.com/office/word"
STYLES_WITH_EFFECTS = "http://schemas.microsoft.com/office/2007/relationships/stylesWithEffects"

# --------------------------------------------------------------------------------------------
# Ordem dos filhos segundo o schema WordprocessingML (ECMA-376 parte 1, §17). O YAML não precisa
# respeitar ordem; o serializador impõe esta.
PPR_ORDER = (
    "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl", "numPr",
    "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens", "kinsoku", "wordWrap",
    "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
    "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc",
    "textDirection", "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr",
)
RPR_ORDER = (
    "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike",
    "outline", "shadow", "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden",
    "color", "spacing", "w", "kern", "position", "sz", "szCs", "highlight", "u", "effect", "bdr",
    "shd", "fitText", "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout", "specVanish",
)
STYLE_ORDER = (
    "name", "aliases", "basedOn", "next", "link", "autoRedefine", "hidden", "uiPriority",
    "semiHidden", "unhideWhenUsed", "qFormat", "locked", "pPr", "rPr", "tblPr", "trPr", "tcPr",
)
TBLPR_ORDER = (
    "tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblW", "jc", "tblCellSpacing", "tblInd",
    "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook",
)
TRPR_ORDER = ("cantSplit", "trHeight", "tblHeader", "tblCellSpacing", "jc", "hidden")
TCPR_ORDER = (
    "cnfStyle", "tcW", "gridSpan", "vMerge", "tcBorders", "shd", "noWrap", "tcMar",
    "textDirection", "tcFitText", "vAlign", "hideMark",
)
BORDER_ORDER = ("top", "left", "start", "bottom", "right", "end", "insideH", "insideV")
NUMPR_ORDER = ("ilvl", "numId")
LVL_ORDER = (
    "start", "numFmt", "lvlRestart", "pStyle", "isLgl", "suff", "lvlText", "lvlPicBulletId",
    "lvlJc", "pPr", "rPr",
)
SETTINGS_ORDER = (
    "writeProtection", "view", "zoom", "removePersonalInformation", "removeDateAndTime",
    "doNotDisplayPageBoundaries", "displayBackgroundShape", "printPostScriptOverText",
    "printFractionalCharacterWidth", "printFormsData", "embedTrueTypeFonts", "embedSystemFonts",
    "saveSubsetFonts", "saveFormsData", "mirrorMargins", "alignBordersAndEdges",
    "bordersDoNotSurroundHeader", "bordersDoNotSurroundFooter", "gutterAtTop",
    "hideSpellingErrors", "hideGrammaticalErrors", "activeWritingStyle", "proofState",
    "formsDesign", "attachedTemplate", "linkStyles", "stylePaneFormatFilter",
    "stylePaneSortMethod", "documentType", "mailMerge", "revisionView", "trackRevisions",
    "doNotTrackMoves", "doNotTrackFormatting", "documentProtection", "autoFormatOverride",
    "styleLockTheme", "styleLockQFSet", "defaultTabStop", "autoHyphenation",
    "consecutiveHyphenLimit", "hyphenationZone", "doNotHyphenateCaps", "showEnvelope",
    "summaryLength", "clickAndTypeStyle", "defaultTableStyle", "evenAndOddHeaders",
    "bookFoldRevPrinting", "bookFoldPrinting", "bookFoldPrintingSheets",
    "drawingGridHorizontalSpacing", "drawingGridVerticalSpacing",
    "displayHorizontalDrawingGridEvery", "displayVerticalDrawingGridEvery",
    "doNotUseMarginsForDrawingGridOrigin", "drawingGridHorizontalOrigin",
    "drawingGridVerticalOrigin", "doNotShadeFormData", "noPunctuationKerning",
    "characterSpacingControl", "printTwoOnOne", "strictFirstAndLastChars", "noLineBreaksAfter",
    "noLineBreaksBefore", "savePreviewPicture", "doNotValidateAgainstSchema", "saveInvalidXml",
    "ignoreMixedContent", "alwaysShowPlaceholderText", "doNotDemarcateInvalidXml",
    "saveXmlDataOnly", "useXSLTWhenSaving", "saveThroughXslt", "showXMLTags",
    "alwaysMergeEmptyNamespace", "updateFields", "hdrShapeDefaults", "footnotePr", "endnotePr",
    "compat", "docVars", "rsids", "mathPr", "attachedSchema", "themeFontLang",
    "clrSchemeMapping", "doNotIncludeSubdocsInStats", "doNotAutoCompressPictures",
    "forceUpgrade", "captions", "readModeInkLockDown", "smartTagType", "schemaLibrary",
    "shapeDefaults", "doNotEmbedSmartTags", "decimalSymbol", "listSeparator",
)
THEME_COLOR_ORDER = (
    "dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5",
    "accent6", "hlink", "folHlink",
)

# Elementos cujo mapa YAML descreve FILHOS (não atributos), com a ordem do schema.
CHILD_ORDERS: dict[str, tuple[str, ...]] = {
    "pPr": PPR_ORDER,
    "rPr": RPR_ORDER,
    "tblPr": TBLPR_ORDER,
    "trPr": TRPR_ORDER,
    "tcPr": TCPR_ORDER,
    "tblCellMar": BORDER_ORDER,
    "tblBorders": BORDER_ORDER,
    "tcBorders": BORDER_ORDER,
    "pBdr": ("top", "left", "bottom", "right", "between", "bar"),
    "numPr": NUMPR_ORDER,
}
LIST_CONTAINERS = {"tabs": "tab"}


class OoxmlConfigError(ValueError):
    """O YAML de base descreve algo que o serializador não sabe (ou não deve) emitir."""


# --------------------------------------------------------------------------------- serializer
def _str(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def build_element(tag: str, value: Any) -> Any:
    """Converte um nó do YAML em elemento `w:<tag>` (convenção descrita em ooxml_base.yaml)."""
    el = OxmlElement(f"w:{tag}")
    if tag in LIST_CONTAINERS:
        for item in value:
            el.append(build_element(LIST_CONTAINERS[tag], item))
    elif tag in CHILD_ORDERS:
        order = CHILD_ORDERS[tag]
        unknown = [k for k in value if k not in order]
        if unknown:
            raise OoxmlConfigError(f"filho(s) não suportado(s) em w:{tag}: {unknown}")
        for key in sorted(value, key=order.index):
            child = value[key]
            if child is None:
                continue
            el.append(build_element(key, child))
    elif value is True:
        pass
    elif value is False:
        el.set(qn("w:val"), "0")
    elif isinstance(value, Mapping):
        for key, attr in value.items():
            el.set(qn(f"w:{key}"), _str(attr))
    else:
        el.set(qn("w:val"), _str(value))
    return el


def build_style(style_id: str, spec: Mapping[str, Any]) -> Any:
    """`w:style` a partir de ooxml_base.styles.definitions[style_id]."""
    el = OxmlElement("w:style")
    el.set(qn("w:type"), spec["type"])
    if spec.get("default"):
        el.set(qn("w:default"), "1")
    if spec.get("customStyle"):
        el.set(qn("w:customStyle"), "1")
    el.set(qn("w:styleId"), style_id)
    keys = [k for k in spec if k not in {"type", "default", "customStyle"}]
    unknown = [k for k in keys if k not in STYLE_ORDER]
    if unknown:
        raise OoxmlConfigError(f"chave(s) não suportada(s) no estilo {style_id}: {unknown}")
    for key in sorted(keys, key=STYLE_ORDER.index):
        el.append(build_element(key, spec[key]))
    return el


def _clear(el: Any) -> None:
    for child in list(el):
        el.remove(child)


def _w(local: str) -> str:
    return f"{{{W_NS}}}{local}"


# ------------------------------------------------------------------------------- config
def load_base_config(path: Path | str | None = None) -> dict[str, Any]:
    """Lê `config/ooxml_base.yaml` (ou outro caminho, para testes)."""
    target = Path(path) if path else BASE_CONFIG_PATH
    return yaml.safe_load(target.read_text(encoding="utf-8"))


def section_config(cfg: Mapping[str, Any], index: int) -> Mapping[str, Any]:
    sections = cfg["page"]["sections"]
    for spec in sections:
        if spec["index"] == index:
            return spec
    raise KeyError(f"seção {index} não existe em ooxml_base.page.sections")


# ----------------------------------------------------------------------------- package parts
def _part_by_reltype(doc: Any, reltype: str) -> Any:
    for rel in doc.part.rels.values():
        if rel.reltype == reltype and not rel.is_external:
            return rel.target_part
    raise KeyError(reltype)


def _rewrite_theme(doc: Any, theme_cfg: Mapping[str, Any]) -> None:
    """ooxml_base.theme: troca clrScheme e fontScheme do tema padrão (Office/Calibri)."""
    part = _part_by_reltype(doc, RT.THEME)
    root = etree.fromstring(part.blob)
    a = f"{{{A_NS}}}"
    clr = root.find(f".//{a}clrScheme")
    clr.set("name", theme_cfg["color_scheme_name"])
    _clear(clr)
    colors = theme_cfg["colors"]
    for slot in THEME_COLOR_ORDER:
        spec = colors[slot]
        holder = etree.SubElement(clr, f"{a}{slot}")
        if "sys" in spec:
            etree.SubElement(holder, f"{a}sysClr", val=spec["sys"], lastClr=_str(spec["last"]))
        else:
            etree.SubElement(holder, f"{a}srgbClr", val=_str(spec["srgb"]))
    fonts = root.find(f".//{a}fontScheme")
    fonts.set("name", theme_cfg["font_scheme_name"])
    fonts.find(f"{a}majorFont/{a}latin").set("typeface", theme_cfg["major_latin"])
    fonts.find(f"{a}minorFont/{a}latin").set("typeface", theme_cfg["minor_latin"])
    for group in ("majorFont", "minorFont"):
        for script in ("ea", "cs"):
            node = fonts.find(f"{a}{group}/{a}{script}")
            if node is not None:
                node.set("typeface", "")
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _drop_styles_with_effects(doc: Any) -> None:
    """Remove a parte stylesWithEffects (Word 2010) do template do python-docx; vale styles.xml."""
    for r_id, rel in list(doc.part.rels.items()):
        if rel.reltype == STYLES_WITH_EFFECTS:
            doc.part.drop_rel(r_id)


def _apply_styles(doc: Any, cfg: Mapping[str, Any]) -> None:
    """ooxml_base.doc_defaults + ooxml_base.styles: styles.xml reescrito do zero."""
    root = doc.styles.element
    _clear(root)
    defaults = cfg["doc_defaults"]
    dd = OxmlElement("w:docDefaults")
    rpr_default = OxmlElement("w:rPrDefault")
    rpr_default.append(build_element("rPr", defaults["rPr"]))
    ppr_default = OxmlElement("w:pPrDefault")
    ppr_default.append(build_element("pPr", defaults["pPr"]))
    dd.append(rpr_default)
    dd.append(ppr_default)
    root.append(dd)
    for style_id, spec in cfg["styles"]["definitions"].items():
        root.append(build_style(style_id, spec))


def _apply_numbering(doc: Any, num_cfg: Mapping[str, Any]) -> None:
    """ooxml_base.numbering.headings: abstractNum multinível ligado a Ttulo1..3 + w:num."""
    root = doc.part.numbering_part.element
    _clear(root)
    spec = num_cfg["headings"]
    abstract = OxmlElement("w:abstractNum")
    abstract.set(qn("w:abstractNumId"), _str(spec["abstract_num_id"]))
    abstract.append(build_element("multiLevelType", spec["multi_level_type"]))
    for level in spec["levels"]:
        lvl = OxmlElement("w:lvl")
        lvl.set(qn("w:ilvl"), _str(level["ilvl"]))
        children = {k: v for k, v in level.items() if k != "ilvl"}
        if "ind" in children:
            children["pPr"] = {"ind": children.pop("ind")}
        unknown = [k for k in children if k not in LVL_ORDER]
        if unknown:
            raise OoxmlConfigError(f"chave(s) não suportada(s) no nível de numeração: {unknown}")
        for key in sorted(children, key=LVL_ORDER.index):
            lvl.append(build_element(key, children[key]))
        abstract.append(lvl)
    root.append(abstract)
    num = OxmlElement("w:num")
    num.set(qn("w:numId"), _str(spec["num_id"]))
    num.append(build_element("abstractNumId", spec["abstract_num_id"]))
    root.append(num)


def _settings_key(el: Any) -> int:
    tag = etree.QName(el)
    if tag.namespace in (W_NS, M_NS) and tag.localname in SETTINGS_ORDER:
        return SETTINGS_ORDER.index(tag.localname)
    return len(SETTINGS_ORDER)          # extensões w14/w15 ficam no fim, na ordem original


def _apply_settings(doc: Any, settings_cfg: Mapping[str, Any]) -> None:
    """ooxml_base.settings: embedTrueTypeFonts, saveSubsetFonts, compat 15, updateFields…"""
    root = doc.settings.element
    values = settings_cfg["values"]
    replaced = set(values) | {"compat"} | set(settings_cfg.get("remove", ()))
    for child in list(root):
        tag = etree.QName(child)
        if tag.namespace == W_NS and tag.localname in replaced:
            root.remove(child)
    for key, value in values.items():
        root.append(build_element(key, value))
    compat = OxmlElement("w:compat")
    for name, val in settings_cfg["compat"].items():
        setting = OxmlElement("w:compatSetting")
        setting.set(qn("w:name"), name)
        setting.set(qn("w:uri"), COMPAT_URI)
        setting.set(qn("w:val"), _str(val))
        compat.append(setting)
    root.append(compat)
    children = sorted(root, key=_settings_key)   # sort estável
    for child in children:
        root.append(child)


def _apply_font_table(doc: Any, fonts_cfg: Mapping[str, Any]) -> None:
    """ooxml_base.font_table: fontTable.xml com as famílias do relatório (o Word completa)."""
    part = _part_by_reltype(doc, RT.FONT_TABLE)
    root = etree.Element(_w("fonts"), nsmap={"w": W_NS})
    for font in fonts_cfg["fonts"]:
        node = etree.SubElement(root, _w("font"))
        node.set(_w("name"), font["name"])
        for key in ("panose1", "charset", "family", "pitch"):
            if font.get(key) is not None:
                etree.SubElement(node, _w(key)).set(_w("val"), _str(font[key]))
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _clear_body(doc: Any) -> None:
    body = doc.element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def new_document(cfg: Mapping[str, Any]) -> Any:
    """`Document()` vazio + tema, estilos, numeração, settings, fontTable e seção 0 (geometria e
    cabeçalho/rodapé). Componentes: PAGE_GEOMETRY, SECTION_SKELETON, HEADER, FOOTER."""
    doc = Document()
    _clear_body(doc)
    _drop_styles_with_effects(doc)
    _rewrite_theme(doc, cfg["theme"])
    _apply_styles(doc, cfg)
    _apply_numbering(doc, cfg["numbering"])
    _apply_settings(doc, cfg["settings"])
    _apply_font_table(doc, cfg["font_table"])
    props = cfg.get("document_properties", {})
    core = doc.core_properties
    core.author = props.get("author", "")
    core.last_modified_by = props.get("author", "")
    core.language = props.get("language", "")
    core.title = ""
    core.comments = ""
    add_section(doc, 0, cfg)
    return doc


# ---------------------------------------------------------------------------------- seções
def add_section(doc: Any, index: int, cfg: Mapping[str, Any]) -> Any:
    """Cria (index > 0) ou reconfigura (index 0) a seção `index` conforme
    ooxml_base.page.sections[index]. As seções são criadas em ordem; a nova seção começa
    em página nova (w:type ausente = nextPage)."""
    spec = section_config(cfg, index)
    count = len(doc.sections)
    if index == 0:
        section = doc.sections[0]
    elif index == count:
        section = doc.add_section(WD_SECTION.NEW_PAGE)
    else:
        raise ValueError(f"seção {index} fora de ordem: o documento tem {count} seção(ões)")
    _apply_geometry(section, spec)
    apply_header_footer(section, cfg, index)
    return section


def _apply_geometry(section: Any, spec: Mapping[str, Any]) -> None:
    """PAGE_GEOMETRY: pgSz, orientação, pgMar (twips exatos), cols, docGrid, titlePg."""
    size, mar = spec["pgSz"], spec["pgMar"]
    landscape = spec["orientation"] == "landscape"
    section.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
    section.page_width = Twips(size["w"])
    section.page_height = Twips(size["h"])
    section.top_margin = Twips(mar["top"])
    section.right_margin = Twips(mar["right"])
    section.bottom_margin = Twips(mar["bottom"])
    section.left_margin = Twips(mar["left"])
    section.header_distance = Twips(mar["header"])
    section.footer_distance = Twips(mar["footer"])
    section.gutter = Twips(mar["gutter"])
    section.different_first_page_header_footer = bool(spec.get("title_page"))
    sect_pr = section._sectPr
    cols = sect_pr.find(qn("w:cols"))
    if cols is not None and spec.get("cols_space") is not None:
        cols.set(qn("w:space"), _str(spec["cols_space"]))
    grid = sect_pr.find(qn("w:docGrid"))
    if grid is not None and spec.get("doc_grid_line_pitch") is not None:
        grid.set(qn("w:linePitch"), _str(spec["doc_grid_line_pitch"]))


# ------------------------------------------------------------------------ cabeçalho/rodapé
def _cell(width: int, borders: Mapping[str, Any], v_align: str, paragraph: Any) -> Any:
    tc = OxmlElement("w:tc")
    tc.append(build_element("tcPr", {
        "tcW": {"w": width, "type": "dxa"},
        "tcBorders": borders,
        "vAlign": v_align,
    }))
    tc.append(paragraph)
    return tc


def _paragraph(ppr: Mapping[str, Any], runs: Iterable[Any] = ()) -> Any:
    p = OxmlElement("w:p")
    p.append(build_element("pPr", ppr))
    for run in runs:
        p.append(run)
    return p


def _text_run(text: str, rpr: Mapping[str, Any] | None = None) -> Any:
    r = OxmlElement("w:r")
    if rpr:
        r.append(build_element("rPr", rpr))
    t = OxmlElement("w:t")
    t.text = text
    if text != text.strip():
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    r.append(t)
    return r


def _field_runs(instruction: str, placeholder: str, rpr: Mapping[str, Any] | None) -> list[Any]:
    """Campo complexo: begin / instrText / separate / resultado / end."""
    runs = []
    for kind in ("begin", "instr", "separate", "result", "end"):
        r = OxmlElement("w:r")
        if rpr:
            r.append(build_element("rPr", rpr))
        if kind == "instr":
            instr = OxmlElement("w:instrText")
            instr.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            instr.text = instruction
            r.append(instr)
        elif kind == "result":
            t = OxmlElement("w:t")
            t.text = placeholder
            r.append(t)
        else:
            fld = OxmlElement("w:fldChar")
            fld.set(qn("w:fldCharType"), kind)
            r.append(fld)
        runs.append(r)
    return runs


def _table(table_cfg: Mapping[str, Any], width: int, jc: str | None) -> Any:
    tbl = OxmlElement("w:tbl")
    margin = table_cfg["cell_margin_lr"]
    tbl_pr: dict[str, Any] = {
        "tblW": {"w": width, "type": "dxa"},
        "tblBorders": {"top": table_cfg["border_top"]},
        "tblCellMar": {"left": {"w": margin, "type": "dxa"}, "right": {"w": margin, "type": "dxa"}},
    }
    if jc:
        tbl_pr["jc"] = jc
    if table_cfg.get("look"):
        tbl_pr["tblLook"] = table_cfg["look"]
    tbl.append(build_element("tblPr", tbl_pr))
    return tbl


def header_table(header_cfg: Mapping[str, Any], layout_id: str) -> Any:
    """HEADER: tabela de N colunas (ooxml_base.header.layouts[layout_id]); texto na 1ª célula."""
    table_cfg = header_cfg["table"]
    layout = header_cfg["layouts"][layout_id]
    tbl = _table(table_cfg, layout["width"], table_cfg.get("jc"))
    grid = OxmlElement("w:tblGrid")
    for width in layout["grid"]:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), _str(width))
        grid.append(col)
    tbl.append(grid)
    tr = OxmlElement("w:tr")
    tr_pr: dict[str, Any] = {"trHeight": table_cfg["row_height"]}
    if table_cfg.get("jc"):
        tr_pr["jc"] = table_cfg["jc"]
    tr.append(build_element("trPr", tr_pr))
    last = len(layout["grid"]) - 1
    for i, width in enumerate(layout["grid"]):
        ppr: dict[str, Any] = {"pStyle": header_cfg["paragraph_style"]}
        runs = []
        if i == 0:
            if layout.get("text_ind"):
                ppr["ind"] = layout["text_ind"]
            runs.append(_text_run(header_cfg["text"]))
        if i == last and table_cfg.get("last_cell_jc"):
            ppr["jc"] = table_cfg["last_cell_jc"]
        tr.append(_cell(width, table_cfg["cell_borders"], table_cfg["v_align"],
                        _paragraph(ppr, runs)))
    tbl.append(tr)
    return tbl


def footer_table(footer_cfg: Mapping[str, Any], layout_id: str) -> Any:
    """FOOTER: "-CONFIDENCIAL-" à esquerda e campo PAGE à direita (ooxml_base.footer)."""
    table_cfg = footer_cfg["table"]
    layout = footer_cfg["layouts"][layout_id]
    tbl = _table(table_cfg, layout["width"], table_cfg.get("jc"))
    grid = OxmlElement("w:tblGrid")
    for width in layout["grid"]:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), _str(width))
        grid.append(col)
    tbl.append(grid)
    tr = OxmlElement("w:tr")
    tr.append(build_element("trPr", {"trHeight": layout["row_height"]}))
    style = footer_cfg["paragraph_style"]
    left_runs = []
    for _ in range(footer_cfg.get("leading_ptabs", 0)):
        r = OxmlElement("w:r")
        ptab = OxmlElement("w:ptab")
        ptab.set(qn("w:relativeTo"), "margin")
        ptab.set(qn("w:alignment"), "left")
        ptab.set(qn("w:leader"), "none")
        r.append(ptab)
        left_runs.append(r)
    left_runs.append(_text_run(footer_cfg["text"]))
    rstyle = {"rStyle": footer_cfg["page_run_style"]}
    right = _paragraph(
        {"pStyle": style, "jc": "right", "rPr": rstyle},
        _field_runs(footer_cfg["page_field"], footer_cfg["page_placeholder"], rstyle),
    )
    widths = layout["grid"]
    tr.append(_cell(widths[0], table_cfg["cell_borders"], table_cfg["v_align"],
                    _paragraph({"pStyle": style}, left_runs)))
    tr.append(_cell(widths[1], table_cfg["cell_borders"], table_cfg["v_align"], right))
    tbl.append(tr)
    return tbl


def _fill(container: Any, table: Any, trailing_style: str) -> None:
    root = container._element
    _clear(root)
    root.append(table)
    root.append(_paragraph({"pStyle": trailing_style}))


def apply_header_footer(section: Any, cfg: Mapping[str, Any], index: int) -> None:
    """HEADER/FOOTER da seção `index` (ooxml_base.page.sections[index].header_footer).

    `first: null` + `title_page: true` = 1ª página sem cabeçalho/rodapé (capa, DEC-011 §3):
    nenhuma referência 'first' é emitida, como no nº 14.
    """
    spec = section_config(cfg, index)
    plan = spec["header_footer"]
    header_cfg, footer_cfg = cfg["header"], cfg["footer"]
    section.different_first_page_header_footer = bool(spec.get("title_page"))

    def fill_pair(header: Any, footer: Any, layouts: Mapping[str, str]) -> None:
        header.is_linked_to_previous = False
        _fill(header, header_table(header_cfg, layouts["header"]),
              header_cfg["trailing_paragraph_style"])
        footer.is_linked_to_previous = False
        flayout = footer_cfg["layouts"][layouts["footer"]]
        _fill(footer, footer_table(footer_cfg, layouts["footer"]),
              flayout.get("trailing_paragraph_style", footer_cfg["trailing_paragraph_style"]))

    fill_pair(section.header, section.footer, plan["default"])
    if plan.get("first"):
        if not spec.get("title_page"):
            raise OoxmlConfigError(f"seção {index}: header_footer.first exige title_page: true")
        fill_pair(section.first_page_header, section.first_page_footer, plan["first"])
    else:
        sect_pr = section._sectPr
        first_refs = "w:headerReference[@w:type='first'] | w:footerReference[@w:type='first']"
        for ref in sect_pr.xpath(first_refs):
            sect_pr.remove(ref)


# ------------------------------------------------------------------------------------- TOC
def _append_block(doc: Any, element: Any) -> Any:
    body = doc.element.body
    sect_pr = body.find(qn("w:sectPr"))
    if sect_pr is not None:
        sect_pr.addprevious(element)
    else:
        body.append(element)
    return element


def add_toc(doc: Any, cfg: Mapping[str, Any]) -> Any:
    """TOC: SDT docPartGallery 'Table of Contents' com título e o campo de ooxml_base.toc.

    O resultado do campo é um texto provisório; o Word o recalcula (settings.updateFields).
    """
    toc = cfg["toc"]
    sdt = parse_xml(f"<w:sdt {nsdecls('w')}/>")
    sdt_pr = OxmlElement("w:sdtPr")
    if toc.get("sdt_rPr"):
        sdt_pr.append(build_element("rPr", toc["sdt_rPr"]))
    sdt_pr.append(build_element("id", toc["sdt_id"]))
    part_obj = OxmlElement("w:docPartObj")
    part_obj.append(build_element("docPartGallery", "Table of Contents"))
    part_obj.append(build_element("docPartUnique", True))
    sdt_pr.append(part_obj)
    sdt.append(sdt_pr)
    sdt.append(OxmlElement("w:sdtEndPr"))
    content = OxmlElement("w:sdtContent")
    content.append(_paragraph({"pStyle": toc["title_style"]}, [_text_run(toc["title"])]))
    content.append(_paragraph({"pStyle": toc["entry_style"]},
                              _field_runs(toc["instruction"], toc["placeholder"], None)))
    sdt.append(content)
    return _append_block(doc, sdt)


# --------------------------------------------------------------------------------- títulos
def heading_style_id(doc: Any, level: int, cfg: Mapping[str, Any] | None = None) -> str:
    """styleId do nível: ooxml_base.headings.levels; sem cfg, procura pelo nome interno do Word
    ('Title', 'heading N') entre os estilos do documento (que vêm do mesmo YAML)."""
    if cfg is not None:
        levels = cfg["headings"]["levels"]
        if level not in levels:
            raise ValueError(f"nível de título não suportado: {level}")
        return levels[level]
    name = "Title" if level == 0 else f"heading {level}"
    for style in doc.styles.element.findall(qn("w:style")):
        node = style.find(qn("w:name"))
        if node is not None and node.get(qn("w:val")) == name:
            return style.get(qn("w:styleId"))
    raise ValueError(f"nível de título não suportado: {level}")


def add_heading(doc: Any, text: str, level: int, cfg: Mapping[str, Any] | None = None) -> Any:
    """Título com o estilo do nível; a numeração (1, 1.1, 1.1.1) vem do estilo, não do texto."""
    style_id = heading_style_id(doc, level, cfg)
    paragraph = doc.add_paragraph(text)
    paragraph._p.get_or_add_pPr().style = style_id
    return paragraph
