"""P2.2_DESAPROPRIACAO e P2.2_INTERFERENCIAS — status externos por rodovia (função pura).

Componente `P2.2_EXTERNAL_STATUS` (MANUAL_INPUT, GAP-009) de `config/g2_report_model.yaml`: não há
planilha de GDP/Casa Civil/GFD/concessionária; a entrada humana `inputs.p22_external_status`
traz, por rodovia, o status desses campos de cada matriz. A Análise Programa (`prog`) NÃO é entrada:
é o status da disciplina na aba Projetos (`schema.derived.prog`, QA2-E). Regras e de onde vêm:

    formato da entrada        model `inputs.p22_external_status.schema` (rodovia -> matriz -> campo)
    campos derivados          `schema.derived.<campo>`: disciplina por matriz (`disciplines`,
                              prefixo de Projetos!D), conjuntos de `p22_highway_block.yaml
                              #status_sets` com a data de referência do 2.2, texto pelo 1º
                              conjunto de `status_text` (`by_matrix` troca o texto numa matriz;
                              `approval_with_reservation` = ressalva pela regra do bloco por
                              rodovia, `reservation_qualifier`, DEC-015: matriz e corpo do 2.2
                              dão o mesmo status à mesma disciplina);
                              linha fora dos conjuntos, ausente/ambígua ou sem a fonte =
                              PENDING_HUMAN com marcador; valor na entrada = ignorado com aviso
    rótulos e campos          `schema.matrices[id].ref` -> `keys` do bloco (content_blocks
                              `matrices[N]` / `matrix`); `schema.matrices[id].fields` = campo da
                              entrada de cada rótulo, na mesma ordem; `label_part` = rótulo
    sequência de parágrafos   `schema.layout[<bloco>]` (spacer | fixed:N | matrix:<id>)
    textos fixos              content_blocks `<bloco>.fixed_parts` (text_standardized > text >
                              text_historical, como o motor de blocos)
    listas                    `highway_item` (numId N lvl 1, 'A)') e `key_item` (lvl 2, •); uma
                              instância nova por matriz (a letra recomeça em 'A')
    ordem das rodovias        `schema.road_order` = ORDER_P22 (a mesma dos blocos por rodovia)
    pontuação                 `schema.punctuation` (';' por item, '.' no último da matriz)
    campo vazio / ausente     `schema.empty_value` / `schema.missing_field`: PENDING_HUMAN com o
                              marcador visível `[PENDENTE: <campo>]` depois do rótulo
    sem informação            `schema.no_information`: o campo recebe `{null_reason: <motivo>}`
                              e sai `<rótulo> <no_information.text>` (status OK, motivo nos fatos)

Um rótulo nunca sai sem valor (anomalia P2.2_DUP_RD101_SEM_VALOR do nº 14 não se reproduz).
Sem entrada (ou entrada vazia) o bloco sai SKIPPED (`P2.2_EXPROPRIATION_LAYOUT.presence`
p22_external_status_present). Nenhum texto, rodovia ou status de um mês está no código.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from prog_g2_report.render.blocktext import BlockText, Paragraph, Segment, numbering_key
from prog_g2_report.sources.projects import (
    ProjectRow,
    ProjectsWorkbook,
    normalize_road,
    normalize_text,
)

if TYPE_CHECKING:
    from prog_g2_report.render.p22_text import P22Rules

BLOCK_IDS = ("P2.2_DESAPROPRIACAO", "P2.2_INTERFERENCIAS")
INPUT_KEY = "p22_external_status"
MISSING_MARKER = "[PENDENTE: {where}]"
_TEXT_KEYS = ("text_standardized", "text", "text_historical")
_FINAL_PUNCT = re.compile(r"[\s;.,:]+$")


class ExternalStatusError(ValueError):
    """Entrada ou definição do bloco inválida (matriz desconhecida, layout ilegível)."""


# --------------------------------------------------------------------------- definição
def block_matrices(block_id: str, block_raw: Mapping[str, Any],
                   schema: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Matrizes do bloco por id: `schema.matrices[id]` (fields, label_part) + a definição do
    bloco apontada por `ref` (`config/g2_content_blocks.yaml#<bloco>/<caminho>`: keys,
    highway_item, key_item)."""
    from prog_g2_report.model import resolve_key

    out: dict[str, dict[str, Any]] = {}
    for mid, spec in (schema.get("matrices") or {}).items():
        if spec.get("block") != block_id:
            continue
        path = str(spec.get("ref", "")).split("#", 1)[-1]
        prefix = f"{block_id}/"
        if not path.startswith(prefix):
            raise ExternalStatusError(f"schema.matrices.{mid}.ref fora do bloco {block_id}: {path}")
        definition = resolve_key(block_raw, path[len(prefix):])
        if not isinstance(definition, Mapping):
            raise ExternalStatusError(f"schema.matrices.{mid}.ref não resolve: {spec.get('ref')}")
        keys, fields = list(definition.get("keys") or []), list(spec.get("fields") or [])
        if not keys or len(keys) != len(fields):
            raise ExternalStatusError(f"schema.matrices.{mid}: {len(fields)} campos para "
                                      f"{len(keys)} rótulos")
        out[str(mid)] = {**definition, "fields": fields, "label_part": spec.get("label_part")}
    return out


