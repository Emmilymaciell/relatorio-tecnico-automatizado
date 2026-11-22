"""Planilha de projetos de uma VERSÃO do SharePoint, lida EM MEMÓRIA (regra nº 1, DEC-012).

Uso: `--projects-version <id>` do `scripts/15_build_report.py` sem `--projects`. A versão é lida
por `sharepoint.graph_ro` (`versions` + `read_version_bytes`, só GET), aberta pelo openpyxl a
partir de um `BytesIO` (`sources.projects.load(bytes)`) e os bytes são descartados: nada é
gravado em disco.

As três abas do produto 2.2 (`config/g2_report_model.yaml: sources.projects.sheets` = GED,
Projetos, Painel de Controle) saem dos MESMOS bytes, portanto do MESMO snapshot (DEC-012: um
snapshot por fonte). A leitura de projetos não usa Excel COM (os quadros do 2.2 são PNG
reconstruídos do dado, DEC-009), então o 2.2 inteiro fecha numa versão.

Identidade da fonte = (drive_id, item_id) do catálogo `data/catalog/work_sources.jsonl`, pelo
nome do modelo (`sources.projects.name`). Mesmo padrão de `sources.master_list_remote`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from prog_g2_report.sources import projects as pj
from prog_g2_report.sources.master_list_remote import (
    VersionReader,
    default_client,
    normalize_version_id,
)
from prog_g2_report.sources.versions import is_current, read_version_payload


@dataclass(frozen=True)
class RemoteProjects:
    drive_id: str
    item_id: str
    version_id: str
    last_modified: str | None
    sha1: str                        # dos bytes lidos em memória (rastreabilidade no manifesto)
    workbook: pj.ProjectsWorkbook    # GED + Projetos + Painel de Controle do mesmo snapshot
    sheets: tuple[str, ...]          # abas do modelo presentes nesta versão


_CACHE: dict[tuple[str, str, str], RemoteProjects] = {}


def _sheets_present(workbook: pj.ProjectsWorkbook) -> tuple[str, ...]:
    present = [pj.SHEET_PROJECTS]
    if workbook.ged:
        present.append(pj.SHEET_GED)
    if workbook.road_order:
        present.append(pj.SHEET_PANEL)
    return tuple(present)


def read_version(drive_id: str, item_id: str, version_id: str | int | float, *,
                 client: VersionReader | None = None) -> RemoteProjects:
    """Lê a versão em memória (uma vez por processo) e devolve as três abas + metadados.
    `version_id` = id explícito ou `current` (a versão vigente, `sources.versions`)."""
    if not is_current(version_id):
        version_id = normalize_version_id(version_id)
        if (drive_id, item_id, version_id) in _CACHE:
            return _CACHE[(drive_id, item_id, version_id)]
    own = client is None
    reader: Any = default_client() if own else client
    try:
        meta, data = read_version_payload(reader, drive_id, item_id, version_id)
    finally:
        if own:
            reader.close()
    key = (drive_id, item_id, meta.version_id)
    if key in _CACHE:
        return _CACHE[key]
    sha1 = hashlib.sha1(data).hexdigest()
    workbook = pj.load(bytes(data))      # BytesIO dentro de `load`: nada vai para o disco
    del data
    result = RemoteProjects(drive_id, item_id, meta.version_id, meta.last_modified, sha1,
                            workbook, _sheets_present(workbook))
    _CACHE[key] = result
    return result


def cached(drive_id: str, item_id: str, version_id: str | int | float) -> RemoteProjects | None:
    return _CACHE.get((drive_id, item_id, normalize_version_id(version_id)))


def clear_cache() -> None:
    _CACHE.clear()
