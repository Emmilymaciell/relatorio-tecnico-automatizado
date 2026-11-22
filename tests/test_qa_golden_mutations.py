"""Golden adversarial (QA-E e QA2-E, Gate D): mutações no PDF GERADO do Relatório G2 nº 14
que o comparador aprovava têm de reprovar — v1 -> v2 (QA-E) e v2 -> v3 (QA2-E, 19 mutações de
conteúdo: status por extenso, cardinais, negação, executora, dia, signatário, parágrafo e
painéis raster).

Só roda com `-m golden` e com os dois PDFs em disco (nunca versionados):
  - referência: `tmp/downloads/relatorios_11_14/...n°14 - 08 2026.pdf` (ou PROG_G2_REFERENCE_DIR)
  - gerado: `output/reconstruction/14_v6/relatorio_g2_n14_2026-08.pdf` (ou
    PROG_G2_GENERATED_14_PDF; controle das allowances v1.9 e dos hunks aprovados n14.yaml,
    modelo v0.14, comparador 4.1), procurado neste checkout, no principal e nos worktrees irmãos.
v4.0: além da verificação v2/v3 que pegou cada mutação, a de texto tem de criar hunk
`text_diff` novo; o catálogo completo das três rodadas está em tests/test_qa_golden_v4.py.
Cada mutação é aplicada a uma cópia no diretório temporário do pytest; o PDF original só é lido.
Mutações "de fatos" (parágrafo duplicado/apagado/trocado) editam os segmentos da seção extraída
do gerado e recalculam os derivados com o MESMO código do extrator (`finish_section`):
equivalem a um PDF com esse texto, sem artefato de redação.

Prova de que o teste pega a regressão: o controle (gerado sem mutação) passa sem nenhuma
CRITICAL/MAJOR; cada mutação cria diferença bloqueante NOVA, na verificação que a v3 acrescentou
(QA2-E mostrou que a v2 aprovava todas: tmp/agent_QAE2/res_*.json). As mutações reproduzem
`tmp/agent_QAE2/mutations.py`, localizando o alvo pelo texto e pelos fatos do controle.
"""

from __future__ import annotations

import copy
import io
import os
import shutil
from pathlib import Path

import pytest

pymupdf = pytest.importorskip("pymupdf")
pytest.importorskip("numpy")

from prog_g2_report.qa.compare import (  # noqa: E402
    CRITICAL,
    MAJOR,
    compare,
    load_allowances,
    number_to_words_pt,
)
from prog_g2_report.qa.extract import (  # noqa: E402
    PT_PER_CM,
    SIGNATORY_RE,
    extract_facts,
    finish_section,
    section_masks,
)
from prog_g2_report.report_id import parse_report_filename  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# Controle do nº 14 (orquestrador, allowances v1.8): o build do RR (14_final: main com QQ, NN,
# OO e MM; projetos v438 em memória). 14_mm3/14_v4 são anteriores à Análise Programa derivada (QQ)
# e ao P2.4_ATAS condicionado (NN): com a v1.8 deixam allowances sem uso e "a mais".
GENERATED_BUILDS = ("14_v6",)
GENERATED_FILE = "relatorio_g2_n14_2026-08.pdf"

# Verificações novas da v2: toda diferença criada por uma mutação do QA-E tem de vir daqui
# (as do v1 não viam nada disso) ou das que a v3 acrescentou.
V2_CHECKS = frozenset({"product_control_rows", "section_presence", "narrative_facts",
                       "narrative_coverage", "narrative_similarity", "figure_content",
                       "figure_identity"})
V3_CHECKS = frozenset({"paragraph_coverage", "paragraph_duplicate", "signatory",
                       "figure_region"})

