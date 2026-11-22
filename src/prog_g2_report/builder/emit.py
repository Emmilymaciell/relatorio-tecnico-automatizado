"""Emissão de `BlockText` (estrutura textual pura) em parágrafos python-docx.

CONTEÚDO chega pronto do renderizador (`render.blocktext.BlockText`, ou objeto com a mesma
forma, como o `BlockText` do 2.1); aqui só se aplica a REPRESENTAÇÃO, pelo motor do builder T
(`builder.blocks`):

    estilo        `Paragraph.style` (styleId; 'Normal' = sem w:pStyle), conferido no documento
    negrito/itál. `Segment.bold` / `Segment.italic`, um run por segmento
    alinhamento   `Paragraph.align` (left | center | right | both)
    listas        definição = `Paragraph.numbering` ('numId_29' -> `LIST_DEFINITIONS['29']`); sem
                  ela, a do `style` do bloco em `config/g2_content_blocks.yaml` ('PargrafodaLista +
                  numId 35 lvl 0'); `list_style='bullet'` sem nada disso = marcador simples.
                  Uma instância `<w:num>` NOVA por `list_key` dentro do bloco
                  (`p24_blocks.yaml common.numbering.restart`): cada lista recomeça.
    imagens       `kind == 'image_slot'`: `ref` = '<prefixo>[:<chave>]' resolvido por
                  `IMAGE_PROVIDERS[<prefixo>](rc, ref) -> ImageSpec | None`. Sem provedor (ou
                  provedor devolvendo None) -> parágrafo-marcador "[PENDENTE: <ref>]" e
                  ComponentResult `IMAGE:<ref>` com status PENDING.

Status do bloco: o do `BlockText` (OK | SKIPPED | PENDING_HUMAN | PENDING | FAILED). SKIPPED não
emite nada; um bloco não-OK sem parágrafos emite o marcador "[PENDENTE: <block_id>]".
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from docx.shared import Cm, Pt

from prog_g2_report.builder.blocks import (
    LIST_DEFINITIONS,
    PENDING_MARKER,
    Block,
    BlockModelError,
    ParagraphSpec,
    StyleSpec,
    emit_paragraph,
    new_list_instance,
    parse_style,
)
from prog_g2_report.builder.blocks import Segment as EngineSegment
from prog_g2_report.builder.context import ComponentResult, RenderContext
from prog_g2_report.render.blocktext import numbering_key
from prog_g2_report.render.docx_emf import add_emf_picture

PENDING = "PENDING"          # dependência de ambiente/implementação (não é entrada humana)
OK_STATUSES = frozenset({"OK", "SKIPPED"})


# --------------------------------------------------------------------------- imagens
@dataclass(frozen=True)
class ImageSpec:
    """Uma imagem pronta para o documento. `fmt` = png | jpeg | emf."""

    data: bytes
    width_cm: float
    fmt: str = "png"
    name: str = "image.png"
    align: str | None = None          # jc do parágrafo da imagem

    @property
    def sha1(self) -> str:
        return hashlib.sha1(self.data).hexdigest()


ImageProvider = Callable[[RenderContext, str], ImageSpec | None]
IMAGE_PROVIDERS: dict[str, ImageProvider] = {}


def register_image_provider(prefix: str) -> Callable[[ImageProvider], ImageProvider]:
    """Decorador: `@register_image_provider("P2.2_ROAD_DASHBOARD")`."""

    def decorator(func: ImageProvider) -> ImageProvider:
        IMAGE_PROVIDERS[prefix] = func
        return func

    return decorator


def ref_prefix(ref: str) -> str:
    return ref.split(":", 1)[0]


def ref_key(ref: str) -> str | None:
    return ref.split(":", 1)[1] if ":" in ref else None


def insert_image(rc: RenderContext, image: ImageSpec, paragraph: Any = None,
                 spacing_zero: bool = False) -> Any:
    """Imagem inline num run novo de `paragraph` (criado se None). EMF pelo `docx_emf`."""
    if paragraph is None:
        paragraph = rc.document.add_paragraph()
        if image.align:
            paragraph.paragraph_format.alignment = _alignment(image.align)
        if spacing_zero:
            fmt = paragraph.paragraph_format
            fmt.space_before = Pt(0)
            fmt.space_after = Pt(0)
            fmt.line_spacing = 1.0
    if image.width_cm <= 0:
        raise ValueError(f"largura inválida para {image.name}: {image.width_cm}")
    if image.fmt == "emf":
        add_emf_picture(paragraph, image.data, image.width_cm, name=image.name)
    else:
        paragraph.add_run().add_picture(io.BytesIO(image.data), width=Cm(image.width_cm))
    return paragraph


def _alignment(value: str) -> Any:
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    return {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
            "right": WD_ALIGN_PARAGRAPH.RIGHT, "both": WD_ALIGN_PARAGRAPH.JUSTIFY}[value]


def emit_marker(rc: RenderContext, label: str) -> str:
    """Parágrafo-marcador visível (o QA procura "[PENDENTE:")."""
    marker = PENDING_MARKER.format(block_id=label)
    emit_paragraph(rc, ParagraphSpec([EngineSegment(marker)]))
    return marker


def emit_image_slot(rc: RenderContext, ref: str,
                    providers: Mapping[str, ImageProvider] | None = None) -> ComponentResult:
    """Resolve e insere a imagem do slot; sem provedor, marcador + PENDING."""
    registry = IMAGE_PROVIDERS if providers is None else providers
    provider = registry.get(ref_prefix(ref))
    component_id = f"IMAGE:{ref}"
    if provider is None:
        marker = emit_marker(rc, ref)
        return rc.record(ComponentResult(component_id, PENDING,
                                         detail=f"sem provedor de imagem para '{ref_prefix(ref)}'",
                                         facts={"marker": marker}))
    try:
        image = provider(rc, ref)
    except Exception as exc:  # o provedor falhou: o documento segue, o resultado acusa
        marker = emit_marker(rc, ref)
        return rc.record(ComponentResult(component_id, "FAILED",
                                         detail=f"{type(exc).__name__}: {exc}",
                                         facts={"marker": marker}))
    if image is None:
        marker = emit_marker(rc, ref)
        return rc.record(ComponentResult(component_id, PENDING, detail="provedor sem imagem",
                                         facts={"marker": marker}))
    insert_image(rc, image)
    return rc.record(ComponentResult(component_id, "OK", detail=image.name, facts={
        "sha1": image.sha1, "width_cm": image.width_cm, "format": image.fmt}))


# --------------------------------------------------------------------------- parágrafos
def _get(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default)


def _list_definition(paragraph: Any, block: Block | None) -> str | None:
    """Chave de LIST_DEFINITIONS do parágrafo (ver docstring do módulo)."""
    key = numbering_key(_get(paragraph, "numbering"))
    if key:
        return key
    if block is not None and block.style:
        try:
            block_key = parse_style(block.style).list_key
        except BlockModelError:
            block_key = None
        if block_key:
            return block_key
    if _get(paragraph, "list_style") == "bullet":
        return "bullet"
    return None


def paragraph_spec(paragraph: Any, list_key: str | None) -> ParagraphSpec:
    segments = [EngineSegment(s.text, bold=bool(_get(s, "bold", False)),
                              italic=bool(_get(s, "italic", False)))
                for s in _get(paragraph, "segments", ()) if s.text]
    style = _get(paragraph, "style") or "Normal"
    level = _get(paragraph, "level", _get(paragraph, "list_level"))
    if level is None and list_key is not None:
        level = 0
    return ParagraphSpec(segments, StyleSpec(style_id=style, list_key=list_key,
                                             ilvl=int(level or 0), jc=_get(paragraph, "align")))


def emit_blocktext(
    rc: RenderContext,
    block: Block | None,
    blocktext: Any,
    *,
    providers: Mapping[str, ImageProvider] | None = None,
    component_id: str | None = None,
    page_break_before: bool = False,
) -> ComponentResult:
    """Emite `blocktext` no fim do documento e registra o ComponentResult do bloco.

    `block` (de `builder.blocks.load_blocks`) só fornece a lista padrão do bloco; pode ser None.
    """
    block_id = component_id or _get(blocktext, "block_id") or (block.block_id if block else "?")
    status = _get(blocktext, "status", "OK") or "OK"
    paragraphs = list(_get(blocktext, "paragraphs", ()) or ())
    warnings = list(_get(blocktext, "warnings", ()) or ())
    facts: dict[str, Any] = dict(_get(blocktext, "facts", {}) or {})
    warnings += [w for w in facts.get("warnings", ()) if w not in warnings]
    detail = _get(blocktext, "detail", "") or ""
    if status == "SKIPPED" and not paragraphs:
        return rc.record(ComponentResult(block_id, "SKIPPED", detail=detail or "ausente",
                                         facts=facts))
    if not paragraphs:
        marker = emit_marker(rc, block_id)
        facts["marker"] = marker
        return rc.record(ComponentResult(block_id, status if status != "OK" else PENDING,
                                         detail=detail or "; ".join(warnings) or "sem texto",
                                         facts=facts))
    instances: dict[tuple[str, str], int] = {}
    images: list[str] = []
    bold: list[str] = []
    first = True
    for paragraph in paragraphs:
        if _get(paragraph, "kind", "text") == "image_slot":
            result = emit_image_slot(rc, paragraph.ref, providers)
            images.append(f"{paragraph.ref}={result.status}")
            first = False
            continue
        list_def = None
        in_list = (_get(paragraph, "level", _get(paragraph, "list_level")) is not None
                   or _get(paragraph, "list_style") is not None
                   or _get(paragraph, "numbering") is not None)
        if in_list:
            list_def = _list_definition(paragraph, block)
            if list_def not in LIST_DEFINITIONS:
                raise BlockModelError(f"{block_id}: lista sem definição: {list_def!r}")
        spec = paragraph_spec(paragraph, list_def)
        if first and page_break_before:
            spec.page_break_before = True
        first = False
        num_id = None
        if list_def is not None:
            instance = (str(_get(paragraph, "list_key") or _get(paragraph, "list_id")
                            or block_id), list_def)
            if instance not in instances:
                instances[instance] = new_list_instance(rc, list_def)
            num_id = instances[instance]
        emit_paragraph(rc, spec, num_id)
        bold += [s.text for s in spec.segments if s.bold]
    facts.update({
        "text": "\n".join(p.text for p in paragraphs if _get(p, "kind", "text") != "image_slot"),
        "bold": bold,
        "numIds": sorted(set(instances.values())),
    })
    if images:
        facts["images"] = images
    if warnings:
        facts["warnings"] = warnings
    if status not in OK_STATUSES and not detail:
        detail = "; ".join(warnings)
    return rc.record(ComponentResult(block_id, status, detail=detail, facts=facts))
