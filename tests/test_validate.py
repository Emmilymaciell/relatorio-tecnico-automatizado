"""Validações do modelo ao fim do build (`builder.validate`), pauta de revisão dos slots e DOCX
final com campos atualizados. Offline: fontes sintéticas de `test_assemble`, Excel/Word falsos.
"""

from __future__ import annotations

import dataclasses
import io
import json
import shutil
import zipfile
from datetime import date
from pathlib import Path

import pytest
from docx import Document

from prog_g2_report.builder import validate as v
from prog_g2_report.builder.assemble import build_report, control_block_ids
from prog_g2_report.builder.blocks import blocks_by_id, load_blocks
from prog_g2_report.builder.context import ReportContext
from prog_g2_report.builder.word_pdf import strip_update_fields
from prog_g2_report.model import load_model
from prog_g2_report.render.docx_emf import add_emf_picture
from prog_g2_report.report_id import ReportRef
from emf_synth import make_emf
from g2_text_support import row
from test_assemble import FakeExcel, synthetic  # noqa: F401  (fixture de módulo)

REPORT = ReportContext(ReportRef(21, "2027-06"), issue_date=date(2027, 7, 8),
                       signature_date=date(2027, 7, 9))


@pytest.fixture(scope="module")
def model():
    return load_model()


@pytest.fixture(scope="module")
def blocks():
    return blocks_by_id(load_blocks())


def _doc(cover: str, presentation: str, closing: str) -> v.DocText:
    """DocText como o de `read_document`: capa antes do sumário, títulos com estilo."""
    return v.DocText(
        paragraphs=[("", cover), ("Ttulo1", "Apresentação"), ("Normal", presentation),
                    ("Ttulo1", "gestão de engenharia e socioambiental"), ("Normal", "x"),
                    ("Ttulo", "ENCERRAMENTO"), ("Normal", closing), ("Ttulo", "ANEXOS")],
        cover=[cover])


GOOD = ("Relatório Mensal N° 21",
        "O Consórcio apresenta o Relatório Mensal N° 21, referente ao período de Junho/2027.",
        "O Relatório Mensal N° 21, referente às atividades durante o mês de Junho/2027, …")


def test_number_and_month_consistent(model, blocks):
    warnings: list[str] = []
    result = v.validate_number_month(_doc(*GOOD), REPORT, model, blocks, warnings)
    assert result.status == "OK" and result.facts["outcome"] == "pass"
    assert result.facts["found"]["Encerramento"] == {"report_number": 21,
                                                     "reference_month": "2027-06"}


@pytest.mark.parametrize("parts, needle", [
    ((GOOD[0].replace("21", "20"), GOOD[1], GOOD[2]), "capa: N° 20 ≠ 21"),
    ((GOOD[0], GOOD[1].replace("Junho", "Maio"), GOOD[2]), "Apresentação: mês 2027-05"),
    ((GOOD[0], GOOD[1], GOOD[2].replace("N° 21", "N° 12")), "Encerramento: N° 12 ≠ 21"),
    ((GOOD[0], GOOD[1], "texto sem número"), "Encerramento: 'Relatório Mensal N°' não"),
])
def test_number_or_month_divergence_is_an_error(model, blocks, parts, needle):
    result = v.validate_number_month(_doc(*parts), REPORT, model, blocks, [])
    assert result.status == "FAILED" and needle in result.detail
    assert v.severity(model, v.V_NUMBER_MONTH) == v.ERROR


def test_pending_closing_text_is_pending_not_failed(model, blocks):
    doc = _doc(GOOD[0], GOOD[1], "[PENDENTE: ENC_P1]")
    assert v.validate_number_month(doc, REPORT, model, blocks, []).status == "PENDING"