# Diferenças REAIS do gerado contra o nº 14 publicado: anomalias catalogadas do publicado que o
# builder corrige e o texto padronizado da DEC-007. Saem ALLOWED (allowances v1.7, itens
# de fatos pinadas). Não são falsos positivos.
#   2.1.2  P2.4_FRASE_TRUNCADA_MEDICOES: publicado "Na RD-101." órfã; gerado completa a frase
#          ("Na RD-104, foram avaliados os Boletins de Medição 07, 08 e 09, referentes aos meses
#          de abril/2026, maio/2026 e junho/2026").
#   2.1.2  P2.1_IDENTIFICACAO_RODOVIA + DEC-007: "RD-102" na agenda; gerado normaliza RD-102A.
#   2.4.2  P2.4_FAIXA_RO_SEMANA_REPETIDA: período "a partir de 25/07/2026" copiado do nº 13;
#          gerado segue a Lista Mestra (01/08/2026).
#   2.4.2  P2.4_RELATORIO_CONSOLIDADO_GRAFIA (v3): frase truncada completada ("a situação das
#          não conformidades...").
#   2.2.2  P2.2_DUP_PARENTESE, P2.2_DUP_RD101_SEM_VALOR e DEC-007 (v3): predicado repetido no
#          publicado, sentinela "Sem informação..." e forma padronizada ("em 1º nível",
#          "encontram-se em análise").
#   2.2.2  v1.8 (extrator 3.1): P2.2_EXTERNAL_PROG_CONTRADIZ_PLANILHA (Análise Programa da planilha,
#          3 pares), P2.2_APROVADOS_COM_RESSALVA_GENERALIZADO (RD-104 Principal "com ressalva"),
#          P2.2_PAVIMENTACAO_RD101_STATUS_DEFASADO (texto da v436: Pavimentação da RD-101 de
#          pendente para em análise) e P2.2_OAE_RD101_ACEITO_INCOMPLETO (Memoriais aceitos).
KNOWN_REAL_DIFFERENCES = frozenset(
    {("narrative_facts", "section:2.1.2", v) for v in (
        "road:RD-102", "road:RD-101", "road:RD-102A", "road:RD-104", "number:07", "number:08",
        "number:09", "month:2026-04", "month:2026-05", "month:2026-06")}
    | {("narrative_facts", "section:2.4.2", v) for v in ("date:25/07/2026", "date:01/08/2026",
                                                         "neg:NAO")}
    | {("narrative_facts", "section:2.2.2", v) for v in (
        "status:APROVADO@APROVACAO", "neg:SEM@PUBLICACAO PELA CASA CIVIL", "ordinal:1",
        "status:EM_ANALISE@DISCIPLINAS EM ANALISE", "status:NAO_APROVADO@ANALISE PROGRAMA",
        "status:EM_ANALISE@ANALISE PROGRAMA", "status:APROVADO_COM_RESSALVA@APROVACAO",
        "discipline:PAVIMENTACAO@DISCIPLINAS PENDENTES DE APROVACAO",
        "discipline:PAVIMENTACAO@DISCIPLINAS EM ANALISE",
        "discipline:MEMORIAIS_ESTRUTURAL@ACEITACAO")}
)


# --------------------------------------------------------------------------- localização


def _main_checkout() -> Path | None:
    parts = ROOT.parts
    for i in range(len(parts) - 1):
        if parts[i] == ".claude" and parts[i + 1] == "worktrees":
            return Path(*parts[:i])
    return None


def _reference_pdf() -> Path | None:
    dirs = [Path(d) for d in [os.environ.get("PROG_G2_REFERENCE_DIR")] if d]
    dirs.append(ROOT / "tmp" / "downloads" / "relatorios_11_14")
    if _main_checkout():
        dirs.append(_main_checkout() / "tmp" / "downloads" / "relatorios_11_14")
    for d in dirs:
        for pdf in sorted(d.glob("*.pdf")) if d.is_dir() else []:
            ref = parse_report_filename(pdf.name)
            if ref and ref.report_number == 14:
                return pdf
    return None


def _generated_pdf() -> Path | None:
    """PROG_G2_GENERATED_14_PDF; senão o build mais recente da lista em output/reconstruction
    deste checkout, do principal ou de um worktree irmão (o do builder que o produziu)."""
    candidates = [Path(p) for p in [os.environ.get("PROG_G2_GENERATED_14_PDF")] if p]
    bases = [ROOT]
    main = _main_checkout()
    if main:
        bases.append(main)
        worktrees = main / ".claude" / "worktrees"
        bases += sorted(worktrees.iterdir()) if worktrees.is_dir() else []
    for build in GENERATED_BUILDS:
        candidates += [base / "output" / "reconstruction" / build / GENERATED_FILE
                       for base in bases]
    return next((p for p in candidates if p.is_file()), None)


def _key(diff) -> tuple:
    return (diff.check, diff.scope, diff.kind, str(diff.value), str(diff.reference),
            str(diff.generated))


def _blocking(report) -> dict[tuple, object]:
    return {_key(d): d for d in report.differences if d.severity in (CRITICAL, MAJOR)}


