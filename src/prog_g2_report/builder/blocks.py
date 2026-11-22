"""Motor genérico de blocos de texto (`config/g2_content_blocks.yaml`).

Classes do YAML (`conventions.classes`) e quem as emite:

    FIXED_TEXT       motor: texto literal (padronização DEC-007 do texto gerado)
    SOURCE_VERBATIM  motor: citação literal, **nunca** padronizada (DEC-007)
    TEMPLATE         motor: frase fixa com `{placeholders}` resolvidos de `values`
    DATA_DRIVEN, AI_SYNTHESIS, MANUAL_INPUT
                     delegados a `BLOCK_RENDERERS[block_id]`, que outros módulos registram com
                     `@register_block_renderer("P2.4_RM")`. Sem renderizador: ComponentResult
                     pendente + parágrafo-marcador visível "[PENDENTE: <block_id>]".

O registro tem precedência para qualquer bloco: um bloco FIXED_TEXT que na verdade é imagem
(`asset`, ex.: APRES_LOGO_GRUPOS) também é delegado, e fica pendente até alguém registrá-lo.

Representação:
    - estilo pelo styleId (`conventions.style`); 'Normal' = parágrafo sem w:pStyle;
    - negrito por `**…**` no template ou pela lista `bold` (segmentos na ordem do texto);
    - \\t -> w:tab, \\n -> w:br; recuo e itálico diretos pelo campo `direct`;
    - listas: uma instância <w:num> nova por lista apontando para o abstractNum da definição
      (`LIST_DEFINITIONS`); se o documento não tiver o abstractNum, cria-se um equivalente mínimo
      e registra-se um ComponentResult `LIST:<chave>`.

Os estilos (Ttulo, Ttulo1–3, PargrafodaLista…) são da fundação; o motor só confere que existem.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Twips

from prog_g2_report import REPO_ROOT
from prog_g2_report.builder import presence as presence_mod
from prog_g2_report.builder.context import ComponentResult, RenderContext
from prog_g2_report.builder.values import MissingValueError

BLOCKS_PATH = REPO_ROOT / "config" / "g2_content_blocks.yaml"

ENGINE_CLASSES = frozenset({"FIXED_TEXT", "SOURCE_VERBATIM", "TEMPLATE"})
DELEGATED_CLASSES = frozenset({"DATA_DRIVEN", "AI_SYNTHESIS", "MANUAL_INPUT"})
PENDING_STATUS = "PENDING_HUMAN"           # vocabulário de ComponentResult.status (context.py)
PENDING_MARKER = "[PENDENTE: {block_id}]"


class BlockModelError(ValueError):
    """O bloco do YAML é inconsistente (negrito inexistente, `**` ímpar, chave faltando…)."""


class UnsupportedBlockError(ValueError):
    """O motor não sabe emitir este formato de bloco (imagem, campo, estrutura própria)."""


class MissingStyleError(ValueError):
    """O styleId exigido pelo bloco não existe no documento (a fundação não rodou?)."""


# --- carga ---------------------------------------------------------------------------------
@dataclass(frozen=True)
class Block:
    block_id: str
    cls: str
    presence: str
    style: str | None
    seq: int
    raw: dict[str, Any] = field(repr=False, compare=False, hash=False)
    derived_from: str | None = None        # bloco virtual gerado a partir de outro (ver retorno)

    @property
    def product(self) -> str | None:
        match = re.match(r"^P(2\.[1-6])_", self.block_id)
        return match.group(1) if match else None

    @property
    def virtual(self) -> bool:
        return self.derived_from is not None


def load_content_model(path: Path = BLOCKS_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def block_from_raw(raw: dict[str, Any], derived_from: str | None = None) -> Block:
    if not raw.get("block_id") or not raw.get("class"):
        raise BlockModelError(f"bloco sem block_id/class: {raw!r:.80}")
    return Block(
        block_id=raw["block_id"],
        cls=raw["class"],
        presence=" ".join(str(raw.get("presence") or "always").split()),
        style=raw.get("style"),
        seq=int(raw.get("seq") or 0),
        raw=raw,
        derived_from=derived_from,
    )


def load_blocks(path: Path = BLOCKS_PATH) -> list[Block]:
    """Blocos na ordem do documento (`seq`)."""
    data = load_content_model(path)
    blocks = [block_from_raw(raw) for raw in data.get("blocks") or []]
    ids = [b.block_id for b in blocks]
    duplicated = sorted({i for i in ids if ids.count(i) > 1})
    if duplicated:
        raise BlockModelError(f"block_id duplicado: {duplicated}")
    return sorted(blocks, key=lambda b: b.seq)


def blocks_by_id(blocks: list[Block]) -> dict[str, Block]:
    return {b.block_id: b for b in blocks}


def derive_block(base: Block, block_id: str, **changes: Any) -> Block:
    """Cópia de `base` com outro id (e campos do YAML trocados/removidos: valor None remove)."""
    raw = copy.deepcopy(base.raw)
    raw["block_id"] = block_id
    for key, value in changes.items():
        if value is None:
            raw.pop(key, None)
        else:
            raw[key] = value
    return block_from_raw(raw, derived_from=base.block_id)


# --- estilo e formatação direta ------------------------------------------------------------
@dataclass(frozen=True)
class StyleSpec:
    style_id: str | None = None
    list_key: str | None = None            # chave de LIST_DEFINITIONS
    ilvl: int = 0
    jc: str | None = None


def parse_style(text: str | None) -> StyleSpec:
    """'PargrafodaLista + numId 35 lvl 0 (•)' -> StyleSpec('PargrafodaLista', '35', 0)."""
    if not text:
        return StyleSpec()
    head = re.match(r"^\s*([A-Za-z][A-Za-z0-9]*)", text)
    if not head:
        raise BlockModelError(f"estilo ilegível: {text!r}")
    num = re.search(r"\bnumId\s+(\d+)", text)
    lvl = re.search(r"\bi?lvl\s+(\d+)", text)
    jc = re.search(r"\bjc\s+(left|center|right|both)\b", text)
    list_key = num.group(1) if num else None
    if list_key is None and "numPr" in text:
        # 'Normal + numPr ilvl 0 (marcador Symbol U+F0B7, ind 720/360)': marcador simples
        if "U+F0B7" not in text:
            raise BlockModelError(f"numPr sem definição de lista reconhecível: {text!r}")
        list_key = "bullet"
    return StyleSpec(
        style_id=head.group(1),
        list_key=list_key,
        ilvl=int(lvl.group(1)) if lvl and list_key else 0,
        jc=jc.group(1) if jc else None,
    )


@dataclass(frozen=True)
class DirectFormat:
    italic: bool = False
    italic_leading_tabs: bool = True
    mark_italic: bool = False
    ind_left: int | None = None


def parse_direct(text: str | None) -> DirectFormat:
    """Campo `direct` do YAML (texto livre) -> formatação direta.

    '4 tabs iniciais (runs sem itálico) + texto itálico; marca de parágrafo itálica'
    '4 tabs + texto, tudo itálico'
    'ind left=2832 twips (5,0 cm), itálico; aspas de fechamento ” no fim'
    """
    if not text:
        return DirectFormat()
    ind = re.search(r"\bind left=(\d+)", text)
    return DirectFormat(
        italic="itálic" in text,
        italic_leading_tabs=not re.search(r"tabs[^;]*sem itálico", text),
        mark_italic="marca de parágrafo itálica" in text,
        ind_left=int(ind.group(1)) if ind else None,
    )


# --- segmentos, placeholders e negrito -----------------------------------------------------
@dataclass
class Segment:
    text: str
    bold: bool = False
    italic: bool = False


@dataclass
class ParagraphSpec:
    segments: list[Segment]
    style: StyleSpec = field(default_factory=StyleSpec)
    ind_left: int | None = None
    mark_italic: bool = False
    page_break_before: bool = False

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.segments)


PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class EmptySlot(str):
    """Valor VAZIO intencional de um slot (ex.: `value_if_false: ''`). `fill` aceita; um `''`
    comum continua sendo valor ausente."""

    def __new__(cls) -> EmptySlot:
        return super().__new__(cls, "")


def fill(text: str, values: dict[str, Any], where: str, used: set[str] | None = None) -> str:
    """Resolve `{nome}`. Placeholder sem valor -> MissingValueError; nunca sobra `{x}`.
    `EmptySlot()` é o único vazio aceito."""

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        value = values.get(name)
        if value is None or (value == "" and not isinstance(value, EmptySlot)):
            raise MissingValueError(name, where)
        if used is not None:
            used.add(name)
        return str(value)

    out = PLACEHOLDER.sub(replace, text)
    if "{" in PLACEHOLDER.sub("", text) or "}" in PLACEHOLDER.sub("", text):
        raise BlockModelError(f"{where}: chave solta no template: {text!r:.80}")
    return out


def parse_markup(
    template: str, values: dict[str, Any], where: str, used: set[str] | None = None
) -> list[Segment]:
    """'a **{x}** b' -> [a ][x em negrito][ b]. Placeholders resolvidos por segmento."""
    parts = template.split("**")
    if len(parts) % 2 == 0:
        raise BlockModelError(f"{where}: marcação '**' sem par")
    return [
        Segment(fill(part, values, where, used), bold=bool(index % 2))
        for index, part in enumerate(parts)
        if part
    ]


def apply_bold(text: str, bold: list[str], where: str) -> list[Segment]:
    """Negrito por lista de segmentos, procurados em ordem a partir do fim do anterior."""
    ranges: list[tuple[int, int]] = []
    cursor = 0
    for piece in bold:
        if not piece:
            continue
        start = text.find(piece, cursor)
        if start < 0:
            start = text.find(piece)
            if start < 0:
                raise BlockModelError(f"{where}: segmento em negrito ausente do texto: {piece!r}")
        ranges.append((start, start + len(piece)))
        cursor = start + len(piece)
    flags = [False] * len(text)
    for start, end in ranges:
        for i in range(start, end):
            flags[i] = True
    segments: list[Segment] = []
    for char, flag in zip(text, flags, strict=True):
        if segments and segments[-1].bold == flag:
            segments[-1].text += char
        else:
            segments.append(Segment(char, bold=flag))
    return segments


def standardize_segments(segments: list[Segment]) -> list[Segment]:
    """DEC-007 no texto gerado: negrito sem espaço nas bordas e sem espaço residual no fim.

    ENC_P1.note: o nº 14 põe negrito em '43 (quarenta e três) ' (com espaço) -> normaliza para o
    número; ANEXOS_TITLE e afins: espaços à direita desaparecem. Nunca aplicar a SOURCE_VERBATIM.
    """
    out: list[Segment] = []

    def push(text: str, bold: bool, italic: bool) -> None:
        if not text:
            return
        if out and out[-1].bold == bold and out[-1].italic == italic:
            out[-1].text += text
        else:
            out.append(Segment(text, bold, italic))

    for seg in segments:
        if seg.bold:
            core = seg.text.strip()
            if not core:
                push(seg.text, False, seg.italic)
                continue
            lead = seg.text[: len(seg.text) - len(seg.text.lstrip())]
            trail = seg.text[len(seg.text.rstrip()) :]
            push(lead, False, seg.italic)
            push(core, True, seg.italic)
            push(trail, False, seg.italic)
        else:
            push(seg.text, False, seg.italic)
    while out and not out[-1].text.rstrip():
        out.pop()
    if out:
        out[-1].text = out[-1].text.rstrip()
    return out


# --- construção pura (sem documento) -------------------------------------------------------
def _generated_paragraph(
    text_or_template: str,
    block: Block,
    values: dict[str, Any],
    bold: list[str] | None,
    style: StyleSpec,
    used: set[str],
    resolve: bool,
) -> ParagraphSpec:
    where = block.block_id
    if resolve and "**" in text_or_template:
        segments = parse_markup(text_or_template, values, where, used)
    else:
        text = fill(text_or_template, values, where, used) if resolve else text_or_template
        resolved_bold = [fill(b, values, where, used) if resolve else b for b in bold or []]
        segments = apply_bold(text, resolved_bold, where) if resolved_bold else [Segment(text)]
    return ParagraphSpec(standardize_segments(segments), style)


_TEXT_KEYS = ("template", "text_standardized", "text", "text_historical")


def check_engine_shape(block: Block) -> None:
    """Levanta UnsupportedBlockError se o motor não sabe emitir o bloco (sem olhar valores)."""
    raw = block.raw
    if block.cls not in ENGINE_CLASSES:
        raise UnsupportedBlockError(f"{block.block_id}: classe {block.cls} é delegada")
    if "table" in raw:
        return
    if "asset" in raw or "field" in raw or block.block_id == "COVER":
        raise UnsupportedBlockError(f"{block.block_id}: não é parágrafo de texto")
    if "lead" in raw or ("items" in raw and not isinstance(raw["items"], list)):
        raise UnsupportedBlockError(f"{block.block_id}: estrutura própria (lead/items)")
    if block.cls == "SOURCE_VERBATIM":
        if not raw.get("paragraphs"):
            raise BlockModelError(f"{block.block_id}: SOURCE_VERBATIM sem paragraphs")
        return
    if not any(k in raw for k in ("items", "texts", *_TEXT_KEYS)):
        raise UnsupportedBlockError(f"{block.block_id}: sem texto emitível")


def build_paragraphs(
    block: Block, values: dict[str, Any], used: set[str] | None = None
) -> list[ParagraphSpec]:
    """O que o motor emitiria para o bloco, sem tocar no documento."""
    raw = block.raw
    used = set() if used is None else used
    check_engine_shape(block)
    if "table" in raw:
        raise UnsupportedBlockError(f"{block.block_id}: tabela (use render_table)")
    style = parse_style(block.style)

    if block.cls == "SOURCE_VERBATIM":
        # DEC-007: preservar exatamente. Sem placeholder, sem strip, sem correção.
        specs = []
        for para in raw.get("paragraphs") or []:
            fmt = parse_direct(para.get("direct"))
            text = para["text"]
            match = re.match(r"^(\t+)(.*)$", text, re.DOTALL)
            if fmt.italic and not fmt.italic_leading_tabs and match:
                segments = [Segment(match.group(1)), Segment(match.group(2), italic=True)]
            else:
                segments = [Segment(text, italic=fmt.italic)]
            specs.append(
                ParagraphSpec(segments, parse_style(para.get("style")), fmt.ind_left,
                              fmt.mark_italic)
            )
        return specs

    resolve = block.cls == "TEMPLATE" or "template" in raw
    if "items" in raw:
        specs = []
        for item in raw["items"]:
            text, bold = (item, raw.get("bold")) if isinstance(item, str) else (
                item["text"], item.get("bold"))
            specs.append(_generated_paragraph(text, block, values, bold, style, used,
                                              block.cls == "TEMPLATE"))
        return specs
    if "texts" in raw:
        return [_generated_paragraph(t, block, values, raw.get("bold"), style, used, False)
                for t in raw["texts"]]
    # template > text_standardized (DEC-007) > text > text_historical
    key = next(k for k in _TEXT_KEYS if k in raw)
    source = raw[key]
    source = "" if source is None else str(source)
    if source == "":
        # parágrafo(s) vazio(s): um por posição registrada em `order` (ENC_SPACERS = 4)
        return [ParagraphSpec([], style) for _ in range(max(1, len(raw.get("order") or [])))]
    return [_generated_paragraph(source, block, values, raw.get("bold"), style, used,
                                 resolve and key == "template")]


# --- listas --------------------------------------------------------------------------------
@dataclass(frozen=True)
class ListLevel:
    num_fmt: str
    lvl_text: str
    left: int
    hanging: int
    font: str | None = None
    jc: str = "left"


def _levels(*levels: ListLevel) -> tuple[ListLevel, ...]:
    return levels


_DOT = ListLevel("bullet", "", 720, 360, "Symbol")
_DOT2 = ListLevel("bullet", "", 2160, 360, "Symbol")
_HYBRID = _levels(_DOT, ListLevel("bullet", "o", 1440, 360, "Courier New"),
                  ListLevel("bullet", "", 2160, 360, "Wingdings"))
_UPPER = _levels(_DOT, ListLevel("upperLetter", "%2)", 1440, 360), _DOT2)

# Equivalentes mínimos das definições do nº 14 (numbering.xml; os ids de abstractNum mudam a cada
# DOCX, por isso a chave é o numId citado no `style` do bloco). Conferido com
# config/data_rules/p24_blocks.yaml common.numbering para 29 e 47.
LIST_DEFINITIONS: dict[str, tuple[ListLevel, ...]] = {
    "bullet": _levels(_DOT, ListLevel("bullet", "", 1440, 360, "Symbol"), _DOT2),
    "29": _levels(_DOT, ListLevel("lowerLetter", "%2)", 1440, 360), _DOT2),
    "35": _HYBRID,
    "36": _HYBRID,
    "37": _HYBRID,
    "28": _UPPER,
    "49": _UPPER,
    "50": _UPPER,
    "47": _levels(ListLevel("lowerLetter", "%1)", 720, 360),
                  ListLevel("upperRoman", "%2.", 1440, 360, jc="right"),
                  ListLevel("lowerRoman", "%3.", 2160, 180, jc="right")),
}
LIST_NAME = "G2_LIST_{key}"


def _abstract_num_xml(abstract_id: int, key: str) -> Any:
    abstract = OxmlElement("w:abstractNum")
    abstract.set(qn("w:abstractNumId"), str(abstract_id))
    multi = OxmlElement("w:multiLevelType")
    multi.set(qn("w:val"), "hybridMultilevel")
    abstract.append(multi)
    name = OxmlElement("w:name")
    name.set(qn("w:val"), LIST_NAME.format(key=key))
    abstract.append(name)
    for ilvl, level in enumerate(LIST_DEFINITIONS[key]):
        lvl = OxmlElement("w:lvl")
        lvl.set(qn("w:ilvl"), str(ilvl))
        for tag, val in (("w:start", "1"), ("w:numFmt", level.num_fmt),
                         ("w:lvlText", level.lvl_text), ("w:lvlJc", level.jc)):
            child = OxmlElement(tag)
            child.set(qn("w:val"), val)
            lvl.append(child)
        ppr = OxmlElement("w:pPr")
        ind = OxmlElement("w:ind")
        ind.set(qn("w:left"), str(level.left))
        ind.set(qn("w:hanging"), str(level.hanging))
        ppr.append(ind)
        lvl.append(ppr)
        if level.font:
            rpr = OxmlElement("w:rPr")
            fonts = OxmlElement("w:rFonts")
            for attr in ("w:ascii", "w:hAnsi", "w:cs"):
                fonts.set(qn(attr), level.font)
            fonts.set(qn("w:hint"), "default")
            rpr.append(fonts)
            lvl.append(rpr)
        abstract.append(lvl)
    return abstract


def _find_abstract(numbering: Any, key: str, mapping: dict[str, Any]) -> int | None:
    ids = {a.get(qn("w:abstractNumId")) for a in numbering.findall(qn("w:abstractNum"))}
    if key in mapping:
        if str(mapping[key]) not in ids:
            raise BlockModelError(f"list_abstract_nums[{key}]={mapping[key]} não existe")
        return int(mapping[key])
    wanted = LIST_NAME.format(key=key)
    for abstract in numbering.findall(qn("w:abstractNum")):
        name = abstract.find(qn("w:name"))
        if name is not None and name.get(qn("w:val")) == wanted:
            return int(abstract.get(qn("w:abstractNumId")))
    return None


def new_list_instance(rc: RenderContext, key: str) -> int:
    """Nova instância <w:num> (numeração reinicia) para a lista `key`; devolve o numId."""
    if key not in LIST_DEFINITIONS:
        raise BlockModelError(f"lista sem definição: {key}")
    numbering = rc.document.part.numbering_part.element
    abstract_id = _find_abstract(numbering, key, rc.data.get("list_abstract_nums") or {})
    if abstract_id is None:
        existing = [int(a.get(qn("w:abstractNumId")))
                    for a in numbering.findall(qn("w:abstractNum"))]
        abstract_id = max(existing, default=-1) + 1
        abstract = _abstract_num_xml(abstract_id, key)
        first_num = numbering.find(qn("w:num"))
        cleanup = numbering.find(qn("w:numIdMacAtCleanup"))
        if first_num is not None:
            first_num.addprevious(abstract)
        elif cleanup is not None:
            cleanup.addprevious(abstract)
        else:
            numbering.append(abstract)
        rc.record(ComponentResult(
            f"LIST:{key}", "OK",
            detail="abstractNum mínimo criado: o documento não tinha a definição",
            facts={"abstractNumId": abstract_id, "name": LIST_NAME.format(key=key)},
        ))
    num = numbering.add_num(abstract_id)
    for ilvl in range(len(LIST_DEFINITIONS[key])):
        num.add_lvlOverride(ilvl=ilvl).add_startOverride(1)
    return int(num.numId)


# --- emissão no documento ------------------------------------------------------------------
_JC = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
       "right": WD_ALIGN_PARAGRAPH.RIGHT, "both": WD_ALIGN_PARAGRAPH.JUSTIFY}


def require_style(rc: RenderContext, style_id: str | None) -> None:
    if not style_id:
        return
    styles = rc.document.styles.element
    if styles.find(f"{qn('w:style')}[@{qn('w:styleId')}='{style_id}']") is None:
        raise MissingStyleError(f"styleId ausente no documento: {style_id}")


def _set_run_font(run: Any, name: str | None, size_pt: float | None) -> None:
    if size_pt is not None:
        run.font.size = Pt(size_pt)
    if name:
        rpr = run._r.get_or_add_rPr()
        fonts = rpr.get_or_add_rFonts()
        for attr in ("w:ascii", "w:hAnsi", "w:cs"):
            fonts.set(qn(attr), name)


def emit_paragraph(
    rc: RenderContext, spec: ParagraphSpec, num_id: int | None = None, container: Any = None,
    font: tuple[str | None, float | None] | None = None,
) -> Any:
    target = container if container is not None else rc.document
    paragraph = target.add_paragraph()
    ppr = paragraph._p.get_or_add_pPr()
    if spec.style.style_id and spec.style.style_id != "Normal":
        require_style(rc, spec.style.style_id)
        ppr.style = spec.style.style_id
    if spec.page_break_before:
        ppr.get_or_add_pageBreakBefore()
    if num_id is not None:
        num_pr = ppr.get_or_add_numPr()
        num_pr.get_or_add_ilvl().val = spec.style.ilvl
        num_pr.get_or_add_numId().val = num_id
    if spec.ind_left is not None:
        paragraph.paragraph_format.left_indent = Twips(spec.ind_left)
    if spec.style.jc:
        paragraph.paragraph_format.alignment = _JC[spec.style.jc]
    if spec.mark_italic:
        rpr = OxmlElement("w:rPr")
        rpr.append(OxmlElement("w:i"))
        ppr.insert_element_before(rpr, "w:sectPr", "w:pPrChange")
    for seg in spec.segments:
        if not seg.text:
            continue
        run = paragraph.add_run(seg.text)
        if seg.bold:
            run.bold = True
        if seg.italic:
            run.italic = True
        if font is not None:
            _set_run_font(run, *font)
    return paragraph


def emit_pending(
    rc: RenderContext, block: Block, detail: str, status: str = PENDING_STATUS
) -> ComponentResult:
    """Parágrafo-marcador visível para o QA e ComponentResult não-OK."""
    marker = PENDING_MARKER.format(block_id=block.block_id)
    emit_paragraph(rc, ParagraphSpec([Segment(marker)]))
    return rc.record(ComponentResult(block.block_id, status, detail=detail,
                                     facts={"marker": marker, "class": block.cls}))


# --- tabela (ENC_SIGNATURE_TABLE: única tabela nativa do documento) ------------------------
def _parse_font(text: str | None) -> tuple[str | None, float | None, bool]:
    if not text:
        return None, None, False
    match = re.match(r"^(?P<name>.+?)\s+(?P<size>\d+(?:[.,]\d+)?)\s*pt(?P<rest>.*)$", text)
    if not match:
        raise BlockModelError(f"fonte ilegível: {text!r}")
    return (match.group("name"), float(match.group("size").replace(",", ".")),
            "negrito" in match.group("rest"))


def _cell_borders(tc: Any, text: str | None) -> None:
    if not text:
        return
    tcpr = tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for side, val, size, color in re.findall(
        r"\b(top|left|bottom|right)\s+(single|double|dotted|dashed|nil|none)\s+sz(\d+)\s+cor\s+"
        r"([0-9A-Fa-f]{6})", text
    ):
        edge = OxmlElement(f"w:{side}")
        edge.set(qn("w:val"), val)
        edge.set(qn("w:sz"), size)
        edge.set(qn("w:space"), "0")
        edge.set(qn("w:color"), color.upper())
        borders.append(edge)
    if not len(borders):
        raise BlockModelError(f"borda ilegível: {text!r}")
    tcpr.append(borders)


def render_table(rc: RenderContext, block: Block, values: dict[str, Any], used: set[str]) -> Any:
    spec = block.raw["table"]
    tbl_text = str(spec.get("tblPr") or "")
    width = re.search(r"(\d+)\s*twips", tbl_text)
    if not width:
        raise BlockModelError(f"{block.block_id}: largura da grade ausente em tblPr")
    width_twips = int(width.group(1))
    rows = sorted((k for k in spec if re.match(r"^row\d+$", k)), key=lambda k: int(k[3:]))
    # resolve tudo antes de tocar no documento: valor faltando não deixa tabela pela metade
    texts = {
        (key, i): (fill(p["text_template"], values, block.block_id, used)
                   if "text_template" in p else str(p.get("text", "")))
        for key in rows for i, p in enumerate(spec[key].get("paragraphs") or [])
    }
    table = rc.document.add_table(rows=len(rows), cols=1)
    tbl = table._tbl
    tbl_jc = re.match(r"^\s*jc\s+(left|center|right)", tbl_text)
    if tbl_jc:
        table.alignment = {"left": WD_TABLE_ALIGNMENT.LEFT, "center": WD_TABLE_ALIGNMENT.CENTER,
                           "right": WD_TABLE_ALIGNMENT.RIGHT}[tbl_jc.group(1)]
    for grid_col in tbl.tblGrid.findall(qn("w:gridCol")):
        grid_col.set(qn("w:w"), str(width_twips))
    row_jc = re.search(r"linhas\s+jc\s+(left|center|right)", tbl_text)
    for index, key in enumerate(rows):
        row_spec = spec[key]
        row = table.rows[index]
        if row_jc:
            trpr = row._tr.get_or_add_trPr()
            jc = OxmlElement("w:jc")
            jc.set(qn("w:val"), row_jc.group(1))
            trpr.append(jc)
        cell = row.cells[0]
        cell.width = Twips(width_twips)
        _cell_borders(cell._tc, row_spec.get("cell_border"))
        first = cell.paragraphs[0]
        for p_index, para in enumerate(row_spec.get("paragraphs") or []):
            text = texts[(key, p_index)]
            name, size, bold = _parse_font(para.get("font"))
            segments = standardize_segments([Segment(text, bold=bold)]) if text else []
            pspec = ParagraphSpec(segments, StyleSpec(jc=para.get("jc")))
            new = emit_paragraph(rc, pspec, container=cell, font=(name, size))
            if p_index == 0:
                first._p.addnext(new._p)
                first._p.getparent().remove(first._p)
                first = new
    return table


# --- registro e renderização ---------------------------------------------------------------
BlockRenderer = Callable[[RenderContext, Block, dict[str, Any]], ComponentResult | None]
BLOCK_RENDERERS: dict[str, BlockRenderer] = {}


def register_block_renderer(block_id: str) -> Callable[[BlockRenderer], BlockRenderer]:
    """Decorador: `@register_block_renderer("P2.4_RM")`. O renderizador decide a presença."""

    def decorator(func: BlockRenderer) -> BlockRenderer:
        BLOCK_RENDERERS[block_id] = func
        return func

    return decorator


def render_with_engine(
    rc: RenderContext,
    block: Block,
    values: dict[str, Any],
    *,
    check_presence: bool = True,
    page_break_before: bool = False,
    fallbacks: dict[str, str] | None = None,
) -> ComponentResult:
    """Caminho do motor (sem consultar o registro). Erros de valor sobem como MissingValueError."""
    if check_presence:
        condition = presence_mod.parse_condition(block.presence, block.block_id, block.product,
                                                 fallbacks)
        if not presence_mod.evaluate(condition, rc):
            return rc.record(ComponentResult(block.block_id, "SKIPPED",
                                             detail=f"presença falsa: {condition}",
                                             facts={"presence": str(condition)}))
    used: set[str] = set()
    facts: dict[str, Any] = {"class": block.cls}
    if block.derived_from:
        facts["derived_from"] = block.derived_from
    if "table" in block.raw and block.cls in ENGINE_CLASSES:
        table = render_table(rc, block, values, used)
        facts["text"] = "\n".join(c.text for row in table.rows for c in row.cells)
    else:
        specs = build_paragraphs(block, values, used)
        for spec in specs:
            require_style(rc, spec.style.style_id if spec.style.style_id != "Normal" else None)
        if page_break_before and specs:
            specs[0].page_break_before = True
        list_key = parse_style(block.style).list_key
        num_id = new_list_instance(rc, list_key) if list_key else None
        for spec in specs:
            spec_num = num_id if spec.style.list_key else None
            emit_paragraph(rc, spec, spec_num)
        facts["text"] = "\n".join(s.text for s in specs)
        facts["style"] = parse_style(block.style).style_id
        facts["bold"] = [s.text for spec in specs for s in spec.segments if s.bold]
        if num_id is not None:
            facts["numId"] = num_id
    facts["values"] = {name: str(values[name]) for name in sorted(used)}
    detail = "derivado de " + block.derived_from if block.derived_from else ""
    return rc.record(ComponentResult(block.block_id, "OK", detail=detail, facts=facts))


def render_block(
    rc: RenderContext,
    block: Block,
    values: dict[str, Any],
    *,
    check_presence: bool = True,
    page_break_before: bool = False,
    fallbacks: dict[str, str] | None = None,
) -> ComponentResult:
    """Emite um bloco: registro > motor (FIXED_TEXT/SOURCE_VERBATIM/TEMPLATE) > pendente."""
    renderer = BLOCK_RENDERERS.get(block.block_id)
    if renderer is not None:
        result = renderer(rc, block, values)
        if result is None:
            result = rc.record(ComponentResult(block.block_id, "OK", detail="renderizador"))
        return result
    if block.cls in DELEGATED_CLASSES:
        return emit_pending(rc, block, f"sem renderizador registrado ({block.cls})")
    if block.cls not in ENGINE_CLASSES:
        raise BlockModelError(f"{block.block_id}: classe desconhecida {block.cls!r}")
    try:
        check_engine_shape(block)
    except UnsupportedBlockError as exc:
        return emit_pending(rc, block, f"sem renderizador registrado: {exc}")
    return render_with_engine(rc, block, values, check_presence=check_presence,
                              page_break_before=page_break_before, fallbacks=fallbacks)