def test_cited_codes_must_be_in_body_rows_except_declared_external_bm(model):
    rows = [row("2.4", "RO-510.1", 21), row("2.2", "PA-502.1", 21)]
    doc = v.DocText(paragraphs=[("Normal", "RD-101: RO-510.1 a RO-510.1; PA-502.1."),
                                ("Normal", "BM-999.1 - Referente a Maio/2027;")])
    ok = v.validate_docs_in_master_list(doc, rows, ["BM-999.1"], model, [])
    assert ok.status == "OK" and ok.facts["external_inputs"] == ["BM-999.1"]
    assert ok.facts["cited"] == 3                         # rodovias (RD-101) não são código
    bad = v.validate_docs_in_master_list(doc, rows, [], model, [])
    assert bad.status == "FAILED" and "BM-999.1" in bad.detail
    assert v.cited_codes(["LA.RC-001.1 e Carta-002.1; NT-123"]) == ["LA.RC-001.1",
                                                                    "Carta-002.1"]


def test_delivery_after_issue_is_a_warning(model):
    late = dataclasses.replace(row("2.4", "PA-503.1", 21), delivery_date=date(2027, 7, 9))
    warnings: list[str] = []
    result = v.validate_delivery_dates([late], REPORT.issue_date, model, warnings)
    assert result.status == "OK" and result.facts["outcome"] == v.WARNING
    assert warnings == [result.detail.removeprefix("aviso: ").join(
        ["V_NO_DELIVERY_AFTER_ISSUE: ", ""])]
    assert "PA-503.1 2027-07-09" in warnings[0]


def _docx_with_emfs(path: Path, emfs: list[tuple[str, bytes]]) -> Path:
    doc = Document()
    for name, data in emfs:
        add_emf_picture(doc.add_paragraph(), data, 17.5, name=name)
    doc.save(str(path))
    return path


def test_emf_frame_against_the_history(model, tmp_path):
    blocks = control_block_ids(model)
    assert "ANEXOS_CONTROLE_CONSOLIDADO" in blocks and "P2.1_CONTROLE_PRODUTOS" in blocks
    good = _docx_with_emfs(tmp_path / "good.docx", [
        ("p2.1_controle_produtos_01.emf", make_emf()),
        ("anexos_controle_consolidado_01.emf", make_emf()),
        ("p22_predecessor_disciplines_diagram.emf", make_emf(frame_01mm=(0, 0, 14423, 100)))])
    result = v.validate_emf_frame(good, blocks, model, [])
    assert result.status == "OK" and result.facts["emfs"] == 2       # o diagrama não conta
    warnings: list[str] = []
    off = _docx_with_emfs(tmp_path / "off.docx", [
        ("p2.4_controle_produtos_01.emf", make_emf(frame_01mm=(0, 0, 17673, 5048),
                                                   device_px=(1536, 864)))])
    result = v.validate_emf_frame(off, blocks, model, warnings)
    assert result.status == "OK" and result.facts["outcome"] == v.WARNING   # não bloqueia
    assert "176.73 mm" in warnings[0] and "1536×864" in warnings[0]
    none = _docx_with_emfs(tmp_path / "none.docx", [])
    assert v.validate_emf_frame(none, blocks, model, []).status == "SKIPPED"


# ------------------------------------------------------------------ build completo (falsos)
def _exporter_with_final(calls: list[dict]):
    import pymupdf

    def exporter(docx_path, pdf_path, final_docx_path=None):
        calls.append({"docx": Path(docx_path), "final": final_docx_path})
        pdf = pymupdf.open()
        for _ in range(9):
            pdf.new_page()
        pdf.save(str(pdf_path))
        pdf.close()
        if final_docx_path is not None:          # o Word salva a cópia com campos atualizados
            shutil.copyfile(docx_path, final_docx_path)
        return 9

    return exporter


