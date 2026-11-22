"""Visuais reconstruídos (DEC-009): determinismo, geometria e regras de representação.

Offline, com dados sintéticos. O teste `-m golden` reconstrói os quadros históricos a partir das
transcrições/snapshots em `tmp/agent_E` e `tmp/agent_B` (fora do Git) e grava PNGs lado a lado
(gerado × histórico) em `tmp/visual_golden/` para inspeção humana; sem eles, é pulado.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("PIL")
pytest.importorskip("matplotlib")

from PIL import Image, ImageDraw, ImageFont

from prog_g2_report.render.visuals import load_render_rules
from prog_g2_report.render.visuals._canvas import resolve_font_file
from prog_g2_report.render.visuals.p22_road_dashboard import (
    RoadDashboardData,
    RoadDashboardRow,
    donut_label,
    render_road_dashboard,
)
from prog_g2_report.render.visuals.p24_environmental import (
    ConditionsStatusData,
    EnvironmentalIndexData,
    LicenseRow,
    card_value_text,
    ordered_desc,
    pct_slots,
    phase_bar_geometry,
    render_conditions_status,
    render_environmental_index,
)

ROOT = Path(__file__).resolve().parents[1]


def _main_checkout() -> Path | None:
    """Raiz do checkout principal quando os testes rodam num worktree (`.git` é arquivo)."""
    git = ROOT / ".git"
    if not git.is_file():
        return None
    match = re.match(r"gitdir:\s*(.+)", git.read_text(encoding="utf-8").strip())
    if not match:
        return None
    return Path(match.group(1).strip()).resolve().parents[2]


def _find(relative: str) -> Path | None:
    for base in (ROOT, _main_checkout()):
        if base is not None and (base / relative).exists():
            return base / relative
    return None


@pytest.fixture(scope="module")
def rules():
    path = _find("config/g2_render_rules.yaml")
    if path is None:
        pytest.skip("config/g2_render_rules.yaml ausente")
    return load_render_rules(path)


def _png(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    return img.convert("RGB")


def _hex(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _close(a, b, tol: int = 6) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


# ---------------------------------------------------------------------------------------------
# Dados sintéticos


def _road_data(n_rows: int = 22, road: str = "RD-999") -> RoadDashboardData:
    rows = []
    for i in range(n_rows):
        rows.append(RoadDashboardRow(
            discipline=f"Disciplina sintética {i + 1}" + (" com nome longo o bastante para quebrar em duas linhas" if i == 3 else ""),
            forecast=date(2026, 1 + i % 12, 1 + i % 27),
            delivery=None if i % 5 == 4 else date(2026, 2, 10),
            revision=None if i % 5 == 4 else i % 6,
            level1="" if i % 5 == 4 else "Sim",
            level2="Aprovado com ressalvas" if i % 8 == 0 else "Aprovado",
            revision_delivery="Concluído" if i % 3 else date(2026, 9, 8),
        ))
    return RoadDashboardData(
        road=road,
        donut_counts={"Analisada": 12, "Atrasado": 5, "Em análise": 3},
        rows=rows,
        updated_at=date(2026, 9, 7),
        groups=("Grupo A", "Grupo B", "Grupo C"),
    )


def _license_rows(n: int) -> list[LicenseRow]:
    roads = ["RD-101", "RD-102a", "RD-103", "RD-104"]
    return [
        LicenseRow(road=roads[i % 4], company=f"Empresa {i % 4}", process=f"{1000 + i}/2026",
                   license="" if i % 6 == 5 else str(5000 + i),
                   phase="Licença Ambiental - Tanque Aéreo e Usina de Concreto" if i % 9 == 0 else "Outorga de uso de recurso hídrico",
                   valid_until=None if i % 6 == 5 else date(2030, 1, 1 + i % 27),
                   status="Aguardando a liberação" if i % 6 == 5 else "Vigente")
        for i in range(n)
    ]


def _index_data(n_rows: int = 6, by_road=None, by_phase=None) -> EnvironmentalIndexData:
    return EnvironmentalIndexData(
        updated_at=date(2026, 9, 7),
        total=33, issued=25, pending=8,
        status_counts={"Pendente": 8, "Vigente": 25},
        by_road=by_road or {"RD-103": 9, "RD-101": 7, "RD-102a": 6, "RD-104": 5},
        by_phase=by_phase or {"Outorga de uso de recurso hídrico": 20, "Licença Ambiental Única": 4,
                              "Licença Ambiental - Canteiro de obra": 3, "Registro Ambiental": 1},
        rows=_license_rows(n_rows),
        roads=("RD-101", "RD-102a", "RD-103", "RD-104"),
    )


def _cond_data(pending: int = 0, near_due: int = 34) -> ConditionsStatusData:
    return ConditionsStatusData(
        road="RD-101", updated_at=date(2026, 9, 7),
        finalized=11, on_time=1, pending=pending, near_due=near_due,
        road_totals={"RD-101": 11 + 1 + pending + near_due, "RD-102a": 43, "RD-103": 44, "RD-104": 60},
        roads=("RD-101", "RD-102a", "RD-103", "RD-104"),
    )


# ---------------------------------------------------------------------------------------------
# Determinismo, dimensões, proporção


RENDERERS = {
    "p22": (lambda r: render_road_dashboard(_road_data(), r), "P2.2_ROAD_DASHBOARDS"),
    "p24_index": (lambda r: render_environmental_index(_index_data(), r), "P2.4_ENV_INDICES_PANEL"),
    "p24_conditions": (lambda r: render_conditions_status(_cond_data(), r), "P2.4_CONDITIONS_PANELS"),
}


@pytest.mark.parametrize("name", sorted(RENDERERS))
def test_same_input_same_bytes(rules, name):
    render, _ = RENDERERS[name]
    first, second = render(rules), render(rules)
    assert hashlib.sha1(first).hexdigest() == hashlib.sha1(second).hexdigest()
    assert b"tIME" not in first and b"tEXt" not in first


@pytest.mark.parametrize("name", sorted(RENDERERS))
def test_width_and_aspect_follow_rules(rules, name):
    render, section = RENDERERS[name]
    img = _png(render(rules))
    out_w = rules["common_placement"]["recommended_output_px_width"]
    canvas = rules[section]["canvas"]
    assert img.width == out_w == 2067
    assert img.height == round(out_w * canvas["h"] / canvas["w"])
    assert abs(img.width / img.height - canvas["aspect"]) < 0.005
    dpi = Image.open(io.BytesIO(render(rules))).info["dpi"][0]
    assert abs(dpi - 300) < 0.5     # 2067 px a 17,50 cm


def test_font_family_is_a_rules_parameter(rules):
    base = render_conditions_status(_cond_data(), rules)
    other = render_conditions_status(_cond_data(), {**rules, "render_options": {"font_family": ["Arial"]}})
    assert base != other


# ---------------------------------------------------------------------------------------------
# Regras de representação


def test_zero_count_is_double_dash():
    assert card_value_text(0) == "--"
    assert card_value_text(7) == "7"


def test_zero_card_draws_dashes_not_digit(rules):
    """Card "Pendentes" com 0: só traços finos à direita do rótulo (não um "0" alto)."""
    sec = rules["P2.4_CONDITIONS_PANELS"]
    em_v = sec["typography"]["card_value"]["em_px"]

    def value_ink_height(pending: int) -> float:
        img = _png(render_conditions_status(_cond_data(pending=pending), rules))
        k = img.width / sec["canvas"]["w"]
        x0, _y0, x1, _y1 = sec["regions_rel"]["cards"][2]
        W, H = sec["canvas"]["w"], sec["canvas"]["h"]
        baseline = sec["regions_rel"]["card_text_baseline_y"] * H
        cw = (x1 - x0) * W
        left = int((x1 * W - 0.07 * cw - em_v * 1.6) * k)
        right = int((x1 * W - 0.07 * cw + 2) * k)
        top, bottom = int((baseline - em_v) * k), int((baseline + 2) * k)
        ys = [y for x in range(left, right) for y in range(top, bottom)
              if min(img.getpixel((x, y))) > 200]
        assert ys, "nenhum valor desenhado"
        return (max(ys) - min(ys)) / k

    assert value_ink_height(0) < em_v * 0.25     # "--": traço fino
    assert value_ink_height(7) > em_v * 0.5      # controle: dígito é alto


def test_donut_numbers_are_integers():
    assert donut_label(17, 22) == "17 (77,27%)"
    assert donut_label(2, 20) == "2 (10%)"
    assert donut_label(3, 22) == "3 (13,64%)"


def test_order_desc_with_alphabetical_tie():
    assert [k for k, _ in ordered_desc({"RD-104": 8, "RD-101": 8, "RD-103": 9, "RD-102a": 8})] == [
        "RD-103", "RD-101", "RD-102a", "RD-104"]


@pytest.mark.parametrize("swap", [False, True])
def test_road_bar_color_follows_road_not_position(rules, swap):
    sec = rules["P2.4_ENV_INDICES_PANEL"]
    by_road = {"RD-103": 9, "RD-101": 7, "RD-102a": 6, "RD-104": 5}
    if swap:
        by_road = {"RD-103": 5, "RD-101": 6, "RD-102a": 9, "RD-104": 7}
    img = _png(render_environmental_index(_index_data(by_road=by_road), rules))
    W, H = sec["canvas"]["w"], sec["canvas"]["h"]
    k = img.width / W
    plot = sec["regions_rel"]["roads_plot"]
    for i, (road, _v) in enumerate(ordered_desc(by_road)):
        cx = (plot["x0"] * W + i * plot["pitch_over_W"] * W + plot["bar_w_over_W"] * W / 2) * k
        cy = (plot["baseline_y"] * H - 0.05 * H) * k   # perto da base: toda barra passa por aqui
        expected = _hex(sec["palette"]["road_bars"][road])
        assert _close(img.getpixel((int(cx), int(cy))), expected), road


def test_largest_phase_bar_fits_canvas(rules):
    sec = rules["P2.4_ENV_INDICES_PANEL"]
    W, H = sec["canvas"]["w"], sec["canvas"]["h"]
    by_phase = {"Outorga de uso de recurso hídrico": 40, "Licença Ambiental Única": 4, "Registro Ambiental": 1}
    bars = phase_bar_geometry(by_phase, rules, W, H)
    plot = sec["regions_rel"]["phases_plot"]
    name, _v, (x0, y0, x1, _y1) = bars[0]
    assert name == "Outorga de uso de recurso hídrico"
    assert x0 >= 0 and x1 <= W
    assert abs((x1 - x0) - (plot["right_x"] - plot["clip_left_x"]) * W) < 1e-6
    img = _png(render_environmental_index(_index_data(by_phase=by_phase), rules))
    k = img.width / W
    color = _hex(sec["palette"]["phases"][name])
    assert _close(img.getpixel((int((x0 + 3) * k), int((y0 + 2) * k))), color)   # começo visível
    assert not _close(img.getpixel((int((x0 - 4) * k), int((y0 + 2) * k))), color)  # e termina ali
    assert _close(img.getpixel((int((x1 - 3) * k), int((y0 + 2) * k))), color)


def test_pct_columns_omit_zero_and_fill_slots_from_left(rules):
    W = rules["P2.4_CONDITIONS_PANELS"]["canvas"]["w"]
    centers = rules["P2.4_CONDITIONS_PANELS"]["regions_rel"]["pct_columns"]["slot_centers_x"]
    slots = pct_slots((11, 1, 0, 34), rules, W)
    assert [i for i, _, _ in slots] == [0, 1, 3]
    assert [round(x / W, 3) for _, x, _ in slots] == centers
    assert abs(sum(p for _, _, p in slots) - 100.0) < 1e-9
    assert [i for i, _, _ in pct_slots((11, 35, 0, 0), rules, W)] == [0, 1]
    assert len(pct_slots((1, 1, 1, 1), rules, W)) == 4


def test_index_table_is_complete_and_grows_panel(rules):
    """Decisão: tabela completa; o painel cresce para baixo na medida das linhas."""
    sec = rules["P2.4_ENV_INDICES_PANEL"]
    small = _png(render_environmental_index(_index_data(n_rows=6), rules))
    mid = _png(render_environmental_index(_index_data(n_rows=20), rules))
    big = _png(render_environmental_index(_index_data(n_rows=40), rules))
    assert abs(small.width / small.height - sec["canvas"]["aspect"]) < 0.005
    assert small.height < mid.height < big.height
    assert small.width == mid.width == big.width


def test_road_table_grows_only_when_rows_overflow(rules):
    base = _png(render_road_dashboard(_road_data(22), rules))
    long = _png(render_road_dashboard(_road_data(40), rules))
    assert abs(base.width / base.height - rules["P2.2_ROAD_DASHBOARDS"]["canvas"]["aspect"]) < 0.005
    assert long.height > base.height and long.width == base.width


def test_road_dashboard_palette_present(rules):
    sec = rules["P2.2_ROAD_DASHBOARDS"]
    img = _png(render_road_dashboard(_road_data(), rules))
    assert _close(img.getpixel((1, img.height // 2)), _hex(sec["frame"]["color"]))
    W, H = sec["canvas"]["w"], sec["canvas"]["h"]
    k = img.width / W
    geo = sec["regions_rel"]["donut"]
    r = geo["r_outer_over_H"] * H
    ring = r * (1 + geo["inner_ratio"]) / 2
    # Analisada começa às 12h no sentido horário: logo à direita do topo do anel.
    x = (geo["center"][0] * W + 0.15 * ring) * k
    y = (geo["center"][1] * H - ring) * k
    assert _close(img.getpixel((int(x), int(y))), _hex(sec["palette"]["donut"]["Analisada"]), tol=12)


# ---------------------------------------------------------------------------------------------
# Golden: reconstrução histórica lado a lado (inspeção humana)


COMPANY_DISPLAY = {   # nomes de exibição do modelo Power BI (WAVE1 §B: MEDIUM), lidos das capturas
    "CONSTRUTORA DELTA LTDA": "Construtora Delta Ltda",
    "CONSTRUTORA OMEGA S/A - CLX": "Construtora Omega S/A",
    "CONSTRUTORA SIGMA - CSG": "Construtora Sigma",
    "TETRA CONSTRUTORA ZETA LTDA": "Construtora Tetra",
}
# Donut do nº 14 transcrito das capturas (tmp/agent_L/r14_image13..16): Analisada/Atrasado/Em análise.
DONUT_N14 = {"RD-103": (17, 3, 2), "RD-102A": (15, 3, 2), "RD-101": (15, 4, 3), "RD-104": (14, 3, 3)}
GROUPS_ALL = ("Fase de Estudos", "OAE", "Projeto Executivo Viário Principal",
              "Projeto Executivo Viário Secundário")
UPDATED = {13: date(2026, 8, 12), 14: date(2026, 9, 7)}   # "Atualizado em" dos painéis ambientais
SNAPSHOT = {13: "v289.0", 14: "v310.0"}                    # WAVE1 §B


def _golden_enabled(request) -> bool:
    return "golden" in (request.config.option.markexpr or "")


def _load_ground_truth(path: Path):
    spec = importlib.util.spec_from_file_location("agent_e_ground_truth", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parse_date(text: str) -> date | str | None:
    if not text:
        return None
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{2})", text)
    if m:
        return date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)   # M/D/AAAA (anomalia road_dash_us_dates)
    if m:
        return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    return text


def _side_by_side(generated: bytes, historical: Path, out: Path, title: str) -> Path:
    gen = _png(generated)
    hist = Image.open(historical).convert("RGB")
    height = 900
    gen_r = gen.resize((round(gen.width * height / gen.height), height), Image.Resampling.LANCZOS)
    hist_r = hist.resize((round(hist.width * height / hist.height), height), Image.Resampling.LANCZOS)
    gap, band = 24, 40
    sheet = Image.new("RGB", (gen_r.width + hist_r.width + 3 * gap, height + band + 2 * gap), "#FFFFFF")
    sheet.paste(gen_r, (gap, band + gap))
    sheet.paste(hist_r, (2 * gap + gen_r.width, band + gap))
    draw = ImageDraw.Draw(sheet)
    font_file = resolve_font_file(("Segoe UI", "Arial"), 400)
    font = ImageFont.truetype(font_file, 22) if font_file else ImageFont.load_default(22)
    draw.text((gap, 10), f"GERADO (builder) - {title}", fill="#000000", font=font)
    draw.text((2 * gap + gen_r.width, 10), f"HISTÓRICO - {historical.name}", fill="#000000", font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, format="PNG")
    return out


@pytest.mark.golden
def test_golden_side_by_side(rules, request):
    if not _golden_enabled(request):
        pytest.skip("rode com -m golden")
    gt_path = _find("tmp/agent_E/ground_truth.py")
    ref_dir = _find("tmp/agent_L")
    snap_dir = _find("tmp/agent_B/snapshots")
    if not (gt_path and ref_dir and snap_dir):
        pytest.skip("referências históricas ausentes em tmp/")
    out_dir = ROOT / "tmp" / "visual_golden"
    written: list[Path] = []

    # P2.2 — 4 quadros por rodovia do nº 14 (ordem e mídias de P2.2_ROAD_DASHBOARDS).
    gt = _load_ground_truth(gt_path)
    truth = gt.ground_truth()
    sec22 = rules["P2.2_ROAD_DASHBOARDS"]
    for road, media in zip(sec22["order_in_doc"], sec22["docx_media"]["n14"], strict=True):
        table = truth[(14, road)]
        rows = []
        for discipline in gt.DISCIPLINES:
            if discipline not in table:
                continue
            prev, ent, rev, n1, n2, entrev = table[discipline]
            rows.append(RoadDashboardRow(discipline, _parse_date(prev), _parse_date(ent),
                                         int(rev) if rev else None, n1, n2, _parse_date(entrev)))
        a, b, cnt = DONUT_N14[road]
        groups = GROUPS_ALL if len(rows) == len(gt.DISCIPLINES) else tuple(g for g in GROUPS_ALL if g != "OAE")
        data = RoadDashboardData(road=road, donut_counts={"Analisada": a, "Atrasado": b, "Em análise": cnt},
                                 rows=rows, updated_at=date.fromisoformat(gt.PRINTED_DATE[14]), groups=groups)
        png = render_road_dashboard(data, rules)
        (out_dir / f"p22_{road}_n14_generated.png").parent.mkdir(parents=True, exist_ok=True)
        (out_dir / f"p22_{road}_n14_generated.png").write_bytes(png)
        written.append(_side_by_side(png, ref_dir / f"r14_{media}.png",
                                     out_dir / f"p22_{road}_n14_side_by_side.png", f"P2.2 {road} nº 14"))

    # P2.4 — Índices e Condicionantes do nº 13 e nº 14 a partir dos snapshots do agente B.
    sec_i, sec_c = rules["P2.4_ENV_INDICES_PANEL"], rules["P2.4_CONDITIONS_PANELS"]
    for number in (13, 14):
        snap = json.loads((snap_dir / f"{SNAPSHOT[number]}.json").read_text(encoding="utf-8"))
        road_of = snap["company_to_road"]
        lic = sorted(snap["licencas_rows"], key=lambda r: (road_of[r["Empresa"]], str(r["Nº Processo"])))
        rows = [LicenseRow(road=road_of[r["Empresa"]], company=COMPANY_DISPLAY.get(r["Empresa"], r["Empresa"]),
                           process=str(r["Nº Processo"]), license="" if r["Nº Licença"] is None else str(r["Nº Licença"]),
                           phase=r["Fase da licença"],
                           valid_until=date.fromisoformat(r["Data de validade"]) if r["Data de validade"] else None,
                           status=r["Status"]) for r in lic]
        total = snap["licencas_n"]
        vigente = snap["licencas_by_status"].get("Vigente", 0)
        index = EnvironmentalIndexData(
            updated_at=UPDATED[number], total=total, issued=total - snap["licencas_no_number"],
            pending=snap["licencas_by_status"].get("Aguardando a liberação", 0),
            status_counts={"Pendente": total - vigente, "Vigente": vigente},
            by_road=snap["licencas_by_road"], by_phase=snap["licencas_by_fase"], rows=rows,
            roads=tuple(sorted(snap["licencas_by_road"])))
        png = render_environmental_index(index, rules)
        (out_dir / f"p24_indices_n{number}_generated.png").write_bytes(png)
        written.append(_side_by_side(png, ref_dir / f"r{number}_{sec_i['docx_media'][f'n{number}']}.png",
                                     out_dir / f"p24_indices_n{number}_side_by_side.png", f"P2.4 Índices nº {number}"))

        status = snap["cond_by_road_status"]
        for road, media in zip(sec_c["order_in_doc"], sec_c["docx_media"][f"n{number}"], strict=True):
            key = next(k for k in snap["cond_by_road"] if k.casefold() == road.casefold())

            def count(s, key=key, status=status):
                return int(status.get(f"{key}|{s}", 0))

            data = ConditionsStatusData(
                road=key, updated_at=UPDATED[number], finalized=count("Finalizada"), on_time=count("No prazo"),
                pending=count("Pendente"), near_due=count("Próximo do vencimento"),
                road_totals=snap["cond_by_road"], roads=tuple(sorted(snap["cond_by_road"])))
            png = render_conditions_status(data, rules)
            (out_dir / f"p24_condic_{road}_n{number}_generated.png").write_bytes(png)
            written.append(_side_by_side(png, ref_dir / f"r{number}_{media}.png",
                                         out_dir / f"p24_condic_{road}_n{number}_side_by_side.png",
                                         f"P2.4 Condicionantes {road} nº {number}"))

    for path in written:
        print(path)
    assert len(written) == 4 + 2 * (1 + 4)


# ---------------------------------------------------------------------------------------------
# Geometria da tabela de licenças (QA-D do nº 14, Gate D: Empresa invadia Rodovia e Nº Processo).
# O bbox é o dos pixels de tinta medido pelo Pillow (`ImageDraw.textbbox`) na fonte do desenho.
# O comparador do golden não mede texto dentro de PNG: esta é a checagem de "texto fora da
# célula" para os visuais reconstruídos.


def _long_license_rows() -> list[LicenseRow]:
    companies = ["CONSTRUTORA SIGMA - CSG", "CONSTRUTORA OMEGA S/A - CLX",
                 "EMPRESA SINTÉTICA DE NOME MUITO MAIS LONGO QUE A COLUNA LTDA - ESML",
                 "X" * 60]
    return [
        LicenseRow(road=["RD-101", "RD-102a", "RD-103", "RD-104"][i % 4],
                   company=companies[i % 4], process=f"{2025000000 + i}/2025-ABCDEFGH",
                   license=str(202514316 + i),
                   phase="Licença Ambiental - Canteiro de obra e Usina de Asfalto",
                   valid_until=date(2030, 1, 1), status="Aguardando a liberação")
        for i in range(8)
    ]


def _with_rows(rows) -> EnvironmentalIndexData:
    return EnvironmentalIndexData(**{**_index_data().__dict__, "rows": rows})


def test_license_table_text_never_leaves_its_cell(rules):
    from prog_g2_report.render.visuals.p24_environmental import draw_environmental_index

    _canvas, layout = draw_environmental_index(_with_rows(_long_license_rows()), rules)
    assert layout.text_boxes, "nenhum texto de célula registrado"
    tol = 0.5   # px canônicos (arredondamento do supersampling)
    for col, row, text, (x0, y0, x1, y1), (cx0, cy0, cx1, cy1) in layout.text_boxes:
        assert x0 >= cx0 - tol and x1 <= cx1 + tol, f"{col}[{row}] {text!r} sai da célula"
        assert y0 >= cy0 - tol and y1 <= cy1 + tol, f"{col}[{row}] {text!r} sai da linha"
    by_row: dict[int, list] = {}
    for col, row, _t, box, _cell in layout.text_boxes:
        by_row.setdefault(row, []).append((col, box))
    for items in by_row.values():                 # vizinhas da mesma linha não se sobrepõem
        for i, (ca, a) in enumerate(items):
            for cb, b in items[i + 1:]:
                if ca != cb:
                    assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (ca, cb)


def test_long_company_wraps_and_row_grows(rules):
    from prog_g2_report.render.visuals.p24_environmental import draw_environmental_index

    _c1, short = draw_environmental_index(_with_rows(_license_rows(8)), rules)
    _c2, long = draw_environmental_index(_with_rows(_long_license_rows()), rules)
    assert long.bottom > short.bottom
    lines = [t for col, row, t, _b, _c in long.text_boxes if col == "Empresa" and row == 2]
    assert len(lines) >= 2                                       # quebrou dentro da célula


def test_company_display_name_from_rules(rules):
    from prog_g2_report.render.visuals.p24_environmental import company_display

    spec = rules["P2.4_ENV_INDICES_PANEL"]["charts"]["table"]
    assert company_display("CONSTRUTORA SIGMA - CSG", spec) == \
        "Construtora Sigma"
    assert company_display("OUTRA EMPRESA", spec) == "OUTRA EMPRESA"
