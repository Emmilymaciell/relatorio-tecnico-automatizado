"""Texto dos blocos do Produto 2.4 — funções PURAS (sem python-docx).

Fonte das regras (lidas em tempo de execução, nunca copiadas para cá):

- `config/data_rules/p24_blocks.yaml` (spec do agente O): consultas, templates, textos fixos,
  ordens de rodovia (`common.highway_orders`), numerais, numeração de listas, rótulos de fase;
- `config/g2_content_blocks.yaml`: blocos do agente D (`P2.4_RO_PERIODO`, `P2.4_RO_LIST`);
- `config/g2_report_model.yaml`: `editorial_defaults.nc_enumeration` e o componente
  `WEEKLY_REPORT_CUTOFF` (faixa RO por rodovia, período min/max, corte no dia 25).

Cada função recebe as linhas do relatório (`body_rows`, `MasterListRow`) e/ou os agregados da
planilha ambiental e devolve `BlockText(paragraphs=[...], facts={...})`. Marcação `**...**` dos
templates vira segmentos em negrito. Formas nunca observadas (UNKNOWN na spec) não são inventadas:
o bloco volta com `status="PENDING_HUMAN"` e um aviso.

`P24_RENDERERS` mapeia `block_id -> callable(P24Inputs) -> BlockText` para o registro do builder.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from prog_g2_report import REPO_ROOT
from prog_g2_report.render.blocktext import BlockText, Paragraph, markup
from prog_g2_report.sources.environmental import (
    STATUS_NEAR_DUE,
    STATUS_OVERDUE,
    EnvironmentalAggregates,
    highway_display,
    norm,
)
from prog_g2_report.sources.master_list import MasterListRow

P24_RULES_PATH = REPO_ROOT / "config" / "data_rules" / "p24_blocks.yaml"
CONTENT_BLOCKS_PATH = REPO_ROOT / "config" / "g2_content_blocks.yaml"
MODEL_PATH = REPO_ROOT / "config" / "g2_report_model.yaml"

PRODUCT = "2.4"  # g2_report_model.yaml products[code=2.4]
WEEKLY_FAMILY = "RO"  # components.WEEKLY_REPORT_CUTOFF.render: "código RO de body_rows"
CUTOFF_DAY = 25  # components.WEEKLY_REPORT_CUTOFF.render: "'até o dia 25' é texto fixo"
# g2_content_blocks.yaml P2.4_BM_EM_ELABORACAO.lead.text (forma de lista, nº 13); bloco MANUAL_INPUT
BM_IN_PROGRESS = "P2.4_BM_EM_ELABORACAO"

Rows = Sequence[MasterListRow]

_CODE = re.compile(r"^([A-Z]+)-0*(\d+)\.(\d+)")
_HIGHWAY = re.compile(r"^RD-\d+[A-Z]?$")
_QUOTED = re.compile(r"'([^']*)'")


# =========================================================================== estrutura de saída
# Segment, Paragraph e BlockText vêm de `render.blocktext` (estrutura comum aos renderizadores).


# =========================================================================== regras
@dataclass(frozen=True)
class P24Rules:
    spec: Mapping[str, Any]  # p24_blocks.yaml
    content_blocks: Mapping[str, Mapping[str, Any]]  # g2_content_blocks.yaml por block_id
    editorial: Mapping[str, Any]  # g2_report_model.yaml editorial_defaults

    def block(self, block_id: str) -> Mapping[str, Any]:
        for item in self.spec["blocks"]:
            if item["block_id"] == block_id:
                return item
        raise KeyError(f"bloco ausente em p24_blocks.yaml: {block_id}")

    def content_block(self, block_id: str) -> Mapping[str, Any]:
        if block_id not in self.content_blocks:
            raise KeyError(f"bloco ausente em g2_content_blocks.yaml: {block_id}")
        return self.content_blocks[block_id]

    def order(self, name: str) -> list[str]:
        """common.highway_orders.<name> (ORDER_RO, ORDER_ALPHA, ORDER_GAMB)."""
        return list(self.spec["common"]["highway_orders"][name])

    @property
    def list_style(self) -> str:
        return str(self.spec["common"]["numbering"]["style"])


def load_rules(
    p24_path: Path = P24_RULES_PATH,
    content_blocks_path: Path = CONTENT_BLOCKS_PATH,
    model_path: Path = MODEL_PATH,
) -> P24Rules:
    spec = yaml.safe_load(Path(p24_path).read_text(encoding="utf-8"))
    blocks = yaml.safe_load(Path(content_blocks_path).read_text(encoding="utf-8"))["blocks"]
    model = yaml.safe_load(Path(model_path).read_text(encoding="utf-8"))
    return P24Rules(
        spec=spec,
        content_blocks={b["block_id"]: b for b in blocks},
        editorial=model.get("editorial_defaults", {}),
    )


@lru_cache(maxsize=1)
def default_rules() -> P24Rules:
    return load_rules()


Rules = P24Rules | None


def _rules(rules: Rules) -> P24Rules:
    return rules if rules is not None else default_rules()


# =========================================================================== utilidades
def code_sort_key(code: str) -> tuple:
    """common.code_sort_key: 'XX-007.1' -> (7, 1)."""
    m = _CODE.match(code or "")
    return (int(m.group(2)), int(m.group(3)), code) if m else (10**9, 0, code or "")


def code_family(code: str) -> str:
    return (code or "").split("-", 1)[0].strip().upper()


def code_suffix(code: str) -> str:
    return (code or "").split("-", 1)[1] if "-" in (code or "") else code


def join_pt(items: Iterable[str]) -> str:
    """common.join_pt: 'A'; 'A e B'; 'A, B e C' (sem vírgula de Oxford)."""
    items = list(items)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " e " + items[-1]


_UNITS_F = ["zero", "uma", "duas", "três", "quatro", "cinco", "seis", "sete", "oito", "nove"]
_TEENS = [
    "dez",
    "onze",
    "doze",
    "treze",
    "quatorze",
    "quinze",
    "dezesseis",
    "dezessete",
    "dezoito",
    "dezenove",
]
_TENS = [
    "",
    "",
    "vinte",
    "trinta",
    "quarenta",
    "cinquenta",
    "sessenta",
    "setenta",
    "oitenta",
    "noventa",
]
_HUNDREDS = [
    "",
    "cento",
    "duzentas",
    "trezentas",
    "quatrocentas",
    "quinhentas",
    "seiscentas",
    "setecentas",
    "oitocentas",
    "novecentas",
]


def _cardinal(n: int, feminine: bool) -> str:
    """Cardinal pt-BR 0..999 (fallback para além do dicionário de common.numerals)."""
    if not 0 <= n <= 999:
        return str(n)

    def small(k: int) -> str:
        if k < 10:
            word = _UNITS_F[k]
            if not feminine:
                word = {"uma": "um", "duas": "dois"}.get(word, word)
            return word
        if k < 20:
            return _TEENS[k - 10]
        tens, unit = divmod(k, 10)
        return _TENS[tens] + (" e " + small(unit) if unit else "")

    if n < 100:
        return small(n)
    if n == 100:
        return "cem"
    hundreds, rest = divmod(n, 100)
    word = _HUNDREDS[hundreds]
    if not feminine and hundreds > 1:
        word = word[:-2] + "os"
    return word + (" e " + small(rest) if rest else "")


def numeral(n: int, feminine: bool, rules: Rules = None) -> str:
    """common.numerals: dicionário do modelo; masculino 1/2 = um/dois, demais = feminino."""
    numerals = _rules(rules).spec["common"]["numerals"]
    fem = {int(k): v for k, v in numerals["feminine"].items()}
    if feminine:
        return fem.get(n) or _cardinal(n, True)
    masc = {int(k): v for k, v in numerals["masculine"].items() if str(k).isdigit()}
    return masc.get(n) or fem.get(n) or _cardinal(n, False)


def _join_pt_slots(template: str) -> str:
    """'{join_pt(highways)}' -> '{highways}' (pseudo-chamada da spec vira slot já unido)."""
    return re.sub(r"\{join_pt\(([A-Za-z_]+)\)\}", r"{\1}", template)


def _single_form(template: str, spec: Mapping[str, str], where: str) -> str:
    """Forma de uma rodovia/trecho: troca `plural_part` por `singular_part` (p24_blocks.yaml
    `<bloco>.single_highway`); o trecho plural precisa existir no template."""
    plural, singular = spec["plural_part"], spec["singular_part"]
    if plural not in template:
        raise KeyError(f"{where}.single_highway.plural_part ausente do template: {plural!r}")
    return template.replace(plural, singular, 1)


def _quoted(text: str) -> list[str]:
    values = _QUOTED.findall(text or "")
    if not values:
        raise ValueError(f"regra sem valor entre aspas: {text!r}")
    return values


def _matcher(query: str) -> Callable[[MasterListRow], bool]:
    """Consulta da spec sobre Manifestação, comparada normalizada (common.manifestation_match).

    "Manifestação == 'X'" / "Manifestação ~ 'X'" -> igualdade; "... começa com 'x'" -> prefixo.
    """
    value = norm(_quoted(query)[0])
    if "começa com" in query:
        return lambda r: norm(r.manifestation).startswith(value)
    return lambda r: norm(r.manifestation) == value


def _rows_24(rows: Iterable[MasterListRow]) -> list[MasterListRow]:
    return sorted((r for r in rows if r.product_code == PRODUCT), key=lambda r: r.physical_row)


def _highway(row: MasterListRow, warnings: list[str]) -> str | None:
    """common.highway_display; 'Geral' (ou outro não-rodovia) nunca aparece nestes blocos."""
    hw = highway_display(row.venture)
    if not _HIGHWAY.match(hw):
        warnings.append(
            f"{row.document} (linha {row.physical_row}): Empreendimento {row.venture!r} ignorado"
        )
        return None
    return hw


def _ordered(highways: Iterable[str], order: Sequence[str], warnings: list[str]) -> list[str]:
    present = list(dict.fromkeys(highways))
    known = [h for h in order if h in present]
    extra = sorted(h for h in present if h not in order)
    if extra:
        warnings.append(f"rodovias fora da ordem do modelo, emitidas ao final: {extra}")
    return known + extra


def _group(rows: Iterable[MasterListRow], warnings: list[str]) -> dict[str, list[MasterListRow]]:
    out: dict[str, list[MasterListRow]] = {}
    for r in rows:
        hw = _highway(r, warnings)
        if hw is not None:
            out.setdefault(hw, []).append(r)
    return out


def _distinct_codes(rows: Iterable[MasterListRow]) -> list[str]:
    return sorted({r.document for r in rows}, key=code_sort_key)


def _para(text: str, **kwargs: Any) -> Paragraph:
    return Paragraph(markup(text), **kwargs)


def _list_para(rules: P24Rules, text: str, numbering: str, level: int, list_key: str) -> Paragraph:
    return Paragraph(
        markup(text), style=rules.list_style, numbering=numbering, level=level, list_key=list_key
    )


def _skipped(block_id: str, reason: str, **facts: Any) -> BlockText:
    return BlockText(block_id, [], {"present": False, "reason": reason, **facts}, status="SKIPPED")


def _ws(text: str) -> str:
    return " ".join(str(text).split())


# =========================================================================== RO (agente D)
def _parse_day(text: str) -> date | None:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_period(value: Any) -> tuple[date, date] | None:
    """Coluna Período: '01/08/2026 A 07/08/2026' ou '02/10/25 a 09/10/25' -> (início, fim)."""
    if value is None:
        return None
    parts = re.split(r"\s+a\s+", str(value).strip(), flags=re.IGNORECASE)
    if len(parts) != 2:
        return None
    start, end = _parse_day(parts[0]), _parse_day(parts[1])
    return (start, end) if start and end else None


def _weekly(rows: Iterable[MasterListRow]) -> list[MasterListRow]:
    return [r for r in _rows_24(rows) if code_family(r.document) == WEEKLY_FAMILY]


def _conditional_clause(spec: Mapping[str, Any], body_rows: Rows, where: str) -> tuple[str, bool]:
    """Cláusula condicional de um template (`trigger_family` + `value_if_true`/`value_if_false`):
    verdadeira se existe documento da família no 2.4 do relatório (P2.4_RM.slots.
    rm_weekly_clause, P2.4_NC.slots.nc_weekly_clause: 'relatórios semanais' só com RO)."""
    family = str(spec.get("trigger_family") or "").upper()
    if not family or "value_if_true" not in spec:
        raise KeyError(f"{where}: cláusula condicional sem trigger_family/value_if_true")
    hit = any(code_family(r.document) == family for r in _rows_24(body_rows))
    return str(spec["value_if_true"] if hit else spec.get("value_if_false") or ""), hit


def render_ro_period(body_rows: Rows, reference_month: str, *, rules: Rules = None) -> BlockText:
    """P2.4_RO_PERIODO — período = menor início e maior fim do `Período` dos RO do relatório;
    corte = dia 25 do mês de referência (components.WEEKLY_REPORT_CUTOFF; WAVE1 §D)."""
    rules = _rules(rules)
    block_id = "P2.4_RO_PERIODO"
    warnings: list[str] = []
    periods = []
    year, month = (int(x) for x in reference_month.split("-"))
    cutoff = date(year, month, CUTOFF_DAY)
    weekly = _weekly(body_rows)
    if not weekly:
        # g2_content_blocks P2.4_RO_PERIODO.presence: só com RO no 2.4 (sem RO, nada a afirmar
        # sobre o período dos relatórios semanais; revisor W4 MINOR 1)
        return _skipped(block_id, "nenhum RO no relatório", cutoff=cutoff.isoformat())
    for r in weekly:
        period = parse_period(r.period)
        if period is None:
            warnings.append(f"{r.document} (linha {r.physical_row}): Período ilegível {r.period!r}")
            continue
        periods.append(period)
        start, end = period
        # validations V_WEEK_START_25: semana iniciada entre 25 e 31 que termina no mês (aviso)
        if start.day >= CUTOFF_DAY and (start.year, start.month) == (end.year, end.month) == (
            year,
            month,
        ):
            warnings.append(
                f"V_WEEK_START_25: {r.document} {highway_display(r.venture)} "
                f"{start:%d/%m/%Y} a {end:%d/%m/%Y} (semana de fronteira entre relatórios)"
            )
    if not periods:
        # há RO, mas nenhum com Período legível: a pessoa precisa informar o período
        return BlockText(
            block_id,
            [],
            {"present": False, "cutoff": cutoff.isoformat()},
            status="PENDING_HUMAN",
            warnings=[*warnings, "nenhum RO com Período legível no relatório"],
        )
    start = min(p[0] for p in periods)
    end = max(p[1] for p in periods)
    template = rules.content_block(block_id)["template"]
    text = template.format(
        weekly_period_start=f"{start:%d/%m/%Y}",
        weekly_period_end=f"{end:%d/%m/%Y}",
        cutoff_date=f"{cutoff:%d/%m/%Y}",
    )
    facts = {
        "present": True,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "cutoff": cutoff.isoformat(),
        "n_weekly_rows": len(periods),
    }
    return BlockText(block_id, [_para(text)], facts, warnings=warnings)


def render_ro_list(body_rows: Rows, *, rules: Rules = None) -> BlockText:
    """P2.4_RO_LIST — por rodovia, 1º e último código RO na ordem física, com a revisão real
    (WAVE1 §D, CONFIRMED); rodovias em common.highway_orders.ORDER_RO (= RO_INTRO)."""
    rules = _rules(rules)
    block_id = "P2.4_RO_LIST"
    warnings: list[str] = []
    weekly = _weekly(body_rows)
    if not weekly:
        # g2_content_blocks P2.4_RO_LIST.presence: só com RO no 2.4 (revisor W4 MINOR 1)
        return _skipped(block_id, "nenhum RO no relatório")
    groups = _group(weekly, warnings)
    if not groups:
        # há RO, mas nenhum com Empreendimento de rodovia: pendência humana
        return BlockText(
            block_id,
            [],
            {"present": False},
            status="PENDING_HUMAN",
            warnings=[*warnings, "nenhum RO no relatório"],
        )
    template = rules.content_block(block_id)["template"]
    paragraphs, ranges = [], {}
    for hw in _ordered(groups, rules.order("ORDER_RO"), warnings):
        first, last = groups[hw][0].document, groups[hw][-1].document
        ranges[hw] = (first, last)
        text = template.replace("RO-{first}", "{first}").replace("RO-{last}", "{last}")
        text = text.format(highway=hw, first=first, last=last)
        paragraphs.append(_list_para(rules, text, "numId_29", 0, block_id))
    facts = {
        "present": True,
        "ranges": ranges,
        "codes": {hw: [r.document for r in rs] for hw, rs in groups.items()},
    }
    return BlockText(block_id, paragraphs, facts, warnings=warnings)


# =========================================================================== RM, NC, ATAS
def render_rm(body_rows: Rows, *, rules: Rules = None) -> BlockText:
    """P2.4_RM — grupos por código RM crescente; rodovias do grupo na ordem física (spec O)."""
    rules = _rules(rules)
    spec = rules.block("P2.4_RM")
    warnings: list[str] = []
    match = _matcher(spec["query"])
    rows = [r for r in _rows_24(body_rows) if match(r)]
    if not rows:
        return _skipped("P2.4_RM", "nenhum Relatório Mensal no relatório")
    groups: dict[str, list[str]] = {}
    for r in rows:
        hw = _highway(r, warnings)
        if hw is not None and hw not in groups.setdefault(r.document, []):
            groups[r.document].append(hw)
    one = spec["slots"]["group_text"]["one_highway"]
    many = _join_pt_slots(spec["slots"]["group_text"]["many_highways"])
    parts = []
    for code in sorted(groups, key=code_sort_key):
        hws = groups[code]
        if len(hws) == 1:
            parts.append(one.format(rm_code=code, highway=hws[0]))
        else:
            parts.append(many.format(rm_code=code, highways=join_pt(hws)))
    weekly, has_weekly = _conditional_clause(spec["slots"]["rm_weekly_clause"], body_rows,
                                             "P2.4_RM.slots.rm_weekly_clause")
    text = _ws(_ws(spec["template"]).format(rm_groups=join_pt(parts), rm_weekly_clause=weekly))
    facts = {"present": True, "groups": groups, "cites_weekly_reports": has_weekly}
    return BlockText("P2.4_RM", [_para(text)], facts, warnings=warnings)


def nc_enumeration_policy(rules: P24Rules) -> str:
    """Política de enumeração das NC: `g2_report_model.yaml editorial_defaults.nc_enumeration
    .value` (único default; sem fallback no código — o validador do modelo confere que o
    `enumerate_max` de p24_blocks.yaml é o mesmo)."""
    try:
        return str(rules.editorial["nc_enumeration"]["value"])
    except (KeyError, TypeError) as exc:
        raise KeyError("editorial_defaults.nc_enumeration ausente no modelo") from exc


def _nc_enumerate(n: int, policy: str) -> bool:
    """editorial_defaults.nc_enumeration: always_when_present | never | up_to_<N>."""
    if n == 0 or policy == "never":
        return False
    if policy == "always_when_present":
        return True
    m = re.fullmatch(r"up_to_(\d+)", policy or "")
    if m:
        return n <= int(m.group(1))
    raise ValueError(f"editorial_defaults.nc_enumeration desconhecido: {policy!r}")


def render_nc(
    body_rows: Rows,
    *,
    rules: Rules = None,
    nature_clause: str = "",
    enumeration: str | None = None,
) -> BlockText:
    """P2.4_NC — frase fixa + enumeração das NC por rodovia (ORDER_ALPHA, códigos crescentes)
    conforme `editorial_defaults.nc_enumeration` + frase de RNC (spec O; WAVE1 §C).

    `nature_clause` é a cláusula AI_SYNTHESIS aprovada (ex.: ', relacionadas a ...');
    vazia por padrão.
    """
    rules = _rules(rules)
    spec = rules.block("P2.4_NC")
    slots = spec["slots"]
    warnings: list[str] = []
    status = "OK"
    rows = _rows_24(body_rows)
    nc = [r for r in rows if _matcher(spec["query"]["nc"])(r)]
    rnc = [r for r in rows if _matcher(spec["query"]["rnc"])(r)]
    policy = enumeration or nc_enumeration_policy(rules)
    nc_groups = {hw: _distinct_codes(rs) for hw, rs in _group(nc, warnings).items()}
    weekly, has_weekly = _conditional_clause(slots["nc_weekly_clause"], body_rows,
                                             "P2.4_NC.slots.nc_weekly_clause")
    text = _ws(_ws(slots["nc_base"]).format(nc_weekly_clause=weekly))
    enumerated = _nc_enumerate(len(nc), policy) and bool(nc_groups)
    if enumerated:
        order = _ordered(nc_groups, rules.order("ORDER_ALPHA"), warnings)
        forms = slots["nc_enum_sentence"]["group_forms"]      # P2.4_NC.slots.nc_enum_sentence
        pieces = []
        for i, hw in enumerate(order):
            codes = nc_groups[hw]
            one = len(codes) == 1
            group = forms["one_code" if one else "many_codes"].format(
                codes=join_pt(codes), highway=hw)
            if i > 0:
                group = forms["next_one_code" if one else "next_many_codes"] + group
            pieces.append(group)
        if len(order) > 2:
            status = "PENDING_HUMAN"
            warnings.append("NC: enumeração com mais de 2 rodovias nunca observada (UNKNOWN)")
        text += slots["nc_enum_sentence"]["text"].format(
            nc_groups="".join(pieces), nc_nature_clause=nature_clause
        )
    rnc_highways = sorted({hw for r in rnc if (hw := _highway(r, warnings))})
    if rnc_highways:
        sentence = slots["rnc_sentence"]["text"]
        if len(rnc_highways) == 1:
            status = "PENDING_HUMAN"
            warnings.append(
                "RNC de um só trecho: forma nunca observada (UNKNOWN); texto provisório"
            )
            sentence = _single_form(sentence, slots["rnc_sentence"]["single_highway"],
                                    "P2.4_NC.slots.rnc_sentence")
            text += sentence.format(highway=rnc_highways[0])
        else:
            text += sentence.format(n_rnc_highways_masc=numeral(len(rnc_highways), False, rules))
    facts = {
        "present": True,
        "nc_codes": nc_groups,
        "n_nc_rows": len(nc),
        "enumerated": enumerated,
        "enumeration_policy": policy,
        "rnc_codes": _distinct_codes(rnc),
        "rnc_highways": rnc_highways,
        "cites_weekly_reports": has_weekly,
    }
    return BlockText("P2.4_NC", [_para(text)], facts, status=status, warnings=warnings)


def render_atas(body_rows: Rows, *, rules: Rules = None) -> BlockText:
    """P2.4_ATAS — moldura fixa + temas por palavra-chave na Descrição das AT (`slots.themes`,
    opcional: sem tema sustentado sai só a moldura factual); presença = existe ≥1 Ata de
    Reunião no 2.4 (anomalia P2.4_ATAS_TEMAS_SEM_SUPORTE)."""
    rules = _rules(rules)
    spec = rules.block("P2.4_ATAS")
    rows = [r for r in _rows_24(body_rows) if _matcher(spec["query"])(r)]
    if not rows:
        return _skipped("P2.4_ATAS", "nenhuma Ata de Reunião no 2.4")
    facts = {"present": True, "n_atas": len(rows), "codes": _distinct_codes(rows)}
    return _themed("P2.4_ATAS", [spec["text"]], body_rows, rules, facts)


# =========================================================================== BM
def _bm_rows(body_rows: Rows, rules: P24Rules, delivered: bool) -> list[MasterListRow]:
    manifestation, status = _quoted(rules.block("P2.4_BM_LIST")["query"])[:2]
    out = []
    for r in _rows_24(body_rows):
        if norm(r.manifestation) != norm(manifestation):
            continue
        if (norm(r.delivery_status) == norm(status)) == delivered:
            out.append(r)
    return out


def _bm_month(description: Any, rules: P24Rules, warnings: list[str], code: str) -> str:
    """P2.4_BM_LIST.slots.bm_month_label: Descrição sem o prefixo 'Boletim de Medição de '."""
    prefix = _quoted(rules.block("P2.4_BM_LIST")["slots"]["bm_month_label"])[0]
    text = _ws(description or "")
    if norm(text[: len(prefix)]) == norm(prefix):
        label = text[len(prefix) :]
    else:
        m = re.search(r"([^\W\d_]+\s*/\s*\d{4})\s*$", text)
        label = m.group(1) if m else text
        warnings.append(f"{code}: Descrição sem o prefixo {prefix!r}: {description!r}")
    return re.sub(r"\s*/\s*", "/", label.strip())


def _bm_paragraphs(
    rules: P24Rules, items: Mapping[str, list[tuple[str, str]]], list_key: str, warnings: list[str]
) -> list[Paragraph]:
    spec = rules.block("P2.4_BM_LIST")["template"]
    semicolon, period = _quoted(rules.block("P2.4_BM_LIST")["slots"]["terminator"])[:2]
    out = []
    for hw in _ordered(items, rules.order("ORDER_ALPHA"), warnings):
        out.append(
            _list_para(
                rules,
                spec["highway_item"]["text"].format(highway=hw),
                "numId_47",
                int(spec["highway_item"]["ilvl"]),
                list_key,
            )
        )
        entries = sorted(items[hw], key=lambda e: code_sort_key(e[0]))
        for i, (code, month) in enumerate(entries):
            terminator = period if i == len(entries) - 1 else semicolon
            text = spec["bm_item"]["text"].format(
                bm_code=code, bm_month_label=month, terminator=terminator
            )
            out.append(_list_para(rules, text, "numId_47", int(spec["bm_item"]["ilvl"]), list_key))
    return out


def _bm_items(
    rows: Iterable[MasterListRow], rules: P24Rules, warnings: list[str]
) -> dict[str, list[tuple[str, str]]]:
    items: dict[str, list[tuple[str, str]]] = {}
    for hw, rs in _group(rows, warnings).items():
        seen = set()
        for r in rs:
            if r.document in seen:
                continue
            seen.add(r.document)
            items.setdefault(hw, []).append(
                (r.document, _bm_month(r.description, rules, warnings, r.document))
            )
    return items


def render_bm_lead(body_rows: Rows, *, rules: Rules = None) -> BlockText:
    """P2.4_BM_LEAD — texto fixo; presença = BM_LIST não vazio."""
    rules = _rules(rules)
    if not _bm_rows(body_rows, rules, delivered=True):
        return _skipped("P2.4_BM_LEAD", "nenhum BM entregue no relatório")
    return BlockText(
        "P2.4_BM_LEAD", [_para(rules.block("P2.4_BM_LEAD")["text"])], {"present": True}
    )


def render_bm_list(body_rows: Rows, *, rules: Rules = None) -> BlockText:
    """P2.4_BM_LIST — BM com Status Entrega 'Entregue'; rodovias ORDER_ALPHA; código crescente;
    ';' nos itens e '.' no último de cada rodovia; numId 47 (lvl0 rodovia, lvl1 BM)."""
    rules = _rules(rules)
    block_id = "P2.4_BM_LIST"
    warnings: list[str] = []
    items = _bm_items(_bm_rows(body_rows, rules, delivered=True), rules, warnings)
    if not items:
        return _skipped(block_id, "nenhum BM entregue no relatório")
    return BlockText(
        block_id,
        _bm_paragraphs(rules, items, block_id, warnings),
        {"present": True, "items": items},
        warnings=warnings,
    )


def render_bm_in_progress(
    body_rows: Rows,
    *,
    rules: Rules = None,
    extra: Sequence[tuple[str, str, str]] = (),
) -> BlockText:
    """P2.4_BM_EM_ELABORACAO (MANUAL_INPUT, parcialmente derivável — P2.4_BM_LIST.adjacent_note).

    Parte derivada = BM do relatório com Status Entrega diferente de 'Entregue'; `extra` são itens
    externos (rodovia, código, 'Mês/AAAA') informados pela revisão humana. Sempre PENDING_HUMAN
    quando há itens: o bloco depende de confirmação.
    """
    rules = _rules(rules)
    block_id = "P2.4_BM_EM_ELABORACAO"
    warnings: list[str] = []
    items = _bm_items(_bm_rows(body_rows, rules, delivered=False), rules, warnings)
    n_extra = 0
    for hw, code, month in extra:
        entries = items.setdefault(highway_display(hw), [])
        # g2_report_model.yaml inputs.p24_bm_in_progress: "a entrada só acrescenta itens
        # externos" — item que já sai derivado da Lista Mestra (mesma rodovia e código) não
        # se repete; o mês derivado prevalece.
        if any(existing == code for existing, _ in entries):
            continue
        entries.append((code, month))
        n_extra += 1
    if not items:
        return _skipped(block_id, "nenhum BM em elaboração")
    lead = _ws(rules.content_block(block_id)["lead"]["text"])
    paragraphs = [_para(lead), *_bm_paragraphs(rules, items, block_id, warnings)]
    facts = {"present": True, "items": items, "n_extra": n_extra}
    return BlockText(
        block_id,
        paragraphs,
        facts,
        status="PENDING_HUMAN",
        warnings=[*warnings, "BM em elaboração: confirmar itens externos à Lista Mestra"],
    )


# =========================================================================== pareceres
def _pa_trigger(body_rows: Rows, presence: str) -> list[MasterListRow]:
    """'existe PA no 2.4 cuja Descrição normalizada contém 'a' OR 'b'' -> PA que disparam."""
    m = re.search(r"existe (\w+) no", presence)
    family = m.group(1).upper() if m else "PA"
    keywords = [norm(k) for k in _quoted(presence)]
    return [
        r
        for r in _rows_24(body_rows)
        if code_family(r.document) == family and any(k in norm(r.description) for k in keywords)
    ]


def _themes_clause(
    spec: Mapping[str, Any], body_rows: Rows
) -> tuple[str, dict[str, list[str]]]:
    """Mapa de temas de um slot (`slots.<nome>` com `themes`): só os temas com documento
    `family` do 2.4 cuja Descrição normalizada casa `any` (regex), na ordem do mapa; formas
    `lead` (1º tema), `follow` (1º depois de `join.after_first`, ou de `join.pair_sep` quando
    são exatamente dois temas) e `bare` (demais), separadores de `join`.
    Devolve (texto, {tema: códigos}); texto vazio = nenhum tema sustentado."""
    family = str(spec.get("family", "PA")).upper()
    docs = [r for r in _rows_24(body_rows) if code_family(r.document) == family]
    hits: dict[str, list[str]] = {}
    chosen = []
    for theme in spec["themes"]:
        codes = [r.document for r in docs
                 if any(re.search(p, norm(r.description)) for p in theme["any"])]
        if codes:
            hits[theme["label"]] = _distinct_codes_from(codes)
            chosen.append(theme)
    if not chosen:
        return "", hits
    join = spec["join"]
    text = chosen[0]["lead"]
    rest = [chosen[1]["follow"], *(t["bare"] for t in chosen[2:])] if len(chosen) > 1 else []
    if len(rest) == 1:
        text += join.get("pair_sep", join["after_first"]) + rest[0]
    elif rest:
        tail = join["rest_sep"].join(rest[:-1]) + join["rest_last_sep"] + rest[-1]
        text += join["after_first"] + tail
    return text, hits


def _distinct_codes_from(codes: Iterable[str]) -> list[str]:
    return sorted(set(codes), key=code_sort_key)


def _theme_slots(block: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    """Slots de um bloco que são mapas de temas (`slots.<nome>.themes`), na ordem do YAML."""
    return [(name, spec) for name, spec in (block.get("slots") or {}).items()
            if isinstance(spec, Mapping) and isinstance(spec.get("themes"), list)]


def _themed(
    block_id: str, texts: list[str], body_rows: Rows, rules: P24Rules, facts: dict[str, Any]
) -> BlockText:
    """`{<slot>}` nos textos = só os temas com documento que os sustente (cada mapa de
    `slots.<slot>.themes` do bloco). Slot sem tema sustentado:
    - `required: false` → entra `empty` (padrão ''), o resto do texto sai (moldura factual);
    - obrigatório (padrão) → nada sai, com `when_unsupported` (padrão PENDING_HUMAN; SKIPPED
      quando o parágrafo simplesmente não se aplica). Texto fixo não afirma tema sem documento."""
    hits_all: dict[str, list[str]] = {}
    for name, spec in _theme_slots(rules.block(block_id)):
        clause, hits = _themes_clause(spec, body_rows)
        hits_all.update(hits)
        if not clause:
            if spec.get("required", True):
                status = str(spec.get("when_unsupported") or "PENDING_HUMAN")
                reason = f"documentos do gatilho sem tema do mapa (slots.{name})"
                if status == "SKIPPED":
                    kept = {k: v for k, v in facts.items() if k != "present"}
                    return _skipped(block_id, reason, **{**kept, "themes": hits_all})
                return BlockText(block_id, [], {**facts, "present": False, "themes": hits_all},
                                 status=status, warnings=[reason])
            clause = str(spec.get("empty") or "")
        texts = [t.replace("{" + name + "}", clause) for t in texts]
    if _theme_slots(rules.block(block_id)):
        facts = {**facts, "themes": hits_all}
    return BlockText(block_id, [_para(_ws(t)) for t in texts], facts)


def _fixed_with_pa(
    block_id: str, presence_block: str, texts: list[str], body_rows: Rows, rules: P24Rules
) -> BlockText:
    """Presença por palavra-chave (`presence` do bloco `presence_block`); temas pelos mapas de
    `slots` do bloco (`_themed`)."""
    trigger = _pa_trigger(body_rows, rules.block(presence_block)["presence"])
    if not trigger:
        return _skipped(block_id, "nenhum PA com as palavras-chave do gatilho")
    facts: dict[str, Any] = {"present": True, "trigger_codes": _distinct_codes(trigger)}
    return _themed(block_id, texts, body_rows, rules, facts)


def render_pareceres_medicao(body_rows: Rows, *, rules: Rules = None) -> BlockText:
    """P2.4_PARECERES_MEDICAO — moldura fixa + temas por palavra-chave (`slots.themes`);
    presença por palavra-chave na Descrição dos PA."""
    rules = _rules(rules)
    return _fixed_with_pa(
        "P2.4_PARECERES_MEDICAO",
        "P2.4_PARECERES_MEDICAO",
        [rules.block("P2.4_PARECERES_MEDICAO")["text"]],
        body_rows,
        rules,
    )


def render_pareceres_medicao_2(body_rows: Rows, *, rules: Rules = None) -> BlockText:
    """P2.4_PARECERES_MEDICAO_2 — moldura + temas analisados (`slots.themes`, obrigatório: sem
    nenhum, SKIPPED) e destaque opcional (`slots.highlight`); presença 'igual a
    P2.4_PARECERES_MEDICAO' (anomalia P2.4_PARECERES_MEDICAO_2_TEMAS_SEM_SUPORTE)."""
    rules = _rules(rules)
    return _fixed_with_pa(
        "P2.4_PARECERES_MEDICAO_2",
        "P2.4_PARECERES_MEDICAO",
        [rules.block("P2.4_PARECERES_MEDICAO_2")["text"]],
        body_rows,
        rules,
    )