def _fixed_text(part: Mapping[str, Any]) -> str:
    return str(next((part[k] for k in _TEXT_KEYS if part.get(k)), ""))


def _list_numbering(spec: Any) -> str | None:
    key = numbering_key(spec) if spec and "numId" in str(spec) else None
    return f"numId_{key}" if key else None


def _level(spec: Any, default: int) -> int:
    match = re.search(r"\blvl\s+(\d+)", str(spec or ""))
    return int(match.group(1)) if match else default


# --------------------------------------------------------------------------- entrada
def canonical_road(value: Any, highways: Sequence[Mapping[str, Any]] = ()) -> str:
    """Código da rodovia: `normalize_road` + aliases de `contract.highways`."""
    norm = normalize_road(value)
    for highway in highways:
        names = [highway.get("code"), *(highway.get("aliases") or [])]
        if any(normalize_road(n) == norm for n in names if n):
            return str(highway["code"])
    return norm


def normalize_status(
    raw: Mapping[str, Any] | None, highways: Sequence[Mapping[str, Any]] = ()
) -> dict[str, dict[str, Any]]:
    """{rodovia canônica: {matriz: {campo: valor}}} na ordem da entrada."""
    out: dict[str, dict[str, Any]] = {}
    for road, matrices in (raw or {}).items():
        if not isinstance(matrices, Mapping):
            raise ExternalStatusError(f"{INPUT_KEY}.{road}: esperado mapeamento matriz -> campos")
        out.setdefault(canonical_road(road, highways), {}).update(matrices)
    return out


def ordered_roads(status: Mapping[str, Any], road_order: Sequence[str]) -> tuple[list[str],
                                                                                    list[str]]:
    """(rodovias na ordem ORDER_P22, rodovias da entrada fora dela — vão ao fim)."""
    order = [normalize_road(r) for r in road_order]
    known = [r for r in order if r in status]
    extra = [r for r in status if r not in order]
    return known + extra, extra


def _value_text(value: Any) -> str:
    """Texto do status sem pontuação final; '' para None, vazio ou só pontuação."""
    if value is None:
        return ""
    return _FINAL_PUNCT.sub("", str(value).strip())


def no_information(schema: Mapping[str, Any]) -> tuple[str, str]:
    """(chave do sentinela, texto padronizado) de `schema.no_information`."""
    spec = schema.get("no_information") or {}
    key, text = str(spec.get("key") or ""), _value_text(spec.get("text"))
    if not key or not text:
        raise ExternalStatusError("schema.no_information sem key/text: o sentinela de 'sem "
                                  "informação' precisa de texto padronizado no modelo")
    return key, text


def field_value(value: Any, schema: Mapping[str, Any], where: str) -> tuple[str | None, str | None]:
    """(texto a emitir, motivo do sentinela) de um campo informado.

    - texto não vazio -> (texto sem pontuação final, None);
    - `{<no_information.key>: motivo}` com motivo -> (no_information.text, motivo);
    - '' / só pontuação / None / motivo vazio -> (None, None): pendência humana
      (`schema.empty_value`); o chamador emite o marcador visível.
    Mapeamento com outra chave é erro de entrada (nunca se adivinha)."""
    if isinstance(value, Mapping):
        key, text = no_information(schema)
        if set(value) != {key}:
            raise ExternalStatusError(f"{where}: mapeamento aceito só como sentinela "
                                      f"{{{key}: <motivo>}} (schema.no_information)")
        reason = _value_text(value[key])
        return (text, reason) if reason else (None, None)
    text = _value_text(value)
    return (text, None) if text else (None, None)