class Golden:
    def __init__(self, reference: Path, generated: Path):
        self.generated = generated
        self.allowances = load_allowances()
        self.hunks = self.allowances.approved_hunks(14)
        self.ref = extract_facts(reference)
        self.gen = extract_facts(generated)
        self.control = compare(self.ref, self.gen, self.allowances, report_number=14)
        self.control_blocking = _blocking(self.control)

    # -- alvos pelos fatos do controle ------------------------------------------------------

    def section_of_page(self, page_no: int) -> str | None:
        current = None
        for h in self.gen["headings"]:
            if h["page"] <= page_no:
                current = h["key"]
        return current

    def text_only_pages(self, section: str) -> list[int]:
        crop_pages = {c["page"] for c in self.gen["product_control"]["crops"]}
        return [p["index"] for p in self.gen["pages"]
                if not p["figures"] and not p["heading_keys"] and p["index"] not in crop_pages
                and self.section_of_page(p["index"]) == section]

    def rasters(self, anchor: str) -> list[tuple[int, tuple[float, ...]]]:
        return [(p["index"], tuple(v * PT_PER_CM for v in f["bbox_cm"]))
                for p in self.gen["pages"] for f in p["figures"]
                if f["kind"] == "raster" and f["anchor"] == anchor]

    def first_crop(self, block: str) -> tuple[int, dict]:
        page = next(c["page"] for c in self.gen["product_control"]["crops"]
                    if c["block"] == block)
        first = next(r for r in self.gen["product_control"]["rows"][block] if r["page"] == page)
        return page, first

    # -- execução ---------------------------------------------------------------------------

    def run(self, tmp_path: Path, mutate, *, deleted_page: bool = False):
        work = tmp_path / "mutado.pdf"
        shutil.copy(self.generated, work)
        doc = pymupdf.open(work)
        mutate(doc)
        out = tmp_path / "mutado_salvo.pdf"
        doc.save(out, garbage=3)
        doc.close()
        facts = extract_facts(out)
        if deleted_page:
            # Total coerente (como o QA-E fez no texto): numeração impressa refeita e
            # Encerramento declarando as páginas que o PDF tem.
            for page in facts["pages"]:
                if page["printed_page_number"] == page["index"] + 1:
                    page["printed_page_number"] = page["index"]
            n = facts["page_count"]
            facts["identity"]["closing"]["declared_pages"] = {
                "value": n, "words": number_to_words_pt(n, feminine=True)}
        report = compare(self.ref, facts, self.allowances, report_number=14)
        new = [d for k, d in _blocking(report).items() if k not in self.control_blocking]
        return report, new

    def run_segments(self, key: str, mutate):
        """Mutação no texto de uma seção do gerado (segmentos), derivados recalculados pelo
        extrator."""
        gen = copy.deepcopy(self.gen)
        section = gen["sections"][key]
        mutate(section["segments"])
        finish_section(section, section_masks(key, section["title"]))
        report = compare(self.ref, gen, self.allowances, report_number=14)
        new = [d for k, d in _blocking(report).items() if k not in self.control_blocking]
        return report, new


@pytest.fixture(scope="module")
def golden(request) -> Golden:
    if "golden" not in (request.config.getoption("-m") or ""):
        pytest.skip("teste do PDF real: rodar com -m golden")
    reference, generated = _reference_pdf(), _generated_pdf()
    if reference is None or generated is None:
        pytest.skip("PDF de referência ou gerado do Relatório G2 nº 14 indisponível")
    return Golden(reference, generated)


# --------------------------------------------------------------------------- mutações


def replace_text(doc, old: str, new: str, max_hits: int = 1, page_no: int | None = None) -> int:
    """QA-E `replace_text`: redige `old` e escreve `new` no mesmo lugar."""
    hits = 0
    pages = range(len(doc)) if page_no is None else [page_no - 1]
    for i in pages:
        page = doc[i]
        spans = [s for b in page.get_text("dict")["blocks"] for ln in b.get("lines", [])
                 for s in ln["spans"] if old in s["text"]]
        for span in spans:
            if hits >= max_hits:
                break
            rects = page.search_for(old, clip=pymupdf.Rect(span["bbox"]))
            if not rects:
                continue
            page.add_redact_annot(rects[0], text=new, fontsize=span["size"] * 0.95,
                                  fontname="helv", align=pymupdf.TEXT_ALIGN_LEFT)
            hits += 1
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        if hits >= max_hits:
            break
    return hits


def _xref_at(doc, page_no: int, bbox: tuple[float, ...]) -> int:
    page = doc[page_no - 1]
    infos = page.get_image_info(xrefs=True)
    best = min(infos, key=lambda i: sum(abs(a - b) for a, b in zip(i["bbox"], bbox,
                                                                    strict=True)))
    return best["xref"]


def blank_image(page_no: int, bbox: tuple[float, ...]):
    def mutate(doc):
        xref = _xref_at(doc, page_no, bbox)
        original = pymupdf.Pixmap(doc, xref)
        white = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, original.width,
                                                           original.height), False)
        white.clear_with(255)
        doc[page_no - 1].replace_image(xref, pixmap=white)
    return mutate


def swap_images(first: tuple[int, tuple], second: tuple[int, tuple]):
    def mutate(doc):
        xa, xb = _xref_at(doc, *first), _xref_at(doc, *second)
        pa, pb = pymupdf.Pixmap(doc, xa), pymupdf.Pixmap(doc, xb)
        doc[first[0] - 1].replace_image(xa, pixmap=pb)
        doc[second[0] - 1].replace_image(xb, pixmap=pa)
    return mutate


def wipe_body(page_no: int):
    def mutate(doc):
        page = doc[page_no - 1]
        r = page.rect
        page.add_redact_annot(pymupdf.Rect(r.x0, r.y0 + 60, r.x1, r.y1 - 40))
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
    return mutate


def delete_page(page_no: int):
    def mutate(doc):
        doc.delete_page(page_no - 1)
    return mutate


def substitute(old: str, new: str, max_hits: int = 1, page_no: int | None = None):
    def mutate(doc):
        if replace_text(doc, old, new, max_hits, page_no) == 0:
            pytest.skip(f"texto-alvo {old!r} ausente no gerado atual")
    return mutate