def render_pareceres_amb(body_rows: Rows, *, rules: Rules = None) -> BlockText:
    """P2.4_PARECERES_AMB — dois parágrafos fixos; presença por palavra-chave na Descrição."""
    rules = _rules(rules)
    return _fixed_with_pa(
        "P2.4_PARECERES_AMB",
        "P2.4_PARECERES_AMB",
        list(rules.block("P2.4_PARECERES_AMB")["texts"]),
        body_rows,
        rules,
    )


# =========================================================================== RI
def render_ri(body_rows: Rows, *, rules: Rules = None) -> BlockText:
    """P2.4_RI — 'das {n} rodovias' (numeral feminino) e faixa menor–maior código (negrito)."""
    rules = _rules(rules)
    spec = rules.block("P2.4_RI")
    warnings: list[str] = []
    rows = [r for r in _rows_24(body_rows) if _matcher(spec["query"])(r)]
    if not rows:
        return _skipped("P2.4_RI", "nenhum Relatório de inspeção do alojamento")
    codes = _distinct_codes(rows)
    highways = sorted(_group(rows, warnings))
    status = "OK"
    seqs = sorted({code_sort_key(c)[0] for c in codes})
    if seqs and seqs[-1] - seqs[0] + 1 != len(seqs):
        status = "PENDING_HUMAN"
        warnings.append(
            f"RI: códigos não contíguos {codes}; a faixa esconderia lacuna (spec: validar)"
        )
    template = spec["template"]
    if len(highways) == 1:
        status = "PENDING_HUMAN"
        warnings.append("RI de uma só rodovia: forma nunca observada (UNKNOWN); texto provisório")
        template = _single_form(template, spec["single_highway"], "P2.4_RI")
        text = template.format(highway=highways[0], ri_first=codes[0], ri_last=codes[-1])
    else:
        text = template.format(
            n_highways_fem=numeral(len(highways), True, rules), ri_first=codes[0], ri_last=codes[-1]
        )
    facts = {"present": True, "codes": codes, "highways": highways, "range": (codes[0], codes[-1])}
    return BlockText("P2.4_RI", [_para(text)], facts, status=status, warnings=warnings)


