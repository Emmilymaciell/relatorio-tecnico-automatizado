"""Leitura da planilha de projetos — "03 - Acompanhamento de Projetos Executivo.xlsx".

Fonte do produto 2.2 (`config/g2_report_model.yaml`, `sources.projects`): abas `GED`, `Projetos`
e `Painel de Controle`. Regras de leitura (`config/data_rules/p22_highway_block.yaml`):

- `meta.sources.projetos_executivo.read_policy`: todas as linhas, ignorando autofiltro e linhas
  ocultas (`sources.projects.ignore_saved_filter: true`). openpyxl lê todas as linhas.
- `meta.sources.projetos_executivo.header_row`: o cabeçalho é localizado pelo **conteúdo**
  (nomes normalizados sem acento), não pela posição.
- `normalization.road`: espaços e NBSP removidos e caixa alta — `'RD-102 A'` vira `'RD-102A'`.
  `'RD-103-0'` (2 linhas da aba GED) **não** se funde com `RD-103`: é o valor da fonte, mantido
  como está (`normalization.road.warn`).
- `normalization.situation_formula`: a coluna I (`Status (SITUAÇÃO)`) depende de `TODAY()`;
  `ProjectRow.situation(reference_date)` a recalcula com a data de referência explícita.

Três entradas, mesmo resultado (`ProjectsWorkbook`):

    load(path_or_bytes)            planilha .xlsx (caminho ou bytes já lidos em memória)
    from_rows(projetos, painel, ged)   linhas cruas (tuplas/listas de valores)
    from_extract(sheets)           extrato derivado do agente N (`projetos_versions.json`:
                                   ``{"Projetos": [{"row": i, "values": [...]}, ...], ...}``;
                                   ou `projetos_range.json`: lista de listas de valores)

Datas no extrato vêm como texto ISO ("2026-08-31"); são convertidas só nas colunas de data.
"""

from __future__ import annotations

import io
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

SHEET_PROJECTS = "Projetos"
SHEET_GED = "GED"
SHEET_PANEL = "Painel de Controle"

_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T]00:00:00(?:\.0+)?)?$")
_ROAD_TOKEN = re.compile(r"^\s*(RD\s*-\s*[0-9]+(?:\s*[A-Z])?)\b", re.IGNORECASE)

# cabeçalho normalizado (`_squash`) -> atributo. Aba Projetos (24 colunas A:X, estável em 128
# versões: meta.sources.projetos_executivo.header_stability).
_PROJECT_HEADERS = {
    "ordem disciplina": "order",
    "obra": "road",
    "grupo": "group",
    "disciplina": "discipline",
    "previsao de entrega": "forecast_date",
    "hoje": "today_cached",
    "data de recebimento": "received_date",
    "status prazo": "deadline_status_cached",
    "status situacao": "situation_cached",
    "ged n": "ged_number",
    "revisao": "revision",
    "inicio da analise ged": "ged_analysis_start",
    "devolutiva ged": "ged_return",
    "documento de recebimento de ged": "ged_receipt_document",
    "disciplina aceita": "accepted_raw",
    "inicio da analise aprovacao": "approval_analysis_start",
    "devolutiva aprovacao": "approval_return",
    "documento de analise de 2 nivel": "approval_document",
    "status avaliacao": "evaluation_raw",
    "entrega da revisao": "revision_delivery",
    "resumo disciplina": "summary",
}
_PROJECT_REQUIRED = {"order", "road", "group", "discipline"}
_PROJECT_DATES = {
    "forecast_date", "today_cached", "received_date", "ged_analysis_start", "ged_return",
    "approval_analysis_start", "approval_return",
}

# Aba GED (log de entregas): RODOVIA, FASE E/OU EVENTO, DISCIPLINA, REVISÃO, Data de Recebimento.
_GED_HEADERS = {
    "ged n": "ged_number",
    "rodovia": "road",
    "fase e ou evento": "group",
    "disciplina": "discipline",
    "revisao": "revision",
    "data de recebimento": "received_date",
}
_GED_REQUIRED = {"road", "group", "discipline", "received_date"}