def _assert_new_v2_failure(report, new, checks: set[str], scope: str | None = None, *,
                           text: bool = True) -> None:
    """Reprova com diferença bloqueante NOVA na verificação da v2/v3 que a pegou e, se a
    mutação mexe em texto, também com hunk `text_diff` novo (v4.0). Desde a v4 as diferenças
    v1 de uma unidade de texto ficam cobertas pelos hunks aprovados enquanto o texto é o
    aprovado: a mutação as reabre, e por isso elas podem aparecer entre as novas."""
    assert not report.passed
    assert new, "a mutação não criou diferença bloqueante nova"
    found = {d.check for d in new}
    assert found & checks, [(d.check, d.scope, d.message) for d in new]
    if scope is not None:
        assert any(d.scope == scope for d in new if d.check in checks)
    if text:
        assert "text_diff" in found, sorted(found)


# --------------------------------------------------------------------------- controle


@pytest.mark.golden
def test_golden_control_has_only_the_known_real_differences(golden):
    """Gerado do main sem mutação (14_v6, DEC-015): PASS no comparador 4.0 — todo trecho de
    texto divergente é um hunk APROVADO (docs/qa/approved_hunks/n14.yaml, anomalia ou DEC),
    nenhum órfão, nenhuma CRITICAL/MAJOR; as diferenças v3 (fatos, linhas do Controle de
    Produtos) saem ALLOWED pelos hunks da sua unidade, e as conhecidas do v3 são as listadas."""
    report = golden.control
    unexpected = [(d.check, d.scope, d.value, d.message) for d in report.differences
                  if d.severity in (CRITICAL, MAJOR)]
    assert unexpected == []
    assert report.passed, report.reasons
    td = report.metrics["text_diff"]
    assert td["hunks"] == td["approved"] == len(golden.hunks.hunks) and td["orphans"] == []
    assert td["unapproved"] == td["pending"] == 0
    assert report.approved_hunks_sha256 == golden.hunks.sha256
    # seletor de rodovia legível e igual nos 4 painéis de condicionantes (sem isso o teste de
    # troca p30 <-> p31 seria vazio); nenhum painel em região acima do limite
    selector = report.metrics["figures"]["selector"]
    assert [selector[f"2.4.2#{n}"] for n in range(2, 6)] == [[1, 1], [2, 2], [3, 3], [4, 4]]
    assert report.find("figure_region") == []
    # Linhas divergentes só a do NT-734.1 (cortado no publicado; o gerado com altura
    # max(27,6 pt, AutoFit), DEC-010 §4): ALLOWED pelo hunk exato do bloco.
    allowed_rows: dict[str, int] = {}
    for d in report.differences:
        if d.check == "product_control_rows" and d.severity == "ALLOWED":
            assert d.value == "NT-734.1#2" and d.allowance_id == f"hunks:{d.scope}", d.message
            block = d.scope.split(":", 1)[1]
            allowed_rows[block] = allowed_rows.get(block, 0) + 1
    assert allowed_rows == {"2.2": 1, "ANEXOS": 1}
    for block, metrics in report.metrics["product_control"].items():
        assert metrics["rows_equal"] + allowed_rows.get(block, 0) == metrics["reference"] \
            == metrics["generated"], block
    figures = report.metrics["figures"]
    assert figures["blank"] == 0 and figures["identity_swapped"] == 0
    # O selo é verificável nos 4 quadros do 2.2.2 (sem isso o teste de troca seria vazio).
    scores = figures["label_scores"]
    assert all(max(s for s in scores[f"2.2.2#{n}"] if s is not None)
               == scores[f"2.2.2#{n}"][n - 1] for n in range(1, 5))
    # allowances v1.9 congeladas para o comparador 4.0: sem aviso; os fatos v3 conhecidos
    # (anomalias corrigidas e DEC-007/DEC-015) saem ALLOWED pelos hunks da unidade
    assert not report.warnings
    allowed = {(d.check, d.scope, str(d.value)) for d in report.differences
               if d.severity == "ALLOWED" and d.check == "narrative_facts"}
    assert allowed >= KNOWN_REAL_DIFFERENCES
    assert all(d.allowance_id.startswith("hunks:") for d in report.differences
               if d.severity == "ALLOWED" and d.check == "narrative_facts")


@pytest.mark.golden
def test_golden_reference_against_itself_has_no_difference(golden):
    report = compare(golden.ref, golden.ref, golden.allowances, report_number=None)
    assert report.passed, report.reasons
    assert report.differences == []


# --------------------------------------------------------------------------- páginas e texto


@pytest.mark.golden
@pytest.mark.parametrize(("section", "position"), [
    ("2.1.2", -1),  # QA-E: página 15 (último texto do 2.1.2 antes do Controle de Produtos)
    ("2.2.2", 0),   # página 22
    ("2.2.2", 1),   # página 23
    ("2.2.2", 2),   # página 24 (só ~85 palavras: pega pela maior lacuna)
])
def test_golden_text_page_removed_with_coherent_total_fails(golden, tmp_path, section, position):
    pages = golden.text_only_pages(section)
    if len(pages) <= abs(position) - (position < 0):
        pytest.skip(f"gerado atual sem a página de texto {position} do {section}")
    page_no = pages[position]
    report, new = golden.run(tmp_path, delete_page(page_no), deleted_page=True)
    if golden.gen["page_count"] - 1 == golden.ref["page_count"]:
        # Cenário do QA-E: gerado com 1 página a mais, que a deleção iguala à referência (o v1
        # não via nada no total de páginas).
        assert report.find("page_count") == [] or all(
            d.severity == "ALLOWED" for d in report.find("page_count"))
    else:
        # Gerado com o total da referência (14_v3/14_v4: 43 = 43): a deleção muda o total, o
        # total declarado e o bloco retrato do Controle de Produtos, e desde as allowances v1.5
        # (ALW-14-005/-006/-007 removidas) o v1 já acusa isso. A prova continua sendo a falha
        # NOVA da v2 (cobertura da seção), sem nenhuma outra verificação do v1 além dessas.
        v1_page_checks = {"page_count", "declared_pages", "orientation_run_length"}
        new = [d for d in new if d.check not in v1_page_checks]
    _assert_new_v2_failure(report, new, {"narrative_coverage"}, f"section:{section}")


