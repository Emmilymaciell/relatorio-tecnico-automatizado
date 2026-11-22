"""Planilha ambiental do 2.4: cabeçalho por conteúdo, todas as linhas, status recalculado (WAVE1 §B)."""

import io
from datetime import date, datetime, timedelta

import pytest

from prog_g2_report.sources import environmental as env
from golden_evidence import (
    ENV_SNAPSHOT,
    PANELS,
    require_golden,
    snapshot,
    workbook_bytes_from_snapshot,
)

REF = date(2026, 9, 7)
CSG, CLX, DELTA, TETRA = (
    "CONSTRUTORA ALFA - AAA", "CONSTRUTORA BETA S/A - BBB",       # nomes sintéticos
    "CONSTRUTORA GAMA ÇÃO LTDA", "DELTA CONSTRUTORA LTDA",           # acento testa a normalização
)
LIC_HEADER = (None, "Nº Licença", "Nº Processo", "Empresa", "Fase da licença", "Data de emissão",
              "Data de validade", "Órgão", "Atividade", "Status")
COND_HEADER = ("Item", "Nº Licença", "Nome da condicionante", "Descrição/Informação complementar",
               "Evidências salvas em", "Data da entrega", "Status", "Observações", "Responsável",
               "Vence em", "Próxima entrega", "Vence em")


def _lic(number, company, phase, status):
    return (None, number, 123, company, phase, None, datetime(2030, 1, 1) if number else None, "OAMB", "x", status)


def _cond(item, company, delivery, obs=None, next_delivery=None, cached="No prazo"):
    return (item, 1, 5, None, None, delivery, cached, obs, company, 0, next_delivery, 0)


def _companies():
    return [
        ("Cadastro de empresas",),
        (),
        (None, "Empresa", None, None, None, None, "Rodovia", None, None, None, None, None, "Rodovia (painel)"),
        (None, CLX, "CLX", None, None, None, "RD-102a", None, None, None, None, None, "RD 102a"),
        (None, DELTA, "Delta", None, None, None, "RD-103", None, None, None, None, None, "RD 103"),
        (None, CSG, "CSG", None, None, None, "RD-101", None, None, None, None, None, "RD 101"),
        (None, TETRA, "Tetra", None, None, None, "RD-104", None, None, None, None, None, "RD 104"),
    ]


def _licenses():
    return [
        ("Licenças",),
        LIC_HEADER,
        _lic(1, CLX, "Licença Ambiental Única", "Vigente"),
        _lic(None, CLX, "Licença Ambiental - Canteiro de obra", "Aguardando a liberação"),
        _lic(2, DELTA, "Outorga de uso de recurso hídrico", "Vigente"),
        _lic(None, DELTA, "Outorga de uso de recurso hídrico", "Aguardando a liberação"),
        _lic(None, DELTA, "Licença Ambiental - Usina", "Aguardando a liberação"),
        _lic(3, CSG, "Licença Ambiental Única", "Vigente"),
        _lic(4, TETRA, "Licença Ambiental Única", "Vigente"),
        (None,) * 10,
    ]


def _conditions():
    d = REF
    return [
        ("Condicionantes",),
        COND_HEADER,
        _cond(1, CLX, d - timedelta(days=400), obs="Finalizada", cached="Finalizada"),
        _cond(2, CLX, d + timedelta(days=200)),
        _cond(3, DELTA, d + timedelta(days=10), cached="No prazo"),        # cache velho: recalcula
        _cond(4, CSG, d - timedelta(days=5), obs="Atendida", next_delivery=d + timedelta(days=90)),
        _cond(5, CSG, d + timedelta(days=60), obs="Justificada\nOFICIO 67"),
        _cond(6, TETRA, d + timedelta(days=30)),
        _cond(7, TETRA, d + timedelta(days=31)),
    ]


