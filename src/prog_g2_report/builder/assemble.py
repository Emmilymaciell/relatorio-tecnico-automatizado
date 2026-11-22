"""Montador do Relatório G2: fontes + modelo -> DOCX novo (de `Document()` vazio) -> PDF.

`build_report(report, sources, inputs, out_dir, office=True)` executa, nesta ordem:

    fundação      `foundation.new_document` (ooxml_base: tema, estilos, numeração, seção 0)
    blocos        `config/g2_content_blocks.yaml` na ordem de `seq` (+ blocos derivados de
                  `text_components.product_slot_blocks`), cada um despachado para quem o emite:

        COVER                          builder.cover (DEC-011)
        TOC                            foundation.add_toc (ooxml_base.toc)
        bloco paisagem                 seção 1 do modelo (`page.sections[1].content =
                                       [landscape_block]`): add_section(1) -> 8 assets do
                                       componente LANDSCAPE_BLOCK (sha1 do manifesto) ->
                                       add_section(2)
        STATIC_ASSET                   componentes do modelo com `asset` (apresentação,
                                       diagrama do 2.2), sha1 de `config/assets_manifest.yaml`
        *_CONTROLE_PRODUTOS            render.product_control (componente CONTROL_OF_PRODUCTS,
                                       `render_params`), EMF do Excel; office=False -> PENDING
        ANEXOS_CONTROLE_CONSOLIDADO    idem com `master_list.select_index` (ANNEX_COMPOSITION,
                                       DEC-012), todos os recortes num parágrafo só
        P2.2_HIGHWAY_BLOCK             render.p22_text.P22_RENDERERS -> builder.emit
        P2.2_EXTERNAL_STATUS (blocos)  render.p22_external com `inputs.p22_external_status`
                                       (MANUAL_INPUT, GAP-009); sem entrada = SKIPPED
        P2.4_*                         render.p24_text.P24_RENDERERS -> builder.emit
        P2.1_SUMMARY_*, MEETINGS       render.p21_text.P21_RENDERERS -> builder.emit
        P2.4_GAMB                     lead + itens do próprio bloco (estrutura lead/items)
        textos                         builder.text_components (Apresentação, cap. 2, títulos,
                                       citações, Encerramento, Anexos)
        demais FIXED/TEMPLATE/VERBATIM builder.blocks.render_block (motor T)

    posição       `positioning` do modelo: vazios entre blocos (`spacers`), alinhamento de
                  assets (`static_assets`), largura do bloco paisagem (`landscape_width`) e
                  âncoras dos visuais (`visual_anchors`)
    visuais       `image_slot` dos BlockText e de `positioning.visual_anchors`, resolvidos por
                  `IMAGE_PROVIDERS` (render.visuals, PNG reconstruído do dado, DEC-009)
    Word          campos/TOC e PDF por `builder.word_pdf.export_pdf`, em passadas: a contagem de
                  páginas (CLOSING_PAGE_COUNT) só existe depois do PDF; regenera-se o DOCX inteiro
                  com o número certo até o PDF confirmar (no máximo `MAX_PASSES`). A última
                  passada salva também `<stem>_final.docx` (campos atualizados, sem prompt).
    validações    `validations` do modelo sobre o DOCX gerado (`builder.validate`); erro
                  bloqueia `ok`, aviso vai para `warnings`.
    pautas        `out_dir/review_brief_<slot>.md` para cada slot AI_SYNTHESIS sem revisão.
    manifesto     `out_dir/manifest.json`: fontes (version_id, sha1), versão do modelo,
                  componentes e status, validações, pautas e DOCX final.

`BuildResult.ok` só é verdadeiro sem nenhum componente PENDING*/FAILED. Status PENDING = falta
ambiente (Excel/Word) ou implementação; PENDING_HUMAN = falta entrada humana (DEC-013).
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from prog_g2_report import REPO_ROOT
from prog_g2_report.builder import foundation as fd
from prog_g2_report.builder.blocks import (
    DELEGATED_CLASSES,
    Block,
    EmptySlot,
    emit_pending,
    load_blocks,
    parse_style,
    render_block,
)
from prog_g2_report.builder.context import (
    BuildResult,
    ComponentResult,
    RenderContext,
    ReportContext,
    SourceManifest,
    SourceRef,
)
from prog_g2_report.builder.cover import build_cover
from prog_g2_report.builder.emit import (
    IMAGE_PROVIDERS,
    PENDING,
    ImageProvider,
    ImageSpec,
    emit_blocktext,
    emit_image_slot,
    emit_marker,
    insert_image,
    ref_key,
)
from prog_g2_report.builder.presence import (
    Condition,
    UntranslatableConditionError,
    evaluate,
    load_data_rule_presences,
    parse_condition,
)
from prog_g2_report.builder.text_components import (
    is_text_block,
    product_slot_blocks,
    render_text_components,
    text_values,
)
from prog_g2_report.builder.values import MissingValueError, input_value
from prog_g2_report.model import load_model
from prog_g2_report.render.blocktext import BlockText, Paragraph, Segment, markup
from prog_g2_report.security import assert_write_allowed
from prog_g2_report.sources import environmental as env
from prog_g2_report.sources import master_list as ml
from prog_g2_report.sources import projects as pj

ASSETS_MANIFEST_PATH = REPO_ROOT / "config" / "assets_manifest.yaml"
RENDER_RULES_PATH = REPO_ROOT / "config" / "g2_render_rules.yaml"
# 1ª passada mede (página da frase de chamada, DEC-010 §3) e dá o nº de páginas; as seguintes
# confirmam a contagem (CLOSING_PAGE_COUNT).
MAX_PASSES = 4
OK_STATUSES = frozenset({"OK", "SKIPPED"})
TWIPS_PER_CM = 1440 / 2.54

ANCHOR_MODES = frozenset({"after", "per_item"})
# A faixa de fotos da Apresentação é o componente PRESENTATION_LOGO (asset
# presentation_coordination_strip), que no modelo não lista o bloco: liga-se aqui.
STATIC_ASSET_BLOCK_FALLBACK = {"APRES_LOGO_GRUPOS": "PRESENTATION_LOGO"}
LANDSCAPE_COMPONENT = "LANDSCAPE_BLOCK"
PRODUCT_CONTROL_COMPONENT = "CONTROL_OF_PRODUCTS"
ANNEX_COMPONENT = "ANNEX_COMPOSITION"
# Componente MANUAL_INPUT de desapropriação/interferências (render.p22_external): blocos e entrada
# vêm do próprio componente no modelo (`blocks`, `input`).
P22_EXTERNAL_COMPONENT = "P2.2_EXTERNAL_STATUS"
_HIGHWAY = re.compile(r"\bRD-\d+[A-Za-z]?\b")


class AssetError(ValueError):
    """Asset ausente do manifesto, do disco, ou com sha1 diferente do registrado."""


# =========================================================================== fontes
def file_sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _versioned(data: Any, version: str | None, what: str) -> Any:
    """Item de um extrato versionado ({'436.0': {...}} ou {'v438.0': {...}})."""
    if not isinstance(data, Mapping) or version is None:
        return data
    for key in (version, f"v{version}", version.removeprefix("v")):
        if key in data:
            return data[key]
    if pj.SHEET_PROJECTS in data or pj.SHEET_PANEL in data:
        return data
    raise KeyError(f"versão {version!r} ausente no extrato de {what}")


def _remote_ref(ref: SourceRef | None) -> bool:
    """Versão do SharePoint lida em memória: sem arquivo local, com (drive, item, versão)."""
    return (ref is not None and ref.local_path is None and bool(ref.drive_id)
            and bool(ref.item_id) and bool(ref.version_id))


def load_projects(sources: SourceManifest, key: str = "projects") -> pj.ProjectsWorkbook | None:
    """`projects` (.xlsx, extrato JSON ou versão do SharePoint em memória; `version_id` escolhe
    a versão); opcionais `projects_panel` (extrato do Painel de Controle) e `projects_ged`
    (.xlsx com a aba GED), alternativa offline registrada como desvio quando o snapshot difere
    (`projects_sheet_origins`). `key` = outra fonte com o mesmo formato (ex.: `projects_text`)."""
    ref = sources.sources.get(key)
    if _remote_ref(ref):
        # sources.projects_remote: GED, Projetos e Painel dos MESMOS bytes (DEC-012)
        from prog_g2_report.sources import projects_remote

        workbook = projects_remote.read_version(str(ref.drive_id), str(ref.item_id),
                                                str(ref.version_id)).workbook
        return _apply_sheet_overrides(sources, workbook)
    if ref is None or ref.local_path is None:
        return None
    path = Path(ref.local_path)
    if path.suffix.lower() == ".json":
        item = _versioned(_json(path), ref.version_id, "projetos")
        if isinstance(item, Mapping) and "rows" in item and pj.SHEET_PROJECTS not in item:
            item = item["rows"]                      # projetos_range.json: só a aba Projetos
        workbook = pj.from_extract(item)
    else:
        workbook = pj.load(path)
    return _apply_sheet_overrides(sources, workbook)


def _apply_sheet_overrides(sources: SourceManifest,
                           workbook: pj.ProjectsWorkbook) -> pj.ProjectsWorkbook:
    """Abas vindas de outra fonte (`projects_panel`, `projects_ged`): alternativa offline."""
    panel_ref = sources.sources.get("projects_panel")
    if panel_ref is not None and panel_ref.local_path is not None:
        panel_item = _versioned(_json(Path(panel_ref.local_path)), panel_ref.version_id, "painel")
        panel_rows = (panel_item.get(pj.SHEET_PANEL) if isinstance(panel_item, Mapping)
                      else panel_item)
        rows, _ = pj._split_extract(panel_rows)
        order, labels = pj.parse_panel(rows)
        workbook = dataclasses.replace(workbook, road_order=order, road_labels=labels)
    ged_ref = sources.sources.get("projects_ged")
    if ged_ref is not None and ged_ref.local_path is not None:
        workbook = dataclasses.replace(workbook, ged=pj.load(Path(ged_ref.local_path)).ged)
    return workbook


PROJECTS_TEXT_KEY = "projects_text"


def load_p22_projects(sources: SourceManifest) -> tuple[
        pj.ProjectsWorkbook | None, pj.ProjectsWorkbook | None, str, list[dict[str, Any]]]:
    """(planilha do TEXTO do 2.2, planilha dos QUADROS, chave da fonte do texto, desvios).

    DEC-012: cada fonte tem UM snapshot por relatório; texto e quadros do 2.2 saem da mesma
    versão (`projects`, `sources.projects.snapshot`). `projects_text` é override explícito
    (ex.: `--projects-text-version`) e vira desvio no manifesto: a divergência histórica do
    nº 14 (texto da v436, quadro da v438) é anomalia (P2.2_PAVIMENTACAO_RD101_STATUS_DEFASADO),
    não regra. A aba Painel de Controle de outra versão também é registrada como desvio.
    """
    from prog_g2_report.builder.provenance import bare_version

    snapshot = load_projects(sources, "projects")
    text, text_key, deviations = snapshot, "projects", []
    base = sources.sources.get("projects")
    base_version = bare_version(base.version_id) if base else None
    override = sources.sources.get(PROJECTS_TEXT_KEY)
    if override is not None and (override.local_path is not None or _remote_ref(override)):
        text, text_key = load_projects(sources, PROJECTS_TEXT_KEY), PROJECTS_TEXT_KEY
        if bare_version(override.version_id) != base_version:
            deviations.append({
                "kind": "SOURCE_VERSION_OVERRIDE", "source": PROJECTS_TEXT_KEY,
                "version_id": override.version_id, "snapshot_version_id": base.version_id
                if base else None, "consumers": "texto do 2.2 (P2.2_HIGHWAY_BLOCK)",
                "rule": "DEC-012: um snapshot por fonte; override explícito, fora do padrão"})
    for sheet, origin in projects_sheet_origins(sources).items():
        if origin["source"] == "projects":
            continue
        version = bare_version(origin["version_id"])
        if version is not None and version == base_version:
            continue
        deviations.append({
            "kind": "SOURCE_VERSION_OVERRIDE" if version is not None
            else "SOURCE_SNAPSHOT_UNVERSIONED",
            "source": origin["source"], "sheet": sheet, "version_id": origin["version_id"],
            "snapshot_version_id": base.version_id if base else None,
            "consumers": SHEET_CONSUMERS.get(sheet, sheet),
            "rule": "DEC-012: um snapshot por fonte (GED, Projetos e Painel da mesma versão)"})
    return text, snapshot, text_key, deviations


# Quem consome cada aba de `sources.projects.sheets` (texto do desvio no manifesto).
SHEET_CONSUMERS = {
    pj.SHEET_PANEL: "aba Painel de Controle (ordem e rótulos das rodovias)",
    pj.SHEET_GED: "aba GED (ordem dos grupos do 2.2)",
    pj.SHEET_PROJECTS: "aba Projetos (texto e quadros do 2.2)",
}
# Fonte que pode substituir uma aba da planilha de `projects` (alternativa offline).
SHEET_OVERRIDE_SOURCES = {pj.SHEET_PANEL: "projects_panel", pj.SHEET_GED: "projects_ged"}


def _base_sheets(ref: SourceRef) -> tuple[str, ...]:
    """Abas que a fonte `projects` fornece sozinha (sem `projects_panel`/`projects_ged`)."""
    every = (pj.SHEET_GED, pj.SHEET_PROJECTS, pj.SHEET_PANEL)
    if _remote_ref(ref):
        from prog_g2_report.sources import projects_remote

        hit = projects_remote.cached(str(ref.drive_id), str(ref.item_id), str(ref.version_id))
        return hit.sheets if hit is not None else every
    if ref.local_path is None:
        return ()
    path = Path(ref.local_path)
    if path.suffix.lower() != ".json":
        return every                       # planilha .xlsx: as três abas do mesmo arquivo
    try:
        item = _versioned(_json(path), ref.version_id, "projetos")
    except (OSError, ValueError, KeyError):
        return (pj.SHEET_PROJECTS,)
    if isinstance(item, Mapping):
        return tuple(s for s in every if s in item) or (pj.SHEET_PROJECTS,)
    return (pj.SHEET_PROJECTS,)            # projetos_range.json: só a aba Projetos


def projects_sheet_origins(sources: SourceManifest) -> dict[str, dict[str, Any]]:
    """{aba: {source, version_id}} da planilha de projetos usada nos quadros do 2.2.

    `sources.projects.sheets` (GED, Projetos, Painel de Controle). Uma aba vinda de outra fonte
    (`projects_panel`, `projects_ged`) que não seja do mesmo snapshot vira desvio (DEC-012).
    """
    base = sources.sources.get("projects")
    if base is None:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for sheet in _base_sheets(base):
        out[sheet] = {"source": "projects", "version_id": base.version_id}
    for sheet, key in SHEET_OVERRIDE_SOURCES.items():
        ref = sources.sources.get(key)
        if ref is not None and ref.local_path is not None:
            out[sheet] = {"source": key, "version_id": ref.version_id}
    order = (pj.SHEET_GED, pj.SHEET_PROJECTS, pj.SHEET_PANEL)
    return {s: out[s] for s in order if s in out}


def environmental_from_snapshot(snap: Mapping[str, Any]) -> env.EnvironmentalWorkbook:
    """Extrato do agente B (`tmp/agent_B/snapshots/v*.json`) -> as três abas em memória.

    Layout da planilha real (sources.environmental): título na linha 1 e cabeçalho na 2
    (Licenças B:P, Condicionantes A:L); Empresas com empresa em B e rodovia em G.
    """
    def cell(value: Any) -> Any:
        if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value)
        return value

    lic = [("Acompanhamento de Licenças",), (None, *snap["licencas_header"])]
    lic += [(None, *(cell(r.get(h)) for h in snap["licencas_header"]))
            for r in snap["licencas_rows"]]
    header = [h[:-2] if h.endswith("_2") else h for h in snap["cond_header"]]
    cond = [("Condicionantes",), tuple(header)]
    cond += [tuple(cell(r.get(h)) for h in snap["cond_header"]) for r in snap["cond_rows"]]
    emp: list[tuple] = [("Cadastro",), (), (None, "Razão social", None, None, None, None, "Obra")]
    emp += [(None, company, "x", None, None, None, road)
            for company, road in snap["company_to_road"].items()]
    return env.parse_workbook_rows(lic, cond, emp)


def load_environmental(sources: SourceManifest) -> env.EnvironmentalWorkbook | None:
    """`environmental`: .xlsx, extrato JSON do agente B ou versão do SharePoint lida em memória
    (`sources.environmental_remote`: Licenças, Condicionantes e Empresas dos MESMOS bytes,
    DEC-012; nada em disco)."""
    ref = sources.sources.get("environmental")
    if _remote_ref(ref):
        from prog_g2_report.sources import environmental_remote

        return environmental_remote.read_version(str(ref.drive_id), str(ref.item_id),
                                                 str(ref.version_id)).workbook
    if ref is None or ref.local_path is None:
        return None
    path = Path(ref.local_path)
    if path.suffix.lower() == ".json":
        return environmental_from_snapshot(_json(path))
    return env.load(path)


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip())


def default_assets_dir() -> Path:
    """assets/discovered/raw (gitignored); num worktree, a do checkout principal."""
    candidates = [REPO_ROOT / "assets" / "discovered" / "raw"]
    if REPO_ROOT.parent.name == "worktrees":
        candidates.append(REPO_ROOT.parents[2] / "assets" / "discovered" / "raw")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


# =========================================================================== modelo
def _component(model: Mapping[str, Any], component_id: str) -> Mapping[str, Any]:
    for comp in model.get("components") or []:
        if comp["component_id"] == component_id:
            return comp
    raise KeyError(f"componente ausente no modelo: {component_id}")


def _components_of_block(model: Mapping[str, Any], block_id: str) -> list[Mapping[str, Any]]:
    return [c for c in model.get("components") or [] if block_id in (c.get("blocks") or [])]


def static_asset_ids(model: Mapping[str, Any], block_id: str) -> list[str]:
    """Assets de um bloco: componente STATIC_ASSET que lista o bloco (`asset`/`assets`)."""
    comps = [c for c in _components_of_block(model, block_id)
             if c.get("automation_class") == "STATIC_ASSET"]
    if not comps and block_id in STATIC_ASSET_BLOCK_FALLBACK:
        comps = [_component(model, STATIC_ASSET_BLOCK_FALLBACK[block_id])]
    out: list[str] = []
    for comp in comps:
        out += list(comp.get("assets") or ([comp["asset"]] if comp.get("asset") else []))
    return out


def _positioning(model: Mapping[str, Any]) -> Mapping[str, Any]:
    return model.get("positioning") or {}


def visual_anchors(model: Mapping[str, Any]) -> dict[str, tuple[str, str]]:
    """`positioning.visual_anchors.anchors`: {bloco: (modo, prefixo do image_slot)}."""
    out: dict[str, tuple[str, str]] = {}
    for anchor in (_positioning(model).get("visual_anchors") or {}).get("anchors") or []:
        mode = str(anchor["mode"])
        if mode not in ANCHOR_MODES:
            raise ValueError(f"positioning.visual_anchors: modo desconhecido {mode!r}")
        out[str(anchor["block"])] = (mode, str(anchor["ref"]))
    return out


def spacer_rules(model: Mapping[str, Any]) -> dict[tuple[str, str], int]:
    """`positioning.spacers.between`: {(bloco anterior, bloco seguinte): nº de vazios}."""
    rules = (_positioning(model).get("spacers") or {}).get("between") or []
    return {(str(r["after"]), str(r["before"])): int(r.get("count", 1)) for r in rules}


def asset_align(model: Mapping[str, Any], asset_id: str) -> str | None:
    """`positioning.static_assets.<asset>.align` (None = alinhamento do estilo)."""
    spec = (_positioning(model).get("static_assets") or {}).get(asset_id) or {}
    return spec.get("align")


def landscape_width_mode(model: Mapping[str, Any]) -> str:
    """`positioning.landscape_width.value`: manifest (GAP-004, padrão) | limit_to_usable_area."""
    spec = _positioning(model).get("landscape_width") or {}
    value = str(spec.get("value", "limit_to_usable_area"))
    if value not in {"manifest", "limit_to_usable_area"}:
        raise ValueError(f"positioning.landscape_width.value desconhecido: {value!r}")
    return value


def keep_with_next_rules(model: Mapping[str, Any]) -> tuple[frozenset[str], bool]:
    """`positioning.keep_with_next`: (blocos cujos parágrafos de texto recebem keepNext,
    frase de chamada do Controle de Produtos recebe keepNext)."""
    spec = _positioning(model).get("keep_with_next") or {}
    return (frozenset(str(b) for b in spec.get("blocks") or ()),
            bool(spec.get("before_product_control", False)))


def keep_with_next_list_titles(model: Mapping[str, Any]) -> tuple[frozenset[str], str]:
    """`positioning.keep_with_next.list_titles`: (blocos, sufixo). Nesses blocos, parágrafo de
    texto terminado no sufixo (título de lista, ex. 'Disciplinas do Viário Secundário:') cujo
    próximo parágrafo não vazio é TEXTO (o 1º item) recebe keepNext; título seguido de imagem
    não (a regra não prende painéis)."""
    spec = (_positioning(model).get("keep_with_next") or {}).get("list_titles") or {}
    suffix = str(spec.get("ends_with") or "")
    blocks = frozenset(str(b) for b in spec.get("blocks") or ())
    if blocks and not suffix:
        raise ValueError("positioning.keep_with_next.list_titles.ends_with vazio")
    return blocks, suffix


def keep_list_titles_with_first_item(elements: Sequence[Any], suffix: str) -> int:
    """Liga keepNext nos títulos de lista de `elements` (ver `keep_with_next_list_titles`) e
    nos vazios entre o título e o 1º item. Devolve quantos títulos foram presos."""
    paragraphs = [el for el in elements if el.tag == qn("w:p")]
    count = 0
    for index, p in enumerate(paragraphs):
        text = _paragraph_text(p).strip()
        if not text.endswith(suffix) or _has_drawing(p):
            continue
        empties: list[Any] = []
        nxt = None
        for q in paragraphs[index + 1:]:
            if _paragraph_text(q).strip() or _has_drawing(q):
                nxt = q
                break
            empties.append(q)
        if nxt is None or _has_drawing(nxt):
            continue
        for el in [p, *empties]:
            set_keep_next(el)
        count += 1
    return count


def product_control_config(model: Mapping[str, Any]) -> dict[str, Any]:
    """`components[CONTROL_OF_PRODUCTS].render_params` no formato de product_control."""
    params = dict(_component(model, PRODUCT_CONTROL_COMPONENT).get("render_params") or {})
    return {"render": params, "width_cm": params.get("width_cm", 17.5)}


def load_assets_manifest(path: Path = ASSETS_MANIFEST_PATH) -> dict[str, Mapping[str, Any]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {a["asset_id"]: a for a in data.get("assets") or []}


def resolve_asset(manifest: Mapping[str, Mapping[str, Any]], asset_id: str,
                  assets_dir: Path) -> tuple[Path, Mapping[str, Any]]:
    """Arquivo do asset em `assets_dir` (pelo nome do manifesto) com o sha1 conferido."""
    if asset_id not in manifest:
        raise AssetError(f"asset fora do manifesto: {asset_id}")
    entry = manifest[asset_id]
    path = Path(assets_dir) / Path(entry["file"]).name
    if not path.is_file():
        raise AssetError(f"asset ausente no disco: {path}")
    actual = file_sha1(path)
    if entry.get("sha1") and actual != entry["sha1"]:
        raise AssetError(f"sha1 divergente para {asset_id}: {actual} != {entry['sha1']}")
    return path, entry


def _usable_width_cm(base: Mapping[str, Any], index: int) -> float:
    spec = fd.section_config(base, index)
    return (spec["pgSz"]["w"] - spec["pgMar"]["left"] - spec["pgMar"]["right"]) / TWIPS_PER_CM


def _image_format(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "emf": "emf"}.get(suffix, suffix)


# =========================================================================== provedores de imagem
def _render_rules(rc: RenderContext) -> dict[str, Any]:
    rules = rc.data.get("render_rules")
    if rules is None:
        rules = yaml.safe_load(RENDER_RULES_PATH.read_text(encoding="utf-8"))
        rc.data["render_rules"] = rules
    return rules


def _visual_width_cm(rules: Mapping[str, Any]) -> float:
    # g2_render_rules.yaml common_placement.width_cm (17,50 cm, 13/13 painéis)
    return float((rules.get("common_placement") or {}).get("width_cm", 17.5))


def _p22_dashboard(rc: RenderContext, ref: str) -> ImageSpec | None:
    """P2.2_ROAD_DASHBOARDS: dados de render.p22_dashboard_data, desenho de render.visuals.

    Lê a planilha do snapshot (`projects_dashboard` = fonte `projects`, DEC-012), nunca o
    override do texto (`load_p22_projects`); sem ela, a de `projects`."""
    from prog_g2_report.render import p22_dashboard_data as dash
    from prog_g2_report.render.visuals.p22_road_dashboard import (
        RoadDashboardData,
        RoadDashboardRow,
        render_road_dashboard,
    )

    projects = rc.data.get("projects_dashboard") or rc.data.get("projects")
    road = ref_key(ref)
    if projects is None or road is None:
        return None
    reference = rc.data["p22_reference_date"]
    p22_rules = rc.data["p22_rules"]
    rows = dash.dashboard_rows(projects, road, p22_rules)

    def revision(row: pj.ProjectRow) -> int | None:
        if row.received_date is None or row.revision is None:
            return None
        try:
            return int(row.revision)
        except (TypeError, ValueError):
            return None

    data = RoadDashboardData(
        road=pj.normalize_road(road),
        donut_counts=dash.donut_counts(rows, reference, p22_rules),
        rows=[RoadDashboardRow(
            discipline=r.discipline, forecast=r.forecast_date, delivery=r.received_date,
            revision=revision(r), level1=dash.sentence_case(r.accepted_raw),
            level2=dash.sentence_case(r.evaluation_raw), revision_delivery=r.revision_delivery,
        ) for r in rows],
        updated_at=reference,
        groups=tuple(sorted({r.group for r in rows})),
    )
    rules = _render_rules(rc)
    png = render_road_dashboard(data, rules)
    return ImageSpec(png, _visual_width_cm(rules), "png", f"p22_dashboard_{data.road}.png")


def _p24_index(rc: RenderContext, ref: str) -> ImageSpec | None:
    """P2.4_ENV_INDICES_PANEL a partir dos agregados (sources.environmental.aggregate)."""
    from prog_g2_report.render.visuals.p24_environmental import (
        EnvironmentalIndexData,
        LicenseRow,
        render_environmental_index,
    )

    agg: env.EnvironmentalAggregates | None = rc.data.get("environmental")
    if agg is None:
        return None
    idx = agg.license_index
    by_road = dict(idx.by_highway)
    rows = sorted(
        (LicenseRow(road=lic.highway or "", company=lic.company or "",
                    process="" if lic.process is None else str(lic.process),
                    license="" if not lic.issued else str(lic.number), phase=lic.phase or "",
                    valid_until=lic.validity, status=lic.status or "")
         for lic in agg.licenses),
        key=lambda r: (r.road, r.process),
    )
    data = EnvironmentalIndexData(
        updated_at=agg.reference_date, total=idx.total, issued=idx.issued, pending=idx.pending,
        # charts.pie.slice_order [Pendente, Vigente]: Pendente = total - Vigente
        status_counts={"Pendente": idx.total - idx.valid, "Vigente": idx.valid},
        by_road=by_road, by_phase=dict(idx.by_phase), rows=rows, roads=tuple(sorted(by_road)),
    )
    rules = _render_rules(rc)
    png = render_environmental_index(data, rules)
    return ImageSpec(png, _visual_width_cm(rules), "png", "p24_environmental_index.png")


def _p24_conditions(rc: RenderContext, ref: str) -> ImageSpec | None:
    """P2.4_CONDITIONS_PANELS: um painel por rodovia (`ref` = 'P2.4_CONDITIONS_PANEL:<rodovia>')."""
    from prog_g2_report.render.visuals.p24_environmental import (
        ConditionsStatusData,
        render_conditions_status,
    )

    agg: env.EnvironmentalAggregates | None = rc.data.get("environmental")
    road = ref_key(ref)
    if agg is None or road is None:
        return None
    key = next((h for h in agg.conditions_by_highway if h.casefold() == road.casefold()), None)
    if key is None:
        return None
    totals = {h: sum(c.values()) for h, c in agg.conditions_by_highway.items()}
    data = ConditionsStatusData(
        road=key, updated_at=agg.reference_date,
        finalized=agg.count(key, env.STATUS_DONE), on_time=agg.count(key, env.STATUS_ON_TIME),
        pending=agg.count(key, env.STATUS_OVERDUE), near_due=agg.count(key, env.STATUS_NEAR_DUE),
        road_totals=totals, roads=tuple(sorted(totals)),
    )
    rules = _render_rules(rc)
    png = render_conditions_status(data, rules)
    return ImageSpec(png, _visual_width_cm(rules), "png", f"p24_conditions_{road}.png")


def default_image_providers() -> dict[str, ImageProvider]:
    """Provedores embutidos (se `render.visuals` importa) + registrados em emit.IMAGE_PROVIDERS."""
    providers: dict[str, ImageProvider] = {}
    try:
        import prog_g2_report.render.visuals  # noqa: F401
    except ImportError:
        pass
    else:
        from prog_g2_report.render.p22_text import DASHBOARD_REF

        providers.update({
            DASHBOARD_REF: _p22_dashboard,
            "P2.4_ENV_INDICES_PANEL": _p24_index,
            "P2.4_CONDITIONS_PANEL": _p24_conditions,
        })
    providers.update(IMAGE_PROVIDERS)
    return providers


# =========================================================================== Excel (cache)
class CachingEmfRenderer:
    """Abre o renderizador só quando preciso, memoriza os EMFs e mantém a instância viva entre
    as passadas; `close()` (no `finally` do `build_report`) é o único que a encerra.

    A 2ª passada USA o Excel quando os recortes mudam (DEC-010 §3, `first_slice_fill`: o 1º
    recorte passa a caber no espaço livre medido no PDF da 1ª passada); só recortes idênticos
    saem do cache. Entre as passadas o Word exporta o PDF e a conexão COM pode cair: o
    `ExcelEmfRenderer` reabre pasta/Excel sozinho; se ainda assim a chamada falhar por
    desconexão, a instância é descartada (fechada) e uma nova é criada pela `factory`, uma vez.
    """

    def __init__(self, factory: Callable[[], Any]) -> None:
        self._factory = factory
        self._inner: Any = None
        self._cache: dict[str, Any] = {}
        self.instances = 0

    def _get(self) -> Any:
        if self._inner is None:
            self._inner = self._factory()
            self.instances += 1
        return self._inner

    def _invoke(self, name: str, *args: Any, **kwargs: Any) -> Any:
        from prog_g2_report.office.excel_emf import is_disconnected

        try:
            return getattr(self._get(), name)(*args, **kwargs)
        except Exception as exc:
            if not is_disconnected(exc):
                raise
        self.close()                         # instância morta: fecha (Quit garantido) e recria
        return getattr(self._get(), name)(*args, **kwargs)

    def _call(self, name: str, args: tuple, kwargs: dict) -> Any:
        key = repr((name, args, sorted(kwargs.items())))
        if key not in self._cache:
            self._cache[key] = self._invoke(name, *args, **kwargs)
        return self._cache[key]

    def measure(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("measure", args, kwargs)

    def measure_row_heights(self, xlsx_path: Any, sheet: str, rows: Sequence[int],
                            **kwargs: Any) -> list[float] | None:
        """Alturas AutoFit por linha (DEC-010 §4): medidas na 1ª passada e memorizadas; as
        passadas seguintes reusam. Renderizador sem o método -> None (estimador offline)."""
        if not hasattr(self._get(), "measure_row_heights"):
            return None
        return self._call("measure_row_heights", (str(xlsx_path), sheet, tuple(rows)), kwargs)

    def render_slices(self, xlsx_path: Any, sheet: str, rows: Sequence[int],
                      slices: Sequence[range], **kwargs: Any) -> list[bytes]:
        args = (str(xlsx_path), sheet, tuple(rows), tuple((s.start, s.stop) for s in slices))
        key = repr(("render", args, sorted(kwargs.items())))
        if key not in self._cache:
            self._cache[key] = self._invoke("render_slices", xlsx_path, sheet, list(rows),
                                            list(slices), **kwargs)
        return self._cache[key]

    def close(self) -> None:
        if self._inner is not None:
            with contextlib.suppress(Exception):
                self._inner.close()
            self._inner = None


def excel_renderer_factory() -> Any:
    from prog_g2_report.office.excel_emf import ExcelEmfRenderer

    renderer = ExcelEmfRenderer()
    renderer.__enter__()
    return renderer


# =========================================================================== composição
@dataclasses.dataclass
class _Env:
    """O que não muda entre passadas."""

    report: ReportContext
    sources: SourceManifest
    inputs: Mapping[str, Any]
    model: dict[str, Any]
    base: dict[str, Any]
    plan: list[Block]
    base_blocks: list[Block]
    assets_dir: Path
    assets_manifest: dict[str, Mapping[str, Any]]
    work_dir: Path
    data: dict[str, Any]
    office: bool
    renderer: CachingEmfRenderer | None
    providers: dict[str, ImageProvider]
    fallbacks: dict[str, str]
    p21: Mapping[str, Callable[..., Any]] | None
    p21_rules: Any
    p22: Mapping[str, Callable[..., Any]]
    p24: Mapping[str, Callable[..., Any]]
    p24_inputs: Any
    warnings: list[str]
    anchors: dict[str, tuple[str, str]] = dataclasses.field(default_factory=dict)
    spacers: dict[tuple[str, str], int] = dataclasses.field(default_factory=dict)
    keep_next_blocks: frozenset[str] = frozenset()
    keep_next_before_control: bool = False
    keep_next_title_blocks: frozenset[str] = frozenset()
    keep_next_title_suffix: str = ""
    # DEC-010 §3: {bloco do Controle de Produtos: (espaço livre abaixo da frase, bloco da
    # frase)} em cm, medidos no PDF da 1ª passada; vazio na 1ª passada (medição).
    first_slice: dict[str, tuple[float, float]] = dataclasses.field(default_factory=dict)
    # DEC-013: pauta de revisão (`ReviewBrief`) de cada slot AI_SYNTHESIS em PENDING_HUMAN,
    # gravada em `out_dir/review_brief_<slot>.md` ao fim do build.
    briefs: dict[str, Any] = dataclasses.field(default_factory=dict)


def _presence(rc: RenderContext, block: Block, fallbacks: dict[str, str]) -> bool:
    """Presença do bloco. Condição que não se traduz levanta `UntranslatableConditionError`
    (nunca 'presente por padrão'); o chamador emite o bloco como pendência visível."""
    condition = parse_condition(block.presence, block.block_id, block.product, fallbacks)
    return evaluate(condition, rc)


def _untranslated(rc: RenderContext, block: Block, exc: Exception) -> ComponentResult:
    return emit_pending(rc, block, f"presença não traduzida: {exc}", status=PENDING)


def _skip(rc: RenderContext, block: Block, why: str) -> ComponentResult:
    return rc.record(ComponentResult(block.block_id, "SKIPPED", detail=why))


def _emit_static_assets(rc: RenderContext, e: _Env, block: Block, asset_ids: list[str], *,
                        section: int, align: str | None,
                        limit_width: bool = True) -> ComponentResult:
    """Assets estáticos (um parágrafo por imagem) na largura do manifesto. `limit_width`: limita
    à área útil da seção (padrão; o bloco paisagem segue `positioning.landscape_width`).
    Alinhamento: `align` do chamador ou `positioning.static_assets.<asset>.align`."""
    usable = _usable_width_cm(e.base, section)
    facts: dict[str, Any] = {"assets": []}
    failures: list[str] = []
    for asset_id in asset_ids:
        try:
            path, entry = resolve_asset(e.assets_manifest, asset_id, e.assets_dir)
        except AssetError as exc:
            failures.append(str(exc))
            emit_marker(rc, asset_id)
            continue
        width = float(entry.get("width_cm") or usable)
        if width > usable:
            if limit_width:
                facts.setdefault("width_limited", []).append(asset_id)
                width = usable
            else:
                facts.setdefault("exceeds_usable_area", []).append(asset_id)
        image = ImageSpec(path.read_bytes(), round(width, 3), _image_format(path), path.name,
                          align or asset_align(e.model, asset_id))
        insert_image(rc, image)
        facts["assets"].append({"asset_id": asset_id, "sha1": image.sha1,
                                "width_cm": image.width_cm})
    status = "FAILED" if failures else "OK"
    return rc.record(ComponentResult(block.block_id, status, detail="; ".join(failures),
                                     facts=facts))


def _emit_landscape(rc: RenderContext, e: _Env, block: Block) -> list[ComponentResult]:
    """Seção 1 (paisagem): model.page.sections[1].content = [landscape_block]."""
    fd.add_section(rc.document, 1, e.base)
    assets = list(_component(e.model, LANDSCAPE_COMPONENT).get("assets") or [])
    result = _emit_static_assets(rc, e, block, assets, section=1, align="center",
                                 limit_width=landscape_width_mode(e.model) != "manifest")
    fd.add_section(rc.document, 2, e.base)
    sections = rc.record(ComponentResult("SECTION_SKELETON", "OK",
                                         detail="3 seções: retrato, paisagem, retrato",
                                         facts={"sections": len(rc.document.sections)}))
    return [result, sections]


def _control_paragraph(rc: RenderContext, spacing_pt: float) -> Any:
    # CONTROL_OF_PRODUCTS.render_params.paragraph_spacing_pt: espaçamento simples, 0 antes/depois
    paragraph = rc.document.add_paragraph()
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(spacing_pt)
    fmt.space_after = Pt(spacing_pt)
    fmt.line_spacing = 1.0
    return paragraph


def _paragraph_text(p: Any) -> str:
    return "".join(t.text or "" for t in p.iter(qn("w:t")))


def _has_drawing(p: Any) -> bool:
    return any(True for _ in p.iter(qn("w:drawing")))


def set_keep_next(p: Any) -> None:
    """w:keepNext no parágrafo (ordem do pPr pelo python-docx)."""
    from docx.text.paragraph import Paragraph as DocxParagraph

    DocxParagraph(p, None).paragraph_format.keep_with_next = True


def lead_paragraphs(body: Any) -> tuple[Any | None, list[Any], int]:
    """Frase imediatamente antes do fim do corpo: (parágrafo com texto, vazios depois dele,
    quantas vezes o mesmo texto aparece antes no corpo)."""
    from prog_g2_report.render.pdf_layout import normalize_for_match

    paragraphs = [el for el in body if el.tag == qn("w:p")]
    empties: list[Any] = []
    for index in range(len(paragraphs) - 1, -1, -1):
        p = paragraphs[index]
        text = _paragraph_text(p)
        if text.strip():
            norm = normalize_for_match(text)
            ordinal = sum(1 for q in paragraphs[:index]
                          if normalize_for_match(_paragraph_text(q)) == norm)
            return p, empties, ordinal
        if _has_drawing(p):
            break
        empties.append(p)
    return None, [], 0


def _body_band_cm(e: _Env, section: int) -> tuple[float, float]:
    """Topo e base do corpo da seção (ooxml_base.page.sections[i].pgSz/pgMar), em cm."""
    spec = fd.section_config(e.base, section)
    return (spec["pgMar"]["top"] / TWIPS_PER_CM,
            (spec["pgSz"]["h"] - spec["pgMar"]["bottom"]) / TWIPS_PER_CM)


def _emit_product_control(rc: RenderContext, e: _Env, block: Block) -> ComponentResult:
    from prog_g2_report.render.product_control import build_product_control

    annex = block.block_id == "ANEXOS_CONTROLE_CONSOLIDADO"
    lead, lead_empties, lead_ordinal = (None, [], 0) if annex else \
        lead_paragraphs(rc.document.element.body)
    all_rows = e.data["master_list_rows"]
    number = rc.report.report_number
    if annex:
        rows = ml.select_index(all_rows, number)            # ANNEX_COMPOSITION, DEC-012
    else:
        try:
            present = _presence(rc, block, e.fallbacks)
        except UntranslatableConditionError as exc:
            return _untranslated(rc, block, exc)
        if not present:
            return _skip(rc, block, f"presença falsa: {block.presence}")
        rows = ml.select(all_rows, number, block.product)    # CONTROL_OF_PRODUCTS, DEC-006
    if not rows:
        return _skip(rc, block, "bloco sem linhas")
    if not e.office or e.renderer is None:
        marker = emit_marker(rc, block.block_id)
        return rc.record(ComponentResult(block.block_id, PENDING,
                                         detail="Controle de Produtos exige Excel (office=False)",
                                         facts={"rows": len(rows), "marker": marker,
                                                "documents": [r.document for r in rows]}))
    master = e.sources.require("master_list")
    if not master.local_path:
        # DEC-010: o EMF é exportado pelo Excel COM a partir do ARQUIVO da Lista Mestra. Fonte só
        # em memória (--master-list-version) não basta; persistir a versão exige autorização
        # (GAP-015). Não se contorna gravando arquivo.
        marker = emit_marker(rc, block.block_id)
        return rc.record(ComponentResult(
            block.block_id, PENDING,
            detail=(f"Controle de Produtos exige o arquivo .xlsx da Lista Mestra (Excel COM, "
                    f"DEC-010); versão {master.version_id} lida só em memória (GAP-015)"),
            facts={"rows": len(rows), "marker": marker,
                   "documents": [r.document for r in rows]}))
    cfg = product_control_config(e.model)
    spacing = float(cfg["render"].get("paragraph_spacing_pt", 0))
    xlsx = Path(master.local_path)
    if annex:   # ANEXOS_CONTROLE_CONSOLIDADO.note: um parágrafo com todos os desenhos
        shared = _control_paragraph(rc, spacing)

        def factory() -> Any:
            return shared
    else:
        def factory() -> Any:
            return _control_paragraph(rc, spacing)
    free, lead_block = e.first_slice.get(block.block_id, (None, 0.0))
    try:
        result = build_product_control(factory, rows, xlsx, cfg, e.renderer,
                                       component_id=block.block_id,
                                       first_page_free_cm=free, lead_block_cm=lead_block)
    except Exception as exc:
        marker = emit_marker(rc, block.block_id)
        return rc.record(ComponentResult(block.block_id, "FAILED",
                                         detail=f"{type(exc).__name__}: {exc}",
                                         facts={"marker": marker}))
    if lead is not None:
        top, bottom = _body_band_cm(e, len(rc.document.sections) - 1)
        result.facts["lead"] = {"text": _paragraph_text(lead), "ordinal": lead_ordinal,
                                "body_top_cm": round(top, 3), "body_bottom_cm": round(bottom, 3)}
        # positioning.keep_with_next.before_product_control: a frase vai com o 1º recorte
        if e.keep_next_before_control and "first_slice" in result.facts:
            for p in [lead, *lead_empties]:
                set_keep_next(p)
            result.facts["lead"]["keep_with_next"] = True
    return rc.record(result)


def _with_anchor_slots(blocktext: Any, anchor: tuple[str, str] | None,
                       highways: Sequence[str]) -> tuple[Any, list[str]]:
    """Insere os image_slot de `positioning.visual_anchors`; devolve (blocktext, refs que ficam
    para depois do bloco)."""
    if anchor is None:
        return blocktext, []
    mode, prefix = anchor
    if mode == "after":
        return blocktext, [prefix]
    paragraphs = list(getattr(blocktext, "paragraphs", ()) or ())
    out: list[Paragraph] = []
    placed: list[str] = []
    for paragraph in paragraphs:
        out.append(paragraph)
        match = _HIGHWAY.match(paragraph.text.strip())
        if match and getattr(paragraph, "kind", "text") != "image_slot":
            road = match.group(0).upper()
            out.append(Paragraph((Segment(""),), kind="image_slot", ref=f"{prefix}:{road}"))
            placed.append(road.casefold())
    rest = [f"{prefix}:{h.upper()}" for h in highways if h.casefold() not in placed]
    if paragraphs and isinstance(blocktext, BlockText):
        blocktext = dataclasses.replace(blocktext, paragraphs=out)
    return blocktext, rest


def _emit_renderer_block(rc: RenderContext, e: _Env, block: Block, blocktext: Any,
                         component_id: str | None = None) -> list[ComponentResult]:
    highways = list(getattr(e.data.get("environmental"), "highways", ()) or ())
    brief = getattr(blocktext, "review_brief", None)
    if brief is not None and getattr(blocktext, "status", None) == "PENDING_HUMAN":
        e.briefs[str(brief.slot_id)] = brief          # DEC-013: pauta do slot sem revisão
    blocktext, trailing = _with_anchor_slots(blocktext, e.anchors.get(block.block_id), highways)
    out = [emit_blocktext(rc, block, blocktext, providers=e.providers,
                          component_id=component_id)]
    out += [emit_image_slot(rc, ref, e.providers) for ref in trailing]
    return out


def contract_item_texts(model: Mapping[str, Any], items: Mapping[str, Any],
                        where: str) -> list[str]:
    """Itens `items.template` sobre `contract.highways` (P2.4_GAMB): um por rodovia, na ordem
    `items.order` (ref de contract.highway_orders); `{letter}` = a, b, c… na ordem emitida;
    `{highway}` = código; demais campos = atributos da rodovia no contrato (ex.: gamb_process)."""
    highways = {h["code"]: h for h in (model.get("contract") or {}).get("highways") or []}
    order = _follow_ref(items["order"]) if items.get("order") else list(highways)
    if not isinstance(order, list) or sorted(order) != sorted(highways):
        raise MissingValueError("order", f"{where}: ordem não é permutação de contract.highways")
    out = []
    for n, code in enumerate(order):
        values = {**highways[code], "highway": code, "letter": chr(ord("a") + n)}
        try:
            out.append(str(items["template"]).format(**values))
        except KeyError as exc:
            raise MissingValueError(str(exc.args[0]), f"{where} ({code})") from exc
    return out


def _emit_lead_items(rc: RenderContext, e: _Env, block: Block) -> ComponentResult:
    """Bloco FIXED_TEXT com `lead` + `items` (P2.4_GAMB): lead em parágrafo próprio e itens na
    lista do `items.style`; 'rodovia em negrito' no estilo dos itens = negrito na rodovia."""
    raw = block.raw
    lead = raw.get("lead") or {}
    lead_text = next((lead[k] for k in ("text_standardized", "text", "text_historical")
                      if lead.get(k)), None)
    items = raw.get("items") or {}
    style = parse_style(items.get("style"))
    bold_highway = "rodovia em negrito" in str(items.get("style") or "")
    paragraphs: list[Paragraph] = []
    if lead_text:
        paragraphs.append(Paragraph((Segment(str(lead_text)),),
                                    style=lead.get("style") or "Normal"))
    item_segments: list[tuple[Segment, ...]] = []
    for text in items.get("texts") or []:
        match = _HIGHWAY.search(text) if bold_highway else None
        if match:
            item_segments.append(tuple(s for s in (Segment(text[:match.start()]),
                                                   Segment(match.group(0), bold=True),
                                                   Segment(text[match.end():])) if s.text))
        else:
            item_segments.append((Segment(text),))
    if not items.get("texts") and items.get("template"):
        item_segments = [markup(t) for t in contract_item_texts(e.model, items, block.block_id)]
    for segs in item_segments:
        paragraphs.append(Paragraph(segs, style=style.style_id or "Normal",
                                    numbering=f"numId_{style.list_key}" if style.list_key else None,
                                    level=style.ilvl if style.list_key else None,
                                    list_key=block.block_id))
    blocktext = BlockText(block.block_id, paragraphs, {"class": block.cls,
                                                       "rule": "content_blocks lead/items"})
    return emit_blocktext(rc, block, blocktext, providers=e.providers)


def _p22_external_blocktext(e: _Env, block: Block) -> BlockText:
    """P2.2_EXTERNAL_STATUS (MANUAL_INPUT): `inputs.p22_external_status` no layout do bloco,
    rodovias em ORDER_P22 (a mesma ordem dos blocos P2.2_HIGHWAY_BLOCK). Os campos derivados
    (`schema.derived`: Análise Programa) saem da MESMA planilha e data do texto do 2.2
    (`projects`, `p22_reference_date`): o bloco não pode contradizer o P2.2_HIGHWAY_BLOCK."""
    from prog_g2_report.render.p22_external import render_external_block
    from prog_g2_report.render.p22_text import road_order

    rules = e.data["p22_rules"]
    projects = e.data.get("projects")
    order = road_order(projects, rules) if projects is not None else list(rules.road_order)
    input_key = str(_component(e.model, P22_EXTERNAL_COMPONENT)["input"])
    spec = (e.model.get("inputs") or {}).get(input_key) or {}
    highways = (e.model.get("contract") or {}).get("highways") or []
    value = input_value(e.inputs, input_key, e.model)
    return render_external_block(block.block_id, block.raw, value,
                                 order, spec.get("schema") or {}, highways,
                                 projects=projects, reference_date=e.data.get("p22_reference_date"),
                                 p22_rules=rules)


def _emit_delegated_without_renderer(rc: RenderContext, e: _Env, block: Block) -> ComponentResult:
    try:
        present = _presence(rc, block, e.fallbacks)
    except UntranslatableConditionError as exc:
        return _untranslated(rc, block, exc)
    if not present:
        return _skip(rc, block, f"presença falsa: {block.presence}")
    return emit_pending(rc, block, f"sem renderizador ({block.cls})",
                        status="PENDING_HUMAN" if block.cls in {"MANUAL_INPUT", "AI_SYNTHESIS"}
                        else PENDING)


_REF_IN_TEXT = re.compile(r"^(config/[\w./-]+?\.ya?ml)#([\w./-]+)$")


def _follow_ref(ref: Any, depth: int = 0) -> Any:
    """'config/<arquivo>.yaml#a/b/c' -> valor; um mapeamento com `ref` é seguido (até 3 saltos)."""
    from prog_g2_report.model import resolve_key

    match = _REF_IN_TEXT.match(str(ref).strip())
    if match is None or depth > 3:
        raise MissingValueError(str(ref), "referência de slot ilegível")
    data = yaml.safe_load((REPO_ROOT / match.group(1)).read_text(encoding="utf-8"))
    value = resolve_key(data, match.group(2))
    if isinstance(value, Mapping) and "ref" in value and not isinstance(value.get("ref"), Mapping):
        return _follow_ref(value["ref"], depth + 1)
    if not isinstance(value, (list, Mapping, str, int, float)):
        raise MissingValueError(str(ref), "referência de slot inexistente")
    return value


def slot_values(rc: RenderContext, block: Block) -> dict[str, str]:
    """Valores dos `slots` declarativos de um bloco TEMPLATE do motor (g2_content_blocks.yaml):

    - `value_if_true`/`value_if_false` + `trigger_rule` -> regra {product, prefix} de data_rules
      (ex.: P2.2_ROTINA_REUNIOES.atas_clause: existe AT no Produto 2.1 do relatório);
    - `source` contract/highways + `order` + `join: join_pt` -> rodovias do contrato na ordem
      citada (ex.: P2.4_RO_INTRO.highways_enum_ro, ORDER_RO).
    Slots de outra forma ficam para `text_values` (ou faltam: MissingValueError no motor)."""
    from prog_g2_report.render.p24_text import join_pt

    out: dict[str, str] = {}
    for name, spec in (block.raw.get("slots") or {}).items():
        if not isinstance(spec, Mapping):
            continue
        if "value_if_true" in spec and spec.get("trigger_rule"):
            trigger = _follow_ref(spec["trigger_rule"])
            if not (isinstance(trigger, Mapping) and trigger.get("product")
                    and trigger.get("prefix")):
                continue
            hit = evaluate(Condition("product_has_prefix",
                                     (str(trigger["product"]), str(trigger["prefix"]))), rc)
            value = str(spec["value_if_true"] if hit else spec.get("value_if_false") or "")
            out[name] = value or EmptySlot()      # vazio declarado (value_if_false: '')
        elif spec.get("join") == "join_pt" and spec.get("order") \
                and "contract/highways" in str(spec.get("source", "")):
            order = _follow_ref(spec["order"])
            contract = [h["code"] for h in (rc.model.get("contract") or {}).get("highways") or []]
            if not isinstance(order, list) or sorted(order) != sorted(contract):
                raise MissingValueError(name, f"{block.block_id}: ordem fora do contrato")
            out[name] = join_pt(order)
    return out


def _emit_engine(rc: RenderContext, e: _Env, block: Block) -> ComponentResult:
    if block.cls in DELEGATED_CLASSES:
        return _emit_delegated_without_renderer(rc, e, block)
    try:
        values = slot_values(rc, block) | text_values(rc)
    except MissingValueError as exc:
        return emit_pending(rc, block, str(exc), status="FAILED")
    try:
        return render_block(rc, block, values, fallbacks=e.fallbacks)
    except MissingValueError as exc:
        return emit_pending(rc, block, str(exc), status="PENDING_HUMAN")
    except UntranslatableConditionError as exc:
        return emit_pending(rc, block, f"presença não traduzida: {exc}", status=PENDING)


def _dispatch(rc: RenderContext, e: _Env, block: Block) -> list[ComponentResult]:
    bid = block.block_id
    if bid == "COVER":
        return [build_cover(rc, e.base)]
    if bid == "TOC":
        fd.add_toc(rc.document, e.base)
        return [rc.record(ComponentResult("TOC", "OK", detail="SDT + campo TOC (Word atualiza)",
                                          facts={"instruction": e.base["toc"]["instruction"]}))]
    if any(c["component_id"] == LANDSCAPE_COMPONENT for c in _components_of_block(e.model, bid)):
        return _emit_landscape(rc, e, block)
    if bid.endswith("_CONTROLE_PRODUTOS") or bid == "ANEXOS_CONTROLE_CONSOLIDADO":
        return [_emit_product_control(rc, e, block)]
    assets = static_asset_ids(e.model, bid)
    if assets:
        # seção corrente = a última criada (as seções nascem em ordem: 0, 1, 2)
        return [_emit_static_assets(rc, e, block, assets,
                                    section=len(rc.document.sections) - 1, align=None)]
    if any(c["component_id"] == P22_EXTERNAL_COMPONENT for c in _components_of_block(e.model, bid)):
        return _emit_renderer_block(rc, e, block, _p22_external_blocktext(e, block))
    if bid in e.p22:
        projects = e.data.get("projects")
        if projects is None:
            return [emit_pending(rc, block, "fonte 'projects' ausente", status=PENDING)]
        out: list[ComponentResult] = []
        # uma instância do bloco por rodovia (P2.2_HIGHWAY_BLOCK.presence 'uma vez por rodovia')
        for blocktext in e.p22[bid](projects, e.data["p22_reference_date"], e.data["p22_rules"]):
            road = blocktext.facts.get("road", "")
            out += _emit_renderer_block(rc, e, block, blocktext, component_id=f"{bid}:{road}")
        return out
    if bid in e.p24:
        return _emit_renderer_block(rc, e, block, e.p24[bid](e.p24_inputs))
    if e.p21 is not None and bid in e.p21 and not is_text_block(bid):
        rows = ml.select(e.data["master_list_rows"], rc.report.report_number)
        blocktext = e.p21[bid](rows, dict(e.inputs), e.p21_rules)
        return _emit_renderer_block(rc, e, block, blocktext)
    if "lead" in block.raw and isinstance(block.raw.get("items"), Mapping):
        return [_emit_lead_items(rc, e, block)]
    if is_text_block(bid):
        return render_text_components(rc, [bid], blocks=e.base_blocks)
    return [_emit_engine(rc, e, block)]


def _insert_spacers(body: Any, index: int, count: int) -> None:
    """`count` parágrafos vazios (estilo Normal) na posição `index` do corpo."""
    anchor = body[index]
    for _ in range(count):
        anchor.addprevious(OxmlElement("w:p"))


def _compose(e: _Env, page_count: int | None) -> RenderContext:
    doc = fd.new_document(e.base)
    data = dict(e.data)
    if page_count is not None:
        data["page_count"] = page_count
    rc = RenderContext(report=e.report, model=e.model, sources=e.sources, document=doc,
                       assets_dir=e.assets_dir, work_dir=e.work_dir, data=data)
    for cid, detail in (("PAGE_GEOMETRY", "ooxml_base.page.sections"),
                        ("HEADER", "ooxml_base.header"), ("FOOTER", "ooxml_base.footer")):
        rc.record(ComponentResult(cid, "OK", detail=detail))
    previous: str | None = None          # último bloco que emitiu algo (não SKIPPED)
    for block in e.plan:
        spacers = e.spacers.get((previous, block.block_id), 0) if previous else 0
        mark = len(rc.results)
        body = rc.document.element.body
        before = len(body)
        # o conteúdo novo entra antes do sectPr final do corpo
        start = before - 1 if before and body[-1].tag == qn("w:sectPr") else before
        try:
            _dispatch(rc, e, block)
        except Exception as exc:  # um bloco quebrado não derruba o documento; o resultado acusa
            emit_pending(rc, block, f"{type(exc).__name__}: {exc}", status="FAILED")
        if len(body) == before:
            continue
        if block.block_id in e.keep_next_blocks:     # positioning.keep_with_next.blocks
            end = len(body) - 1 if body[-1].tag == qn("w:sectPr") else len(body)
            for el in list(body)[start:end]:
                if el.tag == qn("w:p") and _paragraph_text(el).strip() and not _has_drawing(el):
                    set_keep_next(el)
        if block.block_id in e.keep_next_title_blocks:   # keep_with_next.list_titles
            end = len(body) - 1 if body[-1].tag == qn("w:sectPr") else len(body)
            keep_list_titles_with_first_item(list(body)[start:end], e.keep_next_title_suffix)
        if spacers:                      # positioning.spacers: vazios ANTES do bloco emitido
            _insert_spacers(body, start, spacers)
        if any(r.status != "SKIPPED" for r in rc.results[mark:]):
            previous = block.block_id
    if len(doc.sections) != 3:
        rc.record(ComponentResult("SECTION_SKELETON", "FAILED",
                                  detail=f"{len(doc.sections)} seção(ões); o modelo pede 3"))
    return rc


def _page_count_results(rc: RenderContext, office: bool, passes: list[dict[str, Any]]) -> None:
    """CLOSING_PAGE_COUNT; sem Word, o ENC_P1 sai pendente (não falho)."""
    if not office:
        for result in rc.results:
            if result.component_id == "ENC_P1" and result.status == "FAILED" \
                    and "page_count" in result.detail:
                result.status = PENDING
                result.detail = "page_count exige o PDF do Word (office=False)"
        rc.record(ComponentResult("CLOSING_PAGE_COUNT", PENDING,
                                  detail="contagem de páginas exige o Word (office=False)"))
        return
    final = passes[-1] if passes else {}
    ok = bool(final) and final.get("page_count") == final.get("pdf_pages")
    rc.record(ComponentResult(
        "CLOSING_PAGE_COUNT", "OK" if ok else "FAILED",
        detail=(f"{final.get('pdf_pages')} páginas em {len(passes)} passada(s)" if ok
                else f"não convergiu em {len(passes)} passadas"),
        facts={"passes": passes}))


def _validate_annex_count(rc: RenderContext) -> None:
    """V_ANNEX_COUNT: annex_count do ENC_P1 == len(index_rows) == linhas do índice de ANEXOS."""
    index = len(ml.select_index(rc.data["master_list_rows"], rc.report.report_number))
    enc = next((r for r in rc.results if r.component_id == "ENC_P1"), None)
    annex = next((r for r in rc.results if r.component_id == "ANEXOS_CONTROLE_CONSOLIDADO"), None)
    stated = (enc.facts.get("values") or {}).get("annex_count") if enc else None
    rows = annex.facts.get("rows") if annex else None
    problems = []
    if stated is not None and int(stated) != index:
        problems.append(f"ENC_P1 diz {stated}, índice tem {index}")
    if rows is not None and int(rows) != index:
        problems.append(f"ANEXOS tem {rows} linhas, índice tem {index}")
    rc.record(ComponentResult("V_ANNEX_COUNT", "FAILED" if problems else "OK",
                              detail="; ".join(problems) or f"{index} documentos entregues",
                              facts={"index_rows": index}))


def _pdf_pages(pdf: Path) -> int:
    import pymupdf

    with pymupdf.open(str(pdf)) as document:
        return document.page_count


def measure_first_slices(rc: RenderContext, e: _Env, pdf_path: Path
                         ) -> dict[str, tuple[float, float]]:
    """DEC-010 §3: para cada Controle de Produtos emitido (fora os anexos), o espaço livre
    abaixo da frase de chamada e a altura dela, no PDF da passada. A folga
    `render_params.first_slice_gap_cm` sai do espaço livre e entra no bloco da frase."""
    from prog_g2_report.render.pdf_layout import locate_paragraphs

    gap = float(product_control_config(e.model)["render"].get("first_slice_gap_cm", 0.0))
    wanted = [(r.component_id, r.facts["lead"]) for r in rc.results
              if r.status == "OK" and isinstance(r.facts.get("lead"), Mapping)]
    if not wanted or not Path(pdf_path).is_file():
        return {}
    out: dict[str, tuple[float, float]] = {}
    for (block_id, lead) in wanted:
        box = locate_paragraphs(pdf_path, [(lead["text"], int(lead["ordinal"]))],
                                body_top_cm=float(lead["body_top_cm"]),
                                body_bottom_cm=float(lead["body_bottom_cm"]))[0]
        if box is None:
            e.warnings.append(f"{block_id}: frase de chamada não encontrada no PDF; "
                              "1º recorte em página inteira")
            continue
        free = float(lead["body_bottom_cm"]) - box.bottom_cm - gap
        out[block_id] = (max(0.0, free), box.height_cm + gap)
    return out


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))


def _output_file(path: Path | None, out_dir: Path) -> dict[str, Any] | None:
    """Arquivo gerado no manifesto: caminho RELATIVO à pasta de saída (o manifesto viaja com
    ela) e sha1 do conteúdo final."""
    if path is None:
        return None
    path = Path(path)
    try:
        relative = path.resolve().relative_to(Path(out_dir).resolve()).as_posix()
    except ValueError:
        relative = path.name
    return {"path": relative, "sha1": file_sha1(path) if path.is_file() else None}


def write_manifest(path: Path, result: BuildResult, e: _Env, passes: list[dict[str, Any]],
                   deviations: Sequence[Mapping[str, Any]] = (),
                   inputs_path: Path | None = None, *,
                   docx_final: Path | None = None,
                   review_briefs: Mapping[str, Path] | None = None,
                   source_resolution: Mapping[str, Any] | None = None) -> Path:
    """manifest.json: proveniência das fontes (`builder.provenance`), abas da planilha de
    projetos e seu snapshot, arquivo de inputs (caminho e sha1, sem conteúdo), linhagem por
    componente (`components[].source_version`, fichas de `provenance.component_lineage`),
    desvios do snapshot único (DEC-012) e DOCX/PDF relativos à pasta de saída, com sha1.

    `docx_final`: cópia salva pelo Word com campos e sumário atualizados (`word_pdf`);
    `review_briefs`: {slot: pauta de revisão gravada} (DEC-013); `source_resolution`: como
    cada versão foi escolhida (ex.: `current` -> id e lastModified da versão vigente);
    `validations`: resultado de cada validação do modelo (`builder.validate`)."""
    from prog_g2_report.builder.provenance import (
        component_lineage,
        inputs_record,
        source_provenance,
    )
    from prog_g2_report.builder.validate import validation_summary

    provenance = source_provenance(e.sources, e.model)
    if "projects" in provenance:
        provenance["projects"]["sheets"] = projects_sheet_origins(e.sources)
    sources = list(provenance.values())
    inputs_meta = inputs_record(e.inputs, inputs_path)
    used = component_lineage(result.components, e.model, provenance, e.inputs,
                             inputs_meta["sha1"],
                             text_projects_key=e.data.get("projects_text_key", "projects"))
    out_dir = Path(path).parent
    docx = _output_file(result.docx_path, out_dir)
    pdf = _output_file(result.pdf_path, out_dir) if result.pdf_path else None
    final = _output_file(docx_final, out_dir) if docx_final is not None else None
    briefs = {slot: (_output_file(p, out_dir) or {}).get("path")
              for slot, p in (review_briefs or {}).items()}
    meta = e.model.get("model") or {}
    payload = {
        "report": {
            "report_number": e.report.report_number,
            "reference_month": e.report.reference_month,
            "issue_date": e.report.issue_date.isoformat(),
            "signature_date": e.report.signature_date.isoformat()
            if e.report.signature_date else None,
            "mode": str(e.report.mode),
        },
        "model": {"name": meta.get("name"), "version": meta.get("version"),
                  "status": meta.get("status")},
        "ooxml_base_version": (e.base.get("_meta") or {}).get("version"),
        "sources": sources,
        "source_resolution": dict(source_resolution or {}),
        "inputs": inputs_meta,
        "deviations": list(deviations),
        "office": e.office,
        "passes": passes,
        "docx": docx["path"] if docx else None,
        "docx_sha1": docx["sha1"] if docx else None,
        "pdf": pdf["path"] if pdf else None,
        "pdf_sha1": pdf["sha1"] if pdf else None,
        "docx_final": final["path"] if final else None,
        "docx_final_sha1": final["sha1"] if final else None,
        "ok": result.ok,
        "pending": [c.component_id for c in result.components if c.status.startswith("PENDING")],
        "failed": [c.component_id for c in result.components if c.status == "FAILED"],
        "warnings": result.warnings,
        "validations": validation_summary(e.model, result.components),
        "review_briefs": briefs,
        "components": [{"component_id": c.component_id, "status": c.status, "detail": c.detail,
                        "source_version": used[c.component_id],
                        **({"review_brief": briefs[c.component_id]}
                           if c.component_id in briefs else {}),
                        "facts": c.facts} for c in result.components],
    }
    path = assert_write_allowed(path)
    path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return path


REVIEW_BRIEF_PREFIX = "review_brief_"
FINAL_SUFFIX = "_final"


def _accepts_keyword(func: Callable[..., Any], name: str) -> bool:
    import inspect

    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False
    return name in params or any(p.kind is inspect.Parameter.VAR_KEYWORD
                                 for p in params.values())


def control_block_ids(model: Mapping[str, Any]) -> list[str]:
    """Blocos com EMF do Controle de Produtos: `components[CONTROL_OF_PRODUCTS].blocks` + o
    índice consolidado de ANNEX_COMPOSITION."""
    out = [str(b) for b in _component(model, PRODUCT_CONTROL_COMPONENT).get("blocks") or []]
    out += [str(b) for b in _component(model, ANNEX_COMPONENT).get("blocks") or []
            if str(b).endswith("_CONTROLE_CONSOLIDADO")]
    return out


def _run_model_validations(rc: RenderContext, e: _Env, docx_path: Path) -> None:
    """`validations` do modelo sobre o DOCX gerado (builder.validate); avisos vão a `warnings`."""
    from prog_g2_report.builder.blocks import blocks_by_id
    from prog_g2_report.builder.validate import run_validations

    external = [code for _road, code, _month in e.p24_inputs.bm_in_progress_extra]
    results, warnings = run_validations(
        docx_path, rc.report, ml.select(e.data["master_list_rows"], rc.report.report_number),
        external, e.model, blocks_by_id(e.base_blocks), control_block_ids(e.model))
    for result in results:
        rc.record(result)
    e.warnings.extend(warnings)


def _write_review_briefs(rc: RenderContext, e: _Env, out_dir: Path) -> dict[str, Path]:
    """DEC-013: `out_dir/review_brief_<slot>.md` (render.p21_text.write_review_brief) para cada
    slot que terminou PENDING_HUMAN; o componente aponta para a pauta (`facts.review_brief`)."""
    from prog_g2_report.render.p21_text import write_review_brief

    pending = {r.component_id for r in rc.results if r.status == "PENDING_HUMAN"}
    out: dict[str, Path] = {}
    for slot, brief in sorted(e.briefs.items()):
        if slot not in pending:
            continue
        out[slot] = write_review_brief(brief, out_dir, prefix=REVIEW_BRIEF_PREFIX)
        for result in rc.results:
            if result.component_id == slot:
                result.facts["review_brief"] = out[slot].name
    return out


def output_stem(report: ReportContext) -> str:
    return f"relatorio_g2_n{report.report_number:02d}_{report.reference_month}"


def _load_p21() -> tuple[Mapping[str, Callable[..., Any]] | None, Any]:
    try:
        from prog_g2_report.render import p21_text
    except ImportError:
        return None, None
    return p21_text.P21_RENDERERS, p21_text.load_rules()


def _reference_date(inputs: Mapping[str, Any], keys: Sequence[str], fallback: date,
                    warnings: list[str], what: str, model: Mapping[str, Any]) -> date:
    for key in keys:
        value = _as_date(input_value(inputs, key, model))
        if value is not None:
            return value
    warnings.append(f"{what}: sem {' / '.join(keys)} nos inputs; usada a data de emissão")
    return fallback


def build_report(
    report: ReportContext,
    sources: SourceManifest,
    inputs: Mapping[str, Any],
    out_dir: Path,
    *,
    office: bool = True,
    assets_dir: Path | None = None,
    assets_manifest: Path | None = None,
    model: dict[str, Any] | None = None,
    renderer_factory: Callable[[], Any] | None = None,
    pdf_exporter: Callable[..., int] | None = None,
    inputs_path: Path | None = None,
    source_resolution: Mapping[str, Any] | None = None,
) -> BuildResult:
    """Gera `out_dir/<stem>.docx` (e `.pdf` com office=True) e `out_dir/manifest.json`.

    `inputs`: entradas humanas de `model.inputs` (signatory_name, meetings_agenda, ai_review,
    p22_external_status, environmental_reference_date) e `p22_status_reference_date`
    (`p22_highway_block.yaml inputs.status_reference_date`). `renderer_factory`/`pdf_exporter`
    substituem Excel/Word (testes); por padrão ExcelEmfRenderer e word_pdf.export_pdf.
    `inputs_path`: arquivo de onde `inputs` veio; o manifesto registra caminho e sha1 (nunca o
    conteúdo) e as fichas `inputs:<chave>@<sha1>` dos componentes que o consomem.
    `source_resolution`: como as versões das fontes foram escolhidas (vai ao manifesto).

    Com office=True, a última passada do Word salva também `out_dir/<stem>_final.docx` (campos
    e sumário atualizados, sem pedir atualização ao abrir; `word_pdf.export_pdf`). Ao fim,
    `builder.validate` roda as validações do modelo sobre o DOCX; erro bloqueia `ok`. Cada slot
    AI_SYNTHESIS em PENDING_HUMAN grava a pauta `out_dir/review_brief_<slot>.md` (DEC-013).
    """
    from prog_g2_report.render.p22_text import P22_RENDERERS, coerce_rules
    from prog_g2_report.render.p24_text import (
        P24_RENDERERS,
        P24Inputs,
        bm_in_progress_items,
        nc_nature_clause,
    )

    out_dir = assert_write_allowed(Path(out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob(f"{REVIEW_BRIEF_PREFIX}*.md"):   # pauta de um build anterior
        assert_write_allowed(stale)
        stale.unlink()
    work_dir = out_dir / "_work"
    work_dir.mkdir(exist_ok=True)
    model = model or load_model()
    base = fd.load_base_config()
    base_blocks = load_blocks()
    plan = sorted(base_blocks + product_slot_blocks(base_blocks, model),
                  key=lambda b: (b.seq, b.virtual))
    warnings: list[str] = []

    master = sources.require("master_list")
    rows = ml.load_source(master)        # arquivo, ou versão lida em memória (graph_ro)
    projects, projects_dashboard, projects_text_key, deviations = load_p22_projects(sources)
    for deviation in deviations:
        warnings.append(f"desvio de snapshot (DEC-012): {deviation['source']} "
                        f"{deviation['version_id']} != {deviation['snapshot_version_id']}")
    workbook = load_environmental(sources)
    p22_date = _reference_date(inputs, ("p22_status_reference_date",
                                        "environmental_reference_date"),
                               report.issue_date, warnings, "2.2", model)
    env_date = _reference_date(inputs, ("environmental_reference_date",), report.issue_date,
                               warnings, "2.4", model)
    aggregates = env.aggregate(workbook, env_date) if workbook is not None else None
    if projects is None:
        warnings.append("fonte 'projects' ausente: 2.2 pendente")
    if aggregates is None:
        warnings.append("fonte 'environmental' ausente: textos e painéis ambientais do 2.4")
    # P2.4_NC_NATURE: chave da revisão = review_key do componente no modelo
    nc_clause = nc_nature_clause(input_value(inputs, "ai_review", model), model)
    p21, p21_rules = _load_p21()
    data = {
        "master_list_rows": rows,
        "inputs": dict(inputs),
        "ooxml_base": base,
        "projects": projects,
        "projects_dashboard": projects_dashboard,
        "projects_text_key": projects_text_key,
        "environmental": aggregates,
        "p22_reference_date": p22_date,
        "p22_rules": coerce_rules(None),
        "environmental_reference_date": env_date,
    }
    renderer = None
    if office:
        renderer = CachingEmfRenderer(renderer_factory or excel_renderer_factory)
    e = _Env(
        report=report, sources=sources, inputs=inputs, model=model, base=base, plan=plan,
        base_blocks=base_blocks, assets_dir=Path(assets_dir or default_assets_dir()),
        assets_manifest=load_assets_manifest(assets_manifest or ASSETS_MANIFEST_PATH),
        work_dir=work_dir, data=data, office=office, renderer=renderer,
        providers=default_image_providers(), fallbacks=load_data_rule_presences(),
        p21=p21, p21_rules=p21_rules, p22=P22_RENDERERS, p24=P24_RENDERERS,
        p24_inputs=P24Inputs(body_rows=ml.select(rows, report.report_number),
                             reference_month=report.reference_month, environmental=aggregates,
                             nc_nature_clause=str(nc_clause or ""),
                             bm_in_progress_extra=bm_in_progress_items(
                                 input_value(inputs, "p24_bm_in_progress", model))),
        warnings=warnings, anchors=visual_anchors(model), spacers=spacer_rules(model),
    )
    e.keep_next_blocks, e.keep_next_before_control = keep_with_next_rules(model)
    e.keep_next_title_blocks, e.keep_next_title_suffix = keep_with_next_list_titles(model)
    fill_first_slice = bool(product_control_config(model)["render"].get("first_slice_fill"))
    stem = output_stem(report)
    docx_path = assert_write_allowed(out_dir / f"{stem}.docx")
    pdf_path = assert_write_allowed(out_dir / f"{stem}.pdf") if office else None
    final_path = assert_write_allowed(out_dir / f"{stem}{FINAL_SUFFIX}.docx") if office else None
    if final_path is not None and final_path.exists():
        final_path.unlink()                      # cópia final de um build anterior
    passes: list[dict[str, Any]] = []
    try:
        if office:
            from prog_g2_report.builder import word_pdf

            exporter = pdf_exporter or word_pdf.export_pdf
            export_kwargs = ({"final_docx_path": final_path}
                             if _accepts_keyword(exporter, "final_docx_path") else {})
            page_count = 0           # 1ª passada: provisório; o PDF dá o número real
            measured = not fill_first_slice
            for _ in range(MAX_PASSES):
                rc = _compose(e, page_count)
                rc.document.save(docx_path)
                word_pages = exporter(docx_path, pdf_path, **export_kwargs)
                pdf_pages = _pdf_pages(pdf_path) if pdf_path.exists() else word_pages
                record: dict[str, Any] = {"page_count": page_count, "pdf_pages": pdf_pages,
                                          "word_pages": word_pages}
                passes.append(record)
                if not measured:     # DEC-010 §3: mede a frase de chamada no PDF da 1ª passada
                    measured = True
                    e.first_slice = measure_first_slices(rc, e, pdf_path)
                    record["first_slice"] = {k: {"free_cm": round(v[0], 3),
                                                 "lead_block_cm": round(v[1], 3)}
                                             for k, v in e.first_slice.items()}
                    if e.first_slice:
                        page_count = pdf_pages
                        continue
                if pdf_pages == page_count:
                    break
                page_count = pdf_pages
        else:
            rc = _compose(e, None)
            rc.document.save(docx_path)
    finally:
        if renderer is not None:
            renderer.close()
    _page_count_results(rc, office, passes)
    _validate_annex_count(rc)
    docx_final = None
    if final_path is not None and final_path.is_file():
        from prog_g2_report.builder.word_pdf import strip_update_fields

        strip_update_fields(final_path)         # campos já atualizados: sem o prompt ao abrir
        docx_final = final_path
    _run_model_validations(rc, e, docx_path)
    review_briefs = _write_review_briefs(rc, e, out_dir)
    model_meta = model.get("model") or {}
    result = BuildResult(report=report, docx_path=docx_path, pdf_path=pdf_path,
                         model_version=str(model_meta.get("version", "")),
                         components=list(rc.results), warnings=warnings)
    write_manifest(out_dir / "manifest.json", result, e, passes, deviations,
                   inputs_path=inputs_path, docx_final=docx_final, review_briefs=review_briefs,
                   source_resolution=source_resolution)
    return result
