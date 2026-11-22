"""Montador do Relatório G2 (`builder.assemble.build_report`).

Offline: fontes SINTÉTICAS (Lista Mestra, planilha de projetos e planilha ambiental geradas aqui),
assets sintéticos com manifesto próprio, office=False ou Excel/Word falsos.
`-m office`: o nº 14 completo com as fontes locais (tmp/, somente leitura), Excel e Word reais,
e o comparador do golden test (scripts/14_golden_compare.py).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from docx import Document
from docx.enum.section import WD_ORIENT

import _p22_synthetic as syn
from prog_g2_report import REPO_ROOT
from prog_g2_report.builder.assemble import build_report, environmental_from_snapshot
from prog_g2_report.builder.context import (
    BuildMode,
    ReportContext,
    SourceManifest,
    SourceRef,
)
from prog_g2_report.builder.emit import emit_blocktext
from prog_g2_report.render.blocktext import BlockText, Paragraph, Segment
from prog_g2_report.report_id import ReportRef
from emf_synth import make_emf

NUMBER, MONTH = 3, "2026-12"           # relatório sintético (nada do nº 14)
ISSUE, SIGNATURE, REF = date(2027, 1, 11), date(2027, 1, 12), date(2027, 1, 8)
# rodovias do contrato: os painéis do 2.4 têm cor por rodovia em g2_render_rules.yaml
ROADS = ("RD-103", "RD-101")
MODEL_ASSETS = (
    "presentation_coordination_strip", "landscape_block_01_delivery_periodicity",
    "landscape_block_02_periodic_reports", "landscape_block_03_environmental_conditions",
    "landscape_block_04_meeting_minutes", "landscape_block_05_operational_org_cover",
    "landscape_block_06_functional_org_chart", "landscape_block_07_projects_coordination",
    "landscape_block_08_works_field_coordination", "p22_predecessor_disciplines_diagram",
)
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


# ------------------------------------------------------------------ fontes sintéticas
ML_HEADER = ["Produto", "Empresa", "Documento", "Manifestação", "Descrição", "Empreendimento",
             "Data Entrega", "Status Entrega", "Versão", "N° Relatório", "Período"]


def _ml_rows() -> list[list]:
    d = datetime(2026, 12, 20)
    rows = [
        ["2.1 COORDENAÇÃO SETORIAL", "Empresa A", "AT-501.1", "Ata de Reunião",
         "Reunião de alinhamento técnico", ROADS[0], d, "Entregue", 1, NUMBER, None],
        ["2.2 PROJETOS", "Empresa A", "PA-502.1", "Parecer", "Análise do projeto geométrico",
         ROADS[1], d, "Entregue", 1, NUMBER, None],
        ["2.4 GERENCIAMENTO TÉCNICO", "Empresa B", "RO-510.1", "Relatório Semanal de Obras",
         "Relatório semanal", ROADS[0], d, "Entregue", 1, NUMBER, "01/12/2026 a 07/12/2026"],
        ["2.4 GERENCIAMENTO TÉCNICO", "Empresa B", "RO-511.1", "Relatório Semanal de Obras",
         "Relatório semanal", ROADS[0], d, "Entregue", 1, NUMBER, "08/12/2026 a 14/12/2026"],
        ["2.4 GERENCIAMENTO TÉCNICO", "Empresa B", "BM-001.1", "Boletim de Medição",
         "Boletim de medição referente a Novembro/2026", ROADS[1], d, "Em elaboração", 1,
         NUMBER, None],
        ["2.1 COORDENAÇÃO SETORIAL", "Empresa A", "AT-500.1", "Ata de Reunião", "outro mês",
         ROADS[0], d, "Entregue", 1, NUMBER - 1, None],
    ]
    return rows


def _write_master_list(path: Path) -> Path:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Controle Geral"
    ws.append(["Programa | Controle de Produtos"])
    ws.append([])
    ws.append([None, *ML_HEADER])
    for row in _ml_rows():
        ws.append([None, *row])
    wb.save(path)
    return path


def _write_projects(path: Path) -> Path:
    import openpyxl

    rows = [
        syn.approved("1.1", ROADS[0], syn.EST, "Estudos de Tráfego"),
        syn.in_analysis("2.1", ROADS[0], syn.PRI, "Projeto Geométrico"),
        syn.late("2.2", ROADS[0], syn.PRI, "Projeto de Drenagem"),
        syn.approved("1.1", ROADS[1], syn.EST, "Estudos de Tráfego"),
        syn.rejected("2.1", ROADS[1], syn.PRI, "Projeto Geométrico", "Aguardando reentrega"),
        # disciplinas da Análise PROGRAMA de P2.2_DESAPROPRIACAO/INTERFERENCIAS (schema.derived.prog)
        syn.approved("1.6", ROADS[0], syn.EST,
                     "Documentação para Declaração de Utilidade Pública (DUP)"),
        syn.approved("1.6", ROADS[1], syn.EST,
                     "Documentação para Declaração de Utilidade Pública (DUP)",
                     evaluation="Aprovado com ressalvas"),
        syn.in_analysis("3.5", ROADS[1], syn.SEC,
                        "Projeto de Interferência de Iluminação e Rede Elétrica"),
    ]
    sheets = {
        "Projetos": syn.sheet(*rows),
        "GED": syn.ged_sheet(syn.ged(ROADS[0], syn.EST, "Estudos de Tráfego", date(2026, 3, 1)),
                             syn.ged(ROADS[1], syn.EST, "Estudos de Tráfego", date(2026, 3, 1))),
        "Painel de Controle": syn.panel(*ROADS),
    }
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, values in sheets.items():
        ws = wb.create_sheet(name)
        for row in values:
            ws.append(list(row))
    wb.save(path)
    return path


def _write_environmental(path: Path) -> Path:
    import openpyxl

    lic_header = (None, "Nº Licença", "Nº Processo", "Empresa", "Fase da licença",
                  "Data de emissão", "Data de validade", "Órgão", "Atividade", "Status")
    cond_header = ("Item", "Nº Licença", "Nome da condicionante",
                   "Descrição/Informação complementar", "Evidências salvas em",
                   "Data da entrega", "Status", "Observações", "Responsável", "Vence em",
                   "Próxima entrega", "Vence em")
    companies = {"CONSTRUTORA ALFA": ROADS[0], "CONSTRUTORA BETA": ROADS[1]}
    sheets = {
        "Licenças": [("Licenças",), lic_header,
                     (None, 1, 123, "CONSTRUTORA ALFA", "Licença Ambiental Única",
                      None, datetime(2030, 1, 1), "OAMB", "x", "Vigente"),
                     (None, None, 124, "CONSTRUTORA BETA", "Outorga de uso de recurso hídrico",
                      None, None, "OAMB", "x", "Aguardando a liberação")],
        "Condicionantes": [("Condicionantes",), cond_header,
                           (1, 1, 5, None, None, REF + timedelta(days=200), "No prazo", None,
                            "CONSTRUTORA ALFA", 0, None, 0),
                           (2, 1, 5, None, None, REF + timedelta(days=10), "No prazo", None,
                            "CONSTRUTORA BETA", 0, None, 0)],
        "Empresas": [("Cadastro",), (),
                     (None, "Empresa", None, None, None, None, "Rodovia")]
        + [(None, c, "x", None, None, None, r) for c, r in companies.items()],
    }
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, values in sheets.items():
        ws = wb.create_sheet(name)
        for row in values:
            ws.append(list(row))
    wb.save(path)
    return path


def _png(color: tuple[int, int, int], size=(40, 20)) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _assets(directory: Path) -> Path:
    """Assets sintéticos + manifesto com os sha1 deles (mesmos asset_id do modelo)."""
    directory.mkdir(parents=True, exist_ok=True)
    entries = []
    for i, asset_id in enumerate(MODEL_ASSETS):
        if asset_id.startswith("p22_"):
            name, data, width = f"{asset_id}.emf", make_emf(), 15.0
        else:
            name, data = f"{asset_id}.png", _png((10 * i, 100, 200))
            width = 16.0 if asset_id.startswith("presentation") else 27.0   # 27 > área útil
        (directory / name).write_bytes(data)
        entries.append({"asset_id": asset_id, "file": f"assets/discovered/raw/{name}",
                        "sha1": hashlib.sha1(data).hexdigest(), "width_cm": width})
    (directory / "cover_background_composite.png").write_bytes(_png((28, 85, 96), (60, 86)))
    manifest = directory / "assets_manifest.yaml"
    manifest.write_text(yaml.safe_dump({"assets": entries}), encoding="utf-8")
    return manifest


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    root = tmp_path_factory.mktemp("assemble_sources")
    sources = SourceManifest()
    sources.add(SourceRef("master_list", "Lista Mestra (sintética)",
                          _write_master_list(root / "lista_mestre_v1.0.xlsx"), version_id="1.0"))
    sources.add(SourceRef("projects", "Projetos (sintética)", _write_projects(root / "proj.xlsx"),
                          version_id="7.0"))
    sources.add(SourceRef("environmental", "Ambiental (sintética)",
                          _write_environmental(root / "amb.xlsx"), version_id="9.0"))
    manifest = _assets(root / "assets")
    inputs_path = Path(__file__).parent / "fixtures" / "golden_inputs_example.yaml"
    inputs = yaml.safe_load(inputs_path.read_text(encoding="utf-8"))
    report = ReportContext(ReportRef(NUMBER, MONTH), issue_date=ISSUE, signature_date=SIGNATURE)
    return {"sources": sources, "assets_dir": root / "assets", "manifest": manifest,
            "inputs": inputs, "inputs_path": inputs_path, "report": report, "root": root}


@pytest.fixture(scope="module")
def built(synthetic, tmp_path_factory):
    out = tmp_path_factory.mktemp("assemble_out")
    result = build_report(synthetic["report"], synthetic["sources"], synthetic["inputs"], out,
                          office=False, assets_dir=synthetic["assets_dir"],
                          assets_manifest=synthetic["manifest"],
                          inputs_path=synthetic["inputs_path"])
    return result, out


def _status(result, component_id):
    return next(c.status for c in result.components if c.component_id == component_id)


# ------------------------------------------------------------------ office=False
def test_document_opens_with_three_sections_in_model_order(built):
    result, _ = built
    doc = Document(str(result.docx_path))
    orientations = [s.orientation for s in doc.sections]
    assert orientations == [WD_ORIENT.PORTRAIT, WD_ORIENT.LANDSCAPE, WD_ORIENT.PORTRAIT]
    assert result.pdf_path is None


def test_product_titles_2_1_to_2_6_in_order(built):
    result, _ = built
    doc = Document(str(result.docx_path))
    titles = [p.text for p in doc.paragraphs if p.style.style_id == "Ttulo2"]
    assert [t.split(" – ")[0] for t in titles] == [f"Produto 2.{i}" for i in range(1, 7)]


def test_no_unresolved_placeholder_in_xml(built):
    result, _ = built
    xml = Document(str(result.docx_path)).element.xml
    assert "{" not in xml.replace("{http", "")


def test_pending_markers_are_listed_in_the_result(built):
    result, _ = built
    assert not result.ok
    pending = {c.component_id for c in result.components if c.status.startswith("PENDING")}
    for cid in ("P2.1_CONTROLE_PRODUTOS", "P2.2_CONTROLE_PRODUTOS", "P2.4_CONTROLE_PRODUTOS",
                "ANEXOS_CONTROLE_CONSOLIDADO", "ENC_P1", "CLOSING_PAGE_COUNT"):
        assert cid in pending, cid
    text = "\n".join(p.text for p in Document(str(result.docx_path)).paragraphs)
    for cid in ("P2.1_CONTROLE_PRODUTOS", "ENC_P1", "ANEXOS_CONTROLE_CONSOLIDADO"):
        assert f"[PENDENTE: {cid}]" in text
    # sem linhas no relatório: 2.3, 2.5 e 2.6 só com a frase de ausência
    assert _status(result, "P2.3_NO_ACTIVITY") == "OK"
    assert _status(result, "P2.3_TABLE_CALL") == "SKIPPED"


def test_number_month_and_texts_come_from_the_context(built):
    result, _ = built
    text = "\n".join(p.text for p in Document(str(result.docx_path)).paragraphs)
    assert f"Relatório Mensal N° {NUMBER:02d}, referente ao período de Dezembro/2026" in text
    assert "Capital, 12 de Janeiro de 2027" in text
    assert "Referente ao acompanhamento de projeto executivo da Rodovia RD-103:" in text
    assert "N° 14" not in text and "Agosto/2026" not in text


# Textos e contagens que só existem no nº 14 (entrada humana ou fato de agosto): nenhum pode
# aparecer num relatório de outro mês gerado com outras fontes e entradas.
AUGUST_ONLY = ("Agosto/2026", "N° 14", "quarenta e três", "cento e quarenta e nove",
               "Publicado em 01/09/2026", "Realizado pela primeira vez o envio a GDP",
               "09 de Setembro de 2026", "RO-548.1", "complementação da DUP")


def test_report_15_synthetic_carries_nothing_from_august(synthetic, tmp_path):
    report = ReportContext(ReportRef(15, "2026-09"), issue_date=date(2026, 10, 8),
                           signature_date=date(2026, 10, 9))
    result = build_report(report, synthetic["sources"], synthetic["inputs"], tmp_path / "out",
                          office=False, assets_dir=synthetic["assets_dir"],
                          assets_manifest=synthetic["manifest"])
    text = "\n".join(p.text for p in Document(str(result.docx_path)).paragraphs)
    assert "Relatório Mensal N° 15, referente ao período de Setembro/2026" in text
    for needle in AUGUST_ONLY:
        assert needle not in text, needle


def test_p22_external_status_rendered_from_the_input(built):
    result, _ = built
    assert _status(result, "P2.2_DESAPROPRIACAO") == "OK"
    assert _status(result, "P2.2_INTERFERENCIAS") == "OK"
    paragraphs = [p.text for p in Document(str(result.docx_path)).paragraphs]
    # ORDER_P22 (sem Painel: road_order.value) põe RD-103 antes de RD-101
    facts = next(c.facts for c in result.components if c.component_id == "P2.2_DESAPROPRIACAO")
    assert facts["matrices"]["dup"] == ["RD-103", "RD-101"]
    # Análise Programa derivada da aba Projetos (schema.derived.prog), não da entrada
    assert "Análise Programa: Aprovado;" in paragraphs                     # DUP RD-103
    assert "Análise Programa: Aprovado com ressalva;" in paragraphs        # DUP RD-101 (DEC-015)
    assert "Análise Programa: Em análise;" in paragraphs          # interferências RD-101
    assert facts["derived"]["p22_external_status.RD-103.dup.prog"]["set"] == "approval"
    assert facts["derived"]["p22_external_status.RD-101.dup.prog"]["set"] == \
        "approval_with_reservation"
    # coerência com o corpo do 2.2 do mesmo documento (QA4-H): a DUP da RD-101 sai 'com
    # ressalva' também na linha de Aprovação do bloco por rodovia
    dup = "Documentação para Declaração de Utilidade Pública (DUP)"
    assert any(p.startswith("Aprovação:") and dup in p and "com ressalva" in p
               for p in paragraphs)
    assert "Manifestação concessionária: Status sintético cinco;" in paragraphs
    assert "Iniciado processo de realocação de interferências: Status sintético seis." \
        in paragraphs


def test_static_assets_checked_by_sha1_and_width_limited(built):
    result, _ = built
    landscape = next(c for c in result.components if c.component_id == "P2.1_LANDSCAPE_BLOCK")
    assert landscape.status == "OK"
    assert len(landscape.facts["assets"]) == 8
    # positioning.landscape_width = manifest (GAP-004 aberto: reproduzir o histórico)
    assert max(a["width_cm"] for a in landscape.facts["assets"]) == 27.0     # > 26,2 cm úteis
    assert len(landscape.facts["exceeds_usable_area"]) == 8
    assert _status(result, "P2.2_PREDECESSORAS_IMG") == "OK"
    assert _status(result, "APRES_LOGO_GRUPOS") == "OK"


def test_landscape_width_limited_when_the_model_says_so(synthetic, tmp_path):
    from prog_g2_report.model import load_model

    model = load_model()
    model["positioning"]["landscape_width"]["value"] = "limit_to_usable_area"
    result = build_report(synthetic["report"], synthetic["sources"], synthetic["inputs"],
                          tmp_path / "out", office=False, assets_dir=synthetic["assets_dir"],
                          assets_manifest=synthetic["manifest"], model=model)
    landscape = next(c for c in result.components if c.component_id == "P2.1_LANDSCAPE_BLOCK")
    assert max(a["width_cm"] for a in landscape.facts["assets"]) < 27.0     # área útil 26,2 cm
    assert len(landscape.facts["width_limited"]) == 8


def _body(result):
    doc = Document(str(result.docx_path))
    out = []
    for el in doc.element.body.iterchildren():
        text = "".join(t.text or "" for t in el.iter(f"{W}t"))
        out.append((el.tag.split("}")[1], text, bool(list(el.iter(f"{W}drawing")))))
    return out


def test_spacers_between_blocks_follow_the_model(built):
    result, _ = built
    body = _body(result)
    texts = [t for _, t, _ in body]
    title = texts.index("Apresentação")
    # positioning.spacers: vazio após o título, após o 1º parágrafo e em volta da faixa de fotos
    assert body[title + 1][1] == "" and not body[title + 1][2]
    assert body[title + 2][1].startswith("A seleção da empresa")
    assert body[title + 3][1] == "" and not body[title + 3][2]
    assert body[title + 4][2]                                   # faixa de fotos
    assert body[title + 5][1] == "" and not body[title + 5][2]
    assert body[title + 6][1].startswith("O Programa é formado")
    assert body[title + 7][1] == ""
    assert body[title + 8][1].startswith("O Consórcio Estruturador")
    assert body[title + 9][1].startswith("O presente Relatório")   # sem vazio no modelo


def test_declarative_slots_are_resolved_by_the_engine(built):
    from prog_g2_report.builder.blocks import load_blocks

    result, _ = built
    assert _status(result, "P2.2_ROTINA_REUNIOES") == "OK"
    assert _status(result, "P2.4_RO_INTRO") == "OK"
    blocks = {b.block_id: b.raw for b in load_blocks()}
    text = "\n".join(p.text for p in Document(str(result.docx_path)).paragraphs)
    # a Lista Mestra sintética tem AT no 2.1: cláusula das Atas presente
    assert blocks["P2.2_ROTINA_REUNIOES"]["slots"]["atas_clause"]["value_if_true"] in text
    # ORDER_RO do modelo (contract.highway_orders -> p24_blocks.yaml common.highway_orders)
    rules = yaml.safe_load((REPO_ROOT / "config" / "data_rules" / "p24_blocks.yaml")
                           .read_text(encoding="utf-8"))
    order = rules["common"]["highway_orders"]["ORDER_RO"]
    assert f"obras dos trechos {', '.join(order[:-1])} e {order[-1]}, bem como" in text


def test_gamb_items_come_from_the_contract_template(built):
    from prog_g2_report.model import load_model

    result, _ = built
    model = load_model()
    rules = yaml.safe_load((REPO_ROOT / "config" / "data_rules" / "p24_blocks.yaml")
                           .read_text(encoding="utf-8"))
    order = rules["common"]["highway_orders"]["ORDER_GAMB"]
    process = {h["code"]: h["gamb_process"] for h in model["contract"]["highways"]}
    doc = Document(str(result.docx_path))
    items = [p for p in doc.paragraphs if "Processo " in p.text and p.text[:2].endswith(")")]
    assert [p.text for p in items] == [f"{chr(97 + i)}) {code}: Processo {process[code]}."
                                       for i, code in enumerate(order)]
    assert all(any(r.bold and r.text == f"{code}:" for r in p.runs)
               for p, code in zip(items, order, strict=True))


def test_static_asset_alignment_from_the_model(built):
    result, _ = built
    doc = Document(str(result.docx_path))
    images = [p for p in doc.paragraphs if p._p.findall(f".//{W}drawing")
              and p._p.find(f".//{W}jc") is not None]
    centered = [p for p in images if p._p.find(f".//{W}jc").get(f"{W}val") == "center"]
    # diagrama de predecessoras (positioning.static_assets) + 8 do bloco paisagem
    assert len(centered) >= 9


def test_visual_slots_resolved_by_providers(built):
    result, _ = built
    images = {c.component_id: c.status for c in result.components
              if c.component_id.startswith("IMAGE:")}
    assert images.get("IMAGE:P2.2_ROAD_DASHBOARD:RD-103") == "OK"
    assert images.get("IMAGE:P2.4_ENV_INDICES_PANEL") == "OK"
    assert any(k.startswith("IMAGE:P2.4_CONDITIONS_PANEL:") for k in images)


def test_manifest_written_with_sources_model_and_components(built):
    result, out = built
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["model"]["version"] == result.model_version
    keys = {s["key"]: s for s in manifest["sources"]}
    assert keys["master_list"]["version_id"] == "1.0"
    assert len(keys["master_list"]["sha1"]) == 40
    assert "ENC_P1" in manifest["pending"]
    assert manifest["report"] == {"report_number": NUMBER, "reference_month": MONTH,
                                  "issue_date": "2027-01-11", "signature_date": "2027-01-12",
                                  "mode": "PRODUCTION"}
    assert {c["component_id"] for c in manifest["components"]} >= {"COVER", "TOC", "ENC_P1"}


def test_missing_asset_fails_visibly(synthetic, tmp_path):
    assets = tmp_path / "assets"
    manifest = _assets(assets)
    (assets / "landscape_block_03_environmental_conditions.png").write_bytes(_png((1, 2, 3)))
    result = build_report(synthetic["report"], synthetic["sources"], synthetic["inputs"],
                          tmp_path / "out", office=False, assets_dir=assets,
                          assets_manifest=manifest)
    landscape = next(c for c in result.components if c.component_id == "P2.1_LANDSCAPE_BLOCK")
    assert landscape.status == "FAILED" and "sha1 divergente" in landscape.detail


# ------------------------------------------------------------------ Excel/Word falsos
class _Geom:
    width_pt, header_height_pt = 500.0, 60.0


class FakeExcel:
    def __init__(self):
        self.calls = 0
        self.closed = False

    def measure(self, *args, **kwargs):
        return _Geom()

    def render_slices(self, xlsx_path, sheet, rows, slices, **kw):
        self.calls += 1
        out = []
        for s in slices:
            h_pt = _Geom.header_height_pt + len(s) * kw["row_height_pt"]
            frame = (0, 0, round(500 * 2540 / 72), round(h_pt * 2540 / 72))
            out.append(make_emf((0, 0, 999, 999), frame, (1000, 1000), (100, 100)))
        return out

    def close(self):
        self.closed = True


def test_two_passes_fill_page_count_from_the_pdf(synthetic, tmp_path):
    import pymupdf

    excel = FakeExcel()
    exported = []

    def exporter(docx_path, pdf_path):
        exported.append(Path(docx_path).name)
        pdf = pymupdf.open()
        for _ in range(9):
            pdf.new_page()
        pdf.save(str(pdf_path))
        pdf.close()
        return 9

    result = build_report(synthetic["report"], synthetic["sources"], synthetic["inputs"],
                          tmp_path / "out", office=True, assets_dir=synthetic["assets_dir"],
                          assets_manifest=synthetic["manifest"], renderer_factory=lambda: excel,
                          pdf_exporter=exporter)
    assert len(exported) == 2                       # provisório -> 9 -> confirmado
    assert _status(result, "CLOSING_PAGE_COUNT") == "OK"
    assert _status(result, "ENC_P1") == "OK"
    assert _status(result, "P2.1_CONTROLE_PRODUTOS") == "OK"
    assert _status(result, "ANEXOS_CONTROLE_CONSOLIDADO") == "OK"
    assert excel.calls == 4 and excel.closed       # 2.1, 2.2, 2.4 e anexos; 2ª passada em cache
    text = "\n".join(p.text for p in Document(str(result.docx_path)).paragraphs)
    assert "9 (nove) páginas" in text
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert [p["pdf_pages"] for p in manifest["passes"]] == [9, 9]


def test_master_list_in_memory_builds_texts_but_product_control_stays_pending(synthetic, tmp_path):
    """`--master-list-version` sem arquivo: seleção, textos e contagem de anexos saem da versão
    lida em memória; o Controle de Produtos fica PENDING (Excel COM exige o arquivo, GAP-015)."""
    import pymupdf

    from prog_g2_report.sources import master_list_remote as remote

    data = _write_master_list(tmp_path / "synthetic.xlsx").read_bytes()
    (tmp_path / "synthetic.xlsx").unlink()

    class Graph:
        def versions(self, drive_id, item_id):
            return [{"id": "1.0", "lastModifiedDateTime": "2027-01-10T12:00:00Z"}]

        def read_version_bytes(self, drive_id, item_id, version_id):
            return data

    remote.clear_cache()
    version = remote.read_version("drv", "itm", "1", client=Graph())
    sources = SourceManifest()
    for key, ref in synthetic["sources"].sources.items():
        if key != "master_list":
            sources.add(ref)
    sources.add(SourceRef("master_list", "Lista Mestra (sintética)", None, drive_id="drv",
                          item_id="itm", version_id=version.version_id,
                          last_modified=version.last_modified, sha1=version.sha1))
    excel = FakeExcel()

    def exporter(docx_path, pdf_path):
        pdf = pymupdf.open()
        pdf.new_page()
        pdf.save(str(pdf_path))
        pdf.close()
        return 1

    try:
        result = build_report(synthetic["report"], sources, synthetic["inputs"],
                              tmp_path / "out", office=True, assets_dir=synthetic["assets_dir"],
                              assets_manifest=synthetic["manifest"],
                              renderer_factory=lambda: excel, pdf_exporter=exporter)
    finally:
        remote.clear_cache()
    assert excel.calls == 0
    control = next(c for c in result.components if c.component_id == "P2.1_CONTROLE_PRODUTOS")
    assert control.status == "PENDING" and "GAP-015" in control.detail
    assert _status(result, "ANEXOS_CONTROLE_CONSOLIDADO") == "PENDING"
    assert _status(result, "P2.4_RO_LIST") == "OK"              # partes puras saem da versão
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    ml_entry = next(s for s in manifest["sources"] if s["key"] == "master_list")
    assert ml_entry["local_path"] is None and ml_entry["drive_id"] == "drv"
    assert ml_entry["version_id"] == "1.0" and ml_entry["sha1"] == version.sha1
    assert ml_entry["last_modified"] == "2027-01-10T12:00:00Z"


# ------------------------------------------------------------------ peças
def test_emit_blocktext_lists_bold_and_image_slots(tmp_path):
    from g2_text_support import make_rc

    rc = make_rc(tmp=tmp_path)
    block = BlockText("X", [
        Paragraph((Segment("a "), Segment("b", bold=True))),
        Paragraph((Segment("item"),), style="PargrafodaLista", numbering="numId_29", level=0,
                  list_key="L1"),
        Paragraph((Segment("item 2"),), style="PargrafodaLista", numbering="numId_29", level=0,
                  list_key="L1"),
        Paragraph((Segment("outra"),), style="PargrafodaLista", numbering="numId_29", level=0,
                  list_key="L2"),
        Paragraph((Segment(""),), kind="image_slot", ref="SEM_PROVEDOR:x"),
    ])
    result = emit_blocktext(rc, None, block, providers={})
    assert result.status == "OK" and result.facts["bold"] == ["b"]
    assert len(result.facts["numIds"]) == 2                  # uma instância <w:num> por list_key
    image = next(r for r in rc.results if r.component_id == "IMAGE:SEM_PROVEDOR:x")
    assert image.status == "PENDING"
    assert rc.document.paragraphs[-1].text == "[PENDENTE: SEM_PROVEDOR:x]"


def test_environmental_snapshot_extract_is_read_like_the_workbook():
    snap = {
        "licencas_header": ["Nº Licença", "Nº Processo", "Empresa", "Fase da licença",
                            "Data de validade", "Status"],
        "licencas_rows": [{"Nº Licença": None, "Nº Processo": 1, "Empresa": "ALFA",
                           "Fase da licença": "Outorga", "Data de validade": None,
                           "Status": "Aguardando a liberação"}],
        "cond_header": ["Item", "Nº Licença", "Data da entrega", "Status", "Observações",
                        "Responsável", "Próxima entrega"],
        "cond_rows": [{"Item": 1, "Nº Licença": 1, "Data da entrega": "2027-02-01",
                       "Status": "x", "Observações": None, "Responsável": "ALFA",
                       "Próxima entrega": None}],
        "company_to_road": {"ALFA": "RD-010"},
    }
    workbook = environmental_from_snapshot(snap)
    assert workbook.highways == ("RD-010",)
    assert workbook.licenses[0].status == "Aguardando a liberação"
    assert workbook.conditions[0].highway == "RD-010"


# ------------------------------------------------------------------ -m office (nº 14 real)
def _tmp_roots():
    if os.environ.get("PROG_G2_TMP_DIR"):
        yield Path(os.environ["PROG_G2_TMP_DIR"])
    yield REPO_ROOT / "tmp"
    if REPO_ROOT.parent.name == "worktrees":
        yield REPO_ROOT.parents[2] / "tmp"


def _find(relative: str) -> Path:
    for root in _tmp_roots():
        if (root / relative).is_file():
            return root / relative
    pytest.skip(f"fonte local ausente: tmp/{relative}")


@pytest.mark.office
def test_office_builds_report_14_with_word_and_excel():
    if sys.platform != "win32":
        pytest.skip("Excel/Word COM só no Windows")
    pytest.importorskip("win32com.client")
    sources = SourceManifest()
    sources.add(SourceRef("master_list", "00_ Lista mestre.xlsx",
                          _find("historical_sources/lista_mestre_v335.0.xlsx"), version_id="335.0"))
    sources.add(SourceRef("projects", "03 - Acompanhamento de Projetos Executivo.xlsx",
                          _find("agent_N/projetos_range.json"), version_id="438.0"))
    sources.add(SourceRef("projects_panel", "Painel de Controle (extrato)",
                          _find("agent_N/projetos_versions.json"), version_id="v438.0"))
    sources.add(SourceRef("projects_ged", "GED (cópia local)", _find(
        "downloads/fontes_de_trabalho/03 - acompanhamento de projetos executivo.xlsx")))
    sources.add(SourceRef("environmental", "04_Acompanhamento - Licenca Ambiental.xlsx",
                          _find("agent_B/snapshots/v310.0.json"), version_id="310.0"))
    inputs_path = Path(os.environ.get("PROG_G2_INPUTS", "")) if os.environ.get(
        "PROG_G2_INPUTS") else _find("golden_inputs_14.yaml")
    inputs = yaml.safe_load(inputs_path.read_text(encoding="utf-8"))
    report = ReportContext(ReportRef(14, "2026-08"), issue_date=date(2026, 9, 8),
                           signature_date=date.fromisoformat(str(inputs["signature_date"])),
                           mode=BuildMode.RECONSTRUCTION)
    out = REPO_ROOT / "output" / "reconstruction" / "14"
    result = build_report(report, sources, inputs, out, office=True)
    assert result.docx_path.is_file() and result.pdf_path.is_file()
    closing = next(c for c in result.components if c.component_id == "CLOSING_PAGE_COUNT")
    pending = [f"{c.component_id}={c.status}" for c in result.components
               if c.status not in {"OK", "SKIPPED"}]
    print(f"\nDOCX: {result.docx_path}\nPDF: {result.pdf_path}\n{closing.detail}\n"
          f"não-OK: {pending}")
    assert closing.status == "OK", closing.detail

    reference = _find("downloads/relatorios_11_14/"
                      "prog - relatório grupo 2 - relatório mensal n°14 - 08 2026.pdf")
    from prog_g2_report.qa.compare import AllowanceError, compare, load_allowances
    from prog_g2_report.qa.extract import extract_facts

    try:
        allowances = load_allowances()
    except AllowanceError as exc:      # problema do catálogo/allowances, não do builder
        print(f"golden não comparado: allowances inválidas: {exc}")
        return
    report_cmp = compare(extract_facts(reference), extract_facts(result.pdf_path),
                         allowances, report_number=14)
    (out / "golden.json").write_text(json.dumps(report_cmp.to_dict(), ensure_ascii=False,
                                                indent=1), encoding="utf-8")
    (out / "golden.md").write_text(report_cmp.to_markdown(), encoding="utf-8")
    m = report_cmp.metrics
    print(f"golden: {report_cmp.verdict} · estrutural {m['structural_score']:.4f} · "
          f"conteúdo {m['content_accuracy']:.4f} · {m['severity_counts']}")


def test_slot_values_follow_the_trigger_and_accept_a_declared_empty(tmp_path):
    from prog_g2_report.builder.assemble import slot_values
    from prog_g2_report.builder.blocks import EmptySlot, blocks_by_id, fill, load_blocks
    from g2_text_support import make_rc, row

    block = blocks_by_id(load_blocks())["P2.2_ROTINA_REUNIOES"]
    spec = block.raw["slots"]["atas_clause"]
    with_at = make_rc(number=NUMBER, ref=MONTH, rows=[row("2.1", "AT-501.1", NUMBER)],
                      tmp=tmp_path)
    assert slot_values(with_at, block)["atas_clause"] == spec["value_if_true"]
    without_at = make_rc(number=NUMBER, ref=MONTH, rows=[row("2.1", "CT-501.1", NUMBER)],
                         tmp=tmp_path)
    empty = slot_values(without_at, block)["atas_clause"]
    assert isinstance(empty, EmptySlot) and empty == ""
    assert fill("trechos{atas_clause}.", {"atas_clause": empty}, "t") == "trechos."
    with pytest.raises(KeyError):
        fill("trechos{atas_clause}.", {"atas_clause": ""}, "t")


# ------------------------------------------------------------------ posição (QA-D do nº 14)
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CALL = "A relação dos produtos desenvolvidos no período se encontra na tabela apresentada a seguir."


def _keep_next(p) -> bool:
    return p._p.find(f"{W_NS}pPr/{W_NS}keepNext") is not None


def test_lau_items_keep_with_their_panel(built):
    """positioning.keep_with_next.blocks: o item 'RD-xxx:' do P2.4_LAU_LIST fica com o painel."""
    result, _ = built
    doc = Document(str(result.docx_path))
    paragraphs = doc.paragraphs
    items = [i for i, p in enumerate(paragraphs)
             if p.text.startswith(ROADS) and "condicionantes em atraso" in p.text]
    assert items, "itens do P2.4_LAU_LIST não emitidos"
    for i in items:
        assert _keep_next(paragraphs[i]), paragraphs[i].text
        assert not _keep_next(paragraphs[i + 1])           # a imagem não prende o resto


def test_list_titles_keep_with_their_first_item_but_not_with_images():
    """positioning.keep_with_next.list_titles (QA2-D b): título de lista terminado em ':' fica
    com o 1º item (e os vazios no caminho); título seguido de imagem (painel) não."""
    from prog_g2_report.builder.assemble import keep_list_titles_with_first_item

    doc = Document()
    title = doc.add_paragraph("Disciplinas do Viário Secundário:")
    empty = doc.add_paragraph("")
    doc.add_paragraph("Aceitação: encontram-se aceitos em 1º nível ...")
    panel_title = doc.add_paragraph("Referente ao acompanhamento de projeto executivo da Rodovia X:")
    image = doc.add_paragraph()
    image.add_run().add_picture(io.BytesIO(_png_bytes()))
    plain = doc.add_paragraph("Texto que não termina em dois-pontos.")
    last = doc.add_paragraph("Título sem item depois:")
    count = keep_list_titles_with_first_item(list(doc.element.body), ":")
    assert count == 1
    assert _keep_next(title) and _keep_next(empty)
    assert not _keep_next(panel_title) and not _keep_next(image)
    assert not _keep_next(plain) and not _keep_next(last)


def _png_bytes() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_model_keeps_lau_intro_and_p22_list_titles_with_next():
    from prog_g2_report.builder.assemble import keep_with_next_list_titles, keep_with_next_rules
    from prog_g2_report.model import load_model

    model = load_model()
    blocks, before_control = keep_with_next_rules(model)
    assert {"P2.4_LAU_HEAD", "P2.4_LAU_LEAD", "P2.4_LAU_LIST"} <= blocks and before_control
    title_blocks, suffix = keep_with_next_list_titles(model)
    assert suffix == ":" and "P2.2_HIGHWAY_BLOCK" in title_blocks
    with pytest.raises(ValueError, match="ends_with"):
        keep_with_next_list_titles({"positioning": {"keep_with_next": {
            "list_titles": {"blocks": ["X"]}}}})


def test_built_p22_list_titles_keep_with_next(built):
    result, _ = built
    paragraphs = Document(str(result.docx_path)).paragraphs
    titles = [p for p in paragraphs
              if p.text.startswith("Disciplinas d") and p.text.rstrip().endswith(":")]
    assert titles, "títulos de lista do 2.2 não emitidos"
    assert all(_keep_next(p) for p in titles)
    lau = [p for p in paragraphs if p.text.startswith("Referente às Condicionantes")]
    assert lau and all(_keep_next(p) for p in lau)


def test_built_document_writes_the_crase_of_referente_as(built):
    """DEC-007 / anomalia CRASE_REFERENTE_AS (QA4-H): texto gerado do 2.1.2 e do 2.4.2 com a
    crase; a forma sem crase não sai em parágrafo nenhum."""
    import re

    result, _ = built
    texts = [p.text for p in Document(str(result.docx_path)).paragraphs]
    assert any(t.startswith("Referente às atividades periódicas") for t in texts)
    assert any(t.startswith("Ainda referente às Condicionantes Ambientais") for t in texts)
    assert not [t for t in texts if re.search(r"\breferentes?\s+as\b", t, re.IGNORECASE)]


def test_call_sentence_without_measurement_has_no_keep_next(built):
    result, _ = built
    calls = [p for p in Document(str(result.docx_path)).paragraphs if p.text == CALL]
    assert calls and not any(_keep_next(p) for p in calls)


def test_first_slice_is_sized_from_the_first_pass_pdf(synthetic, tmp_path):
    """DEC-010 §3: a 1ª passada mede a frase de chamada no PDF; a 2ª dimensiona o 1º recorte
    para o espaço livre e liga keep-with-next na frase."""
    import pymupdf

    excel = FakeExcel()
    exported = []

    def exporter(docx_path, pdf_path):
        exported.append(Path(docx_path).name)
        pdf = pymupdf.open()
        cm = 72 / 2.54
        for y in (10.0, 25.5, 5.0):            # 2.1: 17,5 cm livres; 2.2: 2,4 cm; 2.4: 22,9 cm
            page = pdf.new_page(width=21 * cm, height=29.7 * cm)
            page.insert_text((2 * cm, y * cm), CALL, fontsize=10)
        pdf.save(str(pdf_path))
        pdf.close()
        return 3

    result = build_report(synthetic["report"], synthetic["sources"], synthetic["inputs"],
                          tmp_path / "out", office=True, assets_dir=synthetic["assets_dir"],
                          assets_manifest=synthetic["manifest"], renderer_factory=lambda: excel,
                          pdf_exporter=exporter)
    assert _status(result, "CLOSING_PAGE_COUNT") == "OK"
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    measured = manifest["passes"][0]["first_slice"]
    assert set(measured) == {"P2.1_CONTROLE_PRODUTOS", "P2.2_CONTROLE_PRODUTOS",
                             "P2.4_CONTROLE_PRODUTOS"}
    assert measured["P2.2_CONTROLE_PRODUTOS"]["free_cm"] < 3.0
    facts = {c.component_id: c.facts for c in result.components}
    assert facts["P2.1_CONTROLE_PRODUTOS"]["first_slice"]["mode"] == "same_page"
    assert facts["P2.2_CONTROLE_PRODUTOS"]["first_slice"]["mode"] == "next_page"
    assert "first_slice" not in facts["ANEXOS_CONTROLE_CONSOLIDADO"]
    calls = [p for p in Document(str(result.docx_path)).paragraphs if p.text == CALL]
    assert len(calls) == 3 and all(_keep_next(p) for p in calls)
    assert len(exported) == 2                      # medição + confirmação da contagem


class _DisconnectedError(Exception):
    """Forma do pywintypes.com_error com CO_E_OBJNOTCONNECTED."""

    def __init__(self):
        super().__init__(-2147220995, "Objeto não conectado ao servidor", None, None)


class DisconnectingExcel(FakeExcel):
    """Excel falso que perde a conexão quando o Word exporta o PDF (o bug da 2ª passada)."""

    def __init__(self):
        super().__init__()
        self.dead = False

    def render_slices(self, *args, **kw):
        if self.dead:
            raise _DisconnectedError()
        return super().render_slices(*args, **kw)


def test_second_pass_survives_excel_disconnected_by_word(synthetic, tmp_path):
    """Com `first_slice_fill`, os recortes da 2ª passada mudam e saem do cache; se a conexão
    com o Excel caiu durante a exportação do Word, o montador recria a instância (e fecha a
    morta) em vez de marcar o Controle de Produtos FAILED."""
    import copy

    import pymupdf

    from prog_g2_report.model import load_model

    # 1 linha basta para o 1º recorte ficar na página da frase: o 2.4 sintético (3 linhas) passa
    # de [0:3] na 1ª passada para [0:1] + [1:3] na 2ª — recortes novos, fora do cache.
    model = copy.deepcopy(load_model())
    control = next(c for c in model["components"] if c.get("component_id") == "CONTROL_OF_PRODUCTS")
    control["render_params"]["first_slice_min_rows"] = 1
    made: list[DisconnectingExcel] = []

    def factory():
        made.append(DisconnectingExcel())
        return made[-1]

    def exporter(docx_path, pdf_path):
        for excel in made:
            excel.dead = True                      # o Word derrubou o apartamento COM
        pdf = pymupdf.open()
        cm = 72 / 2.54
        for y in (10.0, 25.5, 24.6):           # 2.4: ~3,3 cm livres = 1 linha
            page = pdf.new_page(width=21 * cm, height=29.7 * cm)
            page.insert_text((2 * cm, y * cm), CALL, fontsize=10)
        pdf.save(str(pdf_path))
        pdf.close()
        return 3

    result = build_report(synthetic["report"], synthetic["sources"], synthetic["inputs"],
                          tmp_path / "out", office=True, assets_dir=synthetic["assets_dir"],
                          assets_manifest=synthetic["manifest"], renderer_factory=factory,
                          pdf_exporter=exporter, model=model)
    p24 = next(c for c in result.components if c.component_id == "P2.4_CONTROLE_PRODUTOS")
    assert p24.facts["first_slice"]["mode"] == "same_page" and p24.facts["slices"] == [1, 2]
    for block in ("P2.1_CONTROLE_PRODUTOS", "P2.2_CONTROLE_PRODUTOS", "P2.4_CONTROLE_PRODUTOS",
                  "ANEXOS_CONTROLE_CONSOLIDADO"):
        assert _status(result, block) == "OK", block
    assert len(made) == 2                          # 1ª passada + recriada na 2ª
    assert all(excel.closed for excel in made)     # a morta e a do fim, ambas fechadas
    assert made[1].calls >= 1


# ------------------------------------------------------------------ snapshot do 2.2 (DEC-012)
def _projects_extract(path: Path) -> Path:
    """Extrato multiversão SINTÉTICO: na v2.0 o Projeto Geométrico da 1ª rodovia foi aprovado."""
    def version(geometric):
        rows = [syn.approved("1.1", ROADS[0], syn.EST, "Estudos de Tráfego"), geometric]
        return {"Projetos": syn.sheet(*rows), "Painel de Controle": syn.panel(*ROADS),
                "_last_modified": "2027-01-0%sT10:00:00Z" % (1 if geometric[18] is None else 2)}

    data = {"v1.0": version(syn.in_analysis("2.1", ROADS[0], syn.PRI, "Projeto Geométrico")),
            "v2.0": version(syn.approved("2.1", ROADS[0], syn.PRI, "Projeto Geométrico"))}
    path.write_text(json.dumps(data, default=str), encoding="utf-8")
    return path


def _evaluation(workbook) -> str:
    return next(r.evaluation_raw for r in workbook.projects if r.discipline == "Projeto Geométrico")


def test_text_and_dashboards_read_the_same_snapshot(tmp_path):
    from prog_g2_report.builder.assemble import load_p22_projects

    extract = _projects_extract(tmp_path / "projetos_versions.json")
    sources = SourceManifest()
    sources.add(SourceRef("projects", "Projetos", extract, version_id="v2.0"))
    text, dashboard, key, deviations = load_p22_projects(sources)
    assert key == "projects" and deviations == []
    assert _evaluation(text) == _evaluation(dashboard) == "Aprovado"


def test_text_override_is_a_recorded_deviation_and_dashboards_keep_the_snapshot(tmp_path):
    from prog_g2_report.builder.assemble import load_p22_projects

    extract = _projects_extract(tmp_path / "projetos_versions.json")
    sources = SourceManifest()
    sources.add(SourceRef("projects", "Projetos", extract, version_id="v2.0"))
    sources.add(SourceRef("projects_text", "Projetos (texto)", extract, version_id="v1.0"))
    text, dashboard, key, deviations = load_p22_projects(sources)
    assert key == "projects_text"
    assert _evaluation(text) == "" and _evaluation(dashboard) == "Aprovado"
    assert deviations[0]["source"] == "projects_text"
    assert deviations[0]["version_id"] == "v1.0" and deviations[0]["snapshot_version_id"] == "v2.0"


def test_dashboard_provider_reads_the_snapshot_not_the_text_override(tmp_path, monkeypatch):
    from prog_g2_report.builder import assemble
    from prog_g2_report.render import p22_text
    from prog_g2_report.render.visuals import p22_road_dashboard
    from g2_text_support import make_rc

    sources = SourceManifest()
    extract = _projects_extract(tmp_path / "projetos_versions.json")
    sources.add(SourceRef("projects", "Projetos", extract, version_id="v2.0"))
    sources.add(SourceRef("projects_text", "Projetos (texto)", extract, version_id="v1.0"))
    text, dashboard, _key, _dev = assemble.load_p22_projects(sources)
    seen = []
    monkeypatch.setattr(p22_road_dashboard, "render_road_dashboard",
                        lambda data, rules: seen.append(data) or _png((1, 1, 1)))
    rc = make_rc(tmp=tmp_path)
    rc.data.update({"projects": text, "projects_dashboard": dashboard,
                    "p22_reference_date": REF, "p22_rules": p22_text.coerce_rules(None)})
    assert assemble._p22_dashboard(rc, f"{p22_text.DASHBOARD_REF}:{ROADS[0]}") is not None
    levels = {r.discipline: r.level2 for r in seen[0].rows}
    assert levels["Projeto Geométrico"] == "Aprovado"


# ------------------------------------------------------------------ proveniência (manifest.json)
def test_manifest_provenance_from_catalog_and_extract(tmp_path):
    from prog_g2_report.builder.context import ComponentResult
    from prog_g2_report.builder.provenance import component_source_versions, source_provenance

    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "work_sources.jsonl").write_text(
        json.dumps({"name": "planilha.xlsx", "drive_id": "b!SINT", "item_id": "ITEM1"}) + "\n"
        + json.dumps({"name": "lista.xlsx", "drive_id": "b!SINT", "item_id": "ITEM2"}) + "\n",
        encoding="utf-8")
    (catalog / "master_list_versions.jsonl").write_text(
        json.dumps({"version_id": "5.0", "last_modified": "2027-01-05T09:00:00Z"}) + "\n",
        encoding="utf-8")
    snap_dir = tmp_path / "agent_X" / "snapshots"
    snap_dir.mkdir(parents=True)
    env_snapshot = snap_dir / "v9.0.json"
    env_snapshot.write_text("{}", encoding="utf-8")
    (snap_dir.parent / "versions.json").write_text(
        json.dumps([{"version_id": "9.0", "last_modified": "2027-01-09T09:00:00Z"}]),
        encoding="utf-8")
    master = tmp_path / "lista_mestre_v5.0.xlsx"
    master.write_bytes(b"sintetico")
    extract = _projects_extract(tmp_path / "projetos_versions.json")
    model = {"sources": {"master_list": {"name": "lista.xlsx"},
                         "projects": {"name": "planilha.xlsx"},
                         "environmental": {"name": "amb.xlsx"}},
             "components": [
                 {"component_id": "CONTROL_OF_PRODUCTS", "source": "master_list",
                  "blocks": ["P2.1_CONTROLE_PRODUTOS"]},
                 {"component_id": "P2.2_DISCIPLINE_STATUS", "source": "projects",
                  "blocks": ["P2.2_HIGHWAY_BLOCK"]},
                 {"component_id": "P2.2_ROAD_DASHBOARDS", "source": "projects"},
                 {"component_id": "P2.4_LICENSE_DASHBOARDS", "source": "environmental"}]}
    sources = SourceManifest()
    sources.add(SourceRef("master_list", "Lista", master, version_id="5.0"))
    sources.add(SourceRef("projects", "Projetos", extract, version_id="v2.0"))
    sources.add(SourceRef("projects_text", "Projetos (texto)", extract, version_id="v1.0"))
    sources.add(SourceRef("environmental", "Ambiental", env_snapshot, version_id="9.0"))
    prov = source_provenance(sources, model, catalog_dir=catalog)

    assert prov["master_list"]["drive_id"] == "b!SINT" and prov["master_list"]["item_id"] == "ITEM2"
    assert prov["master_list"]["last_modified"] == "2027-01-05T09:00:00Z"
    assert prov["master_list"]["snapshot_origin"] == "lista_mestre_v5.0.xlsx"
    assert prov["master_list"]["sha1"] == hashlib.sha1(b"sintetico").hexdigest()
    assert prov["projects"]["item_id"] == prov["projects_text"]["item_id"] == "ITEM1"
    assert prov["projects"]["snapshot_origin"] == "projetos_versions.json#v2.0"
    assert prov["projects"]["last_modified"] == "2027-01-02T10:00:00Z"
    assert prov["projects_text"]["last_modified"] == "2027-01-01T10:00:00Z"
    assert prov["environmental"]["last_modified"] == "2027-01-09T09:00:00Z"
    assert prov["environmental"]["item_id"] is None                   # fora do catálogo

    results = [ComponentResult("P2.1_CONTROLE_PRODUTOS"), ComponentResult("P2.2_HIGHWAY_BLOCK:RD-103"),
               ComponentResult("IMAGE:P2.2_ROAD_DASHBOARD:RD-103"),
               ComponentResult("IMAGE:P2.4_CONDITIONS_PANEL:RD-101"), ComponentResult("COVER")]
    used = component_source_versions(results, model, prov, text_projects_key="projects_text")
    assert used["P2.1_CONTROLE_PRODUTOS"] == [{"key": "master_list", "version_id": "5.0",
                                               "snapshot_origin": "lista_mestre_v5.0.xlsx"}]
    assert [u["key"] for u in used["P2.2_HIGHWAY_BLOCK:RD-103"]] == ["projects_text"]
    assert [u["key"] for u in used["IMAGE:P2.2_ROAD_DASHBOARD:RD-103"]] == ["projects"]
    assert [u["key"] for u in used["IMAGE:P2.4_CONDITIONS_PANEL:RD-101"]] == ["environmental"]
    assert used["COVER"] == []


def test_built_manifest_declares_source_version_per_component(built):
    _result, out = built
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    by_id = {c["component_id"]: c for c in manifest["components"]}
    p21 = next(c for k, c in by_id.items() if k.startswith("P2.1_CONTROLE"))
    assert "source:master_list@1.0" in p21["source_version"]
    assert manifest["deviations"] == []
    for source in manifest["sources"]:
        assert {"drive_id", "item_id", "version_id", "last_modified", "snapshot_origin",
                "sha1", "local_mtime"} <= set(source)
    # nenhum componente sem linhagem: toda ficha é fonte@versão, input@sha1, report, asset,
    # build ou model (justificativa explícita, nunca null)
    prefixes = ("source:", "inputs:", "default:inputs.", "report:", "asset:", "build:", "model")
    for component in manifest["components"]:
        tokens = component["source_version"]
        assert tokens and all(t.startswith(prefixes) for t in tokens), component
        assert "unmapped" not in tokens and not any(t.endswith("@absent") for t in tokens)
    assert {"model", "report:issue_date", "report:report_number",
            "asset:cover_photo_background"} <= set(by_id["COVER"]["source_version"])
    assert "model:discontinued" in by_id["P2.4_TCE_BLOCK"]["source_version"]
    assert "source:master_list@1.0" in by_id["P2.3_TABLE_CALL"]["source_version"]
    assert by_id["CLOSING_PAGE_COUNT"]["source_version"] == ["model", "build:pdf_page_count"]
    assert by_id["ENC_DATE"]["source_version"] == ["model", "report:signature_date"]
    assert "source:projects@7.0" in next(
        c for k, c in by_id.items() if k.startswith("IMAGE:P2.2_ROAD"))["source_version"]
    assert manifest["sources"][1]["sheets"] == {
        s: {"source": "projects", "version_id": "7.0"}
        for s in ("GED", "Projetos", "Painel de Controle")}


def test_built_manifest_records_the_inputs_file_without_its_content(built, synthetic):
    _result, out = built
    raw = (out / "manifest.json").read_text(encoding="utf-8")
    manifest = json.loads(raw)
    path = synthetic["inputs_path"]
    sha1 = hashlib.sha1(path.read_bytes()).hexdigest()
    assert manifest["inputs"]["path"] == str(path) and manifest["inputs"]["sha1"] == sha1
    assert "signatory_name" in manifest["inputs"]["keys"]
    by_id = {c["component_id"]: c for c in manifest["components"]}
    assert f"inputs:signatory_name@{sha1}" in by_id["ENC_SIGNATURE_TABLE"]["source_version"]
    assert f"inputs:ai_review@{sha1}" in by_id["P2.4_NC"]["source_version"]   # review_key
    assert f"inputs:p22_external_status@{sha1}" in by_id["P2.2_DESAPROPRIACAO"]["source_version"]
    assert "default:inputs.p24_bm_in_progress" in by_id["P2.4_BM_EM_ELABORACAO"]["source_version"]
    inputs = synthetic["inputs"]
    meetings = inputs.get("meetings_agenda")
    assert json.dumps(meetings, ensure_ascii=False, default=str)[1:-1] not in json.dumps(
        manifest["inputs"], ensure_ascii=False)                  # sem conteúdo no registro


def test_built_manifest_points_to_outputs_relative_to_the_out_dir(built):
    result, out = built
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["docx"] == result.docx_path.name
    assert (out / manifest["docx"]).is_file()
    assert manifest["docx_sha1"] == hashlib.sha1(result.docx_path.read_bytes()).hexdigest()
    assert manifest["pdf"] is None and manifest["pdf_sha1"] is None          # office=False

