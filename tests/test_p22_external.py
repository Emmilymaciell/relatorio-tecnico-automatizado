"""P2.2_DESAPROPRIACAO / P2.2_INTERFERENCIAS a partir de `inputs.p22_external_status` + Análise Programa
derivada da aba Projetos (`schema.derived.prog`). Fixtures sintéticas; golden contra o nº 14."""

from __future__ import annotations

import dataclasses
import json
import os
from datetime import date
from pathlib import Path

import pytest

from _p22_synthetic import EST, SEC, approved, in_analysis, late, project, rejected, sheet
from prog_g2_report.builder.blocks import load_blocks
from prog_g2_report.model import load_model
from prog_g2_report.render import p22_external as px
from prog_g2_report.sources import projects as pj

MODEL = load_model()
SCHEMA = MODEL["inputs"]["p22_external_status"]["schema"]
DERIVED = SCHEMA["derived"]["prog"]
HIGHWAYS = MODEL["contract"]["highways"]
BLOCKS = {b.block_id: b.raw for b in load_blocks()}
ORDER = ("RD-103", "RD-102A", "RD-101", "RD-104")
REF = date(2026, 9, 7)
DUP = "Documentação para Declaração de Utilidade Pública (DUP)"
DESAP = "Projeto de Desapropriação"
INTERF = "Projeto de Interferência de Iluminação e Rede Elétrica"


def _all_approved(*roads):
    rows = []
    for road in roads:
        rows += [approved("1.6", road, EST, DUP), approved("3.2", road, SEC, DESAP),
                 approved("3.5", road, SEC, INTERF)]
    return pj.from_rows(sheet(*rows))


PROJECTS = _all_approved(*ORDER, "RD-999")


def _render(block_id: str, status, order=ORDER, projects=PROJECTS, ref=REF):
    return px.render_external_block(block_id, BLOCKS[block_id], status, order, SCHEMA, HIGHWAYS,
                                    projects=projects, reference_date=ref)


def _dup(b="Valor B", c="Valor C"):
    return {"gdp": b, "casa_civil": c}


def _keys(block_id="P2.2_DESAPROPRIACAO", index=0):
    raw = BLOCKS[block_id]
    return (raw["matrices"][index] if "matrices" in raw else raw["matrix"])["keys"]


def test_schema_matrices_match_the_content_blocks():
    for mid, spec in SCHEMA["matrices"].items():
        matrices = px.block_matrices(spec["block"], BLOCKS[spec["block"]], SCHEMA)
        assert mid in matrices
        assert len(matrices[mid]["keys"]) == len(matrices[mid]["fields"])
        assert "prog" in matrices[mid]["fields"]
        assert mid in DERIVED["disciplines"]            # toda matriz tem a disciplina da planilha
    assert set(SCHEMA["layout"]) == set(px.BLOCK_IDS)
    assert DERIVED["source"] in MODEL["sources"]


def test_bad_schema_is_rejected():
    bad = {**SCHEMA, "matrices": {"dup": {**SCHEMA["matrices"]["dup"], "fields": ["prog"]}}}
    with pytest.raises(px.ExternalStatusError):
        px.render_external_block("P2.2_DESAPROPRIACAO", BLOCKS["P2.2_DESAPROPRIACAO"],
                                 {"RD-103": {"dup": _dup()}}, ORDER, bad, HIGHWAYS)
    no_text = {**SCHEMA, "derived": {"prog": {**DERIVED, "status_text": []}}}
    with pytest.raises(px.ExternalStatusError, match="status_text"):
        px.render_external_block("P2.2_DESAPROPRIACAO", BLOCKS["P2.2_DESAPROPRIACAO"],
                                 {"RD-103": {"dup": _dup()}}, ORDER, no_text, HIGHWAYS)


def test_no_input_is_skipped():
    for block_id in px.BLOCK_IDS:
        assert _render(block_id, None).status == "SKIPPED"
        assert _render(block_id, {}).status == "SKIPPED"


def test_roads_follow_order_and_aliases_are_canonical():
    status = {"rd-104": {"dup": _dup()}, "RD 102a": {"dup": _dup()}}
    out = _render("P2.2_DESAPROPRIACAO", status)
    groups = [p.text for p in out.paragraphs if p.kind == "group"]
    assert groups == ["RD-102A:", "RD-104:"]
    assert out.facts["matrices"] == {"dup": ["RD-102A", "RD-104"], "expropriation_project": []}


