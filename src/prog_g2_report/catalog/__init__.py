"""Esquemas dos catalogos JSONL da descoberta (data/catalog/*.jsonl).

Cada linha de um catalogo e um destes modelos serializado. Os campos seguem o briefing
do projeto; `evidence` e obrigatoria e `confidence` usa os niveis canonicos.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from prog_g2_report import REPO_ROOT

CATALOG_DIR = REPO_ROOT / "data" / "catalog"


class Confidence(StrEnum):
    CONFIRMED = "CONFIRMED"
    HIGH = "HIGH_CONFIDENCE"
    MEDIUM = "MEDIUM_CONFIDENCE"
    LOW = "LOW_CONFIDENCE"
    UNKNOWN = "UNKNOWN"


class AnomalyClass(StrEnum):
    HISTORICAL_DEFECT = "HISTORICAL_DEFECT"
    COPY_FORWARD_ERROR = "COPY_FORWARD_ERROR"
    TYPO = "TYPO"
    FORMAT_VARIATION = "FORMAT_VARIATION"
    TRUE_MODEL_CHANGE = "TRUE_MODEL_CHANGE"
    INTERNAL_INCONSISTENCY = "INTERNAL_INCONSISTENCY"  # duas partes do mesmo relatorio divergem
    METHOD_ERROR = "METHOD_ERROR"  # erro do metodo de descoberta, nao do relatorio
    UNRESOLVED = "UNRESOLVED"


class ComponentStatus(StrEnum):
    """Situacao de um componente na linha do tempo Maio -> Junho -> Julho -> Agosto/2026.

    Agosto (Relatorio G2 nº 14) e a referencia do padrao vigente, mas "apareceu em agosto"
    nao significa "sempre usar": por isso NEW_IN_AUGUST e MONTH_SPECIFIC sao distintos, e a
    promocao de um para CURRENT_STANDARD exige evidencia, nao so presenca.
    """

    CURRENT_STANDARD = "CURRENT_STANDARD"      # define o padrao atual, confirmado
    STABLE_PATTERN = "STABLE_PATTERN"          # igual nos quatro meses
    NEW_IN_AUGUST = "NEW_IN_AUGUST"            # aparece so em agosto; regra nova ainda nao provada
    EVOLVING_PATTERN = "EVOLVING_PATTERN"      # muda de forma ao longo dos meses
    MONTH_SPECIFIC = "MONTH_SPECIFIC"          # necessidade daquele mes, nao regra
    HISTORICAL_PATTERN = "HISTORICAL_PATTERN"  # existiu antes, nao faz parte do padrao atual
    HISTORICAL_DEFECT = "HISTORICAL_DEFECT"    # erro; nunca vira regra
    UNKNOWN = "UNKNOWN"


class ComponentType(StrEnum):
    STATIC_TEXT = "STATIC_TEXT"
    STATIC_ASSET = "STATIC_ASSET"
    DYNAMIC_TEXT = "DYNAMIC_TEXT"
    STRUCTURED_TABLE = "STRUCTURED_TABLE"
    SOURCE_SCREENSHOT = "SOURCE_SCREENSHOT"
    CONDITIONAL_BLOCK = "CONDITIONAL_BLOCK"
    CALCULATED_FIELD = "CALCULATED_FIELD"
    TOC_FIELD = "TOC_FIELD"
    HEADER = "HEADER"
    FOOTER = "FOOTER"
    COVER = "COVER"
    SIGNATURE_BLOCK = "SIGNATURE_BLOCK"


class AutomationClass(StrEnum):
    """Como cada componente sera produzido pelo builder."""

    CODE = "CODE"                      # deterministico, gerado por funcao
    STATIC_ASSET = "STATIC_ASSET"      # arquivo pronto, reutilizado sem regerar
    TEMPLATE = "TEMPLATE"              # molde com campos
    STRUCTURED_DATA = "STRUCTURED_DATA"  # tabela/lista derivada de fonte estruturada
    RECONSTRUCTED_VISUAL = "RECONSTRUCTED_VISUAL"  # dado + render proprio (DEC-009)
    AI_SYNTHESIS = "AI_SYNTHESIS"      # narrativa que exige interpretacao
    MANUAL_REVIEW = "MANUAL_REVIEW"    # decisao humana a cada mes
    MANUAL_INPUT = "MANUAL_INPUT"      # entrada humana estruturada, declarada em `inputs`
    DISCONTINUED = "DISCONTINUED"      # fora do padrao vigente; registrado para nao voltar
    UNKNOWN = "UNKNOWN"


class GapStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class ReproducibilityEntry(BaseModel):
    """O que ja sabemos reproduzir e o que ainda impede o builder."""

    component_id: str
    section: str | None = None
    current_standard: bool = True
    source_known: bool = False
    source_exact: bool = False          # arquivo + aba + intervalo, nao so "veio da planilha X"
    transformation_known: bool = False
    representation_known: bool = False
    visual_rule_known: bool = False
    content_rule_known: bool = False
    historical_validated: bool = False
    automation_class: AutomationClass = AutomationClass.UNKNOWN
    confidence: Confidence = Confidence.UNKNOWN
    blockers: list[str] = Field(default_factory=list)            # bloqueiam a GERACAO
    validation_blockers: list[str] = Field(default_factory=list)  # bloqueiam so a VALIDACAO
    inputs: list[str] = Field(default_factory=list)               # entradas humanas exigidas
    note: str | None = None

    @property
    def ready(self) -> bool:
        """Reproduzivel hoje: fonte exata, transformacao e regras conhecidas, sem bloqueio."""
        return (
            self.source_exact
            and self.transformation_known
            and (self.visual_rule_known or self.content_rule_known)
            and not self.blockers
        )


class Gap(BaseModel):
    """Lacuna que ainda impede reproduzir o relatorio, ordenavel por impacto."""

    gap_id: str
    component: str
    impact_on_report: str
    what_is_missing: str
    best_next_action: str
    estimated_investigation_cost: str      # BAIXO | MEDIO | ALTO
    blocks_builder: bool
    priority: str                          # P0 | P1 | P2 | P3
    confidence: Confidence = Confidence.UNKNOWN
    status: GapStatus = GapStatus.OPEN
    resolved_by: str | None = None         # DEC ou secao de achados que fechou o gap
    default_if_open: str | None = None     # default tecnico usado enquanto a decisao nao vem
    blocks_validation: bool = False        # impede o golden test, nao a geracao


class Evidence(BaseModel):
    report_id: str | None = None
    page: int | None = None
    source_ref: str | None = Field(default=None, description="drive_id:item_id ou caminho")
    excerpt: str | None = None
    note: str | None = None


class Anomaly(BaseModel):
    report_id: str
    page: int | None = None
    component: str
    observed_value: str
    expected_value: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    classification: AnomalyClass = AnomalyClass.UNRESOLVED
    confidence: Confidence = Confidence.UNKNOWN
    should_learn_as_rule: bool = False  # sempre False: erro historico nao vira regra


class Component(BaseModel):
    component_id: str
    name: str
    section: str | None = None
    subsection: str | None = None
    component_type: ComponentType
    # Presenca por mes de referencia: {"2026-05": True, "2026-06": True, ...}
    present_in: dict[str, bool] = Field(default_factory=dict)
    first_seen: str | None = None
    last_seen: str | None = None
    status: ComponentStatus = ComponentStatus.UNKNOWN
    changed_in: str | None = Field(default=None, description="Mês em que mudou, se mudou")
    change_description: str | None = None
    automation: str | None = Field(
        default=None, description="CODE | ASSET | TEMPLATE | STRUCTURED_DATA | AI | UNDECIDED"
    )
    source_type: str | None = None
    source_file: str | None = None
    source_sheet: str | None = None
    source_range: str | None = None
    source_document: str | None = None
    source_page: int | None = None
    transformation: str | None = None
    representation: str | None = None
    orientation: str | None = None
    dimensions: dict | None = None
    position: str | None = None
    style: dict | None = None
    conditional_rule: str | None = None
    monthly_or_static: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: Confidence = Confidence.UNKNOWN
    notes: str | None = None


class SourceLineage(BaseModel):
    component: str
    report_id: str
    source: str = "UNKNOWN"
    source_ref: str | None = None
    sheet: str | None = None
    range: str | None = None
    filter: str | None = None
    sort: str | None = None
    transformation: str | None = None
    report_position: str | None = None
    width_cm: float | None = None
    alignment: str | None = None
    status: str = "UNKNOWN"  # UNKNOWN | TRACED | PARTIAL
    confidence: Confidence = Confidence.UNKNOWN
    evidence: list[Evidence] = Field(default_factory=list)


class PageRecord(BaseModel):
    report_id: str
    page: int
    orientation: str | None = None
    width_pt: float | None = None
    height_pt: float | None = None
    section: str | None = None
    has_header: bool | None = None
    has_footer: bool | None = None
    page_number_text: str | None = None
    image_count: int | None = None
    table_count: int | None = None
    text_chars: int | None = None
    fonts: list[str] = Field(default_factory=list)
    notes: str | None = None


def append_record(model: BaseModel, filename: str) -> Path:
    path = CATALOG_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(model.model_dump_json(exclude_none=True) + "\n")
    return path


def read_records[T: BaseModel](model_cls: type[T], filename: str) -> list[T]:
    path = CATALOG_DIR / filename
    if not path.exists():
        return []
    return [
        model_cls.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