def _settings_xml(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        return z.read("word/settings.xml").decode("utf-8")


def test_office_build_runs_validations_and_saves_the_final_docx(synthetic_build):
    result, out, calls = synthetic_build
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    outcomes = {item["id"]: item["outcome"] for item in manifest["validations"]}
    # capa sintética sem o fundo do modelo = marcador pendente; Apresentação e Encerramento
    # conferem número e mês
    assert outcomes["V_NUMBER_MONTH_CONSISTENT"] == "pending"
    found = next(c for c in manifest["components"]
                 if c["component_id"] == "V_NUMBER_MONTH_CONSISTENT")["facts"]["found"]
    assert found["Apresentação"] == found["Encerramento"] == {
        "report_number": 3, "reference_month": "2026-12"}
    assert found["capa"]["pending"] is True
    assert outcomes["V_ALL_DOCS_IN_MASTER_LIST"] == "pass"
    assert outcomes["V_NO_DELIVERY_AFTER_ISSUE"] == "pass"
    assert outcomes["V_ANNEX_COUNT"] == "pass" and outcomes["V_PAGE_COUNT"] == "pass"
    # EMF do Excel falso: frame de 500 pt (176,39 mm) -> aviso, não bloqueia
    assert outcomes["V_EMF_FRAME"] == "warning"
    assert any(w.startswith("V_EMF_FRAME:") for w in result.warnings)
    assert not any(c.status == "FAILED" for c in result.components if c.component_id
                   .startswith("V_"))
    # DOCX final: arquivo novo, sem updateFields; o gerado mantém o seu
    assert all(c["final"] is not None and Path(c["final"]) != c["docx"] for c in calls)
    final = out / manifest["docx_final"]
    assert final.name.endswith("_final.docx") and final.is_file()
    assert "updateFields" not in _settings_xml(final)
    assert "updateFields" in _settings_xml(result.docx_path)
    assert manifest["docx_final_sha1"] and len(manifest["docx_final_sha1"]) == 40


def test_review_brief_written_for_pending_slot_and_removed_once_approved(
        synthetic, tmp_path):  # noqa: F811  (fixture de test_assemble)
    inputs = {k: val for k, val in synthetic["inputs"].items() if k != "ai_review"}
    out = tmp_path / "out"
    kwargs = {"office": False, "assets_dir": synthetic["assets_dir"],
              "assets_manifest": synthetic["manifest"]}
    result = build_report(synthetic["report"], synthetic["sources"], inputs, out, **kwargs)
    slot = "P2.1_SUMMARY_S4_TEMAS"
    component = next(c for c in result.components if c.component_id == slot)
    assert component.status == "PENDING_HUMAN"
    brief = out / f"review_brief_{slot}.md"
    assert brief.is_file() and component.facts["review_brief"] == brief.name
    content = brief.read_text(encoding="utf-8")
    assert f"# Revisão do slot {slot}" in content and "| PA-502.1 |" in content
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["review_briefs"] == {slot: brief.name}
    entry = next(c for c in manifest["components"] if c["component_id"] == slot)
    assert entry["review_brief"] == brief.name
    approved = {**inputs, "ai_review": {slot: {"text": "tema aprovado",
                                               "documents": ["PA-502.1"]}}}
    result = build_report(synthetic["report"], synthetic["sources"], approved, out, **kwargs)
    assert next(c for c in result.components if c.component_id == slot).status == "OK"
    assert not brief.exists()                                  # pauta antiga removida
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["review_briefs"] == {}


def test_strip_update_fields_rewrites_only_settings(tmp_path):
    doc = Document()
    doc.add_paragraph("texto")
    buffer = io.BytesIO()
    doc.save(buffer)
    path = tmp_path / "x_final.docx"
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as src, \
            zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "word/settings.xml":
                data = data.replace(b"</w:settings>",
                                    b'<w:updateFields w:val="true"/></w:settings>')
            dst.writestr(info, data)
    assert strip_update_fields(path) is True
    assert "updateFields" not in _settings_xml(path)
    assert Document(str(path)).paragraphs[0].text == "texto"
    assert strip_update_fields(path) is False


@pytest.fixture(scope="module")
def synthetic_build(synthetic, tmp_path_factory):  # noqa: F811  (fixture de test_assemble)
    calls: list[dict] = []
    excel = FakeExcel()
    out = tmp_path_factory.mktemp("validate_out")
    result = build_report(synthetic["report"], synthetic["sources"], synthetic["inputs"], out,
                          office=True, assets_dir=synthetic["assets_dir"],
                          assets_manifest=synthetic["manifest"], renderer_factory=lambda: excel,
                          pdf_exporter=_exporter_with_final(calls),
                          inputs_path=synthetic["inputs_path"])
    return result, out, calls