def test_layout_labels_lists_and_punctuation():
    status = {"RD-103": {"dup": _dup("Em análise.", "Aguardando")}}
    out = _render("P2.2_DESAPROPRIACAO", status)
    assert out.status == "OK"
    kinds = [p.kind for p in out.paragraphs]
    assert kinds[0] == "spacer" and kinds[-1] == "spacer"
    texts = [p.text for p in out.paragraphs]
    raw = BLOCKS["P2.2_DESAPROPRIACAO"]
    label = raw["fixed_parts"][SCHEMA["matrices"]["dup"]["label_part"]]["text"]
    assert label in texts
    # matriz sem rodovia não emite o rótulo
    other = raw["fixed_parts"][SCHEMA["matrices"]["expropriation_project"]["label_part"]]["text"]
    assert other not in texts
    items = [p for p in out.paragraphs if p.kind == "status"]
    keys = _keys()
    assert [p.text for p in items] == [f"{keys[0]} Aprovado;", f"{keys[1]} Em análise;",
                                       f"{keys[2]} Aguardando."]
    assert {p.numbering for p in out.paragraphs if p.level is not None} == {"numId_28"}
    assert {p.level for p in out.paragraphs if p.kind == "group"} == {1}
    assert {p.level for p in items} == {2}


def test_each_matrix_is_its_own_list_instance():
    status = {"RD-103": {"dup": _dup(), "expropriation_project": {"gdp": "y", "started": "z"}}}
    out = _render("P2.2_DESAPROPRIACAO", status)
    keys = {p.list_key for p in out.paragraphs if p.level is not None}
    assert len(keys) == 2
    assert {p.numbering for p in out.paragraphs if p.level is not None} == {"numId_28",
                                                                             "numId_49"}


@pytest.mark.parametrize("empty", ["", "   ", " ; ", ".", None, {"null_reason": ""}])
def test_empty_value_is_pending_human_with_visible_marker(empty):
    """schema.empty_value: o rótulo NUNCA sai sem valor (anomalia P2.2_DUP_RD101_SEM_VALOR)."""
    out = _render("P2.2_DESAPROPRIACAO", {"RD-101": {"dup": _dup(c=empty)}})
    assert out.status == "PENDING_HUMAN"
    keys = _keys()
    texts = [p.text for p in out.paragraphs]
    assert keys[2] not in texts and not any(t.rstrip().endswith(":") and t.startswith(keys[2])
                                            for t in texts)
    assert f"{keys[2]} [PENDENTE: p22_external_status.RD-101.dup.casa_civil]" in texts
    assert out.facts["missing_fields"] == ["p22_external_status.RD-101.dup.casa_civil"]
    assert any("campo vazio" in w for w in out.warnings)


def test_missing_field_is_pending_human():
    out = _render("P2.2_DESAPROPRIACAO", {"RD-101": {"dup": {"gdp": "y"}}})
    assert out.status == "PENDING_HUMAN"
    assert "[PENDENTE: p22_external_status.RD-101.dup.casa_civil]" in out.text


def test_no_information_sentinel_emits_the_standard_text():
    """schema.no_information: declaração humana explícita -> texto padronizado do modelo, OK."""
    key = SCHEMA["no_information"]["key"]
    standard = SCHEMA["no_information"]["text"]
    status = {"RD-101": {"dup": _dup(c={key: "sem publicação até o fechamento"})},
              "RD-104": {"dup": _dup()}}
    out = _render("P2.2_DESAPROPRIACAO", status)
    assert out.status == "OK" and out.facts["missing_fields"] == []
    keys = _keys()
    assert f"{keys[2]} {standard};" in [p.text for p in out.paragraphs]  # RD-101 não é a última
    assert out.facts["no_information"] == {
        "p22_external_status.RD-101.dup.casa_civil": "sem publicação até o fechamento"}
    assert "sem publicação até o fechamento" not in out.text          # motivo é auditoria


def test_mapping_other_than_the_sentinel_is_rejected():
    with pytest.raises(px.ExternalStatusError, match="sentinela"):
        _render("P2.2_DESAPROPRIACAO", {"RD-101": {"dup": _dup(c={"motivo": "x"})}})


