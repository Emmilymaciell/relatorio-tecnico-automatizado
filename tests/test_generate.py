"""Comando único da produção (`builder.generate`, scripts 15, 16 e 17), offline.

Fontes SINTÉTICAS (as de `test_assemble`), cliente graph FALSO (só `versions` e
`read_version_bytes`), office=False. Nada é lido do SharePoint de verdade nem gravado fora de
`tmp_path`.
"""

from __future__ import annotations

import functools
import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from prog_g2_report import REPO_ROOT
from prog_g2_report.builder.assemble import build_report
from prog_g2_report.builder.generate import (
    InputError,
    SourceMismatchError,
    SourceOptions,
    build_sources,
    report_dates,
)
from prog_g2_report.model import load_model
from prog_g2_report.sources import environmental_remote, master_list_remote, projects_remote
from test_assemble import (
    NUMBER,
    _assets,
    _write_environmental,
    _write_master_list,
    _write_projects,
)

MONTH = "2026-12"
FIXTURE_INPUTS = Path(__file__).parent / "fixtures" / "golden_inputs_example.yaml"


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""),
                                                  REPO_ROOT / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _identity(key: str) -> tuple[str, str]:
    return master_list_remote.catalog_identity(load_model()["sources"][key]["name"])


class FakeGraph:
    """Histórico por item (identidade do catálogo); só leituras."""

    def __init__(self, items: dict[tuple[str, str], dict[str, bytes]]):
        self.items = items
        self.reads: list[tuple[str, str]] = []
        self.closed = False

    def versions(self, drive_id, item_id):
        history = self.items[(drive_id, item_id)]
        return [{"id": v, "lastModifiedDateTime": f"2027-01-{int(float(v)):02d}T09:00:00Z",
                 "lastModifiedBy": {"user": {"displayName": "Pessoa Sintética"}}}
                for v in history]

    def read_version_bytes(self, drive_id, item_id, version_id):
        self.reads.append((item_id, version_id))
        return self.items[(drive_id, item_id)][version_id]

    def close(self):
        self.closed = True


@pytest.fixture
def world(tmp_path):
    for module in (master_list_remote, projects_remote, environmental_remote):
        module.clear_cache()
    src = tmp_path / "src"
    src.mkdir()
    master = _write_master_list(src / "lista_mestre.xlsx")
    projects = _write_projects(src / "proj.xlsx").read_bytes()
    environmental = _write_environmental(src / "amb.xlsx").read_bytes()
    graph = FakeGraph({
        _identity("master_list"): {"2.0": master.read_bytes()},
        _identity("projects"): {"6.0": projects, "7.0": projects},
        _identity("environmental"): {"9.0": environmental},
    })
    inputs = yaml.safe_load(FIXTURE_INPUTS.read_text(encoding="utf-8"))
    inputs_path = tmp_path / "entradas.yaml"
    inputs_path.write_text(yaml.safe_dump(inputs, allow_unicode=True), encoding="utf-8")
    manifest = _assets(tmp_path / "assets")
    yield {"graph": graph, "master": master, "inputs": inputs, "inputs_path": inputs_path,
           "assets_dir": tmp_path / "assets", "assets_manifest": manifest, "root": tmp_path}
    for module in (master_list_remote, projects_remote, environmental_remote):
        module.clear_cache()


# ------------------------------------------------------------------ fontes
def test_current_resolves_every_source_and_verifies_the_local_master_list(world):
    opts = SourceOptions(master_list=world["master"], master_list_version="current",
                         projects_version="current", environmental_version="current",
                         verify_local=True)
    sources, resolution = build_sources(opts, load_model(), client=world["graph"])
    refs = sources.sources
    assert refs["master_list"].local_path == world["master"]       # Excel COM usa o arquivo
    assert refs["master_list"].version_id == "2.0"
    assert refs["master_list"].last_modified == "2027-01-02T09:00:00Z"
    assert refs["projects"].local_path is None and refs["projects"].version_id == "7.0"
    assert refs["environmental"].local_path is None and refs["environmental"].version_id == "9.0"
    assert resolution["master_list"]["local_copy_matches"] is True
    assert {k: (v["requested"], v["version_id"]) for k, v in resolution.items()} == {
        "master_list": ("current", "2.0"), "projects": ("current", "7.0"),
        "environmental": ("current", "9.0")}
    assert not world["graph"].closed            # cliente do chamador não é fechado aqui


def test_explicit_versions_are_kept_for_a_reconstruction(world):
    opts = SourceOptions(master_list=world["master"], master_list_version="2",
                         projects_version="6.0", environmental_version="9",
                         verify_local=True)
    sources, resolution = build_sources(opts, load_model(), client=world["graph"])
    assert sources.sources["projects"].version_id == "6.0"
    assert resolution["projects"] == {"requested": "6.0", "version_id": "6.0",
                                      "last_modified": "2027-01-06T09:00:00Z",
                                      "origin": "sharepoint_memory"}


def test_local_master_list_that_is_not_the_version_aborts(world, tmp_path):
    import openpyxl

    stale = tmp_path / "stale.xlsx"
    stale.write_bytes(world["master"].read_bytes())
    wb = openpyxl.load_workbook(stale)
    wb["Controle Geral"].append([None, "2.4 GERENCIAMENTO", "Empresa", "RO-599.1", "x", "y",
                                 "RD-103", None, "Entregue", 1, NUMBER, None])
    wb.save(stale)
    opts = SourceOptions(master_list=stale, master_list_version="current",
                         projects_version="current")
    with pytest.raises(SourceMismatchError, match="baixe de novo"):
        build_sources(opts, load_model(), client=world["graph"])