# =========================================================================== licenças
def _no_env(block_id: str) -> BlockText:
    return BlockText(
        block_id,
        [],
        {"present": False},
        status="PENDING_HUMAN",
        warnings=["agregados da planilha ambiental ausentes"],
    )


def _pending(env: EnvironmentalAggregates, rules: P24Rules) -> list:
    status = _quoted(rules.block("P2.4_LIC_LEAD")["query"])[0]
    return list(env.pending_licenses(status))


def render_lic_lead(env: EnvironmentalAggregates | None, *, rules: Rules = None) -> BlockText:
    """P2.4_LIC_LEAD — 'encontram-se pendentes {n} licenças' (n = Status 'Aguardando a liberação',
    todas as linhas). n = 0 ou 1 nunca observado: PENDING_HUMAN."""
    rules = _rules(rules)
    block_id = "P2.4_LIC_LEAD"
    if env is None:
        return _no_env(block_id)
    n = len(_pending(env, rules))
    facts = {"present": n >= 2, "n_pending": n}
    if n < 2:
        return BlockText(
            block_id,
            [],
            facts,
            status="PENDING_HUMAN",
            warnings=[f"{n} licença(s) pendente(s): forma nunca observada (UNKNOWN)"],
        )
    text = rules.block(block_id)["template"].format(n_pending_fem=numeral(n, True, rules))
    return BlockText(block_id, [_para(text, align="left")], facts)


