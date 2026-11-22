"""P2.2_HIGHWAY_BLOCK — texto do acompanhamento de projeto executivo por rodovia (função pura).

Spec: `config/data_rules/p22_highway_block.yaml` (agente N, CANDIDATE). Bloco do modelo:
`config/g2_content_blocks.yaml` → `P2.2_HIGHWAY_BLOCK`; componente `P2.2_DISCIPLINE_STATUS` de
`config/g2_report_model.yaml`. Conjunto vazio de "em análise": `editorial_defaults.p22_empty_set`.

Regras implementadas (chave da spec entre parênteses):

- ordem das rodovias pelo Painel de Controle (`road_order`); fallback `road_order.value`;
- ordem dos grupos pela primeira entrega no GED (`group_order.rule`), contando só entregas com
  data ≤ `reference_date`; grupos sem entrega ao fim, pela `Ordem Disciplina`;
- disciplinas pela Ordem Disciplina numérica (`discipline_order_in_lines.rule`);
- exclusões do texto (`exclusions.text.by_prefix_of_discipline`);
- conjuntos (`status_sets`) e presença das linhas (`line_presence`);
- templates canônicos (`templates.*`) com a padronização DEC-007
  (`templates.status_line.punctuation`, artigo em todos os itens, concordância corrigida);
- sem a cláusula "Foram tratadas disciplinas como…" (`clauses.foram_tratadas_disciplinas_como`:
  pertence ao resumo executivo e está ausente no padrão vigente);
- ressalva por disciplina na linha de Aprovação (`templates.approval.reservation_qualifier`,
  DEC-015): aprovadas e, em frase própria, aprovadas com ressalva
  (`templates.approval.with_reservation`), como nos nº 11 e nº 12.

Formato de saída: `render.blocktext.BlockText` (estrutura comum), com `paragraphs` em tupla:

    BlockText(block_id, paragraphs: tuple[Paragraph, ...], facts: dict)
    Paragraph(segments, style, numbering, level, list_key, kind, ref)   # list_level/list_id
    Segment(text, bold=False)                                           # são aliases de leitura

`Paragraph.kind` ∈ {"spacer", "heading", "image_slot", "group", "status"}. `image_slot` marca o
lugar do quadro visual da rodovia (`line_presence.dashboard_image`: logo após o título);
`ref` = ``"P2.2_ROAD_DASHBOARD:<rodovia>"``. `level` (`list_level`) 0 = grupo, 1 = linha de
status; `None` fora de lista. `numbering` = definição da lista, de `templates.group_heading.style`
e `templates.status_line.style` ('PargrafodaLista, numId 37 lvl 0/1'). Nenhuma data aparece no
texto (`templates.dates_in_text`).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from prog_g2_report import REPO_ROOT
from prog_g2_report.render.blocktext import BlockText, Paragraph, Segment, numbering_key
from prog_g2_report.sources.projects import (
    ProjectRow,
    ProjectsWorkbook,
    normalize_road,
    normalize_text,
)

BLOCK_ID = "P2.2_HIGHWAY_BLOCK"
SPEC_PATH = REPO_ROOT / "config" / "data_rules" / "p22_highway_block.yaml"
MODEL_PATH = REPO_ROOT / "config" / "g2_report_model.yaml"
LIST_ID = "P2.2_HIGHWAY_BLOCK"
DASHBOARD_REF = "P2.2_ROAD_DASHBOARD"

# Ordem das linhas de status no grupo (content_blocks P2.2_HIGHWAY_BLOCK labels_nº14_order)
STATUS_KEYS = ("acceptance", "approval", "in_analysis", "pending_approval", "not_delivered")

# GRUPO da planilha → chave de `templates.group_heading.forms` (EST, PRI, SEC, OAE)
_GROUP_KEYWORDS = (("oae", "OAE"), ("secund", "SEC"), ("principal", "PRI"), ("estudo", "EST"))
_ARTICLE_GENDER = {"o": "ms", "a": "fs", "os": "mp", "as": "fp"}
_ALTERNATION = re.compile(r"\{([^{}]*\|[^{}]*)\}")
# templates.approval.reservation_qualifier.value (DEC-015)
RESERVATION_MODES = ("per_discipline", "none")


# --------------------------------------------------------------------------- saída
# Segment, Paragraph e BlockText vêm de `render.blocktext` (estrutura comum aos renderizadores).


# --------------------------------------------------------------------------- regras
@dataclass(frozen=True)
class P22Rules:
    """Parâmetros do modelo usados pelo bloco (nada fixo no código além da gramática)."""

    text_exclusions: tuple[str, ...]          # exclusions.text.by_prefix_of_discipline
    dashboard_exclusions: tuple[str, ...]     # exclusions.quadro.by_prefix_of_discipline
    road_order: tuple[str, ...]               # road_order.value (fallback do Painel)
    group_headings: Mapping[str, str]         # templates.group_heading.forms
    templates: Mapping[str, Any]              # templates.*
    articles: Mapping[str, str]               # templates.status_line.article_table
    empty_in_analysis: str                    # editorial_defaults.p22_empty_set.value
    always_emit_in_analysis: bool             # editorial_defaults.p22_empty_set.always_emit_line
    donut_categories: tuple[str, ...]         # quadro_visual.donut.categories_legend_order
    donut_title: str                          # quadro_visual.donut.title
    dashboard_columns: tuple[str, ...]        # quadro_visual.columns[].header
    # templates.approval.reservation_qualifier (DEC-015): 'per_discipline' | 'none'
    reservation_mode: str = "per_discipline"
    reservation_marker: str = "ressalva"      # ...reservation_qualifier.marker
    reservation_separator: str = ". "         # ...reservation_qualifier.sentence_separator


def load_rules(
    spec: Mapping[str, Any] | None = None, model: Mapping[str, Any] | None = None
) -> P22Rules:
    """Monta `P22Rules` a partir da spec do bloco e do modelo (lidos de `config/` se omitidos)."""
    if spec is None:
        spec = yaml.safe_load(Path(SPEC_PATH).read_text(encoding="utf-8"))
    if model is None:
        model = yaml.safe_load(Path(MODEL_PATH).read_text(encoding="utf-8"))
    templates = spec["templates"]
    empty_set = (model.get("editorial_defaults") or {}).get("p22_empty_set") or {}
    empty_value = empty_set.get("value") or _body(templates["in_analysis"]["empty"])
    visual = spec.get("quadro_visual") or {}
    donut = visual.get("donut") or {}
    qualifier = templates["approval"].get("reservation_qualifier")
    if not isinstance(qualifier, Mapping):    # forma textual antiga (v0.12): não qualificar
        qualifier = {"value": "none"}
    mode = str(qualifier.get("value") or "none")
    if mode not in RESERVATION_MODES:
        raise ValueError(f"templates.approval.reservation_qualifier.value inválido: {mode!r}")
    if mode == "per_discipline" and not templates["approval"].get("with_reservation"):
        raise ValueError("reservation_qualifier per_discipline exige templates.approval."
                         "with_reservation")
    return P22Rules(
        text_exclusions=tuple(spec["exclusions"]["text"]["by_prefix_of_discipline"]),
        dashboard_exclusions=tuple(spec["exclusions"]["quadro"]["by_prefix_of_discipline"]),
        road_order=tuple(normalize_road(r) for r in spec["road_order"]["value"]),
        group_headings=dict(templates["group_heading"]["forms"]),
        templates=templates,
        articles={
            normalize_text(k): v for k, v in templates["status_line"]["article_table"].items()
        },
        empty_in_analysis=str(empty_value),
        always_emit_in_analysis=bool(empty_set.get("always_emit_line", True)),
        donut_categories=tuple(donut.get("categories_legend_order") or ()),
        donut_title=str(donut.get("title") or ""),
        dashboard_columns=tuple(c["header"] for c in visual.get("columns") or ()),
        reservation_mode=mode,
        reservation_marker=normalize_text(qualifier.get("marker") or "ressalva"),
        reservation_separator=str(qualifier.get("sentence_separator") or ". "),
    )


def coerce_rules(rules: P22Rules | Mapping[str, Any] | None) -> P22Rules:
    if isinstance(rules, P22Rules):
        return rules
    if rules is None:
        return load_rules()
    # mapping: a spec, com `editorial_defaults` opcional do modelo embutido
    model = None
    if "editorial_defaults" in rules:
        model = {"editorial_defaults": rules.get("editorial_defaults")}
    return load_rules(rules, model)


# --------------------------------------------------------------------------- utilidades
def is_excluded(discipline: str, prefixes: Iterable[str]) -> bool:
    name = normalize_text(discipline)
    return any(name.startswith(normalize_text(p)) for p in prefixes)


def group_key(group: str) -> str:
    """GRUPO da planilha → chave EST/PRI/SEC/OAE (`templates.group_heading.forms`)."""
    name = normalize_text(group)
    for keyword, key in _GROUP_KEYWORDS:
        if keyword in name:
            return key
    raise ValueError(f"GRUPO sem forma de título no modelo: {group!r}")


def enumerate_pt(items: Sequence[str]) -> str:
    """`templates.status_line.enumeration`: 'A', 'A e B', 'A, B e C' (sem vírgula antes do 'e')."""
    items = list(items)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " e " + items[-1]


def article(discipline: str, rules: P22Rules) -> tuple[str, bool]:
    """(artigo, achado) pela primeira palavra (`templates.status_line.article_table`)."""
    words = normalize_text(discipline).split()
    first = words[0] if words else ""
    if first in rules.articles:
        return rules.articles[first], True
    return "o", False


def _body(template: str) -> str:
    return template.split(": ", 1)[1] if ": " in template else template


def _label(template: str) -> str:
    return template.split(": ", 1)[0]


def _strip_final(text: str) -> str:
    return text.rstrip().rstrip(";.").rstrip()


def _choose(alternatives: list[str], *, gender: str | None = None, context: str = "") -> str:
    """Resolve `{a | b | c}`: pela concordância (gênero/número) ou pelo contexto (grupo)."""
    if context:
        for alt in alternatives:
            if alt and alt in context:
                return alt
    if gender:
        suffix = {"ms": "o", "fs": "a", "mp": "os", "fp": "as"}[gender]
        for alt in alternatives:
            if alt.endswith(suffix):
                return alt
    return alternatives[0]


def fill(template: str, *, gender: str | None = None, context: str = "", **values: str) -> str:
    """Preenche um template do modelo: alternâncias `{x | y}` e campos `{nome}`."""

    def alt(match: re.Match[str]) -> str:
        options = [o.strip() for o in match.group(1).split("|")]
        return _choose(options, gender=gender, context=context)

    text = _ALTERNATION.sub(alt, template)
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


# --------------------------------------------------------------------------- conjuntos
def is_pending_approval(row: ProjectRow, reference_date: date) -> bool:
    """`status_sets.pending_approval.rule` (MEDIUM): aceita, Reprovado e reentrega sem data
    ('Aguardando…') ou vencida (data ≤ referência). Reentrega futura não entra."""
    if row.accepted != "sim" or row.evaluation != "reprovado":
        return False
    delivery = row.revision_delivery
    if isinstance(delivery, date):
        return delivery <= reference_date
    return normalize_text(delivery).startswith("aguardando")


def status_sets(rows: Sequence[ProjectRow], reference_date: date) -> dict[str, list[ProjectRow]]:
    """`status_sets`: universo D já filtrado e ordenado → um conjunto por linha de status."""
    return {
        "universe": list(rows),
        "acceptance": [r for r in rows if r.accepted == "sim"],
        "approval": [r for r in rows if r.evaluation.startswith("aprovad")],
        "in_analysis": [r for r in rows if r.situation(reference_date) == "Em análise"],
        "pending_approval": [r for r in rows if is_pending_approval(r, reference_date)],
        "not_delivered": [r for r in rows if r.situation(reference_date) == "Atrasado"],
    }


def present_lines(sets: Mapping[str, list[ProjectRow]], rules: P22Rules) -> list[str]:
    """`line_presence`: Aceitação e Aprovação sempre; Em análise omitida só se o grupo está todo
    aprovado (e, fora disso, emitida mesmo vazia: `p22_empty_set.always_emit_line`); Pendentes e
    Não entregues só se não vazias."""
    keys = ["acceptance", "approval"]
    all_approved = _same(sets["approval"], sets["universe"])
    if not all_approved and (sets["in_analysis"] or rules.always_emit_in_analysis):
        keys.append("in_analysis")
    for key in ("pending_approval", "not_delivered"):
        if sets[key]:
            keys.append(key)
    return keys


def _same(a: Sequence[ProjectRow], b: Sequence[ProjectRow]) -> bool:
    return {r.physical_row for r in a} == {r.physical_row for r in b}


# --------------------------------------------------------------------------- verbalização
def _number_and_gender(names: Sequence[str], rules: P22Rules) -> tuple[bool, str]:
    """Plural se há mais de um item ou se o único item é plural ('os Estudos…'): DEC-007."""
    if len(names) != 1:
        return True, "mp"
    gender = _ARTICLE_GENDER.get(article(names[0], rules)[0], "ms")
    return gender in {"mp", "fp"}, gender


def has_reservation(row: ProjectRow, rules: P22Rules) -> bool:
    """`templates.approval.reservation_qualifier` (DEC-015): Status (AVALIAÇÃO) aprovado com o
    marcador ('Aprovado com ressalva', 'Aprovada com ressalva', 'Aprovado com ressalvas'…)."""
    return row.evaluation.startswith("aprovad") and rules.reservation_marker in row.evaluation


def reservation_split(
    rows: Sequence[ProjectRow], rules: P22Rules
) -> tuple[list[ProjectRow], list[ProjectRow]]:
    """(aprovadas, aprovadas com ressalva) do conjunto `approval`, na ordem recebida. Com
    `reservation_qualifier.value == 'none'` nenhuma linha é qualificada."""
    if rules.reservation_mode != "per_discipline":
        return list(rows), []
    reserved = [r for r in rows if has_reservation(r, rules)]
    return [r for r in rows if not has_reservation(r, rules)], reserved


def _enumerated(templates: Mapping[str, str], names: Sequence[str], rules: P22Rules) -> str:
    """Forma `plural` ou `singular` de um template de linha, para `names` não vazio."""
    plural, gender = _number_and_gender(names, rules)
    if plural:
        with_article = [f"{article(n, rules)[0]} {n}" for n in names]
        return _strip_final(fill(templates["plural"], enum_com_artigo=enumerate_pt(with_article)))
    art, _ = article(names[0], rules)
    return _strip_final(fill(templates["singular"], gender=gender, artigo=art, disciplina=names[0]))


def _sentence_start(text: str) -> str:
    return text[:1].upper() + text[1:]


def _approval_with_reservation(
    plain: Sequence[ProjectRow], reserved: Sequence[ProjectRow], universal: bool, heading: str,
    rules: P22Rules,
) -> str:
    """`templates.approval.reservation_qualifier.rule`: aprovadas primeiro, depois as com
    ressalva em frase própria (`with_reservation`), separadas por `sentence_separator`."""
    approval = rules.templates["approval"]
    reserved_templates = approval["with_reservation"]
    if universal and not plain:
        return _strip_final(fill(reserved_templates["universal"], context=heading))
    reserved_line = _enumerated(reserved_templates, [r.discipline for r in reserved], rules)
    if universal:
        first = _strip_final(fill(approval["universal"], context=heading))
    elif plain:
        first = _enumerated(approval, [r.discipline for r in plain], rules)
    else:
        return reserved_line
    return first + rules.reservation_separator + _sentence_start(_body(reserved_line))


def verbalize(
    key: str, chosen: Sequence[ProjectRow], universe: Sequence[ProjectRow], gkey: str,
    rules: P22Rules,
) -> str:
    """Uma linha de status, sem a pontuação final (aplicada pelo bloco)."""
    templates = rules.templates[key]
    names = [r.discipline for r in chosen]
    heading = rules.group_headings[gkey]
    if key == "in_analysis" and not names:
        return f"{_label(templates['plural'])}: {_strip_final(rules.empty_in_analysis)}"
    if key == "pending_approval":
        return _strip_final(fill(templates["any"], enum_sem_artigo=enumerate_pt(names)))
    if key in {"acceptance", "approval"}:
        universal = bool(names) and _same(chosen, universe) and gkey != "OAE"
        if key == "approval" and names:
            plain, reserved = reservation_split(chosen, rules)
            if reserved:
                return _approval_with_reservation(plain, reserved, universal, heading, rules)
        if universal:
            return _strip_final(fill(templates["universal"], context=heading))
        if not names:
            return _strip_final(fill(templates["empty"]))
    return _enumerated(templates, names, rules)


# --------------------------------------------------------------------------- ordem
def road_order(projects: ProjectsWorkbook, rules: P22Rules) -> list[str]:
    """`road_order`: Painel de Controle; sem Painel, `road_order.value`; rodovias de Projetos
    fora da lista vão ao fim, na ordem física."""
    base = list(projects.road_order) or list(rules.road_order)
    present = projects.roads()
    ordered = [r for r in base if r in present]
    return ordered + [r for r in present if r not in ordered]


def group_order(
    projects: ProjectsWorkbook, road: str, groups: Sequence[str], reference_date: date
) -> tuple[list[str], dict[str, str | None]]:
    """`group_order.rule`: primeira entrega no GED (data ≤ referência) por rodovia e grupo;
    sem entrega ao fim; empate e sem entrega pela Ordem Disciplina (major)."""
    major = {
        g: min((r.order_key for r in projects.projects if r.road == road and r.group == g),
               default=(10**6, 0))
        for g in groups
    }
    first: dict[str, date | None] = dict.fromkeys(groups)
    by_name = {normalize_text(g): g for g in groups}
    for ged in projects.ged:
        if ged.road != road or ged.received_date is None or ged.received_date > reference_date:
            continue
        group = by_name.get(normalize_text(ged.group))
        if group is None:
            continue
        if first[group] is None or ged.received_date < first[group]:
            first[group] = ged.received_date

    def key(g: str) -> tuple:
        d = first[g]
        return (d is None, d or date.max, major[g])

    ordered = sorted(groups, key=key)
    return ordered, {g: (first[g].isoformat() if first[g] else None) for g in ordered}


# --------------------------------------------------------------------------- bloco
def _numbering(style: str | None) -> str | None:
    key = numbering_key(style) if style and "numId" in style else None
    return f"numId_{key}" if key else None


def _road_heading(road: str, rules: P22Rules) -> Paragraph:
    spec = rules.templates["road_heading"]
    runs = spec.get("runs") or [{"text": spec["text"]}]
    segments = tuple(
        Segment(str(run["text"]).replace("{road}", road), bool(run.get("bold", False)))
        for run in runs
    )
    return Paragraph(segments, style=spec.get("style", "Normal"), kind="heading")


def build_road_block(
    projects: ProjectsWorkbook, road: str, reference_date: date, rules: P22Rules
) -> BlockText:
    rows = sorted(
        (r for r in projects.projects
         if r.road == road and not is_excluded(r.discipline, rules.text_exclusions)),
        key=lambda r: (r.order_key, r.physical_row),
    )
    groups = list(dict.fromkeys(r.group for r in rows))
    ordered, first_delivery = group_order(projects, road, groups, reference_date)
    paragraphs: list[Paragraph] = [
        Paragraph((Segment(""),), kind="spacer"),
        _road_heading(road, rules),
        Paragraph((Segment(""),), kind="image_slot", ref=f"{DASHBOARD_REF}:{road}"),
    ]
    # templates.group_heading.style / templates.status_line.style: definição da lista (numId 37)
    group_numbering = _numbering(rules.templates["group_heading"].get("style"))
    status_numbering = _numbering(rules.templates["status_line"].get("style"))
    facts_groups: list[dict[str, Any]] = []
    warnings: list[str] = []
    status_positions: list[int] = []
    for group in ordered:
        gkey = group_key(group)
        universe = [r for r in rows if r.group == group]
        sets = status_sets(universe, reference_date)
        paragraphs.append(Paragraph((Segment(rules.group_headings[gkey]),), style="PargrafodaLista",
                                    numbering=group_numbering, level=0, list_key=LIST_ID,
                                    kind="group"))
        lines = present_lines(sets, rules)
        for key in lines:
            text = verbalize(key, sets[key], universe, gkey, rules)
            status_positions.append(len(paragraphs))
            paragraphs.append(Paragraph((Segment(text + ";"),), style="PargrafodaLista",
                                        numbering=status_numbering, level=1, list_key=LIST_ID,
                                        kind="status"))
        for r in universe:
            if not article(r.discipline, rules)[1]:
                warnings.append(f"artigo padrão 'o' para disciplina fora da tabela: {r.discipline}")
        facts_groups.append({
            "group": group,
            "group_key": gkey,
            "first_delivery": first_delivery[group],
            "lines": lines,
            "sets": {**{k: [r.discipline for r in v] for k, v in sets.items()},
                     # templates.approval.reservation_qualifier (DEC-015)
                     "approval_with_reservation": [
                         r.discipline for r in reservation_split(sets["approval"], rules)[1]]},
        })
    if status_positions:  # `templates.status_line.punctuation`: ponto final na última linha
        last = paragraphs[status_positions[-1]]
        final = last.text[:-1] + "."
        paragraphs[status_positions[-1]] = replace(last, segments=(Segment(final),))
    facts = {
        "road": road,
        "reference_date": reference_date.isoformat(),
        "group_order": [g["group"] for g in facts_groups],
        "groups": facts_groups,
        "status_lines": len(status_positions),
        "warnings": warnings,
        "rule_source": "config/data_rules/p22_highway_block.yaml",
    }
    return BlockText(BLOCK_ID, tuple(paragraphs), facts)


def build_highway_blocks(
    projects: ProjectsWorkbook,
    reference_date: date,
    rules: P22Rules | Mapping[str, Any] | None = None,
) -> list[BlockText]:
    """Um `BlockText` por rodovia, na ordem do Painel de Controle (`road_order`).

    `reference_date` = `inputs.status_reference_date` da spec (MANUAL_INPUT; a mesma data do
    "Atualizado em" do quadro). `rules`: `P22Rules`, a spec como mapping, ou `None` (lê `config/`).
    """
    resolved = coerce_rules(rules)
    return [build_road_block(projects, road, reference_date, resolved)
            for road in road_order(projects, resolved)]


P22_RENDERERS: dict[str, Callable[..., list[BlockText]]] = {BLOCK_ID: build_highway_blocks}