@pytest.mark.golden
def test_golden_text_page_body_wiped_fails(golden, tmp_path):
    page_no = golden.text_only_pages("2.2.2")[0]  # QA-E: corpo da página 22 apagado
    report, new = golden.run(tmp_path, wipe_body(page_no))
    _assert_new_v2_failure(report, new, {"narrative_coverage"}, "section:2.2.2")


# --------------------------------------------------------------------------- Controle de Produtos


def _other_month(date: str) -> str:
    day, month, year = date.split("/")
    return f"{day}/{(int(month) - 2) % 12 + 1:02d}/{year}"


@pytest.mark.golden
@pytest.mark.parametrize("field", ["date", "status", "road", "description"])
def test_golden_product_control_cell_mutation_fails(golden, tmp_path, field):
    """QA-E: datas 10/08->10/07, "Entregue"->"Pendente", RD-103->RD-104, "Topografia"->
    "Drenagem" no recorte do 2.2."""
    page_no, first = golden.first_crop("2.2")
    cells = dict(zip(("code", "kind", "description", "road", "date", "status"), first["cells"],
                     strict=True))
    if field == "date":
        mutate = substitute(cells["date"], _other_month(cells["date"]), 20, page_no)
    elif field == "status":
        new = "Pendente" if cells["status"] != "Pendente" else "Entregue"
        mutate = substitute(cells["status"], new, 5, page_no)
    elif field == "road":
        new = "RD-104" if cells["road"] != "RD-104" else "RD-103"
        mutate = substitute(cells["road"], new, 1, page_no)
    else:
        mutate = substitute("Topografia", "Drenagem", 1, page_no)
    report, new = golden.run(tmp_path, mutate)
    _assert_new_v2_failure(report, new, {"product_control_rows"}, "block:2.2")
    assert field in {d.context.get("field") for d in new if d.check == "product_control_rows"}


# --------------------------------------------------------------------------- fatos da narrativa


@pytest.mark.golden
@pytest.mark.parametrize(("old", "new"), [
    ("07, 08 e 09", "06, 07 e 08"),  # Boletins de Medição citados
    ("às 10h", "às 15h"),            # hora da reunião
    ("N° 09", "N° 08"),              # número de relatório citado
])
def test_golden_narrative_fact_mutation_fails(golden, tmp_path, old, new):
    report, diffs = golden.run(tmp_path, substitute(old, new))
    _assert_new_v2_failure(report, diffs, {"narrative_facts"})


# --------------------------------------------------------------------------- figuras


@pytest.mark.golden
@pytest.mark.parametrize("anchor", ["2.2.2", "2.4.2"])
def test_golden_blank_panel_fails(golden, tmp_path, anchor):
    """QA-E: painel RD-103 (1º quadro do 2.2.2) e painel ambiental (1º do 2.4.2) em branco."""
    page_no, bbox = golden.rasters(anchor)[0]
    report, new = golden.run(tmp_path, blank_image(page_no, bbox))
    _assert_new_v2_failure(report, new, {"figure_content"}, f"anchor:{anchor}", text=False)
    assert {d.kind for d in new if d.check == "figure_content"} == {"blank"}


@pytest.mark.golden
def test_golden_swapped_panels_fail(golden, tmp_path):
    """QA-E: quadros RD-103 e RD-102A trocados (legendas no lugar)."""
    first, second = golden.rasters("2.2.2")[:2]
    report, new = golden.run(tmp_path, swap_images(first, second))
    _assert_new_v2_failure(report, new, {"figure_identity"}, "anchor:2.2.2", text=False)
    swapped = sorted((d.value, d.generated) for d in new if d.kind == "swapped")
    assert swapped == [("2.2.2#1", 2), ("2.2.2#2", 1)]


# =========================================================================== QA2-E (v2 -> v3)
# As 19 mutações de conteúdo que passavam no comparador 2.0 (docs/qa/GATES.md, QA2-E;
# tmp/agent_QAE2/res_main.json, res_new2.json, res_new5.json, res_fx2.json: verdict PASS).


def _new_values(new, check: str, scope: str | None = None) -> set[str]:
    return {str(d.value) for d in new if d.check == check
            and (scope is None or d.scope == scope)}


