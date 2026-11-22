"""Valores dos placeholders dos blocos de texto (`config/g2_content_blocks.yaml: placeholders`).

Nada aqui conhece um relatório específico: número, mês, datas e contagens chegam pelo
`ReportContext`, pelo modelo (`editorial_defaults`, `inputs`) ou por `RenderContext.data`.

    base_values(report, model)    report_number, month_label, contract_ref, datas por extenso
    closing_values(rc)            page_count/annex_count e extensos (ENC_P1)
    input_value(rc, key)          entrada humana declarada em `model.inputs`
    input_value(inputs, key, model)  idem, sobre o mapeamento de entradas do montador
    number_words_pt(n, feminine)  cardinal por extenso pt-BR, 0 a 999, sem dependência externa
    long_date_pt(d)               '09 de Setembro de 2026'

Convenção de dados (pedida ao orquestrador, ver retorno do builder T):
    rc.data["inputs"]            {chave de model.inputs: valor}
    rc.data["master_list_rows"]  list[MasterListRow] (todas as linhas ou já selecionadas)
    rc.data["page_count"]        páginas do PDF final (segunda passada com o Word)
    rc.data["annex_count"]       opcional; se ausente, len(select_index(...)) (DEC-012)
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from prog_g2_report.builder.context import RenderContext, ReportContext
from prog_g2_report.report_id import MONTH_NAMES, month_label
from prog_g2_report.sources import master_list as ml

# --- extenso pt-BR ------------------------------------------------------------------------
# Regra: g2_content_blocks.yaml ENC_P1.numerals.rule — conectivo 'e' entre centenas, dezenas e
# unidades; 100 = 'cem'; 101–199 = 'cento e …'; gênero só muda 1, 2 e as centenas 200–900.
_UNITS_M = ("zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove")
_UNITS_F = ("zero", "uma", "duas", "três", "quatro", "cinco", "seis", "sete", "oito", "nove")
_TEENS = ("dez", "onze", "doze", "treze", "quatorze", "quinze", "dezesseis", "dezessete",
          "dezoito", "dezenove")
_TENS = ("", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta",
         "noventa")
_HUNDREDS_M = ("", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos",
               "setecentos", "oitocentos", "novecentos")
_HUNDREDS_F = ("", "cento", "duzentas", "trezentas", "quatrocentas", "quinhentas", "seiscentas",
               "setecentas", "oitocentas", "novecentas")


class MissingValueError(KeyError):
    """Um placeholder ou entrada obrigatória não tem valor. Nunca se emite `{x}` no documento."""

    def __init__(self, name: str, where: str = "") -> None:
        self.name = name
        self.where = where
        super().__init__(f"sem valor para '{name}'" + (f" em {where}" if where else ""))


def number_words_pt(n: int, feminine: bool = False) -> str:
    """Cardinal por extenso em minúsculas, 0 a 999. `feminine` para 'páginas', 'licenças'…"""
    if not isinstance(n, int) or isinstance(n, bool) or not 0 <= n <= 999:
        raise ValueError(f"extenso suportado de 0 a 999: {n!r}")
    units = _UNITS_F if feminine else _UNITS_M
    if n == 0:
        return units[0]
    if n == 100:
        return "cem"
    parts: list[str] = []
    hundreds, rest = divmod(n, 100)
    if hundreds:
        parts.append((_HUNDREDS_F if feminine else _HUNDREDS_M)[hundreds])
    if rest:
        tens, unit = divmod(rest, 10)
        if rest < 10:
            parts.append(units[rest])
        elif rest < 20:
            parts.append(_TEENS[rest - 10])
        else:
            parts.append(_TENS[tens] if not unit else f"{_TENS[tens]} e {units[unit]}")
    return " e ".join(parts)


def long_date_pt(value: date) -> str:
    """'09 de Setembro de 2026' — dia com 2 dígitos, mês com inicial maiúscula (ENC_DATE.note)."""
    return f"{value.day:02d} de {MONTH_NAMES[value.month]} de {value.year}"


def format_report_number(number: int) -> str:
    """Número no texto: dois dígitos ('N° 09' em P2.1_ATAS_REALOC; report_id.format_report)."""
    return f"{number:02d}"


# --- valores ------------------------------------------------------------------------------
def base_values(report: ReportContext, model: dict[str, Any]) -> dict[str, str]:
    """Placeholders comuns: report_number, month_label, contract_ref, issue/signature_date_long."""
    try:
        contract_ref = model["editorial_defaults"]["contract_ref"]["value"]
    except (KeyError, TypeError) as exc:
        raise MissingValueError("contract_ref", "model.editorial_defaults") from exc
    values = {
        "report_number": format_report_number(report.report_number),
        "month_label": month_label(report.reference_month),
        "contract_ref": str(contract_ref),
        "issue_date_long": long_date_pt(report.issue_date),
    }
    if report.signature_date is not None:
        values["signature_date_long"] = long_date_pt(report.signature_date)
    return values


def input_value(
    source: RenderContext | Mapping[str, Any] | None,
    key: str,
    model: Mapping[str, Any] | None = None,
) -> Any:
    """Entrada humana declarada em `model.inputs` (nada manual escondido). None = não informada.

    `input_value(rc, key)` lê `rc.data["inputs"]` com `rc.model`; `input_value(inputs, key,
    model)` lê o mapeamento de entradas do montador. Chave fora de `model.inputs` levanta
    KeyError — inclusive quando o valor foi informado (Gate B F1).
    """
    if hasattr(source, "data") and hasattr(source, "model"):          # RenderContext
        inputs = source.data.get("inputs") or {}
        model = source.model if model is None else model
    else:
        if model is None:
            raise TypeError("input_value(inputs, key, model): o modelo é obrigatório")
        inputs = source or {}
    declared = model.get("inputs") or {}
    if key not in declared:
        raise KeyError(f"entrada não declarada em model.inputs: {key}")
    value = inputs.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return value


def master_list_rows(rc: RenderContext) -> list[ml.MasterListRow]:
    if "master_list_rows" not in rc.data:
        raise MissingValueError("master_list_rows", "rc.data")
    return list(rc.data["master_list_rows"])


def closing_values(rc: RenderContext) -> dict[str, str]:
    """page_count/annex_count do ENC_P1, só os que já são conhecidos.

    - page_count: páginas do PDF final (CLOSING_PAGE_COUNT), extenso FEMININO;
    - annex_count: len(index_rows) (CLOSING_ANNEX_COUNT, DEC-012), extenso MASCULINO.
    """
    values: dict[str, str] = {}
    page_count = rc.data.get("page_count")
    if page_count is not None:
        values["page_count"] = str(int(page_count))
        values["page_count_words"] = number_words_pt(int(page_count), feminine=True)
    annex_count = rc.data.get("annex_count")
    if annex_count is None and "master_list_rows" in rc.data:
        annex_count = len(ml.select_index(master_list_rows(rc), rc.report.report_number))
    if annex_count is not None:
        values["annex_count"] = str(int(annex_count))
        values["annex_count_words"] = number_words_pt(int(annex_count), feminine=False)
    return values
