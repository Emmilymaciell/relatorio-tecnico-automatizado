"""Comparador do golden test (`prog_g2_report.qa.compare`) com PDFs SINTÉTICOS.

Cada teste de regressão parte de uma referência coerente, aplica UMA mutação conhecida ao
"gerado" e exige que o comparador REPROVE com a diferença certa — e que a referência contra
ela mesma passe (senão o "reprova" não prova nada).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("pymupdf")

from prog_g2_report.qa.compare import (
    ALLOWED,
    COMPARATOR_VERSION,
    CRITICAL,
    MAJOR,
    MINOR,
    AllowanceError,
    AllowanceSet,
    compare,
    number_to_words_pt,
    parse_allowances,
    sequence_diff,
)
from prog_g2_report.qa.compare import _Comparator as Comparator
from fixtures.qa_synthetic import (
    Page,
    approve_all,
    clone,
    facts_of,
    heading,
    panel,
    row,
    synthetic_pages,
    text,
    write_pdf,
)

ROOT = Path(__file__).resolve().parents[1]


def frozen(*allowances: dict, **tolerances) -> AllowanceSet:
    return parse_allowances({
        "status": "FROZEN", "comparator_version": COMPARATOR_VERSION, "version": "test",
        "tolerances": tolerances, "allowances": list(allowances),
    })


def allowance(**kw) -> dict:
    base = {"id": "ALW-T-001", "report_number": 14}
    base.update(kw)
    return base


@pytest.fixture(scope="module")
def workdir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("cmp")


@pytest.fixture(scope="module")
def ref(workdir) -> dict:
    return facts_of(synthetic_pages(), workdir / "ref.pdf")


def gen_of(pages: list[Page], workdir: Path, name: str) -> dict:
    return facts_of(pages, workdir / f"{name}.pdf")


def blocking(report, check: str) -> list:
    return [d for d in report.find(check) if d.severity in (CRITICAL, MAJOR)]


def _blocking_checks(report) -> set[str]:
    return {d.check for d in report.differences if d.severity in (CRITICAL, MAJOR)}


# --------------------------------------------------------------------------- linha de base


def test_identical_report_passes(ref):
    report = compare(ref, ref, report_number=14)
    assert report.passed, report.reasons
    assert report.differences == []
    assert report.metrics["structural_score"] == 1.0
    assert report.metrics["content_accuracy"] == 1.0


# --------------------------------------------------------------------------- regressões


def test_missing_code_fails(ref, workdir):
    rows = [r for r in synthetic_pages()[6].items[3].rows if r[0] != "BM-007.1"]
    gen = gen_of(synthetic_pages(rows_24=rows), workdir, "missing")
    report = compare(ref, gen, report_number=14)
    assert not report.passed
    for block in ("block:2.4", "block:ANEXOS"):
        hit = report.find("product_control_codes", scope=block, kind="missing", value="BM-007.1")
        assert hit and hit[0].severity == CRITICAL
    assert report.metrics["content_accuracy"] < 1.0
    # O encerramento coerente com 6 anexos ainda diverge da referência (7).
    assert blocking(report, "declared_annexes")


def test_swapped_order_fails_even_with_same_codes(ref, workdir):
    rows = list(synthetic_pages()[6].items[3].rows)
    rows[0], rows[1] = rows[1], rows[0]
    annex = synthetic_pages()[8].items[1].rows  # índice intacto: só o 2.4 troca
    gen = gen_of(synthetic_pages(rows_24=rows, annex_rows=annex), workdir, "order")
    report = compare(ref, gen, report_number=14)
    assert not report.passed
    moved = report.find("product_control_codes", scope="block:2.4", kind="order")
    assert moved and all(d.severity == CRITICAL for d in moved)
    assert report.find("product_control_codes", scope="block:ANEXOS") == []
    assert report.metrics["product_control"]["2.4"]["reference"] == 4
    assert report.metrics["product_control"]["2.4"]["generated"] == 4


def test_landscape_page_turned_portrait_fails(ref, workdir):
    pages = synthetic_pages()
    pages[4].orientation = "portrait"
    report = compare(ref, gen_of(pages, workdir, "portrait"), report_number=14)
    assert not report.passed
    runs = report.find("orientation_runs")
    assert runs and runs[0].severity == CRITICAL
    assert runs[0].reference == ["portrait", "landscape", "portrait"]
    assert runs[0].generated == ["portrait"]


def test_last_landscape_page_turned_portrait_fails_by_run_length(workdir):
    """Paisagem no fim do bloco: a sequência de blocos não muda, o comprimento sim."""
    base = synthetic_pages()
    base.insert(5, Page(orientation="landscape", items=[text("Quadro 2.")]))
    reference = facts_of(base, workdir / "two_land.pdf")
    mutated = clone(base)
    mutated[5].orientation = "portrait"
    report = compare(reference, facts_of(mutated, workdir / "one_land.pdf"))
    assert not report.passed
    lengths = report.find("orientation_run_length")
    assert {(d.scope, d.reference, d.generated) for d in lengths} == {
        ("run:2", 2, 1), ("run:3", 4, 5)}
    assert all(d.severity == MAJOR for d in lengths)


def test_missing_heading_fails(ref, workdir):
    pages = synthetic_pages()
    pages[3].items = [i for i in pages[3].items if not i.text.startswith("2.1.2")]
    report = compare(ref, gen_of(pages, workdir, "noheading"), report_number=14)
    assert not report.passed
    hit = report.find("heading_sequence", kind="missing")
    assert [d.value for d in hit] == ["2.1.2 Produtos desenvolvidos no período"]
    assert hit[0].severity == CRITICAL


def test_reordered_headings_fail(ref, workdir):
    pages = synthetic_pages()
    pages[6].items[0], pages[6].items[1] = pages[6].items[1], pages[6].items[0]
    report = compare(ref, gen_of(pages, workdir, "reorder"), report_number=14)
    assert not report.passed
    assert [d.severity for d in report.find("heading_sequence")] == [CRITICAL]


def test_renamed_heading_is_major(ref, workdir):
    pages = synthetic_pages()
    pages[3].items[3] = heading("2.1.1 Descrição das atividades")
    report = compare(ref, gen_of(pages, workdir, "rename"), report_number=14)
    hit = report.find("heading_text")
    assert hit and hit[0].severity == MAJOR and hit[0].value == "2.1.1"
    assert not report.passed


def test_wrong_report_number_fails(ref, workdir):
    gen = gen_of(synthetic_pages(closing_number=13), workdir, "num13")
    report = compare(ref, gen, report_number=14)
    assert not report.passed
    expected = report.find("expected_report_number", scope="closing")
    assert expected and expected[0].severity == CRITICAL
    assert report.find("report_number", scope="closing")[0].severity == CRITICAL
    assert report.find("expected_report_number", scope="cover") == []


def test_whole_report_numbered_wrong_fails_even_if_reference_agrees(workdir):
    """Gerar o nº 13 quando se pediu o 14: a referência errada não salva o gerado."""
    wrong = facts_of(synthetic_pages(number=13), workdir / "all13.pdf")
    report = compare(wrong, wrong, report_number=14)
    assert not report.passed
    assert {d.scope for d in report.find("expected_report_number")} == {
        "cover", "presentation", "closing"}


def test_wrong_month_fails(ref, workdir):
    gen = gen_of(synthetic_pages(month="2026-07"), workdir, "month")
    report = compare(ref, gen, report_number=14)
    assert not report.passed
    assert {d.scope for d in report.find("reference_month")} == {"presentation", "closing"}
    assert report.find("cover_date")[0].severity == CRITICAL


def test_header_and_footer_regressions_are_major(ref, workdir):
    pages = synthetic_pages()
    pages[6].footer = ""
    pages[7].header = "PROGRAMA | CONSORCIO"
    report = compare(ref, gen_of(pages, workdir, "hf"), report_number=14)
    assert not report.passed
    assert report.find("footer_text")[0].severity == MAJOR
    assert report.find("header_text")[0].severity == MAJOR


def test_page_number_not_printed_is_major(ref, workdir):
    pages = synthetic_pages()
    pages[5].numbered = False
    report = compare(ref, gen_of(pages, workdir, "nonum"), report_number=14)
    assert report.find("page_number")[0].severity == MAJOR


def test_missing_figure_is_major_and_resized_figure_is_minor(ref, workdir):
    pages = synthetic_pages()
    pages[2].items = [i for i in pages[2].items if i.kind != "image"]
    pages[4].items[0].size_cm = (22.0, 12.0)
    report = compare(ref, gen_of(pages, workdir, "fig"), report_number=14)
    count = report.find("figure_count", scope="anchor:1")
    assert count and count[0].severity == MAJOR and count[0].reference == 1
    bbox = report.find("figure_bbox", scope="anchor:2.1.2")
    assert bbox and bbox[0].severity == MINOR
    assert bbox[0].context["max_delta_cm"] == pytest.approx(3.0, abs=0.05)
    assert report.metrics["structural_score"] < 1.0
    assert not report.passed


def test_road_missing_from_text_fails(ref, workdir):
    pages = synthetic_pages()
    pages[3].items[4] = text("Reuniões de alinhamento técnico com a executora da RD-101.")
    report = compare(ref, gen_of(pages, workdir, "road"), report_number=14)
    hit = report.find("roads", scope="section:2.1.1", kind="missing")
    assert [d.value for d in hit] == ["RD-104"] and hit[0].severity == CRITICAL
    assert not report.passed


def test_text_code_changed_fails(ref, workdir):
    pages = synthetic_pages()
    pages[6].items[2] = text("Relatórios semanais de cada obra: RD-103: RO-544.1 a RO-548.1; "
                             "RD-101: RO-544.1 a RO-547.1.")
    report = compare(ref, gen_of(pages, workdir, "ro"), report_number=14)
    kinds = {(d.kind, d.value) for d in report.find("text_codes", scope="section:2.4.2")}
    assert kinds == {("missing", "RO-545.1"), ("extra", "RO-544.1")}
    assert not report.passed


def test_declared_counts_must_match_the_generated_document(ref, workdir):
    gen = gen_of(synthetic_pages(declared_pages=10, declared_annexes=8), workdir, "incoh")
    report = compare(ref, gen, report_number=14)
    scopes = {d.scope for d in report.find("internal_consistency")}
    assert scopes == {"declared_pages", "declared_annexes"}
    assert all(d.severity == CRITICAL for d in report.find("internal_consistency"))


def test_number_in_words_must_match_the_numeral(ref, workdir):
    pages = synthetic_pages()
    closing = pages[7].items[1]
    closing.text = closing.text.replace("9 (nove) páginas", "9 (oito) páginas")
    report = compare(ref, gen_of(pages, workdir, "words"), report_number=14)
    hit = report.find("declared_words", scope="closing:declared_pages")
    assert hit and hit[0].severity == MAJOR and hit[0].generated == "oito"


def test_product_control_label_change_is_major(ref, workdir):
    from fixtures.qa_synthetic import LABELS

    pages = synthetic_pages()
    labels = list(LABELS)
    labels[1] = "Parecer"
    pages[5].items[0].labels = labels
    report = compare(ref, gen_of(pages, workdir, "label"), report_number=14)
    hit = report.find("product_control_labels", scope="block:2.1")
    assert hit and hit[0].severity == MAJOR
    assert (hit[0].reference, hit[0].generated) == ("Manifestação", "Parecer")


# --------------------------------------------------------------------------- v2: linha inteira

FULL_24 = [
    row("RO-545.1", "Relatório", "Relatório semanal de obra", "RD-103", "03/08/2026"),
    row("RO-546.1", "Relatório", "Relatório semanal de obra", "RD-103", "10/08/2026"),
    row("BM-007.1", "Boletim", "Boletim de medição - Topografia", "RD-104", "05/08/2026"),
    row("RI-509.1", "Relatório", "Relatório de inspeção do alojamento", "RD-101", "07/08/2026",
        "Em elaboração"),
]
CELL_CHANGES = {
    # campo: (índice da célula, valor novo) — a regressão que o QA-E injetou no PDF real
    "kind": (1, "Parecer"),
    "description": (2, "Boletim de medição - Drenagem"),
    "road": (3, "RD-103"),
    "date": (4, "05/07/2026"),
    "status": (5, "Pendente"),
}


def pages_with_rows(rows_24: list[tuple]) -> list[Page]:
    """O índice de anexos fica como na referência: a mutação só toca o recorte do 2.4."""
    return synthetic_pages(rows_24=rows_24, annex_rows=[*synthetic_pages()[5].items[0].rows,
                                                         *FULL_24])


@pytest.fixture(scope="module")
def ref_rows(workdir) -> dict:
    return facts_of(pages_with_rows(FULL_24), workdir / "ref_rows.pdf")


@pytest.mark.parametrize("field", sorted(CELL_CHANGES))
def test_product_control_cell_change_is_critical_even_with_the_same_codes(ref_rows, workdir,
                                                                         field):
    """QA-E: datas 10/08->10/07, "Entregue"->"Pendente", RD-103->RD-104 e descrição trocada
    passavam no v1, que só comparava a sequência de códigos."""
    index, value = CELL_CHANGES[field]
    rows = [list(r) for r in FULL_24]
    rows[2][index] = value
    report = compare(ref_rows, gen_of(pages_with_rows([tuple(r) for r in rows]), workdir,
                                      f"cell_{field}"), report_number=14)
    assert report.find("product_control_codes") == []  # o que o v1 via: nada
    hit = report.find("product_control_rows", scope="block:2.4")
    assert [(d.value, d.context["field"], d.generated) for d in hit] == [
        ("BM-007.1#1", field, value)]
    assert hit[0].severity == CRITICAL
    assert report.find("product_control_rows", scope="block:ANEXOS") == []
    assert report.metrics["product_control"]["2.4"]["rows_equal"] == 3
    assert report.metrics["content_accuracy"] < 1.0
    assert not report.passed


def test_product_control_cell_wrapped_differently_is_the_same_cell(ref_rows, workdir):
    """A mesma descrição quebrada em duas linhas (coluna mais estreita) não é diferença; uma
    palavra trocada na 2ª linha é."""
    wrapped = [list(r) for r in FULL_24]
    wrapped[3][2] = "Relatório de inspeção\ndo alojamento"
    same = compare(ref_rows, gen_of(pages_with_rows([tuple(r) for r in wrapped]), workdir,
                                    "wrap_same"), report_number=14)
    assert same.find("product_control_rows") == [], same.find("product_control_rows")
    assert same.passed, same.reasons

    wrapped[3][2] = "Relatório de inspeção\ndo canteiro"
    other = compare(ref_rows, gen_of(pages_with_rows([tuple(r) for r in wrapped]), workdir,
                                     "wrap_other"), report_number=14)
    hit = other.find("product_control_rows", scope="block:2.4")
    assert [(d.value, d.context["field"]) for d in hit] == [("RI-509.1#1", "description")]
    assert hit[0].generated == "Relatório de inspeção do canteiro"


# --------------------------------------------------------------------------- v2: narrativa

FACTS_TEXT = ("Reuniões às quintas, às 10h, com a executora da RD-101; avaliados os Boletins "
              "de Medição 07, 08 e 09, referentes a abril/2026, e entregue em 10/08/2026 o "
              "Relatório N° 09 da RD-104.")


def pages_with_text(value: str, **kw) -> list[Page]:
    pages = synthetic_pages(**kw)
    pages[3].items[4] = text(value)  # corpo do 2.1.1
    return pages


@pytest.fixture(scope="module")
def ref_facts(workdir) -> dict:
    return facts_of(pages_with_text(FACTS_TEXT), workdir / "ref_facts.pdf")


@pytest.mark.parametrize(("old", "new", "missing", "extra"), [
    ("às 10h", "às 15h", "time:10H", "time:15H"),                       # hora da reunião
    ("07, 08 e 09", "06, 07 e 08", "number:09", "number:06"),           # Boletins
    ("10/08/2026", "10/07/2026", "date:10/08/2026", "date:10/07/2026"),  # data
    ("abril/2026", "maio/2026", "month:2026-04", "month:2026-05"),    # mês citado
    ("N° 09", "N° 08", "number:09", "number:08"),                       # nº de relatório citado
])
def test_narrative_fact_change_is_critical(ref_facts, workdir, old, new, missing, extra):
    gen = gen_of(pages_with_text(FACTS_TEXT.replace(old, new)), workdir,
                 f"fact_{abs(hash(new)) % 10**6}")
    report = compare(ref_facts, gen, report_number=14)
    assert report.find("roads") == [] and report.find("text_codes") == []  # cegueira do v1
    hit = report.find("narrative_facts", scope="section:2.1.1")
    assert {d.value for d in hit} >= {missing, extra}, [(d.kind, d.value) for d in hit]
    assert all(d.severity == CRITICAL for d in hit)
    assert report.metrics["content_accuracy"] < 1.0
    assert not report.passed


def test_road_mention_swapped_with_the_same_road_set_is_critical(ref_facts, workdir):
    """'Na RD-104' no lugar de 'Na RD-101': o conjunto de rodovias da seção não muda (v1 cego),
    a sequência de menções muda."""
    swapped = FACTS_TEXT.replace("executora da RD-101", "executora da RD-104").replace(
        "Relatório N° 09 da RD-104", "Relatório N° 09 da RD-101")
    report = compare(ref_facts, gen_of(pages_with_text(swapped), workdir, "road_swap"),
                     report_number=14)
    assert report.find("roads") == []
    hit = report.find("narrative_facts", scope="section:2.1.1")
    assert hit and {d.value for d in hit} <= {"road:RD-101", "road:RD-104"}
    assert not report.passed


def test_identity_numbers_are_not_narrative_facts(workdir):
    """Número do relatório, mês, páginas/anexos declarados e assinatura têm verificação
    própria (com allowances); a narrativa não os conta de novo."""
    reference = facts_of(synthetic_pages(presentation_number=13, declared_pages=10,
                                         declared_annexes=8), workdir / "id_ref.pdf")
    gen = facts_of(synthetic_pages(), workdir / "id_gen.pdf")
    report = compare(reference, gen, report_number=14)
    assert report.find("narrative_facts") == []
    assert report.find("report_number", scope="presentation")
    assert report.find("declared_pages") and report.find("declared_annexes")
    assert reference["sections"]["SUMARIO"]["facts"] == []


def _words(prefix: str, n: int) -> str:
    """n palavras distintas, só letras (nenhum fato): 'termoab termoac ...'."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    return " ".join(f"{prefix}{letters[k // 26]}{letters[k % 26]}" for k in range(n))


DEC_010 = [
    allowance(id=f"ALW-T-{n}", reference={"dec": "DEC-010"}, dimension=dim, check=check,
              scope=scope, match={"max_abs_delta": 2})
    for n, (dim, check, scope) in enumerate([
        ("STRUCTURAL", "page_count", "document"),
        ("CONTENT", "declared_pages", "closing"),
        ("STRUCTURAL", "orientation_run_length", "run:3"),
        ("STRUCTURAL", "heading_page", "document"),
    ])
]


def test_text_page_removed_with_coherent_total_fails_by_coverage(workdir):
    """QA-E: páginas 15/22/23/24 removidas com o total declarado corrigido passavam (a
    paginação do DEC-010 cobre ±2 páginas). A cobertura da seção reprova."""
    def build(with_page: bool) -> list[Page]:
        pages = synthetic_pages(declared_pages=10 if with_page else 9)
        if with_page:
            pages.insert(7, Page(items=[text(_words("obra", 120))]))
        return pages

    reference = facts_of(build(True), workdir / "cov_ref.pdf")
    gen = facts_of(build(False), workdir / "cov_gen.pdf")
    report = compare(reference, gen, frozen(*DEC_010), report_number=14)
    assert report.find("page_count")[0].severity == ALLOWED
    assert report.find("internal_consistency") == []
    hit = report.find("narrative_coverage", scope="section:2.4.2")
    assert hit and hit[0].severity == MAJOR
    assert hit[0].context["longest_gap_words"] == 120
    assert report.metrics["narrative"]["2.4.2"]["coverage"] < 0.2
    assert not report.passed


def test_short_block_of_text_removed_fails_by_longest_gap(workdir):
    """Cobertura ainda acima do mínimo (0,92), mas 50 palavras contínuas sumiram: reprova pela
    maior lacuna. Uma palavra trocada não reprova."""
    head, middle, tail = _words("ini", 300), _words("meio", 50), _words("fim", 250)

    def build(second: str) -> list[Page]:
        pages = synthetic_pages(declared_pages=11)  # duas páginas de texto no 2.1.2
        pages[4:4] = [Page(items=[text(head)]), Page(items=[text(second)])]
        return pages

    reference = facts_of(build(f"{middle} {tail}"), workdir / "gap_ref.pdf")
    removed = compare(reference, gen_of(build(tail), workdir, "gap_cut"), report_number=14)
    hit = removed.find("narrative_coverage", scope="section:2.1.2")
    assert hit and hit[0].severity == MAJOR
    assert hit[0].context["coverage"] > 0.9 and hit[0].context["longest_gap_words"] == 50
    assert not removed.passed

    reworded = f"{middle.replace('meioab', 'outra')} {tail}"
    word = gen_of(build(reworded), workdir, "gap_word")
    ok = compare(reference, word, report_number=14)
    assert ok.find("narrative_coverage") == []
    # v4.0: a palavra trocada é um hunk de texto CRITICAL (só ele); aprovado, passa
    assert _blocking_checks(ok) == {"text_diff"}
    assert compare(reference, word, report_number=14,
                   approved_hunks=approve_all(reference, word, {"dec": "DEC-007"})).passed


def test_missing_section_is_critical(ref, workdir):
    pages = synthetic_pages()
    pages[3].items = [i for i in pages[3].items
                      if not i.text.startswith(("2.1.1", "Reuniões de alinhamento"))]
    report = compare(ref, gen_of(pages, workdir, "nosection"), report_number=14)
    hit = report.find("section_presence", scope="section:2.1.1")
    assert [(d.kind, d.severity) for d in hit] == [("missing", CRITICAL)]
    assert not report.passed


def test_narrative_similarity_is_scored(ref, workdir):
    """Texto acrescentado (sem fato novo, cobertura 100%) baixa a semelhança: v1 só anotava
    (UNSCORED); v2 conta na acurácia de conteúdo e reprova."""
    pages = synthetic_pages()
    pages[3].items[4] = text("Reuniões de alinhamento técnico com as executoras da RD-101 e da "
                             f"RD-104. {_words('extra', 12)}")
    report = compare(ref, gen_of(pages, workdir, "sim"), report_number=14)
    assert report.find("narrative_coverage") == [] and report.find("narrative_facts") == []
    hit = report.find("narrative_similarity", scope="section:2.1.1")
    assert hit and hit[0].severity == MINOR
    assert report.metrics["content_accuracy"] < 1.0
    assert not report.passed


# --------------------------------------------------------------------------- v2: figuras

def pages_with_panels(first=("RD-103", "RD-103"), second=("RD-101", "RD-101"), *,
                      seeds=(1, 1), blank=(False, False)) -> list[Page]:
    """Dois quadros no 2.4.2, cada um depois de uma legenda com a rodovia: (selo, legenda)."""
    pages = synthetic_pages(declared_pages=10)
    pages.insert(7, Page(items=[
        text(f"Referente ao acompanhamento da Rodovia {first[1]}:"),
        panel(first[0], seed=seeds[0], blank=blank[0]),
        text(f"Referente ao acompanhamento da Rodovia {second[1]}:"),
        panel(second[0], seed=seeds[1], blank=blank[1]),
    ]))
    return pages


@pytest.fixture(scope="module")
def ref_panels(workdir) -> dict:
    return facts_of(pages_with_panels(), workdir / "ref_panels.pdf")


def test_identical_panels_pass_with_identity_verified(ref_panels, workdir):
    report = compare(ref_panels, gen_of(pages_with_panels(), workdir, "panels_same"),
                     report_number=14)
    assert report.passed, report.reasons
    figures = report.metrics["figures"]
    assert figures["identity_verified"] == 2 and figures["identity_swapped"] == 0


def test_blank_panel_is_critical(ref_panels, workdir):
    gen = gen_of(pages_with_panels(blank=(True, False)), workdir, "panel_blank")
    report = compare(ref_panels, gen, report_number=14)
    assert report.find("figure_count") == [] and report.find("figure_bbox") == []  # v1 cego
    hit = report.find("figure_content", scope="anchor:2.4.2")
    assert [(d.kind, d.value, d.severity) for d in hit] == [("blank", "2.4.2#1", CRITICAL)]
    assert not report.passed


def test_swapped_panels_are_critical(workdir):
    """Imagens trocadas, legendas no lugar: só o selo dentro da imagem denuncia.

    Versão pública: os selos precisam diferir em dois dígitos, como os pares reais em que a
    margem `figure_identity_margin` foi calibrada. Selos que diferem num só dígito (RD-101 x
    RD-103, efeito da troca de nomes da sanitização) casam entre si com ~0,99 e o detector
    — corretamente, pela calibração — não distingue; por isso este teste usa RD-101 x RD-202.
    """
    ref = facts_of(pages_with_panels(("RD-202", "RD-202"), ("RD-101", "RD-101")),
                   workdir / "ref_panels_swap.pdf")
    gen = gen_of(pages_with_panels(("RD-101", "RD-202"), ("RD-202", "RD-101")), workdir,
                 "panel_swap")
    report = compare(ref, gen, report_number=14)
    hit = report.find("figure_identity", scope="anchor:2.4.2")
    assert [(d.kind, d.value, d.generated) for d in hit] == [
        ("swapped", "2.4.2#1", 2), ("swapped", "2.4.2#2", 1)]
    assert all(d.severity == CRITICAL for d in hit)
    assert report.find("figure_content") == []
    assert not report.passed


def test_panel_with_other_content_is_critical(ref_panels, workdir):
    gen = gen_of(pages_with_panels(seeds=(5, 1)), workdir, "panel_other")
    report = compare(ref_panels, gen, report_number=14)
    hit = report.find("figure_content", scope="anchor:2.4.2")
    assert [(d.kind, d.value) for d in hit] == [("mismatch", "2.4.2#1")]
    assert not report.passed


def test_panel_caption_road_change_is_critical(ref_panels, workdir):
    gen = gen_of(pages_with_panels(("RD-103", "RD-104")), workdir, "panel_caption")
    report = compare(ref_panels, gen, report_number=14)
    hit = report.find("figure_identity", kind="caption")
    assert [(d.reference, d.generated) for d in hit] == [("RD-103", "RD-104")]
    assert not report.passed


# --------------------------------------------------------------------------- v3: narrativa

STATUS_TEXT = [
    "Documentação para Declaração de Utilidade Pública:",
    "A) RD-103:",
    "- Análise Programa: Aprovado;",
    "- Análise GDP: Aceito;",
    "B) RD-101:",
    "- Análise Programa: Não aprovado;",
    "Aceitação: todas as disciplinas encontram-se aceitas em 1º nível;",
    "Aprovação: Todas as disciplinas encontram-se aprovadas;",
    "Encontram-se pendentes oito licenças e não há condicionantes pendentes; nas quatro "
    "rodovias não houve atividades.",
    "Reunião com a DELTA às quintas, às 11h.",
]


def pages_with_paragraphs(paragraphs: list[str], **kw) -> list[Page]:
    """Cada string vira um parágrafo do 2.4.2 (página própria, antes do Controle de
    Produtos do 2.4)."""
    pages = synthetic_pages(declared_pages=10, **kw)
    pages.insert(7, Page(items=[text(p) for p in paragraphs]))
    return pages


@pytest.fixture(scope="module")
def ref_status(workdir) -> dict:
    return facts_of(pages_with_paragraphs(STATUS_TEXT), workdir / "ref_status.pdf")


def _status_variant(old: str, new: str) -> list[str]:
    changed = [p.replace(old, new, 1) for p in STATUS_TEXT]
    assert changed != STATUS_TEXT, old
    return changed


@pytest.mark.parametrize(("old", "new", "values"), [
    # QA2-E: estas trocas passavam no comparador 2.0 (só dígitos/datas/meses/rodovias)
    ("Análise Programa: Aprovado;", "Análise Programa: Não aprovado;",
     {"status:APROVADO@ANALISE PROGRAMA", "status:NAO_APROVADO@ANALISE PROGRAMA"}),
    ("Análise Programa: Não aprovado;", "Análise Programa: Aprovado;",
     {"status:APROVADO@ANALISE PROGRAMA", "status:NAO_APROVADO@ANALISE PROGRAMA"}),
    ("Aprovação: Todas", "Aceitação: Todas", {"status:APROVACAO", "status:ACEITACAO",
                                              "status:APROVADO@APROVACAO",
                                              "status:APROVADO@ACEITACAO"}),
    ("em 1º nível", "em 2º nível", {"ordinal:1", "ordinal:2"}),
    ("oito licenças", "nove licenças", {"number:8", "number:9"}),
    ("nas quatro rodovias", "nas três rodovias", {"number:4", "number:3"}),
    ("não há condicionantes", "há condicionantes", {"neg:NAO_HA"}),
    ("não houve atividades", "houve atividades", {"neg:NAO_HOUVE"}),
    ("com a DELTA", "com a CSG", {"company:DELTA", "company:CSG"}),
    ("às quintas", "às sextas", {"weekday:QUINTA", "weekday:SEXTA"}),
])
def test_v3_status_negation_extenso_company_weekday_changes_are_critical(ref_status, workdir,
                                                                        old, new, values):
    gen = gen_of(pages_with_paragraphs(_status_variant(old, new)), workdir,
                 f"status_{abs(hash((old, new))) % 10**6}")
    report = compare(ref_status, gen, report_number=14)
    assert report.find("roads") == [] and report.find("text_codes") == []
    hit = [d for d in report.find("narrative_facts", scope="section:2.4.2")
           if d.severity == CRITICAL]
    assert {d.value for d in hit} == values, [(d.kind, d.value) for d in hit]
    assert not report.passed


def test_v3_swapped_status_between_fields_or_roads_is_critical(ref_status, workdir):
    """Mesmo multiconjunto de status, outra ordem (QA2-E: Aprovado <-> Não aprovado entre
    RD-103 e RD-101) e rótulos de campo trocados com os mesmos status."""
    swapped = list(STATUS_TEXT)
    swapped[2], swapped[5] = "- Análise Programa: Não aprovado;", "- Análise Programa: Aprovado;"
    report = compare(ref_status, gen_of(pages_with_paragraphs(swapped), workdir, "st_swap"),
                     report_number=14)
    hit = report.find("narrative_facts", scope="section:2.4.2")
    assert hit and all(d.severity == CRITICAL for d in hit)
    assert {d.context["block"] for d in hit} == {"RD-103#1", "RD-101#1"}
    assert any("[RD-103#1]" in d.message for d in hit)

    labels = list(STATUS_TEXT)
    labels[2], labels[3] = "- Análise GDP: Aprovado;", "- Análise Programa: Aceito;"
    report = compare(ref_status, gen_of(pages_with_paragraphs(labels), workdir, "st_labels"),
                     report_number=14)
    assert {d.value for d in report.find("narrative_facts")} == {
        "status:APROVADO@ANALISE PROGRAMA", "status:ACEITO@ANALISE GDP",
        "status:APROVADO@ANALISE GDP", "status:ACEITO@ANALISE PROGRAMA"}
    assert not report.passed


def test_v3_same_text_passes(ref_status, workdir):
    report = compare(ref_status, gen_of(pages_with_paragraphs(STATUS_TEXT), workdir, "st_same"),
                     report_number=14)
    assert report.passed, report.reasons
    # + o parágrafo que o 2.4.2 sintético já tem antes do Controle de Produtos
    assert report.metrics["narrative"]["2.4.2"]["paragraphs_reference"] == len(STATUS_TEXT) + 1


LONG = [_words("ini", 200), _words("mei", 30), _words("fim", 200)]


@pytest.fixture(scope="module")
def ref_long(workdir) -> dict:
    return facts_of(pages_with_paragraphs(LONG), workdir / "ref_long.pdf")


def test_v3_short_paragraph_removed_fails_by_paragraph_coverage(ref_long, workdir):
    """QA2-E: parágrafo de 38 palavras apagado passava (cobertura da seção 0,90+ e lacuna < 40).
    Um parágrafo sem correspondente reprova; uma palavra trocada não."""
    gone = compare(ref_long, gen_of(pages_with_paragraphs([LONG[0], LONG[2]]), workdir,
                                    "long_cut"), report_number=14)
    assert gone.find("narrative_coverage") == []         # o que a v2 via: nada
    hit = gone.find("paragraph_coverage", scope="section:2.4.2")
    assert [(d.kind, d.reference, d.severity) for d in hit] == [("missing", 3, MAJOR)]
    assert hit[0].context["words"] == 30 and hit[0].generated < 0.6
    assert not gone.passed

    reworded = [LONG[0], LONG[1].replace("meiab", "outra"), LONG[2]]
    word = gen_of(pages_with_paragraphs(reworded), workdir, "long_word")
    ok = compare(ref_long, word, report_number=14)
    assert ok.find("paragraph_coverage") == []
    # v4.0: a palavra trocada é hunk CRITICAL (só ele); com o hunk aprovado, passa
    assert _blocking_checks(ok) == {"text_diff"}
    assert compare(ref_long, word, report_number=14,
                   approved_hunks=approve_all(ref_long, word, {"dec": "DEC-007"})).passed


def test_v3_moved_paragraph_is_not_missing(ref_long, workdir):
    moved = compare(ref_long, gen_of(pages_with_paragraphs([LONG[1], LONG[0], LONG[2]]),
                                     workdir, "long_moved"), report_number=14)
    assert moved.find("paragraph_coverage") == []


def test_v3_duplicated_paragraph_is_major_but_repeated_per_road_is_not(ref_long, workdir):
    """QA2-E: parágrafo duplicado passava. Repetido DENTRO do mesmo bloco = MAJOR; o texto
    padronizado que repete a mesma frase em cada rodovia (DEC-007) não é duplicação."""
    dup = compare(ref_long, gen_of(pages_with_paragraphs([LONG[0], LONG[1], LONG[1], LONG[2]]),
                                   workdir, "long_dup"), report_number=14)
    hit = dup.find("paragraph_duplicate", scope="section:2.4.2")
    assert [(d.reference, d.generated, d.severity) for d in hit] == [(1, 2, MAJOR)]
    assert not dup.passed

    per_road = ["A) RD-103:", "- Disciplinas em análise: nenhuma disciplina em análise;",
                "B) RD-101:", "- Disciplinas em análise: nenhuma disciplina em análise;"]
    reference = facts_of(pages_with_paragraphs([*per_road[:2], "B) RD-101:",
                                                "- Outra coisa qualquer sem fato;"]),
                         workdir / "road_ref.pdf")
    report = compare(reference, gen_of(pages_with_paragraphs(per_road), workdir, "road_gen"),
                     report_number=14)
    assert report.find("paragraph_duplicate") == []


def test_v3_signatory_change_is_critical_and_never_printed(workdir):
    reference = facts_of(synthetic_pages(signatory="Fulano Sintético de Teste"),
                         workdir / "sig_ref.pdf")
    same = compare(reference, facts_of(synthetic_pages(signatory="Fulano Sintético de Teste"),
                                       workdir / "sig_same.pdf"), report_number=14)
    assert same.find("signatory") == [] and same.passed, same.reasons
    other = compare(reference, facts_of(synthetic_pages(signatory="Beltrano Inventado Silva"),
                                        workdir / "sig_other.pdf"), report_number=14)
    hit = other.find("signatory", scope="closing")
    assert [d.severity for d in hit] == [CRITICAL]
    assert not other.passed
    rendered = other.to_markdown() + json.dumps(other.to_dict(), ensure_ascii=False)
    assert "Fulano" not in rendered and "Beltrano" not in rendered


# --------------------------------------------------------------------------- v3: regiões raster


def pages_with_tabbed_panels(tabs=(1, 4), kpis=("88", "88"), seeds=(3, 3)) -> list[Page]:
    """Dois painéis no 2.4.2 com seletor de abas (posição 1 = índices, 2 = condicionantes)."""
    pages = synthetic_pages(declared_pages=10)
    pages.insert(7, Page(items=[
        text("Conforme pode ser observado nas imagens a seguir:"),
        panel("", seed=seeds[0], tab=tabs[0], kpi=kpis[0]),
        panel("", seed=seeds[1], tab=tabs[1], kpi=kpis[1]),
    ]))
    return pages


@pytest.fixture(scope="module")
def ref_tabs(workdir) -> dict:
    return facts_of(pages_with_tabbed_panels(), workdir / "ref_tabs.pdf")


def test_v3_tabbed_panels_identical_pass(ref_tabs, workdir):
    report = compare(ref_tabs, gen_of(pages_with_tabbed_panels(), workdir, "tabs_same"),
                     report_number=14)
    assert report.passed, report.reasons
    assert report.metrics["figures"]["selector"] == {"2.4.2#1": [1, 1], "2.4.2#2": [4, 4]}


def test_v3_panel_of_another_road_fails_by_the_selector(ref_tabs, workdir):
    """QA2-E: painéis de condicionantes trocados (p30 <-> p31) passavam: mesmo leiaute, sem
    selo. A aba de rodovia destacada denuncia."""
    report = compare(ref_tabs, gen_of(pages_with_tabbed_panels(tabs=(4, 1)), workdir,
                                      "tabs_swap"), report_number=14)
    hit = report.find("figure_identity", kind="selector")
    assert [(d.value, d.reference, d.generated, d.severity) for d in hit] == [
        ("2.4.2#1", 1, 4, CRITICAL), ("2.4.2#2", 4, 1, CRITICAL)]
    assert not report.passed


def test_v3_changed_kpi_region_is_major(ref_tabs, workdir):
    report = compare(ref_tabs, gen_of(pages_with_tabbed_panels(kpis=("11", "88")), workdir,
                                      "tabs_kpi"), report_number=14)
    hit = report.find("figure_region", scope="anchor:2.4.2")
    assert [(d.value, d.severity) for d in hit] == [("2.4.2#1:kpi_pendentes", MAJOR)]
    assert hit[0].generated > hit[0].reference
    assert not report.passed


def test_v3_grid_swap_of_distinct_panels_is_critical(workdir):
    """Painéis de conteúdo distinto trocados sem selo: a grade de tinta casa com o outro."""
    reference = facts_of(pages_with_tabbed_panels(tabs=(None, None), kpis=(None, None),
                                                  seeds=(3, 11)), workdir / "grid_ref.pdf")
    swapped = facts_of(pages_with_tabbed_panels(tabs=(None, None), kpis=(None, None),
                                                seeds=(11, 3)), workdir / "grid_swap.pdf")
    report = compare(reference, swapped, report_number=14)
    hit = report.find("figure_identity", kind="swapped_grid")
    assert [(d.value, d.generated) for d in hit] == [("2.4.2#1", 2), ("2.4.2#2", 1)]
    assert not report.passed
    same = compare(reference, reference, report_number=14)
    assert same.find("figure_identity") == []


def test_v3_region_delta_and_selector_on_handmade_ink_maps():
    """Unidade: delta de região e aba destacada sobre mapas de tinta montados à mão."""
    import base64

    import numpy as np

    from prog_g2_report.qa.compare import region_delta, selected_tab

    def content(ink, gray) -> dict:
        return {"ink": {"columns": 96, "rows": ink.shape[0], "dpi": 300,
                        "b64": base64.b64encode(ink.astype(np.uint8).tobytes()).decode(),
                        "gray_b64": base64.b64encode(gray.astype(np.uint8).tobytes()).decode()}}

    ink = np.zeros((40, 96))
    gray = np.full((40, 96), 200)
    box = [0.0, 0.0, 0.25, 0.125]  # 24 x 12 células
    a = content(ink, gray)
    ink_b = ink.copy()
    ink_b[3:6, 3:6] = 255          # uma subcélula 3x3 inteira com tinta
    assert region_delta(a, a, box) == 0.0
    assert region_delta(a, content(ink_b, gray), box) == pytest.approx(1.0)
    assert region_delta(a, content(ink_b, gray), [0.5, 0.0, 0.75, 0.125]) == 0.0
    assert region_delta(a, content(np.zeros((5, 96)), gray[:5]), box) is None  # não cabe

    selector = {"box": [0.0, 0.0, 0.25, 0.04], "cells": 4, "min_contrast": 5}
    tabs = gray.copy()
    tabs[0:4, 18:24] = 120          # 4ª aba escura
    assert selected_tab(content(ink, tabs), selector) == 4
    assert selected_tab(content(ink, gray), selector) is None   # nenhuma se destaca


# --------------------------------------------------------------------------- allowances


@pytest.fixture(scope="module")
def ref_with_anomaly(workdir) -> dict:
    """Referência que reproduz a anomalia histórica do nº 14: Apresentação diz 13."""
    return facts_of(synthetic_pages(presentation_number=13), workdir / "ref_anomaly.pdf")


PRESENTATION_ALLOWANCE = allowance(
    reference={"anomaly": "APRESENTACAO_NUMERO_RELATORIO"}, dimension="CONTENT",
    check="report_number", scope="presentation", match={"reference": 13, "generated": 14})


def test_anomaly_allowance_turns_exact_deviation_into_allowed(ref, ref_with_anomaly):
    without = compare(ref_with_anomaly, ref, report_number=14)
    assert not without.passed
    assert without.find("report_number", scope="presentation")[0].severity == CRITICAL

    # v4.0: a allowance cobre a verificação de identidade, mas o "13" -> "14" do texto é um
    # hunk: sem o hunk aprovado continua CRITICAL
    only_allowance = compare(ref_with_anomaly, ref, frozen(PRESENTATION_ALLOWANCE),
                             report_number=14)
    assert _blocking_checks(only_allowance) == {"text_diff"}
    hunks = approve_all(ref_with_anomaly, ref, {"anomaly": "APRESENTACAO_NUMERO_RELATORIO"})
    report = compare(ref_with_anomaly, ref, frozen(PRESENTATION_ALLOWANCE), report_number=14,
                     approved_hunks=hunks)
    assert report.passed, report.reasons
    diff = report.find("report_number", scope="presentation")[0]
    assert diff.severity == ALLOWED and diff.original_severity == CRITICAL
    assert diff.allowance_id == "ALW-T-001"
    assert diff.allowance_reference == "anomalia APRESENTACAO_NUMERO_RELATORIO"
    assert report.allowances_used == ["ALW-T-001"]
    # sem a allowance, o hunk aprovado cobre também a identidade (diagnóstico redundante)
    by_hunk = compare(ref_with_anomaly, ref, report_number=14, approved_hunks=hunks)
    assert by_hunk.passed, by_hunk.reasons
    diff = by_hunk.find("report_number", scope="presentation")[0]
    assert diff.severity == ALLOWED and diff.allowance_id == "hunks:section:1"


def test_allowance_does_not_cover_a_different_wrong_value(ref_with_anomaly, workdir):
    gen = facts_of(synthetic_pages(presentation_number=15), workdir / "p15.pdf")
    report = compare(ref_with_anomaly, gen, frozen(PRESENTATION_ALLOWANCE), report_number=14)
    assert not report.passed
    assert report.find("report_number", scope="presentation")[0].severity == CRITICAL
    assert report.find("expected_report_number", scope="presentation")[0].severity == CRITICAL
    assert report.allowances_unused == ["ALW-T-001"]


def test_allowance_only_applies_to_its_report_number(ref, ref_with_anomaly):
    report = compare(ref_with_anomaly, ref, frozen(PRESENTATION_ALLOWANCE), report_number=13)
    assert report.find("report_number", scope="presentation")[0].severity == CRITICAL


def test_copying_the_anomaly_is_still_caught_by_the_expected_number(ref_with_anomaly):
    """Gerado que reproduz o "N° 13" histórico: igual à referência, mas errado."""
    report = compare(ref_with_anomaly, ref_with_anomaly, frozen(PRESENTATION_ALLOWANCE),
                     report_number=14)
    assert not report.passed
    assert report.find("expected_report_number", scope="presentation")[0].severity == CRITICAL


def test_pinned_sequence_allowance_is_exact(ref, workdir):
    pages = synthetic_pages()
    pages[6].items[2] = text("Relatórios semanais de cada obra: RD-103: RO-544.1 a RO-548.1; "
                             "RD-101: RO-543.1 a RO-547.1.")
    historical = facts_of(pages, workdir / "ro_hist.pdf")
    pin = allowance(
        reference={"anomaly": "P2.4_FAIXA_RO_SEMANA_REPETIDA"}, dimension="CONTENT",
        check="text_codes", scope="section:2.4.2",
        match={"reference_sequence": ["RO-544.1", "RO-548.1", "RO-543.1", "RO-547.1"],
               "generated_sequence": ["RO-545.1", "RO-548.1", "RO-544.1", "RO-547.1"]})
    hunks = approve_all(historical, ref, {"anomaly": "P2.4_FAIXA_RO_SEMANA_REPETIDA"})
    assert compare(historical, ref, frozen(pin), report_number=14, approved_hunks=hunks).passed

    other = clone(pages)
    other[6].items[2] = text("Relatórios semanais de cada obra: RD-103: RO-546.1 a RO-548.1; "
                             "RD-101: RO-544.1 a RO-547.1.")
    report = compare(historical, facts_of(other, workdir / "ro_other.pdf"), frozen(pin),
                     report_number=14, approved_hunks=hunks)
    assert not report.passed
    assert all(d.severity == CRITICAL for d in report.find("text_codes"))
    # o hunk da RD-103 (RO-546.1 em vez do aprovado RO-545.1) é novo e CRITICAL; o aprovado
    # da RD-103 fica órfão (aviso); o da RD-101 continua igual e ALLOWED
    assert sorted(d.severity for d in report.find("text_diff")) == [ALLOWED, CRITICAL]
    assert report.approved_hunks_orphans == ["HNK-14-001"]
    assert any("aprovação órfã: HNK-14-001" in w for w in report.warnings)


def test_dec_allowance_bounds_pagination_drift(ref, workdir):
    """DEC-010: até 2 páginas a mais pela paginação gulosa; 3 reprova."""
    dec = [
        allowance(id=f"ALW-T-{n}", reference={"dec": "DEC-010"}, dimension=dim, check=check,
                  scope=scope, match={"max_abs_delta": 2})
        for n, (dim, check, scope) in enumerate([
            ("STRUCTURAL", "page_count", "document"),
            ("CONTENT", "declared_pages", "closing"),
            ("STRUCTURAL", "orientation_run_length", "run:3"),
            ("STRUCTURAL", "heading_page", "document"),
        ])
    ]

    def with_extra_pages(k: int) -> dict:
        pages = synthetic_pages(declared_pages=9 + k)
        for _ in range(k):
            # Página de continuação sem texto novo (o texto acrescentado reprovaria pela
            # semelhança da narrativa, que a v2 conta).
            pages.insert(6, Page())
        return facts_of(pages, workdir / f"extra{k}.pdf")

    two_facts = with_extra_pages(2)
    # v4.0: "11 (onze) páginas" no Encerramento é texto: hunk aprovado pela mesma DEC
    hunks = approve_all(ref, two_facts, {"dec": "DEC-010"}, allowances=frozen(*dec))
    two = compare(ref, two_facts, frozen(*dec), report_number=14, approved_hunks=hunks)
    assert two.passed, two.reasons
    assert two.find("page_count")[0].severity == ALLOWED

    three = compare(ref, with_extra_pages(3), frozen(*dec), report_number=14,
                    approved_hunks=hunks)
    assert not three.passed
    assert three.find("page_count")[0].severity == MAJOR
    assert three.find("declared_pages")[0].severity == CRITICAL


def test_internal_consistency_is_never_allowed(ref, workdir):
    gen = gen_of(synthetic_pages(declared_pages=10), workdir, "incoh_pages")
    dec = allowance(reference={"dec": "DEC-010"}, dimension="CONTENT", check="declared_pages",
                    scope="closing", match={"max_abs_delta": 2})
    report = compare(ref, gen, frozen(dec), report_number=14)
    assert report.find("declared_pages")[0].severity == ALLOWED
    assert report.find("internal_consistency", scope="declared_pages")[0].severity == CRITICAL
    assert not report.passed


# --------------------------------------------------------------------------- validação


@pytest.mark.parametrize(("change", "message"), [
    ({"match": {}}, "match vazio"),
    ({"scope": "*"}, "genérico"),
    ({"scope": ["section:2.4.2", "section:*"]}, "genérico"),
    ({"reference": {"anomaly": "NAO_EXISTE"}}, "não catalogada"),
    ({"report_number": 13}, "não catalogada"),  # anomalia do nº 14 citada para o nº 13
    ({"reference": {"dec": "DEC-999"}}, "não existe"),
    ({"reference": {}}, "anomaly, dec ou anomaly"),
    ({"reference": {"anomaly": "APRESENTACAO_NUMERO_RELATORIO", "issue": "X"}},
     "anomaly, dec ou anomaly"),
    # v3.0: anomalia + DEC que decidiu — os dois precisam existir
    ({"reference": {"anomaly": "APRESENTACAO_NUMERO_RELATORIO", "dec": "DEC-999"}}, "não existe"),
    ({"reference": {"anomaly": "NAO_EXISTE", "dec": "DEC-010"}}, "não catalogada"),
    # v3.0: decisão pendente não é desvio permitido; se a DEC já decidiu, a flag sai
    ({"pending_decision": True}, "pending_decision — decisão pendente"),
    ({"pending_decision": True,
      "reference": {"anomaly": "APRESENTACAO_NUMERO_RELATORIO", "dec": "DEC-010"}},
     "cita DEC-010, que decidiu: remova pending_decision"),
    ({"check": "expected_report_number"}, "nunca é permitível"),
    ({"check": "internal_consistency", "dimension": "CONTENT"}, "nunca é permitível"),
    ({"dimension": "STRUCTURAL"}, "pertence a CONTENT"),
    ({"check": "qualquer_coisa"}, "check desconhecido"),
    ({"match": {"anything": 1}}, "desconhecidas"),
])
def test_invalid_allowances_are_rejected(change, message):
    raw = dict(PRESENTATION_ALLOWANCE)
    raw.update(change)
    with pytest.raises(AllowanceError, match=message):
        frozen(raw)


def test_allowances_must_be_frozen_and_for_this_comparator():
    with pytest.raises(AllowanceError, match="FROZEN"):
        parse_allowances({"status": "CANDIDATE", "comparator_version": "1.0"})
    with pytest.raises(AllowanceError, match="comparador"):
        parse_allowances({"status": "FROZEN", "comparator_version": "0.9"})
    with pytest.raises(AllowanceError, match="comparador"):
        parse_allowances({"status": "FROZEN", "comparator_version": "5.0"})
    # v4.x: registro de hunks aprovados só nas allowances do comparador atual (4.1: hunks
    # posicionais), sha256 de 64 hex; as da 4.0 (hunks sem posição) não registram hunks
    entry = {"report_number": 14, "file": "x.yaml", "sha256": "a" * 64}
    for old in ("3.0", "4.0"):
        with pytest.raises(AllowanceError, match=r"exige allowances do comparador 4\.1"):
            parse_allowances({"status": "FROZEN", "comparator_version": old,
                              "approved_hunks": [entry]})
    with pytest.raises(AllowanceError, match="64 hex"):
        parse_allowances({"status": "FROZEN", "comparator_version": COMPARATOR_VERSION,
                          "approved_hunks": [dict(entry, sha256="abc")]})
    with pytest.raises(AllowanceError, match="2x"):
        parse_allowances({"status": "FROZEN", "comparator_version": COMPARATOR_VERSION,
                          "approved_hunks": [entry, entry]})
    with pytest.raises(AllowanceError, match="repetido"):
        frozen(PRESENTATION_ALLOWANCE, PRESENTATION_ALLOWANCE)


@pytest.mark.parametrize("version", ["1.0", "2.0", "3.0", "4.0"])
def test_legacy_allowances_are_accepted_with_a_warning(ref, ref_with_anomaly, version):
    """v1.x/v2.x/v3.x/v4.0 continuam valendo para as verificações antigas; o relatório avisa
    que as verificações novas (v3: fatos ampliados, parágrafos, signatário, regiões; v4: diff
    de texto estrito; v4.1: âncora posicional) não estão cobertas — sem hunks aprovados, o
    texto diferente reprova."""
    assert COMPARATOR_VERSION == "4.1"
    legacy = parse_allowances({"status": "FROZEN", "comparator_version": version,
                               "allowances": [PRESENTATION_ALLOWANCE]})
    assert legacy.warnings and version in legacy.warnings[0] and "v4" in legacy.warnings[0]
    assert frozen().warnings == ()
    assert _blocking_checks(compare(ref_with_anomaly, ref, legacy, report_number=14)) == {
        "text_diff"}
    hunks = approve_all(ref_with_anomaly, ref, {"anomaly": "APRESENTACAO_NUMERO_RELATORIO"})
    report = compare(ref_with_anomaly, ref, legacy, report_number=14, approved_hunks=hunks)
    assert report.passed, report.reasons
    assert report.find("report_number", scope="presentation")[0].severity == ALLOWED
    assert report.warnings == list(legacy.warnings)
    assert "Aviso" in report.to_markdown()


def test_anomaly_decided_by_a_dec_is_one_reference_with_both_labels(ref, ref_with_anomaly):
    """v3.0: a allowance da anomalia já decidida cita a DEC (sem `pending_decision`)."""
    decided = dict(PRESENTATION_ALLOWANCE,
                   reference={"anomaly": "APRESENTACAO_NUMERO_RELATORIO", "dec": "DEC-007"})
    hunks = approve_all(ref_with_anomaly, ref, {"anomaly": "APRESENTACAO_NUMERO_RELATORIO",
                                                "dec": "DEC-007"})
    report = compare(ref_with_anomaly, ref, frozen(decided), report_number=14,
                     approved_hunks=hunks)
    assert report.passed, report.reasons
    diff = report.find("report_number", scope="presentation")[0]
    assert diff.allowance_reference == "anomalia APRESENTACAO_NUMERO_RELATORIO (DEC-007)"
    hunk = report.find("text_diff")[0]
    assert hunk.severity == ALLOWED
    assert hunk.allowance_reference == "anomalia APRESENTACAO_NUMERO_RELATORIO (DEC-007)"
    # `pending_decision: false` explícito não é recusado (não há decisão pendente)
    assert frozen(dict(decided, pending_decision=False)).allowances


def test_vertical_delta_of_a_geometry_allowance_is_pinned():
    """v3.0: `max_vertical_delta_cm` prende o desvio vertical de uma allowance de geometria."""
    from prog_g2_report.qa.compare import VISUAL_GEOMETRY, Difference

    alw = frozen(allowance(reference={"dec": "DEC-010"}, dimension="VISUAL_GEOMETRY",
                           check="figure_bbox", scope="anchor:2.4.2",
                           match={"figure_kind": "vector", "max_width_delta_cm": 0.5,
                                  "max_vertical_delta_cm": 2.0})).allowances[0]

    def bbox_diff(horizontal: float, vertical: float) -> Difference:
        return Difference(VISUAL_GEOMETRY, "figure_bbox", "anchor:2.4.2", MINOR, "x",
                          context={"figure_kind": "vector", "horizontal_delta_cm": horizontal,
                                   "vertical_delta_cm": vertical})

    assert alw.matches(bbox_diff(0.1, 1.9), 14)
    assert not alw.matches(bbox_diff(0.1, 2.1), 14)        # desceu demais: volta a MINOR
    assert not alw.matches(bbox_diff(0.6, 0.1), 14)        # horizontal continua preso
    assert not alw.matches(Difference(VISUAL_GEOMETRY, "figure_bbox", "anchor:2.4.2", MINOR,
                                      "x", context={"figure_kind": "vector",
                                                    "horizontal_delta_cm": 0.1}), 14)




def test_v17_geometry_allowances_of_n14_pin_the_vertical_deviation():
    """v1.7: toda allowance de `figure_bbox` do nº 14 prende o desvio vertical (medido no 14_mm3
    + 0,5 cm) e, salvo a dos dois recortes encolhidos à mão (valores exatos), o horizontal."""
    import yaml

    raw = yaml.safe_load((ROOT / "config" / "golden_allowances.yaml").read_text(encoding="utf-8"))
    bbox = {a["id"]: a["match"] for a in raw["allowances"]
            if a["report_number"] == 14 and a["check"] == "figure_bbox"}
    assert set(bbox) == {"ALW-14-010", "ALW-14-016", "ALW-14-017", "ALW-14-018", "ALW-14-028"}
    for aid, m in bbox.items():
        assert 0 < m["max_vertical_delta_cm"] <= 15, aid
        assert m.get("max_width_delta_cm") == 0.5 or m.get("values"), aid
    assert bbox["ALW-14-010"]["max_vertical_delta_cm"] < bbox["ALW-14-028"]["max_vertical_delta_cm"]



def test_items_and_pairs_cover_each_difference_once(ref_status, workdir):
    """`items` (um item = uma diferença) e `pairs` (o que falta e o que sobra no mesmo bloco
    e campo, emparelhados): exatos e consumidos no uso."""
    flip = _status_variant("Análise Programa: Não aprovado;", "Análise Programa: Em análise;")
    gen = gen_of(pages_with_paragraphs(flip), workdir, "pair_flip")
    prog = {"block": "RD-101#1", "reference": "status:NAO_APROVADO@ANALISE PROGRAMA",
            "generated": "status:EM_ANALISE@ANALISE PROGRAMA"}
    pair = allowance(reference={"dec": "DEC-007"}, dimension="CONTENT", check="narrative_facts",
                     scope="section:2.4.2", match={"pairs": [prog]})
    # v4.0: o texto trocado é hunk; aprovado (DEC-007), a allowance cobre os fatos (sem os
    # hunks, as verificações abaixo olham a allowance sozinha)
    hunks = approve_all(ref_status, gen, {"dec": "DEC-007"})
    report = compare(ref_status, gen, frozen(pair), report_number=14, approved_hunks=hunks)
    assert report.passed, report.reasons
    assert {d.context["paired_with"] for d in report.find("narrative_facts")} == {
        prog["reference"], prog["generated"]}
    assert {d.allowance_id for d in report.find("narrative_facts")} == {"ALW-T-001"}
    # par no bloco errado, ou só um lado como item: não cobre
    wrong = dict(prog, block="RD-103#1")
    report = compare(ref_status, gen, frozen(dict(pair, match={"pairs": [wrong]})),
                     report_number=14)
    assert {d.severity for d in report.find("narrative_facts")} == {CRITICAL}
    one_side = dict(pair, match={"items": [{"kind": "missing", "block": "RD-101#1",
                                            "value": prog["reference"]}]})
    report = compare(ref_status, gen, frozen(one_side), report_number=14)
    assert [d.severity for d in report.find("narrative_facts")] == [ALLOWED, CRITICAL]
    # item consumido: a mesma diferença duas vezes não passa com um item só
    twice = [p.replace("oito licenças", "nove licenças").replace("nas quatro", "nas nove")
             for p in STATUS_TEXT]
    item = allowance(reference={"dec": "DEC-007"}, dimension="CONTENT", check="narrative_facts",
                     scope="section:2.4.2", match={"items": [
                         {"kind": "extra", "block": "", "value": "number:9"},
                         {"kind": "missing", "block": "", "value": "number:8"}]})
    report = compare(ref_status, gen_of(pages_with_paragraphs(twice), workdir, "item_twice"),
                     frozen(item), report_number=14)
    severities = sorted((d.kind, d.value, d.severity) for d in report.find("narrative_facts"))
    assert ("extra", "number:9", CRITICAL) in severities
    assert ("extra", "number:9", ALLOWED) in severities
    assert not report.passed


def test_items_allowance_is_all_or_nothing(ref_status, workdir):
    """A lista de itens é o conjunto EXATO de diferenças que a anomalia explica. Usada em parte
    (um dos fatos esperados sumiu do gerado — o QA-E "07, 08 e 09" -> "06, 07 e 08" passava
    assim) = CRITICAL não permitível; sem uso nenhum = nada a dizer."""
    two = [p.replace("oito licenças", "nove licenças").replace("nas quatro", "nas cinco")
           for p in STATUS_TEXT]
    items = [{"kind": "extra", "block": "", "value": "number:9"},
             {"kind": "missing", "block": "", "value": "number:8"},
             {"kind": "extra", "block": "", "value": "number:5"},
             {"kind": "missing", "block": "", "value": "number:4"}]
    alw = allowance(reference={"dec": "DEC-007"}, dimension="CONTENT", check="narrative_facts",
                    scope="section:2.4.2", match={"items": items})
    two_facts = gen_of(pages_with_paragraphs(two), workdir, "items_full")
    full = compare(ref_status, two_facts, frozen(alw), report_number=14,
                   approved_hunks=approve_all(ref_status, two_facts, {"dec": "DEC-007"}))
    assert full.passed, full.reasons
    assert {d.allowance_id for d in full.find("narrative_facts")} == {"ALW-T-001"}

    one = [p.replace("oito licenças", "nove licenças") for p in STATUS_TEXT]
    one_facts = gen_of(pages_with_paragraphs(one), workdir, "items_part")
    # mesmo com o texto aprovado por hunk, a allowance usada em parte é CRITICAL (não é
    # coberta pelos hunks)
    part = compare(ref_status, one_facts, frozen(alw), report_number=14,
                   approved_hunks=approve_all(ref_status, one_facts, {"dec": "DEC-007"}))
    hit = part.find("narrative_facts", kind="incomplete")
    assert [(d.value, d.severity, d.reference, d.generated) for d in hit] == [
        ("ALW-T-001", CRITICAL, 4, 2)]
    assert "number:5" in hit[0].message and not part.passed

    none = compare(ref_status, ref_status, frozen(alw), report_number=14)
    assert none.passed and none.allowances_unused == ["ALW-T-001"]


@pytest.mark.parametrize(("match", "message"), [
    ({"items": []}, "lista não vazia"),
    ({"items": [{"kind": "missing", "value": "x"}]}, "lista não vazia"),
    ({"items": [{"kind": "moved", "block": "", "value": "x"}]}, "items.kind"),
    ({"pairs": [{"block": "", "reference": "a"}]}, "lista não vazia"),
])
def test_invalid_items_and_pairs_are_rejected(match, message):
    raw = allowance(reference={"dec": "DEC-007"}, dimension="CONTENT", check="narrative_facts",
                    scope="section:2.4.2", match=match)
    with pytest.raises(AllowanceError, match=message):
        frozen(raw)
    with pytest.raises(AllowanceError, match="só narrative_facts"):
        frozen(dict(PRESENTATION_ALLOWANCE,
                    match={"items": [{"kind": "missing", "block": "", "value": "x"}]}))





def test_v18_fact_moved_to_another_road_block_is_missing_plus_extra_not_order():
    """v1.8: `order` só para o fato deslocado DENTRO do mesmo bloco. O "aprovados" a mais da
    RD-104 não "cancela" o "aprovados" a menos da RD-101 (o nº 14 juntava os dois numa
    diferença `order` de outra rodovia); falta e sobra no mesmo bloco e campo viram par."""
    a, r = "status:APROVADO@APROVACAO", "status:APROVADO_COM_RESSALVA@APROVACAO"
    ref = {"facts": ["road:RD-101", a, a, "number:11", "road:RD-104", "number:12", r,
                     "road:RD-103", "number:5", "number:2"],
           "fact_blocks": ["RD-101#1"] * 4 + ["RD-104#1"] * 3 + ["RD-103#1"] * 3}
    gen = {"facts": ["road:RD-101", a, "number:11", "road:RD-104", "number:12", a,
                     "road:RD-103", "number:2", "number:5"],
           "fact_blocks": ["RD-101#1"] * 3 + ["RD-104#1"] * 3 + ["RD-103#1"] * 3}
    comparator = Comparator({}, {}, frozen(), report_number=None)
    comparator.facts_unit("section:2.2.2", ref, gen, "fatos")
    got = {(d.kind, d.value, d.context["block"], d.context.get("paired_with"))
           for d in comparator.units[0].diffs}
    moved = {g for g in got if g[0] == "order"}
    assert got - moved == {("missing", a, "RD-101#1", None), ("missing", r, "RD-104#1", a),
                           ("extra", a, "RD-104#1", r)}
    # dentro do mesmo bloco a troca de posição continua `order`
    assert len(moved) == 1 and next(iter(moved))[2] == "RD-103#1"



# --------------------------------------------------------------------------- utilidades e saída


def _vec(page: int, x1: float, y0: float, y1: float) -> dict:
    return {"page": page, "bbox_cm": [2.0, y0, x1, y1], "width_cm": round(x1 - 2.0, 2),
            "height_cm": y1 - y0}


def test_vector_figures_pair_by_page_union_not_global_order():
    """nº 13: um recorte vira 1 a 5 agrupamentos (faixa de título com setas, 18,64 cm; corpo,
    17,50 cm) conforme o conteúdo. Pela ordem global o 2º agrupamento da referência (corpo)
    cruzava com uma faixa do gerado (Δ 1,14 cm) e pedia allowance frouxa de ±1,15 cm."""
    title, body = 20.64, 19.51
    reference = [_vec(31, title, 2.19, 4.22), _vec(31, body, 5.0, 12.0),
                 _vec(32, title, 2.19, 4.22), _vec(32, body, 7.0, 20.0)]
    generated = [_vec(30, title, 2.19, 10.75),
                 _vec(31, title, 2.19, 6.18), _vec(31, body, 8.0, 10.0), _vec(31, body, 12.0, 25.0),
                 _vec(32, title, 2.19, 4.22)]
    by_order = list(zip(reference, generated, strict=False))
    assert max(abs(r["width_cm"] - g["width_cm"]) for r, g in by_order) == pytest.approx(1.13)

    pairs = Comparator.figure_pairs(reference, generated, "vector")
    assert [(n, r["page"], g["page"]) for n, r, g in pairs] == [(1, 31, 30), (3, 32, 31)]
    assert all(abs(r["width_cm"] - g["width_cm"]) < 0.01 for _, r, g in pairs)
    assert [r["fragments"] for _, r, _ in pairs] == [2, 2]
    # Raster continua pela ordem na âncora (um painel por posição).
    assert [n for n, _, _ in Comparator.figure_pairs(reference, generated, "raster")] == [
        1, 2, 3, 4]


def test_sequence_diff_classifies_missing_extra_and_moves():
    assert sequence_diff(["A", "B", "C"], ["A", "B", "C"]) == ([], [], [], 3)
    assert sequence_diff(["A", "B", "C"], ["A", "C"])[:3] == (["B"], [], [])
    assert sequence_diff(["A", "B"], ["A", "B", "B"])[:3] == ([], ["B"], [])
    missing, extra, moved, _ = sequence_diff(["A", "B", "C"], ["A", "C", "B"])
    assert (missing, extra, moved) == ([], [], ["B"]) or (missing, extra, moved) == ([], [], ["C"])


@pytest.mark.parametrize(("n", "feminine", "words"), [
    (3, False, "três"), (43, True, "quarenta e três"), (42, True, "quarenta e duas"),
    (21, True, "vinte e uma"), (100, False, "cem"), (149, False, "cento e quarenta e nove"),
    (165, False, "cento e sessenta e cinco"), (200, True, "duzentas"), (1001, False, "mil e um"),
    (1250, False, "mil duzentos e cinquenta"),
])
def test_number_to_words_pt(n, feminine, words):
    assert number_to_words_pt(n, feminine=feminine) == words


def test_report_serializes_and_renders_diagnostics(ref, workdir):
    pages = synthetic_pages()
    pages[4].orientation = "portrait"
    report = compare(ref, gen_of(pages, workdir, "md"), report_number=14)
    data = json.loads(json.dumps(report.to_dict(), ensure_ascii=False))
    assert data["verdict"] == "FAIL" and data["metrics"]["severity_counts"]["CRITICAL"] >= 1
    md = report.to_markdown()
    assert "**Veredito: FAIL**" in md and "orientation_runs" in md and "## CRITICAL" in md


def _load_cli():
    path = ROOT / "scripts" / "14_golden_compare.py"
    spec = importlib.util.spec_from_file_location("golden_compare_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_writes_json_and_markdown_and_returns_verdict(tmp_path):
    cli = _load_cli()
    allow = tmp_path / "allow.yaml"
    allow.write_text("status: FROZEN\ncomparator_version: '1.0'\nallowances: []\n",
                     encoding="utf-8")
    reference = write_pdf(synthetic_pages(), tmp_path / "ref.pdf")
    same = write_pdf(synthetic_pages(), tmp_path / "same.pdf")
    broken_pages = synthetic_pages()
    broken_pages[4].orientation = "portrait"
    broken = write_pdf(broken_pages, tmp_path / "broken.pdf")

    common = ["--reference", str(reference), "--report-number", "14",
              "--allowances", str(allow)]
    assert cli.main([*common, "--generated", str(same), "--out", str(tmp_path / "ok.json"),
                     "--facts-dir", str(tmp_path / "facts")]) == 0
    assert json.loads((tmp_path / "ok.json").read_text(encoding="utf-8"))["verdict"] == "PASS"
    assert (tmp_path / "ok.md").exists()
    assert (tmp_path / "facts" / "reference_facts_14.json").exists()
    assert cli.main([*common, "--generated", str(broken), "--out", str(tmp_path / "ko")]) == 1
    assert json.loads((tmp_path / "ko.json").read_text(encoding="utf-8"))["verdict"] == "FAIL"

    allow.write_text("status: CANDIDATE\ncomparator_version: '1.0'\n", encoding="utf-8")
    assert cli.main([*common, "--generated", str(same), "--out", str(tmp_path / "x")]) == 2
