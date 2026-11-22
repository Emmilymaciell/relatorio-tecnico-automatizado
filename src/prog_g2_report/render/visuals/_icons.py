"""Ícones vetoriais desenhados com primitivas (substitutos provisórios dos rasters do Power BI).

Gap registrado em `config/g2_render_rules.yaml` (gaps): os ícones dos 4 cards e do mapa/pino só
existem como raster ~110 px nas capturas. Até haver asset limpo, o builder desenha equivalentes
com a mesma semântica (`P2.4_CONDITIONS_PANELS.charts.cards[*].icon`,
`P2.2_ROAD_DASHBOARDS.regions_rel.corner_icon_note`). Coordenadas em px canônicos; `s` = lado.
"""

from __future__ import annotations

import math

from prog_g2_report.render.visuals._canvas import Canvas, polar

# P2.4_*.title_suffix: "logotipo Programa"; P2.2 regions_rel.logo_note: logotipo colorido.
# Sem asset isolado no DOCX (gaps do YAML): o fallback é o logotipo composto em texto.
BRAND_WORDMARK = "PRG"
# Subtítulo do logotipo colorido (P2.2 regions_rel.logo_note), com a acentuação da captura.
BRAND_SUBTITLE = ("CONSÓRCIO ESTRUTURADOR", "DO PROGRAMA")


def wordmark(
    c: Canvas,
    x: float,
    y_mid: float,
    em_px: float,
    color: str,
    families: tuple[str, ...],
    anchor_h: str = "l",
) -> float:
    """Desenha o logotipo em texto, centrado verticalmente em `y_mid`; devolve a largura."""
    font = c.font(families, "bold", em_px)
    c.text(x, y_mid, BRAND_WORDMARK, font, fill=color, anchor=anchor_h + "m")
    return c.text_width(BRAND_WORDMARK, font)


def _check(c: Canvas, cx: float, cy: float, s: float, color: str, width: float) -> None:
    c.line(
        [
            (cx - 0.30 * s, cy + 0.02 * s),
            (cx - 0.08 * s, cy + 0.24 * s),
            (cx + 0.32 * s, cy - 0.20 * s),
        ],
        fill=color,
        width=width,
    )


def cycle_check(c: Canvas, cx: float, cy: float, s: float, color: str) -> None:
    """ "ciclo com check": anel segmentado em 8 arcos com um check no centro."""
    r = 0.44 * s
    for i in range(8):
        start = i * 45 + 6
        c.arc(cx, cy, r, start, start + 33, fill=color, width=0.10 * s)
    _check(c, cx, cy, 0.62 * s, color, 0.09 * s)


def calendar_check(c: Canvas, cx: float, cy: float, s: float, color: str, background: str) -> None:
    """ "calendario com check": folha com argolas e grade, selo circular com check."""
    x0, y0, x1, y1 = cx - 0.42 * s, cy - 0.36 * s, cx + 0.34 * s, cy + 0.40 * s
    c.rounded(x0, y0, x1, y1, 0.06 * s, outline=color, width=0.06 * s)
    c.line([(x0, y0 + 0.16 * s), (x1, y0 + 0.16 * s)], fill=color, width=0.05 * s)
    for fx in (0.28, 0.72):
        rx = x0 + fx * (x1 - x0)
        c.line([(rx, y0 - 0.10 * s), (rx, y0 + 0.06 * s)], fill=color, width=0.07 * s)
    cell = 0.075 * s
    for row in range(3):
        for col in range(4):
            gx = x0 + 0.10 * s + col * 0.15 * s
            gy = y0 + 0.26 * s + row * 0.14 * s
            c.rect(gx, gy, gx + cell, gy + cell, fill=color)
    bx, by, br = cx + 0.26 * s, cy + 0.26 * s, 0.24 * s
    c.circle(bx, by, br, fill=background, outline=color, width=0.06 * s)
    _check(c, bx, by, 0.30 * s, color, 0.06 * s)


def warning(c: Canvas, cx: float, cy: float, s: float, color: str) -> None:
    """ "triangulo de alerta": triângulo vazado com exclamação."""
    top = (cx, cy - 0.44 * s)
    left = (cx - 0.48 * s, cy + 0.40 * s)
    right = (cx + 0.48 * s, cy + 0.40 * s)
    c.line([top, right, left, top, right], fill=color, width=0.08 * s)
    c.line([(cx, cy - 0.16 * s), (cx, cy + 0.14 * s)], fill=color, width=0.09 * s)
    c.circle(cx, cy + 0.27 * s, 0.05 * s, fill=color)


