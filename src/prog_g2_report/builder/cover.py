"""Capa do Relatório G2 (componente COVER do modelo), conforme DEC-011 opção (b').

    fundo   imagem sem texto, composta UMA vez das mídias internas do slide de capa
            (ooxml_base.cover.background.layers) e ancorada atrás do texto, página inteira
            com sangria (ooxml_base.cover.bleed_twips);
    textos  parágrafos do Word em quadros com posição absoluta na página (w:framePr):
            fixos (título) e variáveis (número do relatório e data de emissão), vindos de
            ReportContext.report_number e ReportContext.issue_date (ooxml_base.cover.texts).

O slide (19,05 × 27,517 cm) é mapeado na página + sangria pela mesma transformação para fundo
e textos, como a prévia histórica (esticada à página inteira; WAVE1 §I).
A seção 0 tem titlePg sem referência 'first' (foundation.apply_header_footer): capa sem
cabeçalho e rodapé (DEC-011 §3).
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

from prog_g2_report.builder.context import ComponentResult, RenderContext, ReportContext
from prog_g2_report.builder.foundation import build_element, section_config
from prog_g2_report.report_id import MONTH_NAMES

EMU_PER_INCH = 914400
EMU_PER_TWIP = 635
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


# ------------------------------------------------------------------------------- textos
def format_issue_date(issue_date: Any, template: str) -> str:
    """ooxml_base.cover.texts[issue_date].template, ex.: '08 de Setembro de 2026'.
    O nome do mês vem de prog_g2_report.report_id.MONTH_NAMES (fonte única do vocabulário)."""
    return template.format(day=issue_date.day, month_name=MONTH_NAMES[issue_date.month],
                           year=issue_date.year)


def cover_field_values(report: ReportContext, cover_cfg: Mapping[str, Any]) -> dict[str, str]:
    """Textos variáveis da capa (kind: field) a partir do contexto. Nada do nº 14 fixo aqui."""
    values: dict[str, str] = {}
    for spec in cover_cfg["texts"]:
        if spec["kind"] != "field":
            continue
        if spec["id"] == "report_number":
            values["report_number"] = spec["template"].format(report_number=report.report_number)
        elif spec["id"] == "issue_date":
            values["issue_date"] = format_issue_date(report.issue_date, spec["template"])
        else:
            raise ValueError(f"campo de capa sem regra: {spec['id']}")
    return values


# ---------------------------------------------------------------------------- mapeamento
@dataclass(frozen=True)
class SlideToPage:
    """Transformação slide (EMU) -> página (twips). Anisotrópica, como a prévia histórica, que
    estica o slide até a página inteira. A sangria não altera a escala: o fundo é estendido
    `bleed` twips além de cada borda (bordas replicadas) e ancorado em (-bleed, -bleed)."""

    page_w: int          # twips
    page_h: int
    bleed: int           # twips além de cada borda
    slide_w: int         # EMU
    slide_h: int

    @property
    def sx(self) -> float:   # EMU de página por EMU de slide (adimensional)
        return self.page_w * EMU_PER_TWIP / self.slide_w

    @property
    def sy(self) -> float:
        return self.page_h * EMU_PER_TWIP / self.slide_h

    def x(self, emu: float) -> int:
        return round(emu * self.sx / EMU_PER_TWIP)

    def y(self, emu: float) -> int:
        return round(emu * self.sy / EMU_PER_TWIP)

    def width(self, emu: float) -> int:
        return round(emu * self.sx / EMU_PER_TWIP)


def slide_mapping(cfg: Mapping[str, Any]) -> SlideToPage:
    """ooxml_base.cover.slide_size_emu + bleed_twips sobre ooxml_base.page.sections[0].pgSz."""
    cover = cfg["cover"]
    size = section_config(cfg, 0)["pgSz"]
    slide_w, slide_h = cover["slide_size_emu"]
    return SlideToPage(size["w"], size["h"], cover["bleed_twips"], slide_w, slide_h)


def _half_points(size_pt: float, scale: float) -> int:
    return max(2, round(size_pt * scale * 2))


# ------------------------------------------------------------------------- composição
def _px(emu: float, dpi: int) -> float:
    return emu / EMU_PER_INCH * dpi


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = str(hex_color)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _svg_to_rgba(data: bytes, width: int, height: int) -> Any:
    import pymupdf
    from PIL import Image

    doc = pymupdf.open(stream=data, filetype="svg")
    try:
        page = doc[0]
        matrix = pymupdf.Matrix(width / page.rect.width, height / page.rect.height)
        pix = page.get_pixmap(matrix=matrix, alpha=True)
        image = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
    finally:
        doc.close()
    if image.size != (width, height):
        image = image.resize((width, height), Image.LANCZOS)
    return image


def _extend_edges(image: Any, margin_x: int, margin_y: int) -> Any:
    """Sangria: replica as bordas do slide `margin` px para fora (fica fora da página)."""
    from PIL import Image

    if margin_x <= 0 and margin_y <= 0:
        return image
    w, h = image.size
    out = Image.new(image.mode, (w + 2 * margin_x, h + 2 * margin_y))
    out.paste(image, (margin_x, margin_y))
    if margin_x > 0:
        out.paste(image.crop((0, 0, 1, h)).resize((margin_x, h)), (0, margin_y))
        out.paste(image.crop((w - 1, 0, w, h)).resize((margin_x, h)), (margin_x + w, margin_y))
    if margin_y > 0:
        full_w = w + 2 * margin_x
        out.paste(out.crop((0, margin_y, full_w, margin_y + 1)).resize((full_w, margin_y)), (0, 0))
        out.paste(out.crop((0, margin_y + h - 1, full_w, margin_y + h)).resize((full_w, margin_y)),
                  (0, margin_y + h))
    return out


def compose_background(assets_dir: Path, cover_cfg: Mapping[str, Any], out_path: Path,
                       mapping: SlideToPage | None = None) -> Path:
    """Compõe o fundo sem texto (ooxml_base.cover.background.layers) no tamanho do slide e,
    com `mapping`, estende as bordas pela sangria (ooxml_base.cover.bleed_twips).

    Camadas: foto recortada (srcRect em 1/1000 %), véu accent1 com alfa, filetes, logos SVG
    rasterizados por PyMuPDF. Saída PNG determinística (mesmas entradas -> mesmo sha1).
    """
    from PIL import Image, ImageDraw

    background = cover_cfg["background"]
    dpi = int(background["dpi"])
    slide_w, slide_h = cover_cfg["slide_size_emu"]
    width, height = round(_px(slide_w, dpi)), round(_px(slide_h, dpi))
    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    for layer in background["layers"]:
        kind = layer["kind"]
        if kind == "photo":
            photo = Image.open(assets_dir / layer["file"]).convert("RGB")
            bw, bh = photo.size
            rect = layer["src_rect"]
            left, top = rect["l"] / 100000 * bw, rect["t"] / 100000 * bh
            right, bottom = (1 - rect["r"] / 100000) * bw, (1 - rect["b"] / 100000) * bh
            src = Image.new("RGB", (round(right - left), round(bottom - top)), (255, 255, 255))
            crop = photo.crop((max(0, round(left)), max(0, round(top)),
                               min(bw, round(right)), min(bh, round(bottom))))
            src.paste(crop, (max(0, -round(left)), max(0, -round(top))))
            ox, oy = layer["pos"]
            ex, ey = layer["size"]
            x0, y0 = round(_px(ox, dpi)), round(_px(oy, dpi))
            x1, y1 = round(_px(ox + ex, dpi)), round(_px(oy + ey, dpi))
            resized = src.resize((x1 - x0, y1 - y0), Image.LANCZOS).convert("RGBA")
            canvas.paste(resized, (x0, y0))
        elif kind == "rect":
            ox, oy = layer["pos"]
            ex, ey = layer["size"]
            veil = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            alpha = round(float(layer["alpha"]) * 255)
            ImageDraw.Draw(veil).rectangle(
                [_px(ox, dpi), _px(oy, dpi), _px(ox + ex, dpi), _px(oy + ey, dpi)],
                fill=(*_rgb(layer["color"]), alpha))
            canvas = Image.alpha_composite(canvas, veil)
        elif kind == "hline":
            half = layer["width"] / 2
            ImageDraw.Draw(canvas).rectangle(
                [_px(layer["x"], dpi), _px(layer["y"] - half, dpi),
                 _px(layer["x"] + layer["length"], dpi), _px(layer["y"] + half, dpi)],
                fill=(*_rgb(layer["color"]), 255))
        elif kind == "svg":
            ox, oy = layer["pos"]
            ex, ey = layer["size"]
            logo = _svg_to_rgba((assets_dir / layer["file"]).read_bytes(),
                                round(_px(ex, dpi)), round(_px(ey, dpi)))
            canvas.alpha_composite(logo, (round(_px(ox, dpi)), round(_px(oy, dpi))))
        else:
            raise ValueError(f"camada de capa desconhecida: {kind}")
    if mapping is not None and mapping.bleed > 0:
        canvas = _extend_edges(canvas, round(mapping.bleed * width / mapping.page_w),
                               round(mapping.bleed * height / mapping.page_h))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    from PIL import PngImagePlugin

    info = PngImagePlugin.PngInfo()
    info.add_text(SIGNATURE_KEY, layers_signature(cover_cfg, mapping))
    buffer = io.BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG", optimize=True, dpi=(dpi, dpi),
                               pnginfo=info)
    out_path.write_bytes(buffer.getvalue())
    return out_path


SIGNATURE_KEY = "prog_cover_layers_sha1"


def layers_signature(cover_cfg: Mapping[str, Any], mapping: SlideToPage | None = None) -> str:
    """sha1 das entradas da composição (camadas, dpi, slide, sangria): o fundo pré-composto só
    vale se foi gerado com exatamente estas camadas (ooxml_base.cover.background.layers)."""
    import json

    background = cover_cfg["background"]
    payload = {"layers": background["layers"], "dpi": background["dpi"],
               "slide": list(cover_cfg["slide_size_emu"]),
               "bleed": None if mapping is None else [mapping.bleed, mapping.page_w,
                                                      mapping.page_h]}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha1(raw.encode("ascii")).hexdigest()


def _png_signature(path: Path) -> str | None:
    from PIL import Image

    try:
        with Image.open(path) as image:
            value = getattr(image, "text", {}).get(SIGNATURE_KEY)
    except Exception:
        return None
    return None if value is None else str(value)


def resolve_background(assets_dir: Path, cfg: Mapping[str, Any], work_dir: Path) -> Path:
    """Usa o asset `cover_background_composite` de assets_dir se ele foi composto com as camadas
    atuais (assinatura `layers_signature` gravada no PNG); senão compõe em work_dir a partir dos
    assets de origem (cover_photo_background + logos). Um fundo pré-composto antigo (sem
    assinatura ou com outra) nunca é usado: mudar uma camada no modelo muda a capa."""
    cover_cfg = cfg["cover"]
    name = cover_cfg["background"]["file"]
    mapping = slide_mapping(cfg)
    registered = Path(assets_dir) / name
    if registered.exists() and _png_signature(registered) == layers_signature(cover_cfg, mapping):
        return registered
    return compose_background(Path(assets_dir), cover_cfg, Path(work_dir) / name, mapping)


def sha1_of(path: Path) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


# ------------------------------------------------------------------------------ OOXML
_ANCHOR = (
    '<wp:anchor {ns} distT="0" distB="0" distL="0" distR="0" simplePos="0" relativeHeight="0" '
    'behindDoc="1" locked="1" layoutInCell="1" allowOverlap="1">'
    '<wp:simplePos x="0" y="0"/>'
    '<wp:positionH relativeFrom="page"><wp:posOffset>{x}</wp:posOffset></wp:positionH>'
    '<wp:positionV relativeFrom="page"><wp:posOffset>{y}</wp:posOffset></wp:positionV>'
    '<wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/><wp:wrapNone/>'
    '</wp:anchor>'
)


def _anchor_background(paragraph: Any, image: Path, mapping: SlideToPage) -> Any:
    """Imagem inline -> wp:anchor atrás do texto, relativa à página, com sangria."""
    cx = (mapping.page_w + 2 * mapping.bleed) * EMU_PER_TWIP
    cy = (mapping.page_h + 2 * mapping.bleed) * EMU_PER_TWIP
    run = paragraph.add_run()
    inline = run.add_picture(str(image), width=cx, height=cy)._inline
    offset = -mapping.bleed * EMU_PER_TWIP
    anchor = parse_xml(_ANCHOR.format(ns=nsdecls("wp"), x=offset, y=offset, cx=cx, cy=cy))
    for local in ("docPr", "cNvGraphicFramePr"):
        node = inline.find(f"{{{WP_NS}}}{local}")
        if node is not None:
            anchor.append(node)
    anchor.append(inline.find(f"{{{A_NS}}}graphic"))
    inline.getparent().replace(inline, anchor)
    return anchor


def _frame_paragraph(doc: Any, spec: Mapping[str, Any], lines: list[str], mapping: SlideToPage,
                     cover_cfg: Mapping[str, Any]) -> Any:
    """Um quadro (w:framePr) com posição absoluta na página para uma caixa de texto do slide."""
    scale = mapping.sy if cover_cfg.get("font_scale", "vertical") == "vertical" else 1.0
    if spec.get("page_size_pt") is not None:
        # tamanho medido na página publicada (prévia do OLE), sem a escala do slide
        half_points = _half_points(float(spec["page_size_pt"]), 1.0)
    else:
        half_points = _half_points(spec["size_pt"], scale)
    insets = spec["insets"]
    box_x, box_y = spec["box_off"]
    box_w, box_h = spec["box_ext"]
    x = mapping.x(box_x + insets["l"])
    w = mapping.width(box_w - insets["l"] - insets["r"])
    line_pct = spec.get("line_spacing_pct", 100)
    if spec.get("anchor", "top") == "center":
        line_twips = half_points * 10 * cover_cfg["line_height_factor"] * line_pct / 100
        y = round(mapping.y(box_y + box_h / 2) - line_twips * len(lines) / 2)
    else:
        y = mapping.y(box_y + insets["t"])
    paragraph = doc.add_paragraph()
    p_pr = paragraph._p.get_or_add_pPr()
    for child in list(p_pr):
        p_pr.remove(child)
    frame = OxmlElement("w:framePr")
    for key, value in (("w", w), ("hSpace", 0), ("wrap", "around"), ("vAnchor", "page"),
                       ("hAnchor", "page"), ("x", x), ("y", y)):
        frame.set(qn(f"w:{key}"), str(value))
    p_pr.append(frame)
    p_pr.append(build_element("spacing", {"before": 0, "after": 0,
                                          "line": round(240 * line_pct / 100), "lineRule": "auto"}))
    p_pr.append(build_element("jc", "left"))
    r_pr: dict[str, Any] = {
        "rFonts": {"ascii": spec["font"], "hAnsi": spec["font"], "eastAsia": spec["font"],
                   "cs": spec["font"]},
        "b": bool(spec.get("bold")),
        "bCs": bool(spec.get("bold")),
        "color": cover_cfg["color"],
        "sz": half_points,
        "szCs": half_points,
        "lang": {"val": "pt-BR"},
    }
    if cover_cfg.get("char_scale_from_aspect"):
        r_pr["w"] = round(100 * mapping.sx / mapping.sy)
    for i, text in enumerate(lines):
        run = OxmlElement("w:r")
        run.append(build_element("rPr", r_pr))
        if i:
            run.append(OxmlElement("w:br"))
        t = OxmlElement("w:t")
        t.text = text
        run.append(t)
        paragraph._p.append(run)
    return paragraph


def add_cover(doc: Any, report: ReportContext, cfg: Mapping[str, Any],
              background: Path) -> dict[str, Any]:
    """Escreve a capa no início do corpo (deve ser o primeiro conteúdo do documento)."""
    cover = cfg["cover"]
    if doc.element.body.find(qn("w:p")) is not None:
        raise ValueError("a capa deve ser o primeiro conteúdo do documento")
    mapping = slide_mapping(cfg)
    values = cover_field_values(report, cover)
    anchor_paragraph = doc.add_paragraph()
    _anchor_background(anchor_paragraph, background, mapping)
    emitted: dict[str, str] = {}
    for spec in cover["texts"]:
        lines = list(spec["lines"]) if spec["kind"] == "fixed" else [values[spec["id"]]]
        _frame_paragraph(doc, spec, lines, mapping, cover)
        emitted[spec["id"]] = "\n".join(lines)
    if cover.get("page_break_after", True):
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    return {"texts": emitted, "background": str(background), "background_sha1": sha1_of(background)}


def build_cover(ctx: RenderContext, cfg: Mapping[str, Any] | None = None) -> ComponentResult:
    """COVER: fundo (asset ou composição em ctx.work_dir) + textos do contexto.

    `cfg` é o ooxml_base carregado; sem ele, usa ctx.data['ooxml_base'] (o orquestrador carrega).
    """
    base = cfg if cfg is not None else ctx.data.get("ooxml_base")
    if base is None:
        raise KeyError("ooxml_base ausente: passe cfg ou ctx.data['ooxml_base']")
    background = resolve_background(ctx.assets_dir, base, ctx.work_dir)
    facts = add_cover(ctx.document, ctx.report, base, background)
    texts = facts["texts"]
    detail = f"capa: {texts.get('report_number', '')} / {texts.get('issue_date', '')}"
    return ctx.record(ComponentResult("COVER", status="OK", detail=detail, facts=facts))
