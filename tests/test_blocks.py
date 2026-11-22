"""Motor de blocos: citação byte a byte, negrito, tabs/quebras, listas, delegação, placeholders."""

import pytest
import yaml
from docx import Document
from docx.oxml.ns import qn

from prog_g2_report import REPO_ROOT
from prog_g2_report.builder import blocks as engine
from prog_g2_report.builder.blocks import (
    BLOCK_RENDERERS,
    LIST_DEFINITIONS,
    BlockModelError,
    MissingStyleError,
    block_from_raw,
    blocks_by_id,
    build_paragraphs,
    load_blocks,
    parse_direct,
    parse_style,
    register_block_renderer,
    render_block,
)
from prog_g2_report.builder.context import ComponentResult
from prog_g2_report.builder.values import MissingValueError
from g2_text_support import make_rc

PRODUCTS = ("2.1", "2.2", "2.3", "2.4", "2.5", "2.6")


@pytest.fixture(scope="module")
def blocks():
    return blocks_by_id(load_blocks())


def _bold(paragraph):
    return [r.text for r in paragraph.runs if r.bold]


def test_blocks_load_in_document_order(blocks):
    ordered = load_blocks()
    assert len(ordered) == 118
    assert [b.seq for b in ordered] == sorted(b.seq for b in ordered)
    assert ordered[0].block_id == "COVER" and ordered[-1].block_id == "ANEXOS_CONTROLE_CONSOLIDADO"
    assert blocks["P2.3_NO_ACTIVITY"].product == "2.3" and blocks["ENC_P1"].product is None


@pytest.mark.parametrize(("text", "style_id", "key", "ilvl"), [
    ("Normal", "Normal", None, 0),
    ("Ttulo1", "Ttulo1", None, 0),
    ("PargrafodaLista + numId 35 lvl 0 (•)", "PargrafodaLista", "35", 0),
    ("Normal + numId 36 lvl 0 (•)", "Normal", "36", 0),
    ("Normal + numPr ilvl 0 (marcador Symbol U+F0B7, ind 720/360)", "Normal", "bullet", 0),
    ("PargrafodaLista numId 29 lvl 0 (•) + letra digitada", "PargrafodaLista", "29", 0),
])
def test_parse_style(text, style_id, key, ilvl):
    spec = parse_style(text)
    assert (spec.style_id, spec.list_key, spec.ilvl) == (style_id, key, ilvl)


def test_parse_style_reads_direct_alignment():
    assert parse_style("Normal + jc left, spacing auto (colado de HTML)").jc == "left"


def test_parse_direct():
    first = parse_direct("4 tabs iniciais (runs sem itálico) + texto itálico; "
                         "marca de parágrafo itálica")
    assert first.italic and not first.italic_leading_tabs and first.mark_italic
    second = parse_direct("4 tabs + texto, tudo itálico")
    assert second.italic and second.italic_leading_tabs and not second.mark_italic
    third = parse_direct("ind left=2832 twips (5,0 cm), itálico; aspas de fechamento ” no fim")
    assert third.ind_left == 2832 and third.italic


@pytest.mark.parametrize("code", PRODUCTS)
def test_contract_quote_is_byte_identical_to_the_yaml(tmp_path, blocks, code):
    block = blocks[f"P{code}_QUOTE"]
    rc = make_rc(tmp=tmp_path)
    result = render_block(rc, block, {})
    assert result.status == "OK"
    paragraphs = rc.document.paragraphs
    expected = [p["text"] for p in block.raw["paragraphs"]]
    assert [p.text for p in paragraphs] == expected
    assert [p.text.encode("utf-8") for p in paragraphs] == [t.encode("utf-8") for t in expected]
    first, second, third = paragraphs
    # 1º: tabs sem itálico, texto itálico, marca de parágrafo itálica
    assert first.runs[0].text == "\t\t\t\t" and not first.runs[0].italic
    assert first.runs[1].italic and first.runs[1].text.startswith("“3.7.")
    assert first._p.pPr.find(qn("w:rPr")).find(qn("w:i")) is not None
    # 2º: tudo itálico
    assert all(r.italic for r in second.runs)
    # 3º: recuo direto 2832 twips, itálico, aspas de fechamento U+201D
    assert third._p.pPr.find(qn("w:ind")).get(qn("w:left")) == "2832"
    assert all(r.italic for r in third.runs) and third.text.endswith("”")
    assert first.runs[0]._r.findall(qn("w:tab")) and not first.runs[0]._r.findall(qn("w:t"))


def test_source_verbatim_is_never_standardized(tmp_path):
    raw = {"block_id": "X_QUOTE", "class": "SOURCE_VERBATIM", "seq": 1, "paragraphs": [
        {"style": "Normal", "direct": "itálico", "text": "é assim descrita no {texto}  "}]}
    rc = make_rc(tmp=tmp_path)
    render_block(rc, block_from_raw(raw), {})
    assert rc.document.paragraphs[0].text == "é assim descrita no {texto}  "


