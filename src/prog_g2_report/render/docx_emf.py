"""Inserção de metarquivo EMF inline num DOCX criado do zero (DEC-010 §5).

Puro python-docx/lxml: cria a parte OPC `/word/media/emfN.emf` (`image/x-emf`), relaciona-a ao
documento (`RT.IMAGE`) e monta um `wp:inline` com `pic:pic`. Não abre Word nem Excel.

Geometria (modelo `control_of_products.width_cm`, 17,5 cm no rascunho):

- a largura é a do modelo; a altura sai do **aspecto do EMR_HEADER**;
- `aspect="frame"` (padrão) usa `rclFrame` convertido para pixels do dispositivo de referência
  (`szlDevice` / `szlMillimeters`). É o que o Word faz ao colar: nos 12 EMFs do Relatório G2
  nº 14 o `wp:extent` histórico difere desse aspecto em ≤ 0,12 %;
- `aspect="bounds"` usa `rclBounds` (pixels inclusivos). Serve quando o desenho não transborda
  o intervalo; nos recortes cujo texto vaza à direita (`rclBounds` 1253 px contra 1232 px de
  frame) erra a altura em ~1,7 % contra o histórico, por isso não é o padrão.
"""

from __future__ import annotations

import struct
from typing import Any, NamedTuple

EMR_HEADER = 1
EMF_SIGNATURE = b" EMF"
EMU_PER_CM = 360_000
_HEADER_MIN_SIZE = 88  # até szlMillimeters inclusive (MS-EMF 2.3.4.2)


class EmfHeader(NamedTuple):
    """Campos do EMR_HEADER que importam para a geometria.

    `left..bottom` = `rclBounds` (pixels do dispositivo, inclusivos);
    `frame_*_mm` = `rclFrame` em milímetros (o arquivo guarda centésimos de milímetro).
    """

    left: int
    top: int
    right: int
    bottom: int
    frame_left_mm: float
    frame_top_mm: float
    frame_right_mm: float
    frame_bottom_mm: float
    device_px: tuple[int, int]
    device_mm: tuple[int, int]

    @property
    def frame_width_mm(self) -> float:
        return self.frame_right_mm - self.frame_left_mm

    @property
    def frame_height_mm(self) -> float:
        return self.frame_bottom_mm - self.frame_top_mm

    @property
    def frame_cm(self) -> tuple[float, float]:
        return (round(self.frame_width_mm / 10, 3), round(self.frame_height_mm / 10, 3))

    def aspect(self, mode: str = "frame") -> float:
        """altura / largura do desenho, no critério pedido."""
        if mode == "bounds":
            width = self.right - self.left + 1
            height = self.bottom - self.top + 1
        elif mode == "frame":
            px_x, px_y = self.device_px
            mm_x, mm_y = self.device_mm
            if min(px_x, px_y, mm_x, mm_y) <= 0:   # dispositivo ausente: frame puro
                px_x = px_y = mm_x = mm_y = 1
            width = self.frame_width_mm * px_x / mm_x
            height = self.frame_height_mm * px_y / mm_y
        else:
            raise ValueError(f"aspecto desconhecido: {mode!r} (use 'frame' ou 'bounds')")
        if width <= 0 or height <= 0:
            raise ValueError("EMF com dimensões nulas no cabeçalho")
        return height / width


def emf_bounds(emf_bytes: bytes) -> EmfHeader:
    """Lê o EMR_HEADER. Levanta `ValueError` se os bytes não forem um EMF."""
    data = bytes(emf_bytes)
    if len(data) < _HEADER_MIN_SIZE:
        raise ValueError("bytes curtos demais para um EMF")
    rtype, rsize = struct.unpack_from("<II", data, 0)
    if rtype != EMR_HEADER or data[40:44] != EMF_SIGNATURE or rsize < _HEADER_MIN_SIZE:
        raise ValueError("não é um EMF (EMR_HEADER/assinatura ' EMF' ausentes)")
    left, top, right, bottom = struct.unpack_from("<4i", data, 8)
    frame = struct.unpack_from("<4i", data, 24)
    device_px = struct.unpack_from("<2i", data, 72)
    device_mm = struct.unpack_from("<2i", data, 80)
    return EmfHeader(left, top, right, bottom, *(v / 100 for v in frame),
                     tuple(device_px), tuple(device_mm))


# Registros usados para ler o texto desenhado (MS-EMF 2.3.5.8, 2.3.8.4, 2.3.5.4).
EMR_EXTCREATEFONTINDIRECTW = 82
EMR_SELECTOBJECT = 37
EMR_DELETEOBJECT = 40
EMR_EXTTEXTOUTW = 84
_STOCK_OBJECT = 0x80000000
BOLD_WEIGHT = 700