def _phase_label(phase: Any, labels: Mapping[str, str]) -> str | None:
    for key, label in labels.items():
        if norm(key) == norm(phase):
            return label
    return None


def render_lic_list(
    env: EnvironmentalAggregates | None, *, rules: Rules = None, standardize: bool = False
) -> BlockText:
    """P2.4_LIC_LIST — pendentes por rodovia; ordem por contagem crescente, desempate ORDER_GAMB;
    rótulo de fase pelo dicionário `phase_label` (multi-fase: `phase_label_multi_variant`).

    `standardize=True` aplica a concordância 'licenças referentes' (DEC-007, decisão editorial);
    o padrão reproduz o observado (spec: divergences.editorial).
    """
    rules = _rules(rules)
    block_id = "P2.4_LIC_LIST"
    if env is None:
        return _no_env(block_id)
    spec = rules.block(block_id)
    warnings: list[str] = []
    status = "OK"
    by_hw: dict[str, list[str]] = {}
    for lic in _pending(env, rules):
        if lic.highway is None:
            warnings.append(f"Licenças linha {lic.row}: empresa sem rodovia ({lic.company!r})")
            status = "PENDING_HUMAN"
            continue
        by_hw.setdefault(lic.highway, []).append(lic.phase)
    if not by_hw:
        return _skipped(block_id, "nenhuma licença pendente")
    gamb = rules.order("ORDER_GAMB")
    order = sorted(
        by_hw, key=lambda h: (len(by_hw[h]), gamb.index(h) if h in gamb else len(gamb), h)
    )
    semicolon, period = _quoted(spec["template"]["terminator"])[:2]
    single = spec["template"]["single_phase"]
    multi = re.sub(r"\{join_pt\([^}]*\)\}", "{phases}", spec["template"]["multi_phase"])
    labels, multi_labels = spec["phase_label"], spec.get("phase_label_multi_variant", {})
    paragraphs = []
    for i, hw in enumerate(order):
        phases = by_hw[hw]
        terminator = period if i == len(order) - 1 else semicolon
        resolved = []
        for phase in phases:
            label = _phase_label(phase, labels)
            if label is None:
                status = "PENDING_HUMAN"
                warnings.append(f"fase sem rótulo no modelo (phase_label): {phase!r}")
                label = norm(phase)
            resolved.append((phase, label))
        kinds = sorted(
            {p for p, _ in resolved}, key=lambda p: (-phases.count(p), dict(resolved)[p])
        )
        n = len(phases)
        if len(kinds) == 1:
            text = single.format(
                highway=hw,
                n_fem=numeral(n, True, rules),
                s="s" if n > 1 else "",
                phase_label=resolved[0][1],
                terminator=terminator,
            )
            if standardize and n > 1:
                std = spec["template"]["standardized_plural"]   # DEC-007 (editorial)
                text = text.replace(std["observed"], std["standard"], 1)
        else:
            parts = []
            for kind in kinds:
                count = phases.count(kind)
                label = _phase_label(kind, multi_labels) or dict(resolved)[kind]
                part = spec["template"]["phase_part"]["many" if count > 1 else "one"]
                parts.append(part.format(k_fem=numeral(count, True, rules), phase_label=label))
            text = multi.format(
                highway=hw,
                n_fem=numeral(n, True, rules),
                phases=join_pt(parts),
                terminator=terminator,
            )
        paragraphs.append(_list_para(rules, text, "numId_29", 0, block_id))
    facts = {
        "present": True,
        "pending_by_highway": {h: list(v) for h, v in by_hw.items()},
        "order": order,
        "n_pending": sum(len(v) for v in by_hw.values()),
    }
    return BlockText(block_id, paragraphs, facts, status=status, warnings=warnings)


