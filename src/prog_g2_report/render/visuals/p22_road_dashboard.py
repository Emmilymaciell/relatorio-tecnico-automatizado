# ruff: noqa: N803  -- W/H seguem a notação do YAML (`*_over_W`, `*_over_H`, `canvas.w/h`)
"""Quadro por rodovia do produto 2.2 (RECONSTRUCTED_VISUAL, DEC-009).

Fonte das regras: `config/g2_render_rules.yaml`, seção `P2.2_ROAD_DASHBOARDS`. Este módulo só
desenha: as linhas chegam já filtradas e ordenadas (ordem de disciplina, DEC-009 item 4) e as
contagens do donut chegam prontas — a seleção é de outro módulo.

Defaults técnicos (WAVE1_FINDINGS §L; revisáveis):
- canvas de saída de 2067 px (300 dpi a 17,50 cm) com a proporção `canvas.aspect` 1,781;
- sem o slicer "Disciplina: Todos" (ruído de interface; `ui_noise_do_not_reproduce`, gaps);
- números do donut inteiros (`charts.donut.label_format_recommended`);
- tabela em Arial nas 4 rodovias (`historical_variation_not_rule`), família parametrizável.

Comportamento com tabela longa (decisão deste módulo): se as linhas não cabem até
`regions_rel.table_body[3]`, o canvas cresce para baixo na medida exata (largura fixa, sem
reduzir fonte nem passo de linha); os elementos ancorados ao rodapé (triângulo, ícone, rótulo da
rodovia) acompanham a borda inferior. Com as 22 disciplinas do padrão vigente cabe sem crescer.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from prog_g2_report.render.visuals import _icons
from prog_g2_report.render.visuals._canvas import (
    Canvas,
    Metrics,
    em,
    fmt_date,
    fmt_decimal,
    lookup,
    render_options,
    rule_key,
    weight_of,
)

SECTION = "P2.2_ROAD_DASHBOARDS"

# Folga horizontal do texto dentro da célula: medida em ref_layout_r14_image13 (texto a 6 px da
# borda da tabela em 1557 px). Sem chave própria no YAML -> constante técnica relativa a W.
CELL_PAD_OVER_W = 0.0040
# `table.empty_cell`: "vazio (nao usa --)".
EMPTY_CELL = ""
# Formato das datas de "Entrega da Revisão" quando chegam como data: anomalia candidata
# road_dash_us_dates (M/D/AAAA misturado no histórico) -> o builder emite dd/mm/aaaa.
REVISION_DATE_FORMAT = "dd/mm/aaaa"


@dataclass(frozen=True)
class RoadDashboardRow:
    """Uma linha da tabela de 7 colunas (`table.columns`, na mesma ordem)."""

    discipline: str
    forecast: date | str | None = None  # Previsão (dd/mm/aa)
    delivery: date | str | None = None  # Entrega (dd/mm/aa)
    revision: int | None = None  # REV (inteiro)
    level1: str = ""  # 1º Nível
    level2: str = ""  # 2º Nível
    revision_delivery: date | str | None = None  # Entrega da Revisão (status ou data)


@dataclass(frozen=True)
class RoadDashboardData:
    """Conteúdo de um quadro. `donut_counts` usa os nomes de `charts.donut.categories_order`."""

    road: str
    donut_counts: Mapping[str, int]
    rows: Sequence[RoadDashboardRow]
    updated_at: date
    groups: Sequence[str] = field(default_factory=tuple)  # tiles GRUPO (data_driven_texts)


@dataclass
class _Row:
    y0: float
    y1: float
    cells: list[list[str]]


@dataclass
class _Table:
    x0: float
    x1: float
    cols: list[tuple[float, float, str]]  # (x0, x1, align)
    header_y0: float
    header_y1: float
    rows: list[_Row]

    @property
    def bottom(self) -> float:
        return self.rows[-1].y1 if self.rows else self.header_y1


def render_road_dashboard(data: RoadDashboardData, rules: dict[str, Any]) -> bytes:
    """PNG do quadro por rodovia. `rules` = `config/g2_render_rules.yaml` carregado."""
    sec = rules[SECTION]
    opts = render_options(rules)
    W, H0 = float(sec["canvas"]["w"]), float(sec["canvas"]["h"])
    reg = sec["regions_rel"]

    metrics = Metrics(W, out_width=opts["out_width_px"], supersample=opts["supersample"])
    table = _layout_table(metrics, data, sec, opts, W, H0)
    body_limit = reg["table_body"][3] * H0
    extra = max(0.0, table.bottom - body_limit)
    H = H0 + extra

    c = Canvas(
        W,
        H,
        out_width=opts["out_width_px"],
        supersample=opts["supersample"],
        width_cm=opts["width_cm"],
        background=sec["background"],
    )
    ui = opts["font_family"]
    _draw_header_block(c, data, sec, opts, W, H0)
    _draw_groups(c, data.groups, sec, ui, W, H0)
    _draw_donut(c, data.donut_counts, sec, ui, W, H0)
    _draw_table(c, table, sec, opts)
    _draw_corner(c, data.road, sec, ui, W, H0, extra)
    _draw_frame(c, sec, W, H)
    return c.to_png()


# ---------------------------------------------------------------------------------------------
# Tabela


def _cell_texts(row: RoadDashboardRow, columns: list[dict[str, Any]]) -> list[str]:
    values = [
        row.discipline,
        row.forecast,
        row.delivery,
        row.revision,
        row.level1,
        row.level2,
        row.revision_delivery,
    ]
    out: list[str] = []
    for col, value in zip(columns, values, strict=True):
        fmt = col.get("format")
        if value is None or value == "":
            out.append(EMPTY_CELL)
        elif fmt == "inteiro":
            out.append(str(int(value)))
        elif isinstance(value, date):
            out.append(fmt_date(value, fmt or REVISION_DATE_FORMAT))
        else:
            out.append(str(value))
    return out


def _layout_table(
    m: Metrics,
    data: RoadDashboardData,
    sec: dict[str, Any],
    opts: dict[str, Any],
    W: float,
    H0: float,
) -> _Table:
    reg, spec = sec["regions_rel"], sec["table"]
    columns = spec["columns"]
    if len(columns) != 7:
        raise ValueError(f"{SECTION}.table.columns: esperado 7 colunas, veio {len(columns)}")
    x0, x1 = reg["table_header"][0] * W, reg["table_header"][2] * W
    width = x1 - x0
    cols: list[tuple[float, float, str]] = []
    cursor = x0
    for col in columns:
        right = cursor + float(col["w"]) * width
        cols.append((cursor, right, col.get("align", "left")))
        cursor = right

    body = sec["typography"]["items"]["table_body"]
    font = m.font(opts["font_family_table_p22"], weight_of(body), em(body))
    pad = CELL_PAD_OVER_W * W
    pitch = float(spec["row_pitch_px"])
    line_step = float(spec["row_pitch_2_lines_px"]) - pitch

    rows: list[_Row] = []
    y = reg["table_body"][1] * H0
    for row in data.rows:
        cells: list[list[str]] = []
        for (cx0, cx1, _align), text in zip(cols, _cell_texts(row, columns), strict=True):
            cells.append(m.wrap(text, font, cx1 - cx0 - 2 * pad) if text else [""])
        n_lines = max(len(lines) for lines in cells)
        height = pitch + (n_lines - 1) * line_step
        rows.append(_Row(y, y + height, cells))
        y += height
    return _Table(x0, x1, cols, reg["table_header"][1] * H0, reg["table_header"][3] * H0, rows)


def _draw_table(c: Canvas, t: _Table, sec: dict[str, Any], opts: dict[str, Any]) -> None:
    pal, spec, typ = sec["palette"], sec["table"], sec["typography"]["items"]
    fam = opts["font_family_table_p22"]
    head = c.font(fam, weight_of(typ["table_header"], "bold"), em(typ["table_header"]))
    body = c.font(fam, weight_of(typ["table_body"]), em(typ["table_body"]))
    pad = CELL_PAD_OVER_W * c.W
    pitch = float(spec["row_pitch_px"])
    line_step = float(spec["row_pitch_2_lines_px"]) - pitch

    ymid = (t.header_y0 + t.header_y1) / 2
    for (x0, x1, align), col in zip(t.cols, spec["columns"], strict=True):
        _cell_text(c, col["name"], x0, x1, ymid, align, head, typ["table_header"]["color"], pad)
    rule_w = float(pal["header_rule_px"])
    c.rect(t.x0, t.header_y1 - rule_w, t.x1, t.header_y1, fill=pal["header_rule"])

    zebra = (spec.get("first_row_fill", pal["zebra_first_row"]), pal["zebra_second_row"])
    for i, row in enumerate(t.rows):
        c.rect(t.x0, row.y0, t.x1, row.y1, fill=zebra[i % 2])
        c.rect(t.x0, row.y1 - 1, t.x1, row.y1, fill=pal["row_separator"])
        for (x0, x1, align), lines in zip(t.cols, row.cells, strict=True):
            for j, line in enumerate(lines):
                y = row.y0 + pitch / 2 + j * line_step
                _cell_text(c, line, x0, x1, y, align, body, typ["table_body"]["color"], pad)


def _cell_text(
    c: Canvas,
    text: str,
    x0: float,
    x1: float,
    ymid: float,
    align: str,
    font,
    color: str,
    pad: float,
) -> None:
    if not text:
        return
    if align == "right":
        c.text(x1 - pad, ymid, text, font, fill=color, anchor="rm")
    elif align == "center":
        c.text((x0 + x1) / 2, ymid, text, font, fill=color, anchor="mm")
    else:
        c.text(x0 + pad, ymid, text, font, fill=color, anchor="lm")


# ---------------------------------------------------------------------------------------------
# Cabeçalho: logotipo, "Atualizado em", GRUPO


def _draw_header_block(
    c: Canvas,
    data: RoadDashboardData,
    sec: dict[str, Any],
    opts: dict[str, Any],
    W: float,
    H0: float,
) -> None:
    reg, pal, typ = sec["regions_rel"], sec["palette"], sec["typography"]["items"]
    ui = opts["font_family"]
    lx0, ly0, lx1, ly1 = (
        reg["logo"][0] * W,
        reg["logo"][1] * H0,
        reg["logo"][2] * W,
        reg["logo"][3] * H0,
    )
    if opts.get("logo_png"):
        c.paste_fit(opts["logo_png"], lx0, ly0, lx1, ly1)
    else:
        _logo_fallback(c, lx0, ly0, lx1, ly1, pal["logo_teal"], ui)

    item = typ["updated_label"]
    font = c.font(ui, weight_of(item), em(item))
    y = (reg["updated_label"][1] + reg["updated_label"][3]) / 2 * H0
    c.text(reg["updated_label"][0] * W, y, item["text"], font, fill=item["color"], anchor="lm")

    item = typ["updated_date"]
    font = c.font(ui, weight_of(item), em(item))
    y = (reg["updated_date"][1] + reg["updated_date"][3]) / 2 * H0
    c.text(
        reg["updated_date"][0] * W,
        y,
        fmt_date(data.updated_at, item["format"]),
        font,
        fill=item["color"],
        anchor="lm",
    )


def _logo_fallback(
    c: Canvas, x0: float, y0: float, x1: float, y1: float, color: str, ui: tuple[str, ...]
) -> None:
    """Logotipo Programa em texto (gap: sem asset isolado); marca no alto, subtítulo abaixo."""
    h, w = y1 - y0, x1 - x0
    mark = c.fit_font(_icons.BRAND_WORDMARK, ui, "bold", h * 0.78, w)
    c.text((x0 + x1) / 2, y0 + h * 0.34, _icons.BRAND_WORDMARK, mark, fill=color, anchor="mm")
    sub_em = h * 0.105
    sub = c.font(ui, "regular", sub_em)
    for i, line in enumerate(_icons.BRAND_SUBTITLE):
        tracking = 0.0
        natural = c.spaced_width(line, sub, 0.0)
        if len(line) > 1:
            tracking = max(0.0, (w * 0.98 - natural) / (len(line) - 1))
        lw = c.spaced_width(line, sub, tracking)
        c.spaced_text(
            (x0 + x1) / 2 - lw / 2,
            y0 + h * (0.83 + 0.15 * i),
            line,
            sub,
            fill=color,
            tracking=tracking,
            anchor_v="m",
        )


def _draw_groups(
    c: Canvas, groups: Sequence[str], sec: dict[str, Any], ui: tuple[str, ...], W: float, H0: float
) -> None:
    """Tiles GRUPO: grupos presentes na rodovia (`data_driven_texts.grupo_tiles`), 2 colunas."""
    if not groups:
        return
    reg, pal, typ = sec["regions_rel"], sec["palette"], sec["typography"]["items"]
    item = typ["grupo_label"]
    font = c.font(ui, weight_of(item), em(item))
    y = (reg["grupo_label"][1] + reg["grupo_label"][3]) / 2 * H0
    c.text(reg["grupo_label"][0] * W, y, item["text"], font, fill=item["color"], anchor="lm")

    geo = reg["grupo_tile_geometry"]
    tile = typ["tile_text"]
    tfont = c.font(ui, weight_of(tile), em(tile))
    tw, th = geo["tile_w_over_W"] * W, geo["tile_h_over_H"] * H0
    gx, gy = geo["gap_x_over_W"] * W, geo["gap_y_over_H"] * H0
    x_start, y_start = reg["grupo_tiles"][0] * W, reg["grupo_tiles"][1] * H0
    cols = int(geo["cols"])
    for i, name in enumerate(groups):
        r, col = divmod(i, cols)
        x0, y0 = x_start + col * (tw + gx), y_start + r * (th + gy)
        c.rounded(
            x0,
            y0,
            x0 + tw,
            y0 + th,
            4,
            fill=sec["background"],
            outline=pal["tile_border"],
            width=1.5,
        )
        c.text(x0 + 0.010 * W, y0 + th / 2, name, tfont, fill=tile["color"], anchor="lm")


# ---------------------------------------------------------------------------------------------
# Donut e legenda


def donut_label(n: int, total: int) -> str:
    """`charts.donut.label_format_recommended`: "{n inteiro} ({pct até 2 decimais}%)"."""
    pct = 100.0 * n / total if total else 0.0
    return f"{int(n)} ({fmt_decimal(pct, 2, strip_zeros=True)}%)"


def _draw_donut(
    c: Canvas,
    counts: Mapping[str, int],
    sec: dict[str, Any],
    ui: tuple[str, ...],
    W: float,
    H0: float,
) -> None:
    reg, pal, spec = sec["regions_rel"], sec["palette"], sec["charts"]["donut"]
    order = list(spec["categories_order"])
    values = [int(lookup(counts, name, 0)) for name in order]
    total = sum(values)
    geo = reg["donut"]
    cx, cy = geo["center"][0] * W, geo["center"][1] * H0
    r = geo["r_outer_over_H"] * H0
    r_in = r * float(geo["inner_ratio"])
    start = float(spec["start_angle_deg_clockwise_from_12h"])
    clockwise = spec.get("direction", "clockwise") == "clockwise"
    colors = pal["donut"]

    labels: list[tuple[float, list[str]]] = []  # (y alvo, linhas)
    angle = start
    for name, value in zip(order, values, strict=True):
        if value <= 0 or total == 0:
            continue  # charts.donut.zero_category: omite fatia e rótulo; legenda mantém
        sweep = 360.0 * value / total
        a0, a1 = (angle, angle + sweep) if clockwise else (angle - sweep, angle)
        c.pieslice(cx, cy, r, a0, a1, fill=lookup(colors, rule_key(name)))
        mid = (a0 + a1) / 2
        labels.append((cy - r * _cos(mid), [donut_label(value, total)]))
        angle = a1 if clockwise else a0
    c.circle(cx, cy, r_in, fill=sec["background"])
    _donut_labels(c, labels, cx, cy, r, sec, ui)
    _legend(c, order, sec, ui, W, H0)


def _cos(deg: float) -> float:
    return math.cos(math.radians(deg))


def _donut_labels(
    c: Canvas,
    labels: list[tuple[float, list[str]]],
    cx: float,
    cy: float,
    r: float,
    sec: dict[str, Any],
    ui: tuple[str, ...],
) -> None:
    """Rótulos à esquerda do donut com linha guia (padrão das 4 capturas do nº 14)."""
    item = sec["typography"]["items"]["donut_label"]
    font = c.font(ui, weight_of(item), em(item))
    color = item["color"]
    leader = item.get("leader_line", "#7C7C7B 1 px").split()[0]
    line_h = em(item) * 1.25
    x_end = cx - r - 0.010 * c.W
    x_text = x_end - 0.003 * c.W
    min_x = float(sec["frame"]["thickness_px"]) + 0.006 * c.W

    prepared: list[tuple[float, list[str]]] = []
    for y, lines in sorted(labels, key=lambda t: t[0]):
        text = lines[0]
        if x_text - c.text_width(text, font) < min_x:
            count, pct = text.split(" ", 1)
            lines = [count, pct]
        prepared.append((y, lines))
    # Espaçamento mínimo: empurra para baixo os rótulos que se sobrepõem.
    placed: list[tuple[float, float, list[str]]] = []
    cursor = -1e9
    for y_target, lines in prepared:
        height = line_h * len(lines)
        top = max(y_target - height / 2, cursor)
        placed.append((y_target, top, lines))
        cursor = top + height + 2
    for _y_target, top, lines in placed:
        y_line = top + line_h / 2
        dy = max(-r, min(r, y_line - cy))
        ax = cx - math.sqrt(
            r * r - dy * dy
        )  # ponto do arco externo à esquerda, na altura do rótulo
        c.line([(ax, cy + dy), (x_end, y_line)], fill=leader, width=1)
        for j, line in enumerate(lines):
            c.text(x_text, y_line + j * line_h, line, font, fill=color, anchor="rm")


def _legend(
    c: Canvas, order: list[str], sec: dict[str, Any], ui: tuple[str, ...], W: float, H0: float
) -> None:
    reg, typ, pal = sec["regions_rel"], sec["typography"]["items"], sec["palette"]
    x0, y0 = reg["legend"][0] * W, reg["legend"][1] * H0
    title = typ["legend_title"]
    tfont = c.font(ui, weight_of(title, "bold"), em(title))
    c.text(x0, y0 + em(title) / 2, title["text"], tfont, fill=title["color"], anchor="lm")
    item = typ["legend_item"]
    ifont = c.font(ui, weight_of(item), em(item))
    pitch = float(item["pitch_px"])
    marker_r = 6.0
    for i, name in enumerate(order):
        y = y0 + em(title) / 2 + pitch * (i + 1)
        c.circle(x0 + marker_r, y, marker_r, fill=lookup(pal["donut"], rule_key(name)))
        c.text(x0 + 2 * marker_r + 2, y, name, ifont, fill=item["color"], anchor="lm")


# ---------------------------------------------------------------------------------------------
# Canto inferior e moldura


def _draw_corner(
    c: Canvas,
    road: str,
    sec: dict[str, Any],
    ui: tuple[str, ...],
    W: float,
    H0: float,
    extra: float,
) -> None:
    reg, typ = sec["regions_rel"], sec["typography"]["items"]
    tri = reg["corner_triangle"]
    p0 = (tri["line_from"][0] * W, tri["line_from"][1] * H0 + extra)
    p1 = (tri["line_to"][0] * W, tri["line_to"][1] * H0 + extra)
    c.polygon([p0, p1, (0, p1[1]), (0, p0[1])], fill=tri["fill_below_line"])
    c.line([p0, p1], fill=tri["color"], width=float(tri["width_px"]))
    ix0, iy0, ix1, iy1 = reg["corner_icon"]
    _icons.map_pin(
        c, ix0 * W, iy0 * H0 + extra, ix1 * W, iy1 * H0 + extra, "#000000", tri["fill_below_line"]
    )
    item = typ["road_label"]
    font = c.font(ui, weight_of(item, "bold"), em(item))
    y = (reg["road_label"][1] + reg["road_label"][3]) / 2 * H0 + extra
    c.text(reg["road_label"][0] * W, y, road, font, fill=item["color"], anchor="lm")


def _draw_frame(c: Canvas, sec: dict[str, Any], W: float, H: float) -> None:
    """`frame`: moldura uniforme (o histórico 3 a 11 px é recorte manual)."""
    t = float(sec["frame"]["thickness_px"])
    color = sec["frame"]["color"]
    c.rect(0, 0, W, t, fill=color)
    c.rect(0, H - t, W, H, fill=color)
    c.rect(0, 0, t, H, fill=color)
    c.rect(W - t, 0, W, H, fill=color)
