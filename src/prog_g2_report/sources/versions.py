"""Histórico de versões de uma fonte no SharePoint, SOMENTE LEITURA (regra nº 1, DEC-012).

Funções puras sobre o leitor `graph_ro` (`versions`, `read_version_bytes`: só GET). Servem às
três fontes do modelo (`config/g2_report_model.yaml: sources.master_list`, `sources.projects`,
`sources.environmental`), lidas por versão EM MEMÓRIA:

- `resolve_version(reader, drive, item, "current")` -> a versão VIGENTE (a mais recente do
  histórico, `sources.<fonte>.snapshot.production`: "estado no instante da geração; versão
  registrada no manifesto"); com um id explícito ('438', 'v438', '438.0'), a própria versão;
- `read_version_payload(...)` -> (metadados, bytes) da versão; os bytes vivem só em memória e
  o chamador os descarta depois de convertê-los;
- `version_rows(...)` -> linhas (id, lastModified, autor) para a listagem do
  `scripts/16_list_versions.py`.

Nada aqui grava em disco. Versão ausente do histórico (podada: limite de 500 versões) levanta
`LookupError` com a referência GAP-015.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

# Pedido de versão que se resolve para a mais recente do histórico (produção mensal).
CURRENT = "current"
_NUMERIC = re.compile(r"^(\d+)(?:\.(\d+))?$")


class VersionReader(Protocol):
    def versions(self, drive_id: str, item_id: str) -> list[dict]: ...

    def read_version_bytes(self, drive_id: str, item_id: str, version_id: str) -> bytes: ...


@dataclass(frozen=True)
class VersionInfo:
    """Uma entrada do histórico de versões (sem conteúdo)."""

    version_id: str
    last_modified: str | None
    author: str | None
    size: int | None = None


def normalize_version_id(version_id: str | int | float) -> str:
    """'162' / 162 / 'v162' -> '162.0' (forma dos ids de versão do Graph)."""
    text = str(version_id).strip().lower().removeprefix("v")
    return text if "." in text else f"{text}.0"


def is_current(requested: Any) -> bool:
    return str(requested or "").strip().lower() == CURRENT


def _author(meta: Mapping[str, Any]) -> str | None:
    by = meta.get("lastModifiedBy") or {}
    for key in ("user", "application", "device"):
        name = (by.get(key) or {}).get("displayName")
        if name:
            return str(name)
    return None


def info(meta: Mapping[str, Any]) -> VersionInfo:
    size = meta.get("size")
    return VersionInfo(str(meta.get("id")), meta.get("lastModifiedDateTime"), _author(meta),
                       int(size) if isinstance(size, (int, float)) else None)


def _sort_key(meta: Mapping[str, Any]) -> tuple[str, int, int]:
    match = _NUMERIC.match(str(meta.get("id") or ""))
    major, minor = (int(match.group(1)), int(match.group(2) or 0)) if match else (-1, -1)
    return (str(meta.get("lastModifiedDateTime") or ""), major, minor)


def newest_first(entries: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Histórico do mais recente para o mais antigo (instante; empate pelo número da versão).
    Não confia na ordem devolvida pelo Graph."""
    return sorted(entries, key=_sort_key, reverse=True)


def latest(reader: VersionReader, drive_id: str, item_id: str) -> Mapping[str, Any]:
    entries = newest_first(reader.versions(drive_id, item_id))
    if not entries:
        raise LookupError("o item não tem histórico de versões no SharePoint")
    return entries[0]


def find(reader: VersionReader, drive_id: str, item_id: str,
         version_id: str | int | float) -> Mapping[str, Any]:
    wanted = normalize_version_id(version_id)
    meta = next((v for v in reader.versions(drive_id, item_id) if str(v.get("id")) == wanted),
                None)
    if meta is None:
        raise LookupError(f"versão {wanted} não existe mais no histórico do SharePoint "
                          "(poda de 500 versões; GAP-015)")
    return meta


def resolve_version(reader: VersionReader, drive_id: str, item_id: str,
                    requested: str | int | float) -> VersionInfo:
    """`current` -> a versão vigente; id explícito -> a própria versão (que tem de existir)."""
    meta = latest(reader, drive_id, item_id) if is_current(requested) else \
        find(reader, drive_id, item_id, requested)
    return info(meta)


def read_version_payload(reader: VersionReader, drive_id: str, item_id: str,
                         version_id: str | int | float) -> tuple[VersionInfo, bytes]:
    """(metadados, bytes) de uma versão, lidos em memória. `version_id` pode ser `current`."""
    meta = resolve_version(reader, drive_id, item_id, version_id)
    return meta, reader.read_version_bytes(drive_id, item_id, meta.version_id)


def version_rows(reader: VersionReader, drive_id: str, item_id: str,
                 last: int | None = None) -> list[VersionInfo]:
    """Histórico (mais recente primeiro), opcionalmente só as `last` últimas versões."""
    entries = [info(m) for m in newest_first(reader.versions(drive_id, item_id))]
    return entries[:last] if last else entries