def clock_alert(c: Canvas, cx: float, cy: float, s: float, color: str, background: str) -> None:
    """ "relogio com exclamacao": mostrador com marcas e ponteiros, selo com exclamação."""
    ox, oy, r = cx - 0.08 * s, cy - 0.06 * s, 0.38 * s
    c.circle(ox, oy, r, outline=color, width=0.06 * s)
    for i in range(12):
        p0 = polar(ox, oy, r * 0.78, i * 30)
        p1 = polar(ox, oy, r * 0.90, i * 30)
        c.line([p0, p1], fill=color, width=0.035 * s)
    c.line([(ox, oy), polar(ox, oy, r * 0.62, 0)], fill=color, width=0.05 * s)
    c.line([(ox, oy), polar(ox, oy, r * 0.42, 300)], fill=color, width=0.05 * s)
    bx, by, br = cx + 0.24 * s, cy + 0.24 * s, 0.22 * s
    c.circle(bx, by, br, fill=background, outline=color, width=0.06 * s)
    c.line([(bx, by - 0.12 * s), (bx, by + 0.04 * s)], fill=color, width=0.06 * s)
    c.circle(bx, by + 0.11 * s, 0.035 * s, fill=color)


def map_pin(
    c: Canvas, x0: float, y0: float, x1: float, y1: float, color: str, background: str
) -> None:
    """ "icone de mapa com pino, traco preto": mapa dobrado em ziguezague e pino acima."""
    w, h = x1 - x0, y1 - y0
    top, bottom = y0 + 0.45 * h, y1
    xs = [x0 + w * f for f in (0.0, 0.33, 0.66, 1.0)]
    outline = [
        (xs[0], top + 0.08 * h),
        (xs[1], top),
        (xs[2], top + 0.08 * h),
        (xs[3], top),
        (xs[3], bottom - 0.08 * h),
        (xs[2], bottom),
        (xs[1], bottom - 0.08 * h),
        (xs[0], bottom),
        (xs[0], top + 0.08 * h),
    ]
    stroke = max(1.5, 0.045 * w)
    c.line(outline, fill=color, width=stroke)
    c.line([(xs[1], top), (xs[1], bottom - 0.08 * h)], fill=color, width=stroke)
    c.line([(xs[2], top + 0.08 * h), (xs[2], bottom)], fill=color, width=stroke)
    c.line(
        [
            (xs[0] + 0.1 * w, bottom - 0.2 * h),
            (xs[1], top + 0.35 * h),
            (xs[2] + 0.05 * w, top + 0.3 * h),
            (xs[3] - 0.1 * w, bottom - 0.25 * h),
        ],
        fill=color,
        width=stroke * 0.7,
    )
    pcx, pcy, pr = x0 + 0.5 * w, y0 + 0.22 * h, 0.17 * w
    tip = (pcx, top + 0.22 * h)
    a = math.radians(35)
    left = (pcx - pr * math.cos(a), pcy + pr * math.sin(a))
    right = (pcx + pr * math.cos(a), pcy + pr * math.sin(a))
    c.polygon([left, tip, right], fill=background)
    c.circle(pcx, pcy, pr, fill=background, outline=color, width=stroke)
    c.line([left, tip, right], fill=color, width=stroke)
    c.circle(pcx, pcy, pr * 0.40, outline=color, width=stroke * 0.8)


def chain_link(c: Canvas, cx: float, cy: float, s: float, color: str) -> None:
    """ "icone de corrente" da coluna Link: dois elos em cápsula a 45 graus."""
    for off in (-0.17, 0.17):
        ex, ey = cx + off * s, cy - off * s
        _capsule(c, ex, ey, 0.44 * s, 0.13 * s, -45.0, color, 0.08 * s)


def _capsule(
    c: Canvas,
    cx: float,
    cy: float,
    length: float,
    radius: float,
    angle_deg: float,
    color: str,
    width: float,
) -> None:
    a = math.radians(angle_deg)
    ux, uy = math.cos(a), math.sin(a)
    half = length / 2 - radius
    pts: list[tuple[float, float]] = []
    for end, base in ((1, -90), (-1, 90)):
        ox, oy = cx + end * half * ux, cy + end * half * uy
        for step in range(13):
            t = math.radians(base + step * 15) + a
            pts.append((ox + radius * math.cos(t), oy + radius * math.sin(t)))
    pts.append(pts[0])
    c.line(pts, fill=color, width=width)
