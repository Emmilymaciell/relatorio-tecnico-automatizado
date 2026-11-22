"""Geração do Relatório G2 de um mês, de ponta a ponta (Fase 11: `generate_report`).

Camada de linha de comando sobre `assemble.build_report`, usada por
`scripts/15_build_report.py` (opções completas) e `scripts/17_generate_report.py` (comando único
da produção mensal):

    resolver fontes     `build_sources`: cada fonte por arquivo local ou por VERSÃO do
                        SharePoint lida em memória (graph_ro, só GET; nada gravado em disco).
                        `current` = a versão vigente (`sources.versions`; modelo
                        `sources.<fonte>.snapshot.production`: "estado no instante da geração;
                        versão registrada no manifesto"). O manifesto recebe id e lastModified
                        (SourceRef) e, em `source_resolution`, como cada versão foi escolhida.
    Lista Mestra        continua exigindo o ARQUIVO local fornecido pela Emmily: o Controle de
                        Produtos é exportado pelo Excel COM a partir dele (DEC-010; GAP-015).
                        Com versão pedida (`current` ou id) e cliente disponível, a cópia local é
                        CONFERIDA contra a versão lida em memória (mesmas linhas da aba Controle
                        Geral); cópia diferente aborta (`SourceMismatchError`: baixe de novo).
    entradas humanas    `load_inputs` + `report_dates`: `issue_date` e `signature_date` vêm da
                        linha de comando ou do YAML (`config/g2_report_model.yaml: inputs`, as
                        duas `required: true`); `signatory_name` também é obrigatório (sem
                        padrão do relatório anterior). Falta = `InputError` antes do build.
    resumo              `summary_lines`: ok, páginas, fontes, validações, pendências, avisos,
                        pautas de revisão e caminhos.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from prog_g2_report import REPO_ROOT
from prog_g2_report.builder.context import (
    BuildMode,
    BuildResult,
    ReportContext,
    SourceManifest,
    SourceRef,
)
from prog_g2_report.report_id import ReportRef, format_report
from prog_g2_report.sources.versions import CURRENT, is_current

_VERSION = re.compile(r"v(\d+(?:\.\d+)?)", re.IGNORECASE)
# Chaves do modelo (`inputs`) obrigatórias para gerar (required: true, sem padrão).
REQUIRED_INPUTS = ("issue_date", "signature_date", "signatory_name")


class InputError(ValueError):
    """Entrada humana obrigatória ausente ou inválida (o build nem começa)."""


class SourceMismatchError(ValueError):
    """Cópia local diferente da versão do SharePoint que ela deveria representar."""


# --------------------------------------------------------------------------- ambiente
def default_env_file() -> Path | None:
    """`.env` da raiz do repositório; num worktree de agente, o do checkout principal."""
    candidates = [REPO_ROOT / ".env"]
    if REPO_ROOT.parent.name == "worktrees":
        candidates.append(REPO_ROOT.parents[2] / ".env")
    return next((c for c in candidates if c.is_file()), None)


class _LazyClient:
    """Cliente graph_ro criado só se alguma fonte for lida do SharePoint; `close()` no fim."""

    def __init__(self, client: Any = None, env_file: Path | None = None) -> None:
        self._client = client
        self._own = client is None
        self._env_file = env_file

    def get(self) -> Any:
        if self._client is None:
            from prog_g2_report.sources import master_list_remote

            self._client = master_list_remote.default_client(self._env_file or
                                                             default_env_file())
        return self._client

    def close(self) -> None:
        if self._own and self._client is not None:
            self._client.close()
        self._client = None


# --------------------------------------------------------------------------- fontes
@dataclass
class SourceOptions:
    """Como obter cada fonte (`config/g2_report_model.yaml: sources`)."""

    master_list: Path | None = None
    master_list_version: str | None = None
    projects: Path | None = None
    projects_version: str | None = None
    projects_text_version: str | None = None
    projects_panel: Path | None = None
    projects_panel_version: str | None = None
    projects_ged: Path | None = None
    environmental: Path | None = None
    environmental_version: str | None = None
    # conferir a cópia local contra a versão pedida (sempre com `current`)
    verify_local: bool = False

    @classmethod
    def from_namespace(cls, args: Any, **extra: Any) -> SourceOptions:
        names = cls.__dataclass_fields__
        values = {k: getattr(args, k) for k in names if hasattr(args, k)}
        return cls(**{**values, **extra})


def _label(path: Path, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    match = _VERSION.search(Path(path).name)
    return match.group(1) if match else None


def _source_name(model: Mapping[str, Any], key: str, fallback: str) -> str:
    return str(((model.get("sources") or {}).get(key) or {}).get("name") or fallback)


def _resolution(requested: str | None, version_id: str, last_modified: str | None,
                origin: str, **extra: Any) -> dict[str, Any]:
    return {"requested": str(requested) if requested is not None else None,
            "version_id": version_id, "last_modified": last_modified, "origin": origin,
            **extra}


def _master_list(opts: SourceOptions, model: Mapping[str, Any], client: _LazyClient,
                 sources: SourceManifest, resolution: dict[str, Any]) -> None:
    from prog_g2_report.sources import master_list as ml
    from prog_g2_report.sources import master_list_remote as remote

    name = _source_name(model, "master_list", "Lista Mestra")
    requested = opts.master_list_version
    if opts.master_list is not None:
        verify = bool(requested) and (opts.verify_local or is_current(requested))
        if not verify:                       # rótulo informado (ou do nome do arquivo)
            sources.add(SourceRef("master_list", name, opts.master_list,
                                  version_id=_label(opts.master_list, requested)))
            return
        drive_id, item_id = remote.catalog_identity(name)
        version = remote.read_version(drive_id, item_id, str(requested), client=client.get())
        local = tuple(ml.load(Path(opts.master_list)))
        if local != version.rows:
            raise SourceMismatchError(
                f"a cópia local {Path(opts.master_list).name} não é a versão "
                f"{version.version_id} ({version.last_modified}) da Lista Mestra no SharePoint "
                "(linhas diferentes): baixe de novo a versão vigente e confira o Histórico de "
                "versões")
        sources.add(SourceRef("master_list", name, opts.master_list, drive_id=drive_id,
                              item_id=item_id, version_id=version.version_id,
                              last_modified=version.last_modified))
        resolution["master_list"] = _resolution(
            requested, version.version_id, version.last_modified, "local_file",
            local_copy_matches=True, remote_sha1=version.sha1)
        return
    # Versão lida EM MEMÓRIA (nada em disco); o Controle de Produtos fica PENDING porque o
    # Excel COM exige o arquivo (DEC-010, GAP-015).
    drive_id, item_id = remote.catalog_identity(name)
    version = remote.read_version(drive_id, item_id, str(requested), client=client.get())
    sources.add(SourceRef("master_list", name, None, drive_id=drive_id, item_id=item_id,
                          version_id=version.version_id, last_modified=version.last_modified,
                          sha1=version.sha1))
    resolution["master_list"] = _resolution(requested, version.version_id,
                                            version.last_modified, "sharepoint_memory")


def _projects(opts: SourceOptions, model: Mapping[str, Any], client: _LazyClient,
              sources: SourceManifest, resolution: dict[str, Any]) -> None:
    from prog_g2_report.sources import master_list_remote, projects_remote

    name = _source_name(model, "projects", "projetos")
    if opts.projects:
        if is_current(opts.projects_version):
            raise InputError("--projects-version current exige leitura do SharePoint: não "
                             "informe --projects (arquivo local)")
        snapshot = (opts.projects_version or opts.projects_panel_version
                    or _label(opts.projects, None))
        sources.add(SourceRef("projects", name, opts.projects, version_id=snapshot))
        if opts.projects_text_version:      # override explícito, registrado como desvio
            sources.add(SourceRef("projects_text", f"{name} (texto)", opts.projects,
                                  version_id=opts.projects_text_version))
    elif opts.projects_version:
        # GED, Projetos e Painel de Controle dos mesmos bytes (DEC-012); nada em disco.
        drive_id, item_id = master_list_remote.catalog_identity(name)
        wanted = [("projects", name, opts.projects_version)]
        if opts.projects_text_version:      # override explícito, registrado como desvio
            wanted.append(("projects_text", f"{name} (texto)", opts.projects_text_version))
        for key, label, requested in wanted:
            version = projects_remote.read_version(drive_id, item_id, requested,
                                                   client=client.get())
            sources.add(SourceRef(key, label, None, drive_id=drive_id, item_id=item_id,
                                  version_id=version.version_id,
                                  last_modified=version.last_modified, sha1=version.sha1))
            resolution[key] = _resolution(requested, version.version_id,
                                          version.last_modified, "sharepoint_memory")
    if opts.projects_panel:
        sources.add(SourceRef("projects_panel", "Painel de Controle (extrato)",
                              opts.projects_panel, version_id=opts.projects_panel_version))
    if opts.projects_ged:
        sources.add(SourceRef("projects_ged", "GED (planilha de projetos)", opts.projects_ged))


def _environmental(opts: SourceOptions, model: Mapping[str, Any], client: _LazyClient,
                   sources: SourceManifest, resolution: dict[str, Any]) -> None:
    from prog_g2_report.sources import environmental as env
    from prog_g2_report.sources import environmental_remote, master_list_remote

    name = _source_name(model, "environmental", "ambiental")
    requested = opts.environmental_version
    if opts.environmental is not None:
        local = Path(opts.environmental)
        verify = (bool(requested) and (opts.verify_local or is_current(requested))
                  and local.suffix.lower() == ".xlsx")
        if not verify:
            if is_current(requested):
                raise InputError("--environmental-version current com extrato JSON: informe a "
                                 "versão do extrato ou leia do SharePoint sem --environmental")
            sources.add(SourceRef("environmental", name, local,
                                  version_id=_label(local, requested)))
            return
        drive_id, item_id = master_list_remote.catalog_identity(name)
        version = environmental_remote.read_version(drive_id, item_id, str(requested),
                                                    client=client.get())
        if env.load(local) != version.workbook:
            raise SourceMismatchError(
                f"a cópia local {local.name} não é a versão {version.version_id} "
                f"({version.last_modified}) da planilha ambiental no SharePoint: baixe de novo "
                "ou leia a versão em memória (sem --environmental)")
        sources.add(SourceRef("environmental", name, local, drive_id=drive_id, item_id=item_id,
                              version_id=version.version_id,
                              last_modified=version.last_modified))
        resolution["environmental"] = _resolution(
            requested, version.version_id, version.last_modified, "local_file",
            local_copy_matches=True, remote_sha1=version.sha1)
        return
    if not requested:
        return
    # Licenças, Condicionantes e Empresas dos mesmos bytes (DEC-012); nada em disco.
    drive_id, item_id = master_list_remote.catalog_identity(name)
    version = environmental_remote.read_version(drive_id, item_id, str(requested),
                                                client=client.get())
    sources.add(SourceRef("environmental", name, None, drive_id=drive_id, item_id=item_id,
                          version_id=version.version_id, last_modified=version.last_modified,
                          sha1=version.sha1))
    resolution["environmental"] = _resolution(requested, version.version_id,
                                              version.last_modified, "sharepoint_memory")


def build_sources(opts: SourceOptions, model: Mapping[str, Any], *, client: Any = None,
                  env_file: Path | None = None) -> tuple[SourceManifest, dict[str, Any]]:
    """(fontes do relatório, `source_resolution` do manifesto). `client`: leitor graph_ro
    (testes: falso); sem ele, um `GraphReadOnlyClient` com o `.env`, só se precisar."""
    if opts.master_list is None and not opts.master_list_version:
        raise InputError("informe a Lista Mestra (arquivo .xlsx) ou a versão a ler em memória")
    holder = _LazyClient(client, env_file)
    sources = SourceManifest()
    resolution: dict[str, Any] = {}
    try:
        _master_list(opts, model, holder, sources, resolution)
        _projects(opts, model, holder, sources, resolution)
        _environmental(opts, model, holder, sources, resolution)
    finally:
        holder.close()
    return sources, resolution


# --------------------------------------------------------------------------- entradas
def load_inputs(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if data is not None and not isinstance(data, Mapping):
        raise InputError(f"{Path(path).name}: o YAML de entradas deve ser um mapeamento")
    return dict(data or {})


def _date(value: Any, key: str) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise InputError(f"{key}: data inválida {value!r} (use AAAA-MM-DD)") from exc


def report_dates(inputs: Mapping[str, Any], issue_date: Any = None,
                 signature_date: Any = None) -> tuple[date, date]:
    """(emissão, assinatura): linha de comando prevalece; senão o YAML. As duas e o
    `signatory_name` são obrigatórios (`inputs.*.required: true`)."""
    issue = _date(issue_date, "issue_date") or _date(inputs.get("issue_date"), "issue_date")
    signature = (_date(signature_date, "signature_date")
                 or _date(inputs.get("signature_date"), "signature_date"))
    signatory = inputs.get("signatory_name")
    missing = [key for key, value in (("issue_date", issue), ("signature_date", signature),
                                      ("signatory_name", signatory))
               if value is None or (isinstance(value, str) and not value.strip())]
    if missing:
        raise InputError("entrada obrigatória ausente: " + ", ".join(missing)
                         + " (YAML de entradas ou linha de comando)")
    assert issue is not None and signature is not None
    return issue, signature


# --------------------------------------------------------------------------- geração
@dataclass
class Generated:
    result: BuildResult
    manifest_path: Path
    manifest: dict[str, Any] = field(default_factory=dict)


def default_out(report_number: int, reference_month: str) -> Path:
    return REPO_ROOT / "output" / f"{report_number:02d}_{reference_month}"


def run_build(report: ReportContext, sources: SourceManifest, inputs: Mapping[str, Any],
              out: Path, *, resolution: Mapping[str, Any] | None = None, office: bool = True,
              assets_dir: Path | None = None, inputs_path: Path | None = None,
              build: Callable[..., BuildResult] | None = None) -> Generated:
    from prog_g2_report.builder.assemble import build_report

    build = build or build_report
    result = build(report, sources, inputs, out, office=office, assets_dir=assets_dir,
                   inputs_path=inputs_path, source_resolution=resolution)
    manifest_path = Path(result.docx_path).parent / "manifest.json"
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.is_file() else {})
    return Generated(result, manifest_path, manifest)


def generate_report(report_number: int, reference_month: str, *, inputs_path: Path,
                    master_list: Path, out: Path | None = None,
                    master_list_version: str = CURRENT, projects_version: str = CURRENT,
                    environmental_version: str = CURRENT, mode: str = "production",
                    office: bool = True, env_file: Path | None = None,
                    assets_dir: Path | None = None, client: Any = None,
                    build: Callable[..., BuildResult] | None = None) -> Generated:
    """O `generate_report(report_number, reference_month)` da Fase 11.

    Lista Mestra: arquivo local (Excel COM), conferido contra a versão pedida (padrão
    `current`). Projetos e ambiental: versão do SharePoint lida em memória (padrão `current`).
    Datas e signatário: do YAML de entradas (`issue_date`, `signature_date`, `signatory_name`).
    """
    from prog_g2_report.model import load_model

    inputs = load_inputs(inputs_path)
    issue, signature = report_dates(inputs)
    model = load_model()
    opts = SourceOptions(master_list=Path(master_list), master_list_version=master_list_version,
                         projects_version=projects_version,
                         environmental_version=environmental_version, verify_local=True)
    sources, resolution = build_sources(opts, model, client=client, env_file=env_file)
    report = ReportContext(
        ReportRef(report_number, reference_month), issue_date=issue, signature_date=signature,
        mode=BuildMode.RECONSTRUCTION if mode == "reconstruction" else BuildMode.PRODUCTION)
    return run_build(report, sources, inputs, out or default_out(report_number, reference_month),
                     resolution=resolution, office=office, assets_dir=assets_dir,
                     inputs_path=inputs_path, build=build)


# --------------------------------------------------------------------------- resumo
def _pages(manifest: Mapping[str, Any]) -> Any:
    passes = manifest.get("passes") or []
    return passes[-1].get("pdf_pages") if passes else None


def summary_lines(generated: Generated) -> list[str]:
    """Resumo do build para o terminal (sem segredo; sem conteúdo das entradas)."""
    result, manifest = generated.result, generated.manifest
    report = result.report
    out_dir = generated.manifest_path.parent
    lines = [f"{format_report(report.report_number, report.reference_month)} · modelo "
             f"{result.model_version} · ok={result.ok}"]
    pages = _pages(manifest)
    lines.append(f"páginas: {pages if pages is not None else 'pendente (sem Word)'}")
    for source in manifest.get("sources") or []:
        lines.append(f"fonte {source.get('key')}: versão {source.get('version_id')} · "
                     f"{source.get('last_modified') or '-'} · "
                     f"{source.get('snapshot_origin') or '-'}")
    for key, item in (manifest.get("source_resolution") or {}).items():
        lines.append(f"  {key}: pedido {item.get('requested')} -> {item.get('version_id')}")
    for item in manifest.get("validations") or []:
        lines.append(f"validação {item['id']}: {item['outcome']}"
                     + (f" — {item['detail'][:140]}" if item.get("detail")
                        and item["outcome"] not in {"pass"} else ""))
    pending = [c for c in result.components if c.status not in {"OK", "SKIPPED"}]
    lines.append(f"pendências/falhas: {len(pending)}")
    for component in pending:
        lines.append(f"  {component.status:<13} {component.component_id}: "
                     f"{component.detail[:120]}")
    lines.append(f"avisos: {len(result.warnings)}")
    lines += [f"  aviso: {w}" for w in result.warnings]
    for slot, path in (manifest.get("review_briefs") or {}).items():
        lines.append(f"pauta de revisão {slot}: {out_dir / path}")
    lines.append(f"DOCX: {result.docx_path}")
    if manifest.get("docx_final"):
        lines.append(f"DOCX final (campos atualizados): {out_dir / manifest['docx_final']}")
    if result.pdf_path:
        lines.append(f"PDF:  {result.pdf_path}")
    lines.append(f"manifesto: {generated.manifest_path}")
    return lines
