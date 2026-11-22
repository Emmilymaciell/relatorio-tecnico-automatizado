"""Controle de Produtos com renderizador FALSO: ordem física, um EMF por recorte, fatos."""

from dataclasses import dataclass

import pytest
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT

from prog_g2_report.render.product_control import build_product_control, resolve_config
from prog_g2_report.sources.master_list import MasterListRow
from emf_synth import make_emf

WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
PT_TO_01MM = 2540 / 72   # 1 pt = 25,4/72 mm = 35,28 centésimos de mm


@dataclass(frozen=True)
class Geom:
    width_pt: float
    header_height_pt: float


class FakeRenderer:
    """Devolve um EMF cujo frame tem exatamente a altura prevista (+ `extra_pt` por recorte)."""

    def __init__(self, width_pt=500.0, header_pt=60.0, extra_pt=0.0):
        self.geom = Geom(width_pt, header_pt)
        self.extra_pt = extra_pt
        self.measures = 0
        self.calls = []

    def measure(self, xlsx_path, sheet, columns="D:I", header_rows=(1, 3)):
        self.measures += 1
        return self.geom

    def render_slices(self, xlsx_path, sheet, selected_physical_rows, slices, **kw):
        self.calls.append({"rows": list(selected_physical_rows), "slices": list(slices), **kw})
        out = []
        for s in slices:
            h_pt = self.geom.header_height_pt + len(s) * kw["row_height_pt"] + self.extra_pt
            frame = (0, 0, round(self.geom.width_pt * PT_TO_01MM), round(h_pt * PT_TO_01MM))
            # dispositivo quadrado: aspecto do frame = aspecto em pixels
            out.append(make_emf((0, 0, 999, 999), frame, (1000, 1000), (100, 100)))
        return out


def _row(n, doc, product="2.2 PROJETOS"):
    return MasterListRow(physical_row=n, product=product, company=None, document=doc,
                         manifestation=None, description=None, venture=None, delivery_date=None,
                         delivery_status=None, version=1, report_number=7)


MODEL = {"control_of_products": {"width_cm": 17.5,
                                 "render": {"row_height_pt": 30.0, "avail_height_cm": 20.0}}}


def _blobs(doc):
    rel_by_id = {rid: r.target_part for rid, r in doc.part.rels.items() if r.reltype == RT.IMAGE}
    blip = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
    rid_attr = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
    return [rel_by_id[b.get(rid_attr)].blob for b in doc.element.body.iter(blip)]


def test_physical_order_one_emf_per_slice_and_facts():
    # 30 pt × 17,5/500 = 1,05 cm por linha; cabeçalho 2,1 cm; 20 cm úteis → 17 linhas/recorte
    rows = [_row(100 + i, f"NT-{500 + i:03d}.1") for i in range(40)]
    shuffled = rows[::-1]
    doc = Document()
    paragraphs = []

    def factory():
        p = doc.add_paragraph()
        paragraphs.append(p)
        return p

    renderer = FakeRenderer()
    result = build_product_control(factory, shuffled, "lista.xlsx", MODEL, renderer)

    assert result.status == "OK", result.detail
    assert result.component_id == "CONTROL_OF_PRODUCTS"
    assert result.facts["rows"] == 40
    assert result.facts["slices"] == [17, 17, 6]
    assert result.facts["documents"] == [r.document for r in rows]       # ordem física
    assert result.facts["physical_rows"] == [[100, 116], [117, 133], [134, 139]]
    assert all(h <= 20.0 for h in result.facts["heights_cm"])

    call = renderer.calls[0]
    assert call["rows"] == list(range(100, 140))
    assert call["row_height_pt"] == 30.0
    assert call["columns"] == "D:I" and call["header_rows"] == (1, 3)
    assert renderer.measures == 1

    assert len(paragraphs) == 3                                           # um parágrafo por EMF
    for p in paragraphs:
        assert len(p._p.findall(f".//{WP}inline")) == 1
    assert len(_blobs(doc)) == 3


def test_empty_block_is_skipped_without_rendering():
    renderer = FakeRenderer()
    result = build_product_control(lambda: pytest.fail("não deve criar parágrafo"), [],
                                   "lista.xlsx", MODEL, renderer)
    assert result.status == "SKIPPED"
    assert result.facts == {"rows": 0, "slices": [], "documents": []}
    assert renderer.calls == [] and renderer.measures == 0


def test_duplicate_physical_rows_are_rejected():
    rows = [_row(5, "A"), _row(5, "B")]
    with pytest.raises(ValueError, match="repetidas"):
        build_product_control(Document().add_paragraph, rows, "x.xlsx", MODEL, FakeRenderer())