class EmfTextRun(NamedTuple):
    """Um EMR_EXTTEXTOUTW com a fonte (LOGFONT) selecionada no momento do desenho."""

    text: str
    x: int                  # ptlReference (unidades lógicas)
    y: int
    weight: int             # lfWeight (400 normal, 700 negrito; 0 = padrão/estoque)
    italic: bool
    face: str

    @property
    def bold(self) -> bool:
        return self.weight >= BOLD_WEIGHT


def emf_text_runs(emf_bytes: bytes) -> list[EmfTextRun]:
    """Texto de um EMF com o peso da fonte ativa em cada desenho.

    Lê EXTCREATEFONTINDIRECTW (tabela de objetos), SELECTOBJECT/DELETEOBJECT (fonte ativa) e
    EXTTEXTOUTW (texto UTF-16). Objeto de estoque selecionado = peso 0 (desconhecido). Serve
    para conferir a tipografia de um recorte do Controle de Produtos (ex.: só o cabeçalho em
    negrito, `CONTROL_OF_PRODUCTS.render_params.normalize_data_font`).
    """
    data = bytes(emf_bytes)
    emf_bounds(data)
    fonts: dict[int, tuple[int, bool, str]] = {}
    current: tuple[int, bool, str] = (0, False, "")
    out: list[EmfTextRun] = []
    off = 0
    while off + 8 <= len(data):
        rtype, rsize = struct.unpack_from("<II", data, off)
        if rsize < 8 or off + rsize > len(data):
            break
        if rtype == EMR_EXTCREATEFONTINDIRECTW and rsize >= 12 + 92:
            handle = struct.unpack_from("<I", data, off + 8)[0]
            weight = struct.unpack_from("<i", data, off + 12 + 16)[0]
            italic = bool(data[off + 12 + 20])
            face = data[off + 12 + 28: off + 12 + 92].decode("utf-16-le", "replace")
            fonts[handle] = (weight, italic, face.split("\x00", 1)[0])
        elif rtype == EMR_SELECTOBJECT:
            handle = struct.unpack_from("<I", data, off + 8)[0]
            if handle in fonts:
                current = fonts[handle]
            elif handle & _STOCK_OBJECT and 10 <= (handle & 0xFF) <= 17:   # fontes de estoque
                current = (0, False, "")
        elif rtype == EMR_DELETEOBJECT:
            fonts.pop(struct.unpack_from("<I", data, off + 8)[0], None)
        elif rtype == EMR_EXTTEXTOUTW and rsize >= 76:
            x, y, nchars, offstr = struct.unpack_from("<iiII", data, off + 36)
            raw = data[off + offstr: off + offstr + 2 * nchars]
            out.append(EmfTextRun(raw.decode("utf-16-le", "replace"), x, y, *current))
        off += rsize
    return out


def emf_display_height_cm(emf_bytes: bytes, width_cm: float, aspect: str = "frame") -> float:
    """Altura (cm) com que o EMF aparece no DOCX quando inserido com `width_cm` de largura."""
    width_emu = round(width_cm * EMU_PER_CM)
    return round(width_emu * emf_bounds(emf_bytes).aspect(aspect)) / EMU_PER_CM


def add_emf_picture(paragraph: Any, emf_bytes: bytes, width_cm: float = 17.5, *,
                    name: str = "controle_de_produtos.emf", aspect: str = "frame") -> None:
    """Acrescenta o EMF como imagem inline num run novo de `paragraph` (python-docx).

    `width_cm` vem do modelo (`control_of_products.width_cm`); o default 17,5 cm é o do
    rascunho do modelo e do Relatório G2 nº 14 (`wp:extent cx=6301105`).
    """
    from docx.opc.constants import CONTENT_TYPE as CT
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part
    from docx.oxml.shape import CT_Inline
    from docx.shared import Emu

    if width_cm <= 0:
        raise ValueError("width_cm deve ser positivo")
    header = emf_bounds(emf_bytes)
    doc_part = paragraph.part
    package = doc_part.package
    partname = package.next_partname("/word/media/emf%d.emf")
    part = Part(PackURI(partname), CT.X_EMF, bytes(emf_bytes), package)
    r_id = doc_part.relate_to(part, RT.IMAGE)
    width = Emu(round(width_cm * EMU_PER_CM))
    height = Emu(round(width * header.aspect(aspect)))
    inline = CT_Inline.new_pic_inline(doc_part.next_id, r_id, name, width, height)
    paragraph.add_run()._r.add_drawing(inline)