def test_schema_documents_empty_value_without_citing_the_anomaly_as_behaviour():
    assert "P2.2_DUP_RD101_SEM_VALOR" not in SCHEMA["empty_value"]
    assert "PENDING_HUMAN" in SCHEMA["empty_value"]
    assert SCHEMA["no_information"]["text"] and SCHEMA["no_information"]["key"]
    assert "P2.2_EXTERNAL_PROG_CONTRADIZ_PLANILHA" not in str(DERIVED)   # anomalia não é regra


def test_interferences_block_and_unknown_matrix():
    status = {"RD-104": {"interferences": {"gfd": "b", "utility": "c", "started": "d"}}}
    out = _render("P2.2_INTERFERENCIAS", status)
    assert out.status == "OK"
    assert [p.text for p in out.paragraphs if p.kind == "group"] == ["RD-104:"]
    assert out.paragraphs[-1].kind == "spacer"
    assert _render("P2.2_DESAPROPRIACAO", status).status == "SKIPPED"
    with pytest.raises(px.ExternalStatusError):
        _render("P2.2_INTERFERENCIAS", {"RD-104": {"inventada": {}}})


def test_road_outside_order_goes_last_with_warning():
    status = {"RD-999": {"dup": _dup()}, "RD-103": {"dup": _dup()}}
    out = _render("P2.2_DESAPROPRIACAO", status)
    assert [p.text for p in out.paragraphs if p.kind == "group"] == ["RD-103:", "RD-999:"]
    assert any("RD-999" in w for w in out.warnings)


# ------------------------------------------------------------- Análise Programa derivada (QA2-E)
def _prog(block_id: str, mid: str, row, road="RD-103", index=0):
    """Texto do item 'Análise Programa:' da rodovia com a linha `row` da disciplina na planilha."""
    projects = pj.from_rows(sheet(row))
    fields = {"dup": _dup(), "expropriation_project": {"gdp": "y", "started": "z"},
              "interferences": {"gfd": "b", "utility": "c", "started": "d"}}[mid]
    out = _render(block_id, {road: {mid: fields}}, projects=projects)
    label = _keys(block_id, index)[0]
    item = next(p.text for p in out.paragraphs if p.text.startswith(label))
    return item[len(label):].strip().rstrip(";."), out


@pytest.mark.parametrize(("row", "expected"), [
    (approved("1.6", "RD-103", EST, DUP), "Aprovado"),
    # schema.derived.prog.status_text approval_with_reservation (DEC-015 na matriz, QA4-H)
    (approved("1.6", "RD-103", EST, DUP, evaluation="Aprovada com ressalva"),
     "Aprovado com ressalva"),
    (approved("1.6", "RD-103", EST, DUP, evaluation="Aprovado com Ressalvas"),
     "Aprovado com ressalva"),
    (rejected("1.6", "RD-103", EST, DUP, date(2026, 10, 1)), "Não aprovado"),
    (rejected("1.6", "RD-103", EST, DUP, "Aguardando previsão"), "Não aprovado"),
    (in_analysis("1.6", "RD-103", EST, DUP), "Em análise"),
    (late("1.6", "RD-103", EST, DUP), "Não entregue"),
])
def test_prog_follows_the_highway_block_status_sets(row, expected):
    """schema.derived.prog.status_text sobre p22_highway_block.yaml#status_sets."""
    text, out = _prog("P2.2_DESAPROPRIACAO", "dup", row)
    assert text == expected and out.status == "OK"
    fact = out.facts["derived"]["p22_external_status.RD-103.dup.prog"]
    assert fact["value"] == expected and fact["physical_row"] == 2