def _assert_v3_catches(report, new, check: str, scope: str, values: set[str] | None = None):
    """Reprova, com diferença bloqueante NOVA na verificação da v3 e, se dado, exatamente com
    esses valores entre os novos (os fatos do vocabulário que a v2 não tinha)."""
    assert not report.passed
    assert new, "a mutação não criou diferença bloqueante nova"
    hit = [d for d in new if d.check == check and d.scope == scope]
    assert hit, [(d.check, d.scope, d.message) for d in new]
    if values is not None:
        assert values <= _new_values(new, check, scope), [(d.kind, d.value) for d in hit]


# --------------------------------------------------------------------------- fatos ampliados


@pytest.mark.golden
@pytest.mark.parametrize(("name", "old", "new_text", "scope", "values"), [
    ("new_24_word_count_licencas", "oito licen", "nove licen", "section:2.4.2",
     {"number:8", "number:9"}),
    ("new_24_word_count_cinco", "cinco licen", "três licen", "section:2.4.2",
     {"number:5", "number:3"}),
    ("new_24_rodovias_quatro", "alojamentos das quatro", "alojamentos das três",
     "section:2.4.2", {"number:4", "number:3"}),
    ("new_24_cond_negation", "não há condicionantes pendentes", "há condicionantes pendentes",
     "section:2.4.2", {"neg:NAO_HA"}),
    ("new_22_status_value_flip", "Análise Programa: Aprovado;", "Análise Programa: Não aprovado;",
     "section:2.2.2", {"status:APROVADO@ANALISE PROGRAMA", "status:NAO_APROVADO@ANALISE PROGRAMA"}),
    # 14_v6: o "Aprovado" que sobra na RD-103#3 casa, no alinhamento dos fatos, com o
    # "Aprovado" da DUP da RD-103 da referência (no gerado, "Aprovado com ressalva"): o fato
    # que denuncia a mutação é o "Não aprovado" que falta
    ("new_22_status_neg_removed", "Análise Programa: Não aprovado;", "Análise Programa: Aprovado;",
     "section:2.2.2", {"status:NAO_APROVADO@ANALISE PROGRAMA"}),
    ("new_22_aprovacao_aceitacao", "Aprovação: Todas", "Aceitação: Todas", "section:2.2.2",
     {"status:APROVACAO", "status:APROVADO@APROVACAO", "status:APROVADO@ACEITACAO"}),
    ("new_22_nivel_1_2", "aceitos em 1º nível", "aceitos em 2º nível", "section:2.2.2",
     {"ordinal:1", "ordinal:2"}),
    ("new_21_company_swap", "com a DELTA", "com a CSG", "section:2.1.2",
     {"company:DELTA", "company:CSG"}),
    ("new_21_weekday", "às quintas, às 11h", "às sextas, às 11h", "section:2.1.2",
     {"weekday:QUINTA", "weekday:SEXTA"}),
])
def test_golden_v3_narrative_fact_mutation_fails(golden, tmp_path, name, old, new_text, scope,
                                                 values):
    report, new = golden.run(tmp_path, substitute(old, new_text))
    _assert_v3_catches(report, new, "narrative_facts", scope, values)


@pytest.mark.golden
def test_golden_v3_negation_in_2_5_removed_fails(golden, tmp_path):
    """QA2-E new_25_negation: "não houve atividades" -> "houve atividades" no 2.5.2."""
    page = golden.gen["sections"]["2.5.2"]["page"]
    report, new = golden.run(tmp_path, substitute("não houve atividades", "houve atividades",
                                                  1, page))
    _assert_v3_catches(report, new, "narrative_facts", "section:2.5.2", {"neg:NAO_HOUVE"})


@pytest.mark.golden
def test_golden_v3_signatory_swapped_fails_without_printing_the_name(golden, tmp_path):
    """QA2-E new_closing_signer: outro nome no Encerramento. O nome é lido do próprio gerado
    (não fica no código do teste) e não pode aparecer no relatório de comparação."""
    match = SIGNATORY_RE.search(golden.gen["sections"]["ENCERRAMENTO"]["text"])
    assert match, "assinatura não reconhecida no Encerramento do gerado"
    name = match.group("name")
    report, new = golden.run(tmp_path, substitute(name, "Fulano de Tal Silva"))
    _assert_v3_catches(report, new, "signatory", "closing")
    assert [d.severity for d in report.find("signatory")] == [CRITICAL]
    rendered = report.to_markdown() + repr(report.to_dict())
    assert name not in rendered and "Fulano" not in rendered


# --------------------------------------------------------------------------- parágrafos


_P24_PARECER = "Adicionalmente, foram emitidos pareceres técnicos no âmbito do Produto P2.4"
_P24_ENSAIOS = "Os documentos contemplam a análise dos ensaios"


def _index(segments: list[dict], start: str) -> int:
    return next(i for i, s in enumerate(segments) if s["kind"] == "body"
                and s["text"].startswith(start))