# =========================================================================== condicionantes
def _cond_counts(env: EnvironmentalAggregates) -> tuple[int, int]:
    overdue = sum(env.count(h, STATUS_OVERDUE) for h in env.highways)
    near = sum(env.count(h, STATUS_NEAR_DUE) for h in env.highways)
    return overdue, near


def render_lau_lead(env: EnvironmentalAggregates | None, *, rules: Rules = None) -> BlockText:
    """P2.4_LAU_LEAD — cláusula pelo total de Pendente/Próximo do vencimento (recalculado)."""
    rules = _rules(rules)
    block_id = "P2.4_LAU_LEAD"
    if env is None:
        return _no_env(block_id)
    spec = rules.block(block_id)
    overdue, near = _cond_counts(env)
    facts = {
        "present": overdue == 0,
        "overdue": overdue,
        "near_due": near,
        "reference_date": env.reference_date.isoformat(),
    }
    clauses = spec["slots"]["lau_status_clause"]
    if overdue > 0:
        return BlockText(
            block_id,
            [],
            facts,
            status="PENDING_HUMAN",
            warnings=[f"{overdue} condicionante(s) pendente(s): forma nunca observada (UNKNOWN)"],
        )
    clause = (
        clauses["pendentes == 0 and proximas > 0"]
        if near
        else clauses["pendentes == 0 and proximas == 0"]
    )
    return BlockText(block_id, [_para(spec["template"].format(lau_status_clause=clause))], facts)


