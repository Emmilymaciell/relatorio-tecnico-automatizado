"""Golden adversarial do comparador 4.0 (Gate D): TODAS as mutações das três rodadas de QA-E
(tests/fixtures/qa_mutation_catalog.py, inclusive as que passaram na rodada 3), a varredura de 200
palavras e os controles sem mutação do nº 14 e do nº 13.

Só roda com `-m golden` e com os PDFs em disco (nunca versionados; tests/fixtures/golden_pdfs):
  - referência: tmp/downloads/relatorios_11_14/...n°14 / n°13
  - controle: output/reconstruction/14_v6 e 13_v6 (modelo v0.14, agente XX; comparador 4.1)
As mutações rodam em processos paralelos (`prog_g2_report.qa.mutate`, PROG_QA_WORKERS); cada
PDF mutado fica no diretório temporário do pytest e é apagado. Um teste por mutação.

Prova de que pega a regressão: o controle passa sem CRITICAL/MAJOR e cada mutação cria
diferença bloqueante NOVA; toda mutação de TEXTO cria um hunk `text_diff` novo (as 22 de
texto que passavam no comparador 3.0, QA3-E, incluídas). As de conteúdo DENTRO de figura
raster que passaram na rodada 3 continuam fora do alcance (sem OCR): xfail estrito
documentado — se passarem a reprovar, o xfail vira falha e o teste tem de ser revisto.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

pytest.importorskip("pymupdf")
pytest.importorskip("numpy")
pytest.importorskip("PIL.Image")

from prog_g2_report.qa.compare import CRITICAL, MAJOR, compare, load_allowances
from prog_g2_report.qa.extract import extract_facts
from prog_g2_report.qa.mutate import (
    blocking_keys,
    relocation_specs,
    run_mutations,
    word_sweep_specs,
)
from fixtures.golden_pdfs import generated_pdf, reference_pdf
from fixtures.qa_mutation_catalog import CATALOG

CONTROL_14 = ("14_v6",)
CONTROL_13 = ("13_v6",)
SWEEP_WORDS = 200
SWEEP_SEED = 20261002

# QA4-E (comparador 4.0 aprovava): a ressalva da DUP sai de uma rodovia e vai para a RD-102A,
# nos fatos e no PDF do controle 14_v6. O parágrafo publicado ("Aprovação: Todas as disciplinas
# encontram-se aprovadas;") é igual nas 3 rodovias e as duas aprovações (HNK-14-058/060) casavam
# por hash + contexto + ocorrência, onde quer que o texto estivesse.
_DUP = "Todas as disciplinas encontram-se aprovadas. A Documentação"
_PLAIN = "Aprovação: Todas as disciplinas encontram-se aprovadas;"
_LONG = ("Aprovação: Todas as disciplinas encontram-se aprovadas. A Documentação para "
         "Declaração de Utilidade Pública (DUP) encontra-se aprovada com ressalva;")
_PDF_TO_RD102A = {"page": 19, "needle": _PLAIN, "nth": 0, "lines": 1, "text": _LONG}
QA4E_ATTACKS = [
    {"name": "q4e_a_fatos_dup_RD103_para_RD102A", "op": "f_swap_segs", "section": "2.2.2",
     "a": _DUP, "b": _PLAIN, "expect": "text"},
    {"name": "q4e_c_fatos_dup_RD104_para_RD102A", "op": "f_swap_segs", "section": "2.2.2",
     "a": _PLAIN, "b": _DUP, "expect": "text"},
    {"name": "q4e_a_pdf_dup_RD103_para_RD102A", "op": "rewrite_lines", "expect": "text",
     "items": [{"page": 18, "needle": "Aprovação: Todas as disciplinas encontram-se aprovadas. A",
                "lines": 2, "text": _PLAIN}, _PDF_TO_RD102A]},
    {"name": "q4e_c_pdf_dup_RD104_para_RD102A", "op": "rewrite_lines", "expect": "text",
     "items": [{"page": 21, "needle": "Aprovação: Todas as disciplinas encontram-se aprovadas. A",
                "lines": 2, "text": _PLAIN}, _PDF_TO_RD102A]},
    # item 2: quebra de parágrafo perdida na RD-103 (Projeto de Desapropriação): nenhum token
    # muda, o status passa ao campo errado; no 4.0 o v3 saía ALLOWED pelos hunks da unidade
    {"name": "q4e_fato_bloco_sem_hunk_RD103_desapropriacao", "op": "f_merge_seg",
     "section": "2.2.2", "block": "RD-103#3", "needle": "A) RD-103:", "expect": "facts"},
    # MAJOR do QA4-E (texto que o extrator lê e o leitor não vê): no 4.0 passavam
    {"name": "q4e_d2_branqueia_Nao_do_status", "op": "cover_text", "page": 23,
     "needle": "Análise Programa: Não aprovado;", "part": "Não", "expect": "visibility"},
    {"name": "q4e_d5_status_em_texto_branco", "op": "rewrite_lines", "expect": "visibility",
     "items": [{"page": 23, "needle": "Análise Programa: Não aprovado;", "lines": 1,
                "text": "Análise Programa: Não aprovado;", "color": (1, 1, 1)}]},
    {"name": "q4e_j10_linha_do_controle_coberta", "op": "cover_text", "page": 40,
     "needle": "NT-741.1", "band": True, "expect": "visibility"},
    {"name": "q4e_j11_numero_da_capa_coberto", "op": "cover_text", "page": 1,
     "needle": "Mensal N° 14", "part": "14", "expect": "visibility"},
]
_RD102A_STUDIES = "RD-102A#1 > DISCIPLINAS DA FASE DE ESTUDOS"

RASTER_LIMIT = (
    "LIMITAÇÃO documentada (raster_regions.yaml): sem OCR, um dígito ou célula pintados DENTRO "
    "de um painel raster ficam abaixo do ruído legítimo das regiões calibradas; o diff de "
    "texto não vê raster. Coberto pelo QA de fonte. strict: se passar a reprovar, revisar.")


def _require_golden(request) -> None:
    if "golden" not in (request.config.getoption("-m") or ""):
        pytest.skip("teste do PDF real: rodar com -m golden")


class GoldenV4:
    def __init__(self, tmp: Path):
        reference, generated = reference_pdf(14), generated_pdf(14, CONTROL_14)
        if reference is None or generated is None:
            pytest.skip("PDF de referência ou controle 14_v6 do Relatório G2 nº 14 indisponível")
        self.generated_pdf = generated
        self.allowances = load_allowances()
        self.ref = extract_facts(reference)
        self.gen = extract_facts(generated)
        self.control = compare(self.ref, self.gen, self.allowances, report_number=14)
        keys = blocking_keys(self.control)
        self.text_pages = self._text_pages()
        common = {"reference_facts": self.ref, "generated_facts": self.gen,
                  "generated_pdf": generated, "report_number": 14, "control_keys": keys}
        self.results = run_mutations(CATALOG, tmp_dir=tmp / "catalogo", **common)
        self.sweep_specs = word_sweep_specs(self.gen, n=SWEEP_WORDS, seed=SWEEP_SEED)
        self.sweep = run_mutations(self.sweep_specs, tmp_dir=tmp / "varredura", **common)
        self.qa4e = run_mutations(QA4E_ATTACKS, tmp_dir=tmp / "qa4e", **common)
        self.relocation_plan = relocation_specs(self.ref, self.gen,
                                                self.allowances.approved_hunks(14))
        self.relocation = run_mutations(self.relocation_plan["specs"],
                                        tmp_dir=tmp / "realocacao", **common)

    def _text_pages(self) -> set[int]:
        """Páginas do controle com texto comparado (segmento, título ou linha do Controle de
        Produtos): apagar o corpo de outra página (só painéis) não é mutação de texto."""
        pages = {s["page"] for sec in self.gen["sections"].values()
                 for s in sec.get("segments") or []}
        pages |= {h["page"] for h in self.gen["headings"]}
        pages |= {r["page"] for rows in self.gen["product_control"]["rows"].values()
                  for r in rows}
        return pages

    def expects_text(self, spec: dict) -> bool:
        if spec["expect"] != "text":
            return False
        if spec["op"] == "wipe_body":
            return spec["page"] in self.text_pages
        return True


@pytest.fixture(scope="module")
def golden_v4(request, tmp_path_factory) -> GoldenV4:
    _require_golden(request)
    return GoldenV4(tmp_path_factory.mktemp("golden_v4"))


# --------------------------------------------------------------------------- controle


@pytest.mark.golden
def test_v4_control_14_passes_with_every_hunk_approved(golden_v4):
    report = golden_v4.control
    assert report.passed, report.reasons
    assert [d for d in report.differences if d.severity in (CRITICAL, MAJOR)] == []
    td = report.metrics["text_diff"]
    assert td["hunks"] == td["approved"] == 113 and td["orphans"] == [] and not report.warnings
    assert report.metrics["content_accuracy"] == 1.0
    assert report.metrics["structural_score"] >= 0.99
    # v4.1: todo `narrative_facts` do controle explicado por um hunk aprovado do mesmo bloco
    assert td["v3_unexplained"] == 0
    facts = report.find("narrative_facts")
    assert facts and all(d.severity == "ALLOWED" and "HNK-14-" in d.allowance_reference
                         for d in facts if d.context.get("block"))


# --------------------------------------------------------------------------- QA4-E


@pytest.mark.golden
@pytest.mark.parametrize("spec", QA4E_ATTACKS, ids=[s["name"] for s in QA4E_ATTACKS])
def test_v41_qa4e_attacks_fail(golden_v4, spec):
    """BLOCKS_GATE do QA4-E: no comparador 4.0 as quatro realocações da ressalva da DUP
    PASSAVAM (tmp/agent_QAE4, fatos e PDF); a quebra de parágrafo da RD-103 (fato no campo
    errado, nenhum token mudado) também. No 4.1 todas reprovam com diferença NOVA: as da
    ressalva por hunk `text_diff` no bloco da RD-102A (posição não aprovada); a do fato por
    `narrative_facts` sem hunk aprovado no bloco."""
    result = golden_v4.qa4e[spec["name"]]
    assert result["error"] is None, result["error"]
    new = result["new"]
    assert result["verdict"] == "FAIL" and new
    if spec["expect"] == "text":
        assert any(d["check"] == "text_diff" and _RD102A_STUDIES in d["message"]
                   for d in new), [d["message"] for d in new]
    elif spec["expect"] == "visibility":
        assert "text_visibility" in {d["check"] for d in new}, [d["message"] for d in new]
    else:
        assert {d["check"] for d in new} == {"narrative_facts"}
        assert all("RD-103#3" in d["message"] and "v4.1" in d["message"] for d in new)


@pytest.mark.golden
def test_v41_relocation_sweep_every_relocated_approval_fails(golden_v4, tmp_path):
    """Varredura de REALOCAÇÃO: cada hunk aprovado num bloco de rodovia com irmão (mesmo grupo
    em outra rodovia, mesmo item em outra lista) tem o lado gerado trocado com o parágrafo do
    irmão. Troca que não muda o texto (os dois gerados iguais) não é mutação (`noop`). Taxa de
    reprovação pelo diff estrito = 100%; o par HNK-14-058/060 está na varredura."""
    plan, results = golden_v4.relocation_plan, golden_v4.relocation
    specs = plan["specs"]
    assert len(specs) >= 100 and len(results) == len(specs)
    caught = {name for name, r in results.items() if r["error"] is None
              and r["verdict"] == "FAIL" and any(d["check"] == "text_diff" for d in r["new"])}
    rate = len(caught) / len(results)
    hunks = {s["hunk"] for s in specs}
    summary = {"relocations": len(results), "caught": len(caught), "rate": rate,
               "hunks": len(hunks), "noop": len(plan["noop"]),
               "no_sibling": len(plan["no_sibling"]),
               "missed": sorted(set(results) - caught)}
    (tmp_path / "realocacao.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"\nvarredura de realocação: {len(caught)}/{len(results)} = {rate:.0%} "
          f"({len(hunks)} hunks; {len(plan['noop'])} trocas nulas; "
          f"{len(plan['no_sibling'])} hunks sem bloco irmão)")
    assert {"HNK-14-058", "HNK-14-060"} <= hunks
    assert "reloc_HNK-14-058_RD-103_to_RD-102A" in results
    assert "reloc_HNK-14-060_RD-104_to_RD-102A" in results
    assert rate == 1.0, summary["missed"]


# --------------------------------------------------------------------------- catálogo

def _catalog_params():
    for spec in CATALOG:
        marks = (pytest.mark.xfail(strict=True, reason=RASTER_LIMIT)
                 if spec["expect"] == "raster_limit" else ())
        yield pytest.param(spec, id=spec["name"], marks=marks)


@pytest.mark.golden
@pytest.mark.parametrize("spec", list(_catalog_params()))
def test_v4_every_mutation_of_the_three_rounds_fails(golden_v4, spec):
    result = golden_v4.results[spec["name"]]
    assert result["error"] is None, result["error"]
    new = {d["check"] for d in result["new"]}
    assert result["verdict"] == "FAIL" and new, "a mutação não criou diferença bloqueante nova"
    if golden_v4.expects_text(spec):
        assert "text_diff" in new, f"mutação de texto sem hunk novo: {sorted(new)}"


@pytest.mark.golden
def test_v4_text_mutations_that_passed_round_3_now_fail_by_the_strict_diff(golden_v4):
    """QA3-E: as mutações de TEXTO que o comparador 3.0 aprovava (status fora do vocabulário,
    quantificadores, verbos de estado, item curto apagado, sumário, contrato) — todas com hunk
    `text_diff` novo."""
    passed = [s for s in CATALOG if s.get("passed_round3") and s["expect"] == "text"]
    assert len(passed) == 22
    missed = [s["name"] for s in passed
              if "text_diff" not in {d["check"] for d in golden_v4.results[s["name"]]["new"]}]
    assert missed == []


@pytest.mark.golden
def test_v4_catalog_covers_the_three_rounds(golden_v4):
    rounds = Counter(s["name"].split("_", 1)[0] for s in CATALOG)
    assert rounds["r1"] == 26 and rounds["r3"] >= 50 and rounds["r4"] == 3
    assert sum(1 for s in CATALOG if s["name"].startswith(("r2_sweep_del_", "r2_wsweep_"))) == 84
    assert set(golden_v4.results) == {s["name"] for s in CATALOG}


# --------------------------------------------------------------------------- varredura


@pytest.mark.golden
def test_v4_word_sweep_every_replaced_word_fails(golden_v4, tmp_path):
    """200 palavras do texto gerado (seções e células do Controle de Produtos), semente fixa,
    cada uma trocada por outra palavra plausível do próprio documento: taxa de reprovação pelo
    diff estrito = 100%."""
    results = golden_v4.sweep
    assert len(results) == SWEEP_WORDS == len(golden_v4.sweep_specs)
    caught = {name for name, r in results.items() if r["error"] is None
              and r["verdict"] == "FAIL" and any(d["check"] == "text_diff" for d in r["new"])}
    rate = len(caught) / len(results)
    by_unit = Counter(s["unit"].split(":")[0] for s in golden_v4.sweep_specs)
    summary = {"words": len(results), "caught": len(caught), "rate": rate,
               "seed": SWEEP_SEED, "units": dict(by_unit),
               "missed": sorted(set(results) - caught)}
    (tmp_path / "varredura.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"\nvarredura de palavras: {len(caught)}/{len(results)} = {rate:.0%}")
    assert by_unit["section"] > 0 and by_unit["block"] > 0
    assert rate == 1.0, summary["missed"]


# --------------------------------------------------------------------------- nº 13

# Resíduo Lista Mestra v134 × v162 (GAP-015): os únicos hunks NÃO aprovados do nº 13.
RESIDUAL_13 = Counter({
    ("section:ENCERRAMENTO", "165", "163"): 1,
    ("section:ENCERRAMENTO", "cinco", "três"): 1,
    ("block:2.2", "Projeto Executivo", "Documentos"): 5,
    ("block:ANEXOS", "Projeto Executivo", "Documentos"): 5,
    ("block:2.4", "Entregue", "Em elaboração"): 2,
    ("block:2.4", "Tecnológico e Topográfico ( Mar/26 )", "Te"): 1,
    ("block:2.4", "Tecnológico e Topográfico ( Abr/26 )", "Te"): 1,
    ("block:2.4", "Tecnológico e Topográfico ( Mai/26 )", "Te"): 1,
    ("block:ANEXOS", "Tecnológico e Topográfico ( Mar/26 )", "Te"): 1,
    ("block:ANEXOS", "Tecnológico e Topográfico ( Abr/26 )", "Te"): 1,
    ("block:ANEXOS", "Tecnológico e Topográfico ( Mai/26 )", "Te"): 1,
    ("block:2.4", "BM-007.1 | Boletim de Medição |", ""): 1,
    ("block:ANEXOS", "PA-640.1 | Parecer |", ""): 1,
    ("block:ANEXOS", "PA-677.1 | Parecer |", ""): 1,
})


@pytest.mark.golden
def test_v4_control_13_fails_only_by_the_master_list_residual(request):
    """13_v6: os 117 hunks aprovados casam (sem órfão); NÃO aprovados são só os 23 do resíduo
    v134 × v162, e as diferenças v3 bloqueantes só nos blocos do Controle de Produtos e no total
    de anexos. A página a mais (44 × 43, ressalva por disciplina) sai pelas ALW-13-039..041."""
    _require_golden(request)
    reference, generated = reference_pdf(13), generated_pdf(13, CONTROL_13)
    if reference is None or generated is None:
        pytest.skip("PDF de referência ou controle 13_v6 do Relatório G2 nº 13 indisponível")
    report = compare(extract_facts(reference), extract_facts(generated), load_allowances(),
                     report_number=13)
    assert not report.passed
    td = report.metrics["text_diff"]
    assert td["approved"] == 117 and td["orphans"] == [] and td["pending"] == 0
    open_hunks = Counter()
    for d in report.find("text_diff"):
        if d.severity == CRITICAL:
            ref = d.reference or ""
            if " | " in ref:  # linha inteira do Controle de Produtos: código e 2ª célula
                ref = " | ".join(ref.split(" | ")[:2]) + " |"
            open_hunks[(d.scope, ref, d.generated or "")] += 1
    assert open_hunks == RESIDUAL_13
    other = {(d.check, d.scope) for d in report.differences
             if d.severity in (CRITICAL, MAJOR) and d.check != "text_diff"}
    assert {scope for _, scope in other} <= {"block:2.2", "block:2.4", "block:ANEXOS",
                                              "closing"}
    assert {c for c, s in other if s == "closing"} == {"declared_annexes"}
    assert set(report.allowances_used) >= {"ALW-13-039", "ALW-13-040", "ALW-13-041"}


@pytest.mark.golden
def test_v4_pre_tt_build_regresses_and_fails_on_the_ressalva(request):
    """Regressão real: o 14_final (anterior ao TT, ressalva generalizada do modelo v0.12)
    contra os hunks do 14_v6 reprova — no 2.2.2 (hunks da ressalva por disciplina) e, desde o
    modelo v0.14, também pela crase revertida ao publicado ('Referente as', 2.1.2 e 2.4.2)."""
    _require_golden(request)
    reference, generated = reference_pdf(14), generated_pdf(14, ("14_final",))
    if reference is None or generated is None:
        pytest.skip("14_final indisponível")
    report = compare(extract_facts(reference), extract_facts(generated), load_allowances(),
                     report_number=14)
    assert not report.passed
    blocking = [d for d in report.find("text_diff") if d.severity == CRITICAL]
    assert blocking and "section:2.2.2" in {d.scope for d in blocking}
    outside = [d for d in blocking if d.scope != "section:2.2.2"]
    assert {d.scope for d in outside} <= {"section:2.1.2", "section:2.4.2"}
    assert all(d.kind == "reverted" and d.reference == "as" for d in outside)
    assert any(d.kind == "delete" and d.reference == "com ressalva" for d in blocking)
    assert len(report.approved_hunks_orphans) >= 10