def test_geometry_from_model_skips_measure():
    model = {"control_of_products": {"width_cm": 17.5, "render": {
        "row_height_pt": 30.0, "avail_height_cm": 20.0, "source_width_pt": 500.0,
        "header_height_pt": 60.0}}}
    renderer = FakeRenderer()
    doc = Document()
    result = build_product_control(doc.add_paragraph, [_row(10, "X")], "x.xlsx", model, renderer)
    assert result.status == "OK" and renderer.measures == 0
    assert result.facts["slices"] == [1]


def test_overflow_triggers_one_repagination():
    # o desenho real é 40 pt mais alto que o previsto: o 1º corte estoura, o 2º corrige
    rows = [_row(100 + i, f"D{i}") for i in range(40)]
    renderer = FakeRenderer(extra_pt=40.0)
    result = build_product_control(Document().add_paragraph, rows, "x.xlsx", MODEL, renderer)
    assert len(renderer.calls) == 2
    assert result.status == "OK", result.detail
    assert all(h <= 20.0 + 0.005 for h in result.facts["heights_cm"])
    assert sum(result.facts["slices"]) == 40
    assert max(result.facts["slices"]) < 17


FILL = {"control_of_products": {"width_cm": 17.5, "render": {
    "row_height_pt": 30.0, "avail_height_cm": 20.0, "first_slice_fill": True,
    "first_slice_min_rows": 3, "normalize_data_font": True}}}


def test_first_slice_fills_the_page_of_the_call_sentence():
    # DEC-010 §3: 8,5 cm livres -> (8,5 − 2,1) / 1,05 = 6 linhas na página da frase
    rows = [_row(100 + i, f"D{i}") for i in range(40)]
    renderer = FakeRenderer()
    result = build_product_control(Document().add_paragraph, rows, "x.xlsx", FILL, renderer,
                                   first_page_free_cm=8.5, lead_block_cm=0.8)
    assert result.status == "OK", result.detail
    assert result.facts["slices"] == [6, 17, 17]
    assert result.facts["first_slice"]["mode"] == "same_page"
    assert result.facts["heights_cm"][0] <= 8.5


def test_first_slice_goes_down_with_the_sentence_when_too_few_rows_fit():
    # 4 cm livres -> 1 linha < first_slice_min_rows: desce com a frase (20 − 0,8 cm)
    rows = [_row(100 + i, f"D{i}") for i in range(40)]
    result = build_product_control(Document().add_paragraph, rows, "x.xlsx", FILL,
                                   FakeRenderer(), first_page_free_cm=4.0, lead_block_cm=0.8)
    assert result.facts["first_slice"]["mode"] == "next_page"
    assert result.facts["slices"] == [16, 17, 7]
    assert result.facts["heights_cm"][0] <= 20.0 - 0.8


def test_without_measurement_or_flag_the_first_slice_is_a_full_page():
    rows = [_row(100 + i, f"D{i}") for i in range(40)]
    plain = build_product_control(Document().add_paragraph, rows, "x.xlsx", FILL, FakeRenderer())
    assert plain.facts["slices"] == [17, 17, 6] and "first_slice" not in plain.facts
    off = build_product_control(Document().add_paragraph, rows, "x.xlsx", MODEL, FakeRenderer(),
                                first_page_free_cm=8.5)
    assert off.facts["slices"] == [17, 17, 6] and "first_slice" not in off.facts


def test_normalize_data_font_is_passed_to_the_renderer():
    renderer = FakeRenderer()
    build_product_control(Document().add_paragraph, [_row(10, "X")], "x.xlsx", FILL, renderer)
    assert renderer.calls[0]["normalize_data_font"] is True
    renderer = FakeRenderer()
    build_product_control(Document().add_paragraph, [_row(10, "X")], "x.xlsx", MODEL, renderer)
    assert renderer.calls[0]["normalize_data_font"] is False


def test_model_turns_on_first_slice_and_font_normalization():
    import yaml

    from prog_g2_report import REPO_ROOT

    model = yaml.safe_load((REPO_ROOT / "config" / "g2_report_model.yaml").read_text("utf-8"))
    cfg = resolve_config(model)
    assert cfg["first_slice_fill"] is True and cfg["normalize_data_font"] is True
    assert cfg["first_slice_min_rows"] >= 1 and cfg["first_slice_gap_cm"] > 0


def test_resolve_config_accepts_block_or_full_model_and_defaults():
    full = resolve_config(MODEL)
    block = resolve_config(MODEL["control_of_products"])
    assert full == block
    assert full["width_cm"] == 17.5 and full["row_height_pt"] == 30.0
    assert full["sheet"] == "Controle Geral" and full["aspect"] == "frame"
    defaults = resolve_config({})
    assert defaults["row_height_pt"] == 27.6 and defaults["avail_height_cm"] == 26.2
    assert defaults["row_height_mode"] == "uniform"


