"""Leitura da planilha ambiental do Produto 2.4 (`04_Acompanhamento - Licenca Ambiental.xlsx`).

Regras do modelo (`config/g2_report_model.yaml`, `sources.environmental`) e da linhagem
(`docs/discovery/WAVE1_FINDINGS.md` §B):

- abas `Licenças`, `Condicionantes` e `Empresas` (`sources.environmental.sheets`); a aba
  `Dashboard` é legada e não é o painel do relatório;
- todas as linhas, ignorando autofiltro salvo e ocultação (`ignore_saved_filter: true`): os
  painéis só batem incluindo as linhas ocultas (DEC-009 §3);
- cabeçalho localizado pelo conteúdo, não por posição;
- o `Status` das condicionantes é fórmula com `TODAY()`: o gerador **recalcula** com data de
  referência explícita e nunca usa o valor em cache (`sources.environmental.status_recalculation`).

Funções puras sobre tuplas (`parse_workbook_rows`) e um carregador fino de bytes/caminho (`load`).
Nada aqui escreve em disco nem fala com o SharePoint.
"""

from __future__ import annotations

import io
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, BinaryIO

# sources.environmental.sheets
SHEET_LICENSES = "Licenças"
SHEET_CONDITIONS = "Condicionantes"
SHEET_COMPANIES = "Empresas"

# WAVE1 §B: rótulos de status recalculado das condicionantes
STATUS_DONE = "Finalizada"
STATUS_OVERDUE = "Pendente"
STATUS_NEAR_DUE = "Próximo do vencimento"
STATUS_ON_TIME = "No prazo"
CONDITION_STATUSES = (STATUS_DONE, STATUS_ON_TIME, STATUS_OVERDUE, STATUS_NEAR_DUE)
# WAVE1 §B: dias <= 0 -> Pendente; <= 30 -> Próximo do vencimento; senão No prazo
NEAR_DUE_DAYS = 30

# WAVE1 §B / config/data_rules/p24_blocks.yaml P2.4_LIC_LEAD.query: licença pendente
LICENSE_PENDING = "Aguardando a liberação"
LICENSE_VALID = "Vigente"

_HIGHWAY = re.compile(r"^RD[\s\-]?\d+[A-Za-z]?$", re.IGNORECASE)


