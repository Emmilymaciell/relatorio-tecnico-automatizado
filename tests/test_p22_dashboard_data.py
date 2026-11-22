"""Dados do quadro por rodovia do 2.2: sintético + golden contra a transcrição do agente E."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import unicodedata
from datetime import date
from pathlib import Path

import pytest
import yaml

from _p22_synthetic import (
    EST,
    OAE,
    PRI,
    SEC,
    approved,
    in_analysis,
    late,
    project,
    rejected,
    sheet,
)
from prog_g2_report.render import p22_text as t
from prog_g2_report.render.p22_dashboard_data import road_dashboard_data, sentence_case
from prog_g2_report.sources import projects as pj

REF = date(2026, 9, 7)


def _data(*rows, highway="RD-103", ref=REF):
    return road_dashboard_data(pj.from_rows(sheet(*rows)), highway, ref)


def test_format_fields_and_columns_from_model():
    spec = yaml.safe_load(t.SPEC_PATH.read_text(encoding="utf-8"))
    data = _data(approved("1.1", "RD-103", EST, "Estudos A"))
    assert data["columns"] == [c["header"] for c in spec["quadro_visual"]["columns"]]
    assert len(data["columns"]) == 7
    assert data["highway"] == "RD-103"
    assert data["updated_at"] == "07/09/2026"
    assert data["donut_title"] == spec["quadro_visual"]["donut"]["title"]
    assert set(data) >= {"highway", "donut", "rows", "updated_at"}
    json.dumps(data)  # serializável


def test_rows_order_by_discipline_order_and_dashboard_exclusions():
    rows = [
        in_analysis("4.1", "RD-103", OAE, "Projeto de Obra de Arte Especial (OAE)"),
        late("3.10", "RD-103", SEC, "Projeto Executivo"),
        late("3.9", "RD-103", SEC, "Equipe Fixa de Projeto de Engenharia - PES"),
        late("3.6", "RD-103", SEC, "Memoriais Descritivos da Obra"),
        approved("2.1", "RD-103", PRI, "Projeto Geométrico e Interseções"),
        approved("1.1", "RD-103", EST, "Estudos A"),
        approved("1.1", "RD-101", EST, "Outra rodovia"),
    ]
    data = _data(*rows)
    assert [r[0] for r in data["rows"]] == [
        "Estudos A", "Projeto Geométrico e Interseções", "Memoriais Descritivos da Obra",
        "Projeto de Obra de Arte Especial (OAE)"]
    assert all(len(r) == 7 for r in data["rows"])


def test_cell_formats():
    rows = [
        approved("1.1", "RD-103", EST, "Estudos A", forecast=date(2026, 1, 30), received=date(2026, 2, 12),
                 revision=4.0, accepted="SIm ", evaluation="Aprovado com Ressalvas"),
        late("1.2", "RD-103", EST, "Estudos B", forecast=date(2026, 5, 8), revision=3,
             revision_delivery="2026-08-14"),
        rejected("1.3", "RD-103", EST, "Estudos C", "Aguardando Previsão", accepted="não",
                 evaluation="disciplina não aceita", revision=0),
    ]
    data = _data(*rows)
    assert data["rows"][0] == ["Estudos A", "30/01/26", "12/02/26", "4", "Sim", "Aprovado com ressalvas",
                               "Concluído"]
    assert data["rows"][1] == ["Estudos B", "08/05/26", "", "", "", "", "14/08/26"]   # REV vazio sem entrega
    assert data["rows"][2][3:] == ["0", "Não", "Disciplina não aceita", "Aguardando Previsão"]


def test_highway_with_space_or_nbsp():
    rows = [approved("1.1", "RD-102 A", EST, "Estudos A"), approved("1.2", "RD-102 A", EST, "Estudos B")]
    for highway in ("RD-102A", "RD-102 A", "RD-102 A"):
        data = _data(*rows, highway=highway)
        assert data["highway"] == "RD-102A"
        assert len(data["rows"]) == 2


def test_donut_counts_by_recalculated_situation():
    rows = [
        approved("1.1", "RD-103", EST, "Estudos A"),
        approved("1.2", "RD-103", EST, "Estudos B"),
        in_analysis("2.1", "RD-103", PRI, "Projeto C"),
        late("3.1", "RD-103", SEC, "Projeto D", forecast=date(2026, 9, 1), situation_cached="No prazo"),
        late("3.2", "RD-103", SEC, "Projeto E", forecast=date(2026, 9, 30)),
        project("3.3", "RD-103", SEC, "Projeto F", forecast=None),
    ]
    data = _data(*rows)
    assert list(data["donut"])[:3] == ["Analisada", "Atrasado", "Em análise"]
    assert data["donut"] == {"Analisada": 2, "Atrasado": 1, "Em análise": 1,
                             "Aguardando previsão": 1, "No prazo": 1}
    assert data["facts"]["donut_total"] == len(data["rows"]) == 6


def test_donut_categories_always_present():
    data = _data(approved("1.1", "RD-103", EST, "Estudos A"))
    assert data["donut"] == {"Analisada": 1, "Atrasado": 0, "Em análise": 0}


def test_groups_slicer_alphabetical():
    rows = [approved("4.1", "RD-103", OAE, "Projeto de OAE"), approved("1.1", "RD-103", EST, "Estudos A")]
    assert _data(*rows)["groups"] == ["Fase de Estudos", "OAE"]


def test_sentence_case():
    assert sentence_case("sim") == "Sim"
    assert sentence_case("  Aprovado   com Ressalvas ") == "Aprovado com ressalvas"
    assert sentence_case("") == ""


# ------------------------------------------------------------------ golden (-m golden)
def _evidence_root() -> Path | None:
    env = os.environ.get("PROG_EVIDENCE_ROOT")
    candidates = [Path(env)] if env else []
    candidates += list(Path(__file__).resolve().parents)
    for root in candidates:
        if (root / "tmp" / "agent_E" / "ground_truth.py").exists() and (
                root / "tmp" / "agent_N" / "projetos_versions.json").exists():
            return root
    return None


EVIDENCE = _evidence_root()
golden = pytest.mark.skipif(EVIDENCE is None, reason="extratos dos agentes E/N ausentes em tmp/")


def _ground_truth():
    spec = importlib.util.spec_from_file_location("agent_e_ground_truth",
                                                  EVIDENCE / "tmp" / "agent_E" / "ground_truth.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _norm(s) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(s or ""))).strip().lower()


def _gt_cell(value: str) -> str:
    """'Entrega da Revisão' do Power BI em M/D/AAAA → dd/mm/aa (anomalia P2.2_QUADRO_DATA_MDY)."""
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", value.strip())
    if m:
        mo, d, y = m.groups()
        return f"{int(d):02d}/{int(mo):02d}/{y[2:]}"
    return value


def _cell_eq(got: str, want: str) -> bool:
    """Critério do agente E: caixa e espaços ignorados; '*' = texto truncado na imagem (prefixo)."""
    g, w = _norm(got), _norm(_gt_cell(want))
    return g.startswith(w[:-1]) if w.endswith("*") else g == w


@pytest.mark.golden
@golden
@pytest.mark.parametrize(("report", "version"), [(14, "v438.0"), (13, "v328.0")])
def test_golden_dashboards_match_transcription(report, version):
    """Quadros nº 14 (v438) e nº 13 (v328): 100% das células contra a transcrição do agente E."""
    gt = _ground_truth()
    truth = gt.ground_truth()
    ref = date.fromisoformat(gt.PRINTED_DATE[report])
    versions = json.loads((EVIDENCE / "tmp" / "agent_N" / "projetos_versions.json").read_text(encoding="utf-8"))
    wb = pj.from_extract(versions[version])
    total = ok = 0
    diffs = []
    for highway in ("RD-103", "RD-102A", "RD-101", "RD-104"):
        data = road_dashboard_data(wb, highway, ref)
        expected = truth[(report, highway)]
        assert [r[0] for r in data["rows"]] == list(expected), highway   # disciplinas e ordem
        assert data["updated_at"] == ref.strftime("%d/%m/%Y")
        for row in data["rows"]:
            for got, want in zip(row[1:], expected[row[0]], strict=True):
                total += 1
                if _cell_eq(got, want):
                    ok += 1
                else:
                    diffs.append((highway, row[0], got, want))
    print(f"nº{report} {version}: {ok}/{total} células", diffs[:5])
    assert total == 504  # 84 linhas x 6 campos (agente E: 504 células por relatório)
    assert ok == total, diffs


@pytest.mark.golden
@golden
def test_golden_no14_donut_v438():
    """Rosca do nº 14 (spec quadro_visual.donut.check_no14_v438)."""
    spec = yaml.safe_load(t.SPEC_PATH.read_text(encoding="utf-8"))
    checks = spec["quadro_visual"]["donut"]["check_no14_v438"]
    versions = json.loads((EVIDENCE / "tmp" / "agent_N" / "projetos_versions.json").read_text(encoding="utf-8"))
    wb = pj.from_extract(versions["v438.0"])
    for highway, expected in checks.items():
        donut = road_dashboard_data(wb, highway, date(2026, 9, 7))["donut"]
        got = " / ".join(str(donut[c]) for c in ("Analisada", "Atrasado", "Em análise"))
        assert got == expected, highway