def render_lau_list(env: EnvironmentalAggregates | None, *, rules: Rules = None) -> BlockText:
    """P2.4_LAU_LIST — as rodovias da aba Empresas em ORDER_ALPHA; cláusula por nº de próximas
    (0 / 1 / >1); ';' inclusive no último (reproduz o observado)."""
    rules = _rules(rules)
    block_id = "P2.4_LAU_LIST"
    if env is None:
        return _no_env(block_id)
    spec = rules.block(block_id)
    clauses = spec["slots"]["near_due_clause"]
    warnings: list[str] = []
    status = "OK"
    paragraphs, near_by_hw = [], {}
    for hw in _ordered(env.highways, rules.order("ORDER_ALPHA"), warnings):
        overdue, near = env.count(hw, STATUS_OVERDUE), env.count(hw, STATUS_NEAR_DUE)
        near_by_hw[hw] = near
        if overdue:
            status = "PENDING_HUMAN"
            warnings.append(
                f"{hw}: {overdue} condicionante(s) pendente(s): forma nunca observada (UNKNOWN)"
            )
            continue
        key = "proximas == 0" if near == 0 else ("proximas == 1" if near == 1 else "proximas > 1")
        text = spec["template"].format(highway=hw, near_due_clause=clauses[key])
        paragraphs.append(_list_para(rules, text, "numId_29", 0, block_id))
    facts = {
        "present": bool(paragraphs),
        "near_due_by_highway": near_by_hw,
        "overdue_by_highway": {h: env.count(h, STATUS_OVERDUE) for h in env.highways},
    }
    return BlockText(block_id, paragraphs, facts, status=status, warnings=warnings)


