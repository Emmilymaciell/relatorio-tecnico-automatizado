"""Planilha ambiental por VERSÃO do SharePoint, lida em memória, e resolução de `current`.

Offline: cliente graph FALSO e planilha ambiental SINTÉTICA montada em BytesIO; nada em disco.
`-m network`: lê a versão 310.0 de verdade (só GET, nada em disco, nada de token impresso) e
confere que as três abas saem da mesma versão (e, se o extrato do agente B estiver em tmp/, que
os agregados do 2.4 batem com ele).
"""

from __future__ import annotations

import io
from datetime import date, datetime
from pathlib import Path

import pytest

from prog_g2_report import REPO_ROOT
from prog_g2_report.builder.assemble import environmental_from_snapshot, load_environmental
from prog_g2_report.builder.context import SourceManifest, SourceRef
from prog_g2_report.sources import environmental as env
from prog_g2_report.sources import environmental_remote as remote
from prog_g2_report.sources import versions

ROADS = ("RD-103", "RD-101")
REF = date(2027, 1, 8)


def env_xlsx_bytes(extra_license: bool = False) -> bytes:
    """Planilha ambiental sintética (layout real: título + cabeçalho; Empresas B/G)."""
    import openpyxl

    lic_header = (None, "Nº Licença", "Nº Processo", "Empresa", "Fase da licença",
                  "Data de emissão", "Data de validade", "Órgão", "Atividade", "Status")
    cond_header = ("Item", "Nº Licença", "Nome da condicionante",
                   "Descrição/Informação complementar", "Evidências salvas em",
                   "Data da entrega", "Status", "Observações", "Responsável", "Vence em",
                   "Próxima entrega", "Vence em")
    licenses = [(None, 1, 123, "CONSTRUTORA ALFA", "Licença Ambiental Única", None,
                 datetime(2030, 1, 1), "OAMB", "x", "Vigente")]
    if extra_license:
        licenses.append((None, None, 124, "CONSTRUTORA BETA", "Outorga", None, None, "OAMB",
                         "x", "Aguardando a liberação"))
    sheets = {
        "Licenças": [("Licenças",), lic_header, *licenses],
        "Condicionantes": [("Condicionantes",), cond_header,
                           (1, 1, 5, None, None, datetime(2027, 3, 1), "No prazo", None,
                            "CONSTRUTORA ALFA", 0, None, 0)],
        "Empresas": [("Cadastro",), (), (None, "Empresa", None, None, None, None, "Rodovia"),
                     (None, "CONSTRUTORA ALFA", "x", None, None, None, ROADS[0]),
                     (None, "CONSTRUTORA BETA", "x", None, None, None, ROADS[1])],
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


class FakeGraph:
    """Só as duas leituras do graph_ro que o leitor usa; nada de escrita. Ordem do Graph
    embaralhada de propósito (o leitor não confia nela)."""

    def __init__(self, by_version: dict[str, bytes]):
        self.by_version = by_version
        self.reads: list[str] = []

    def versions(self, drive_id, item_id):
        stamps = {"8.0": "2027-01-08T10:00:00Z", "9.0": "2027-01-09T10:00:00Z",
                  "10.0": "2027-01-09T10:00:00Z"}
        return [{"id": v, "lastModifiedDateTime": stamps.get(v, "2027-01-01T00:00:00Z"),
                 "lastModifiedBy": {"user": {"displayName": f"Pessoa {v}"}}}
                for v in sorted(self.by_version)]

    def read_version_bytes(self, drive_id, item_id, version_id):
        self.reads.append(version_id)
        return self.by_version[version_id]


@pytest.fixture
def fake(tmp_path, monkeypatch):
    remote.clear_cache()
    monkeypatch.chdir(tmp_path)
    graph = FakeGraph({"8.0": env_xlsx_bytes(), "9.0": env_xlsx_bytes(),
                       "10.0": env_xlsx_bytes(extra_license=True)})
    yield graph
    remote.clear_cache()


def test_version_read_in_memory_gives_the_three_sheets_and_writes_nothing(fake, tmp_path):
    version = remote.read_version("d", "i", "v8", client=fake)
    assert version.version_id == "8.0" and version.last_modified == "2027-01-08T10:00:00Z"
    assert len(version.sha1) == 40
    workbook = version.workbook
    assert len(workbook.licenses) == 1 and len(workbook.conditions) == 1
    assert ROADS[0] in set(workbook.company_to_highway.values())
    remote.read_version("d", "i", "8", client=fake)
    assert fake.reads == ["8.0"]                              # uma leitura por processo
    assert list(tmp_path.iterdir()) == []                     # nada gravado em disco
    with pytest.raises(LookupError, match="GAP-015"):
        remote.read_version("d", "i", "99", client=fake)


def test_current_resolves_the_newest_version_not_the_graph_order(fake):
    # 9.0 e 10.0 com o mesmo instante: desempata pelo número da versão (10 > 9)
    version = remote.read_version("d", "i", "current", client=fake)
    assert version.version_id == "10.0" and len(version.workbook.licenses) == 2
    assert remote.cached("d", "i", "10.0") is version
    info = versions.resolve_version(fake, "d", "i", versions.CURRENT)
    assert (info.version_id, info.author) == ("10.0", "Pessoa 10.0")


def test_builder_reads_the_remote_environmental_source(fake):
    version = remote.read_version("d", "i", "9.0", client=fake)
    sources = SourceManifest()
    sources.add(SourceRef("environmental", "Ambiental", None, drive_id="d", item_id="i",
                          version_id=version.version_id))
    workbook = load_environmental(sources)
    assert workbook == version.workbook
    aggregates = env.aggregate(workbook, REF)
    assert aggregates.license_index.total == 1


def test_version_listing_is_newest_first_and_limited():
    graph = FakeGraph({"1.0": b"", "2.0": b"", "10.0": b""})
    rows = versions.version_rows(graph, "d", "i", last=2)
    assert [r.version_id for r in rows] == ["10.0", "2.0"]
    assert rows[0].author == "Pessoa 10.0" and graph.reads == []    # só metadados
    assert versions.normalize_version_id("v310") == "310.0"
    assert versions.is_current(" Current ") and not versions.is_current("310.0")


# ------------------------------------------------------------------ -m network (v310.0 real)
def _env_file() -> Path | None:
    from prog_g2_report.builder.generate import default_env_file

    return default_env_file()


def _snapshot_extract() -> Path | None:
    roots = [REPO_ROOT / "tmp"]
    if REPO_ROOT.parent.name == "worktrees":
        roots.append(REPO_ROOT.parents[2] / "tmp")
    return next((r / "agent_B" / "snapshots" / "v310.0.json" for r in roots
                 if (r / "agent_B" / "snapshots" / "v310.0.json").is_file()), None)


@pytest.mark.network
def test_network_v310_environmental_in_memory(request, tmp_path, monkeypatch):
    if "network" not in (request.config.getoption("markexpr") or ""):
        pytest.skip("network: rodar com -m network")
    env_file = _env_file()
    if env_file is None:
        pytest.skip(".env ausente")
    import json

    from prog_g2_report.model import load_model
    from prog_g2_report.sources import master_list_remote

    monkeypatch.chdir(tmp_path)
    name = load_model()["sources"]["environmental"]["name"]
    drive_id, item_id = master_list_remote.catalog_identity(name)
    remote.clear_cache()
    client = master_list_remote.default_client(env_file)
    try:
        version = remote.read_version(drive_id, item_id, "310.0", client=client)
    finally:
        client.close()
    assert version.version_id == "310.0" and version.last_modified
    workbook = version.workbook
    assert workbook.licenses and workbook.conditions and workbook.company_to_highway
    assert list(tmp_path.iterdir()) == []                     # nada gravado em disco
    extract = _snapshot_extract()
    if extract is not None:
        reference = date(2026, 9, 1)
        mine = env.aggregate(workbook, reference)
        theirs = env.aggregate(environmental_from_snapshot(
            json.loads(extract.read_text(encoding="utf-8"))), reference)
        assert mine.license_index == theirs.license_index
        assert mine.conditions_by_highway == theirs.conditions_by_highway
    print(f"\nv{version.version_id} {version.last_modified} sha1={version.sha1} "
          f"licenças={len(workbook.licenses)} condicionantes={len(workbook.conditions)}")
    remote.clear_cache()