# --------------------------------------------------------------------------- normalização
def _squash(value: Any) -> str:
    """Cabeçalho comparável: sem acento, minúsculas, pontuação vira espaço, espaços colapsados."""
    text = unicodedata.normalize("NFD", str(value or "")).replace("º", "").replace("°", "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = "".join(c if c.isalnum() else " " for c in text.lower())
    return " ".join(text.split())


def normalize_text(value: Any) -> str:
    """`normalization.text_fields`: NFC, NBSP vira espaço, trim, espaços colapsados, minúsculas."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value)).replace(" ", " ")
    return " ".join(text.split()).lower()


def clean_text(value: Any) -> str:
    """Texto de exibição: NFC, NBSP vira espaço, trim e espaços colapsados (caixa preservada)."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value)).replace(" ", " ")
    return " ".join(text.split())


def normalize_road(value: Any) -> str:
    """`normalization.road`: remove espaços (inclusive NBSP) e põe em maiúsculas.

    Mesmo efeito da fórmula da coluna V de Projetos
    (`SUBSTITUTE(TRIM(SUBSTITUTE(B,CHAR(160),' ')),' ','')`). `'RD-103-0'` permanece
    `'RD-103-0'`: não é fundido com `RD-103`.
    """
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value))
    return "".join(text.split()).upper()


def normalize_acceptance(value: Any) -> str:
    """`normalization.acceptance`: minúsculas e sem espaços ('Sim ', 'SIm' viram 'sim')."""
    return "".join(normalize_text(value).split())


def as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        match = _ISO_DATE.match(value.strip())
        if match:
            year, month, day = (int(g) for g in match.groups())
            return date(year, month, day)
    return None


def _date_or_text(value: Any) -> date | str | None:
    """Coluna W (Entrega da Revisão): data digitada ou texto ('Aguardando previsão')."""
    parsed = as_date(value)
    if parsed is not None:
        return parsed
    text = clean_text(value)
    return text or None


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "") or value == 0


def _text_or_blank(value: Any) -> str:
    """Valor de célula de fórmula `LET(v, INDEX(...), IF(OR(v="", v=0), "", v))`: 0 é vazio."""
    return "" if _blank(value) else clean_text(value)


def _as_int(value: Any) -> int | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def order_key(value: Any) -> tuple[int, int]:
    """`discipline_order_in_lines.rule`: Ordem Disciplina numérica (major, minor).

    '3.10' vem depois de '3.9'. Valores não numéricos vão para o fim.
    """
    text = clean_text(value)
    major, _, minor = text.partition(".")
    try:
        return int(major), int(minor or 0)
    except ValueError:
        return 10**6, 10**6


# --------------------------------------------------------------------------- linhas
@dataclass(frozen=True)
class ProjectRow:
    """Uma linha da aba Projetos (todas as linhas, inclusive as ocultas pelo autofiltro)."""

    physical_row: int
    order: str
    road: str                                  # normalizada (RD-102A)
    road_raw: str
    group: str                                 # GRUPO (trim)
    discipline: str                            # Disciplina (trim; nome de exibição)
    forecast_date: date | None = None          # E Previsão de Entrega
    received_date: date | None = None          # G Data de Recebimento
    revision: int | None = None                # K REVISÃO
    ged_analysis_start: Any = None             # L Início da Análise - GED (data ou texto)
    accepted_raw: str = ""                     # O Disciplina ACEITA? (como digitado)
    evaluation_raw: str = ""                   # S Status (AVALIAÇÃO) (como digitado)
    revision_delivery: date | str | None = None  # W Entrega da Revisão
    situation_cached: str = ""                 # I Status (SITUAÇÃO) — cache de TODAY()
    deadline_status_cached: str = ""           # H Status (PRAZO) — cache de TODAY()
    summary: str = ""                          # X Resumo Disciplina
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def order_key(self) -> tuple[int, int]:
        return order_key(self.order)

    @property
    def accepted(self) -> str:
        """'sim', 'não' ou '' (`normalization.acceptance`)."""
        return normalize_acceptance(self.accepted_raw)

    @property
    def evaluation(self) -> str:
        """Status (AVALIAÇÃO) normalizado em minúsculas (`normalization.text_fields`)."""
        return normalize_text(self.evaluation_raw)

    def situation(self, reference_date: date) -> str:
        """Recalcula Projetos!I com a data de referência (`normalization.situation_formula`).

        Mesma árvore da fórmula, com `reference_date` no lugar de `TODAY()`:
        Previsão vazia → 'Aguardando previsão'; S preenchido → 'Analisada'; L preenchido →
        'Em análise'; G preenchido → 'Aguardando início da análise'; Previsão < referência
        (H 'ESTÁ ATRASADO') → 'Atrasado'; senão (H 'Faltam') → 'No prazo'.
        """
        if self.forecast_date is None:
            return "Aguardando previsão"
        if self.evaluation_raw:
            return "Analisada"
        if not _blank(self.ged_analysis_start):
            return "Em análise"
        if self.received_date is not None:
            return "Aguardando início da análise"
        if self.forecast_date < reference_date:
            return "Atrasado"
        return "No prazo"