def test_label_only_without_verification_needs_no_client(world):
    opts = SourceOptions(master_list=world["master"], master_list_version="335.0")
    sources, resolution = build_sources(opts, load_model(), client=None)
    assert sources.sources["master_list"].version_id == "335.0" and resolution == {}


# ------------------------------------------------------------------ entradas
def test_dates_and_signatory_are_required_without_previous_report_default():
    inputs = {"issue_date": date(2027, 1, 11), "signature_date": "2027-01-12",
              "signatory_name": "Fulano"}
    assert report_dates(inputs) == (date(2027, 1, 11), date(2027, 1, 12))
    assert report_dates(inputs, "2027-01-20")[0] == date(2027, 1, 20)    # CLI prevalece
    with pytest.raises(InputError, match="signatory_name"):
        report_dates({**inputs, "signatory_name": "  "})
    with pytest.raises(InputError, match="issue_date, signature_date"):
        report_dates({"signatory_name": "Fulano"})
    model_inputs = load_model()["inputs"]
    for key in ("issue_date", "signature_date", "signatory_name"):
        assert model_inputs[key]["required"] is True
        assert "default_from" not in model_inputs[key] and "default" not in model_inputs[key]


# ------------------------------------------------------------------ scripts
def _build(world):
    return functools.partial(build_report, assets_manifest=world["assets_manifest"])


def test_script_17_generates_with_current_versions_and_prints_the_summary(world, capsys):
    gen = _script("17_generate_report.py")
    out = world["root"] / "out"
    code = gen.main(["--report-number", str(NUMBER), "--reference-month", MONTH,
                     "--inputs", str(world["inputs_path"]), "--master-list", str(world["master"]),
                     "--out", str(out), "--assets-dir", str(world["assets_dir"]), "--no-office"],
                    client=world["graph"], build=_build(world))
    printed = capsys.readouterr().out
    assert code == 1                                     # sem Word/Excel: pendente, não entrega
    assert printed.splitlines()[0].endswith("ok=False")
    assert "páginas: pendente (sem Word)" in printed
    assert "projects: pedido current -> 7.0" in printed
    assert "validação V_ALL_DOCS_IN_MASTER_LIST: pass" in printed
    assert f"manifesto: {out / 'manifest.json'}".lower() in printed.lower()   # normcase
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["report"]["issue_date"] == "2027-01-11"          # do YAML de entradas
    assert manifest["source_resolution"]["environmental"]["version_id"] == "9.0"
    by_key = {s["key"]: s for s in manifest["sources"]}
    assert by_key["environmental"]["snapshot_origin"] == "sharepoint:versions/9.0 (memória)"
    assert by_key["projects"]["last_modified"] == "2027-01-07T09:00:00Z"
    assert {v["id"] for v in manifest["validations"]} == {
        v["id"] for v in load_model()["validations"]}
    # SharePoint só lido: versões e bytes, nenhuma outra chamada existe no falso
    assert {v for _, v in world["graph"].reads} == {"2.0", "7.0", "9.0"}


def test_script_17_without_signatory_stops_before_building(world, capsys):
    gen = _script("17_generate_report.py")
    inputs = dict(world["inputs"])
    inputs.pop("signatory_name")
    path = world["root"] / "sem_signatario.yaml"
    path.write_text(yaml.safe_dump(inputs, allow_unicode=True), encoding="utf-8")
    out = world["root"] / "out2"
    code = gen.main(["--report-number", str(NUMBER), "--reference-month", MONTH,
                     "--inputs", str(path), "--master-list", str(world["master"]),
                     "--out", str(out), "--no-office"], client=world["graph"],
                    build=_build(world))
    assert code == 2 and "signatory_name" in capsys.readouterr().err
    assert not out.exists() and world["graph"].reads == []


def test_script_15_accepts_issue_date_from_the_inputs_and_environmental_version(world, capsys):
    build15 = _script("15_build_report.py")
    out = world["root"] / "out15"
    original = build15.run_build
    build15.run_build = functools.partial(original, build=_build(world))
    try:
        code = build15.main(["--report-number", str(NUMBER), "--reference-month", MONTH,
                             "--master-list", str(world["master"]),
                             "--projects-version", "7", "--environmental-version", "9.0",
                             "--inputs", str(world["inputs_path"]), "--out", str(out),
                             "--assets-dir", str(world["assets_dir"]), "--no-office"],
                            client=world["graph"])
    finally:
        build15.run_build = original
    assert code == 1
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["report"]["issue_date"] == "2027-01-11"
    assert manifest["source_resolution"]["environmental"]["requested"] == "9.0"
    assert "master_list" not in manifest["source_resolution"]      # rótulo do nome do arquivo
    assert capsys.readouterr().out.startswith("Relatório G2 nº 03 — Dezembro/2026")


def test_script_16_lists_versions_on_stdout_only(world, tmp_path, monkeypatch, capsys):
    listing = _script("16_list_versions.py")
    monkeypatch.chdir(tmp_path / "src")
    before = sorted(p.name for p in (tmp_path / "src").iterdir())
    assert listing.main(["--source", "projects", "--last", "1"], client=world["graph"]) == 0
    printed = capsys.readouterr().out.splitlines()
    assert printed[0].startswith(load_model()["sources"]["projects"]["name"])
    assert printed[2].split() == ["7.0", "2027-01-07T09:00:00Z", "Pessoa", "Sintética"]
    assert len(printed) == 3 and world["graph"].reads == []          # só o histórico
    assert sorted(p.name for p in (tmp_path / "src").iterdir()) == before