# =========================================================================== RCA, RA
def _rca_groups(body_rows: Rows, rules: P24Rules, warnings: list[str]) -> dict[str, list[str]]:
    rows = [r for r in _rows_24(body_rows) if _matcher(rules.block("P2.4_RCA_LIST")["query"])(r)]
    return {hw: _distinct_codes(rs) for hw, rs in _group(rows, warnings).items()}


def render_rca_head(body_rows: Rows, *, rules: Rules = None) -> BlockText:
    """P2.4_RCA_HEAD — texto fixo; presença (padrão nº 13–14) = existe ≥1 RCA."""
    rules = _rules(rules)
    if not _rca_groups(body_rows, rules, []):
        return _skipped("P2.4_RCA_HEAD", "nenhuma análise de RCA no relatório")
    return BlockText(
        "P2.4_RCA_HEAD", [_para(rules.block("P2.4_RCA_HEAD")["text"])], {"present": True}
    )


def render_rca_list(body_rows: Rows, *, rules: Rules = None) -> BlockText:
    """P2.4_RCA_LIST — só rodovias com RCA (TRUE_CHANGE desde nº 13), ORDER_GAMB, letra digitada"""
    rules = _rules(rules)
    block_id = "P2.4_RCA_LIST"
    warnings: list[str] = []
    groups = _rca_groups(body_rows, rules, warnings)
    if not groups:
        return _skipped(block_id, "nenhuma análise de RCA no relatório")
    template = rules.block(block_id)["template"]["sent"]
    paragraphs = []
    for i, hw in enumerate(_ordered(groups, rules.order("ORDER_GAMB"), warnings)):
        if len(groups[hw]) > 1:
            warnings.append(
                f"{hw}: mais de um RCA no relatório (forma não observada); códigos unidos"
            )
        text = template.format(letter=chr(ord("a") + i), highway=hw, rca_code=join_pt(groups[hw]))
        paragraphs.append(_list_para(rules, text, "numId_29", 0, block_id))
    return BlockText(block_id, paragraphs, {"present": True, "codes": groups}, warnings=warnings)


