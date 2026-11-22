"""Interfaces compartilhadas do builder do Relatório G2.

Este módulo é o contrato entre os módulos de construção. Nenhum módulo do builder lê fonte,
modelo ou parâmetro por conta própria: tudo chega por `RenderContext`.

    ReportContext   quem é o relatório (número, mês, datas) e em que modo se constrói
    SourceRef       uma fonte identificada por (drive_id, item_id, version_id), DEC-003/DEC-008
    SourceManifest  as fontes resolvidas para este relatório
    ComponentModel  uma entrada do modelo G2_REPORT_MODEL (classe, fonte, regra, presença)
    RenderContext   o que um módulo recebe para construir sua parte do documento
    ComponentResult o que um módulo devolve
    BuildResult     o que o builder devolve ao final

Alterar este arquivo é mudança de interface: só o orquestrador altera.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

from prog_g2_report.catalog import AutomationClass, Confidence
from prog_g2_report.report_id import ReportRef


class BuildMode(StrEnum):
    PRODUCTION = "PRODUCTION"          # relatório novo, fontes vigentes
    RECONSTRUCTION = "RECONSTRUCTION"  # golden test: fontes no snapshot da emissão (DEC-008)


@dataclass(frozen=True)
class ReportContext:
    """Identidade e datas do relatório. As duas datas são independentes e nunca coincidem."""

    ref: ReportRef
    issue_date: date                       # data da capa (emissão)
    signature_date: date | None = None     # entrada humana (MANUAL_REVIEW); None = pendente
    mode: BuildMode = BuildMode.PRODUCTION

    @property
    def report_number(self) -> int:
        return self.ref.report_number

    @property
    def reference_month(self) -> str:
        if self.ref.reference_month is None:
            raise ValueError("reference_month é obrigatório para construir um relatório")
        return self.ref.reference_month


@dataclass(frozen=True)
class SourceRef:
    """Uma fonte resolvida. Identidade é (drive_id, item_id); o caminho é atributo mutável."""

    key: str                               # ex.: "master_list", "projects", "nc", "environmental"
    name: str
    local_path: Path | None = None         # cópia autorizada em tmp/ ou extrato derivado
    drive_id: str | None = None
    item_id: str | None = None
    version_id: str | None = None          # versão escolhida pelo critério DEC-008
    last_modified: str | None = None
    sha1: str | None = None


@dataclass
class SourceManifest:
    sources: dict[str, SourceRef] = field(default_factory=dict)

    def add(self, source: SourceRef) -> None:
        self.sources[source.key] = source

    def require(self, key: str) -> SourceRef:
        if key not in self.sources:
            raise KeyError(f"fonte obrigatória ausente no manifesto: {key}")
        return self.sources[key]


@dataclass(frozen=True)
class ComponentModel:
    """Uma entrada do modelo. `provenance` aponta a evidência (DEC, catálogo, relatório)."""

    component_id: str
    automation_class: AutomationClass
    confidence: Confidence
    source: str | None = None              # chave do SourceManifest ou "model"/"asset:<id>"
    render_rule: str | None = None
    presence: str = "always"               # "always" ou condição nomeada (ex.: "product_has_rows")
    provenance: tuple[str, ...] = ()


@dataclass
class ComponentResult:
    component_id: str
    status: str = "OK"                     # OK | SKIPPED | PENDING_HUMAN | FAILED
    detail: str = ""
    facts: dict[str, Any] = field(default_factory=dict)  # fatos emitidos, para o QA de conteúdo


@dataclass
class RenderContext:
    """O que um módulo recebe. `document` é um python-docx Document criado do zero."""

    report: ReportContext
    model: dict[str, Any]                  # o YAML do modelo já carregado
    sources: SourceManifest
    document: Any
    assets_dir: Path
    work_dir: Path                         # saída intermediária desta construção (fora do Git)
    data: dict[str, Any] = field(default_factory=dict)   # dados já lidos (ex.: Lista Mestra)
    results: list[ComponentResult] = field(default_factory=list)

    def record(self, result: ComponentResult) -> ComponentResult:
        self.results.append(result)
        return result


@dataclass
class BuildResult:
    report: ReportContext
    docx_path: Path
    pdf_path: Path | None = None
    model_version: str = ""
    components: list[ComponentResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.status in {"OK", "SKIPPED"} for c in self.components)