# --------------------------------------------------------------------------- normalização
def norm(value: Any) -> str:
    """casefold, sem acento, sem º/°, espaços colapsados (mesma ideia do leitor da Lista Mestra)."""
    text = unicodedata.normalize("NFD", str(value if value is not None else ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("°", "").replace("º", "").replace("ª", "")
    return " ".join(text.casefold().split())


def highway_display(value: Any) -> str:
    """p24_blocks.yaml common.highway_display: 'RD-102a' -> 'RD-102A'; 'RD 102a' -> 'RD-102A'."""
    text = " ".join(str(value or "").split()).upper()
    return re.sub(r"^RD[\s]+", "RD-", text)


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    return None


def _clean(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


# --------------------------------------------------------------------------- registros
@dataclass(frozen=True)
class License:
    row: int  # linha do Excel (1-based)
    number: Any  # Nº Licença (vazio = não emitida)
    process: Any
    company: str | None
    phase: str | None  # Fase da licença
    status: str | None  # Status (texto digitado na aba Licenças)
    validity: date | None
    highway: str | None  # pela aba Empresas

    @property
    def issued(self) -> bool:
        return self.number not in (None, "")


@dataclass(frozen=True)
class Condition:
    row: int
    item: Any
    license_number: Any
    delivery_date: Any  # F — Data da entrega (valor cru)
    observations: str | None  # H — Observações
    responsible: str | None  # I — Responsável (empresa)
    next_delivery: Any  # K — Próxima entrega (valor cru)
    cached_status: str | None  # G — valor em cache de TODAY(); só para auditoria
    highway: str | None


@dataclass(frozen=True)
class EnvironmentalWorkbook:
    licenses: tuple[License, ...]
    conditions: tuple[Condition, ...]
    company_to_highway: Mapping[str, str]  # empresa (texto original) -> rodovia
    highways: tuple[str, ...]  # rodovias da aba Empresas, ordem da aba
    warnings: tuple[str, ...] = ()


# --------------------------------------------------------------------------- status
def _classify(days: int) -> str:
    if days <= 0:
        return STATUS_OVERDUE
    if days <= NEAR_DUE_DAYS:
        return STATUS_NEAR_DUE
    return STATUS_ON_TIME


def recompute_status(row: Condition | Mapping[str, Any], reference_date: date) -> str | None:
    """Status da condicionante na data de referência (WAVE1 §B, 0 divergências em v289/v310).

    Observações 'Finalizada' -> Finalizada; 'Atendida' -> usa Próxima entrega (K); senão Data da
    entrega (F). Dias até a data: <= 0 Pendente, <= 30 Próximo do vencimento, senão No prazo.
    Devolve None quando a data necessária não é uma data (indeterminado; o chamador avisa).
    Aceita `Condition` ou um mapeamento com as chaves do cabeçalho da planilha.
    """
    if isinstance(row, Condition):
        obs, delivery, next_delivery = row.observations, row.delivery_date, row.next_delivery
    else:
        obs = row.get("Observações")
        delivery = row.get("Data da entrega")
        next_delivery = row.get("Próxima entrega")
    obs_n = norm(obs)
    if obs_n == norm(STATUS_DONE):
        return STATUS_DONE
    target = _as_date(next_delivery if obs_n == "atendida" else delivery)
    if target is None:
        return None
    return _classify((target - reference_date).days)


# --------------------------------------------------------------------------- cabeçalhos
_LICENSE_HEADERS = {
    "n licenca": "number",
    "n processo": "process",
    "empresa": "company",
    "fase da licenca": "phase",
    "data de validade": "validity",
    "status": "status",
}
_CONDITION_HEADERS = {
    "item": "item",
    "n licenca": "license_number",
    "data da entrega": "delivery_date",
    "status": "cached_status",
    "observacoes": "observations",
    "responsavel": "responsible",
    "proxima entrega": "next_delivery",
}


def _find_header(
    rows: list[tuple], wanted: Mapping[str, str], required: set[str], sheet: str, scan: int = 15
) -> tuple[int, dict[str, int]]:
    """(índice 0-based da linha de cabeçalho, {atributo: coluna}); 1ª ocorrência de cada nome."""
    for index, row in enumerate(rows[:scan]):
        mapping: dict[str, int] = {}
        for col, cell in enumerate(row or ()):
            key = wanted.get(norm(cell))
            if key and key not in mapping:
                mapping[key] = col
        if required <= set(mapping):
            return index, mapping
    raise ValueError(f"cabeçalho da aba {sheet!r} não encontrado ({sorted(required)})")


def _cell(row: tuple, col: int | None) -> Any:
    if col is None or col >= len(row):
        return None
    return _clean(row[col])


def _company_map(
    rows: list[tuple], companies: Iterable[str]
) -> tuple[dict[str, str], tuple[str, ...], list[str]]:
    """Empresa -> rodovia pela aba Empresas, localizando as colunas pelo CONTEÚDO.

    Coluna da empresa = a que contém mais nomes de empresa vistos nas abas Licenças e
    Condicionantes; coluna da rodovia = a mais à esquerda cujos valores, nas mesmas linhas, têm
    todos forma de rodovia ('RD-102a', 'RD 102a'). Evidência: agente B
    leu B (empresa) e G (rodovia); `Empresas!M` repete a rodovia com grafia 'RD 102a' (WAVE1 §B).
    """
    known = {norm(c) for c in companies if c}
    warnings: list[str] = []
    width = max((len(r) for r in rows if r), default=0)
    hits = [sum(1 for r in rows if r and c < len(r) and norm(r[c]) in known) for c in range(width)]
    if not known or not hits or max(hits) == 0:
        raise ValueError(
            "aba Empresas: nenhuma coluna com as empresas das abas Licenças/Condicionantes"
        )
    company_col = hits.index(max(hits))
    company_rows = [r for r in rows if r and company_col < len(r) and norm(r[company_col]) in known]
    road_col = None
    for c in range(width):
        if c == company_col:
            continue
        values = [r[c] for r in company_rows if c < len(r) and r[c] is not None]
        if values and sum(1 for v in values if _HIGHWAY.match(str(v).strip())) == len(company_rows):
            road_col = c
            break
    if road_col is None:
        raise ValueError("aba Empresas: nenhuma coluna de rodovia para todas as empresas")
    mapping: dict[str, str] = {}
    order: list[str] = []
    for r in company_rows:
        company = str(r[company_col]).strip()
        road = highway_display(r[road_col])
        mapping[company] = road
        if road not in order:
            order.append(road)
    missing = known - {norm(c) for c in mapping}
    if missing:
        warnings.append(f"empresas sem rodovia na aba Empresas: {sorted(missing)}")
    return mapping, tuple(order), warnings


def _lookup(mapping: Mapping[str, str], company: Any) -> str | None:
    target = norm(company)
    for name, road in mapping.items():
        if norm(name) == target:
            return road
    return None


def parse_workbook_rows(
    licenses_rows: Iterable[tuple],
    conditions_rows: Iterable[tuple],
    companies_rows: Iterable[tuple],
    first_row_number: int = 1,
) -> EnvironmentalWorkbook:
    """Converte as três abas (tuplas de valores, todas as linhas) em registros tipados."""
    lic_rows = [tuple(r) if r is not None else () for r in licenses_rows]
    cond_rows = [tuple(r) if r is not None else () for r in conditions_rows]
    comp_rows = [tuple(r) if r is not None else () for r in companies_rows]

    lh, lmap = _find_header(
        lic_rows, _LICENSE_HEADERS, {"company", "phase", "status"}, SHEET_LICENSES
    )
    ch, cmap = _find_header(
        cond_rows,
        _CONDITION_HEADERS,
        {"delivery_date", "observations", "responsible", "next_delivery"},
        SHEET_CONDITIONS,
    )
    companies = [_cell(r, lmap.get("company")) for r in lic_rows[lh + 1 :]]
    companies += [_cell(r, cmap.get("responsible")) for r in cond_rows[ch + 1 :]]
    company_to_highway, highways, warnings = _company_map(comp_rows, [c for c in companies if c])

    licenses: list[License] = []
    for offset, row in enumerate(lic_rows[lh + 1 :], start=lh + 1):
        if not row or all(v is None or str(v).strip() == "" for v in row):
            continue
        company = _cell(row, lmap.get("company"))
        licenses.append(
            License(
                row=first_row_number + offset,
                number=_cell(row, lmap.get("number")),
                process=_cell(row, lmap.get("process")),
                company=company,
                phase=_cell(row, lmap.get("phase")),
                status=_cell(row, lmap.get("status")),
                validity=_as_date(_cell(row, lmap.get("validity"))),
                highway=_lookup(company_to_highway, company),
            )
        )
    conditions: list[Condition] = []
    for offset, row in enumerate(cond_rows[ch + 1 :], start=ch + 1):
        if not row or all(v is None or str(v).strip() == "" for v in row):
            continue
        responsible = _cell(row, cmap.get("responsible"))
        conditions.append(
            Condition(
                row=first_row_number + offset,
                item=_cell(row, cmap.get("item")),
                license_number=_cell(row, cmap.get("license_number")),
                delivery_date=_cell(row, cmap.get("delivery_date")),
                observations=_cell(row, cmap.get("observations")),
                responsible=responsible,
                next_delivery=_cell(row, cmap.get("next_delivery")),
                cached_status=_cell(row, cmap.get("cached_status")),
                highway=_lookup(company_to_highway, responsible),
            )
        )
    return EnvironmentalWorkbook(
        licenses=tuple(licenses),
        conditions=tuple(conditions),
        company_to_highway=company_to_highway,
        highways=highways,
        warnings=tuple(warnings),
    )


def _find_sheet(names: Iterable[str], wanted: str) -> str:
    for name in names:
        if norm(name) == norm(wanted):
            return name
    raise KeyError(f"aba ausente na planilha ambiental: {wanted}")


def load(source: bytes | bytearray | BinaryIO | Path | str) -> EnvironmentalWorkbook:
    """Lê a planilha de bytes (conteúdo em memória), arquivo aberto ou caminho local autorizado.

    openpyxl em `read_only` devolve todas as linhas: autofiltro e ocultação são ignorados.
    """
    import openpyxl

    if isinstance(source, bytes | bytearray):
        handle: Any = io.BytesIO(bytes(source))
    elif isinstance(source, str | Path):
        handle = Path(source)
    else:
        handle = source
    workbook = openpyxl.load_workbook(handle, read_only=True, data_only=True)
    try:

        def rows_of(wanted: str) -> list[tuple]:
            return list(
                workbook[_find_sheet(workbook.sheetnames, wanted)].iter_rows(values_only=True)
            )

        return parse_workbook_rows(
            rows_of(SHEET_LICENSES), rows_of(SHEET_CONDITIONS), rows_of(SHEET_COMPANIES)
        )
    finally:
        workbook.close()


# --------------------------------------------------------------------------- agregados
@dataclass(frozen=True)
class LicenseIndex:
    """Painel 'Índices de Acompanhamento Ambiental' (WAVE1 §B), aba Licenças, todas as linhas."""

    total: int
    issued: int  # Nº Licença preenchido
    valid: int  # Status == Vigente (pizza)
    pending: int  # Status == Aguardando a liberação
    by_status: Mapping[str, int]
    by_highway: tuple[tuple[str, int], ...]  # barras: decrescente, empate alfabético
    by_phase: Mapping[str, int]


@dataclass(frozen=True)
class EnvironmentalAggregates:
    reference_date: date
    highways: tuple[str, ...]
    license_index: LicenseIndex
    licenses: tuple[License, ...]
    conditions: tuple[tuple[Condition, str | None], ...]  # (condicionante, status recalculado)
    conditions_by_highway: Mapping[str, Mapping[str, int]]  # painéis 'Status das Condicionantes'
    conditions_by_status: Mapping[str, int]
    warnings: tuple[str, ...] = field(default=())

    def pending_licenses(self, status: str = LICENSE_PENDING) -> tuple[License, ...]:
        return tuple(lic for lic in self.licenses if norm(lic.status) == norm(status))

    def count(self, highway: str, status: str) -> int:
        return int(self.conditions_by_highway.get(highway, {}).get(status, 0))


def aggregate(workbook: EnvironmentalWorkbook, reference_date: date) -> EnvironmentalAggregates:
    """Agregados dos painéis do 2.4 com o status recalculado na data de referência."""
    warnings = list(workbook.warnings)
    lic = workbook.licenses
    by_status = Counter(lic_.status for lic_ in lic)
    by_highway = Counter(lic_.highway for lic_ in lic if lic_.highway)
    index = LicenseIndex(
        total=len(lic),
        issued=sum(1 for lic_ in lic if lic_.issued),
        valid=sum(n for s, n in by_status.items() if norm(s) == norm(LICENSE_VALID)),
        pending=sum(n for s, n in by_status.items() if norm(s) == norm(LICENSE_PENDING)),
        by_status=dict(by_status),
        by_highway=tuple(sorted(by_highway.items(), key=lambda kv: (-kv[1], kv[0]))),
        by_phase=dict(Counter(lic_.phase for lic_ in lic)),
    )
    statuses: list[tuple[Condition, str | None]] = []
    table: dict[str, dict[str, int]] = {
        h: dict.fromkeys(CONDITION_STATUSES, 0) for h in workbook.highways
    }
    for cond in workbook.conditions:
        status = recompute_status(cond, reference_date)
        statuses.append((cond, status))
        if status is None:
            warnings.append(f"Condicionantes linha {cond.row}: status indeterminado (data ausente)")
            continue
        if cond.highway is None:
            warnings.append(
                f"Condicionantes linha {cond.row}: responsável sem rodovia ({cond.responsible!r})"
            )
            continue
        table.setdefault(cond.highway, dict.fromkeys(CONDITION_STATUSES, 0))[status] += 1
    by_cond_status = Counter(s for _, s in statuses if s is not None)
    return EnvironmentalAggregates(
        reference_date=reference_date,
        highways=workbook.highways,
        license_index=index,
        licenses=lic,
        conditions=tuple(statuses),
        conditions_by_highway=table,
        conditions_by_status=dict(by_cond_status),
        warnings=tuple(warnings),
    )