def test_prog_matrix_specific_text_and_expropriation_project():
    """status_text.by_matrix: interferência aprovada = 'Aprovado e encaminhado a GFD'; com
    ressalva, o encaminhamento se mantém (v438: as 2 aprovadas têm ressalva e o nº 14 as dá por
    encaminhadas)."""
    text, _ = _prog("P2.2_INTERFERENCIAS", "interferences",
                    approved("3.5", "RD-103", SEC, INTERF, evaluation="Aprovado com ressalvas"))
    assert text == "Aprovado com ressalva e encaminhado a GFD"
    text, _ = _prog("P2.2_INTERFERENCIAS", "interferences",
                    approved("3.5", "RD-103", SEC, INTERF))
    assert text == "Aprovado e encaminhado a GFD"
    text, _ = _prog("P2.2_DESAPROPRIACAO", "expropriation_project",
                    approved("3.2", "RD-103", SEC, DESAP, evaluation="Aprovado com ressalva"),
                    index=1)
    assert text == "Aprovado com ressalva"
    text, _ = _prog("P2.2_DESAPROPRIACAO", "expropriation_project",
                    rejected("3.2", "RD-103", SEC, DESAP, "Aguardando previsão"), index=1)
    assert text == "Não aprovado"


def test_prog_reservation_follows_the_highway_block_qualifier_mode():
    """A ressalva da matriz usa o MESMO `reservation_qualifier` do P2.2_HIGHWAY_BLOCK: com
    `value: none` (forma v0.12, só para comparação) nem o corpo nem a matriz qualificam."""
    from prog_g2_report.render import p22_text

    rules = p22_text.load_rules()
    none = dataclasses.replace(rules, reservation_mode="none")
    projects = pj.from_rows(sheet(approved("1.6", "RD-103", EST, DUP,
                                           evaluation="Aprovada com ressalva")))
    got = px.derive_value(DERIVED, "dup", "RD-103", projects, REF, none)
    assert got.value == "Aprovado" and got.facts["set"] == "approval"
    got = px.derive_value(DERIVED, "dup", "RD-103", projects, REF, rules)
    assert got.value == "Aprovado com ressalva"
    assert got.facts["set"] == "approval_with_reservation"
    assert DERIVED["status_text"][0]["set"] == "approval_with_reservation"   # precede approval


def _approval_sentences(block, rules) -> list[str]:
    """Frases das linhas de Aprovação do bloco (rótulo de `templates.approval.plural`)."""
    label = rules.templates["approval"]["plural"].split(":", 1)[0] + ":"
    return [s for p in block.paragraphs if p.text.startswith(label)
            for s in p.text.split(". ")]


def _body_status(block, discipline: str, rules) -> str | None:
    """Status da disciplina no corpo do 2.2 (fatos do bloco por rodovia) e conferência no texto:
    a frase da linha de Aprovação que cita a disciplina diz 'com ressalva' só se ela tem."""
    sentences = _approval_sentences(block, rules)
    for group in block.facts["groups"]:
        sets = group["sets"]
        if discipline in sets["approval_with_reservation"]:
            sentence = next(s for s in sentences if discipline in s)
            assert "com ressalva" in sentence, sentence
            return "approval_with_reservation"
        for key in ("approval", "in_analysis", "not_delivered"):
            if discipline in sets[key]:
                if key == "approval":
                    assert not any(discipline in s and "com ressalva" in s for s in sentences)
                return key
    return None


def _matrix_status(value: str) -> str:
    if value.startswith("Aprovado"):
        return "approval_with_reservation" if "com ressalva" in value else "approval"
    return {"Em análise": "in_analysis", "Não entregue": "not_delivered"}.get(value, value)


def _assert_matrix_matches_body(projects, reference_date) -> int:
    """Para cada disciplina citada no corpo do 2.2 E numa matriz da Análise Programa, o status é o
    mesmo (QA4-H: a v0.13 dizia 'Aprovado' na matriz e 'aprovado com ressalva' no corpo)."""
    from prog_g2_report.render import p22_text

    rules = p22_text.load_rules()
    blocks = {b.facts["road"]: b for b in p22_text.build_highway_blocks(projects, reference_date,
                                                                          rules)}
    checked = 0
    for mid, prefix in DERIVED["disciplines"].items():
        for road, block in blocks.items():
            rows = px.discipline_rows(projects, road, prefix)
            if len(rows) != 1:
                continue
            body = _body_status(block, rows[0].discipline, rules)
            got = px.derive_value(DERIVED, mid, road, projects, reference_date, rules)
            if body is None or got.value is None:
                continue
            assert _matrix_status(got.value) == body, (mid, road, got.value, body)
            checked += 1
    return checked


