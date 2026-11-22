"""Componentes textuais: Apresentação, capítulo 2, cabeçalhos dos produtos, Encerramento, Anexos."""

from datetime import date

import pytest
from docx.oxml.ns import qn

from prog_g2_report.builder.blocks import PENDING_STATUS, blocks_by_id, load_blocks
from prog_g2_report.builder.text_components import render_text_components, text_component_plan
from prog_g2_report.model import load_model
from g2_text_support import body_texts, make_rc, row, usual_rows

CONTRACT = load_model()["editorial_defaults"]["contract_ref"]["value"]


@pytest.fixture(scope="module")
def blocks():
    return blocks_by_id(load_blocks())


def _paragraph(rc, prefix):
    found = [p for p in rc.document.paragraphs if p.text.startswith(prefix)]
    assert len(found) == 1, prefix
    return found[0]


def _bold(paragraph):
    return [r.text for r in paragraph.runs if r.bold]


@pytest.mark.parametrize(("number", "ref", "label"),
                         [(14, "2026-08", "Agosto/2026"), (15, "2026-09", "Setembro/2026")])
def test_presentation_and_closing_take_number_and_month_from_the_context(
    tmp_path, number, ref, label
):
    rc = make_rc(number=number, ref=ref, tmp=tmp_path)
    render_text_components(rc)
    apres = _paragraph(rc, "O Consórcio Estruturador")
    assert apres.text == (
        f"O Consórcio Estruturador apresenta ao Parceiro o Relatório Mensal N° {number}, "
        f"referente ao período de {label}, em conformidade ao {CONTRACT}.")
    assert _bold(apres) == [f"Relatório Mensal N° {number}", label]
    closing = _paragraph(rc, "O Relatório Mensal")
    assert closing.text.startswith(f"O Relatório Mensal N° {number}, referente")
    assert f"durante o mês de {label}," in closing.text
    body = "\n".join(body_texts(rc))
    # anomalia APRESENTACAO_NUMERO_RELATORIO do nº 14 ('N° 13') nunca é aprendida
    assert f"N° {number - 1}" not in body
    assert "{" not in rc.document.element.body.xml


@pytest.mark.parametrize(("month", "number", "pages", "annexes"), [
    ("Maio/2026", 11, 38, 150), ("Julho/2026", 13, 43, 165), ("Agosto/2026", 14, 43, 149)])
def test_closing_paragraph_reproduces_the_observed_text(tmp_path, blocks, month, number, pages,
                                                         annexes):
    ref = {"Maio/2026": "2026-05", "Julho/2026": "2026-07", "Agosto/2026": "2026-08"}[month]
    rows = [row("2.4", f"RO-{i:03d}.1", number, physical_row=i) for i in range(annexes)]
    rows.append(row("2.4", "BM-999.1", number, status="Em elaboração"))   # fora do índice
    rc = make_rc(number=number, ref=ref, rows=rows, page_count=pages, tmp=tmp_path)
    render_text_components(rc, ["ENC_P1"])
    observed = blocks["ENC_P1"].raw["observed"][month]
    # única diferença aceita: forma única do contrato (DEC-007)
    assert rc.document.paragraphs[0].text == observed.replace("Contrato N°00/0000-PARC", CONTRACT)


def test_closing_bold_is_normalized_to_the_numbers(tmp_path):
    rows = [row("2.4", f"RO-{i:03d}.1", physical_row=i) for i in range(149)]
    rc = make_rc(rows=rows, page_count=43, tmp=tmp_path)
    render_text_components(rc, ["ENC_P1"])
    assert _bold(rc.document.paragraphs[0]) == [
        "Relatório Mensal N° 14", "Agosto/2026", "43 (quarenta e três)",
        "149 (cento e quarenta e nove)"]


def test_closing_without_page_count_is_failed_with_marker(tmp_path):
    rc = make_rc(page_count=None, tmp=tmp_path)
    (result,) = render_text_components(rc, ["ENC_P1"])
    assert result.status == "FAILED" and "page_count" in result.detail
    assert body_texts(rc) == ["[PENDENTE: ENC_P1]"]