@pytest.mark.golden
def test_golden_v3_duplicated_paragraph_fails(golden):
    """QA2-E fx_dup_paragraph_212: o parágrafo dos pareceres do P2.4 repetido no 2.1.2."""
    def mutate(segments):
        i = _index(segments, _P24_PARECER)
        segments.insert(i + 1, dict(segments[i]))

    report, new = golden.run_segments("2.1.2", mutate)
    _assert_v3_catches(report, new, "paragraph_duplicate", "section:2.1.2")
    # o parágrafo do gerado (S7 do 2.1, temas sem PA fora: P2.1_S7_TEMAS_SEM_SUPORTE) não
    # existe com esse texto na referência; repetido, aparece 2x no mesmo bloco
    assert [(d.reference, d.generated) for d in new if d.check == "paragraph_duplicate"] == [
        (0, 2)]


@pytest.mark.golden
def test_golden_v3_short_paragraph_deleted_fails(golden):
    """QA2-E fx2_del_38w_24: parágrafo de 38 palavras do 2.4.2 apagado (abaixo da lacuna de 40
    palavras da v2; cobertura da seção continua > 0,9)."""
    def mutate(segments):
        segments.pop(_index(segments, _P24_ENSAIOS))

    report, new = golden.run_segments("2.4.2", mutate)
    _assert_v3_catches(report, new, "paragraph_coverage", "section:2.4.2")
    # v1.8: no 14_final o 2.4.2 do controle já perdeu os temas das atas e dos pareceres (NN,
    # ALW-14-034), então a cobertura da seção cai abaixo de 0,9 com esta mutação e a v2 também
    # a veria; o que prova a v3 é o parágrafo de 38 palavras sem correspondente.
    hit = [d for d in new if d.check == "paragraph_coverage" and d.context["words"] >= 30]
    assert hit, [(d.check, d.value) for d in new]
    assert "text_diff" in {d.check for d in new}


@pytest.mark.golden
def test_golden_v3_status_swapped_between_roads_fails(golden):
    """QA2-E fx_swap_status_same_road_22: "Análise Programa: Aprovado" (RD-103, DUP) trocado com
    "Análise Programa: Não aprovado" (RD-103, Desapropriação): mesmo multiconjunto, outra ordem.
    Controle 14_v6 (modelo v0.14): a DUP da RD-103 sai "Aprovado com ressalva" (v438)."""
    def mutate(segments):
        a = _index(segments, "• Análise Programa: Aprovado com ressalva;")
        b = _index(segments, "• Análise Programa: Não aprovado;")
        segments[a]["text"], segments[b]["text"] = segments[b]["text"], segments[a]["text"]

    report, new = golden.run_segments("2.2.2", mutate)
    _assert_v3_catches(report, new, "narrative_facts", "section:2.2.2",
                       {"status:APROVADO_COM_RESSALVA@ANALISE PROGRAMA",
                        "status:NAO_APROVADO@ANALISE PROGRAMA"})
    blocks = {d.context.get("block") for d in new if d.check == "narrative_facts"
              and "ANALISE PROGRAMA" in str(d.value)}
    # RD-103#1 = acompanhamento do projeto; #2 = DUP; #3 = Projeto de Desapropriação
    assert {"RD-103#2", "RD-103#3"} <= blocks


@pytest.mark.golden
def test_golden_v3_license_counts_swapped_between_roads_fails(golden):
    """QA2-E fx_swap_license_counts_24: "duas licenças" (RD-104) <-> "cinco licenças"
    (RD-103)."""
    def mutate(segments):
        a = _index(segments, "• RD-104: duas licenças")
        b = _index(segments, "• RD-103: cinco licenças")
        segments[a]["text"] = segments[a]["text"].replace("duas licenças", "cinco licenças")
        segments[b]["text"] = segments[b]["text"].replace("cinco licenças", "duas licenças")

    report, new = golden.run_segments("2.4.2", mutate)
    _assert_v3_catches(report, new, "narrative_facts", "section:2.4.2", {"number:5"})
    # v1.8: o fato que muda de bloco de rodovia é falta + sobra (não `order`), em cada bloco
    fives = {(d.kind, d.context.get("block")) for d in new if d.value == "number:5"}
    assert {k for k, _ in fives} == {"missing", "extra"} and len({b for _, b in fives}) == 2


_QQ_BLOCKS = ("RD-104#3", "RD-102A#4", "RD-104#4")


def _prog_status(new_value: str):
    """Análise Programa dos 3 itens de P2.2_EXTERNAL_PROG_CONTRADIZ_PLANILHA (Desapropriação da
    RD-104; Interferência da RD-102A e da RD-104) trocada no texto do gerado. O gerado anterior
    ao QQ (14_mm3) dizia "Não aprovado"; o 14_final (v1.8) já diz "Em análise"."""
    current = {"• Análise Programa: Não aprovado;", "• Análise Programa: Em análise;"}

    def mutate(segments):
        hits = 0
        for segment in segments:
            if segment.get("block") in _QQ_BLOCKS and segment["text"] in current:
                segment["text"] = f"• Análise Programa: {new_value};"
                hits += 1
        assert hits == 3, hits
    return mutate


