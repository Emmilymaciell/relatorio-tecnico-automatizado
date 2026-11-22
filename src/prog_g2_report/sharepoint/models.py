"""Modelos dos objetos descobertos no SharePoint.

Identidade canonica de um arquivo/pasta e `(drive_id, item_id)`. Caminho e nome sao
atributos mutaveis e servem apenas para leitura humana e busca.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SiteRef(BaseModel):
    id: str
    display_name: str | None = None
    web_url: str | None = None
    hostname: str
    site_path: str


class DriveRef(BaseModel):
    id: str
    name: str
    drive_type: str | None = None
    web_url: str | None = None
    site_id: str


class ItemRef(BaseModel):
    """Um driveItem (arquivo ou pasta), com os metadados usados no inventario."""

    drive_id: str
    item_id: str
    name: str
    path: str = Field(description="Caminho relativo a raiz do drive, separador '/'")
    is_folder: bool
    size: int | None = None
    child_count: int | None = None
    mime_type: str | None = None
    quick_xor_hash: str | None = None
    etag: str | None = None
    ctag: str | None = None
    created: datetime | None = None
    modified: datetime | None = None
    web_url: str | None = None
    parent_item_id: str | None = None

    @property
    def extension(self) -> str:
        return self.name.rsplit(".", 1)[-1].lower() if "." in self.name else ""

    @classmethod
    def from_graph(cls, item: dict, drive_id: str | None = None) -> ItemRef:
        parent = item.get("parentReference") or {}
        parent_path = parent.get("path", "")
        folder_part = parent_path.split("root:", 1)[1] if "root:" in parent_path else ""
        folder_part = folder_part.strip("/")
        from urllib.parse import unquote

        folder_part = unquote(folder_part)
        name = item.get("name", "")
        path = f"{folder_part}/{name}" if folder_part else name
        file_meta = item.get("file") or {}
        folder_meta = item.get("folder")
        return cls(
            drive_id=drive_id or parent.get("driveId", ""),
            item_id=item["id"],
            name=name,
            path=path,
            is_folder=folder_meta is not None,
            size=item.get("size"),
            child_count=(folder_meta or {}).get("childCount"),
            mime_type=file_meta.get("mimeType"),
            quick_xor_hash=(file_meta.get("hashes") or {}).get("quickXorHash"),
            etag=item.get("eTag"),
            ctag=item.get("cTag"),
            created=item.get("createdDateTime"),
            modified=item.get("lastModifiedDateTime"),
            web_url=item.get("webUrl"),
            parent_item_id=parent.get("id"),
        )


class FolderSummary(BaseModel):
    """Resumo por metadados de uma pasta (sem baixar nada)."""

    folder: ItemRef
    file_count: int = 0
    folder_count: int = 0
    total_size: int = 0
    last_modified: datetime | None = None
    extensions: dict[str, int] = Field(default_factory=dict)
    depth_scanned: int = 0