def test_absence_sentence_only_for_products_without_rows(tmp_path):
    rc = make_rc(rows=usual_rows(), tmp=tmp_path)
    render_text_components(rc)
    body = body_texts(rc)
    for code in ("2.3", "2.5", "2.6"):
        assert ("No período de referência do presente relatório não houve atividades "
                f"relacionadas ao produto {code}.") in body
    for code in ("2.1", "2.2", "2.4"):
        assert not any(t.endswith(f"produto {code}.") for t in body)
    calls = [t for t in body if t.startswith("A relação dos produtos desenvolvidos")]
    assert len(calls) == 3      # occurrences_per_report: 3


def test_absence_and_table_call_switch_with_the_rows(tmp_path):
    # 2.3 com linhas e 2.5 sem: nunca observado; blocos derivados do irmão
    rows = [row("2.1", "AT-501.1"), row("2.2", "PA-501.1"), row("2.3", "OF-001.1"),
            row("2.4", "RO-501.1")]
    rc = make_rc(rows=rows, tmp=tmp_path)
    results = {r.component_id: r for r in render_text_components(rc)}
    body = body_texts(rc)
    assert ("No período de referência do presente relatório não houve atividades "
            "relacionadas ao produto 2.5.") in body
    assert not any(t.endswith("produto 2.3.") for t in body)
    assert results["P2.3_TABLE_CALL"].status == "OK"
    assert results["P2.3_TABLE_CALL"].facts["derived_from"] == "P2.1_TABLE_CALL"
    assert results["P2.3_NO_ACTIVITY"].status == "SKIPPED"
    assert results["P2.1_NO_ACTIVITY"].status == "SKIPPED"
    assert results["P2.1_TABLE_CALL"].status == "OK"


@pytest.mark.parametrize(("number", "ref"), [(14, "2026-08"), (15, "2026-09")])
def test_p21_without_documents_never_says_no_activity(tmp_path, number, ref):
    """NO_ACTIVITY_SENTENCE.never_for['2.1'] (QA2-E): mês sintético sem documento do 2.1 — a
    chamada da tabela some e o slot fica PENDING_HUMAN com o aviso; a frase de ausência do 2.1
    (contraditória com a coordenação e a agenda de reuniões) nunca sai."""
    model = load_model()
    spec = next(c for c in model["components"]
                if c["component_id"] == "NO_ACTIVITY_SENTENCE")["never_for"]["2.1"]
    rows = [row("2.2", "PA-501.1", number), row("2.4", "RO-501.1", number)]
    rc = make_rc(number=number, ref=ref, rows=rows, tmp=tmp_path)
    results = {r.component_id: r for r in render_text_components(rc)}
    body = body_texts(rc)
    assert not any("relacionadas ao produto 2.1" in t for t in body)
    absent = results["P2.1_NO_ACTIVITY"]
    assert absent.status == spec["status"] == PENDING_STATUS
    assert absent.detail == spec["warning"] == absent.facts["warning"]
    assert "[PENDENTE: P2.1_NO_ACTIVITY]" in body
    assert results["P2.1_TABLE_CALL"].status == "SKIPPED"
    # os demais produtos sem linhas continuam com a frase de ausência
    for code in ("2.3", "2.5", "2.6"):
        assert ("No período de referência do presente relatório não houve atividades "
                f"relacionadas ao produto {code}.") in body


def test_product_headers_and_order(tmp_path, blocks):
    rc = make_rc(tmp=tmp_path)
    render_text_components(rc)
    titles = [p for p in rc.document.paragraphs if p.style.style_id == "Ttulo2"]
    assert [p.text for p in titles] == [blocks[f"P2.{i}_TITLE"].raw["text"] for i in range(1, 7)]
    assert all("–" in p.text for p in titles)
    # products[*].page_break_before.value = true: todo produto abre página (DOCX nº 11–14)
    flags = [p._p.pPr.pageBreakBefore is not None for p in titles]
    assert flags == [True] * 6
    h3 = [p.text for p in rc.document.paragraphs if p.style.style_id == "Ttulo3"]
    assert h3 == ["Descrição das atividades atribuídas", "Produtos desenvolvidos no período"] * 6
    assert _paragraph(rc, "gestão de engenharia").style.style_id == "Ttulo1"
    assert _paragraph(rc, "O Produto 2.1,").text.endswith("é assim descrito no Termo de "
                                                           "Referência do Edital N° 000/0000/SUP:")


