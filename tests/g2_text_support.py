"""Apoio dos testes do motor de blocos: documento vazio com os styleIds do nº 14 e linhas
sintéticas da Lista Mestra. Nada aqui vem de documento corporativo."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.style import WD_STYLE_TYPE

from prog_g2_report.builder.context import (
    RenderContext,
    ReportContext,
    SourceManifest,
)
from prog_g2_report.model import load_model
from prog_g2_report.report_id import ReportRef
from prog_g2_report.sources.master_list import MasterListRow

STYLE_IDS = ("Ttulo", "Ttulo1", "Ttulo2", "Ttulo3", "PargrafodaLista")


def make_document():
    doc = Document()
    for style_id in STYLE_IDS:
        doc.styles.add_style(style_id, WD_STYLE_TYPE.PARAGRAPH)
    return doc


def row(product: str, document: str, number: int = 14, status: str = "Entregue",
        description: str | None = "desc", physical_row: int = 10) -> MasterListRow:
    names = {"2.1": "COORDENAÇÃO", "2.2": "PROJETOS", "2.3": "CONTRATAÇÕES",
             "2.4": "GERENCIAMENTO", "2.5": "RECEBIMENTO", "2.6": "LICENCIAMENTO"}
    return MasterListRow(
        physical_row=physical_row, product=f"{product} {names[product]}", company="Empresa X",
        document=document, manifestation="Parecer", description=description, venture="RD-000",
        delivery_date=None, delivery_status=status, version=1, report_number=number,
    )


def usual_rows(number: int = 14) -> list[MasterListRow]:
    """Produtos 2.1, 2.2 e 2.4 ativos; 2.3, 2.5 e 2.6 sem linhas."""
    return [
        row("2.1", "AT-501.1", number, physical_row=10),
        row("2.2", "PA-502.1", number, physical_row=11),
        row("2.4", "RO-503.1", number, physical_row=12),
        row("2.4", "BM-004.1", number, status="Em elaboração", physical_row=13),
    ]


def make_rc(
    number: int = 14,
    ref: str = "2026-08",
    issue: date = date(2026, 9, 8),
    signature: date | None = date(2026, 9, 9),
    rows: list[MasterListRow] | None = None,
    inputs: dict[str, Any] | None = None,
    page_count: int | None = 43,
    tmp: Path | None = None,
    model: dict[str, Any] | None = None,
) -> RenderContext:
    data: dict[str, Any] = {
        "master_list_rows": usual_rows(number) if rows is None else rows,
        "inputs": {"signatory_name": "Fulano de Tal"} if inputs is None else inputs,
    }
    if page_count is not None:
        data["page_count"] = page_count
    report = ReportContext(ReportRef(number, ref), issue_date=issue, signature_date=signature)
    work = tmp or Path(".")
    return RenderContext(report=report, model=model or load_model(), sources=SourceManifest(),
                         document=make_document(), assets_dir=work, work_dir=work, data=data)


def body_texts(rc: RenderContext) -> list[str]:
    return [p.text for p in rc.document.paragraphs]
