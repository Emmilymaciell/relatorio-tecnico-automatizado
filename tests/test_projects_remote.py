"""Planilha de projetos por VERSÃO do SharePoint, lida em memória (DEC-012, regra nº 1).

Offline: cliente graph FALSO e planilha SINTÉTICA (`_p22_synthetic`), montada em BytesIO.
`-m network`: lê a versão 438.0 de verdade (só GET, nada em disco, nada de token impresso) e
confere que GED, Projetos e Painel de Controle saem dos mesmos bytes.
"""

from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path

import pytest

import _p22_synthetic as syn
from prog_g2_report import REPO_ROOT
from prog_g2_report.builder.assemble import load_p22_projects, projects_sheet_origins
from prog_g2_report.builder.context import SourceManifest, SourceRef
from prog_g2_report.sources import projects_remote as remote

ROADS = ("RD-103", "RD-101")


def _xlsx_bytes() -> bytes:
    import openpyxl

    sheets = {
        "Projetos": syn.sheet(syn.approved("1.1", ROADS[0], syn.EST, "Estudos de Tráfego"),
                              syn.in_analysis("2.1", ROADS[1], syn.PRI, "Projeto Geométrico")),
        "GED": syn.ged_sheet(syn.ged(ROADS[0], syn.EST, "Estudos de Tráfego", date(2026, 3, 1))),
        "Painel de Controle": syn.panel(*ROADS),
    }
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, values in sheets.items():
        ws = wb.create_sheet(name)
        for row in values:
            ws.append(list(row))
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


class _FakeGraph:
    """Só as duas leituras do graph_ro que o leitor usa; nada de escrita."""

    def __init__(self, data: bytes):
        self.data = data
        self.reads = 0

    def versions(self, drive_id, item_id):
        return [{"id": "7.0", "lastModifiedDateTime": "2027-01-07T10:00:00Z"},
                {"id": "8.0", "lastModifiedDateTime": "2027-01-08T10:00:00Z"}]

    def read_version_bytes(self, drive_id, item_id, version_id):
        self.reads += 1
        return self.data


@pytest.fixture
def fake(tmp_path, monkeypatch):
    remote.clear_cache()
    monkeypatch.chdir(tmp_path)
    graph = _FakeGraph(_xlsx_bytes())
    yield graph
    remote.clear_cache()


def test_version_read_in_memory_gives_the_three_sheets_and_writes_nothing(fake, tmp_path):
    version = remote.read_version("d", "i", "v7", client=fake)
    assert version.version_id == "7.0" and version.last_modified == "2027-01-07T10:00:00Z"
    assert len(version.sha1) == 40
    assert set(version.sheets) == {"Projetos", "GED", "Painel de Controle"}
    workbook = version.workbook
    assert [r.road for r in workbook.projects] == list(ROADS)
    assert [g.road for g in workbook.ged] == [ROADS[0]]
    assert workbook.road_order == ROADS
    remote.read_version("d", "i", "7", client=fake)
    assert fake.reads == 1                                   # uma leitura por processo
    assert list(tmp_path.iterdir()) == []                    # nada gravado em disco
    with pytest.raises(LookupError, match="GAP-015"):
        remote.read_version("d", "i", "99", client=fake)


def _remote_sources() -> SourceManifest:
    sources = SourceManifest()
    sources.add(SourceRef("projects", "Projetos", None, drive_id="d", item_id="i",
                          version_id="7.0"))
    return sources


def test_remote_snapshot_feeds_text_and_dashboards_with_no_deviation(fake):
    remote.read_version("d", "i", "7.0", client=fake)
    sources = _remote_sources()
    text, dashboard, key, deviations = load_p22_projects(sources)
    assert key == "projects" and deviations == []
    assert text is dashboard and dashboard.ged and dashboard.road_order == ROADS
    origins = projects_sheet_origins(sources)
    assert list(origins) == ["GED", "Projetos", "Painel de Controle"]
    assert {o["source"] for o in origins.values()} == {"projects"}
    assert {o["version_id"] for o in origins.values()} == {"7.0"}