@dataclass(frozen=True)
class GedRow:
    """Uma entrega registrada na aba GED (log de recebimentos)."""

    physical_row: int
    road: str                      # normalizada; 'RD-103-0' fica como está
    road_raw: str
    group: str                     # FASE E/OU EVENTO (trim)
    discipline: str
    received_date: date | None
    revision: Any = None


@dataclass(frozen=True)
class ProjectsWorkbook:
    """As três abas já interpretadas. `road_order` vem do Painel de Controle (vazio se ausente)."""

    projects: tuple[ProjectRow, ...]
    ged: tuple[GedRow, ...] = ()
    road_order: tuple[str, ...] = ()
    road_labels: Mapping[str, str] = field(default_factory=dict)

    def roads(self) -> list[str]:
        """Rodovias presentes em Projetos, na ordem física de primeira aparição."""
        seen: dict[str, None] = {}
        for row in self.projects:
            seen.setdefault(row.road, None)
        return list(seen)


# --------------------------------------------------------------------------- cabeçalho
def _find_header(
    rows: Sequence[Sequence[Any]], headers: Mapping[str, str], required: set[str], scan: int = 12
) -> tuple[int, dict[int, str]]:
    for index, row in enumerate(rows[:scan]):
        mapping: dict[int, str] = {}
        for col, cell in enumerate(row or ()):
            key = headers.get(_squash(cell))
            if key and key not in mapping.values():
                mapping[col] = key
        if required <= set(mapping.values()):
            return index, mapping
    raise ValueError(f"cabeçalho não encontrado: faltam {sorted(required)}")


def _cell(row: Sequence[Any], col: int) -> Any:
    return row[col] if row is not None and col < len(row) else None


# --------------------------------------------------------------------------- parsers
def parse_projects(
    rows: Iterable[Sequence[Any]], physical_rows: Sequence[int] | None = None
) -> list[ProjectRow]:
    """Aba Projetos → `ProjectRow`, na ordem física. Linhas sem Obra são ignoradas."""
    rows = [list(r or ()) for r in rows]
    numbers = list(physical_rows) if physical_rows is not None else list(range(1, len(rows) + 1))
    header_index, mapping = _find_header(rows, _PROJECT_HEADERS, _PROJECT_REQUIRED)
    parsed: list[ProjectRow] = []
    for offset in range(header_index + 1, len(rows)):
        row = rows[offset]
        values = {key: _cell(row, col) for col, key in mapping.items()}
        if not clean_text(values.get("road")):
            continue
        for key in _PROJECT_DATES:
            if key in values:
                values[key] = as_date(values[key]) if values[key] is not None else None
        received = values.get("received_date")
        parsed.append(
            ProjectRow(
                physical_row=numbers[offset],
                order=clean_text(values.get("order")),
                road=normalize_road(values.get("road")),
                road_raw=str(values.get("road")),
                group=clean_text(values.get("group")),
                discipline=clean_text(values.get("discipline")),
                forecast_date=values.get("forecast_date"),
                received_date=received,
                revision=_as_int(values.get("revision")),
                ged_analysis_start=None if _blank(values.get("ged_analysis_start"))
                else values.get("ged_analysis_start"),
                accepted_raw=_text_or_blank(values.get("accepted_raw")),
                evaluation_raw=_text_or_blank(values.get("evaluation_raw")),
                revision_delivery=_date_or_text(values.get("revision_delivery")),
                situation_cached=clean_text(values.get("situation_cached")),
                deadline_status_cached=clean_text(values.get("deadline_status_cached")),
                summary=clean_text(values.get("summary")),
            )
        )
    return parsed


def parse_ged(
    rows: Iterable[Sequence[Any]], physical_rows: Sequence[int] | None = None
) -> list[GedRow]:
    """Aba GED → `GedRow`. Linhas sem RODOVIA ou FASE são ignoradas."""
    rows = [list(r or ()) for r in rows]
    numbers = list(physical_rows) if physical_rows is not None else list(range(1, len(rows) + 1))
    header_index, mapping = _find_header(rows, _GED_HEADERS, _GED_REQUIRED)
    parsed: list[GedRow] = []
    for offset in range(header_index + 1, len(rows)):
        row = rows[offset]
        values = {key: _cell(row, col) for col, key in mapping.items()}
        road = normalize_road(values.get("road"))
        group = clean_text(values.get("group"))
        if not road or not group:
            continue
        parsed.append(
            GedRow(
                physical_row=numbers[offset],
                road=road,
                road_raw=str(values.get("road")),
                group=group,
                discipline=clean_text(values.get("discipline")),
                received_date=as_date(values.get("received_date")),
                revision=values.get("revision"),
            )
        )
    return parsed