# --------------------------------------------------------------------------- derivados
@dataclass(frozen=True)
class Derived:
    """Valor de um campo derivado (`schema.derived.<campo>`) para uma rodovia e matriz."""

    value: str | None                  # None = PENDING_HUMAN (marcador visível)
    reason: str = ""                   # por que ficou pendente (aviso)
    facts: Mapping[str, Any] | None = None


def derived_fields(schema: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """{campo: spec} de `schema.derived` (campos que não são entrada humana)."""
    out: dict[str, Mapping[str, Any]] = {}
    for name, spec in (schema.get("derived") or {}).items():
        if not isinstance(spec, Mapping) or not spec.get("disciplines") \
                or not spec.get("status_text"):
            raise ExternalStatusError(f"schema.derived.{name}: exige disciplines e status_text")
        out[str(name)] = spec
    return out


@lru_cache(maxsize=1)
def _default_p22_rules() -> P22Rules:
    from prog_g2_report.render.p22_text import load_rules

    return load_rules()


def _row_sets(row: ProjectRow, reference_date: date,
              p22_rules: P22Rules | None = None) -> set[str]:
    """Conjuntos de `p22_highway_block.yaml#status_sets` que contêm a linha (as mesmas regras do
    bloco por rodovia, `render.p22_text.status_sets`) + `rejected` (Status AVALIAÇÃO
    'reprovado', o teste de `status_sets.pending_approval` sem a condição da reentrega) +
    `approval_with_reservation` (linha de `approval` com ressalva pela MESMA regra do bloco por
    rodovia: `templates.approval.reservation_qualifier`, DEC-015, `render.p22_text.
    reservation_split`; com `value: none` nenhuma linha é qualificada, como no texto)."""
    from prog_g2_report.render.p22_text import reservation_split, status_sets

    sets = {key for key, rows in status_sets([row], reference_date).items()
            if key != "universe" and rows}
    if row.evaluation == "reprovado":
        sets.add("rejected")
    if "approval" in sets:
        rules = p22_rules if p22_rules is not None else _default_p22_rules()
        if reservation_split([row], rules)[1]:
            sets.add("approval_with_reservation")
    return sets


def discipline_rows(projects: ProjectsWorkbook, road: str, prefix: str) -> list[ProjectRow]:
    """Linhas de Projetos da rodovia cuja Disciplina começa por `prefix` (normalizado)."""
    wanted = normalize_text(prefix)
    return [r for r in projects.projects
            if r.road == normalize_road(road) and normalize_text(r.discipline).startswith(wanted)]


def derive_value(spec: Mapping[str, Any], matrix_id: str, road: str,
                 projects: ProjectsWorkbook | None, reference_date: date | None,
                 p22_rules: P22Rules | None = None) -> Derived:
    """Valor de `schema.derived.<campo>` para a rodovia e a matriz (função pura).

    Texto = `status_text` do 1º conjunto que contém a linha da disciplina (`by_matrix` troca o
    texto da matriz). Sem fonte, sem data, sem linha, mais de uma linha ou linha fora dos
    conjuntos = `Derived(None, motivo)`: o chamador emite o marcador (`unmatched`,
    `missing_source`). `p22_rules` = as regras do P2.2_HIGHWAY_BLOCK do mesmo relatório (a
    ressalva usa o mesmo `reservation_qualifier`); omitidas, as de `config/`."""
    prefix = (spec.get("disciplines") or {}).get(matrix_id)
    if not prefix:
        return Derived(None, f"schema.derived: matriz {matrix_id} sem disciplina")
    if projects is None or reference_date is None:
        return Derived(None, f"fonte {spec.get('source', 'projects')!r} ausente "
                             "(schema.derived.missing_source)")
    rows = discipline_rows(projects, road, str(prefix))
    if len(rows) != 1:
        found = ", ".join(f"linha {r.physical_row}" for r in rows) or "nenhuma linha"
        return Derived(None, f"{road}: {found} com a disciplina {prefix!r} na aba Projetos")
    row = rows[0]
    sets = _row_sets(row, reference_date, p22_rules)
    facts = {"physical_row": row.physical_row, "discipline": row.discipline,
             "evaluation": row.evaluation_raw, "situation": row.situation(reference_date),
             "sets": sorted(sets)}
    for item in spec.get("status_text") or []:
        if item.get("set") in sets:
            text = (item.get("by_matrix") or {}).get(matrix_id) or item.get("text")
            return Derived(_value_text(text), facts={**facts, "set": item["set"]})
    return Derived(None, f"{road} {row.discipline!r}: avaliação {row.evaluation_raw!r}, situação "
                         f"{facts['situation']!r} fora de status_text (schema.derived.unmatched)",
                   facts)


# --------------------------------------------------------------------------- render
def render_external_block(
    block_id: str,
    block_raw: Mapping[str, Any],
    status_input: Mapping[str, Any] | None,
    road_order: Sequence[str],
    schema: Mapping[str, Any] | None = None,
    highways: Sequence[Mapping[str, Any]] = (),
    projects: ProjectsWorkbook | None = None,
    reference_date: date | None = None,
    p22_rules: P22Rules | None = None,
) -> BlockText:
    """Um bloco P2.2_DESAPROPRIACAO / P2.2_INTERFERENCIAS: entrada humana + campos derivados
    (`schema.derived`) da planilha de projetos `projects` na data `reference_date` (o mesmo
    snapshot, a mesma data e as mesmas regras `p22_rules` do texto do 2.2)."""
    schema = schema or {}
    if not status_input:
        return BlockText(block_id, (), {"input": INPUT_KEY}, status="SKIPPED",
                         detail=f"sem entrada {INPUT_KEY} (presença p22_external_status_present)")
    status = normalize_status(status_input, highways)
    matrices = block_matrices(block_id, block_raw, schema)
    derived = derived_fields(schema)
    known_ids = set((schema.get("matrices") or {}).keys())
    unknown = {m for road in status.values() for m in road} - known_ids if known_ids else set()
    if unknown:
        raise ExternalStatusError(f"{INPUT_KEY}: matriz desconhecida {sorted(unknown)} "
                                  f"(schema.matrices: {sorted(known_ids)})")
    roads, extra_roads = ordered_roads(status, road_order)
    punct = schema.get("punctuation") or {}
    item_end, last_end = str(punct.get("item", ";")), str(punct.get("last_item", "."))
    parts = list(block_raw.get("fixed_parts") or [])
    paragraphs: list[Paragraph] = []
    warnings = [f"rodovia fora de ORDER_P22 no fim: {r}" for r in extra_roads]
    missing: list[str] = []
    no_info: dict[str, str] = {}               # campo -> motivo declarado (schema.no_information)
    facts_matrices: dict[str, list[str]] = {}
    facts_derived: dict[str, Any] = {}         # campo -> linha/conjunto da planilha
    ignored_input: dict[str, Any] = {}         # campo derivado informado na entrada (ignorado)

    def fixed(index: int) -> None:
        if not 0 <= index < len(parts):
            raise ExternalStatusError(f"{block_id}: fixed_parts[{index}] inexistente")
        part = parts[index]
        paragraphs.append(Paragraph((Segment(_fixed_text(part)),),
                                    style=part.get("style") or "Normal"))

    def matrix(mid: str) -> None:
        if mid not in matrices:
            raise ExternalStatusError(f"{block_id}: layout cita matriz inexistente {mid!r}")
        spec = matrices[mid]
        rows = [r for r in roads if isinstance(status[r].get(mid), Mapping)]
        facts_matrices[mid] = rows
        if projects is not None:
            # schema.derived.*.matrix_roads: rodovia com a disciplina na planilha e fora da
            # entrada não entra na matriz (matrix_absent), mas é avisada
            for derived_spec in derived.values():
                prefix = (derived_spec.get("disciplines") or {}).get(mid)
                for road in ([] if not prefix else projects.roads()):
                    if road not in rows and discipline_rows(projects, road, str(prefix)):
                        warnings.append(f"{INPUT_KEY}: {road} tem {prefix!r} na aba Projetos "
                                        f"e não está na matriz {mid} da entrada")
        if not rows:
            return
        if spec.get("label_part") is not None:
            fixed(int(spec["label_part"]))
        numbering = _list_numbering(spec.get("highway_item"))
        road_level = _level(spec.get("highway_item"), 1)
        key_level = _level(spec.get("key_item"), road_level + 1)
        list_key = f"{block_id}:{mid}"
        items: list[int] = []
        for road in rows:
            paragraphs.append(Paragraph((Segment(f"{road}:"),), style="PargrafodaLista",
                                        numbering=numbering, level=road_level,
                                        list_key=list_key, kind="group"))
            values = status[road][mid]
            for label, field in zip(spec["keys"], spec["fields"], strict=True):
                where = f"{INPUT_KEY}.{road}.{mid}.{field}"
                if field in derived:
                    # schema.derived: a planilha prevalece; a entrada não substitui o valor
                    if field in values:
                        ignored_input[where] = values[field]
                        warnings.append(f"{where}: entrada ignorada — campo derivado da fonte "
                                        f"{derived[field].get('source', 'projects')!r} "
                                        f"(schema.derived.{field})")
                    got = derive_value(derived[field], mid, road, projects, reference_date,
                                       p22_rules)
                    facts_derived[where] = {"value": got.value, **(got.facts or {})}
                    if got.value is None:
                        missing.append(where)
                        warnings.append(f"{where}: {got.reason}")
                        text = f"{label} {MISSING_MARKER.format(where=where)}"
                    else:
                        text = f"{label} {got.value}"
                        items.append(len(paragraphs))
                    paragraphs.append(Paragraph((Segment(text),), style="PargrafodaLista",
                                                numbering=numbering, level=key_level,
                                                list_key=list_key, kind="status"))
                    continue
                value, reason = (field_value(values[field], schema, where)
                                 if field in values else (None, None))
                if value is None:
                    # schema.missing_field / schema.empty_value: nunca o rótulo sem valor
                    missing.append(where)
                    if field in values:
                        warnings.append(f"{where}: campo vazio — informar o status ou "
                                        f"{{{no_information(schema)[0]}: <motivo>}}")
                    text = f"{label} {MISSING_MARKER.format(where=where)}"
                else:
                    if reason is not None:
                        no_info[where] = reason
                    text = f"{label} {value}"
                    items.append(len(paragraphs))
                paragraphs.append(Paragraph((Segment(text),), style="PargrafodaLista",
                                            numbering=numbering, level=key_level,
                                            list_key=list_key, kind="status"))
        for n, pos in enumerate(items):
            end = last_end if n == len(items) - 1 else item_end
            para = paragraphs[pos]
            paragraphs[pos] = Paragraph((Segment(para.text + end),), style=para.style,
                                        numbering=para.numbering, level=para.level,
                                        list_key=para.list_key, kind=para.kind)

    layout = (schema.get("layout") or {}).get(block_id)
    if not layout:
        raise ExternalStatusError(f"schema.layout sem a sequência de {block_id}")
    for token in layout:
        token = str(token)
        if token == "spacer":
            paragraphs.append(Paragraph((Segment(""),), kind="spacer"))
        elif token.startswith("fixed:"):
            fixed(int(token.split(":", 1)[1]))
        elif token.startswith("matrix:"):
            matrix(token.split(":", 1)[1])
        else:
            raise ExternalStatusError(f"{block_id}: token de layout desconhecido {token!r}")
    if not any(facts_matrices.values()):
        return BlockText(block_id, (), {"matrices": facts_matrices}, status="SKIPPED",
                         detail="entrada sem nenhuma matriz deste bloco")
    facts = {"input": INPUT_KEY, "roads": roads, "matrices": facts_matrices,
             "missing_fields": missing, "no_information": no_info, "warnings": warnings,
             "derived": facts_derived, "ignored_input": ignored_input,
             "reference_date": reference_date.isoformat() if reference_date else None,
             "rule_source": "config/g2_report_model.yaml#inputs/p22_external_status/schema"}
    return BlockText(block_id, tuple(paragraphs), facts,
                     status="PENDING_HUMAN" if missing else "OK", warnings=warnings,
                     detail=f"campos sem valor: {', '.join(missing)}" if missing else "")
