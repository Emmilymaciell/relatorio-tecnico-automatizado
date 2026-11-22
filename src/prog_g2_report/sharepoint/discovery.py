"""Descoberta read-only do SharePoint: site -> drive -> pastas -> inventario por metadados.

Nada aqui baixa conteudo, exceto `download_authorized()`, que exige uma autorizacao
explicita (registrada em `state/download_authorizations.jsonl`) e grava apenas em
`tmp/downloads/`. Leitura em memoria (`GraphReadOnlyClient.read_bytes`) nao passa por aqui.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from prog_g2_report import REPO_ROOT
from prog_g2_report.security import (
    ProtectedPathError,
    assert_download_destination,
    assert_write_allowed,
)
from prog_g2_report.sharepoint.graph_ro import GraphReadOnlyClient
from prog_g2_report.sharepoint.models import DriveRef, FolderSummary, ItemRef, SiteRef

AUTHORIZATIONS_LOG = REPO_ROOT / "state" / "download_authorizations.jsonl"


class Discovery:
    def __init__(self, client: GraphReadOnlyClient):
        self.client = client

    # ------------------------------------------------------------ site / drives
    def resolve_site(self, hostname: str, site_path: str) -> SiteRef:
        data = self.client.site_by_path(hostname, site_path)
        return SiteRef(
            id=data["id"],
            display_name=data.get("displayName"),
            web_url=data.get("webUrl"),
            hostname=hostname,
            site_path=site_path,
        )

    def list_drives(self, site: SiteRef) -> list[DriveRef]:
        return [
            DriveRef(
                id=d["id"],
                name=d.get("name", ""),
                drive_type=d.get("driveType"),
                web_url=d.get("webUrl"),
                site_id=site.id,
            )
            for d in self.client.site_drives(site.id)
        ]

    def find_drive(self, site: SiteRef, name: str) -> DriveRef | None:
        wanted = name.strip().casefold()
        for drive in self.list_drives(site):
            if drive.name.strip().casefold() == wanted:
                return drive
        return None

    # ------------------------------------------------------------ itens
    def item_by_path(self, drive: DriveRef, relative_path: str) -> ItemRef:
        return ItemRef.from_graph(self.client.item_by_path(drive.id, relative_path), drive.id)

    def children(self, drive_id: str, item_id: str | None = None) -> Iterator[ItemRef]:
        for raw in self.client.children(drive_id, item_id):
            yield ItemRef.from_graph(raw, drive_id)

    def walk(
        self, drive_id: str, item_id: str | None, max_depth: int = 3
    ) -> Iterator[tuple[int, ItemRef]]:
        """Percorre pastas em largura ate `max_depth`, so metadados. Gera (profundidade, item)."""
        queue: list[tuple[int, str | None]] = [(0, item_id)]
        while queue:
            depth, current = queue.pop(0)
            for item in self.children(drive_id, current):
                yield depth, item
                if item.is_folder and depth + 1 < max_depth:
                    queue.append((depth + 1, item.item_id))

    def summarize(self, folder: ItemRef, max_depth: int = 3) -> FolderSummary:
        summary = FolderSummary(folder=folder, depth_scanned=max_depth)
        for _depth, item in self.walk(folder.drive_id, folder.item_id, max_depth):
            if item.is_folder:
                summary.folder_count += 1
            else:
                summary.file_count += 1
                summary.total_size += item.size or 0
                ext = item.extension or "(sem extensao)"
                summary.extensions[ext] = summary.extensions.get(ext, 0) + 1
            newer = summary.last_modified is None or (
                item.modified is not None and item.modified > summary.last_modified
            )
            if item.modified and newer:
                summary.last_modified = item.modified
        return summary

    # ------------------------------------------------------------ download autorizado
    def download_authorized(
        self,
        item: ItemRef,
        authorization: DownloadAuthorization,
        destination_dir: Path | None = None,
    ) -> Path:
        """Grava o conteudo em tmp/downloads/ SOMENTE com autorizacao explicita.

        A autorizacao e registrada em `state/download_authorizations.jsonl` antes do
        download. Sem autorizacao (ou com item diferente) levanta ProtectedPathError.
        """
        if authorization.item_id != item.item_id or authorization.drive_id != item.drive_id:
            raise ProtectedPathError("autorizacao nao corresponde ao item pedido")
        if not authorization.granted_by.strip():
            raise ProtectedPathError("autorizacao sem responsavel identificado")
        base = destination_dir or (REPO_ROOT / "tmp" / "downloads" / authorization.purpose_slug)
        target = assert_download_destination(base / item.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        authorization.record()
        data = self.client.read_bytes(
            item.drive_id, item.item_id, max_bytes=authorization.max_bytes
        )
        target.write_bytes(data)
        return target


@dataclass
class DownloadAuthorization:
    """Registro de que a usuaria autorizou copiar um arquivo bruto para tmp/."""

    drive_id: str
    item_id: str
    item_name: str
    purpose: str
    granted_by: str
    granted_at: str = ""
    delete_after: bool = True
    max_bytes: int = 200 * 1024 * 1024

    @property
    def purpose_slug(self) -> str:
        return "".join(c if c.isalnum() else "_" for c in self.purpose.lower())[:60].strip("_")

    def record(self) -> None:
        self.granted_at = self.granted_at or datetime.now(UTC).isoformat(timespec="seconds")
        path = assert_write_allowed(AUTHORIZATIONS_LOG)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(self.__dict__, ensure_ascii=False) + "\n")
