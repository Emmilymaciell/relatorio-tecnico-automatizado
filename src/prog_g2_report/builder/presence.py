"""Condições de presença dos blocos (`presence` em `config/g2_content_blocks.yaml`).

O YAML descreve a condição em texto. Aqui ela vira um predicado **nomeado** e testável:

    always                         sempre
    never                          bloco do padrão histórico, removido (TRUE_CHANGE)
    product_has_rows(2.X)          produto com ≥1 linha da Lista Mestra no relatório (DEC-006)
    product_has_no_rows(2.X)       produto sem linhas no relatório (frase de ausência)
    report_has_prefix(P, …)        existe documento com prefixo P no relatório
    product_has_prefix(2.X, P, …)  existe documento com prefixo P no produto
    product_description_matches(2.X, P, k…)  existe documento P no produto cuja Descrição
                                   normalizada contém uma das palavras k (data_rules)
    product_prefix_status_not(2.X, P, s)  existe documento P no produto com Status Entrega
                                   diferente de s (BM em elaboração)
    environmental_license_status(s)  existe licença da planilha ambiental com Status s
    input_present(chave)           entrada humana de `model.inputs` informada
    any(c1, c2, …)                 'c1 OR c2': alguma das condições

O mesmo vocabulário aceita os nomes curtos de `ComponentModel.presence` no modelo
(`product_has_rows`, `product_has_no_rows`, `p22_external_status_present`).

Condição que não se traduz levanta `UntranslatableConditionError` — nunca se adivinha nem se
trata como 'presente por padrão'. Para essas, `parse_condition` tenta a forma mais específica de
`config/data_rules/*.yaml`; o validador do modelo (`model.validate_model`) reprova todo bloco cuja
presença não se traduz (`untranslated_conditions`).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from prog_g2_report import REPO_ROOT
from prog_g2_report.builder.context import RenderContext
from prog_g2_report.sources import master_list as ml

DATA_RULES_DIR = REPO_ROOT / "config" / "data_rules"


class UntranslatableConditionError(ValueError):
    """A condição textual do YAML não corresponde a nenhum predicado nomeado."""


@dataclass(frozen=True)
class Condition:
    name: str
    args: tuple[Any, ...] = ()
    source_text: str = ""

    def __str__(self) -> str:
        return f"{self.name}({', '.join(map(str, self.args))})" if self.args else self.name


# --- normalização --------------------------------------------------------------------------
def _fold(text: Any) -> str:
    raw = unicodedata.normalize("NFD", str(text or ""))
    raw = "".join(c for c in raw if not unicodedata.combining(c))
    return " ".join(raw.casefold().split())


def document_prefix(document: str) -> str:
    """'PA-512.1' -> 'PA'; 'POP-007.1' -> 'POP'."""
    match = re.match(r"\s*([A-Za-z]+)", document or "")
    return match.group(1).upper() if match else ""


# --- tradução texto -> Condition -----------------------------------------------------------
_PRODUCT = r"(2\.[1-6])"
_PREFIXES = r"([A-Z]{2,4}(?:(?:,\s*|\s+ou\s+)[A-Z]{2,4})*)"
_RULES: tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], Condition]], ...] = ()


def _split_prefixes(text: str) -> tuple[str, ...]:
    return tuple(p for p in re.split(r",\s*|\s+ou\s+", text.strip()) if p)


def _rule(pattern: str):
    compiled = re.compile(pattern)

    def decorator(func: Callable[[re.Match[str]], Condition]):
        global _RULES
        _RULES = (*_RULES, (compiled, func))
        return func

    return decorator


@_rule(r"^always(?:,\s.*)?$")
def _always(_m: re.Match[str]) -> Condition:
    # 'always', 'always, uma vez por rodovia', 'always, 4 rodovias': repetição é do renderizador
    return Condition("always")


@_rule(r"^always \(se P" + _PRODUCT + r" ativo\)$")
def _active(m: re.Match[str]) -> Condition:
    # produto ativo = produto com ≥1 linha (placeholders.active_products_enum)
    return Condition("product_has_rows", (m.group(1),))


@_rule(r"^if Produto " + _PRODUCT + r" tem documentos(?: no relatório)?$")
def _has_rows(m: re.Match[str]) -> Condition:
    return Condition("product_has_rows", (m.group(1),))


@_rule(r"^if count\(Lista Mestra, Produto=" + _PRODUCT + r", N\S? ?Relatório=N\) == 0$")
def _no_rows(m: re.Match[str]) -> Condition:
    return Condition("product_has_no_rows", (m.group(1),))


@_rule(r"^if existe (?:documento )?" + _PREFIXES + r" no Produto " + _PRODUCT + r"(?:\s*\(.*\))?$")
def _product_prefix(m: re.Match[str]) -> Condition:
    return Condition("product_has_prefix", (m.group(2), *_split_prefixes(m.group(1))))


@_rule(r"^if existe (?:documento )?" + _PREFIXES + r"(?: no relatório)?(?:\s*\(.*\))?$")
def _report_prefix(m: re.Match[str]) -> Condition:
    return Condition("report_has_prefix", _split_prefixes(m.group(1)))


@_rule(r"^if existe ([A-Z]{2,4}) no Produto " + _PRODUCT
       + r" com Status Entrega diferente de '([^']+)'$")
def _prefix_status_not(m: re.Match[str]) -> Condition:
    # P2.4_BM_EM_ELABORACAO: BM do relatório não entregue (p24_blocks P2.4_BM_LIST.adjacent_note)
    return Condition("product_prefix_status_not", (m.group(2), m.group(1), _fold(m.group(3))))


@_rule(r"^if existe licença com Status '([^']+)'$")
def _license_status(m: re.Match[str]) -> Condition:
    # P2.4_LIC_LIST: licença pendente na planilha ambiental (p24_blocks P2.4_LIC_LEAD.query)
    return Condition("environmental_license_status", (m.group(1),))


@_rule(r"^somente nº .*removido a partir de .*$")
def _removed(_m: re.Match[str]) -> Condition:
    return Condition("never")


# formas de config/data_rules/*.yaml (mais específicas, agente O)
@_rule(r"^(?:padrão \([^)]*\):\s*)?existe ≥1 (?:linha )?([A-Z]{2,4})"
       r"(?: no " + _PRODUCT + r")?\b.*$")
def _at_least_one(m: re.Match[str]) -> Condition:
    if m.group(2):
        return Condition("product_has_prefix", (m.group(2), m.group(1)))
    return Condition("report_has_prefix", (m.group(1),))


@_rule(r"^existe ([A-Z]{2,4}) no " + _PRODUCT + r" cuja Descrição normalizada contém (.+)$")
def _description(m: re.Match[str]) -> Condition:
    keywords = tuple(_fold(k) for k in re.findall(r"'([^']+)'", m.group(3)))
    if not keywords:
        raise UntranslatableConditionError(m.group(0))
    return Condition("product_description_matches", (m.group(2), m.group(1), *keywords))


_MODEL_NAMES = {"always", "never", "product_has_rows", "product_has_no_rows"}
_INPUT_PRESENT = re.compile(r"^([a-z0-9_]+)_present$")


def parse_condition(
    text: str | None,
    block_id: str | None = None,
    product: str | None = None,
    fallbacks: dict[str, str] | None = None,
) -> Condition:
    """Traduz uma condição textual. `fallbacks` = presença em data_rules por block_id."""
    source = " ".join(str(text or "always").split())
    if source in _MODEL_NAMES:
        if source.startswith("product_"):
            if product is None:
                raise UntranslatableConditionError(f"{source} exige o código do produto")
            return Condition(source, (product,), source)
        return Condition(source, (), source)
    if match := _INPUT_PRESENT.match(source):
        return Condition("input_present", (match.group(1),), source)
    for pattern, build in _RULES:
        if match := pattern.match(source):
            cond = build(match)
            return Condition(cond.name, cond.args, source)
    if " OR " in source:
        # 'c1 OR c2' (depois das formas inteiras: 'contém 'a' OR 'b'' é uma regra só); cada
        # parte se traduz sozinha, sem fallback — o OR é explícito no YAML
        try:
            parts = tuple(parse_condition(p, block_id, product) for p in source.split(" OR "))
        except UntranslatableConditionError:
            parts = ()
        if parts:
            return Condition("any", parts, source)
    if fallbacks and block_id and block_id in fallbacks:
        alias = re.match(r"^igual a (\S+)$", fallbacks[block_id])
        target = alias.group(1) if alias else block_id
        if target in fallbacks and not re.match(r"^igual a ", fallbacks[target]):
            return parse_condition(fallbacks[target], target, product, None)
    raise UntranslatableConditionError(f"{block_id or '?'}: {source!r}")


def load_data_rule_presences(directory: Path = DATA_RULES_DIR) -> dict[str, str]:
    """{block_id: presence} de config/data_rules/*.yaml (só presenças textuais)."""
    out: dict[str, str] = {}
    if not directory.exists():
        return out
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for block in data.get("blocks") or []:
            presence = block.get("presence")
            if isinstance(presence, str) and block.get("block_id"):
                out[block["block_id"]] = " ".join(presence.split())
    return out


# --- avaliação -----------------------------------------------------------------------------
def _rows(rc: RenderContext) -> list[ml.MasterListRow]:
    if "master_list_rows" not in rc.data:
        raise KeyError("rc.data['master_list_rows'] é obrigatório para avaliar esta presença")
    return ml.select(rc.data["master_list_rows"], rc.report.report_number)


def _product_rows(rc: RenderContext, product: str) -> list[ml.MasterListRow]:
    return [r for r in _rows(rc) if r.product_code == product]


def _has_prefix(rows: Iterable[ml.MasterListRow], prefixes: Iterable[str]) -> bool:
    wanted = {p.upper() for p in prefixes}
    return any(document_prefix(r.document) in wanted for r in rows)


def _input_present(rc: RenderContext, key: str) -> bool:
    if key not in (rc.model.get("inputs") or {}):
        raise KeyError(f"entrada não declarada em model.inputs: {key}")
    value = (rc.data.get("inputs") or {}).get(key)
    return value is not None and value != "" and value != {} and value != []


def _eval_prefix_status_not(rc: RenderContext, product: str, prefix: str, status: str) -> bool:
    return any(document_prefix(r.document) == prefix and _fold(r.delivery_status) != status
               for r in _product_rows(rc, product))


def _eval_license_status(rc: RenderContext, status: str) -> bool:
    if "environmental" not in rc.data:
        raise KeyError("rc.data['environmental'] é obrigatório para avaliar esta presença")
    aggregates = rc.data["environmental"]
    if aggregates is None:
        raise KeyError("agregados da planilha ambiental ausentes: presença não avaliável")
    return bool(aggregates.pending_licenses(status))


PREDICATES: dict[str, Callable[..., bool]] = {
    "always": lambda rc: True,
    "never": lambda rc: False,
    "product_has_rows": lambda rc, product: bool(_product_rows(rc, product)),
    "product_has_no_rows": lambda rc, product: not _product_rows(rc, product),
    "report_has_prefix": lambda rc, *prefixes: _has_prefix(_rows(rc), prefixes),
    "product_has_prefix": lambda rc, product, *prefixes: _has_prefix(
        _product_rows(rc, product), prefixes
    ),
    "product_description_matches": lambda rc, product, prefix, *keywords: any(
        document_prefix(r.document) == prefix and any(k in _fold(r.description) for k in keywords)
        for r in _product_rows(rc, product)
    ),
    "product_prefix_status_not": _eval_prefix_status_not,
    "environmental_license_status": _eval_license_status,
    "input_present": _input_present,
    "any": lambda rc, *conditions: any(evaluate(c, rc) for c in conditions),
}


def evaluate(condition: Condition, rc: RenderContext) -> bool:
    return PREDICATES[condition.name](rc, *condition.args)


def untranslated_conditions(blocks: Iterable[Any], fallbacks: dict[str, str] | None = None):
    """[(block_id, presence)] que não se traduzem (nem pelo fallback de data_rules)."""
    out: list[tuple[str, str]] = []
    for block in blocks:
        try:
            parse_condition(block.presence, block.block_id, block.product, fallbacks)
        except UntranslatableConditionError:
            out.append((block.block_id, block.presence))
    return out