def test_generated_text_drops_residual_trailing_spaces(tmp_path, blocks):
    # APRES_P1_SELECAO termina em 'grupos: ' no YAML; ANEXOS_TITLE tinha 5 espaços (DEC-007)
    rc = make_rc(tmp=tmp_path)
    render_block(rc, blocks["APRES_P1_SELECAO"], {})
    render_block(rc, blocks["ANEXOS_TITLE"], {})
    first, title = rc.document.paragraphs
    assert first.text == blocks["APRES_P1_SELECAO"].raw["text"].rstrip()
    assert title.text == "ANEXOS" and title.style.style_id == "Ttulo"


def test_quote_intro_uses_the_standardized_text(tmp_path, blocks):
    rc = make_rc(tmp=tmp_path)
    render_block(rc, blocks["P2.3_QUOTE_INTRO"], {})
    text = rc.document.paragraphs[0].text
    assert text == blocks["P2.3_QUOTE_INTRO"].raw["text_standardized"]
    assert "é assim descrito" in text and "referente à elaboração" in text


def test_bold_markup_and_placeholders(tmp_path, blocks):
    rc = make_rc(tmp=tmp_path)
    values = {"report_number": "15", "month_label": "Setembro/2026",
              "contract_ref": "Contrato N° 00/0000-PARC"}
    result = render_block(rc, blocks["APRES_P3_IDENTIFICACAO"], values)
    paragraph = rc.document.paragraphs[0]
    assert _bold(paragraph) == ["Relatório Mensal N° 15", "Setembro/2026"]
    assert result.facts["values"] == values


def test_bold_list_marks_segments_in_order(tmp_path, blocks):
    # Gate B (objeção 1): tipos e rodovias do resumo são slots; o negrito segue a lista `bold`,
    # inclusive segmento com placeholder resolvido.
    rc = make_rc(tmp=tmp_path)
    s3 = {"p22_verb": "foram emitidas", "p22_types": "Notas Técnicas e Pareceres Técnicos",
          "p22_rodovias": "RD-101, RD-102A, RD-103 e RD-104"}
    render_block(rc, blocks["P2.1_SUMMARY_S3_P22"], s3)
    assert _bold(rc.document.paragraphs[0]) == ["Produto P2.2", "Notas Técnicas e Pareceres Técnicos"]
    s5 = {"p24_rodovias": "RD-101, RD-102A, RD-103 e RD-104", "p24_types": "Boletins de Medição",
          "p24_activities_sentence": " Paralelamente, foram desenvolvidas atividades."}
    render_block(rc, blocks["P2.1_SUMMARY_S5_P24"], s5)
    assert _bold(rc.document.paragraphs[1]) == blocks["P2.1_SUMMARY_S5_P24"].raw["bold"]


def test_list_items_with_their_own_bold(tmp_path, blocks):
    rc = make_rc(tmp=tmp_path)
    render_block(rc, blocks["P2.2_NIVEIS_LIST"], {})
    assert [_bold(p) for p in rc.document.paragraphs] == [
        ["Aceitação (1º Nível)"], ["Aprovação (2º Nível)"], ["Certificação"]]
    assert all(p.style.style_id == "PargrafodaLista" for p in rc.document.paragraphs)


def test_bold_segment_missing_from_text_is_a_model_error():
    raw = {"block_id": "X", "class": "FIXED_TEXT", "seq": 1, "style": "Normal",
           "text": "abc", "bold": ["zzz"]}
    with pytest.raises(BlockModelError):
        build_paragraphs(block_from_raw(raw), {})


def test_tabs_and_breaks_become_ooxml(tmp_path):
    raw = {"block_id": "X", "class": "TEMPLATE", "seq": 1, "style": "Normal",
           "template": "a\t{x}\nb"}
    rc = make_rc(tmp=tmp_path)
    render_block(rc, block_from_raw(raw), {"x": "1"})
    p = rc.document.paragraphs[0]._p
    assert p.findall(f".//{qn('w:tab')}") and p.findall(f".//{qn('w:br')}")
    assert rc.document.paragraphs[0].text == "a\t1\nb"


def test_missing_placeholder_is_an_explicit_error_and_nothing_is_emitted(tmp_path, blocks):
    rc = make_rc(tmp=tmp_path)
    with pytest.raises(MissingValueError) as info:
        render_block(rc, blocks["APRES_P3_IDENTIFICACAO"], {"report_number": "14"})
    assert info.value.name in {"month_label", "contract_ref"}
    assert "{" not in rc.document.element.body.xml
    assert rc.document.paragraphs == []


def test_unpaired_bold_markup_is_a_model_error():
    raw = {"block_id": "X", "class": "TEMPLATE", "seq": 1, "template": "a **b"}
    with pytest.raises(BlockModelError):
        build_paragraphs(block_from_raw(raw), {})