# ------------------------------------------------- altura mínima + AutoFit (DEC-010 §4)
AUTOFIT = {"control_of_products": {"width_cm": 17.5, "render": {
    "row_height_pt": 30.0, "avail_height_cm": 20.0, "row_height_mode": "min_autofit",
    "row_height_estimate": {"line_height_pt": 15.0, "chars_per_line": {"description": 20}}}}}


class AutofitRenderer(FakeRenderer):
    """Falso com `measure_row_heights`: devolve alturas por linha física; o EMF tem a altura
    da soma das alturas pedidas (`row_heights_pt`)."""

    def __init__(self, tall: dict[int, float], **kw):
        super().__init__(**kw)
        self.tall = tall
        self.measured = []

    def measure_row_heights(self, xlsx_path, sheet, rows, *, columns, min_height_pt,
                            normalize_data_font):
        self.measured.append(list(rows))
        return [max(min_height_pt, self.tall.get(r, 0.0)) for r in rows]

    def render_slices(self, xlsx_path, sheet, selected_physical_rows, slices, **kw):
        self.calls.append({"rows": list(selected_physical_rows), "slices": list(slices), **kw})
        heights = kw["row_heights_pt"]
        out = []
        for s in slices:
            h_pt = self.geom.header_height_pt + sum(heights[i] for i in s)
            frame = (0, 0, round(self.geom.width_pt * PT_TO_01MM), round(h_pt * PT_TO_01MM))
            out.append(make_emf((0, 0, 999, 999), frame, (1000, 1000), (100, 100)))
        return out


def test_min_autofit_measures_once_and_paginates_by_real_heights():
    # 30 pt = 1,05 cm; cabeçalho 2,1 cm; 20 cm úteis -> 17 linhas uniformes por recorte
    rows = [_row(100 + i, f"NT-{500 + i:03d}.1") for i in range(40)]
    renderer = AutofitRenderer({103: 60.0, 104: 60.0})          # 2 linhas com o dobro
    result = build_product_control(Document().add_paragraph, rows, "x.xlsx", AUTOFIT, renderer)
    assert result.status == "OK", result.detail
    assert renderer.measured == [[r.physical_row for r in rows]]
    assert result.facts["row_heights_source"] == "excel_autofit"
    assert result.facts["tall_rows"] == {"NT-503.1": 60.0, "NT-504.1": 60.0}
    assert result.facts["slices"] == [15, 17, 8]                # 2 linhas a menos no 1º
    sent = renderer.calls[-1]["row_heights_pt"]
    assert sent[3] == sent[4] == 60.0 and sent[0] == 30.0 and len(sent) == 40
    assert renderer.calls[-1]["row_height_pt"] == 30.0          # mínimo continua informado
    assert all(h <= 20.0 + 0.005 for h in result.facts["heights_cm"])


def test_min_autofit_without_measurement_uses_the_estimator():
    long = "uma descrição bem comprida que ocupa três linhas"     # 17 + 18 + 11 caracteres
    rows = [MasterListRow(physical_row=100 + i, product="2.2 PROJETOS", company=None,
                          document=f"NT-{500 + i:03d}.1", manifestation=None,
                          description=long if i == 1 else "curta", venture=None,
                          delivery_date=None, delivery_status=None, version=1, report_number=7)
            for i in range(3)]

    class NoMeasure(AutofitRenderer):
        measure_row_heights = None                               # renderizador sem medição

    renderer = NoMeasure({})
    result = build_product_control(Document().add_paragraph, rows, "x.xlsx", AUTOFIT, renderer)
    assert result.facts["row_heights_source"] == "estimate"
    assert result.facts["tall_rows"] == {"NT-501.1": 45.0}       # 3 linhas × 15 pt
    assert renderer.calls[-1]["row_heights_pt"] == [30.0, 45.0, 30.0]


def test_uniform_mode_sends_no_per_row_heights():
    renderer = AutofitRenderer({})
    renderer.render_slices = FakeRenderer.render_slices.__get__(renderer)
    result = build_product_control(Document().add_paragraph, [_row(10, "X")], "x.xlsx", MODEL,
                                   renderer)
    assert result.facts["row_height_mode"] == "uniform" and "tall_rows" not in result.facts
    assert "row_heights_pt" not in renderer.calls[0] and renderer.measured == []


def test_model_uses_min_autofit_with_the_documented_estimator():
    import yaml

    from prog_g2_report import REPO_ROOT

    model = yaml.safe_load((REPO_ROOT / "config" / "g2_report_model.yaml").read_text("utf-8"))
    cfg = resolve_config(model)
    assert cfg["row_height_mode"] == "min_autofit" and cfg["row_height_pt"] == 27.6
    estimate = cfg["row_height_estimate"]
    assert estimate["line_height_pt"] > 0
    assert set(estimate["chars_per_line"]) <= {"manifestation", "description", "delivery_status"}
    with pytest.raises(ValueError, match="row_height_mode"):
        resolve_config({"render_params": {"row_height_mode": "auto"}})