def _workbook_bytes(hidden_rows=(), autofilter=True, header_offset=0):
    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in (("Dashboard", [("legado",)]), ("Licenças", _licenses()),
                       ("Condicionantes", _conditions()), ("Empresas", _companies())):
        ws = wb.create_sheet(name)
        for _ in range(header_offset if name == "Licenças" else 0):
            ws.append(())
        for row in rows:
            ws.append(list(row))
        if autofilter and name in {"Licenças", "Condicionantes"}:
            ws.auto_filter.ref = f"A2:L{ws.max_row}"
    for sheet, row in hidden_rows:
        wb[sheet].row_dimensions[row].hidden = True
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# --------------------------------------------------------------------------- status
@pytest.mark.parametrize(
    ("days", "expected"),
    [(-1, "Pendente"), (0, "Pendente"), (1, "Próximo do vencimento"), (30, "Próximo do vencimento"),
     (31, "No prazo"), (365, "No prazo")],
)
def test_recompute_status_thresholds_use_delivery_date(days, expected):
    row = {"Observações": None, "Data da entrega": REF + timedelta(days=days), "Próxima entrega": None}
    assert env.recompute_status(row, REF) == expected


def test_recompute_status_finalizada_wins_over_any_date():
    row = {"Observações": " finalizada ", "Data da entrega": REF - timedelta(days=99)}
    assert env.recompute_status(row, REF) == "Finalizada"


def test_recompute_status_atendida_uses_next_delivery_not_delivery_date():
    row = {"Observações": "Atendida", "Data da entrega": REF - timedelta(days=10),
           "Próxima entrega": (REF + timedelta(days=40)).isoformat()}
    assert env.recompute_status(row, REF) == "No prazo"


def test_recompute_status_justificada_uses_delivery_date():
    row = {"Observações": "Justificada\nOFICIO 67", "Data da entrega": datetime(2026, 9, 20),
           "Próxima entrega": datetime(2027, 1, 1)}
    assert env.recompute_status(row, REF) == "Próximo do vencimento"


def test_recompute_status_without_date_is_undetermined():
    assert env.recompute_status({"Observações": "Atendida", "Próxima entrega": "Finalizada"}, REF) is None


def test_recompute_status_depends_only_on_reference_date():
    row = {"Data da entrega": date(2026, 9, 1)}
    assert env.recompute_status(row, date(2026, 7, 1)) == "No prazo"
    assert env.recompute_status(row, date(2026, 8, 15)) == "Próximo do vencimento"
    assert env.recompute_status(row, date(2026, 9, 1)) == "Pendente"


# --------------------------------------------------------------------------- leitura
def test_load_reads_every_row_ignoring_hidden_and_autofilter():
    data = _workbook_bytes(hidden_rows=[("Licenças", 4), ("Condicionantes", 3), ("Condicionantes", 9)])
    wb = env.load(data)
    assert len(wb.licenses) == 7          # linha vazia final descartada
    assert len(wb.conditions) == 7
    assert [c.row for c in wb.conditions][:2] == [3, 4]


def test_header_is_found_by_content_not_position():
    wb = env.load(_workbook_bytes(header_offset=3))
    assert wb.licenses[0].row == 6
    assert wb.licenses[1].status == "Aguardando a liberação"


def test_companies_sheet_mapped_by_content_and_highway_normalized():
    wb = env.load(_workbook_bytes())
    assert wb.company_to_highway[CLX] == "RD-102A"          # 'RD-102a' -> 'RD-102A', coluna G (não M)
    assert wb.highways == ("RD-102A", "RD-103", "RD-101", "RD-104")
    assert {lic.highway for lic in wb.licenses} == {"RD-102A", "RD-103", "RD-101", "RD-104"}


def test_highway_display_normalizes_spacing_and_case():
    assert env.highway_display(" RD 102a ") == "RD-102A"
    assert env.highway_display("RD-104") == "RD-104"


def test_load_accepts_path_and_file_object(tmp_path):
    data = _workbook_bytes()
    path = tmp_path / "ambiental_sintetica.xlsx"
    path.write_bytes(data)
    assert len(env.load(path).licenses) == 7
    assert len(env.load(io.BytesIO(data)).licenses) == 7


