"""Leitura da Lista Mestra — o manifesto do Relatório G2 (DEC-006).

Regras do modelo (`config/report_spec_draft.yaml`, bloco `selection`):

- seleção por `N° Relatório == report_number`, nunca por data, status, empresa ou linha oculta;
- ordem = ordem física da linha na planilha; nunca reordenar;
- autofiltro salvo e linhas ocultas não são verdade (DEC-009): lê-se tudo.

O cabeçalho é localizado pelo conteúdo, não por posição fixa, e os nomes são normalizados sem
acento para tolerar a codificação da planilha.
"""

from __future__ import annotations

import io
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import IO, Any

SHEET = "Controle Geral"

# nome normalizado do cabeçalho -> atributo
_HEADERS = {
    "produto": "product",
    "empresa": "company",
    "documento": "document",
    "manifestacao": "manifestation",
    "parecer": "manifestation",        # nome da mesma coluna em versões de julho (v134.0)
    "descricao": "description",
    "empreendimento": "venture",
    "data entrega": "delivery_date",
    "status entrega": "delivery_status",
    "versao": "version",
    "n relatorio": "report_number",
    "periodo": "period",
}


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c) and c.isprintable())
    text = text.replace("°", "").replace("º", "").replace("�", "")
    return " ".join(text.lower().split())


def _header_key(value: Any) -> str | None:
    norm = _norm(value)
    if not norm:
        return None
    if norm.startswith("contem anexos") or norm.startswith("contm anexos"):
        return "has_annexes"
    squashed = " ".join("".join(c for c in norm if c.isalnum() or c == " ").split())
    if squashed in _HEADERS:
        return _HEADERS[squashed]
    # tolera caracteres perdidos na codificação ("Relat�rio" -> "relatrio")
    best = max(_HEADERS, key=lambda k: SequenceMatcher(None, k, squashed).ratio())
    if SequenceMatcher(None, best, squashed).ratio() >= 0.85:
        return _HEADERS[best]
    return None


@dataclass(frozen=True)
class MasterListRow:
    physical_row: int                 # linha do Excel (1-based): a ordem canônica
    product: str
    company: str | None
    document: str
    manifestation: str | None
    description: str | None
    venture: str | None
    delivery_date: date | None
    delivery_status: str | None
    version: Any
    report_number: int | None
    period: Any = None
    has_annexes: Any = None

    @property
    def product_code(self) -> str:
        """'2.1 COORDENAÇÃO ...' -> '2.1'."""
        return self.product.split()[0] if self.product else ""


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def find_header(rows: list[tuple], scan: int = 12) -> tuple[int, dict[int, str]]:
    """Devolve (índice 0-based da linha de cabeçalho, {coluna: atributo})."""
    for index, row in enumerate(rows[:scan]):
        mapping = {col: key for col, cell in enumerate(row) if (key := _header_key(cell))}
        if {"product", "document", "report_number"} <= set(mapping.values()):
            return index, mapping
    raise ValueError("cabeçalho da Lista Mestra não encontrado (Produto/Documento/N° Relatório)")


def parse_rows(rows: Iterable[tuple], first_row_number: int = 1) -> list[MasterListRow]:
    """Converte linhas cruas (tuplas de valores) em `MasterListRow`, preservando a ordem."""
    rows = list(rows)
    header_index, mapping = find_header(rows)
    parsed: list[MasterListRow] = []
    for offset, row in enumerate(rows[header_index + 1 :], start=header_index + 1):
        values = {key: (row[col] if col < len(row) else None) for col, key in mapping.items()}
        document = values.get("document")
        if document is None or str(document).strip() == "":
            continue
        parsed.append(
            MasterListRow(
                physical_row=first_row_number + offset,
                product=str(values.get("product") or "").strip(),
                company=values.get("company"),
                document=str(document).strip(),
                manifestation=values.get("manifestation"),
                description=values.get("description"),
                venture=values.get("venture"),
                delivery_date=_as_date(values.get("delivery_date")),
                delivery_status=values.get("delivery_status"),
                version=values.get("version"),
                report_number=_as_int(values.get("report_number")),
                period=values.get("period"),
                has_annexes=values.get("has_annexes"),
            )
        )
    return parsed


def load(path: Path | IO[bytes], sheet: str = SHEET) -> list[MasterListRow]:
    """Lê a aba inteira, ignorando autofiltro e ocultação (openpyxl lê todas as linhas)."""
    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = list(workbook[sheet].iter_rows(values_only=True))
    finally:
        workbook.close()
    return parse_rows(rows)


def load_bytes(data: bytes, sheet: str = SHEET) -> list[MasterListRow]:
    """Mesma leitura de `load`, a partir de bytes EM MEMÓRIA (nada vai para disco)."""
    return load(io.BytesIO(data), sheet)


def load_source(ref: Any) -> list[MasterListRow]:
    """Linhas da Lista Mestra de um `SourceRef` (builder.context).

    `local_path` -> arquivo (cópia autorizada em tmp/). Sem `local_path`, com `drive_id`,
    `item_id` e `version_id` -> a versão é lida EM MEMÓRIA pelo `graph_ro`
    (`sources.master_list_remote`), sem gravar bytes (regra nº 1; GAP-015).
    """
    if getattr(ref, "local_path", None):
        return load(Path(ref.local_path))
    if ref.drive_id and ref.item_id and ref.version_id:
        from prog_g2_report.sources.master_list_remote import read_version

        return list(read_version(ref.drive_id, ref.item_id, ref.version_id).rows)
    raise ValueError("Lista Mestra sem local_path e sem (drive_id, item_id, version_id)")


def select(
    rows: Iterable[MasterListRow], report_number: int, product: str | None = None
) -> list[MasterListRow]:
    """Linhas do relatório, na ordem física. `product` = '2.2' filtra pelo código do produto."""
    chosen = [r for r in rows if r.report_number == report_number]
    if product is not None:
        chosen = [r for r in chosen if r.product_code == product]
    return sorted(chosen, key=lambda r: r.physical_row)


def select_index(rows: Iterable[MasterListRow], report_number: int) -> list[MasterListRow]:
    """Linhas do índice de ANEXOS e do total do encerramento: só as entregues (DEC-012)."""
    return [r for r in select(rows, report_number) if _norm(r.delivery_status) == "entregue"]
