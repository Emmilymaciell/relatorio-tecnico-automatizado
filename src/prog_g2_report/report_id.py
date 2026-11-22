"""Vocabulario canonico do projeto: como o documento e nomeado e identificado.

O objeto de trabalho e o **Relatorio G2** (por extenso, "Relatorio Mensal do G2").
"RM14" NAO e nomenclatura do sistema: aparece apenas quando se cita o nome literal de um
arquivo de terceiros. Em texto, use `format_report()`:

    Relatorio G2 nº 14 — Agosto/2026

Tecnicamente, um relatorio e identificado por dois campos independentes:

    report_number     14          inteiro, sequencial no contrato
    reference_month   "2026-08"   mes de referencia, ISO ano-mes

Esses dois campos sao a chave em todo catalogo, schema e nome de variavel.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

GROUP = "G2"
REPORT_LABEL = "Relatório G2"
REPORT_LABEL_LONG = "Relatório Mensal do G2"

MONTHS_PT = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
MONTH_NAMES = {number: name.capitalize() for name, number in MONTHS_PT.items()}
MONTH_NAMES[3] = "Março"

# Nome de pasta mensal: "14. Agosto 2026", "09. Março 2026", "07.Janeiro 2026".
MONTHLY_FOLDER = re.compile(r"^(\d{1,2})\s*\.\s*(.+?)\s+(\d{4})\s*$")

# Nome de arquivo: "... Relatório Mensal N°14 - 08 2026.docx"; tolera o mojibake
# "NB014" que aparece em nomes sanitizados de arquivos assinados.
REPORT_FILENAME = re.compile(
    r"Relat[oó]rio[ _]Mensal[ _]N[°ºo]?B?0*(\d{1,2})"
    r"(?:[ _]*-[ _]*(\d{2})[ _]+(\d{4}))?",
    re.IGNORECASE,
)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


def reference_month(year: int, month: int) -> str:
    """(2026, 8) -> '2026-08'."""
    return f"{year:04d}-{month:02d}"


def month_label(ref: str) -> str:
    """'2026-08' -> 'Agosto/2026'."""
    year, month = ref.split("-")
    return f"{MONTH_NAMES[int(month)]}/{year}"


def format_report(number: int | None, ref: str | None = None) -> str:
    """Nome canonico para texto: 'Relatório G2 nº 14 — Agosto/2026'."""
    if number is None:
        return REPORT_LABEL
    text = f"{REPORT_LABEL} nº {number:02d}"
    return f"{text} — {month_label(ref)}" if ref else text


@dataclass(frozen=True)
class ReportRef:
    """Identidade de um Relatorio G2: numero + mes de referencia."""

    report_number: int
    reference_month: str | None = None

    def __str__(self) -> str:
        return format_report(self.report_number, self.reference_month)

    def as_dict(self) -> dict:
        return {"report_number": self.report_number, "reference_month": self.reference_month}


def parse_monthly_folder(name: str) -> ReportRef | None:
    """Le '14. Agosto 2026'. O prefixo e o numero do relatorio (confirmado na Fase 2)."""
    match = MONTHLY_FOLDER.match(name)
    if not match:
        return None
    number, month_name, year = match.groups()
    month = MONTHS_PT.get(strip_accents(month_name).strip().lower())
    if month is None:
        return None
    return ReportRef(int(number), reference_month(int(year), month))


def parse_report_filename(name: str) -> ReportRef | None:
    """Le o numero (e o mes, quando presente) do nome do arquivo do relatorio."""
    match = REPORT_FILENAME.search(name)
    if not match:
        return None
    number, month, year = match.groups()
    ref = reference_month(int(year), int(month)) if month and year else None
    return ReportRef(int(number), ref)
