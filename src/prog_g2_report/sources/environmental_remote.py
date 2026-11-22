"""Planilha ambiental de uma VERSÃO do SharePoint, lida EM MEMÓRIA (regra nº 1, DEC-012).

Uso: `--environmental-version <id|current>` do `scripts/15_build_report.py` sem
`--environmental` (e o padrão do `scripts/17_generate_report.py`). A versão é lida por
`sharepoint.graph_ro` (`versions` + `read_version_bytes`, só GET), aberta pelo openpyxl a partir
de um `BytesIO` (`sources.environmental.load(bytes)`) e os bytes são descartados: nada é gravado
em disco.

As três abas do 2.4 (`config/g2_report_model.yaml: sources.environmental.sheets` = Licenças,
Condicionantes, Empresas) saem dos MESMOS bytes, portanto do MESMO snapshot (DEC-012). O Status
das condicionantes é recalculado com a data de referência explícita
(`sources.environmental.status_recalculation`), nunca o cache de TODAY() da planilha.

Identidade da fonte = (drive_id, item_id) do catálogo `data/catalog/work_sources.jsonl`, pelo
nome do modelo (`sources.environmental.name`). Mesmo padrão de `sources.projects_remote`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from prog_g2_report.sources import environmental as env
from prog_g2_report.sources.master_list_remote import VersionReader, default_client
from prog_g2_report.sources.versions import (
    is_current,
    normalize_version_id,
    read_version_payload,
)


@dataclass(frozen=True)
class RemoteEnvironmental:
    drive_id: str
    item_id: str
    version_id: str
    last_modified: str | None
    sha1: str                             # dos bytes lidos em memória (rastreabilidade)
    workbook: env.EnvironmentalWorkbook   # Licenças + Condicionantes + Empresas do mesmo snapshot


_CACHE: dict[tuple[str, str, str], RemoteEnvironmental] = {}


def read_version(drive_id: str, item_id: str, version_id: str | int | float, *,
                 client: VersionReader | None = None) -> RemoteEnvironmental:
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
    workbook = env.load(bytes(data))      # BytesIO dentro de `load`: nada vai para o disco
    del data
    result = RemoteEnvironmental(drive_id, item_id, meta.version_id, meta.last_modified, sha1,
                                 workbook)
    _CACHE[key] = result
    return result


def cached(drive_id: str, item_id: str,
           version_id: str | int | float) -> RemoteEnvironmental | None:
    return _CACHE.get((drive_id, item_id, normalize_version_id(version_id)))


def clear_cache() -> None:
    _CACHE.clear()