def test_matrix_and_body_give_the_same_status_to_the_same_discipline():
    rows = [approved("1.6", "RD-103", EST, DUP, evaluation="Aprovada com ressalva"),
            approved("1.7", "RD-103", EST, "Estudos Geotécnicos"),
            approved("3.2", "RD-103", SEC, DESAP),
            approved("3.5", "RD-103", SEC, INTERF, evaluation="Aprovado com ressalvas"),
            approved("1.6", "RD-101", EST, DUP),
            in_analysis("3.2", "RD-101", SEC, DESAP),
            approved("3.5", "RD-101", SEC, INTERF, evaluation="Aprovado com Ressalvas"),
            approved("3.6", "RD-101", SEC, "Projeto de Paisagismo")]
    projects = pj.from_rows(sheet(*rows))
    assert _assert_matrix_matches_body(projects, REF) == 6


@pytest.mark.parametrize("row", [
    # situação 'No prazo' (sem entrega, previsão futura) e avaliação fora dos conjuntos:
    # forma nunca observada -> pendência humana (schema.derived.prog.unmatched)
    late("1.6", "RD-103", EST, DUP, forecast=date(2026, 12, 1)),
    approved("1.6", "RD-103", EST, DUP, evaluation="Parecer emitido"),
    project("1.6", "RD-103", EST, DUP, forecast=None),
    approved("1.6", "RD-103", EST, "Outra disciplina"),            # linha ausente
])
def test_prog_outside_the_sets_is_pending_human_with_marker(row):
    _, out = _prog("P2.2_DESAPROPRIACAO", "dup", row)
    where = "p22_external_status.RD-103.dup.prog"
    assert out.status == "PENDING_HUMAN" and out.facts["missing_fields"] == [where]
    assert f"{_keys()[0]} [PENDENTE: {where}]" in [p.text for p in out.paragraphs]
    assert any(w.startswith(where) for w in out.warnings)


def test_prog_ambiguous_rows_and_missing_source_are_pending():
    two = pj.from_rows(sheet(approved("1.6", "RD-103", EST, DUP), late("1.7", "RD-103", EST, DUP)))
    out = _render("P2.2_DESAPROPRIACAO", {"RD-103": {"dup": _dup()}}, projects=two)
    assert out.status == "PENDING_HUMAN" and "linha 2, linha 3" in " ".join(out.warnings)
    for kwargs in ({"projects": None}, {"ref": None}):
        out = _render("P2.2_DESAPROPRIACAO", {"RD-103": {"dup": _dup()}}, **kwargs)
        assert out.status == "PENDING_HUMAN"
        assert "[PENDENTE: p22_external_status.RD-103.dup.prog]" in out.text
        assert any("missing_source" in w for w in out.warnings)


def test_prog_in_the_input_is_ignored_and_the_sheet_wins():
    """schema.derived.prog.input_value: a entrada não substitui a planilha (nunca contradiz o
    P2.2_HIGHWAY_BLOCK do mesmo snapshot)."""
    projects = pj.from_rows(sheet(in_analysis("1.6", "RD-103", EST, DUP)))
    out = _render("P2.2_DESAPROPRIACAO", {"RD-103": {"dup": {**_dup(), "prog": "Não aprovado"}}},
                  projects=projects)
    assert f"{_keys()[0]} Em análise;" in [p.text for p in out.paragraphs]
    assert "Não aprovado" not in out.text
    where = "p22_external_status.RD-103.dup.prog"
    assert out.facts["ignored_input"] == {where: "Não aprovado"}
    assert any(w.startswith(f"{where}: entrada ignorada") for w in out.warnings)


def test_road_with_the_discipline_but_absent_from_the_input_is_warned():
    out = _render("P2.2_DESAPROPRIACAO", {"RD-103": {"dup": _dup()}})
    assert out.facts["matrices"]["dup"] == ["RD-103"]                # matrix_absent
    assert any("RD-104" in w and "matriz dup" in w for w in out.warnings)


# ------------------------------------------------------------------ golden (-m golden)
def _evidence() -> Path | None:
    env = os.environ.get("PROG_EVIDENCE_ROOT")
    for root in ([Path(env)] if env else []) + list(Path(__file__).resolve().parents):
        if (root / "tmp" / "agent_N" / "projetos_versions.json").exists():
            return root / "tmp" / "agent_N" / "projetos_versions.json"
    return None