@pytest.mark.golden
def test_golden_v3_prog_status_from_the_projects_sheet_is_allowed_exactly(golden):
    """Builder QQ: a Análise Programa sai da aba Projetos e o gerado diz "Em análise" onde o
    publicado diz "Não aprovado" (3 itens). Desde a v1.9 (comparador 4.0) cada item é um hunk
    aprovado com a anomalia P2.2_EXTERNAL_PROG_CONTRADIZ_PLANILHA (era a ALW-14-029); o mesmo
    campo com outro valor é hunk novo, CRITICAL, e os fatos v3 voltam a bloquear."""
    report, new = golden.run_segments("2.2.2", _prog_status("Em análise"))
    assert report.passed, [(d.check, d.message) for d in new]
    prog = [d for d in report.find("text_diff")
            if (d.reference, d.generated) == ("Não aprovado", "Em análise")]
    assert len(prog) == 3 and all(d.severity == "ALLOWED" for d in prog)
    assert {d.allowance_reference for d in prog} == {
        "anomalia P2.2_EXTERNAL_PROG_CONTRADIZ_PLANILHA"}

    report, new = golden.run_segments("2.2.2", _prog_status("Aprovado"))
    _assert_v3_catches(report, new, "narrative_facts", "section:2.2.2",
                       {"status:NAO_APROVADO@ANALISE PROGRAMA", "status:APROVADO@ANALISE PROGRAMA"})
    assert "text_diff" in {d.check for d in new}


# --------------------------------------------------------------------------- painéis raster


def paint_in_image(page_no: int, bbox: tuple[float, ...], frac: tuple[float, ...], label: str):
    """QA2-E `paint_in_image`: retângulo com a cor de fundo e um texto novo por cima, dentro
    do painel (troca de um dado impresso)."""
    image_mod = pytest.importorskip("PIL.Image")
    draw_mod = pytest.importorskip("PIL.ImageDraw")
    font_mod = pytest.importorskip("PIL.ImageFont")

    def mutate(doc):
        page = doc[page_no - 1]
        xref = _xref_at(doc, page_no, bbox)
        pix = pymupdf.Pixmap(doc, xref)
        if pix.alpha or pix.n != 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        im = image_mod.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        w, h = im.size
        box = [int(frac[0] * w), int(frac[1] * h), int(frac[2] * w), int(frac[3] * h)]
        background = im.getpixel((box[0] + 1, box[1] + 1))
        draw = draw_mod.Draw(im)
        draw.rectangle(box, fill=background)
        try:
            font = font_mod.truetype("arial.ttf", max(10, int((box[3] - box[1]) * 0.7)))
        except OSError:
            font = font_mod.load_default()
        draw.text((box[0] + 2, box[1] + 1), label, fill=(20, 20, 20), font=font)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        page.replace_image(xref, stream=buf.getvalue())
    return mutate


@pytest.mark.golden
@pytest.mark.parametrize(("name", "frac", "label", "region"), [
    # QA2-E new5_*: frações da imagem do painel de índices ambientais (1º raster do 2.4.2)
    ("new5_panel_updated_date", (0.817, 0.008, 0.905, 0.031), "Atualizado em 08/10/2026",
     "atualizado_em"),
    ("new5_panel_kpi_pendentes", (0.80, 0.064, 0.86, 0.10), " 3", "kpi_pendentes"),
])
def test_golden_v3_panel_text_region_painted_fails(golden, tmp_path, name, frac, label, region):
    page_no, bbox = golden.rasters("2.4.2")[0]
    report, new = golden.run(tmp_path, paint_in_image(page_no, bbox, frac, label))
    _assert_v3_catches(report, new, "figure_region", "anchor:2.4.2", {f"2.4.2#1:{region}"})
    assert all(d.severity == MAJOR for d in new if d.check == "figure_region")


@pytest.mark.golden
def test_golden_v3_condition_panels_swapped_fail_by_the_selector(golden, tmp_path):
    """QA2-E new_swap_env_panels_30_31: 1º painel de condicionantes (RD-101, p. 30) trocado
    com o último (RD-104, p. 31). Mesmo leiaute, sem selo: a aba destacada denuncia."""
    rasters = golden.rasters("2.4.2")
    report, new = golden.run(tmp_path, swap_images(rasters[1], rasters[4]))
    _assert_v3_catches(report, new, "figure_identity", "anchor:2.4.2")
    selector = sorted((d.value, d.reference, d.generated) for d in new if d.kind == "selector")
    assert selector == [("2.4.2#2", 1, 4), ("2.4.2#5", 4, 1)]


@pytest.mark.golden
@pytest.mark.xfail(strict=True, reason=(
    "LIMITAÇÃO documentada (raster_regions.yaml): sem OCR, célula da tabela dos quadros do "
    "2.2.2 não é verificável — ruído legítimo 0,2+ (quebra de linha, formato de data) contra "
    "~0,1 da célula pintada; coberto pelo QA de fonte. strict: se passar a reprovar, revisar."))
def test_golden_v3_quadro_table_cell_painted_is_a_documented_limitation(golden, tmp_path):
    """QA2-E new2_22_quadro_cell: "Reprovado" pintado sobre células do quadro RD-103."""
    page_no, bbox = golden.rasters("2.2.2")[0]
    report, new = golden.run(tmp_path, paint_in_image(page_no, bbox, (0.55, 0.30, 0.70, 0.36),
                                                      "Reprovado"))
    assert not report.passed and new