def parse_panel(rows: Iterable[Sequence[Any]]) -> tuple[tuple[str, ...], dict[str, str]]:
    """Painel de Controle → (ordem das rodovias, rótulo de cada rodovia).

    `road_order.source`: a linha que tem 'DISCIPLINA' traz os grupos de colunas por rodovia
    ('RD-103 - DELTA', 'RD-102A - CLX / TRAFEX', …), da esquerda para a direita.
    """
    for row in rows:
        cells = list(row or ())
        if not any(_squash(c) == "disciplina" for c in cells):
            continue
        order: list[str] = []
        labels: dict[str, str] = {}
        for cell in cells:
            if not isinstance(cell, str):
                continue
            match = _ROAD_TOKEN.match(cell)
            if not match:
                continue
            road = normalize_road(match.group(1))
            if road not in labels:
                order.append(road)
                labels[road] = clean_text(cell)
        if order:
            return tuple(order), labels
    return (), {}


# --------------------------------------------------------------------------- entradas
def from_rows(
    projects: Iterable[Sequence[Any]],
    panel: Iterable[Sequence[Any]] | None = None,
    ged: Iterable[Sequence[Any]] | None = None,
    *,
    projects_physical_rows: Sequence[int] | None = None,
    ged_physical_rows: Sequence[int] | None = None,
) -> ProjectsWorkbook:
    order, labels = parse_panel(panel) if panel is not None else ((), {})
    return ProjectsWorkbook(
        projects=tuple(parse_projects(projects, projects_physical_rows)),
        ged=tuple(parse_ged(ged, ged_physical_rows)) if ged is not None else (),
        road_order=order,
        road_labels=labels,
    )


def _split_extract(sheet: Any) -> tuple[list[list[Any]], list[int] | None]:
    """Aceita `[{"row": i, "values": [...]}, ...]` ou `[[...], ...]`."""
    if sheet is None:
        return [], None
    sheet = list(sheet)
    if sheet and isinstance(sheet[0], Mapping):
        values = [list(item.get("values") or ()) for item in sheet]
        return values, [int(item["row"]) for item in sheet]
    return [list(item or ()) for item in sheet], None


def from_extract(
    sheets: Mapping[str, Any] | Sequence[Any],
    *,
    panel: Any = None,
    ged: Any = None,
) -> ProjectsWorkbook:
    """Extrato derivado (sem acesso à planilha bruta), para o golden test.

    `sheets` é um item de `projetos_versions.json` (``{"Projetos": [...], "Painel de Controle":
    [...], "GED": [...]}``) ou a lista `rows` de `projetos_range.json` (só a aba Projetos).
    `panel` e `ged` completam abas que o extrato não tem.
    """
    if isinstance(sheets, Mapping):
        projects_rows, projects_numbers = _split_extract(sheets.get(SHEET_PROJECTS))
        panel = sheets.get(SHEET_PANEL, panel)
        ged = sheets.get(SHEET_GED, ged)
    else:
        projects_rows, projects_numbers = _split_extract(sheets)
    panel_rows, _ = _split_extract(panel)
    ged_rows, ged_numbers = _split_extract(ged)
    return from_rows(
        projects_rows,
        panel_rows if panel is not None else None,
        ged_rows if ged is not None else None,
        projects_physical_rows=projects_numbers,
        ged_physical_rows=ged_numbers,
    )


def load(source: Path | str | bytes) -> ProjectsWorkbook:
    """Lê a planilha (.xlsx) de um caminho ou de bytes em memória, todas as linhas das 3 abas.

    Somente leitura: `read_only=True, data_only=True` (valores em cache das fórmulas; a coluna
    I é recalculada por `ProjectRow.situation`). Autofiltro e ocultação não afetam a leitura.
    """
    import openpyxl

    handle: Any = io.BytesIO(source) if isinstance(source, bytes | bytearray) else Path(source)
    workbook = openpyxl.load_workbook(handle, read_only=True, data_only=True)
    try:
        def sheet_rows(name: str) -> list[tuple] | None:
            if name not in workbook.sheetnames:
                return None
            return list(workbook[name].iter_rows(values_only=True))

        projects = sheet_rows(SHEET_PROJECTS)
        if projects is None:
            raise ValueError(f"aba obrigatória ausente: {SHEET_PROJECTS}")
        return from_rows(projects, sheet_rows(SHEET_PANEL), sheet_rows(SHEET_GED))
    finally:
        workbook.close()