def _published_prog(block_id: str, keys_index: int | None) -> dict[str, str]:
    """Rodovia -> 'Análise Programa' publicada no nº 14 (content_blocks `observed.values_no14`)."""
    raw = BLOCKS[block_id]
    values = raw["observed"]["values_no14"]
    label = _keys(block_id, keys_index or 0)[0]
    out, road, seen = {}, None, 0
    start = 0 if keys_index is None else None
    if keys_index is not None:                     # 2ª matriz da desapropriação: 2º 'RD-103:'
        for i, v in enumerate(values):
            if v == "RD-103:":
                seen += 1
                if seen == keys_index + 1:
                    start = i
                    break
    for value in values[start:]:
        if value.endswith(":") and value.startswith("RD-"):
            if value[:-1] in out:
                break
            road = value[:-1]
        elif value.startswith(label) and road and road not in out:
            out[road] = value[len(label):].strip().rstrip(";.")
    return out


@pytest.mark.golden
def test_golden_n14_prog_from_v438_and_the_documented_divergences():
    """nº 14 × v438 (snapshot DEC-012 do texto do 2.2): 3 de 12 Análises Programa iguais.
    - 3 divergências (Desapropriação RD-104; Interferência RD-102A e RD-104) são a anomalia
      P2.2_EXTERNAL_PROG_CONTRADIZ_PLANILHA: o texto publicado diz 'Não aprovado' e o bloco por
      rodovia do MESMO relatório lista as três disciplinas 'em análise pelo Programa';
    - 6 são a ressalva da planilha que o publicado omite (P2.2_EXTERNAL_PROG_RESSALVA_OMITIDA,
      modelo v0.14): o gerado qualifica como o corpo do 2.2."""
    path = _evidence()
    if path is None:
        pytest.skip("extrato do agente N ausente (tmp/agent_N/projetos_versions.json)")
    projects = pj.from_extract(json.loads(path.read_text(encoding="utf-8"))["v438.0"])
    published = {
        "dup": _published_prog("P2.2_DESAPROPRIACAO", 0),
        "expropriation_project": _published_prog("P2.2_DESAPROPRIACAO", 1),
        "interferences": _published_prog("P2.2_INTERFERENCIAS", None),
    }
    same, diverging = 0, {}
    for mid, by_road in published.items():
        assert set(by_road) == set(ORDER), (mid, by_road)
        for road, text in by_road.items():
            got = px.derive_value(DERIVED, mid, road, projects, REF)
            assert got.value is not None, got.reason
            if got.value == text:
                same += 1
            else:
                diverging[(mid, road)] = (text, got.value)
    reserved = ("Aprovado", "Aprovado com ressalva")
    gfd = ("Aprovado e encaminhado a GFD", "Aprovado com ressalva e encaminhado a GFD")
    assert same == 3
    assert diverging == {
        ("expropriation_project", "RD-104"): ("Não aprovado", "Em análise"),
        ("interferences", "RD-102A"): ("Não aprovado", "Em análise"),
        ("interferences", "RD-104"): ("Não aprovado", "Em análise"),
        ("dup", "RD-103"): reserved, ("dup", "RD-101"): reserved, ("dup", "RD-104"): reserved,
        ("expropriation_project", "RD-102A"): reserved,
        ("interferences", "RD-103"): gfd, ("interferences", "RD-101"): gfd,
    }
    # coerência interna do gerado: matriz e corpo do 2.2 com o mesmo status por disciplina
    assert _assert_matrix_matches_body(projects, REF) >= 9
    contradicting = {k for k, (pub, _) in diverging.items() if pub == "Não aprovado"}
    # o bloco por rodovia do mesmo snapshot diz 'em análise' para as três: sem contradição
    from prog_g2_report.render import p22_text

    blocks = {b.facts["road"]: b for b in p22_text.build_highway_blocks(projects, REF)}
    for mid, road in contradicting:
        prefix = DERIVED["disciplines"][mid]
        in_analysis_sets = [d for g in blocks[road].facts["groups"]
                            for d in g["sets"]["in_analysis"]]
        assert any(d.startswith(prefix) for d in in_analysis_sets), (road, prefix)