def test_offline_ged_copy_without_version_is_a_recorded_deviation(tmp_path):
    extract = tmp_path / "projetos_range.json"
    extract.write_text(json.dumps({"7.0": {"rows": syn.sheet(
        syn.approved("1.1", ROADS[0], syn.EST, "Estudos de Tráfego"))}}, default=str),
        encoding="utf-8")
    panel = tmp_path / "projetos_versions.json"
    panel.write_text(json.dumps({"v7.0": {"Painel de Controle": syn.panel(*ROADS)},
                                 "v6.0": {"Painel de Controle": syn.panel(*ROADS)}}),
                     encoding="utf-8")
    ged = tmp_path / "copia_local.xlsx"
    ged.write_bytes(_xlsx_bytes())
    sources = SourceManifest()
    sources.add(SourceRef("projects", "Projetos", extract, version_id="7.0"))
    sources.add(SourceRef("projects_panel", "Painel", panel, version_id="v7.0"))
    sources.add(SourceRef("projects_ged", "GED (cópia local)", ged))
    _text, dashboard, _key, deviations = load_p22_projects(sources)
    assert dashboard.ged and dashboard.road_order == ROADS
    origins = projects_sheet_origins(sources)
    assert origins["Projetos"] == {"source": "projects", "version_id": "7.0"}
    assert origins["Painel de Controle"]["source"] == "projects_panel"
    assert origins["GED"] == {"source": "projects_ged", "version_id": None}
    assert [(d["kind"], d["sheet"]) for d in deviations] == [
        ("SOURCE_SNAPSHOT_UNVERSIONED", "GED")]               # painel v7.0 = mesmo snapshot

    sources.add(SourceRef("projects_panel", "Painel", panel, version_id="v6.0"))
    _t, _d, _k, deviations = load_p22_projects(sources)
    assert {(d["kind"], d["sheet"]) for d in deviations} == {
        ("SOURCE_SNAPSHOT_UNVERSIONED", "GED"), ("SOURCE_VERSION_OVERRIDE", "Painel de Controle")}


def test_manifest_provenance_of_a_remote_version(fake):
    from prog_g2_report.builder.provenance import source_provenance

    version = remote.read_version("d", "i", "7.0", client=fake)
    sources = SourceManifest()
    sources.add(SourceRef("projects", "Projetos", None, drive_id="d", item_id="i",
                          version_id=version.version_id, last_modified=version.last_modified,
                          sha1=version.sha1))
    prov = source_provenance(sources, {"sources": {"projects": {"name": "planilha.xlsx"}}})
    entry = prov["projects"]
    assert entry["snapshot_origin"] == "sharepoint:versions/7.0 (memória)"
    assert entry["last_modified"] == "2027-01-07T10:00:00Z" and entry["sha1"] == version.sha1
    assert entry["local_path"] is None and entry["local_mtime"] is None


# ------------------------------------------------------------------ -m network (v438.0 real)
def _env_file() -> Path | None:
    candidates = [REPO_ROOT / ".env"]
    if REPO_ROOT.parent.name == "worktrees":
        candidates.append(REPO_ROOT.parents[2] / ".env")
    return next((c for c in candidates if c.is_file()), None)


@pytest.mark.network
def test_network_v438_sheets_come_from_one_version(request):
    if "network" not in (request.config.getoption("markexpr") or ""):
        pytest.skip("network: rodar com -m network")
    env_file = _env_file()
    if env_file is None:
        pytest.skip(".env ausente")
    from prog_g2_report.model import load_model
    from prog_g2_report.sources import master_list_remote

    name = load_model()["sources"]["projects"]["name"]
    drive_id, item_id = master_list_remote.catalog_identity(name)
    remote.clear_cache()
    client = master_list_remote.default_client(env_file)
    try:
        version = remote.read_version(drive_id, item_id, "438.0", client=client)
    finally:
        client.close()
    assert version.version_id == "438.0"
    assert version.last_modified == "2026-09-04T19:53:50Z"     # DEC-012 (catálogo de versões)
    assert set(version.sheets) == {"GED", "Projetos", "Painel de Controle"}
    workbook = version.workbook
    assert workbook.projects and workbook.ged and workbook.road_order
    sources = SourceManifest()
    sources.add(SourceRef("projects", name, None, drive_id=drive_id, item_id=item_id,
                          version_id=version.version_id))
    origins = projects_sheet_origins(sources)
    assert {(o["source"], o["version_id"]) for o in origins.values()} == {("projects", "438.0")}
    _text, _dash, _key, deviations = load_p22_projects(sources)
    assert deviations == []
    print(f"\nv{version.version_id} {version.last_modified} sha1={version.sha1} "
          f"projetos={len(workbook.projects)} ged={len(workbook.ged)} "
          f"rodovias={list(workbook.road_order)}")
    remote.clear_cache()
