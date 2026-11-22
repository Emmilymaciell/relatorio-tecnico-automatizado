"""Comparador 4.0 — diff de texto ESTRITO e hunks aprovados (`prog_g2_report.qa.textdiff` e
`prog_g2_report.qa.compare`), com textos e PDFs SINTÉTICOS e com os conjuntos congelados do
repositório (docs/qa/approved_hunks/, sem PDF).

Cada teste de regressão mostra as duas metades: a mudança que o comparador 3.0 deixava passar
(QA3-E: status fora do vocabulário, quantificador, verbo de estado, item curto apagado,
sumário) agora reprova pelo `text_diff`, e o texto igual (ou só com diferença de leiaute)
passa — senão o "reprova" não prova nada.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

pytest.importorskip("pymupdf")

from prog_g2_report.qa.compare import (
    ALLOWED,
    COMPARATOR_VERSION,
    CRITICAL,
    MAJOR,
    AllowanceError,
    AllowanceSet,
    HunkSet,
    compare,
    draft_hunks,
    load_allowances,
    load_approved_hunks,
    parse_allowances,
    parse_approved_hunks,
)
from prog_g2_report.qa.textdiff import (
    CONTEXT_TOKENS,
    TextUnit,
    diff_unit,
    mask_signatory,
    normalize_strict,
    paragraph_anchor,
    tokens,
)
from fixtures.qa_synthetic import (
    Page,
    approve_all,
    facts_of,
    synthetic_pages,
    text,
)

ROOT = Path(__file__).resolve().parents[1]
HUNKS_DIR = ROOT / "docs" / "qa" / "approved_hunks"
# Os conjuntos congelados nNN.yaml contêm trechos dos relatórios reais: removidos na versão pública.
REAL_HUNKS = pytest.mark.skip(
    reason="depende de dado real do contrato — removido na versão pública")


def unit(*paragraphs: str, scope: str = "section:T") -> TextUnit:
    u = TextUnit(scope)
    for p in paragraphs:
        u.add(p)
    return u


def blocking_checks(report) -> set[str]:
    return {d.check for d in report.differences if d.severity in (CRITICAL, MAJOR)}


# --------------------------------------------------------------------------- normalização


@pytest.mark.parametrize(("raw", "normalized"), [
    ("encontram-  se  aprovados", "encontram-se aprovados"),   # espaços especiais
    ("encontram- se aprovados", "encontram-se aprovados"),           # hífen de fim de linha
    ("NC- 525.1 e RD- 101", "NC-525.1 e RD-101"),                     # código quebrado pelo Word
    ("Grupo 2 – Gestão", "Grupo 2 - Gestão"),                         # travessão unificado
    ("Grupo 2 - Gestão", "Grupo 2 - Gestão"),                         # hífen espaçado fica
    ("“aspas” e ‘simples’", "\"aspas\" e 'simples'"),
    ("▪ item", "• item"),
    ("2.4 Produto ......................... 27", "2.4 Produto 27"),  # pontilhado do sumário
    ("Pavimen­tação", "Pavimentação"),                           # hífen discricionário
])
def test_normalization_only_erases_layout(raw, normalized):
    assert normalize_strict(raw) == normalized


def test_normalization_preserves_case_accents_and_punctuation():
    """A régua estrita: caixa, acento e pontuação são texto (o v3 dobrava caixa e acento)."""
    assert tokens("Todas") != tokens("todas")
    assert tokens("análise") != tokens("analise")
    assert tokens("aprovado;") != tokens("aprovado.")
    assert tokens("três licenças") == ["três", "licenças"]


def test_every_visible_character_is_in_some_token():
    """'(DUP_ e' (anomalia P2.2_DUP_PARENTESE): o '_' é token — antes da correção do
    tokenizador ele sumia e a troca '_' -> ')' não era vista."""
    assert tokens("(DUP_ e") == ["(", "DUP", "_", "e"]
    assert tokens("NC-525.1, 01/08/2026; 1.234,56%") == [
        "NC-525.1", ",", "01/08/2026", ";", "1.234,56", "%"]
    text_ = "Projeto (OAE) – 1º nível: 40% | ¶ ® x"
    assert "".join(tokens(text_)) == "".join(normalize_strict(text_).split())


def test_signatory_name_becomes_a_hash_token():
    texts = ["Capital, 09 de Setembro de 2026", "Eng° Fulana de Teste Silva",
             "Programa - Consórcio Estruturador do Programa"]
    masked = mask_signatory(texts)
    assert all("Fulana" not in t for t in masked)
    assert "⟨signatário:" in masked[1]
    other = mask_signatory([texts[0], "Eng° Beltrana de Teste Souza", texts[2]])
    assert other[1] != masked[1]                       # outro nome = outro token
    assert mask_signatory(["sem assinatura"]) == ["sem assinatura"]


# --------------------------------------------------------------------------- hunks


def test_hunk_kinds_anchor_and_context():
    ref = unit("O Produto 2.1 , referente ao Relatório , é assim descrita no Termo de Referência .")
    gen = unit("O Produto 2.1 , referente ao Relatório , é assim descrito no Termo de Referência .")
    (h,) = diff_unit(ref, gen, "section:T")
    assert (h.kind, h.reference_text, h.generated_text) == ("replace", "descrita", "descrito")
    assert h.anchor == paragraph_anchor(ref.paragraphs[0])
    assert len(h.context_before) == CONTEXT_TOKENS
    assert len(h.context_after) == 5                   # fim da unidade: o que houver
    assert h.context_before[-2:] == ("é", "assim") and h.context_after[:2] == ("no", "Termo")
    inserted = diff_unit(ref, unit(ref.paragraphs[0] + " Novo."), "section:T")
    assert [(x.kind, x.generated_text) for x in inserted] == [("insert", "Novo .")]
    deleted = diff_unit(unit("A B C D"), unit("A D"), "section:T")
    assert [(x.kind, x.reference_text) for x in deleted] == [("delete", "B C")]
    assert diff_unit(ref, unit(*ref.paragraphs), "section:T") == []


def test_close_changes_merge_into_one_hunk_and_far_ones_do_not():
    ref = unit("a b c d e f g h i j k l m n o p")
    near = diff_unit(ref, unit("a X c Y e f g h i j k l m n o p"), "section:T")
    assert [(h.reference_text, h.generated_text) for h in near] == [("b c d", "X c Y")]
    far = diff_unit(ref, unit("a X c d e f g h i j k l m n Y p"), "section:T")
    assert [(h.reference_text, h.generated_text) for h in far] == [("b", "X"), ("o", "Y")]


def test_unit_only_on_one_side_is_one_whole_hunk():
    (h,) = diff_unit(None, unit("Seção nova inteira."), "section:9")
    assert (h.kind, h.reference_text, h.anchor) == ("insert", "", "")


# --------------------------------------------------------------------------- PDFs sintéticos

TEXT_24 = [
    "Encontram-se algumas condicionantes próximas ao vencimento a serem apresentadas.",
    "Os relatórios semanais contemplam as atividades executadas no período.",
    "- Relatório Mensal de Obras;",
    "Aprovação: Todas as disciplinas encontram-se aprovadas;",
    "Publicação pela Casa Civil: Aguardando aceite da GDP;",
    "Análise GDP: Solicitado complementação, encontra-se em avaliação pela GDP.",
]


def pages_with(paragraphs: list[str], **kw) -> list[Page]:
    pages = synthetic_pages(declared_pages=10, **kw)
    pages.insert(7, Page(items=[text(p) for p in paragraphs]))
    return pages


@pytest.fixture(scope="module")
def workdir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("textdiff")


@pytest.fixture(scope="module")
def ref24(workdir) -> dict:
    return facts_of(pages_with(TEXT_24), workdir / "ref24.pdf")


def variant(workdir: Path, name: str, old: str, new: str | None) -> dict:
    paragraphs = [p for p in TEXT_24 if not (new is None and p == old)]
    if new is not None:
        paragraphs = [p.replace(old, new, 1) for p in paragraphs]
    assert paragraphs != TEXT_24
    return facts_of(pages_with(paragraphs), workdir / f"{name}.pdf")


def test_same_text_passes_with_no_hunk(ref24, workdir):
    same = facts_of(pages_with(TEXT_24), workdir / "same24.pdf")
    report = compare(ref24, same, report_number=14)
    assert report.passed, report.reasons
    assert report.find("text_diff") == [] and report.metrics["text_diff"]["hunks"] == 0


# As 13 mutações de texto do QA3-E que passavam no comparador 3.0, em miniatura: cada uma
# reprova pelo `text_diff` (o v3 não as via — os fatos não mudam ou ficam fora do vocabulário).
@pytest.mark.parametrize(("name", "old", "new"), [
    ("quantificador", "algumas condicionantes", "todas as condicionantes"),
    ("verbo_de_estado", "relatórios semanais", "relatórios quinzenais"),
    ("item_curto_apagado", "- Relatório Mensal de Obras;", None),
    ("nem_todas", "Aprovação: Todas", "Aprovação: Nem todas"),
    ("status_fora_do_vocabulario", "Aguardando aceite da GDP", "Publicada, aceite da GDP"),
    ("gdp_dispensado", "Solicitado complementação", "Dispensado complementação"),
    ("caixa", "Aprovação: Todas", "Aprovação: todas"),
    ("pontuacao", "aprovadas;", "aprovadas."),
])
def test_v3_blind_text_mutations_fail_by_the_strict_diff(ref24, workdir, name, old, new):
    report = compare(ref24, variant(workdir, name, old, new), report_number=14)
    assert not report.passed
    hits = [d for d in report.find("text_diff") if d.severity == CRITICAL]
    assert hits and all(d.scope == "section:2.4.2" for d in hits), hits


@pytest.mark.parametrize(("name", "spec", "words"), [
    ("branqueado", {"op": "cover_text", "page": 8, "needle": "algumas condicionantes",
                    "part": "algumas"}, {"algumas"}),
    ("texto_branco", {"op": "rewrite_lines", "items": [{
        "page": 8, "needle": "Aprovação: Todas as disciplinas encontram-se aprovadas;",
        "text": "Aprovação: Todas as disciplinas encontram-se aprovadas;",
        "color": (1, 1, 1)}]}, {"Aprovação:", "Todas", "disciplinas", "aprovadas;"}),
])
def test_text_that_is_extracted_but_not_visible_is_critical(workdir, name, spec, words):
    """QA4-E (MAJOR → verificação `text_visibility`, extrator 3.2): coberto por um retângulo da
    cor do fundo, ou escrito na cor do fundo, o texto continua extraível — o diff de texto não
    vê nada e o leitor não lê. O controle (mesmo PDF sem a mutação) tem 0 palavra invisível."""
    import pymupdf

    from prog_g2_report.qa.extract import extract_facts
    from prog_g2_report.qa.mutate import _pdf
    from fixtures.qa_synthetic import write_pdf

    source = write_pdf(pages_with(TEXT_24), workdir / f"vis_{name}_src.pdf")
    reference = extract_facts(source)
    assert not any(p["invisible_words"] for p in reference["pages"])
    control = compare(reference, reference, report_number=14)
    assert control.passed and control.metrics["text_visibility"] == {"invisible_words": 0}
    doc = pymupdf.open(source)
    _pdf(doc, spec)
    mutated = workdir / f"vis_{name}.pdf"
    doc.save(mutated)
    doc.close()
    report = compare(reference, extract_facts(mutated), report_number=14)
    hits = [d for d in report.find("text_visibility") if d.severity == CRITICAL]
    assert not report.passed and words <= {d.value for d in hits}
    assert {d.scope for d in hits} == {"page:8"}
    assert [d for d in report.find("text_diff") if d.severity == CRITICAL] == []  # tokens iguais


def test_toc_line_must_match_the_heading_and_page_of_the_body(workdir):
    """Sumário do gerado contra o próprio corpo (`toc_consistency`, nunca permitível) e contra
    a referência (`text_diff` do SUMARIO)."""
    pages = synthetic_pages()
    reference = facts_of(pages, workdir / "toc_ref.pdf")
    wrong = synthetic_pages()
    wrong[1].items[1] = text("1 APRESENTAÇÃO ........ 5")
    report = compare(reference, facts_of(wrong, workdir / "toc_wrong.pdf"), report_number=14)
    toc = report.find("toc_consistency")
    assert [(d.kind, d.reference, d.generated) for d in toc] == [("delta", 3, 5)]
    assert {d.scope for d in report.find("text_diff")} == {"section:SUMARIO"}
    renamed = synthetic_pages()
    renamed[1].items[1] = text("1 INTRODUÇÃO ........ 3")
    report = compare(reference, facts_of(renamed, workdir / "toc_name.pdf"), report_number=14)
    assert [d.kind for d in report.find("toc_consistency")] == ["missing"]
    assert compare(reference, reference, report_number=14).find("toc_consistency") == []
    assert reference["sections"]["SUMARIO"]["segments"]


def test_signatory_change_is_a_hunk_without_the_name(workdir):
    a = facts_of(synthetic_pages(signatory="Fulana de Teste Silva"), workdir / "sig_a.pdf")
    b = facts_of(synthetic_pages(signatory="Beltrana de Teste Souza"), workdir / "sig_b.pdf")
    report = compare(a, b, report_number=14)
    hunks = report.find("text_diff", scope="section:ENCERRAMENTO")
    assert hunks and not report.passed
    rendered = report.to_markdown() + json.dumps(report.to_dict(), ensure_ascii=False)
    assert "Fulana" not in rendered and "Beltrana" not in rendered


# --------------------------------------------------------------------------- hunks aprovados


def test_approved_hunk_turns_the_exact_difference_into_allowed(ref24, workdir):
    gen = variant(workdir, "aprov", "relatórios semanais", "relatórios quinzenais")
    hunks = approve_all(ref24, gen, {"dec": "DEC-007"})
    assert hunks.status == "FROZEN" and len(hunks.hunks) == 1
    report = compare(ref24, gen, report_number=14, approved_hunks=hunks)
    assert report.passed, report.reasons
    (d,) = report.find("text_diff")
    assert d.severity == ALLOWED and d.original_severity == CRITICAL
    assert d.allowance_id == hunks.hunks[0].id and d.allowance_reference == "DEC-007"
    # a mesma posição com outra palavra: hunk novo CRITICAL + aprovação órfã (aviso)
    other = variant(workdir, "aprov_outro", "relatórios semanais", "relatórios mensais")
    report = compare(ref24, other, report_number=14, approved_hunks=hunks)
    assert not report.passed
    assert [d.severity for d in report.find("text_diff")] == [CRITICAL]
    assert report.approved_hunks_orphans == [hunks.hunks[0].id]
    assert any("aprovação órfã" in w for w in report.warnings)


def test_approved_hunks_are_not_valid_for_another_report_number(ref24, workdir):
    gen = variant(workdir, "num", "relatórios semanais", "relatórios quinzenais")
    hunks = approve_all(ref24, gen, {"dec": "DEC-007"})
    with pytest.raises(AllowanceError, match="nº 14 usados no nº 13"):
        compare(ref24, gen, report_number=13, approved_hunks=hunks)


def test_reverting_to_the_published_text_is_critical_not_just_an_orphan(ref24, workdir):
    """Regressão que copia a anomalia: o gerado volta ao texto da referência onde o hunk
    aprovado exige a correção. Sem diff no lugar, só a aprovação órfã avisaria — e o golden
    passaria (QA do SS: 'r4_ressalva_generalizada'). Agora é CRITICAL `reverted`."""
    gen = variant(workdir, "rev", "relatórios semanais", "relatórios quinzenais")
    hunks = approve_all(ref24, gen, {"dec": "DEC-007"})
    report = compare(ref24, ref24, report_number=14, approved_hunks=hunks)
    assert not report.passed
    (d,) = report.find("text_diff")
    assert (d.kind, d.severity, d.context["approved_hunk"]) == (
        "reverted", CRITICAL, hunks.hunks[0].id)


def test_stale_approval_is_only_an_orphan_warning(ref24):
    """Hunk aprovado cujo trecho não existe nem na referência (conjunto desatualizado): aviso
    de aprovação órfã, sem mudar o veredito."""
    stale = parse_approved_hunks({
        "status": "FROZEN", "version": "t", "report_number": 14,
        "comparator_version": COMPARATOR_VERSION,
        "hunks": [{"id": "HNK-T-001", "section": "section:2.4.2", "anchor": "0" * 12,
                   "position": NO_BLOCK,
                   "context_before": ["inexistente"], "context_after": ["também"],
                   "reference_text": "x", "generated_text": "y",
                   "reference": {"dec": "DEC-007"}}]})
    report = compare(ref24, ref24, report_number=14, approved_hunks=stale)
    assert report.passed, report.reasons
    assert report.approved_hunks_orphans == ["HNK-T-001"]
    assert report.warnings and "aprovação órfã: HNK-T-001" in report.warnings[0]
    assert report.metrics["text_diff"]["orphans"] == ["HNK-T-001"]


def test_pending_hunk_marks_the_real_hunk_and_never_allows_it(ref24, workdir):
    """`pending`: o hunk ESPERADO de um builder que ainda não entrou. O hunk real no mesmo
    parágrafo sai CRITICAL marcado; quando o gerado traz o texto esperado, sai ALLOWED."""
    expected = variant(workdir, "pend_exp", "relatórios semanais", "relatórios quinzenais")
    current = variant(workdir, "pend_cur", "relatórios semanais", "relatórios mensais")
    data = draft_hunks(compare(ref24, expected, report_number=14,
                               approved_hunks=HunkSet.empty(14)))
    data["hunks"][0].update(reference={"dec": "DEC-007"}, pending="builder X")
    data.update(status="FROZEN", version="t")
    hunks = parse_approved_hunks(data)
    report = compare(ref24, current, report_number=14, approved_hunks=hunks)
    (d,) = report.find("text_diff")
    assert d.severity == CRITICAL and d.context["pending"] == "builder X"
    assert "PENDENTE" in d.message and not report.passed
    assert report.metrics["text_diff"]["pending"] == 1
    assert any("pendente (builder X)" in w for w in report.warnings)
    ok = compare(ref24, expected, report_number=14, approved_hunks=hunks)
    assert ok.passed and ok.find("text_diff")[0].severity == ALLOWED


def test_identical_hunks_need_one_approval_each(workdir):
    """O mesmo parágrafo padronizado em duas rodovias, com a mesma troca e o mesmo contexto:
    cada lugar precisa da sua aprovação (v4.1: a posição distingue; `occurrence` saiu)."""
    para = "Aceitação: todas as disciplinas do Viário Principal foram aceitas em 1º nível;"
    sep = "Texto separador com palavras suficientes para isolar os dois blocos iguais aqui."
    ref = facts_of(pages_with([sep, para, sep, para, sep]), workdir / "occ_ref.pdf")
    changed = para.replace("foram", "encontram-se")
    gen = facts_of(pages_with([sep, changed, sep, changed, sep]), workdir / "occ_gen.pdf")
    hunks = approve_all(ref, gen, {"dec": "DEC-007"})
    assert len({h.reference_span for h in hunks.hunks}) == 2
    assert compare(ref, gen, report_number=14, approved_hunks=hunks).passed
    first_only = HunkSet(**{**hunks.__dict__, "hunks": hunks.hunks[:1]})
    report = compare(ref, gen, report_number=14, approved_hunks=first_only)
    assert sorted(d.severity for d in report.find("text_diff")) == [ALLOWED, CRITICAL]
    with pytest.raises(AllowanceError, match="chaves desconhecidas"):
        parse_approved_hunks(hunk_set(occurrence=2))


# --------------------------------------------------------------------------- v4.1 posição

# Blocos de rodovia como no 2.2 do nº 14: o mesmo "Aprovação: Todas …;" nas três rodovias; o
# controle qualifica a ressalva da DUP na RD-103 e na RD-104, não na RD-102A.
ROAD_PARAS = {road: [f"Referente ao acompanhamento de projeto executivo da Rodovia {road}:",
                     "- Disciplinas da Fase de Estudos:",
                     "- Aceitação: todas as disciplinas da Fase de Estudos foram aceitas;",
                     "- Aprovação: Todas as disciplinas encontram-se aprovadas;"]
              for road in ("RD-103", "RD-102A", "RD-104")}
DUP = (" A Documentação para Declaração de Utilidade Pública (DUP) encontra-se aprovada com "
       "ressalva;")


def road_text(with_dup: set[str]) -> list[str]:
    out = []
    for road, paras in ROAD_PARAS.items():
        last = paras[-1].replace("aprovadas;", "aprovadas." + DUP) if road in with_dup else (
            paras[-1])
        out += [*paras[:-1], last]
    return out


@pytest.fixture(scope="module")
def roads(workdir) -> dict:
    ref = facts_of(pages_with(road_text(set())), workdir / "roads_ref.pdf")
    control = facts_of(pages_with(road_text({"RD-103", "RD-104"})), workdir / "roads_ctl.pdf")
    hunks = approve_all(ref, control, {"dec": "DEC-015"})
    return {"ref": ref, "control": control, "hunks": hunks}


def test_hunk_records_the_structural_position():
    ref = TextUnit("section:T")
    gen = TextUnit("section:T")
    for unit, last in ((ref, "Todas aprovadas ;"), (gen, "Todas aprovadas . DUP com ressalva ;")):
        unit.add("Rodovia RD-103 :", "RD-103#1")
        unit.add("• Disciplinas da Fase de Estudos :", "RD-103#1 > FASE")
        unit.add("o Aceitação : todas aceitas ;", "RD-103#1 > FASE")
        unit.add(last, "RD-103#1 > FASE")
    (h,) = diff_unit(ref, gen, "section:T")
    assert (h.block, h.block_paragraph, h.generated_block) == (
        "RD-103#1 > FASE", 2, "RD-103#1 > FASE")
    assert h.reference_span == (len(ref.tokens) - 1, len(ref.tokens) - 1)
    assert h.position == {"block": "RD-103#1 > FASE", "paragraph": 2,
                          "tokens": list(h.reference_span), "generated_block": "RD-103#1 > FASE"}
    assert h.key != diff_unit(ref, gen, "section:U")[0].key            # unidade faz parte


def test_control_passes_and_every_approval_is_fixed_on_its_road(roads):
    report = compare(roads["ref"], roads["control"], report_number=14,
                     approved_hunks=roads["hunks"])
    assert report.passed, report.reasons
    blocks = sorted(h.block for h in roads["hunks"].hunks)
    assert blocks == ["RD-103#1 > DISCIPLINAS DA FASE DE ESTUDOS",
                      "RD-104#1 > DISCIPLINAS DA FASE DE ESTUDOS"]
    assert all(h.generated_block == h.block for h in roads["hunks"].hunks)


@pytest.mark.parametrize(("name", "with_dup"), [
    ("RD-103_para_RD-102A", {"RD-102A", "RD-104"}),     # QA4-E (a)
    ("RD-104_para_RD-102A", {"RD-103", "RD-102A"}),     # QA4-E (c)
    ("tres_rodovias", {"RD-103", "RD-102A", "RD-104"}),
])
def test_approved_text_moved_to_a_sibling_road_fails(roads, workdir, name, with_dup):
    """QA4-E BLOCKS_GATE: o mesmo texto aprovado (ressalva da DUP) em outra rodovia. No 4.0 a
    âncora era o hash do parágrafo, igual nas três, e o contexto também: as duas aprovações
    casavam com a 1ª e a 2ª ocorrência, onde quer que estivessem, e o golden passava. No 4.1
    o hunk na RD-102A tem outra posição (bloco e tokens): CRITICAL; a RD-103 que voltou ao
    publicado sai `reverted`."""
    moved = facts_of(pages_with(road_text(with_dup)), workdir / f"roads_{name}.pdf")
    report = compare(roads["ref"], moved, report_number=14, approved_hunks=roads["hunks"])
    assert not report.passed
    critical = [d for d in report.find("text_diff") if d.severity == CRITICAL]
    assert {d.context["position"]["block"] for d in critical if d.kind != "reverted"} == {
        "RD-102A#1 > DISCIPLINAS DA FASE DE ESTUDOS"}
    if with_dup != {"RD-103", "RD-102A", "RD-104"}:
        assert [d.kind for d in critical if d.kind == "reverted"] == ["reverted"]


def test_reverted_text_is_searched_only_in_the_block_of_the_hunk(roads):
    """O texto publicado ('… aprovadas;') existe legitimamente na RD-102A; o órfão da RD-103
    só é `reverted` se o texto voltar NO BLOCO dele. Aqui o gerado não tem mais nenhum hunk
    nem o texto em lugar algum: só órfão, sem `reverted` falso."""
    gone = json.loads(json.dumps(roads["control"]))
    for seg in gone["sections"]["2.4.2"]["segments"]:
        if seg.get("block", "").startswith("RD-103#1") and "Aprovação" in seg["text"]:
            seg["text"] = "- Aprovação: Todas as disciplinas encontram-se aprovadas com ressalva;"
    report = compare(roads["ref"], gone, report_number=14, approved_hunks=roads["hunks"])
    kinds = [d.kind for d in report.find("text_diff") if d.severity == CRITICAL]
    assert kinds and "reverted" not in kinds
    assert report.approved_hunks_orphans == [h.id for h in roads["hunks"].hunks
                                             if h.block.startswith("RD-103")]


def test_narrative_fact_only_covered_by_an_approved_hunk_in_the_same_block(workdir):
    """QA4-E: `_cover_by_hunks` rebaixava QUALQUER `narrative_facts` de uma unidade com todos
    os hunks aprovados. No 4.1 o fato só sai ALLOWED se um hunk aprovado do MESMO bloco o
    explicar. Prova: a quebra de parágrafo perdida na RD-103 ('A) RD-103: • Análise Programa: Não
    aprovado;') não muda nenhum token (o diff de texto não vê), mas o status passa a ser do
    campo errado — no 4.0 sairia ALLOWED pela troca aprovada na RD-102A; no 4.1 é CRITICAL."""
    paras = ["Documentação para Declaração de Utilidade Pública:", "A) RD-103:",
             "- Análise Programa: Não aprovado;", "B) RD-102A:", "- Análise Programa: Não aprovado;",
             "Texto final do bloco com palavras suficientes para separar."]
    ref = facts_of(pages_with(paras), workdir / "fact_ref.pdf")
    fixed = [p if n != 4 else "- Análise Programa: Em análise;" for n, p in enumerate(paras)]
    gen = facts_of(pages_with(fixed), workdir / "fact_gen.pdf")
    hunks = approve_all(ref, gen, {"dec": "DEC-007"})
    ok = compare(ref, gen, report_number=14, approved_hunks=hunks)
    assert ok.passed, ok.reasons
    facts = ok.find("narrative_facts")
    assert facts and all(d.severity == ALLOWED and d.context["block"] == "RD-102A#1"
                         and hunks.hunks[0].id in d.allowance_reference for d in facts)
    merged = json.loads(json.dumps(gen))
    from prog_g2_report.qa.mutate import _facts
    _facts(merged, {"op": "f_merge_seg", "section": "2.4.2", "needle": "A) RD-103:"})
    report = compare(ref, merged, report_number=14, approved_hunks=hunks)
    assert [d.severity for d in report.find("text_diff")] == [ALLOWED]   # nenhum token mudou
    blocking = [d for d in report.find("narrative_facts") if d.severity == CRITICAL]
    assert blocking and all(d.context["block"] == "RD-103#1" and d.context.get("unexplained")
                            for d in blocking)
    assert not report.passed
    assert report.metrics["text_diff"]["v3_unexplained"] == len(blocking)


def test_v3_differences_are_judged_by_their_own_hunk_without_cascade(ref24, workdir):
    """Diagnóstico redundante: os fatos v3 da troca aprovada saem ALLOWED pelo SEU hunk. Um
    outro trecho não aprovado na mesma seção reprova sozinho (CRITICAL) e não derruba mais os
    fatos já explicados (v4.1, orquestrador: no 4.0 um hunk em aberto levava em cascata todas
    as `hunks:section:*` da seção — 52 CRITICAL + 1 MAJOR no nº 14 v6)."""
    gen = variant(workdir, "cov", "Aprovação: Todas", "Aceitação: Todas")
    hunks = approve_all(ref24, gen, {"dec": "DEC-007"})
    report = compare(ref24, gen, report_number=14, approved_hunks=hunks)
    assert report.passed
    covered = [d for d in report.differences if d.allowance_id == "hunks:section:2.4.2"]
    assert covered and report.metrics["text_diff"]["v3_covered"] == len(covered)
    assert {d.check for d in covered} >= {"narrative_facts"}
    both = [p.replace("Aprovação: Todas", "Aceitação: Todas")
            .replace("relatórios semanais", "relatórios quinzenais") for p in TEXT_24]
    worse = facts_of(pages_with(both), workdir / "cov_worse.pdf")
    report = compare(ref24, worse, report_number=14, approved_hunks=hunks)
    assert not report.passed
    still = {(d.check, d.kind, str(d.value)) for d in report.differences
             if d.allowance_id == "hunks:section:2.4.2"}
    assert {(d.check, d.kind, str(d.value)) for d in covered
            if d.check == "narrative_facts"} <= still
    blocking = [d for d in report.differences if d.severity in (CRITICAL, MAJOR)]
    assert [(d.check, d.generated) for d in blocking if d.check == "text_diff"] == [
        ("text_diff", "quinzenais")]
    assert not [d for d in blocking if d.check == "narrative_facts"]


def test_unapproved_hunk_facts_stay_blocking_even_next_to_approved_ones(ref24, workdir):
    """O outro lado do não-cascata: o fato que o hunk EM ABERTO muda não é explicado pelos
    aprovados da seção (grupo com hunk em aberto não explica nada)."""
    gen = variant(workdir, "cov2", "Aprovação: Todas", "Aceitação: Todas")
    hunks = approve_all(ref24, gen, {"dec": "DEC-007"})
    both = [p.replace("Aprovação: Todas", "Aceitação: Todas")
            .replace("Aguardando aceite", "Publicada") for p in TEXT_24]
    worse = facts_of(pages_with(both), workdir / "cov2_worse.pdf")
    report = compare(ref24, worse, report_number=14, approved_hunks=hunks)
    assert not report.passed
    critical_text = [d for d in report.find("text_diff") if d.severity == CRITICAL]
    assert len(critical_text) == 1 and "Publicada" in critical_text[0].generated


def test_text_diff_and_toc_consistency_are_never_allowable_by_allowance():
    for check in ("text_diff", "toc_consistency"):
        with pytest.raises(AllowanceError, match="nunca é permitível"):
            parse_allowances({"status": "FROZEN", "comparator_version": COMPARATOR_VERSION,
                              "allowances": [{
                                  "id": "ALW-T-1", "report_number": 14,
                                  "reference": {"dec": "DEC-007"}, "dimension": "CONTENT",
                                  "check": check, "scope": "section:2.4.2",
                                  "match": {"kind": "replace"}}]})


NO_BLOCK = {"block": "", "paragraph": 0, "tokens": [0, 1], "generated_block": ""}
BASE_HUNK = {"id": "HNK-T-001", "section": "section:2.4.2", "anchor": "a" * 12,
             "position": NO_BLOCK,
             "context_before": ["a"], "context_after": ["b"], "reference_text": "x",
             "generated_text": "y", "reference": {"dec": "DEC-007"}}


def hunk_set(**changes) -> dict:
    return {"status": "FROZEN", "version": "t", "report_number": 14,
            "comparator_version": COMPARATOR_VERSION, "hunks": [dict(BASE_HUNK, **changes)]}


@pytest.mark.parametrize(("data", "message"), [
    ({**hunk_set(), "status": "DRAFT"}, "CONGELADOS"),
    ({**hunk_set(), "comparator_version": "3.0"}, "comparador"),
    ({**hunk_set(), "report_number": "14"}, "report_number inteiro"),
    ({**hunk_set(), "extra": 1}, "chaves desconhecidas"),
    (hunk_set(reference=None), "hunk sem justificativa"),          # rascunho não classificado
    (hunk_set(reference={}), "hunk sem justificativa"),
    (hunk_set(reference={"anomaly": "NAO_EXISTE"}), "não catalogada"),
    (hunk_set(reference={"anomaly": "APRESENTACAO_MES_REFERENCIA"}), "não catalogada"),  # é nº 13
    (hunk_set(reference={"dec": "DEC-999"}), "não existe"),
    (hunk_set(reference={"issue": "X"}), "hunk sem justificativa"),
    (hunk_set(context_before=["a"] * 7), "até 6 tokens"),
    (hunk_set(generated_text="x"), "textos diferentes"),
    (hunk_set(reference_text="", generated_text=""), "textos diferentes"),
    (hunk_set(anchor="xyz"), "anchor"),
    (hunk_set(occurrence=2), "chaves desconhecidas"),              # v4.1: a posição distingue
    ({**hunk_set(), "comparator_version": "4.0"}, "comparador"),  # formato sem posição
    (dict(hunk_set(), hunks=[{k: v for k, v in BASE_HUNK.items() if k != "position"}]),
     "position"),
    (hunk_set(position={**NO_BLOCK, "extra": 1}), "position"),
    (hunk_set(position={**NO_BLOCK, "paragraph": -1}), "paragraph"),
    (hunk_set(position={**NO_BLOCK, "paragraph": True}), "paragraph"),
    (hunk_set(position={**NO_BLOCK, "block": None}), "block"),
    (hunk_set(position={**NO_BLOCK, "tokens": [2, 1]}), "tokens"),
    (hunk_set(position={**NO_BLOCK, "tokens": [0]}), "tokens"),
    (hunk_set(position={**NO_BLOCK, "tokens": [0, 2]}), "não tem os 1 tokens"),
    (hunk_set(reference_text="", position={**NO_BLOCK, "tokens": [3, 4]}), "não tem os 0"),
    (hunk_set(pending=""), "pending"),
    (hunk_set(note="x"), "chaves desconhecidas"),
])
def test_invalid_approved_hunks_are_rejected(data, message):
    with pytest.raises(AllowanceError, match=message):
        parse_approved_hunks(data)


def test_duplicate_hunk_or_id_is_rejected():
    data = hunk_set()
    data["hunks"].append(dict(BASE_HUNK, id="HNK-T-002"))
    with pytest.raises(AllowanceError, match="hunk repetido"):
        parse_approved_hunks(data)
    data["hunks"][1]["position"] = {**NO_BLOCK, "tokens": [5, 6]}     # outro lugar: outro hunk
    assert len(parse_approved_hunks(data).hunks) == 2
    data["hunks"][1]["position"] = {**NO_BLOCK, "block": "RD-103#1"}
    assert len(parse_approved_hunks(data).hunks) == 2
    data["hunks"][1]["id"] = "HNK-T-001"
    with pytest.raises(AllowanceError, match="id repetido"):
        parse_approved_hunks(data)


def test_frozen_file_is_loaded_with_sha256_and_edits_are_refused(tmp_path):
    path = tmp_path / "n14.yaml"
    path.write_text(yaml.safe_dump(hunk_set(), allow_unicode=True), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    loaded = load_approved_hunks(path, expected_sha256=digest)
    assert loaded.status == "FROZEN" and loaded.sha256 == digest and loaded.source == str(path)
    path.write_text(path.read_text(encoding="utf-8") + "# editado\n", encoding="utf-8")
    with pytest.raises(AllowanceError, match="difere do registrado"):
        load_approved_hunks(path, expected_sha256=digest)
    # pelo registro das allowances (caminho absoluto para o teste)
    registered = parse_allowances({"status": "FROZEN", "comparator_version": COMPARATOR_VERSION,
                                   "approved_hunks": [{"report_number": 14, "file": str(path),
                                                       "sha256": digest}]})
    with pytest.raises(AllowanceError, match="difere do registrado"):
        registered.approved_hunks(14)
    assert registered.approved_hunks(13).hunks == ()
    # caminho dado à mão (CLI --approved-hunks): o mesmo sha256 registrado, ou recusa
    with pytest.raises(AllowanceError, match="difere do registrado"):
        registered.load_hunks_file(path, 14)
    with pytest.raises(AllowanceError, match="não registram hunks aprovados para o nº 13"):
        registered.load_hunks_file(path, 13)
    assert registered.hunk_sha256(14) == digest and registered.hunk_sha256(13) is None


def test_draft_lists_every_hunk_and_is_refused_until_classified(ref24, workdir):
    gen = variant(workdir, "draft", "relatórios semanais", "relatórios quinzenais")
    report = compare(ref24, gen, report_number=14, approved_hunks=HunkSet.empty(14))
    draft = draft_hunks(report)
    assert draft["status"] == "DRAFT" and len(draft["hunks"]) == len(report.find("text_diff"))
    assert all(h["reference"] is None for h in draft["hunks"])
    with pytest.raises(AllowanceError):
        parse_approved_hunks({**draft, "status": "FROZEN"})


# --------------------------------------------------------------------------- repositório


@REAL_HUNKS
def test_repository_allowances_v110_register_the_frozen_hunk_sets():
    allowances = load_allowances()
    assert allowances.version == "1.10" and allowances.comparator_version == "4.1"
    assert allowances.warnings == ()
    registry = {n: (f, sha) for n, f, sha in allowances.hunk_files}
    assert set(registry) == {13, 14}
    for number, (file, sha) in registry.items():
        path = ROOT / file
        assert path.parent == HUNKS_DIR and path.name == f"n{number}.yaml"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
        hunks = allowances.approved_hunks(number)
        assert hunks.status == "FROZEN" and hunks.sha256 == sha
        assert hunks.report_number == number and hunks.comparator_version == "4.1"
        assert hunks.version == "1.2"
        assert [h.id for h in hunks.hunks] == [f"HNK-{number}-{i:03d}"
                                               for i in range(1, len(hunks.hunks) + 1)]
        assert not [h.id for h in hunks.hunks if h.pending], "controle v5 já tem o TT"


@REAL_HUNKS
def test_v19_content_allowances_migrated_to_hunks():
    """Toda allowance de CONTENT da v1.8 virou hunk com a mesma anomalia/DEC; ficam só as de
    geometria/estrutura e as da paginação do nº 13 (DEC-015). ALW-14-031, ALW-13-035 e
    ALW-13-037 (ressalva generalizada) não existem mais."""
    allowances = load_allowances()
    content = [a.id for a in allowances.allowances if a.dimension == "CONTENT"]
    assert content == ["ALW-13-041"]
    ids = {a.id for a in allowances.allowances}
    assert not ids & {"ALW-14-031", "ALW-13-035", "ALW-13-037", "ALW-14-003", "ALW-14-024"}
    v18 = {
        14: {"APRESENTACAO_NUMERO_RELATORIO", "P2.4_FAIXA_RO_SEMANA_REPETIDA",
             "CONTROLE_DE_PRODUTOS_CABECALHO_COLUNA_2", "P2.1_IDENTIFICACAO_RODOVIA",
             "CONTROLE_PRODUTOS_DESCRICAO_CORTADA", "P2.4_FRASE_TRUNCADA_MEDICOES",
             "P2.2_DUP_PARENTESE", "P2.2_DUP_RD101_SEM_VALOR", "DEC-007",
             "P2.4_RELATORIO_CONSOLIDADO_GRAFIA", "P2.2_EXTERNAL_PROG_CONTRADIZ_PLANILHA",
             "P2.2_APROVADOS_COM_RESSALVA_GENERALIZADO",
             "P2.2_PAVIMENTACAO_RD101_STATUS_DEFASADO", "P2.2_OAE_RD101_ACEITO_INCOMPLETO",
             "P2.4_ATAS_TEMAS_SEM_SUPORTE"},
        13: {"APRESENTACAO_MES_REFERENCIA", "CAPA_DATA_EMISSAO", "P2.4_FAIXA_RO_SEMANA_OMITIDA",
             "P2.4_BM_CODIGOS_RD103", "P2.1_IDENTIFICACAO_RODOVIA", "P2.1_RESUMO_BM_RODOVIAS",
             "P2.4_FRASE_TRUNCADA_MEDICOES", "P2.1_CLAUSULA_DISCIPLINAS_REMOVIDA",
             "P2.4_RCA_RODOVIA_DIVERGENTE", "P2.4_BM_EM_ELABORACAO_ORDEM",
             "P2.4_NC_FRASE_TRUNCADA", "P2.4_ATAS_TEMAS_SEM_SUPORTE",
             "P2.2_ROTULO_DISCIPLINAS_EM_REVISAO", "P2.2_PENDENTES_NAO_ENTREGUES_ADOCAO",
             "DEC-007", "P2.2_OAE_RD101_ACEITO_INCOMPLETO",
             "P2.2_APROVADOS_COM_RESSALVA_GENERALIZADO", "P2.2_PREDICADO_REPETIDO"},
    }
    for number, needed in v18.items():
        cited = set()
        for h in allowances.approved_hunks(number).hunks:
            cited |= {v for k, v in h.reference.items()}
        assert needed <= cited, (number, needed - cited)


def test_v19_page_allowances_only_for_the_n13_dec015_pagination():
    by_id = {a.id: a for a in load_allowances().allowances}
    page = {a.id for a in by_id.values()
            if a.check in {"page_count", "declared_pages", "orientation_run_length",
                           "heading_page"}}
    assert page == {"ALW-13-039", "ALW-13-040", "ALW-13-041"}
    for aid in page:
        a = by_id[aid]
        assert a.report_number == 13 and a.reference == {"dec": "DEC-015"}
        assert {"reference", "generated"} <= set(a.match) and "max_abs_delta" not in a.match
    assert (by_id["ALW-13-039"].match["reference"], by_id["ALW-13-039"].match["generated"]) == (
        43, 44)


@REAL_HUNKS
def test_n14_ressalva_hunks_are_per_discipline_one_by_one():
    """DEC-015: cada hunk da ressalva cita a anomalia e a DEC, no 2.2.2, com o texto exato;
    na RD-104 Principal o Geométrico sai 'aprovado' e a Terraplenagem 'com ressalva'; nenhum
    hunk aprova a forma generalizada antiga (apagar 'com ressalva' da RD-104)."""
    hunks = load_allowances().approved_hunks(14).hunks
    ressalva = [h for h in hunks if h.reference == {
        "anomaly": "P2.2_APROVADOS_COM_RESSALVA_GENERALIZADO", "dec": "DEC-015"}]
    assert len(ressalva) == 11 and {h.section for h in ressalva} == {"section:2.2.2"}
    rd104 = [(h.reference_text, h.generated_text) for h in ressalva
             if h.anchor == "f04fdbbb535a"]
    assert rd104 == [("e o", "encontra-se aprovado . O"),
                     ("encontram-se aprovados", "encontra-se aprovado")]
    assert not [h for h in hunks if h.reference_text == "com ressalva" and not h.generated_text]
    assert sum("ressalva" in h.generated_text for h in ressalva) == 8


@REAL_HUNKS
def test_n14_cut_description_and_column_label_are_exact_hunks():
    hunks = load_allowances().approved_hunks(14).hunks
    cut = [(h.section, h.reference_text, h.generated_text) for h in hunks
           if h.reference == {"anomaly": "CONTROLE_PRODUTOS_DESCRICAO_CORTADA"}]
    assert cut == [("block:2.2", "", "Interferência"), ("block:ANEXOS", "", "Interferência")]
    labels = {h.section for h in hunks if (h.reference_text, h.generated_text) == (
        "Parecer", "Manifestação")}
    assert labels == {"block:2.1", "block:2.2", "block:2.4", "block:ANEXOS"}


@REAL_HUNKS
def test_n13_master_list_residual_is_never_approved():
    """Resíduo Lista Mestra v134 × v162 (GAP-015): nenhum hunk aprovado no Controle de
    Produtos (só os rótulos não aparecem no nº 13) nem no total de anexos do Encerramento."""
    hunks = load_allowances().approved_hunks(13).hunks
    assert not [h.id for h in hunks if h.section.startswith("block:")]
    closing = [(h.reference_text, h.generated_text) for h in hunks
               if h.section == "section:ENCERRAMENTO"]
    assert sorted(closing) == [("43", "44"), ("três", "quatro")]      # paginação (DEC-015)
    assert not [h for h in hunks if "165" in h.reference_text or h.reference_text == "cinco"]


@REAL_HUNKS
def test_every_repository_hunk_cites_a_catalogued_anomaly_or_existing_dec():
    """O parser já recusa; aqui a contagem por referência que a Emmily revisa."""
    for number in (14, 13):
        hunks = load_allowances().approved_hunks(number).hunks
        assert all(h.reference and set(h.reference) <= {"anomaly", "dec"} for h in hunks)
        assert all(h.rationale for h in hunks)
    assert len(load_allowances().approved_hunks(14).hunks) == 113
    assert len(load_allowances().approved_hunks(13).hunks) == 117


def test_empty_hunk_set_and_allowance_set_defaults():
    assert HunkSet.empty(14).hunks == () and AllowanceSet.empty().hunk_files == ()


@REAL_HUNKS
def test_n14_dup_ressalva_pair_is_fixed_on_rd103_and_rd104():
    """QA4-E/QA4-H: HNK-14-058 e HNK-14-060 têm o MESMO texto ('A Documentação para
    Declaração de Utilidade Pública (DUP) encontra-se aprovada com ressalva'), e o parágrafo
    publicado é igual nas 3 rodovias com 'Todas … aprovadas'. Projetos v438: DUP 'Aprovada com
    ressalva' na RD-103 (linha 31) e na RD-104 (linha 83); na RD-102A (linha 7), 'Aprovado'."""
    by_id = {h.id: h for h in load_allowances().approved_hunks(14).hunks}
    a, b = by_id["HNK-14-058"], by_id["HNK-14-060"]
    assert (a.generated_text, a.context_before) == (b.generated_text, b.context_before)
    assert (a.block, a.generated_block) == ("RD-103#1 > DISCIPLINAS DA FASE DE ESTUDOS",) * 2
    assert (b.block, b.generated_block) == ("RD-104#1 > DISCIPLINAS DA FASE DE ESTUDOS",) * 2
    assert a.block_paragraph == b.block_paragraph == 2
    assert a.reference_span != b.reference_span
    assert not [h for h in by_id.values() if "RD-102A" in h.block and "DUP" in h.generated_text]


@REAL_HUNKS
def test_v12_hunks_of_the_v6_controls_one_per_place():
    """v1.2 (controles 14_v6/13_v6, modelo v0.14): crase e Análise Programa com ressalva, cada
    hunk fixo no seu lugar — a ressalva da matriz só nas 6 linhas que a v438 qualifica."""
    h14 = load_allowances().approved_hunks(14).hunks
    prog = [h for h in h14 if h.reference == {
        "anomaly": "P2.2_EXTERNAL_PROG_RESSALVA_OMITIDA", "dec": "DEC-015"}]
    assert sorted(h.block for h in prog) == sorted(
        ["RD-103#2", "RD-101#2", "RD-104#2", "RD-102A#3", "RD-103#4", "RD-101#4"])
    assert all((h.reference_text, h.generated_text) == ("", "com ressalva") for h in prog)
    assert all(h.section == "section:2.2.2" and h.generated_block == h.block for h in prog)
    for number in (14, 13):
        crase = [h for h in load_allowances().approved_hunks(number).hunks
                 if h.reference == {"anomaly": "CRASE_REFERENTE_AS", "dec": "DEC-007"}]
        assert sorted((h.section, h.reference_text, h.generated_text) for h in crase) == [
            ("section:2.1.2", "as", "às"), ("section:2.4.2", "as", "às")]
    by_id = {h.id: h for h in load_allowances().approved_hunks(13).hunks}
    assert by_id["HNK-13-020"].reference == {"anomaly": "P2.1_CLAUSULA_DISCIPLINAS_REMOVIDA"}


@REAL_HUNKS
def test_every_repository_hunk_has_a_position_inside_its_unit():
    """Posição bem formada e coerente: tokens do tamanho do texto de referência; bloco
    estrutural nos parágrafos de rodovia do 2.2/2.4, código da linha no Controle de Produtos."""
    for number in (14, 13):
        hunks = load_allowances().approved_hunks(number).hunks
        keys = {h.key for h in hunks}
        assert len(keys) == len(hunks)
        for h in hunks:
            start, end = h.reference_span
            assert end - start == (len(h.reference_text.split(" ")) if h.reference_text else 0)
            if h.section.startswith("block:"):
                assert h.block, h.id
        roads = [h for h in hunks if h.section == "section:2.2.2" and "ressalva" in
                 h.generated_text]
        assert roads and all(h.block.startswith("RD-") for h in roads)


def _load_cli():
    import importlib.util

    path = ROOT / "scripts" / "14_golden_compare.py"
    spec = importlib.util.spec_from_file_location("golden_compare_cli_v41", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_approved_hunks_path_must_have_the_registered_sha256(tmp_path, ref24, workdir):
    """QA4-E: `--approved-hunks` trocava o conjunto sem conferir nada. No 4.1 o caminho dado só
    vale com o sha256 registrado nas allowances para o relatório; senão código 2."""
    cli = _load_cli()
    gen = variant(workdir, "cli", "relatórios semanais", "relatórios quinzenais")
    ref_pdf, gen_pdf = tmp_path / "ref.pdf", tmp_path / "gen.pdf"
    from fixtures.qa_synthetic import write_pdf
    write_pdf(pages_with(TEXT_24), ref_pdf)
    write_pdf(pages_with([p.replace("relatórios semanais", "relatórios quinzenais")
                          for p in TEXT_24]), gen_pdf)
    draft = draft_hunks(compare(ref24, gen, report_number=14, approved_hunks=HunkSet.empty(14)))
    for h in draft["hunks"]:
        h["reference"] = {"dec": "DEC-007"}
    draft.update(status="FROZEN", version="t", generated_from=None)
    hunks_file = tmp_path / "n14.yaml"
    hunks_file.write_text(yaml.safe_dump(draft, allow_unicode=True), encoding="utf-8")
    digest = hashlib.sha256(hunks_file.read_bytes()).hexdigest()
    allow = tmp_path / "allow.yaml"

    def allowances(sha: str | None) -> None:
        data = {"status": "FROZEN", "version": "t", "comparator_version": COMPARATOR_VERSION,
                "allowances": []}
        if sha:
            data["approved_hunks"] = [{"report_number": 14, "file": str(hunks_file),
                                       "sha256": sha}]
        allow.write_text(yaml.safe_dump(data), encoding="utf-8")

    common = ["--reference", str(ref_pdf), "--generated", str(gen_pdf), "--report-number",
              "14", "--allowances", str(allow)]
    allowances(digest)
    assert cli.main([*common, "--out", str(tmp_path / "ok")]) == 0
    assert cli.main([*common, "--out", str(tmp_path / "ok2"),
                     "--approved-hunks", str(hunks_file)]) == 0
    other = tmp_path / "outro.yaml"                        # editado: mesmo conteúdo + linha
    other.write_text(hunks_file.read_text(encoding="utf-8") + "# editado\n", encoding="utf-8")
    assert cli.main([*common, "--out", str(tmp_path / "ko"), "--approved-hunks",
                     str(other)]) == 2
    allowances(None)                                       # nada registrado para o nº 14
    assert cli.main([*common, "--out", str(tmp_path / "ko2"), "--approved-hunks",
                     str(hunks_file)]) == 2
    assert cli.main([*common, "--out", str(tmp_path / "ko3")]) == 1   # sem hunks: CRITICAL
