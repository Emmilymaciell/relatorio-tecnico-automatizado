# ruff: noqa: N803  -- W/H seguem a notação do YAML (`*_over_W`, `*_over_H`, `canvas.w/h`)
"""Infraestrutura comum dos visuais reconstruídos: canvas canônico, fontes, texto e PNG estável.

Regras de `config/g2_render_rules.yaml` aplicadas aqui:
- `common_placement.scale_rule`: desenha-se no canvas canônico (px do histórico) e multiplica-se
  por k = largura_de_saída / canvas_w. Todas as coordenadas dos renderizadores são canônicas.
- `common_placement.recommended_output_px_width`: 2067 px = 300 dpi a 17,50 cm
  (`common_placement.width_cm`); a tag dpi do PNG é derivada dessas duas chaves.
- `common_placement.format`: PNG RGB.

Defaults técnicos (WAVE1_FINDINGS §L, revisáveis por `rules["render_options"]`):
- família tipográfica "Segoe UI" com fallback "Arial" (Arial Nova não está instalada nesta
  máquina, §L "Ambiente"); a família é parâmetro (`render_options.font_family`);
- canvas de saída de 2067 px de largura;
- saída determinística: sem metadado de data/software no PNG, layout de texto BASIC (não
  depende de libraqm), supersampling fixo e redimensionamento LANCZOS.
"""

from __future__ import annotations

import io
import logging
import math
import unicodedata
from collections.abc import Iterable, Sequence
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# WAVE1_FINDINGS §L: "canvas 2067 px (300 dpi) a 17,50 cm". Usado só se o YAML não trouxer a chave.
DEFAULT_OUT_WIDTH_PX = 2067
DEFAULT_WIDTH_CM = 17.50

DEFAULT_OPTIONS: dict[str, Any] = {
    # WAVE1 §L / tarefa do builder: Segoe UI com fallback Arial; parâmetro de rules.
    "font_family": ("Segoe UI", "Arial"),
    # P2.2_ROAD_DASHBOARDS.historical_variation_not_rule: "tabela em Segoe UI ... só em RD-102A ->
    # unificar (Arial, 3 de 4 páginas)".
    "font_family_table_p22": ("Arial", "Segoe UI"),
    "out_width_px": None,  # None -> common_placement.recommended_output_px_width
    "supersample": 2,  # desenha em 2x e reduz: antialias determinístico de formas
    "logo_png": None,  # caminho do logotipo Programa colorido (gap: asset ainda inexistente)
    "logo_white_png": None,  # caminho do logotipo Programa branco dos títulos do 2.4 (gap idem)
}

WEIGHTS = {"regular": 400, "semibold": 600, "bold": 700}


def load_render_rules(path: str | Path) -> dict[str, Any]:
    """Carrega `config/g2_render_rules.yaml` (ou outro arquivo com a mesma estrutura)."""
    import yaml

    with Path(path).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def render_options(rules: dict[str, Any]) -> dict[str, Any]:
    """Opções técnicas efetivas: DEFAULT_OPTIONS sobrepostos por `rules["render_options"]`."""
    opts = dict(DEFAULT_OPTIONS)
    opts.update(rules.get("render_options") or {})
    placement = rules.get("common_placement") or {}
    if opts["out_width_px"] is None:
        opts["out_width_px"] = int(
            placement.get("recommended_output_px_width", DEFAULT_OUT_WIDTH_PX)
        )
    opts["width_cm"] = float(placement.get("width_cm", DEFAULT_WIDTH_CM))
    for key in ("font_family", "font_family_table_p22"):
        value = opts[key]
        opts[key] = (value,) if isinstance(value, str) else tuple(value)
    return opts


# ---------------------------------------------------------------------------------------------
# Fontes


@cache
def resolve_font_file(families: tuple[str, ...], weight: int) -> str | None:
    """Primeiro arquivo de fonte instalado da lista de famílias, no peso pedido (ou o próximo)."""
    from matplotlib import font_manager

    logger = logging.getLogger("matplotlib.font_manager")
    previous = logger.level
    logger.setLevel(logging.ERROR)
    try:
        for family in families:
            props = font_manager.FontProperties(family=family, style="normal", weight=weight)
            try:
                return font_manager.findfont(props, fallback_to_default=False)
            except ValueError:
                continue
    finally:
        logger.setLevel(previous)
    return None


@cache
def _load_font(families: tuple[str, ...], weight: int, size_px: int) -> ImageFont.FreeTypeFont:
    path = resolve_font_file(families, weight)
    if path is None:
        return ImageFont.load_default(size_px)
    return ImageFont.truetype(path, size_px, layout_engine=ImageFont.Layout.BASIC)


# ---------------------------------------------------------------------------------------------
# Formatação


