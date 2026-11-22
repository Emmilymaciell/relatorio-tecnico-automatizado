"""Lista Mestra de uma VERSÃO do SharePoint, lida EM MEMÓRIA (regra nº 1, DEC-012).

Uso: `--master-list-version <id>` do `scripts/15_build_report.py` sem `--master-list`. A versão é
lida por `sharepoint.graph_ro` (`versions` + `read_version_bytes`, só GET), convertida em linhas
e os bytes são descartados: nada é gravado em disco. Isso serve às partes PURAS do builder
(seleção `body_rows`/`index_rows`, textos, contagem de anexos do encerramento).

Limite (GAP-015): o Controle de Produtos é um EMF exportado pelo Excel COM a partir do ARQUIVO da
Lista Mestra (DEC-010); com a fonte só em memória ele fica PENDING. Persistir o arquivo da
versão em `tmp/` exige autorização explícita da Emmily — este módulo não contorna isso.

Identidade da fonte = (drive_id, item_id) do catálogo `data/catalog/work_sources.jsonl`, pelo
nome do modelo (`config/g2_report_model.yaml: sources.master_list.name`).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from prog_g2_report import REPO_ROOT
from prog_g2_report.sources.master_list import MasterListRow, load_bytes
from prog_g2_report.sources.versions import (
    is_current,
    normalize_version_id,
    read_version_payload,
)

WORK_SOURCES = REPO_ROOT / "data" / "catalog" / "work_sources.jsonl"


class VersionReader(Protocol):
    def versions(self, drive_id: str, item_id: str) -> list[dict]: ...

    def read_version_bytes(self, drive_id: str, item_id: str, version_id: str) -> bytes: ...


@dataclass(frozen=True)
class RemoteVersion:
    drive_id: str
    item_id: str
    version_id: str
    last_modified: str | None
    sha1: str                       # dos bytes lidos em memória (rastreabilidade no manifesto)
    rows: tuple[MasterListRow, ...]


_CACHE: dict[tuple[str, str, str], RemoteVersion] = {}


def catalog_identity(name: str, path: Path = WORK_SOURCES) -> tuple[str, str]:
    """(drive_id, item_id) da fonte de trabalho `name` no catálogo (DEC-003)."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("name") == name:
            return entry["drive_id"], entry["item_id"]
    raise LookupError(f"fonte {name!r} ausente de {path.name}")


def default_client(env_file: Path | None = None) -> Any:
    """Cliente `graph_ro` com a credencial do `.env` (DEC-004); nunca expõe o segredo."""
    from prog_g2_report.settings import Settings, load_settings
    from prog_g2_report.sharepoint.auth import build_token_provider
    from prog_g2_report.sharepoint.graph_ro import GraphReadOnlyClient

    settings = Settings(_env_file=env_file) if env_file else load_settings()  # type: ignore[call-arg]
    return GraphReadOnlyClient(build_token_provider(settings).token)


def read_version(drive_id: str, item_id: str, version_id: str, *,
                 client: VersionReader | None = None) -> RemoteVersion:
    """Lê a versão em memória (uma vez por processo) e devolve linhas + metadados.
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
    rows = tuple(load_bytes(data))
    del data
    result = RemoteVersion(drive_id, item_id, meta.version_id, meta.last_modified, sha1, rows)
    _CACHE[key] = result
    return result


def clear_cache() -> None:
    _CACHE.clear()