def render_ra(body_rows: Rows, *, rules: Rules = None) -> BlockText:
    """P2.4_RA — lead fixo + itens '{rodovia}: {códigos};' em ORDER_RO (numId 29 lvl1)."""
    rules = _rules(rules)
    spec = rules.block("P2.4_RA")
    warnings: list[str] = []
    rows = [r for r in _rows_24(body_rows) if _matcher(spec["query"])(r)]
    groups = {hw: _distinct_codes(rs) for hw, rs in _group(rows, warnings).items()}
    if not groups:
        return _skipped("P2.4_RA", "nenhum Relatório Ambiental Consolidado")
    template = _join_pt_slots(spec["items"]["template"])
    paragraphs = [_para(spec["lead"]["text"])]
    for hw in _ordered(groups, rules.order("ORDER_RO"), warnings):
        text = template.format(highway=hw, ra_codes=join_pt(groups[hw]))
        paragraphs.append(_list_para(rules, text, "numId_29", 1, "P2.4_RA"))
    return BlockText("P2.4_RA", paragraphs, {"present": True, "codes": groups}, warnings=warnings)


# =========================================================================== registro
@dataclass(frozen=True)
class P24Inputs:
    """Tudo o que os renderizadores do 2.4 consomem (montado pelo builder a partir do contexto)."""

    body_rows: Rows
    reference_month: str | None = None
    environmental: EnvironmentalAggregates | None = None
    rules: Rules = None
    # P2.4_NC_NATURE: inputs.ai_review[review_key do modelo] aprovado (opcional), via
    # nc_nature_clause()
    nc_nature_clause: str = ""
    # P2.4_BM_IN_PROGRESS: inputs.p24_bm_in_progress (itens externos), via bm_in_progress_items()
    bm_in_progress_extra: Sequence[tuple[str, str, str]] = ()


NC_NATURE_COMPONENT = "P2.4_NC_NATURE"   # g2_report_model.yaml components (AI_SYNTHESIS)


def nc_nature_review_key(model: Mapping[str, Any]) -> str:
    """Chave da cláusula aprovada em `inputs.ai_review`: `review_key` do componente
    P2.4_NC_NATURE no modelo (nunca fixa no código)."""
    for comp in model.get("components") or []:
        if comp.get("component_id") == NC_NATURE_COMPONENT:
            key = comp.get("review_key")
            if not key:
                raise KeyError(f"{NC_NATURE_COMPONENT}.review_key ausente no modelo")
            return str(key)
    raise KeyError(f"componente {NC_NATURE_COMPONENT} ausente no modelo")


def nc_nature_clause(ai_review: Any, model: Mapping[str, Any]) -> str:
    """Cláusula de natureza das NC aprovada (`inputs.ai_review[review_key]`, string ou
    `{text: ...}`); '' sem aprovação (DEC-013: a cláusula só sai revisada)."""
    if not isinstance(ai_review, Mapping):
        return ""
    value = ai_review.get(nc_nature_review_key(model))
    if isinstance(value, Mapping):
        value = value.get("text")
    return str(value or "")


_BM_FIELDS = (
    ("rodovia", "highway"),
    ("código", "codigo", "code", "document"),
    ("mês", "mes", "month", "month_label"),
)


def bm_in_progress_items(value: Any) -> tuple[tuple[str, str, str], ...]:
    """`inputs.p24_bm_in_progress` (g2_report_model.yaml inputs, lista) -> itens externos
    (rodovia, código, 'Mês/AAAA') de `P24Inputs.bm_in_progress_extra`.

    Aceita mapeamentos `{rodovia, código, mês}` (ou `highway`, `code`, `month`) e trios. Vazio ou
    None = só a parte derivada (BM do relatório com Status Entrega != 'Entregue')."""
    out: list[tuple[str, str, str]] = []
    for item in value or ():
        if isinstance(item, Mapping):
            fields = [next((item[k] for k in names if item.get(k)), None) for names in _BM_FIELDS]
        elif isinstance(item, Sequence) and not isinstance(item, str) and len(item) == 3:
            fields = list(item)
        else:
            fields = [None]
        if len(fields) != 3 or not all(str(f or "").strip() for f in fields):
            raise ValueError(f"inputs.p24_bm_in_progress: item sem rodovia, código e mês: {item!r}")
        out.append(tuple(str(f).strip() for f in fields))  # type: ignore[arg-type]
    return tuple(out)


def _require_month(inputs: P24Inputs) -> str:
    if not inputs.reference_month:
        raise ValueError("reference_month é obrigatório para P2.4_RO_PERIODO")
    return inputs.reference_month


P24_RENDERERS: dict[str, Callable[[P24Inputs], BlockText]] = {
    "P2.4_RO_PERIODO": lambda i: render_ro_period(i.body_rows, _require_month(i), rules=i.rules),
    "P2.4_RO_LIST": lambda i: render_ro_list(i.body_rows, rules=i.rules),
    "P2.4_RM": lambda i: render_rm(i.body_rows, rules=i.rules),
    "P2.4_NC": lambda i: render_nc(i.body_rows, rules=i.rules, nature_clause=i.nc_nature_clause),
    "P2.4_ATAS": lambda i: render_atas(i.body_rows, rules=i.rules),
    "P2.4_BM_LEAD": lambda i: render_bm_lead(i.body_rows, rules=i.rules),
    "P2.4_BM_LIST": lambda i: render_bm_list(i.body_rows, rules=i.rules),
    "P2.4_BM_EM_ELABORACAO": lambda i: render_bm_in_progress(
        i.body_rows, rules=i.rules, extra=i.bm_in_progress_extra
    ),
    "P2.4_PARECERES_MEDICAO": lambda i: render_pareceres_medicao(i.body_rows, rules=i.rules),
    "P2.4_PARECERES_MEDICAO_2": lambda i: render_pareceres_medicao_2(i.body_rows, rules=i.rules),
    "P2.4_RI": lambda i: render_ri(i.body_rows, rules=i.rules),
    "P2.4_LIC_LEAD": lambda i: render_lic_lead(i.environmental, rules=i.rules),
    "P2.4_LIC_LIST": lambda i: render_lic_list(i.environmental, rules=i.rules),
    "P2.4_LAU_LEAD": lambda i: render_lau_lead(i.environmental, rules=i.rules),
    "P2.4_LAU_LIST": lambda i: render_lau_list(i.environmental, rules=i.rules),
    "P2.4_PARECERES_AMB": lambda i: render_pareceres_amb(i.body_rows, rules=i.rules),
    "P2.4_RCA_HEAD": lambda i: render_rca_head(i.body_rows, rules=i.rules),
    "P2.4_RCA_LIST": lambda i: render_rca_list(i.body_rows, rules=i.rules),
    "P2.4_RA": lambda i: render_ra(i.body_rows, rules=i.rules),
}


def render_all(inputs: P24Inputs) -> dict[str, BlockText]:
    """Todos os blocos do 2.4, na ordem do registro (= ordem do documento)."""
    return {block_id: fn(inputs) for block_id, fn in P24_RENDERERS.items()}