def fmt_date(value: date | str | None, fmt: str) -> str:
    """Formata data pelo padrão do YAML ("dd/mm/aaaa", "dd/mm/aa"). Texto passa como está."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    pattern = fmt.replace("aaaa", "%Y").replace("aa", "%y").replace("dd", "%d").replace("mm", "%m")
    return value.strftime(pattern)


def fmt_decimal(value: float, decimals: int, strip_zeros: bool = False) -> str:
    """Número em pt-BR (vírgula decimal). `strip_zeros` remove zeros finais e a vírgula órfã."""
    text = f"{value:.{decimals}f}"
    if strip_zeros and "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def rule_key(name: str) -> str:
    """Nome de categoria -> chave do YAML: sem acento, espaço vira "_".

    Ex.: "Em análise" -> "Em_analise" (`palette.donut`).
    """
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return folded.replace(" ", "_")


def lookup(mapping: dict[str, Any], name: str, default: Any = KeyError) -> Any:
    """Busca tolerante a acento e caixa ("RD-102A" acha "RD-102a")."""
    if name in mapping:
        return mapping[name]
    wanted = rule_key(name).casefold()
    for key, value in mapping.items():
        if rule_key(key).casefold() == wanted:
            return value
    if default is KeyError:
        raise KeyError(f"'{name}' ausente em {sorted(mapping)} (config/g2_render_rules.yaml)")
    return default


def em(item: dict[str, Any]) -> float:
    return float(item["em_px"])


def weight_of(item: dict[str, Any], default: str = "regular") -> str:
    return str(item.get("weight", default))


# ---------------------------------------------------------------------------------------------
# Canvas


class Metrics:
    """Medição de texto em px canônicos para uma escala k (sem imagem; usada antes do canvas)."""

    def __init__(self, width: float, *, out_width: int, supersample: int) -> None:
        self.W = float(width)
        self.out_w = int(out_width)
        self.ss = max(1, int(supersample))
        self.k = self.out_w / self.W * self.ss

    # fontes ----------------------------------------------------------------------------------
    def font(
        self, families: Sequence[str], weight: str | int, em_px: float
    ) -> ImageFont.FreeTypeFont:
        w = WEIGHTS[weight] if isinstance(weight, str) else int(weight)
        return _load_font(tuple(families), w, max(1, round(em_px * self.k)))

    def text_width(self, text: str, font: ImageFont.FreeTypeFont) -> float:
        return font.getlength(text) / self.k

    def wrap(self, text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
        """Quebra gulosa por palavra; palavra maior que a largura fica inteira na sua linha."""
        words = text.split()
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if self.text_width(trial, font) <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def fit_font(
        self, text: str, families: Sequence[str], weight: str, em_px: float, max_width: float
    ) -> ImageFont.FreeTypeFont:
        """Fonte no tamanho pedido ou reduzida (passo de 0,5 px) até caber em `max_width`."""
        size = em_px
        font = self.font(families, weight, size)
        while size > 6 and self.text_width(text, font) > max_width:
            size -= 0.5
            font = self.font(families, weight, size)
        return font

    def spaced_width(self, text: str, font: ImageFont.FreeTypeFont, tracking: float) -> float:
        return sum(self.text_width(ch, font) for ch in text) + tracking * max(0, len(text) - 1)


class Canvas(Metrics):
    """Imagem supersampleada com API em px canônicos (origem topo-esquerda)."""

    def __init__(
        self,
        width: float,
        height: float,
        *,
        out_width: int,
        supersample: int,
        width_cm: float,
        background: str,
    ) -> None:
        super().__init__(width, out_width=out_width, supersample=supersample)
        self.H = float(height)
        self.out_h = round(self.out_w * self.H / self.W)
        self.width_cm = width_cm
        self.img = Image.new("RGB", (self.out_w * self.ss, self.out_h * self.ss), background)
        self.draw = ImageDraw.Draw(self.img)

    # conversão -------------------------------------------------------------------------------
    def p(self, v: float) -> float:
        return v * self.k

    def pi(self, v: float) -> int:
        return round(v * self.k)

    def lw(self, width: float) -> int:
        return max(1, round(width * self.k))

    def box(self, x0: float, y0: float, x1: float, y1: float) -> list[int]:
        return [
            self.pi(x0),
            self.pi(y0),
            max(self.pi(x0), self.pi(x1) - 1),
            max(self.pi(y0), self.pi(y1) - 1),
        ]

    # primitivas ------------------------------------------------------------------------------
    def rect(self, x0, y0, x1, y1, *, fill=None, outline=None, width: float = 1) -> None:
        self.draw.rectangle(
            self.box(x0, y0, x1, y1),
            fill=fill,
            outline=outline,
            width=self.lw(width) if outline else 0,
        )

    def rounded(
        self, x0, y0, x1, y1, radius: float, *, fill=None, outline=None, width: float = 1
    ) -> None:
        self.draw.rounded_rectangle(
            self.box(x0, y0, x1, y1),
            radius=self.pi(radius),
            fill=fill,
            outline=outline,
            width=self.lw(width) if outline else 0,
        )

    def line(self, points: Iterable[tuple[float, float]], *, fill, width: float = 1) -> None:
        pts = [(self.p(x), self.p(y)) for x, y in points]
        self.draw.line(pts, fill=fill, width=self.lw(width), joint="curve")

    def polygon(
        self, points: Iterable[tuple[float, float]], *, fill=None, outline=None, width: float = 1
    ) -> None:
        pts = [(self.p(x), self.p(y)) for x, y in points]
        self.draw.polygon(pts, fill=fill, outline=outline, width=self.lw(width) if outline else 0)

    def circle(self, cx, cy, r, *, fill=None, outline=None, width: float = 1) -> None:
        self.draw.ellipse(
            self.box(cx - r, cy - r, cx + r, cy + r),
            fill=fill,
            outline=outline,
            width=self.lw(width) if outline else 0,
        )

    def pieslice(self, cx, cy, r, start_clock_deg: float, end_clock_deg: float, *, fill) -> None:
        """Fatia por ângulo horário a partir de 12h (convenção do YAML); Pillow conta de 3h."""
        self.draw.pieslice(
            self.box(cx - r, cy - r, cx + r, cy + r),
            start_clock_deg - 90.0,
            end_clock_deg - 90.0,
            fill=fill,
        )

    def arc(
        self, cx, cy, r, start_clock_deg: float, end_clock_deg: float, *, fill, width: float
    ) -> None:
        self.draw.arc(
            self.box(cx - r, cy - r, cx + r, cy + r),
            start_clock_deg - 90.0,
            end_clock_deg - 90.0,
            fill=fill,
            width=self.lw(width),
        )

    def text(
        self,
        x: float,
        y: float,
        text: str,
        font: ImageFont.FreeTypeFont,
        *,
        fill,
        anchor: str = "la",
    ) -> None:
        self.draw.text((self.p(x), self.p(y)), text, font=font, fill=fill, anchor=anchor)

    def text_bbox(
        self, x: float, y: float, text: str, font: ImageFont.FreeTypeFont, *, anchor: str = "la"
    ) -> tuple[float, float, float, float]:
        """Caixa (px canônicos) dos pixels de tinta do texto como `text()` o desenha."""
        x0, y0, x1, y1 = self.draw.textbbox((self.p(x), self.p(y)), text, font=font, anchor=anchor)
        return (x0 / self.k, y0 / self.k, x1 / self.k, y1 / self.k)

    def spaced_text(
        self,
        x: float,
        y: float,
        text: str,
        font: ImageFont.FreeTypeFont,
        *,
        fill,
        tracking: float,
        anchor_v: str = "s",
    ) -> float:
        """Texto com espaçamento entre letras (canônico); devolve a largura desenhada."""
        cursor = x
        for ch in text:
            self.text(cursor, y, ch, font, fill=fill, anchor="l" + anchor_v)
            cursor += self.text_width(ch, font) + tracking
        return cursor - tracking - x

    def paste_fit(self, source: str | Path | bytes, x0, y0, x1, y1) -> None:
        """Cola um asset raster dentro da caixa, preservando proporção (sem esticar)."""
        raw = source if isinstance(source, bytes) else Path(source).read_bytes()
        with Image.open(io.BytesIO(raw)) as im:
            asset = im.convert("RGBA")
        bw, bh = self.p(x1 - x0), self.p(y1 - y0)
        scale = min(bw / asset.width, bh / asset.height)
        size = (max(1, round(asset.width * scale)), max(1, round(asset.height * scale)))
        asset = asset.resize(size, Image.Resampling.LANCZOS)
        self.img.paste(asset, (self.pi(x0), self.pi(y0)), asset)

    # saída -----------------------------------------------------------------------------------
    def to_png(self) -> bytes:
        img = self.img
        if self.ss > 1:
            img = img.resize((self.out_w, self.out_h), Image.Resampling.LANCZOS)
        dpi = self.out_w / (self.width_cm / 2.54)
        buf = io.BytesIO()
        # Sem PngInfo: nenhum tEXt/tIME; compress_level fixo -> mesma entrada, mesmos bytes.
        img.save(buf, format="PNG", dpi=(dpi, dpi), compress_level=9, optimize=False)
        return buf.getvalue()


def rel_box(box: Sequence[float], W: float, H: float) -> tuple[float, float, float, float]:
    """[x0, y0, x1, y1] relativos -> px canônicos."""
    x0, y0, x1, y1 = box
    return x0 * W, y0 * H, x1 * W, y1 * H


def polar(cx: float, cy: float, r: float, clock_deg: float) -> tuple[float, float]:
    """Ponto no círculo pelo ângulo horário a partir de 12h."""
    a = math.radians(clock_deg)
    return cx + r * math.sin(a), cy - r * math.cos(a)
