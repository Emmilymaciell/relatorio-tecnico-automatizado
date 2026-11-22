"""Extração factual do golden test (`prog_g2_report.qa.extract`).

Offline: PDFs SINTÉTICOS gerados em memória (tests/fixtures/qa_synthetic.py). O teste
`-m golden` lê os PDFs reais nº 13 e nº 14 de `tmp/downloads/relatorios_11_14/` (somente
leitura, nunca versionados) e confere invariantes já provados na descoberta; sem `-m golden`
ou sem os arquivos, é pulado.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path

import pytest

pytest.importorskip("pymupdf")

from prog_g2_report.qa.extract import (
    COMPANIES,
    PRODUCT_CONTROL_FIELDS,
    ROAD_RE,
    extract_facts,
    finish_section,
    mask_facts,
    narrative_facts,
    normalize_road,
    parse_date_pt,
    signatory_hash,
    text_codes,
)
from prog_g2_report.report_id import parse_report_filename, strip_accents
from fixtures.qa_synthetic import (
    Page,
    boxed,
    facts_of,
    heading,
    panel,
    row,
    synthetic_pages,
    table,
    text,
)

ROOT = Path(__file__).resolve().parents[1]
QA_DIR = ROOT / "src" / "prog_g2_report" / "qa"


@pytest.fixture(scope="module")
def facts(tmp_path_factory) -> dict:
    return facts_of(synthetic_pages(), tmp_path_factory.mktemp("qa") / "ref.pdf")


def _long(prefix: str, n: int) -> str:
    """n palavras distintas, só letras (nenhum fato)."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    return " ".join(f"{prefix}{letters[k // 26]}{letters[k % 26]}" for k in range(n))


# --------------------------------------------------------------------------- páginas


def test_pages_orientation_size_and_bands(facts):
    assert facts["page_count"] == 9
    assert facts["orientation_runs"] == [["portrait", 4], ["landscape", 1], ["portrait", 4]]
    assert {p["size_name"] for p in facts["pages"]} == {"A4"}
    landscape = facts["pages"][4]
    assert landscape["orientation"] == "landscape"
    assert landscape["width_cm"] == pytest.approx(29.7, abs=0.01)
    body = [p for p in facts["pages"] if not p["is_cover"]]
    assert {tuple(p["header_text"]) for p in body} == {
        ("PROGRAMA | CONSÓRCIO ESTRUTURADOR DO PROGRAMA",)}
    assert {tuple(p["footer_text"]) for p in body} == {("-CONFIDENCIAL-",)}
    # Número impresso no rodapé é separado do texto do rodapé e igual à página física.
    assert [p["printed_page_number"] for p in body] == [p["index"] for p in body]
    cover = facts["pages"][0]
    assert cover["header_text"] == [] and cover["printed_page_number"] is None


def test_headings_sequence_merges_wrapped_title_and_skips_cover(facts):
    labels = [h["label"] for h in facts["headings"]]
    assert labels == [
        "SUMÁRIO",
        "1 APRESENTAÇÃO",
        "2 GESTÃO DE ENGENHARIA E SOCIOAMBIENTAL",
        "2.1 Produto 2.1 - Relatório de Coordenação Setorial dos Serviços de Engenharia",
        "2.1.1 Descrição das atividades atribuídas",
        "2.1.2 Produtos desenvolvidos no período",
        "2.4 Produto 2.4 - Relatório de Gerenciamento Técnico de Obra",
        "2.4.2 Produtos desenvolvidos no período",
        "ENCERRAMENTO",
        "ANEXOS",
    ]
    by_key = {h["key"]: h for h in facts["headings"]}
    assert by_key["2.1.1"]["level"] == 3 and by_key["ANEXOS"]["level"] == 1
    assert by_key["2.4.2"]["page"] == 7


def test_bold_text_inside_a_vector_figure_is_not_a_heading(tmp_path):
    """nº 13: o cabeçalho "PREDECESSORES" (negrito 10,7 pt) do quadro vetorial de disciplinas
    virava título. Texto dentro de figura vetorial nunca é título."""
    pages = synthetic_pages()
    pages[3].items.append(boxed("PREDECESSORES MÍNIMOS"))
    f = facts_of(pages, tmp_path / "boxed.pdf")
    labels = [h["label"] for h in f["headings"]]
    assert "PREDECESSORES MÍNIMOS" not in labels
    assert labels[-1] == "ANEXOS" and len(labels) == 10


def test_body_size_ignores_large_tables(tmp_path):
    """nº 13: 165 linhas de Controle de Produtos a 7 pt tinham mais caracteres que o corpo
    a 11 pt; o corpo virava 7 pt e o título de cada recorte (negrito 9 pt) virava título."""
    many = [(f"PA-{n:03d}.1", "RD-101") for n in range(100, 145)]
    pages = synthetic_pages(annex_rows=many, declared_annexes=135)
    pages.insert(8, Page(items=[table(many)]))
    pages.insert(8, Page(items=[table(many)]))
    f = facts_of(pages, tmp_path / "big.pdf")
    assert f["body_font_size"] == 11.0
    assert [h["key"] for h in f["headings"]][-2:] == ["ENCERRAMENTO", "ANEXOS"]
    assert not any("Controle" in h["label"] for h in f["headings"])


# --------------------------------------------------------------------------- Controle de Produtos


def test_product_control_codes_by_block_in_order(facts):
    pc = facts["product_control"]
    assert pc["block_order"] == ["2.1", "2.4", "ANEXOS"]
    assert pc["blocks"]["2.1"] == ["PA-901.1", "NT-902.1", "NT-903.1"]
    assert pc["blocks"]["2.4"] == ["RO-545.1", "RO-546.1", "BM-007.1", "RI-509.1"]
    assert pc["blocks"]["ANEXOS"] == pc["blocks"]["2.1"] + pc["blocks"]["2.4"]
    assert [r["road"] for r in pc["rows"]["2.1"]] == ["RD-104", "Geral", "RD-102A"]
    assert [c["labels"][1] for c in pc["crops"]] == ["Manifestação"] * 3
    assert [c["anchor"] for c in pc["crops"]] == ["2.1.2", "2.4.2", "ANEXOS"]


def test_product_control_rows_carry_all_six_cells(facts):
    rows = facts["product_control"]["rows"]["2.1"]
    assert [r["cells"] for r in rows][1] == [
        "NT-902.1", "Parecer", "Descrição sintética do documento", "Geral", "01/08/2026",
        "Entregue"]
    assert all(len(r["cells"]) == len(PRODUCT_CONTROL_FIELDS) for b in
               facts["product_control"]["rows"].values() for r in b)


def test_product_control_wrapped_cell_and_centered_status_land_in_their_columns(tmp_path):
    """Descrição em duas linhas (acima e abaixo da linha do código) vira uma célula; status
    centralizado (começa antes do rótulo) continua no status, não na data."""
    pages = synthetic_pages(rows_24=[
        row("RO-545.1", "Relatório", "Relatório semanal de acompanhamento\nda obra", "RD-103",
            "03/08/2026", "Em elaboração"),
        row("RO-546.1", road="RD-104", status="Entregue"),
    ])
    rows = facts_of(pages, tmp_path / "wrap.pdf")["product_control"]["rows"]["2.4"]
    assert rows[0]["cells"] == ["RO-545.1", "Relatório",
                                "Relatório semanal de acompanhamento da obra", "RD-103",
                                "03/08/2026", "Em elaboração"]
    assert rows[0]["road"] == "RD-103" and rows[1]["road"] == "RD-104"


def test_narrative_facts_in_text_order_without_codes():
    text_ = ("Na RD- 104, às 10h, Boletins 07, 08 e 09 de abril/2026, entregue em 10/08/2026 "
             "(NT-726.1, P2.1, 40%) e Março.")
    assert narrative_facts(text_) == [
        "road:RD-104", "time:10H", "number:07", "number:08", "number:09", "month:2026-04",
        "status:ENTREGUE", "date:10/08/2026", "number:40", "month:03"]
    # Código quebrado no hífen de fim de linha (extrator 1.1) continua código, não número.
    assert narrative_facts("emitida a NC- 525.1 às 10h") == ["time:10H"]


# --------------------------------------------------------------------------- v3.0: fatos

@pytest.mark.parametrize(("value", "facts"), [
    # status: vocabulário fechado, flexão normalizada, negada antes da afirmativa
    ("Análise Programa: Não aprovado;", ["status:NAO_APROVADO@ANALISE PROGRAMA"]),
    ("todas encontram-se aprovadas e aceitas", ["status:APROVADO", "status:ACEITO"]),
    ("Reprovado, em análise, pendentes, atrasada, entregues, em elaboração, no prazo",
     ["status:REPROVADO", "status:EM_ANALISE", "status:PENDENTE", "status:ATRASADO",
      "status:ENTREGUE", "status:EM_ELABORACAO", "status:NO_PRAZO"]),
    ("condicionantes em atraso e próximas ao vencimento",
     ["status:ATRASADO", "status:PROXIMO_VENCIMENTO"]),
    ("Aceitação (1º Nível) e Aprovação (2º Nível)",
     ["status:ACEITACAO", "ordinal:1", "status:APROVACAO", "ordinal:2"]),
    ("disciplinas não aceitas no 1° nível", ["status:NAO_ACEITO", "ordinal:1"]),
    # negação como fato
    ("não há condicionantes; não houve atividades; nenhuma disciplina; sem informação; não "
     "foram", ["neg:NAO_HA", "neg:NAO_HOUVE", "neg:NENHUM", "neg:SEM", "neg:NAO"]),
    # cardinais por extenso -> número; 'uma' sozinho é artigo
    ("pendentes oito licenças: duas, cinco e quatro; uma licença; quarenta e três páginas",
     ["status:PENDENTE", "number:8", "number:2", "number:5", "number:4", "number:43"]),
    ("cento e quarenta e nove anexos e vinte e um dias; dois mil", ["number:149", "number:21",
                                                                   "number:2000"]),
    # dias da semana e executoras do contrato (domínio de config/g2_report_model.yaml)
    ("reunião com a DELTA às quintas e com o Consórcio CLX/TRAFEX às sextas-feiras",
     ["company:DELTA", "weekday:QUINTA", "company:CONSORCIO CLX/TRAFEX",
      "weekday:SEXTA"]),
])
def test_narrative_facts_v3_vocabulary(value, facts):
    assert narrative_facts(value) == facts


def test_ordinal_is_not_swallowed_and_number_sign_is_not_ordinal():
    """v2 perdia o "1º" (o "º" é \\w e o número exigia (?!\\w)); "N° 09" e "Eng°" não são
    ordinais."""
    assert narrative_facts("análise de 1º nível e de 2ª instância") == ["ordinal:1", "ordinal:2"]
    assert narrative_facts("Relatório N° 09, Eng° Fulano") == ["number:09"]


def test_status_is_qualified_by_its_field_so_swapped_labels_differ():
    """Status por campo: trocar os rótulos de dois campos muda os fatos mesmo com os mesmos
    status na mesma ordem."""
    a = narrative_facts("• Análise Programa: Aprovado;") + narrative_facts("• Análise GDP: Aceito;")
    b = narrative_facts("• Análise GDP: Aprovado;") + narrative_facts("• Análise Programa: Aceito;")
    assert a == ["status:APROVADO@ANALISE PROGRAMA", "status:ACEITO@ANALISE GDP"]
    assert a != b
    # rótulo longo não é campo; rodovia como rótulo qualifica pela rodovia
    assert narrative_facts("Conforme pode ser observado na imagem a seguir: não há") == [
        "neg:NAO_HA"]
    assert narrative_facts("• RD-103: Não apresenta condicionantes em atraso") == [
        "road:RD-103", "neg:NAO@RD-103", "status:ATRASADO@RD-103"]


def test_v31_reservation_qualifier_is_a_status_of_its_own():
    """Extrator 3.1: "aprovado com ressalva(s)" é status próprio (Projetos!S distingue por
    disciplina); trocar por "aprovado" muda o fato."""
    assert narrative_facts("o Aprovação: X e Y encontram- se aprovados com ressalva;") == [
        "status:APROVACAO", "status:APROVADO_COM_RESSALVA@APROVACAO"]
    assert narrative_facts("DUP Aprovada com Ressalvas e Tráfego aprovado") == [
        "status:APROVADO_COM_RESSALVA", "status:APROVADO"]
    # a forma negada vem antes (alternação da esquerda para a direita)
    assert narrative_facts("Não aprovado com ressalva") == ["status:NAO_APROVADO"]


def test_v31_disciplines_in_a_field_value_are_a_set_qualified_by_the_field():
    """Extrator 3.1: disciplinas no valor de um campo do 2.2 são fatos (conjunto em ordem
    canônica, depois dos outros fatos do campo): mudar a Pavimentação de lista muda o fato;
    a ordem da enumeração e as formas curta/longa do nome não mudam."""
    pending = "o Disciplinas pendentes de aprovação: Projeto de Terraplenagem e Projeto de Pavimentação;"
    analysis = ("o Disciplinas em análise: o Projeto de Drenagem e Obra de Arte Corrente (OAC) e o "
                "Projeto de Pavimentação encontram-se em análise pelo Programa;")
    assert narrative_facts(pending) == [
        "status:PENDENTE", "status:APROVACAO",
        "discipline:PAVIMENTACAO@DISCIPLINAS PENDENTES DE APROVACAO",
        "discipline:TERRAPLENAGEM@DISCIPLINAS PENDENTES DE APROVACAO"]
    assert "discipline:PAVIMENTACAO@DISCIPLINAS EM ANALISE" in narrative_facts(analysis)
    swapped = pending.replace("Projeto de Terraplenagem e Projeto de Pavimentação",
                              "Projeto de Pavimentação e Projeto de Terraplenagem")
    assert narrative_facts(swapped) == narrative_facts(pending)
    short = "o Aprovação: encontra-se aprovado apenas o Projeto Geométrico;"
    long_ = "o Aprovação: o Projeto Geométrico e Interseções encontra-se aprovado;"
    assert [f for f in narrative_facts(short) if f.startswith("discipline:")] == [
        f for f in narrative_facts(long_) if f.startswith("discipline:")] == [
        "discipline:GEOMETRICO@APROVACAO"]
    # OAE uma vez (nome + sigla); fora de campo a disciplina não é fato
    assert [f for f in narrative_facts(
        "o Aceitação: o Projeto de Obra de Arte Especial (OAE) se encontra aceito em 1º nível;")
        if f.startswith("discipline:")] == ["discipline:OAE@ACEITACAO"]
    assert not [f for f in narrative_facts("foram tratadas disciplinas como Projeto de Drenagem")
                if f.startswith("discipline:")]


def test_mask_facts_keeps_articles_and_replaces_each_fact_by_its_kind():
    assert mask_facts("uma licença aprovada em 10/08/2026 com a CSG").split() == [
        "uma", "licença", "<status>", "em", "<date>", "com", "a", "<company>"]


def test_company_domain_comes_from_the_contract_config():
    names = {strip_accents(n).upper() for n in COMPANIES}
    assert {"CSG", "CLX", "DELTA", "TETRA"} <= names
    assert "CONSORCIO TETRA ENGEX" in names


def test_finish_section_assigns_road_blocks_and_groups():
    section = {"title": "2.2.2 Produtos", "segments": [
        {"kind": "body", "text": "Documentação para Declaração de Utilidade Pública:"},
        {"kind": "body", "text": "A) RD-103:"},
        {"kind": "body", "text": "• Análise Programa: Aprovado;"},
        {"kind": "body", "text": "B) RD-101:"},
        {"kind": "body", "text": "• Disciplinas do Viário Principal:"},
        {"kind": "body", "text": "o Aprovação: nenhuma disciplina aprovada;"},
        {"kind": "body", "text": "Projeto de Desapropriação:"},
        {"kind": "body", "text": "A) RD-103:"},
        {"kind": "body", "text": "• Análise Programa: Não aprovado;"},
    ]}
    finish_section(section)
    assert list(zip(section["fact_blocks"], section["facts"], strict=True)) == [
        ("RD-103#1", "road:RD-103"),
        ("RD-103#1", "status:APROVADO@ANALISE PROGRAMA"),
        ("RD-101#1", "road:RD-101"),
        ("RD-101#1 > DISCIPLINAS DO VIARIO PRINCIPAL", "status:APROVACAO"),
        ("RD-101#1 > DISCIPLINAS DO VIARIO PRINCIPAL", "neg:NENHUM@APROVACAO"),
        ("RD-101#1 > DISCIPLINAS DO VIARIO PRINCIPAL", "status:APROVADO@APROVACAO"),
        ("RD-103#2", "road:RD-103"),
        ("RD-103#2", "status:NAO_APROVADO@ANALISE PROGRAMA"),
    ]
    assert section["text"].startswith("Documentação para Declaração")
    assert section["roads"] == ["RD-103", "RD-101"]


def test_paragraphs_are_segmented_by_spacing_and_list_markers(tmp_path):
    """Cada `text` sintético é um parágrafo (espaço de 6 pt entre itens, linhas a 16 pt);
    o quadro vetorial vira segmento 'figure' e não parágrafo do corpo."""
    pages = synthetic_pages()
    pages[3].items[4] = text(_long("primeiro", 30))
    pages[3].items.insert(5, text("A) RD-103: segundo parágrafo curto com status aprovado;"))
    facts = facts_of(pages, tmp_path / "par.pdf")
    body = [s for s in facts["sections"]["2.1.1"]["segments"] if s["kind"] == "body"]
    assert [len(s["text"].split()) for s in body] == [30, 8]
    assert body[1]["block"] == "RD-103#1"
    assert facts["sections"]["2.1.1"]["facts"] == ["road:RD-103",
                                                   "status:APROVADO@RD-103"]


def test_signatory_is_extracted_only_as_a_hash(tmp_path):
    facts = facts_of(synthetic_pages(signatory="Fulano Sintético de Teste"),
                     tmp_path / "sig.pdf")
    closing = facts["identity"]["closing"]
    expected = hashlib.sha256(b"FULANO SINTETICO DE TESTE").hexdigest()
    assert closing["signatory_sha256"] == expected
    assert "Fulano" not in json.dumps(facts["identity"], ensure_ascii=False)
    assert signatory_hash("Capital, 09 de Setembro de 2026 Eng° Fulano Sintético de Teste "
                          "Programa - Consórcio") == expected
    assert facts_of(synthetic_pages(), tmp_path / "nosig.pdf")["identity"]["closing"][
        "signatory_sha256"] is None


def test_raster_ink_map_measures_text_not_background(tmp_path):
    """Mapa de tinta: o mesmo numeral sobre fundos diferentes dá o mesmo mapa na região do
    numeral (fundo local por mediana); numeral diferente muda."""
    from prog_g2_report.qa.compare import region_delta

    def kpi_panel(kpi: str, name: str) -> dict:
        pages = synthetic_pages(declared_pages=10)
        pages.insert(7, Page(items=[panel(None, seed=2, kpi=kpi)]))
        return facts_of(pages, tmp_path / f"{name}.pdf")

    def content(facts: dict) -> dict:
        return next(f["content"] for p in facts["pages"] for f in p["figures"]
                    if f["kind"] == "raster" and f["anchor"] == "2.4.2")

    eight, same, three = kpi_panel("8", "k8"), kpi_panel("8", "k8b"), kpi_panel("3", "k3")
    ink = content(eight)["ink"]
    assert ink["columns"] == 96 and ink["dpi"] == 300 and ink["gray_b64"]
    box = [0.78, 0.080, 0.88, 0.135]
    assert region_delta(content(eight), content(same), box) == 0.0
    assert region_delta(content(eight), content(three), box) > 0.04


def test_section_facts_mask_identity_numbers(facts):
    """Apresentação e Encerramento: número do relatório, mês, contagens e assinatura têm
    verificação própria e ficam fora dos fatos da narrativa."""
    s = facts["sections"]
    assert s["1"]["facts"] == ["number:00/0000"]  # só o "Contrato N° 00/0000"
    assert "number:9" not in s["ENCERRAMENTO"]["facts"]
    assert s["2.4.2"]["facts"] == ["road:RD-103", "road:RD-101"]
    assert s["SUMARIO"]["facts"] == []


def test_raster_figures_carry_content_and_caption_road(tmp_path):
    pages = synthetic_pages(declared_pages=10)
    pages.insert(7, Page(items=[text("Referente ao acompanhamento da Rodovia RD-103:"),
                                panel("RD-103", seed=1),
                                text("Sem rodovia nesta linha."),
                                panel("RD-101", blank=True)]))
    figures = [f for p in facts_of(pages, tmp_path / "panels.pdf")["pages"]
               for f in p["figures"] if f["anchor"] == "2.4.2" and f["kind"] == "raster"]
    assert [f["caption_road"] for f in figures] == ["RD-103", None]
    assert figures[0]["content"]["gray_std"] > 10 and figures[1]["content"]["gray_std"] == 0
    assert figures[1]["content"]["colors"] == 1
    thumb = figures[0]["content"]["thumb"]
    assert thumb["columns"] == 32 and len(thumb["hex"]) == 2 * 32 * thumb["rows"]
    assert set(figures[0]["content"]["label"]) == {"template", "area"}


def test_two_crops_on_the_same_page_do_not_merge(tmp_path):
    pages = synthetic_pages()
    pages[5].items.append(table([("XY-999.1", "RD-101")]))
    pc = facts_of(pages, tmp_path / "two.pdf")["product_control"]
    assert [c["rows"] for c in pc["crops"] if c["page"] == 6] == [3, 1]
    assert pc["blocks"]["2.1"][-1] == "XY-999.1"


# --------------------------------------------------------------------------- texto


def test_section_text_codes_and_roads_exclude_tables(facts):
    s = facts["sections"]
    assert s["2.4.2"]["text_codes"] == ["RO-545.1", "RO-548.1", "RO-544.1", "RO-547.1"]
    assert s["2.4.2"]["roads"] == ["RD-103", "RD-101"]
    assert "Descrição sintética" not in s["2.4.2"]["text"]
    # RD-102A só existe numa célula do Controle de Produtos: não é rodovia citada no texto.
    assert "RD-102A" not in facts["roads"]
    assert facts["roads"] == ["RD-101", "RD-104", "RD-103"]


def test_identity_number_month_and_declared_counts(facts):
    ident = facts["identity"]
    assert ident["cover"]["report_numbers"] == [14]
    assert ident["cover"]["date_iso"] == "2026-09-08"
    assert ident["presentation"]["report_numbers"] == [14]
    assert ident["presentation"]["reference_months"] == ["2026-08"]
    closing = ident["closing"]
    assert closing["report_numbers"] == [14]
    assert closing["reference_months"] == ["2026-08"]
    assert closing["declared_pages"] == {"value": 9, "words": "nove"}
    assert closing["declared_annexes"] == {"value": 7, "words": "sete"}
    assert closing["signature_date_iso"] == "2026-09-09"


def test_identity_reads_the_number_each_part_actually_prints(tmp_path):
    pages = synthetic_pages(presentation_number=13)
    ident = facts_of(pages, tmp_path / "p.pdf")["identity"]
    assert ident["presentation"]["report_numbers"] == [13]
    assert ident["closing"]["report_numbers"] == [14]


# --------------------------------------------------------------------------- figuras


def test_figures_raster_vector_in_cm_with_title_anchor(facts):
    pages = facts["pages"]
    cover = pages[0]["figures"]
    assert [(f["kind"], f["anchor"]) for f in cover] == [("raster", "CAPA")]
    assert cover[0]["width_cm"] == pytest.approx(21.0, abs=0.05)
    assert cover[0]["height_cm"] == pytest.approx(29.7, abs=0.05)
    land = pages[4]["figures"]
    assert [(f["kind"], f["anchor"]) for f in land] == [("raster", "2.1.2")]
    assert land[0]["width_cm"] == pytest.approx(25.0, abs=0.05)
    assert land[0]["height_cm"] == pytest.approx(12.0, abs=0.05)
    assert [(f["kind"], f["anchor"]) for f in pages[5]["figures"]] == [("vector", "2.1.2")]
    assert [(f["kind"], f["anchor"]) for f in pages[8]["figures"]] == [("vector", "ANEXOS")]


# --------------------------------------------------------------------------- normalização


def test_text_codes_rejoin_hyphen_line_break():
    """Extrator 1.1: o Word quebra a linha no hífen do código ("NC-" + "025.1"); a junção das
    linhas vira "NC- 525.1" e o código tem de ser lido inteiro, como RD- 101 em ROAD_RE."""
    assert text_codes("emitidas as NC- 525.1, referente à RD-103, e a NC-525.1.") == [
        "NC-525.1", "NC-525.1"]
    assert text_codes("RO-540.1 a RO-544.1; BM-001.2 e ANEXO-123.4 x RCA-512.1") == [
        "RO-540.1", "RO-544.1", "BM-001.2", "RCA-512.1"]
    assert text_codes("NC -525.1 e NC-25.1") == []


def test_road_and_date_normalization():
    assert normalize_road("102", "a") == "RD-102A"
    assert [normalize_road(*m) for m in ROAD_RE.findall("RD 102a, RD-101 e RD-102")] == [
        "RD-102A", "RD-101", "RD-102"]
    assert parse_date_pt("08 de Setembro de 2026") == "2026-09-08"
    assert parse_date_pt("11de Agosto de 2026") == "2026-08-11"
    assert parse_date_pt("sem data") is None


def test_empty_page_and_page_without_header_are_tolerated(tmp_path):
    pages = [Page(cover=True), Page(header="", footer="", numbered=False,
                                    items=[heading("ENCERRAMENTO"), text("Fim.")])]
    f = facts_of(pages, tmp_path / "min.pdf")
    assert f["page_count"] == 2
    assert f["pages"][1]["header_text"] == [] and f["pages"][1]["printed_page_number"] is None
    assert f["identity"]["closing"]["declared_pages"] is None
    assert f["product_control"]["blocks"] == {}


# --------------------------------------------------------------------------- independência


def test_qa_never_imports_builder_or_render():
    """WAVE1 §H: a régua não pode depender do que mede."""
    for path in QA_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                assert ".builder" not in name and "render" not in name, (path.name, name)


# --------------------------------------------------------------------------- golden (PDF real)


def _reference_dirs() -> list[Path]:
    env = os.environ.get("PROG_G2_REFERENCE_DIR")
    dirs = [Path(env)] if env else []
    dirs.append(ROOT / "tmp" / "downloads" / "relatorios_11_14")
    parts = ROOT.parts
    for i in range(len(parts) - 1):
        if parts[i] == ".claude" and parts[i + 1] == "worktrees":
            dirs.append(Path(*parts[:i]) / "tmp" / "downloads" / "relatorios_11_14")
    return dirs


def _reference_pdf(number: int) -> Path | None:
    for d in _reference_dirs():
        if not d.is_dir():
            continue
        for pdf in sorted(d.glob("*.pdf")):
            ref = parse_report_filename(pdf.name)
            if ref and ref.report_number == number:
                return pdf
    return None


@pytest.fixture(scope="module")
def real_facts(request):
    if "golden" not in (request.config.getoption("-m") or ""):
        pytest.skip("teste do PDF real: rodar com -m golden")
    cache: dict[int, dict] = {}

    def get(number: int) -> dict:
        if number not in cache:
            pdf = _reference_pdf(number)
            if pdf is None:
                pytest.skip(f"PDF real do Relatório G2 nº {number} indisponível")
            cache[number] = extract_facts(pdf)
        return cache[number]

    return get


@pytest.mark.golden
def test_golden_real_report_14_invariants(real_facts):
    f = real_facts(14)
    assert f["page_count"] == 43
    assert f["orientation_runs"] == [["portrait", 6], ["landscape", 8], ["portrait", 29]]
    assert f["product_control"]["counts"] == {"2.1": 3, "2.2": 48, "2.4": 98, "ANEXOS": 149}
    # WAVE1 §A: recortes por página 2.2=25+23; 2.4=32+34+32; anexos=31+31+39+33+15.
    crops = [(c["block"], c["rows"]) for c in f["product_control"]["crops"]]
    assert crops == [("2.1", 3), ("2.2", 25), ("2.2", 23), ("2.4", 32), ("2.4", 34),
                     ("2.4", 32), ("ANEXOS", 31), ("ANEXOS", 31), ("ANEXOS", 39),
                     ("ANEXOS", 33), ("ANEXOS", 15)]
    closing = f["identity"]["closing"]
    assert closing["declared_annexes"]["value"] == 149
    assert closing["declared_annexes"]["value"] == len(f["product_control"]["blocks"]["ANEXOS"])
    assert closing["declared_pages"] == {"value": 43, "words": "quarenta e três"}
    assert closing["report_numbers"] == [14] and closing["reference_months"] == ["2026-08"]
    # Anomalia APRESENTACAO_NUMERO_RELATORIO: a Apresentação diz 13.
    assert f["identity"]["presentation"]["report_numbers"] == [13]
    assert f["identity"]["cover"]["report_numbers"] == [14]
    assert len(f["headings"]) == 23 and f["headings"][-1]["label"] == "ANEXOS"
    assert len(set(f["product_control"]["blocks"]["ANEXOS"])) == 135  # 149 linhas, 135 códigos
    # v2: linha inteira; descrição quebrada em duas linhas vira uma célula.
    rows = f["product_control"]["rows"]
    assert rows["2.2"][1]["cells"] == [
        "NT-726.1", "Nota Técnica",
        "Nota Técnica de Análise de Projeto Executivo - Projeto de Terraplenagem", "RD-103",
        "10/08/2026", "Entregue"]
    assert all(len(r["cells"]) == 6 and all(r["cells"]) for b in rows.values() for r in b)
    # v2: rodovia da legenda de cada quadro do 2.2.2 e de cada painel de condicionantes.
    captions = [(fig["anchor"], fig["caption_road"]) for p in f["pages"]
                for fig in p["figures"] if fig["kind"] == "raster"
                and fig["anchor"] in ("2.2.2", "2.4.2")]
    assert captions == [("2.2.2", r) for r in ("RD-103", "RD-102A", "RD-101", "RD-104")] + [
        ("2.4.2", r) for r in ("RD-103", "RD-101", "RD-102A", "RD-103", "RD-104")]


@pytest.mark.golden
def test_golden_real_report_13_invariants(real_facts):
    f = real_facts(13)
    assert f["page_count"] == 43
    assert f["product_control"]["counts"] == {"2.1": 10, "2.2": 50, "2.4": 111, "ANEXOS": 165}
    assert f["identity"]["closing"]["declared_annexes"]["value"] == 165
    # DEC-012 §3: índice = corpo menos as 6 linhas BM "Em elaboração" (RD-102A e RD-104).
    rows = f["product_control"]["rows"]
    body = [(r["code"], r["road"]) for b in ("2.1", "2.2", "2.4") for r in rows[b]]
    annex = [(r["code"], r["road"]) for r in rows["ANEXOS"]]
    left_out = sorted(set(body) - set(annex))
    assert left_out == sorted((f"BM-00{n}.1", road) for n in (7, 8, 9)
                              for road in ("RD-102A", "RD-104"))
    assert f["identity"]["presentation"]["reference_months"] == ["2026-08"]
    # extrator 1.1: o PDF quebra a linha em "NC-" / "025.1"; o DOCX nº 13 cita NC-525.1 duas vezes
    assert f["sections"]["2.4.2"]["text_codes"].count("NC-525.1") == 2


@pytest.mark.golden
def test_golden_frozen_allowances_pin_what_the_real_pdfs_print(real_facts):
    """Um desvio pinado que não bate com o PDF real nunca casaria: seria letra morta. Desde as
    allowances v1.9 (comparador 4.0) o CONTENT está nos hunks aprovados: cada hunk tem o
    contexto e o texto de referência CONTÍGUOS no texto que o PDF publicado imprime, na sua
    unidade (e a âncora é a de um parágrafo que existe)."""
    from prog_g2_report.qa.compare import load_allowances
    from prog_g2_report.qa.textdiff import paragraph_anchor, text_units

    allowances = load_allowances()
    f14, f13 = real_facts(14), real_facts(13)
    for number, facts in ((14, f14), (13, f13)):
        units = text_units(facts)
        for h in allowances.approved_hunks(number).hunks:
            unit = units[h.section]
            run = [*h.context_before, *(h.reference_text.split(" ") if h.reference_text
                                       else []), *h.context_after]
            n = len(run)
            assert any(unit.tokens[i:i + n] == run for i in range(len(unit.tokens) - n + 1)), (
                number, h.id)
            assert h.anchor in {paragraph_anchor(p) for p in unit.paragraphs}, (number, h.id)
    # a 2ª coluna do Controle de Produtos do nº 14 é "Parecer" em todos os recortes (hunk do
    # rótulo, anomalia CONTROLE_DE_PRODUTOS_CABECALHO_COLUNA_2)
    assert {c["labels"][1] for c in f14["product_control"]["crops"]} == {"Parecer"}
    assert "RD-102" in f14["sections"]["2.1.2"]["roads"]
    assert "Calibri" in f14["identity"]["cover"]["fonts"]
    assert f13["identity"]["cover"]["date_text"] == "11de Agosto de 2026"
    # v1.3: ALW-13-003 removida (o golden do nº 13 transcreve a data impressa; nada a permitir)
    ids = {a.id for a in allowances.allowances}
    assert "ALW-13-003" not in ids and f13["identity"]["closing"]["signature_date_iso"]
    assert "ArialMT" in f13["identity"]["cover"]["fonts"]