def test_list_gets_a_new_num_instance_with_restart(tmp_path, blocks):
    rc = make_rc(tmp=tmp_path)
    render_block(rc, blocks["CH2_ATIV_LIST"], {})
    render_block(rc, blocks["P2.2_GRUPOS_LIST"], {})
    render_block(rc, blocks["P2.2_NIVEIS_LIST"], {})
    num_ids = [p._p.pPr.numPr.numId.val for p in rc.document.paragraphs]
    ch2, groups, levels = set(num_ids[:11]), set(num_ids[11:15]), set(num_ids[15:18])
    assert len(ch2) == len(groups) == len(levels) == 1   # CH2: UMA lista (não 10 numIds)
    assert len(ch2 | groups | levels) == 3               # uma <w:num> nova por lista
    numbering = rc.document.part.numbering_part.element
    abstract_of = {n.numId: n.abstractNumId.val for n in numbering.num_lst}
    assert abstract_of[num_ids[11]] == abstract_of[num_ids[15]]   # mesma definição (29)
    names = [a.find(qn("w:name")).get(qn("w:val")) for a in numbering.findall(qn("w:abstractNum"))
             if a.find(qn("w:name")) is not None]
    assert names.count("G2_LIST_bullet") == 1 and names.count("G2_LIST_29") == 1
    created = [r.component_id for r in rc.results if r.component_id.startswith("LIST:")]
    assert created == ["LIST:bullet", "LIST:29"]          # abstractNum criado uma vez e registrado
    num = numbering.num_having_numId(num_ids[15])
    assert num.findall(qn("w:lvlOverride"))[0].find(qn("w:startOverride")).get(qn("w:val")) == "1"
    # w:abstractNum vem antes de todo w:num (ordem do schema)
    tags = [child.tag for child in numbering]
    assert max(i for i, t in enumerate(tags) if t == qn("w:abstractNum")) < min(
        i for i, t in enumerate(tags) if t == qn("w:num"))


def test_list_uses_the_foundation_abstract_num_when_mapped(tmp_path, blocks):
    rc = make_rc(tmp=tmp_path)
    numbering = rc.document.part.numbering_part.element
    foundation = engine._abstract_num_xml(77, "29")       # como se a fundação o tivesse criado
    foundation.remove(foundation.find(qn("w:name")))
    numbering.insert(0, foundation)
    rc.data["list_abstract_nums"] = {"29": 77}
    render_block(rc, blocks["P2.2_GRUPOS_LIST"], {})
    assert not [r for r in rc.results if r.component_id.startswith("LIST:")]
    num_id = rc.document.paragraphs[0]._p.pPr.numPr.numId.val
    assert numbering.num_having_numId(num_id).abstractNumId.val == 77


def test_list_definitions_agree_with_the_p24_data_rules():
    path = REPO_ROOT / "config" / "data_rules" / "p24_blocks.yaml"
    rules = yaml.safe_load(path.read_text(encoding="utf-8"))
    numbering = rules["common"]["numbering"]
    for key in ("29", "47"):
        for ilvl, level in enumerate(LIST_DEFINITIONS[key]):
            spec = numbering[f"numId_{key}"][f"lvl{ilvl}"]
            assert level.num_fmt == spec["numFmt"]
            assert (level.left, level.hanging) == (spec["ind_left"], spec["hanging"])
            if spec["numFmt"] != "bullet":
                assert level.lvl_text == spec["lvlText"]


def test_delegated_block_without_renderer_leaves_a_visible_marker(tmp_path, blocks):
    rc = make_rc(tmp=tmp_path)
    result = render_block(rc, blocks["P2.4_RM"], {})
    assert result.status == engine.PENDING_STATUS
    assert rc.document.paragraphs[0].text == "[PENDENTE: P2.4_RM]"
    # bloco FIXED_TEXT que na verdade é imagem também fica pendente
    assert render_block(rc, blocks["P2.2_PREDECESSORAS_IMG"], {}).status == engine.PENDING_STATUS


def test_registered_renderer_receives_the_block(tmp_path, blocks):
    seen = []

    @register_block_renderer("P2.4_RI")
    def fake(rc, block, values):
        seen.append(block.block_id)
        return rc.record(ComponentResult(block.block_id, "OK", detail="fake"))

    try:
        rc = make_rc(tmp=tmp_path)
        assert render_block(rc, blocks["P2.4_RI"], {}).detail == "fake"
        assert seen == ["P2.4_RI"]
    finally:
        BLOCK_RENDERERS.pop("P2.4_RI", None)


def test_absent_presence_skips_the_block(tmp_path, blocks):
    rc = make_rc(rows=[], tmp=tmp_path)
    assert render_block(rc, blocks["P2.1_TABLE_CALL"], {}).status == "SKIPPED"
    assert rc.document.paragraphs == []


def test_missing_style_is_an_explicit_error(tmp_path, blocks):
    rc = make_rc(tmp=tmp_path)
    rc.document = Document()          # sem os styleIds do nº 14
    with pytest.raises(MissingStyleError):
        render_block(rc, blocks["APRES_TITLE"], {})


def test_empty_spacer_emits_one_paragraph_per_recorded_position(tmp_path, blocks):
    rc = make_rc(tmp=tmp_path)
    render_block(rc, blocks["ENC_SPACERS"], {})
    assert [p.text for p in rc.document.paragraphs] == ["", "", "", ""]