def test_missing_sheet_or_header_fails_loudly():
    with pytest.raises(ValueError, match="Licenças"):
        env.parse_workbook_rows([("nada",)], _conditions(), _companies())
    import openpyxl

    wb = openpyxl.Workbook()
    wb.active.title = "Licenças"
    buffer = io.BytesIO()
    wb.save(buffer)
    with pytest.raises(KeyError, match="Condicionantes"):
        env.load(buffer.getvalue())


def test_companies_without_highway_column_fail():
    companies = [(None, "Empresa"), (None, CLX, "sem rodovia")]
    with pytest.raises(ValueError, match="rodovia"):
        env.parse_workbook_rows(_licenses(), _conditions(), companies)


# --------------------------------------------------------------------------- agregados
def test_license_index_panel_counts():
    agg = env.aggregate(env.load(_workbook_bytes()), REF)
    idx = agg.license_index
    assert (idx.total, idx.issued, idx.valid, idx.pending) == (7, 4, 4, 3)
    assert idx.by_highway == (("RD-103", 3), ("RD-102A", 2), ("RD-101", 1), ("RD-104", 1))
    assert idx.by_phase["Licença Ambiental Única"] == 3
    assert [lic.highway for lic in agg.pending_licenses()] == ["RD-102A", "RD-103", "RD-103"]


def test_conditions_by_highway_use_recomputed_status_never_cache():
    agg = env.aggregate(env.load(_workbook_bytes()), REF)
    assert dict(agg.conditions_by_highway["RD-102A"]) == {
        "Finalizada": 1, "No prazo": 1, "Pendente": 0, "Próximo do vencimento": 0}
    assert agg.count("RD-103", "Próximo do vencimento") == 1      # cache dizia 'No prazo'
    assert agg.count("RD-101", "No prazo") == 2                   # Atendida -> K; Justificada -> F
    assert agg.count("RD-104", "Próximo do vencimento") == 1      # 30 dias
    assert agg.count("RD-104", "No prazo") == 1                   # 31 dias
    assert agg.conditions_by_status == {"Finalizada": 1, "No prazo": 4, "Próximo do vencimento": 2}


def test_unknown_responsible_and_missing_dates_become_warnings():
    conditions = [*_conditions(), _cond(8, "EMPRESA NOVA", REF), _cond(9, CSG, None)]
    wb = env.parse_workbook_rows(_licenses(), conditions, _companies())
    agg = env.aggregate(wb, REF)
    assert any("EMPRESA NOVA" in w for w in agg.warnings)
    assert any("indeterminado" in w for w in agg.warnings)
    assert sum(sum(v.values()) for v in agg.conditions_by_highway.values()) == 7


# --------------------------------------------------------------------------- golden
@pytest.mark.golden
@pytest.mark.parametrize("number", [13, 14])
def test_golden_panels_from_agent_b_snapshots(request, number):
    """Agregados da versão da planilha no instante 'Atualizado em' = painéis do PDF (WAVE1 §B)."""
    root = require_golden(request)
    version, reference = ENV_SNAPSHOT[number]
    snap = snapshot(root, version)
    agg = env.aggregate(env.load(workbook_bytes_from_snapshot(snap)), reference)
    expected = PANELS[number]
    statuses = ("Finalizada", "No prazo", "Pendente", "Próximo do vencimento")
    got = {hw: tuple(agg.count(hw, s) for s in statuses) for hw in expected["cond"]}
    assert got == expected["cond"]
    idx = agg.license_index
    assert (idx.total, idx.valid, idx.total - idx.valid) == expected["lic"]
    assert dict(idx.by_highway) == expected["lic_road"]
    # o recálculo reproduz o cache de TODAY() gravado naquela data: 0 divergências
    diverging = [c.row for c, s in agg.conditions if (c.cached_status or "").casefold() != (s or "").casefold()]
    assert diverging == []
    assert agg.warnings == ()
