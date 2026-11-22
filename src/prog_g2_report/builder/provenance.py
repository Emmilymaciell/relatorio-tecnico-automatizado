"""Proveniência das fontes no `manifest.json` do build (DEC-003, DEC-008, DEC-012).

Para cada fonte do `SourceManifest`, o manifesto registra a identidade no SharePoint
(`drive_id`, `item_id`), a versão (`version_id`), o instante dessa versão (`last_modified`), o
snapshot local de onde ela foi lida (`snapshot_origin`: arquivo e, num extrato multiversão, a
chave da versão) e o sha1 do arquivo usado. Por componente, `source_version` diz qual
fonte/versão ele consumiu.

De onde vem cada campo, nesta ordem (o `SourceRef` explícito sempre prevalece):

    drive_id/item_id  `data/catalog/work_sources.jsonl`, pelo nome do arquivo da fonte no modelo
                      (`sources.<chave>.name`). `projects_text`, `projects_panel` e
                      `projects_ged` são abas/versões da MESMA planilha de `projects`.
    last_modified     catálogo de versões `data/catalog/<fonte>_versions.jsonl`; senão o próprio
                      extrato multiversão (`_last_modified` ou `t` do item da versão); senão um
                      `versions.json` (lista version_id/last_modified) ao lado do snapshot ou
                      na pasta acima (extratos de descoberta, ex.: tmp/agent_B).
    snapshot_origin   arquivo local (`#versão` num extrato multiversão) ou, sem arquivo,
                      `sharepoint:versions/<id> (memória)` — versão lida pelo graph_ro sem
                      gravar bytes (`sources.master_list_remote`, `sources.projects_remote`).
    local_mtime       mtime do arquivo local (UTC): denuncia cópia local sem versão posterior
                      ao snapshot (ex.: GED de uma cópia modificada depois da versão do 2.2).

Linhagem por componente (`component_lineage`, `components[].source_version` do manifesto): uma
lista de fichas, nunca vazia, uma por insumo consumido:

    source:<chave>@<versão>      fonte do SourceManifest (`components[].source`; abas
                                 `projects_panel`/`projects_ged` quando vierem de outra fonte)
    inputs:<chave>@<sha1>        entrada humana declarada em `model.inputs` (`used_by` ou
                                 `components[].input`/`fields`), sha1 do arquivo de inputs
    default:inputs.<chave>       entrada humana ausente: vale o `default` do modelo
    report:<campo>               ReportContext (número, mês, datas da capa e do Encerramento)
    asset:<id>                   asset estático (`components[].asset`/`assets`, sha1 conferido)
    build:<o quê>                derivado do próprio build (nº de páginas do PDF, campos Word)
    model                        texto/estrutura fixos do modelo (ooxml_base, content blocks)
    model:discontinued           bloco de `discontinued` do modelo (não se emite)

Resultado -> componente do modelo: `components[].blocks` (também `<bloco>:<chave>` e os blocos
derivados P<código>_TABLE_CALL/_NO_ACTIVITY pelo sufixo), `review_key`, o próprio
`component_id`, `IMAGE_COMPONENTS` e `VALIDATION_COMPONENTS`.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

from prog_g2_report import REPO_ROOT
from prog_g2_report.builder.context import ComponentResult, SourceManifest, SourceRef

CATALOG_DIR = REPO_ROOT / "data" / "catalog"
WORK_SOURCES = CATALOG_DIR / "work_sources.jsonl"
# Fontes que são abas ou versões da planilha de outra fonte do modelo.
SAME_FILE_AS = {"projects_text": "projects", "projects_panel": "projects",
                "projects_ged": "projects"}
# Visual reconstruído (prefixo do image_slot) -> componente do modelo que declara a fonte.
IMAGE_COMPONENTS = {
    "P2.2_ROAD_DASHBOARD": "P2.2_ROAD_DASHBOARDS",
    "P2.4_ENV_INDICES_PANEL": "P2.4_LICENSE_DASHBOARDS",
    "P2.4_CONDITIONS_PANEL": "P2.4_LICENSE_DASHBOARDS",
}


def bare_version(version: Any) -> str | None:
    """'v438.0' -> '438.0'; None fica None."""
    if version is None:
        return None
    text = str(version).strip()
    return text[1:] if text[:1] in {"v", "V"} else text


def _sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


@cache
def _catalog_ids(path: str) -> dict[str, tuple[str | None, str | None]]:
    return {str(r.get("name")): (r.get("drive_id"), r.get("item_id"))
            for r in _jsonl(Path(path))}


def _base_key(key: str) -> str:
    return SAME_FILE_AS.get(key, key)


def file_name_of(key: str, model: Mapping[str, Any]) -> str | None:
    """Nome do arquivo da fonte no modelo (`sources.<chave>.name`)."""
    spec = (model.get("sources") or {}).get(_base_key(key)) or {}
    return spec.get("name")


def _versions_in(records: Iterable[Mapping[str, Any]], version: str) -> str | None:
    for record in records:
        if bare_version(record.get("version_id")) == version:
            return record.get("last_modified")
    return None


def _extract_item(path: Path, version: str) -> Mapping[str, Any] | None:
    if path.suffix.lower() != ".json" or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, Mapping):
        return None
    for key in (version, f"v{version}"):
        item = data.get(key)
        if isinstance(item, Mapping):
            return item
    return None


def is_multiversion_extract(path: Path, version: str | None) -> bool:
    return version is not None and _extract_item(path, version) is not None


def last_modified_of(ref: SourceRef, catalog_dir: Path = CATALOG_DIR) -> str | None:
    if ref.last_modified:
        return ref.last_modified
    version = bare_version(ref.version_id)
    if version is None:
        return None
    found = _versions_in(_jsonl(catalog_dir / f"{_base_key(ref.key)}_versions.jsonl"), version)
    if found:
        return found
    local = Path(ref.local_path) if ref.local_path else None
    if local is None:
        return None
    item = _extract_item(local, version)
    if item is not None:
        for key in ("_last_modified", "t", "last_modified"):
            if item.get(key):
                return str(item[key])
    for folder in (local.parent, local.parent.parent):
        listing = folder / "versions.json"
        if listing.is_file():
            try:
                records = json.loads(listing.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(records, list):
                found = _versions_in(records, version)
                if found:
                    return found
    return None


def source_provenance(sources: SourceManifest, model: Mapping[str, Any], *,
                      catalog_dir: Path = CATALOG_DIR) -> dict[str, dict[str, Any]]:
    """{chave: campos de proveniência} para cada fonte (ver docstring do módulo)."""
    ids = _catalog_ids(str(catalog_dir / WORK_SOURCES.name))
    out: dict[str, dict[str, Any]] = {}
    for ref in sources.sources.values():
        local = Path(ref.local_path) if ref.local_path else None
        file_name = file_name_of(ref.key, model) or ref.name
        drive_id, item_id = ids.get(str(file_name), (None, None))
        version = bare_version(ref.version_id)
        origin = None
        mtime = None
        if local is not None:
            origin = local.name
            if is_multiversion_extract(local, version):
                origin = f"{local.name}#{ref.version_id}"
            if local.is_file():
                mtime = datetime.fromtimestamp(local.stat().st_mtime, UTC).strftime(
                    "%Y-%m-%dT%H:%M:%SZ")
        elif ref.drive_id and ref.item_id and ref.version_id:
            origin = f"sharepoint:versions/{ref.version_id} (memória)"
        out[ref.key] = {
            "key": ref.key,
            "name": ref.name,
            "file": file_name,
            "version_id": ref.version_id,
            "last_modified": last_modified_of(ref, catalog_dir),
            "drive_id": ref.drive_id or drive_id,
            "item_id": ref.item_id or item_id,
            "snapshot_origin": origin,
            "sha1": ref.sha1 or (_sha1(local) if local is not None and local.is_file() else None),
            "local_path": str(local) if local else None,
            "local_mtime": mtime,
        }
    return out


def _model_sources(model: Mapping[str, Any], component_id: str) -> list[str]:
    for comp in model.get("components") or []:
        if comp.get("component_id") == component_id and comp.get("source"):
            return [str(comp["source"])]
    return []


def _block_sources(model: Mapping[str, Any], block_id: str) -> list[str]:
    out: list[str] = []
    for comp in model.get("components") or []:
        if block_id in (comp.get("blocks") or []) and comp.get("source"):
            out.append(str(comp["source"]))
    return out


def component_source_keys(component_id: str, model: Mapping[str, Any],
                          available: Iterable[str], *,
                          text_projects_key: str = "projects") -> list[str]:
    """Fontes (chaves do SourceManifest) que um resultado consumiu.

    Bloco -> `source` dos componentes do modelo que listam o bloco; `IMAGE:<prefixo>` ->
    componente do visual (`IMAGE_COMPONENTS`); `<bloco>:<chave>` -> o do bloco. Os textos do
    2.2 leem `text_projects_key` (override `projects_text`, registrado como desvio); os
    quadros leem `projects` (+ `projects_panel` para a aba Painel de Controle, se declarada).
    """
    have = set(available)
    if component_id.startswith("IMAGE:"):
        prefix = component_id[len("IMAGE:"):].split(":", 1)[0]
        comp = IMAGE_COMPONENTS.get(prefix)
        keys = _model_sources(model, comp) if comp else []
        if "projects" in keys and "projects_panel" in have:
            keys = [*keys, "projects_panel"]
    else:
        keys = _block_sources(model, component_id.split(":", 1)[0])
        keys = [text_projects_key if k == "projects" else k for k in keys]
    seen: dict[str, None] = {}
    for key in keys:
        if key in have:
            seen.setdefault(key, None)
    return list(seen)


def component_source_versions(results: Iterable[ComponentResult], model: Mapping[str, Any],
                              provenance: Mapping[str, Mapping[str, Any]], *,
                              text_projects_key: str = "projects"
                              ) -> dict[str, list[dict[str, Any]]]:
    """{component_id: [{key, version_id, snapshot_origin}]} (vazio = não lê fonte)."""
    out: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        keys = component_source_keys(result.component_id, model, provenance,
                                      text_projects_key=text_projects_key)
        out[result.component_id] = [
            {"key": k, "version_id": provenance[k].get("version_id"),
             "snapshot_origin": provenance[k].get("snapshot_origin")} for k in keys]
    return out


# --------------------------------------------------------------------------- linhagem por ficha
# Campos de `components[].fields` e chaves de `model.inputs` que o builder lê do ReportContext
# (nunca do arquivo de inputs): `build_report` só usa `report.issue_date`/`signature_date`.
REPORT_FIELDS = {"report_number": "report:report_number",
                 "month_label": "report:reference_month",
                 "issue_date": "report:issue_date",
                 "signature_date": "report:signature_date"}
# Campos derivados do próprio build (CLOSING_PARAGRAPH.fields: page_count = PDF da passada
# anterior, CLOSING_PAGE_COUNT) ou de outro componente (annex_count = CLOSING_ANNEX_COUNT).
BUILD_FIELDS = {"page_count": "build:pdf_page_count"}
FIELD_COMPONENTS = {"annex_count": "CLOSING_ANNEX_COUNT"}
# Componentes cujo valor só existe depois do Word (`builder.word_pdf`).
COMPONENT_BUILD = {"CLOSING_PAGE_COUNT": "build:pdf_page_count", "TOC": "build:word_fields"}
# Presença nomeada (`components[].presence`) -> insumo que a decide (builder.presence).
PRESENCE_LINEAGE = {"product_has_rows": ("source", "master_list"),
                    "product_has_no_rows": ("source", "master_list"),
                    "p22_external_status_present": ("input", "p22_external_status")}
# Validação do modelo (`validations[].id`) -> componente cujo dado ela confere.
VALIDATION_COMPONENTS = {"V_ANNEX_COUNT": "CLOSING_ANNEX_COUNT",
                         "V_PAGE_COUNT": "CLOSING_PAGE_COUNT",
                         # builder.validate: número/mês do Encerramento (CLOSING_PARAGRAPH:
                         # report_number, month_label), códigos citados e Data Entrega contra
                         # body_rows, frame dos EMF do Controle de Produtos
                         "V_NUMBER_MONTH_CONSISTENT": "CLOSING_PARAGRAPH",
                         "V_ALL_DOCS_IN_MASTER_LIST": "CONTROL_OF_PRODUCTS",
                         "V_NO_DELIVERY_AFTER_ISSUE": "CONTROL_OF_PRODUCTS",
                         "V_EMF_FRAME": "CONTROL_OF_PRODUCTS"}
# Classes cujo texto não vem do modelo: só da entrada (AI_SYNTHESIS), do asset ou do dado.
_NO_MODEL_TEXT = {"AI_SYNTHESIS", "STATIC_ASSET", "RECONSTRUCTED_VISUAL"}
PROJECTS_SHEET_SOURCES = ("projects_panel", "projects_ged")


def inputs_record(inputs: Mapping[str, Any] | None, path: Path | None = None) -> dict[str, Any]:
    """Arquivo de entradas humanas no manifesto: caminho, sha1 e chaves — NUNCA o conteúdo.

    Sem arquivo (inputs passados em memória), o sha1 é o do mapeamento serializado.
    """
    inputs = inputs or {}
    if path is not None and Path(path).is_file():
        sha1 = _sha1(Path(path))
    else:
        sha1 = hashlib.sha1(json.dumps(inputs, sort_keys=True, default=str,
                                       ensure_ascii=False).encode("utf-8")).hexdigest()
    keys = sorted(k for k, v in inputs.items()
                  if v is not None and not (isinstance(v, str) and not v.strip()))
    return {"path": os.path.abspath(path) if path is not None else None, "sha1": sha1,
            "keys": keys}


def _resolve_components(component_id: str, model: Mapping[str, Any]
                        ) -> list[Mapping[str, Any]]:
    comps = list(model.get("components") or [])
    by_id = {str(c.get("component_id")): c for c in comps}
    if component_id.startswith("IMAGE:"):
        prefix = component_id[len("IMAGE:"):].split(":", 1)[0]
        target = IMAGE_COMPONENTS.get(prefix)
        return [by_id[target]] if target in by_id else []
    target = VALIDATION_COMPONENTS.get(component_id)
    if target in by_id:
        return [by_id[target]]
    if component_id in by_id:
        return [by_id[component_id]]
    block = component_id.split(":", 1)[0]
    found = [c for c in comps if block in (c.get("blocks") or [])]
    found += [c for c in comps if c.get("review_key") == block and c not in found]
    if not found and block.startswith("P") and "_" in block:
        # bloco derivado por produto (`text_components.product_slot_blocks`: P<código>_TABLE_CALL
        # / _NO_ACTIVITY) pertence ao componente do bloco-base de mesmo sufixo
        suffix = block.split("_", 1)[1]
        found = [c for c in comps
                 if any(str(b).startswith("P") and str(b).split("_", 1)[-1] == suffix
                        for b in c.get("blocks") or [])]
    return found


def _discontinued(component_id: str, model: Mapping[str, Any]) -> bool:
    block = component_id.split(":", 1)[0]
    return any(block in (d.get("blocks") or []) or block == d.get("component_id")
               for d in model.get("discontinued") or [])


def component_lineage(results: Iterable[ComponentResult], model: Mapping[str, Any],
                      provenance: Mapping[str, Mapping[str, Any]],
                      inputs: Mapping[str, Any] | None, inputs_sha1: str, *,
                      text_projects_key: str = "projects") -> dict[str, list[str]]:
    """{component_id: [fichas]} (ver docstring do módulo). Lista nunca vazia: um resultado
    que não se liga a nenhum componente do modelo recebe `unmapped` (o teste o proíbe)."""
    inputs = inputs or {}
    declared = model.get("inputs") or {}
    comps_by_id = {str(c.get("component_id")): c for c in model.get("components") or []}

    def source_token(key: str) -> str:
        if key not in provenance:
            return f"source:{key}@absent"
        version = bare_version(provenance[key].get("version_id"))
        return f"source:{key}@{version or 'unversioned'}"

    def input_token(key: str) -> str:
        if key in REPORT_FIELDS:
            return REPORT_FIELDS[key]
        value = inputs.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            return f"default:inputs.{key}"
        return f"inputs:{key}@{inputs_sha1}"

    def component_sources(comp: Mapping[str, Any], image: bool) -> list[str]:
        key = comp.get("source")
        if not key:
            return []
        key = str(key)
        if key not in provenance and key not in (model.get("sources") or {}):
            return ["model"]                      # ex.: `contract` = seção do próprio modelo
        keys = [text_projects_key if key == "projects" and not image else key]
        if key == "projects":
            keys += [k for k in PROJECTS_SHEET_SOURCES if k in provenance]
        return [source_token(k) for k in keys]

    out: dict[str, list[str]] = {}
    for result in results:
        cid = result.component_id
        image = cid.startswith("IMAGE:")
        tokens: list[str] = []
        if cid.startswith("LIST:"):
            tokens.append("model")                # definição de lista do ooxml_base/blocks
        if _discontinued(cid, model):
            tokens.append("model:discontinued")   # `discontinued` do modelo: não se emite
        comps = _resolve_components(cid, model)
        for comp in comps:
            comp_id = str(comp.get("component_id"))
            if str(comp.get("automation_class")) not in _NO_MODEL_TEXT:
                tokens.append("model")
            tokens += component_sources(comp, image)
            for asset in [comp.get("asset"), *(comp.get("assets") or [])]:
                if asset:
                    tokens.append(f"asset:{asset}")
            if comp.get("input"):
                tokens.append(input_token(str(comp["input"])))
            for name, spec in declared.items():
                if comp_id in ((spec or {}).get("used_by") or []):
                    tokens.append(input_token(str(name)))
            for field_name in comp.get("fields") or []:
                field_name = str(field_name)
                if field_name in declared or field_name in REPORT_FIELDS:
                    tokens.append(input_token(field_name))
                elif field_name in BUILD_FIELDS:
                    tokens.append(BUILD_FIELDS[field_name])
                elif FIELD_COMPONENTS.get(field_name) in comps_by_id:
                    tokens += component_sources(comps_by_id[FIELD_COMPONENTS[field_name]],
                                                False) or ["model"]
                else:
                    tokens.append("model")
            kind, ref = PRESENCE_LINEAGE.get(str(comp.get("presence") or ""), (None, None))
            if kind == "source" and ref:
                tokens.append(source_token(ref))
            elif kind == "input" and ref:
                tokens.append(input_token(ref))
            if comp_id in COMPONENT_BUILD:
                tokens.append(COMPONENT_BUILD[comp_id])
        if cid in VALIDATION_COMPONENTS:
            tokens.append("build:document")       # a validação confere o documento montado
        if not tokens:
            tokens.append("model" if comps else "unmapped")
        out[cid] = list(dict.fromkeys(tokens))
    return out