def test_signature_date_and_table(tmp_path):
    rc = make_rc(signature=date(2026, 9, 9), inputs={"signatory_name": "Fulana de Teste"},
                 tmp=tmp_path)
    render_text_components(rc, ["ENC_DATE", "ENC_SIGNATURE_TABLE"])
    assert body_texts(rc)[0] == "Capital, 09 de Setembro de 2026"
    (table,) = rc.document.tables
    tbl = table._tbl
    assert tbl.tblPr.find(qn("w:jc")).get(qn("w:val")) == "center"
    assert [g.get(qn("w:w")) for g in tbl.tblGrid.findall(qn("w:gridCol"))] == ["4535"]
    top, bottom = table.rows[0].cells[0], table.rows[1].cells[0]
    edge = top._tc.tcPr.find(qn("w:tcBorders")).find(qn("w:bottom"))
    assert (edge.get(qn("w:val")), edge.get(qn("w:sz")), edge.get(qn("w:color"))) == (
        "single", "4", "808080")
    assert bottom._tc.tcPr.find(qn("w:tcBorders")).find(qn("w:top")) is not None
    texts = [p.text for p in bottom.paragraphs]
    assert texts == ["Eng° Fulana de Teste",
                     "Programa – Consórcio Estruturador do Programa",
                     "Produto P2.1 – Relatório Mensal – Grupo 2.", ""]
    name, prog, product = (p.runs[0] for p in bottom.paragraphs[:3])
    assert name.font.size.pt == 9 and not name.bold
    assert prog.font.size.pt == 6 and prog.bold
    assert product.font.size.pt == 6 and not product.bold
    fonts = name._r.rPr.find(qn("w:rFonts"))
    assert fonts.get(qn("w:ascii")) == fonts.get(qn("w:hAnsi")) == "Times New Roman"
    assert all(p.alignment == 1 for p in bottom.paragraphs)   # center


def test_missing_human_inputs_are_pending_not_invented(tmp_path):
    rc = make_rc(signature=None, inputs={}, tmp=tmp_path)
    results = render_text_components(rc, ["ENC_DATE", "ENC_SIGNATURE_TABLE"])
    assert [r.status for r in results] == [PENDING_STATUS, PENDING_STATUS]
    assert body_texts(rc) == ["[PENDENTE: ENC_DATE]", "[PENDENTE: ENC_SIGNATURE_TABLE]"]
    assert rc.document.tables == []


def test_block_ids_filter_keeps_document_order(tmp_path):
    rc = make_rc(tmp=tmp_path)
    results = render_text_components(rc, ["ANEXOS_TITLE", "APRES_TITLE"])
    assert [r.component_id for r in results] == ["APRES_TITLE", "ANEXOS_TITLE"]
    assert body_texts(rc) == ["Apresentação", "ANEXOS"]
    with pytest.raises(KeyError):
        render_text_components(rc, ["P2.4_RM"])


def test_plan_covers_every_product(blocks):
    plan = {b.block_id for b in text_component_plan(list(blocks.values()), load_model())}
    for i in range(1, 7):
        for suffix in ("TITLE", "H3_DESCRICAO", "QUOTE_INTRO", "QUOTE", "H3_PRODUTOS",
                       "TABLE_CALL", "NO_ACTIVITY"):
            assert f"P2.{i}_{suffix}" in plan
    assert {"APRES_TITLE", "CH2_ATIV_LIST", "ENC_SIGNATURE_TABLE", "ANEXOS_TITLE"} <= plan
    assert "ANEXOS_CONTROLE_CONSOLIDADO" not in plan


def test_full_text_run_has_no_placeholder_and_only_the_logo_pending(tmp_path):
    rc = make_rc(tmp=tmp_path)
    results = render_text_components(rc)
    assert "{" not in rc.document.element.body.xml and "}" not in rc.document.element.body.xml
    pending = [r.component_id for r in results if r.status not in {"OK", "SKIPPED"}]
    assert pending == ["APRES_LOGO_GRUPOS"]     # imagem: espera o módulo de assets
    assert "ANEXOS" in body_texts(rc) and "ANEXOS     " not in body_texts(rc)
