# ruff: noqa: N803  -- W/H seguem a notação do YAML (`*_over_W`, `*_over_H`, `canvas.w/h`)
"""Painéis ambientais do produto 2.4 (RECONSTRUCTED_VISUAL, DEC-009).

    render_environmental_index  "Índices de Acompanhamento Ambiental"  (P2.4_ENV_INDICES_PANEL)
    render_conditions_status    "Status das Condicionantes", 1 por rodovia (P2.4_CONDITIONS_PANELS)

Fonte das regras: `config/g2_render_rules.yaml`. Contagens, linhas e ordem da tabela chegam
prontas (WAVE1_FINDINGS §B: o gerador recalcula status e contagens em outro módulo); aqui só se
desenha e se aplicam as regras de REPRESENTAÇÃO do YAML (ordem das barras, escalas, omissões).

Defaults técnicos (WAVE1_FINDINGS §L; revisáveis):
- fundo sólido `background.median_color` (#275559) no lugar da foto sob véu (sem cópia limpa);
- tabela de Índices COMPLETA (a captura era janela de rolagem): o canvas cresce para baixo na
  medida exata das linhas; com até a janela histórica (~8 linhas) mantém a proporção 1,779;
- barras de fase em escala proporcional (`charts.phases_bars.recommended_scale`): a maior mede
  right_x - clip_left_x = 0,344 W e não é cortada (anomalia phase_bar_clip não reproduzida);
- "Próximo à vencer" -> "Próximo a vencer" (anomalia cond_card_crase);
- tabela de Índices: Empresa pelo nome de exibição (`charts.table.company_display`, MEDIUM) e
  texto mais largo que a célula quebra dentro dela (`charts.table.cell_overflow`, QA-D nº 14);
  `draw_environmental_index` devolve o bbox de cada texto para o teste de geometria;
- canvas de saída de 2067 px (300 dpi a 17,50 cm), proporções 1,779 e 2,49.
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
    polar,
    render_options,
    rule_key,
    weight_of,
)

SECTION_INDEX = "P2.4_ENV_INDICES_PANEL"
SECTION_CONDITIONS = "P2.4_CONDITIONS_PANELS"

# road_buttons_note: "gap ~3 px" entre os botões de rodovia.
BUTTON_GAP_PX = 3.0
# Anomalia cond_card_crase: texto fixo com crase indevida no card 4 (nº 11 a nº 14).
CARD_LABEL_FIXES = {"Próximo à vencer": "Próximo a vencer"}
# typography.card_value.zero = "--", zero_note "dois traços espaçados".
ZERO_TEXT = "--"
ZERO_TRACKING_OVER_EM = 0.25
# kpis_layout "rótulo em cima, inteiro grande embaixo": centros medidos em ref_layout_r14_image19
# (rótulo a 0,25 e valor a 0,64 da altura do card). Sem chave própria no YAML.
KPI_LABEL_Y_OVER_CARD_H = 0.25
KPI_VALUE_Y_OVER_CARD_H = 0.64
# Cards das condicionantes: centro do ícone a 0,38 da altura do card (medido em
# ref_layout_r14_image20); folga lateral do texto 7% da largura do card.
CARD_ICON_Y_OVER_CARD_H = 0.38
CARD_TEXT_PAD_OVER_CARD_W = 0.07
# Limite esquerdo dos rótulos de fase (não invadir a pizza): fração de W.
PHASE_LABEL_MIN_X_OVER_W = 0.60
# Base inferior do plot de fases: a última barra não passa do topo dos rótulos do eixo das
# rodovias (`roads_plot.xlabel_y[0]`); com mais fases o passo é comprimido.


# =============================================================================================
# Dados


@dataclass(frozen=True)
class LicenseRow:
    """Linha da tabela de Índices (`charts.table.columns`, mesma ordem; Link = ícone)."""

    road: str
    company: str
    process: str
    license: str
    phase: str
    valid_until: date | str | None
    status: str
    has_link: bool = True


@dataclass(frozen=True)
class EnvironmentalIndexData:
    """Conteúdo do painel de Índices. `status_counts` usa `charts.pie.slice_order`."""

    updated_at: date
    total: int
    issued: int
    pending: int
    status_counts: Mapping[str, int]
    by_road: Mapping[str, int]
    by_phase: Mapping[str, int]
    rows: Sequence[LicenseRow]
    roads: Sequence[str] = field(default_factory=tuple)  # botões, na grafia do dado


@dataclass(frozen=True)
class ConditionsStatusData:
    """Conteúdo de um painel de condicionantes (uma rodovia).

    `road_totals` = total de condicionantes de cada uma das rodovias do mês (escala da barra:
    `charts.road_bar.scale`, comprimento = n / max das rodovias).
    """

    road: str
    updated_at: date
    finalized: int
    on_time: int
    pending: int
    near_due: int
    road_totals: Mapping[str, int]
    roads: Sequence[str] = field(default_factory=tuple)

    @property
    def counts(self) -> tuple[int, int, int, int]:
        """Na ordem de `charts.cards` e de `charts.pct_columns.categories_fixed_order`."""
        return (self.finalized, self.on_time, self.pending, self.near_due)

    @property
    def total(self) -> int:
        return sum(self.counts)


# =============================================================================================
# Regras puras (testáveis sem pixel)


def card_value_text(n: int) -> str:
    """`typography.card_value.zero`: zero aparece como "--"."""
    return ZERO_TEXT if int(n) == 0 else str(int(n))


def card_label(label: str) -> str:
    return CARD_LABEL_FIXES.get(label, label)


def ordered_desc(values: Mapping[str, int]) -> list[tuple[str, int]]:
    """`roads_columns.order` e `phases_bars.order`: valor decrescente, empate alfabético."""
    return sorted(values.items(), key=lambda kv: (-int(kv[1]), kv[0]))


def phase_bar_geometry(
    by_phase: Mapping[str, int], rules: dict[str, Any], W: float, H: float
) -> list[tuple[str, int, tuple[float, float, float, float]]]:
    """Retângulos (x0, y0, x1, y1) das barras de fase em px canônicos.

    Escala proporcional (`phases_bars.recommended_scale`): maior valor = right_x - clip_left_x
    (0,344 W), ancorada à direita em `phases_plot.right_x`. Nenhuma barra sai do canvas.
    """
    sec = rules[SECTION_INDEX]
    plot = sec["regions_rel"]["phases_plot"]
    roads = sec["regions_rel"]["roads_plot"]
    items = [(name, int(v)) for name, v in ordered_desc(by_phase) if int(v) > 0]
    if not items:
        return []
    right = plot["right_x"] * W
    max_len = (plot["right_x"] - plot["clip_left_x"]) * W
    vmax = max(v for _, v in items)
    top = plot["first_bar_top_y"] * H
    bar_h = plot["bar_h_over_H"] * H
    pitch = plot["pitch_over_H"] * H
    bottom_limit = roads["xlabel_y"][0] * H
    if len(items) > 1 and top + (len(items) - 1) * pitch + bar_h > bottom_limit:
        pitch = (bottom_limit - top - bar_h) / (len(items) - 1)
        bar_h = min(bar_h, pitch * (plot["bar_h_over_H"] / plot["pitch_over_H"]))
    out = []
    for i, (name, v) in enumerate(items):
        y0 = top + i * pitch
        length = max_len * v / vmax
        out.append((name, v, (right - length, y0, right, y0 + bar_h)))
    return out


def pct_slots(
    counts: Sequence[int], rules: dict[str, Any], W: float
) -> list[tuple[int, float, float]]:
    """(índice da categoria, centro x, percentual) das colunas presentes.

    `pct_columns.zero`: categoria com 0 é omitida e as presentes ocupam os slots da esquerda.
    Com as 4 presentes (nunca observado; gap "slot da coluna Pendentes", LOW) os centros são
    redistribuídos uniformemente entre o primeiro e o último slot medidos.
    """
    geo = rules[SECTION_CONDITIONS]["regions_rel"]["pct_columns"]
    total = sum(int(n) for n in counts)
    present = [(i, int(n)) for i, n in enumerate(counts) if int(n) > 0]
    if total == 0 or not present:
        return []
    centers = [x * W for x in geo["slot_centers_x"]]
    if len(present) > len(centers):
        first, last = centers[0], centers[-1]
        step = (last - first) / (len(present) - 1)
        centers = [first + i * step for i in range(len(present))]
    return [(i, centers[j], 100.0 * n / total) for j, (i, n) in enumerate(present)]


# =============================================================================================
# Cabeçalho comum (botões, título, "Atualizado em")


def _canvas(sec: dict[str, Any], opts: dict[str, Any], H: float) -> Canvas:
    bg = sec["background"]
    color = bg["median_color"] if isinstance(bg, dict) else None
    if color is None:  # P2.4_CONDITIONS_PANELS.background: "igual ao P2.4_ENV_INDICES_PANEL"
        color = opts["_index_background"]
    return Canvas(
        float(sec["canvas"]["w"]),
        H,
        out_width=opts["out_width_px"],
        supersample=opts["supersample"],
        width_cm=opts["width_cm"],
        background=color,
    )


def _options(rules: dict[str, Any]) -> dict[str, Any]:
    opts = render_options(rules)
    opts["_index_background"] = rules[SECTION_INDEX]["background"]["median_color"]
    return opts


def _updated_spec(typ: dict[str, Any]) -> tuple[str, float, float, str, str]:
    """Normaliza `updated_label`/`updated_date` (Índices) e `updated` (Condicionantes)."""
    if "updated" in typ:
        u = typ["updated"]
        return u["text"], float(u["label_em_px"]), float(u["date_em_px"]), "semibold", u["format"]
    lab, dat = typ["updated_label"], typ["updated_date"]
    return lab["text"], em(lab), em(dat), weight_of(dat, "semibold"), dat["format"]


def _panel_header(
    c: Canvas,
    sec: dict[str, Any],
    roads: Sequence[str],
    selected: str | None,
    updated_at: date,
    ui: tuple[str, ...],
    W: float,
    H0: float,
) -> None:
    reg, pal, typ = sec["regions_rel"], sec["palette"], sec["typography"]
    text_color = pal["text"]

    if roads:
        bx0, by0, bx1, by1 = (
            reg["road_buttons"][0] * W,
            reg["road_buttons"][1] * H0,
            reg["road_buttons"][2] * W,
            reg["road_buttons"][3] * H0,
        )
        n = len(roads)
        bw = (bx1 - bx0 - (n - 1) * BUTTON_GAP_PX) / n
        bfont = c.font(ui, weight_of(typ["road_button"], "bold"), em(typ["road_button"]))
        for i, road in enumerate(roads):
            x0 = bx0 + i * (bw + BUTTON_GAP_PX)
            is_sel = (
                selected is not None and rule_key(road).casefold() == rule_key(selected).casefold()
            )
            fill = pal.get("button_fill_selected") if is_sel else pal["button_fill"]
            c.rect(x0, by0, x0 + bw, by1, fill=fill, outline=pal["button_border"], width=1.5)
            c.text(x0 + bw / 2, (by0 + by1) / 2, road, bfont, fill=text_color, anchor="mm")

    title = typ["title"]
    tfont = c.font(ui, weight_of(title, "bold"), em(title))
    tx = reg["title"][0] * W
    ty = (reg["title"][1] + reg["title"][3]) / 2 * H0
    c.text(tx, ty, sec["title_text"], tfont, fill=text_color, anchor="lm")
    x_logo = tx + c.text_width(sec["title_text"], tfont)
    if c_opts_logo := sec.get("_logo_white_png"):
        h = (reg["title"][3] - reg["title"][1]) * H0 * 1.4
        c.paste_fit(c_opts_logo, x_logo, ty - h / 2, reg["title"][2] * W, ty + h / 2)
    else:
        _icons.wordmark(c, x_logo, ty, em(title) * 1.3, text_color, ui)
    rule = reg["title_rule"]
    c.rect(
        rule["x"][0] * W, rule["y"][0] * H0, rule["x"][1] * W, rule["y"][1] * H0, fill=rule["color"]
    )

    label, label_em, date_em, date_weight, fmt = _updated_spec(typ)
    ux0, uy0, ux1, uy1 = (
        reg["updated_box"][0] * W,
        reg["updated_box"][1] * H0,
        reg["updated_box"][2] * W,
        reg["updated_box"][3] * H0,
    )
    c.rect(
        ux0,
        uy0,
        ux1,
        uy1,
        fill=pal.get("updated_box_fill"),
        outline=pal.get("updated_box_border", pal["button_border"]),
        width=1.5,
    )
    h = uy1 - uy0
    c.text(
        (ux0 + ux1) / 2,
        uy0 + h * 0.30,
        label,
        c.font(ui, "regular", label_em),
        fill=text_color,
        anchor="mm",
    )
    c.text(
        (ux0 + ux1) / 2,
        uy0 + h * 0.66,
        fmt_date(updated_at, fmt),
        c.font(ui, date_weight, date_em),
        fill=text_color,
        anchor="mm",
    )


# =============================================================================================
# Painel "Índices de Acompanhamento Ambiental"


@dataclass
class _LicenseLayout:
    cols: list[tuple[float, float, str]]
    rows: list[tuple[float, float, list[list[str]]]]
    header: tuple[float, float, float, float]
    bottom: float
    # Texto desenhado na tabela: (coluna, linha, texto, bbox do texto, caixa da célula), em px
    # canônicos; bbox medido pelo Pillow (`ImageDraw.textbbox`) na fonte do desenho. Prova de
    # geometria: nenhum texto sai da sua célula.
    text_boxes: list[tuple[str, int, str, tuple[float, float, float, float],
                           tuple[float, float, float, float]]] = field(default_factory=list)


def render_environmental_index(data: EnvironmentalIndexData, rules: dict[str, Any]) -> bytes:
    """PNG do painel de Índices. `rules` = `config/g2_render_rules.yaml` carregado."""
    canvas, _layout = draw_environmental_index(data, rules)
    return canvas.to_png()


def draw_environmental_index(
    data: EnvironmentalIndexData, rules: dict[str, Any]
) -> tuple[Canvas, _LicenseLayout]:
    """Desenha o painel de Índices e devolve o canvas e o layout da tabela (com `text_boxes`)."""
    sec = dict(rules[SECTION_INDEX])
    opts = _options(rules)
    sec["_logo_white_png"] = opts.get("logo_white_png")
    W, H0 = float(sec["canvas"]["w"]), float(sec["canvas"]["h"])
    ui = opts["font_family"]

    metrics = Metrics(W, out_width=opts["out_width_px"], supersample=opts["supersample"])
    layout = _layout_licenses(metrics, data.rows, sec, ui, W, H0)
    reg = sec["regions_rel"]
    pad = (reg["table_header"][0] - reg["table_container"][0]) * W
    H = max(H0, layout.bottom + pad)

    c = _canvas(sec, opts, H)
    _panel_header(c, sec, data.roads, None, data.updated_at, ui, W, H0)
    _kpis(c, data, sec, ui, W, H0)
    _roads_chart(c, data.by_road, sec, ui, W, H0)
    _pie(c, data.status_counts, sec, ui, W, H0)
    _phases(c, data.by_phase, rules, sec, ui, W, H0)
    _license_table(c, layout, data.rows, sec, ui, W, H0, H)
    return c, layout


def _kpis(
    c: Canvas,
    data: EnvironmentalIndexData,
    sec: dict[str, Any],
    ui: tuple[str, ...],
    W: float,
    H0: float,
) -> None:
    reg, pal, typ = sec["regions_rel"], sec["palette"], sec["typography"]
    lfont = c.font(ui, weight_of(typ["kpi_label"]), em(typ["kpi_label"]))
    vfont = c.font(ui, weight_of(typ["kpi_value"]), em(typ["kpi_value"]))
    values = (data.total, data.issued, data.pending)
    for box, label, value in zip(reg["kpi_cards"], sec["charts"]["kpis"], values, strict=True):
        x0, y0, x1, y1 = box[0] * W, box[1] * H0, box[2] * W, box[3] * H0
        c.rect(
            x0,
            y0,
            x1,
            y1,
            fill=pal["container_fill"],
            outline=pal["card_border"],
            width=float(pal["card_border_px"]),
        )
        cx, h = (x0 + x1) / 2, y1 - y0
        c.text(cx, y0 + h * KPI_LABEL_Y_OVER_CARD_H, label, lfont, fill=pal["text"], anchor="mm")
        c.text(
            cx,
            y0 + h * KPI_VALUE_Y_OVER_CARD_H,
            str(int(value)),
            vfont,
            fill=pal["text"],
            anchor="mm",
        )


def _centered_title(
    c: Canvas, box: Sequence[float], text: str, font, color: str, W: float, H0: float
) -> None:
    c.text(
        (box[0] + box[2]) / 2 * W, (box[1] + box[3]) / 2 * H0, text, font, fill=color, anchor="mm"
    )


# Títulos dos gráficos: textos fixos das capturas (nº 11 a nº 14), sem chave de texto no YAML.
ROADS_CHART_TITLE = "Total de Licenças por Rodovia"
PHASES_CHART_TITLE = "Fases de Licença Ambiental"
PIE_CENTER_FALLBACK = "Status"


def _roads_chart(
    c: Canvas,
    by_road: Mapping[str, int],
    sec: dict[str, Any],
    ui: tuple[str, ...],
    W: float,
    H0: float,
) -> None:
    reg, pal, typ = sec["regions_rel"], sec["palette"], sec["typography"]
    tfont = c.font(ui, weight_of(typ["chart_title"], "bold"), em(typ["chart_title"]))
    _centered_title(c, reg["roads_title"], ROADS_CHART_TITLE, tfont, pal["text"], W, H0)
    plot = reg["roads_plot"]
    items = [(r, int(v)) for r, v in ordered_desc(by_road)]
    if not items:
        return
    vmax = max(v for _, v in items) or 1
    base = plot["baseline_y"] * H0
    max_h = plot["max_bar_h_over_H"] * H0
    bw, pitch = plot["bar_w_over_W"] * W, plot["pitch_over_W"] * W
    vfont = c.font(ui, weight_of(typ["bar_value"], "bold"), em(typ["bar_value"]))
    afont = c.font(ui, weight_of(typ["axis_label"]), em(typ["axis_label"]))
    label_y = (plot["xlabel_y"][0] + plot["xlabel_y"][1]) / 2 * H0
    for i, (road, v) in enumerate(items):
        x0 = plot["x0"] * W + i * pitch
        h = max_h * v / vmax
        top = base - h
        if v > 0:
            c.rect(x0, top, x0 + bw, base, fill=lookup(pal["road_bars"], road))
        cx = x0 + bw / 2
        # value_label: acima da barra; a que toca o topo do plot leva o rótulo dentro do topo.
        if v == vmax:
            c.text(cx, top + 4, str(v), vfont, fill=pal["text"], anchor="mt")
        else:
            c.text(cx, top - 6, str(v), vfont, fill=pal["text"], anchor="mb")
        c.text(cx, label_y, road, afont, fill=pal["text"], anchor="mm")


def _pie(
    c: Canvas,
    counts: Mapping[str, int],
    sec: dict[str, Any],
    ui: tuple[str, ...],
    W: float,
    H0: float,
) -> None:
    reg, pal, typ, spec = (
        sec["regions_rel"],
        sec["palette"],
        sec["typography"],
        sec["charts"]["pie"],
    )
    order = list(spec["slice_order"])
    values = [int(lookup(counts, name, 0)) for name in order]
    total = sum(values)
    cx, cy = reg["pie"]["center"][0] * W, reg["pie"]["center"][1] * H0
    r = reg["pie"]["r_over_H"] * H0
    lfont = c.font(ui, weight_of(typ["pie_label"], "bold"), em(typ["pie_label"]))
    angle = float(spec["first_slice_start_deg_clockwise_from_12h"])
    if total > 0:
        labels = []
        for name, v in zip(order, values, strict=True):
            if v <= 0:
                continue
            sweep = 360.0 * v / total
            if sweep >= 360.0:
                c.circle(cx, cy, r, fill=lookup(pal["pie"], name))
            else:
                c.pieslice(cx, cy, r, angle, angle + sweep, fill=lookup(pal["pie"], name))
            labels.append((angle + sweep / 2, 100.0 * v / total))
            angle += sweep
        for mid, pct in labels:
            # labels: "fora, linha guia curta".
            p0 = polar(cx, cy, r * 1.01, mid)
            p1 = polar(cx, cy, r * 1.10, mid)
            right = math.sin(math.radians(mid)) >= 0
            p2 = (p1[0] + (8 if right else -8), p1[1])
            c.line([p0, p1, p2], fill=pal["text"], width=1)
            text = f"{fmt_decimal(pct, 1)}%"  # pie_label.format "0,0%"
            c.text(
                p2[0] + (4 if right else -4),
                p2[1],
                text,
                lfont,
                fill=pal["text"],
                anchor="lm" if right else "rm",
            )
    center = typ["pie_center"]
    c.text(
        cx,
        cy,
        center.get("text", PIE_CENTER_FALLBACK),
        c.font(ui, weight_of(center, "bold"), em(center)),
        fill=pal["text"],
        anchor="mm",
    )

    # pie_legend: "circulo vazado para Pendente, cheio para Vigente".
    leg = typ["pie_legend"]
    font = c.font(ui, weight_of(leg, "bold"), em(leg))
    lx0, ly0, _lx1, ly1 = reg["pie_legend"]
    x, y = lx0 * W, (ly0 + ly1) / 2 * H0
    mr = em(leg) * 0.33
    for i, name in enumerate(order):
        color = lookup(pal["pie"], name)
        if i == 0:
            c.circle(x + mr, y, mr, outline=color, width=1.5)
        else:
            c.circle(x + mr, y, mr, fill=color)
        x += 2 * mr + 2
        c.text(x, y, name, font, fill=pal["text"], anchor="lm")
        x += c.text_width(name, font) + em(leg) * 0.6


def _phases(
    c: Canvas,
    by_phase: Mapping[str, int],
    rules: dict[str, Any],
    sec: dict[str, Any],
    ui: tuple[str, ...],
    W: float,
    H0: float,
) -> None:
    reg, pal, typ = sec["regions_rel"], sec["palette"], sec["typography"]
    tfont = c.font(ui, weight_of(typ["chart_title"], "bold"), em(typ["chart_title"]))
    _centered_title(c, reg["phases_title"], PHASES_CHART_TITLE, tfont, pal["text"], W, H0)
    item = typ["phase_label"]
    min_x = PHASE_LABEL_MIN_X_OVER_W * W
    gap = 6.0
    bars = phase_bar_geometry(by_phase, rules, W, H0)
    for idx, (name, v, (x0, y0, x1, y1)) in enumerate(bars):
        color = lookup(pal["phases"], name, pal["phases"]["_default"])
        c.rect(x0, y0, x1, y1, fill=color)
        ymid = (y0 + y1) / 2
        count, rest = str(v), f" {name}"
        bold = c.font(ui, item.get("count_weight", "bold"), em(item))
        reg_font = c.font(ui, weight_of(item), em(item))
        width = c.text_width(count, bold) + c.text_width(rest, reg_font)
        inside = idx == 0 and width + 2 * gap <= (x1 - x0)
        if inside:  # recommended_scale: o rótulo da maior fica dentro, alinhado à esquerda
            tx = x0 + gap + 4
        else:  # demais: à esquerda da barra
            available = x0 - gap - min_x
            if width > available:
                scale = max(0.5, available / width)
                bold = c.font(ui, item.get("count_weight", "bold"), em(item) * scale)
                reg_font = c.font(ui, weight_of(item), em(item) * scale)
                width = c.text_width(count, bold) + c.text_width(rest, reg_font)
            tx = x0 - gap - width
        c.text(tx, ymid, count, bold, fill=pal["text"], anchor="lm")
        c.text(tx + c.text_width(count, bold), ymid, rest, reg_font, fill=pal["text"], anchor="lm")


def company_display(company: str, table_spec: dict[str, Any]) -> str:
    """`charts.table.company_display.names`: nome de exibição (Power BI); sem entrada, o dado."""
    names = (table_spec.get("company_display") or {}).get("names") or {}
    return str(lookup(names, company, company)) if company else company


def _license_cells(
    row: LicenseRow, columns: list[dict[str, Any]], table_spec: dict[str, Any] | None = None
) -> list[str]:
    values: list[Any] = [
        row.road,
        company_display(row.company, table_spec or {}),
        row.process,
        row.license,
        row.phase,
        row.valid_until,
        row.status,
        "",
    ]
    out = []
    for col, value in zip(columns, values, strict=True):
        if value is None:
            out.append("")
        elif isinstance(value, date):
            out.append(fmt_date(value, col.get("format", "dd/mm/aaaa")))
        else:
            out.append(str(value))
    return out


def fit_lines(m: Metrics, text: str, font, max_width: float) -> list[str]:
    """Linhas de `text` que cabem em `max_width`: quebra por palavra e, se uma palavra sozinha
    não couber (número de processo longo), por caractere. Texto que cabe fica numa linha."""
    if not text or m.text_width(text, font) <= max_width:
        return [text]
    out: list[str] = []
    for line in m.wrap(text, font, max_width):
        if m.text_width(line, font) <= max_width:
            out.append(line)
            continue
        current = ""
        for ch in line:
            if current and m.text_width(current + ch, font) > max_width:
                out.append(current.rstrip())
                current = ch.lstrip()
            else:
                current += ch
        if current:
            out.append(current)
    return out


def _layout_licenses(
    m: Metrics,
    rows: Sequence[LicenseRow],
    sec: dict[str, Any],
    ui: tuple[str, ...],
    W: float,
    H0: float,
) -> _LicenseLayout:
    reg, typ, spec = sec["regions_rel"], sec["typography"], sec["charts"]["table"]
    columns = spec["columns"]
    cols = [(col["x"][0] * W, col["x"][1] * W, col.get("align", "left")) for col in columns]
    header = (
        reg["table_header"][0] * W,
        reg["table_header"][1] * H0,
        reg["table_header"][2] * W,
        reg["table_header"][3] * H0,
    )
    font = m.font(ui, weight_of(typ["table_body"]), em(typ["table_body"]))
    pitch = spec["row_pitch_over_H"] * H0
    # row_pitch_note: "26 px; linha com quebra 50 px" -> cada linha extra soma 24 px (canvas 877).
    line_step = pitch * (50.0 - 26.0) / 26.0
    pad = 4.0
    y = header[3]
    out_rows = []
    for row in rows:
        cells = []
        for (x0, x1, _a), _col, text in zip(
            cols, columns, _license_cells(row, columns, spec), strict=True
        ):
            # charts.table.columns[*].wrap e QA-D do nº 14 (Gate D): texto mais largo que a
            # célula quebra dentro dela e a linha cresce (`row_pitch_note`); nunca invade a
            # coluna vizinha, com ou sem `wrap` declarado.
            cells.append(fit_lines(m, text, font, x1 - x0 - 2 * pad))
        n = max(len(cell) for cell in cells)
        h = pitch + (n - 1) * line_step
        out_rows.append((y, y + h, cells))
        y += h
    return _LicenseLayout(cols, out_rows, header, y)


def _license_table(
    c: Canvas,
    layout: _LicenseLayout,
    rows: Sequence[LicenseRow],
    sec: dict[str, Any],
    ui: tuple[str, ...],
    W: float,
    H0: float,
    H: float,
) -> None:
    reg, pal, typ, spec = (
        sec["regions_rel"],
        sec["palette"],
        sec["typography"],
        sec["charts"]["table"],
    )
    cont = reg["table_container"]
    c.rect(cont[0] * W, cont[1] * H0, cont[2] * W, H, fill=pal["container_fill"])
    hx0, hy0, hx1, hy1 = layout.header
    c.rect(hx0, hy0, hx1, hy1, fill=pal["table_header_fill"])
    hfont = c.font(ui, weight_of(typ["table_header"], "bold"), em(typ["table_header"]))
    bfont = c.font(ui, weight_of(typ["table_body"]), em(typ["table_body"]))
    pad = 4.0
    columns = spec["columns"]
    for i, ((x0, x1, _a), col) in enumerate(zip(layout.cols, columns, strict=True)):
        # header_align: "Rodovia a esquerda; demais centralizados".
        align = "left" if i == 0 else "center"
        _cell(c, col["name"], x0, x1, (hy0 + hy1) / 2, align, hfont, pal["text"], pad)
    pitch = spec["row_pitch_over_H"] * H0
    line_step = pitch * (50.0 - 26.0) / 26.0
    body_bottom = layout.rows[-1][1] if layout.rows else hy1
    for r_idx, ((y0, y1, cells), row) in enumerate(zip(layout.rows, rows, strict=True)):
        c.rect(hx0, y0, hx1, y1, fill=pal["table_row_fill"])
        c.rect(hx0, y1 - 1, hx1, y1, fill=pal["table_hgrid"])
        for (x0, x1, align), col, lines in zip(layout.cols, columns, cells, strict=True):
            if col["name"] == "Link":
                if row.has_link:  # content: "icone de corrente"
                    _icons.chain_link(c, (x0 + x1) / 2, y0 + pitch / 2, pitch * 0.62, pal["text"])
                continue
            for j, line in enumerate(lines):
                box = _cell(
                    c, line, x0, x1, y0 + pitch / 2 + j * line_step, align, bfont, pal["text"], pad
                )
                if box is not None:
                    layout.text_boxes.append((col["name"], r_idx, line, box, (x0, y0, x1, y1)))
    for x0, _x1, _a in layout.cols[1:]:
        c.rect(x0 - 1, hy0, x0 + 1, body_bottom, fill=pal["table_vgrid"])


def _cell(
    c: Canvas,
    text: str,
    x0: float,
    x1: float,
    ymid: float,
    align: str,
    font,
    color: str,
    pad: float,
) -> tuple[float, float, float, float] | None:
    """Desenha o texto da célula e devolve o bbox dele (px canônicos, `ImageDraw.textbbox`)."""
    if not text:
        return None
    if align == "center":
        x, anchor = (x0 + x1) / 2, "mm"
    elif align == "right":
        x, anchor = x1 - pad, "rm"
    else:
        x, anchor = x0 + pad, "lm"
    c.text(x, ymid, text, font, fill=color, anchor=anchor)
    return c.text_bbox(x, ymid, text, font, anchor=anchor)


# =============================================================================================
# Painel "Status das Condicionantes"


# Subtítulos fixos: `charts.subtitles` [rodovia, percentuais].
def render_conditions_status(data: ConditionsStatusData, rules: dict[str, Any]) -> bytes:
    """PNG de um painel de condicionantes. `rules` = `config/g2_render_rules.yaml` carregado."""
    sec = dict(rules[SECTION_CONDITIONS])
    opts = _options(rules)
    sec["_logo_white_png"] = opts.get("logo_white_png")
    W, H = float(sec["canvas"]["w"]), float(sec["canvas"]["h"])
    ui = opts["font_family"]
    c = _canvas(sec, opts, H)
    _panel_header(c, sec, data.roads, data.road, data.updated_at, ui, W, H)
    _condition_cards(c, data, sec, ui, W, H)
    _condition_road_bar(c, data, sec, ui, W, H)
    _condition_pct(c, data, rules, sec, ui, W, H)
    return c.to_png()


def _condition_cards(
    c: Canvas,
    data: ConditionsStatusData,
    sec: dict[str, Any],
    ui: tuple[str, ...],
    W: float,
    H: float,
) -> None:
    reg, pal, typ, cards = (
        sec["regions_rel"],
        sec["palette"],
        sec["typography"],
        sec["charts"]["cards"],
    )
    lab_item, val_item = typ["card_label"], typ["card_value"]
    vfont = c.font(ui, weight_of(val_item), em(val_item))
    baseline = reg["card_text_baseline_y"] * H
    radius = float(pal["card_corner_radius_px"])
    icons = (_icons.cycle_check, _icons.calendar_check, _icons.warning, _icons.clock_alert)
    for box, card, n, icon in zip(reg["cards"], cards, data.counts, icons, strict=True):
        x0, y0, x1, y1 = box[0] * W, box[1] * H, box[2] * W, box[3] * H
        cw, ch = x1 - x0, y1 - y0
        c.rounded(x0, y0, x1, y1, radius, fill=pal["card_fill"])
        size = 0.18 * H  # card_icon: "~0.18H de altura"
        icx, icy = (x0 + x1) / 2, y0 + ch * CARD_ICON_Y_OVER_CARD_H
        if icon in (_icons.calendar_check, _icons.clock_alert):
            icon(c, icx, icy, size, pal["text"], pal["card_fill"])
        else:
            icon(c, icx, icy, size, pal["text"])
        label = card_label(card["label"])
        dot = lookup(pal["dots"], rule_key(label))
        # card_dot: r ~0.018H, borda branca 1 px, centro a 0.013W da direita e 0.035H do topo.
        c.circle(x1 - 0.013 * W, y0 + 0.035 * H, 0.018 * H, fill=dot, outline=pal["text"], width=1)

        value = card_value_text(n)
        pad = CARD_TEXT_PAD_OVER_CARD_W * cw
        tracking = em(val_item) * ZERO_TRACKING_OVER_EM if value == ZERO_TEXT else 0.0
        vwidth = c.spaced_width(value, vfont, tracking)
        vx = x1 - pad - vwidth
        lfont = c.fit_font(
            label, ui, weight_of(lab_item), em(lab_item), vx - (x0 + pad) - em(lab_item) * 0.3
        )
        c.text(x0 + pad, baseline, label, lfont, fill=pal["text"], anchor="ls")
        c.spaced_text(vx, baseline, value, vfont, fill=pal["text"], tracking=tracking, anchor_v="s")


def _condition_road_bar(
    c: Canvas,
    data: ConditionsStatusData,
    sec: dict[str, Any],
    ui: tuple[str, ...],
    W: float,
    H: float,
) -> None:
    reg, pal, typ, subtitles = (
        sec["regions_rel"],
        sec["palette"],
        sec["typography"],
        sec["charts"]["subtitles"],
    )
    sfont = c.font(ui, weight_of(typ["subtitle"], "bold"), em(typ["subtitle"]))
    _centered_title(c, reg["subtitle_road"], subtitles[0], sfont, pal["text"], W, H)
    bar = reg["road_bar"]
    y0, y1 = bar["y"][0] * H, bar["y"][1] * H
    ymid = (y0 + y1) / 2
    n = data.total
    vmax = max([int(v) for v in data.road_totals.values()] + [n]) or 1
    length = bar["max_len_over_W"] * W * n / vmax  # road_bar.scale: n / max das rodovias
    x0 = bar["x0"] * W
    if n > 0:
        c.rect(x0, y0, x0 + length, y1, fill=pal["road_bar"])
    c.text(
        bar["label_x0"] * W,
        ymid,
        data.road,
        c.font(ui, weight_of(typ["road_label"]), em(typ["road_label"])),
        fill=pal["text"],
        anchor="lm",
    )
    c.text(
        x0 + length + 10,
        ymid,
        str(n),
        c.font(ui, weight_of(typ["road_value"], "bold"), em(typ["road_value"])),
        fill=pal["text"],
        anchor="lm",
    )


def _condition_pct(
    c: Canvas,
    data: ConditionsStatusData,
    rules: dict[str, Any],
    sec: dict[str, Any],
    ui: tuple[str, ...],
    W: float,
    H: float,
) -> None:
    reg, pal, typ, spec = (
        sec["regions_rel"],
        sec["palette"],
        sec["typography"],
        sec["charts"]["pct_columns"],
    )
    sfont = c.font(ui, weight_of(typ["subtitle"], "bold"), em(typ["subtitle"]))
    _centered_title(c, reg["subtitle_pct"], sec["charts"]["subtitles"][1], sfont, pal["text"], W, H)
    geo = reg["pct_columns"]
    names = spec["categories_fixed_order"]
    base = geo["baseline_y"] * H
    h100 = geo["h100_over_H"] * H
    pfont = c.font(ui, weight_of(typ["pct_label"], "bold"), em(typ["pct_label"]))
    xfont = c.font(ui, weight_of(typ["pct_xlabel"]), em(typ["pct_xlabel"]))
    slots = pct_slots(data.counts, rules, W)
    centers = [x * W for x in geo["slot_centers_x"]]
    pitch = (centers[1] - centers[0]) if len(centers) > 1 else geo["col_w_over_W"] * W
    if len(slots) > len(centers) and len(slots) > 1:
        pitch = (slots[-1][1] - slots[0][1]) / (len(slots) - 1)
    col_w = min(geo["col_w_over_W"] * W, pitch * 0.9)
    for idx, cx, pct in slots:
        name = names[idx]
        # pct_columns.scale: fixa de 0 a 100%: altura = pct * h100; não-zero tem ao menos 1 px.
        h = max(1.0, h100 * pct / 100.0)
        color = lookup(pal["pct_columns"], rule_key(name), None)
        if color is None:
            # gap "slot da coluna Pendentes": sem cor medida; usa a cor do ponto do card (LOW).
            color = lookup(pal["dots"], rule_key(name))
        c.rect(cx - col_w / 2, base - h, cx + col_w / 2, base, fill=color)
        c.text(cx, base - h - 8, f"{fmt_decimal(pct, 2)}%", pfont, fill=pal["text"], anchor="ms")
        lines = c.wrap(name, xfont, pitch * 0.98)
        line_h = em(typ["pct_xlabel"]) * 1.2
        for j, line in enumerate(lines):
            c.text(cx, geo["xlabel_y"] * H + j * line_h, line, xfont, fill=pal["text"], anchor="mm")
