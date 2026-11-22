"""Componentes textuais simples, emitidos pelo motor de blocos.

    Apresentação           APRES_*  (PRESENTATION_PARAGRAPH; a faixa de fotos é delegada)
    Capítulo 2             CH2_*
    Produtos 2.1 a 2.6     título, subtítulos, cabeçalho da citação, citação (SOURCE_VERBATIM),
                           espaçador, e no fim a frase de ausência OU a chamada da tabela
    Encerramento           ENC_TITLE, ENC_P1, ENC_DATE, ENC_SPACERS, ENC_SIGNATURE_TABLE
    Anexos                 ANEXOS_TITLE

Presença da frase de ausência / chamada da tabela (NO_ACTIVITY_SENTENCE e TABLE_CALL_SENTENCE
do modelo): o YAML só registra a chamada para 2.1, 2.2 e 2.4 e a ausência para 2.3, 2.5 e 2.6,
porque a condição nunca alternou na janela (revisão H). Para que cada produto responda aos dois
casos, os blocos que faltam são **derivados** do irmão (mesmo texto; o template da ausência já é
genérico em `{product_code}`) e marcados `derived_from` — confiança UNKNOWN, nunca observados.
Exceção: produto em `NO_ACTIVITY_SENTENCE.never_for` (o 2.1, QA2-E) nunca emite a frase de
ausência; sem linhas, o slot vira `never_for.<produto>.status` (PENDING_HUMAN) com o `warning`.

`render_text_components(rc, block_ids=None)` emite os blocos na ordem do documento; com
`block_ids`, só os pedidos (ainda na ordem do documento), para o orquestrador intercalar os
outros módulos.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from prog_g2_report.builder.blocks import (
    PENDING_STATUS,
    Block,
    derive_block,
    emit_pending,
    load_blocks,
    load_content_model,
    register_block_renderer,
    render_block,
    render_with_engine,
)
from prog_g2_report.builder.context import ComponentResult, RenderContext
from prog_g2_report.builder.presence import evaluate, load_data_rule_presences, parse_condition
from prog_g2_report.builder.values import (
    MissingValueError,
    base_values,
    closing_values,
    input_value,
)

TEXT_BLOCK_PATTERNS = (
    re.compile(r"^APRES_"),
    re.compile(r"^CH2_"),
    re.compile(r"^P2\.[1-6]_(TITLE|H3_DESCRICAO|QUOTE_INTRO|QUOTE|SPACER|H3_PRODUTOS|"
               r"TABLE_CALL|NO_ACTIVITY)$"),
    re.compile(r"^ENC_"),
    re.compile(r"^ANEXOS_TITLE$"),
)


def _product_codes(model: dict[str, Any]) -> list[str]:
    codes = [str(p["code"]) for p in model.get("products") or []]
    if not codes:
        raise KeyError("model.products vazio")
    return codes


def product_slot_blocks(blocks: Iterable[Block], model: dict[str, Any]) -> list[Block]:
    """Blocos derivados para que todo produto tenha TABLE_CALL e NO_ACTIVITY (ver docstring)."""
    by_id = {b.block_id: b for b in blocks}
    calls = [b for b in by_id.values() if b.block_id.endswith("_TABLE_CALL") and b.product]
    absents = [b for b in by_id.values() if b.block_id.endswith("_NO_ACTIVITY") and b.product]
    if not calls or not absents:
        raise KeyError("o modelo de blocos precisa de ao menos um TABLE_CALL e um NO_ACTIVITY")
    call_base, absent_base = calls[0], absents[0]
    derived: list[Block] = []
    for code in _product_codes(model):
        call_id, absent_id = f"P{code}_TABLE_CALL", f"P{code}_NO_ACTIVITY"
        slot = by_id.get(call_id) or by_id.get(absent_id)
        if slot is None:
            raise KeyError(f"produto {code} sem TABLE_CALL nem NO_ACTIVITY no modelo de blocos")
        if call_id not in by_id:
            derived.append(derive_block(
                call_base, call_id, seq=slot.seq,
                presence=call_base.presence.replace(call_base.product, code),
            ))
        if absent_id not in by_id:
            derived.append(derive_block(
                absent_base, absent_id, seq=slot.seq, text=None,   # só o template genérico
                presence=absent_base.presence.replace(absent_base.product, code),
            ))
    return derived


def is_text_block(block_id: str) -> bool:
    return any(p.match(block_id) for p in TEXT_BLOCK_PATTERNS)


def text_component_plan(blocks: list[Block], model: dict[str, Any]) -> list[Block]:
    chosen = [b for b in blocks if is_text_block(b.block_id)]
    chosen += product_slot_blocks(blocks, model)
    return sorted(chosen, key=lambda b: (b.seq, b.virtual))


def _human_placeholders(content_model: dict[str, Any]) -> set[str]:
    """Placeholders cuja fonte é entrada humana (`placeholders.*.source` MANUAL_INPUT)."""
    out = set()
    for name, spec in (content_model.get("placeholders") or {}).items():
        if str((spec or {}).get("source", "")).startswith("MANUAL_INPUT"):
            out.add(name)
    return out


def _page_break_before(model: dict[str, Any], block: Block) -> bool:
    """`products[].page_break_before.value` aplicado ao título do produto (P2.6 no nº 14)."""
    if not block.block_id.endswith("_TITLE") or block.product is None:
        return False
    for product in model.get("products") or []:
        if str(product.get("code")) == block.product:
            flag = product.get("page_break_before")
            return bool(flag.get("value") if isinstance(flag, dict) else flag)
    return False


NO_ACTIVITY_COMPONENT = "NO_ACTIVITY_SENTENCE"


def no_activity_exception(model: dict[str, Any], block: Block) -> dict[str, Any] | None:
    """`components[NO_ACTIVITY_SENTENCE].never_for[<produto>]` do slot P<produto>_NO_ACTIVITY
    (frase de ausência proibida para o produto), ou None."""
    if block.product is None or not block.block_id.endswith("_NO_ACTIVITY"):
        return None
    for comp in model.get("components") or []:
        if comp.get("component_id") == NO_ACTIVITY_COMPONENT:
            spec = (comp.get("never_for") or {}).get(str(block.product))
            return dict(spec) if isinstance(spec, dict) else None
    return None


def _render_never_absent(rc: RenderContext, block: Block, spec: dict[str, Any],
                         fallbacks: dict[str, str]) -> ComponentResult:
    """NO_ACTIVITY_SENTENCE.never_for: produto com linhas -> SKIPPED (a chamada da tabela sai);
    sem linhas -> pendência (`status`, padrão PENDING_HUMAN) com o `warning`, nunca a frase."""
    condition = parse_condition(block.presence, block.block_id, block.product, fallbacks)
    if not evaluate(condition, rc):
        return rc.record(ComponentResult(block.block_id, "SKIPPED",
                                         detail=f"presença falsa: {condition}"))
    warning = str(spec.get("warning") or f"Produto {block.product} sem documento — confirmar")
    result = emit_pending(rc, block, warning, status=str(spec.get("status") or PENDING_STATUS))
    result.facts.update({"warning": warning, "rule": f"components[{NO_ACTIVITY_COMPONENT}]"
                                                     f".never_for[{block.product}]"})
    return result


def text_values(rc: RenderContext) -> dict[str, str]:
    values = base_values(rc.report, rc.model) | closing_values(rc)
    signatory = input_value(rc, "signatory_name")
    if signatory is not None:
        values["signatory_name"] = str(signatory).strip()
    return values


@register_block_renderer("ENC_DATE")
def render_signature_date(rc: RenderContext, block: Block, values: dict[str, Any]):
    """ENC_DATE (MANUAL_INPUT, SIGNATURE_DATE): 'Capital, {signature_date_long}'."""
    if not values.get("signature_date_long"):
        return emit_pending(rc, block, "data de assinatura não informada (inputs.signature_date)")
    # a entrada é humana; a frase em volta é molde: o motor a emite como TEMPLATE
    return render_with_engine(rc, replace(block, cls="TEMPLATE"), values, check_presence=False)


def render_text_components(
    rc: RenderContext,
    block_ids: list[str] | None = None,
    blocks: list[Block] | None = None,
) -> list[ComponentResult]:
    """Emite os blocos textuais (todos, ou só `block_ids`) na ordem do documento."""
    content_model = load_content_model() if blocks is None else {}
    blocks = load_blocks() if blocks is None else blocks
    plan = text_component_plan(blocks, rc.model)
    if block_ids is not None:
        wanted = set(block_ids)
        unknown = wanted - {b.block_id for b in plan}
        if unknown:
            raise KeyError(f"blocos fora dos componentes textuais: {sorted(unknown)}")
        plan = [b for b in plan if b.block_id in wanted]
    values = text_values(rc)
    human = _human_placeholders(content_model) or {"signatory_name", "signature_date_long",
                                                   "issue_date_long"}
    fallbacks = load_data_rule_presences()
    results: list[ComponentResult] = []
    for block in plan:
        block_values = values | ({"product_code": block.product} if block.product else {})
        never = no_activity_exception(rc.model, block)
        if never is not None:
            results.append(_render_never_absent(rc, block, never, fallbacks))
            continue
        try:
            results.append(render_block(
                rc, block, block_values,
                page_break_before=_page_break_before(rc.model, block), fallbacks=fallbacks,
            ))
        except MissingValueError as exc:
            status = PENDING_STATUS if exc.name in human else "FAILED"
            results.append(emit_pending(rc, block, str(exc), status=status))
    return results
