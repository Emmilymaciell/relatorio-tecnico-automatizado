"""Controle de Produtos: Lista Mestra → recortes EMF inline no DOCX (DEC-006, DEC-010).

Regras e a chave do modelo que define cada uma (`config/g2_report_model.yaml`, componente
`CONTROL_OF_PRODUCTS`):

- conteúdo = `body_rows` do produto (`sources.master_list.selection`; o chamador seleciona com
  `sources.master_list.select`); ordem física, nunca reordenada (`selection.order`);
- representação = EMF vetorial do Excel (`render`, DEC-010 §1);
- um EMF por página, cabeçalho repetido (`render_params`, DEC-010 §3–4): `sheet`, `columns`,
  `header_rows`, `filter_columns`, `row_height_pt`, `width_cm`, `avail_height_cm`, `aspect`,
  `balance`, e opcionalmente `source_width_pt`/`header_height_pt` (sem eles, a geometria é
  medida na planilha pelo renderizador);
- 1º recorte na página da frase de chamada (`first_slice_fill`, `first_slice_min_rows`,
  `first_slice_gap_cm`, DEC-010 §3): com o espaço livre medido no PDF da 1ª passada
  (`first_page_free_cm`), o 1º recorte ocupa esse espaço se couberem `first_slice_min_rows`
  linhas; senão vai para a página seguinte junto com a frase (keep-with-next), com a altura
  útil menos a da frase (`lead_block_cm`);
- formatação das linhas de dados normalizada antes da cópia (`normalize_data_font`, DEC-007):
  o negrito herdado da planilha nas linhas de dados não é dado; o cabeçalho mantém o seu;
- altura de linha (`row_height_mode`, DEC-010 §4): `min_autofit` = `max(row_height_pt, AutoFit
  do Excel)` por linha, medida pelo renderizador (`measure_row_heights`, COM, na 1ª passada; o
  montador memoriza) — nunca corta uma descrição longa; sem medição (renderizador falso,
  offline) usa o estimador por nº de linhas do texto (`row_height_estimate`,
  `render.paginate.estimate_row_height_pt`). A paginação usa as alturas reais por linha.
  `uniform` = todas com `row_height_pt` (forma antiga).

`resolve_config` aceita o modelo inteiro, o componente ou só o seu `render_params`; aceita ainda
a forma antiga `{control_of_products: {width_cm, render: {...}}}` (fixtures de teste).

O renderizador é injetado (`EmfRenderer`): em produção `office.excel_emf.ExcelEmfRenderer`;
nos testes, um falso que devolve EMF sintético.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from prog_g2_report.builder.context import ComponentResult
from prog_g2_report.render.docx_emf import add_emf_picture, emf_display_height_cm
from prog_g2_report.render.paginate import (
    DEFAULT_AVAIL_HEIGHT_CM,
    DEFAULT_ROW_HEIGHT_PT,
    DEFAULT_WIDTH_CM,
    estimate_row_height_pt,
    paginate,
    rows_that_fit,
    slice_height_cm,
)
from prog_g2_report.sources.master_list import SHEET, MasterListRow

DEFAULT_COMPONENT_ID = "CONTROL_OF_PRODUCTS"
# Defaults documentados da prova (scripts/12_probe_emf_export.py); o modelo prevalece.
DEFAULT_RENDER: dict[str, Any] = {
    "sheet": SHEET,
    "columns": "D:I",              # Documento .. Status Entrega
    "header_rows": (1, 3),         # título + cabeçalho, repetidos em todo recorte
    "filter_columns": "B:M",       # autofiltro histórico (só as setas; nunca a seleção)
    "row_height_pt": DEFAULT_ROW_HEIGHT_PT,
    "avail_height_cm": DEFAULT_AVAIL_HEIGHT_CM,
    "aspect": "frame",
    "balance": False,              # DEC-010 §3: gulosa; True distribui por igual
    "first_slice_fill": False,     # DEC-010 §3: 1º recorte no espaço livre da frase de chamada
    "first_slice_min_rows": 3,
    "first_slice_gap_cm": 0.3,
    "normalize_data_font": False,  # DEC-007: negrito herdado nas linhas de dados é ruído
    "row_height_mode": "uniform",  # DEC-010 §4: "min_autofit" = max(row_height_pt, AutoFit)
    "row_height_estimate": None,   # estimador offline do AutoFit (sem Excel)
}
ROW_HEIGHT_MODES = frozenset({"uniform", "min_autofit"})
_HEIGHT_TOLERANCE_CM = 0.005


class Geometry(Protocol):
    width_pt: float
    header_height_pt: float


class EmfRenderer(Protocol):
    def measure(self, xlsx_path: Path | str, sheet: str, columns: str = ...,
                header_rows: tuple[int, int] = ...) -> Geometry: ...

    def render_slices(self, xlsx_path: Path | str, sheet: str,
                      selected_physical_rows: Sequence[int], slices: Sequence[range], *,
                      columns: str = ..., header_rows: tuple[int, int] = ...,
                      row_height_pt: float | None = ..., filter_columns: str | None = ...,
                      normalize_data_font: bool = ...,
                      row_heights_pt: Sequence[float] | None = ...) -> list[bytes]: ...

    # Opcional (DEC-010 §4, `row_height_mode: min_autofit`); sem ele, ou devolvendo None, vale o
    # estimador offline:
    #   measure_row_heights(xlsx_path, sheet, selected_physical_rows, *, columns,
    #                       min_height_pt, normalize_data_font) -> list[float] | None


def _render_params(model_cfg: dict[str, Any], component_id: str) -> dict[str, Any]:
    """`render_params` do componente no G2_REPORT_MODEL (modelo inteiro, componente ou params)."""
    if "components" in model_cfg:
        comp = next((c for c in model_cfg["components"] or []
                     if c.get("component_id") == component_id), None)
        if comp is None:
            raise KeyError(f"componente {component_id} ausente do modelo")
        return dict(comp.get("render_params") or {})
    if "render_params" in model_cfg:
        return dict(model_cfg["render_params"] or {})
    if "control_of_products" in model_cfg or "render" in model_cfg:   # forma antiga
        block = model_cfg.get("control_of_products", model_cfg)
        params = dict(block.get("render") or {})
        if "width_cm" in block:
            params["width_cm"] = block["width_cm"]
        return params
    return dict(model_cfg)


def resolve_config(model_cfg: dict[str, Any],
                   component_id: str = DEFAULT_COMPONENT_ID) -> dict[str, Any]:
    """Junta `render_params` do componente (`config/g2_report_model.yaml`) com os defaults."""
    params = _render_params(model_cfg or {}, component_id)
    render = {**DEFAULT_RENDER, **{k: v for k, v in params.items() if k != "width_cm"}}
    render["header_rows"] = tuple(int(v) for v in render["header_rows"])
    if len(render["header_rows"]) != 2:
        raise ValueError(f"{component_id}.render_params.header_rows deve ser [primeira, última]")
    render["width_cm"] = float(params.get("width_cm", DEFAULT_WIDTH_CM))
    if render["row_height_mode"] not in ROW_HEIGHT_MODES:
        raise ValueError(f"{component_id}.render_params.row_height_mode deve ser um de "
                         f"{sorted(ROW_HEIGHT_MODES)}: {render['row_height_mode']!r}")
    return render


# Campos de MasterListRow aceitos em `row_height_estimate.chars_per_line`.
_ESTIMATE_FIELDS = ("document", "manifestation", "description", "venture", "delivery_status")


def estimate_row_heights(rows: Sequence[MasterListRow], cfg: dict[str, Any]) -> list[float]:
    """Alturas offline (sem Excel) pelo nº de linhas do texto (DEC-010 §4).

    `render_params.row_height_estimate`: `line_height_pt` (altura de uma linha de texto) e
    `chars_per_line` ({campo de MasterListRow: caracteres por linha} das colunas com quebra
    automática). Altura = max(`row_height_pt`, `line_height_pt` × maior nº de linhas)."""
    params = cfg.get("row_height_estimate") or {}
    min_pt = float(cfg["row_height_pt"])
    cpl = {str(k): int(v) for k, v in (params.get("chars_per_line") or {}).items()}
    unknown = sorted(set(cpl) - set(_ESTIMATE_FIELDS))
    if unknown:
        raise ValueError(f"row_height_estimate.chars_per_line com campo desconhecido: {unknown}")
    if not cpl:
        return [min_pt] * len(rows)
    line_pt = float(params.get("line_height_pt") or min_pt / 2)
    return [estimate_row_height_pt({f: getattr(r, f) for f in cpl}, cpl, line_pt, min_pt)
            for r in rows]


def row_heights(rows: Sequence[MasterListRow], xlsx_path: Path | str, cfg: dict[str, Any],
                renderer: Any) -> tuple[list[float] | None, str]:
    """(alturas por linha, origem) conforme `render_params.row_height_mode` (DEC-010 §4).

    `uniform` -> (None, "uniform"); `min_autofit` -> medidas pelo renderizador
    (`measure_row_heights`, Excel COM: "excel_autofit") ou, sem medição, pelo estimador
    ("estimate"). Nunca abaixo de `row_height_pt`."""
    if cfg["row_height_mode"] != "min_autofit":
        return None, "uniform"
    min_pt = float(cfg["row_height_pt"])
    measure = getattr(renderer, "measure_row_heights", None)
    if callable(measure):
        measured = measure(xlsx_path, cfg["sheet"], [r.physical_row for r in rows],
                           columns=cfg["columns"], min_height_pt=min_pt,
                           normalize_data_font=bool(cfg["normalize_data_font"]))
        if measured is not None:
            heights = [max(min_pt, float(h)) for h in measured]
            if len(heights) != len(rows):
                raise RuntimeError(f"renderizador mediu {len(heights)} alturas para "
                                   f"{len(rows)} linhas")
            return heights, "excel_autofit"
    return estimate_row_heights(rows, cfg), "estimate"


def first_slice_avail_cm(cfg: dict[str, Any], header_pt: float, width_pt: float,
                         first_page_free_cm: float | None,
                         lead_block_cm: float = 0.0,
                         row_heights_pt: Sequence[float] | None = None,
                         ) -> tuple[float | None, str | None]:
    """Altura do 1º recorte e onde ele fica (DEC-010 §3, `render_params.first_slice_*`).

    - `same_page`: o espaço livre abaixo da frase de chamada comporta ao menos
      `first_slice_min_rows` linhas -> o 1º recorte usa esse espaço;
    - `next_page`: não comporta -> o 1º recorte desce com a frase (keep-with-next) e tem a
      altura útil menos o bloco da frase (`lead_block_cm`).
    Sem medição (`first_page_free_cm` None) ou com `first_slice_fill` desligado: (None, None).
    `row_heights_pt`: alturas reais das linhas (DEC-010 §4); as primeiras decidem se cabem.
    """
    if first_page_free_cm is None or not cfg.get("first_slice_fill"):
        return None, None
    row_pt = float(cfg["row_height_pt"])
    width_cm = float(cfg["width_cm"])
    fit = rows_that_fit(row_pt, header_pt, first_page_free_cm, width_cm, source_width_pt=width_pt,
                        row_heights_pt=row_heights_pt)
    if fit >= int(cfg["first_slice_min_rows"]):
        return first_page_free_cm, "same_page"
    return float(cfg["avail_height_cm"]) - max(0.0, lead_block_cm), "next_page"


def build_product_control(paragraph_factory: Callable[[], Any], rows: Sequence[MasterListRow],
                          xlsx_path: Path | str, model_cfg: dict[str, Any],
                          renderer: EmfRenderer, *,
                          component_id: str = DEFAULT_COMPONENT_ID,
                          first_page_free_cm: float | None = None,
                          lead_block_cm: float = 0.0) -> ComponentResult:
    """Pagina as linhas, gera um EMF por recorte e insere cada um num parágrafo novo.

    `paragraph_factory()` devolve o parágrafo (python-docx) que recebe o EMF do recorte; é
    chamado uma vez por recorte, na ordem. Sem linhas, devolve SKIPPED (a frase de ausência é
    do produto, componente `NO_ACTIVITY_SENTENCE` do modelo).

    `first_page_free_cm`/`lead_block_cm`: espaço livre abaixo da frase de chamada e altura da
    frase (com o espaçamento), medidos no PDF da passada anterior (`render.pdf_layout`); ver
    `first_slice_avail_cm`.
    """
    cfg = resolve_config(model_cfg)
    ordered = sorted(rows, key=lambda r: r.physical_row)          # selection.order
    physical = [r.physical_row for r in ordered]
    if len(set(physical)) != len(physical):
        raise ValueError("linhas físicas repetidas na seleção do Controle de Produtos")
    if not ordered:
        return ComponentResult(component_id, status="SKIPPED", detail="bloco sem linhas",
                               facts={"rows": 0, "slices": [], "documents": []})

    width_pt = cfg.get("source_width_pt")
    header_pt = cfg.get("header_height_pt")
    if width_pt is None or header_pt is None:
        geometry = renderer.measure(xlsx_path, cfg["sheet"], cfg["columns"], cfg["header_rows"])
        width_pt = geometry.width_pt if width_pt is None else width_pt
        header_pt = geometry.header_height_pt if header_pt is None else header_pt
    width_pt, header_pt = float(width_pt), float(header_pt)
    row_pt = float(cfg["row_height_pt"])
    avail = float(cfg["avail_height_cm"])
    width_cm = cfg["width_cm"]
    plan: dict[str, Any] = {}
    heights_pt, heights_source = row_heights(ordered, xlsx_path, cfg, renderer)
    height_kwargs: dict[str, Any] = {}
    if heights_pt is not None:
        height_kwargs["row_heights_pt"] = heights_pt

    def _rows_pt(part: range) -> list[float] | None:
        return None if heights_pt is None else [heights_pt[i] for i in part]

    def _render(header: float) -> tuple[list[range], list[bytes], list[float], list[float]]:
        first_avail, mode = first_slice_avail_cm(cfg, header, width_pt, first_page_free_cm,
                                                 lead_block_cm, row_heights_pt=heights_pt)
        plan.clear()
        if mode is not None:
            plan.update({"mode": mode, "avail_cm": round(float(first_avail), 3),
                         "free_cm": round(float(first_page_free_cm), 3)})
        slices = paginate(len(ordered), row_pt, header, avail, width_cm, source_width_pt=width_pt,
                          balance=bool(cfg["balance"]), first_avail_height_cm=first_avail,
                          min_rows=int(cfg["first_slice_min_rows"]), row_heights_pt=heights_pt)
        emfs = renderer.render_slices(
            xlsx_path, cfg["sheet"], physical, slices, columns=cfg["columns"],
            header_rows=cfg["header_rows"], row_height_pt=row_pt,
            filter_columns=cfg["filter_columns"],
            normalize_data_font=bool(cfg["normalize_data_font"]), **height_kwargs)
        if len(emfs) != len(slices):
            raise RuntimeError(f"renderizador devolveu {len(emfs)} EMF para {len(slices)} recortes")
        heights = [emf_display_height_cm(e, width_cm, cfg["aspect"]) for e in emfs]
        limits = [avail] * len(slices)
        if first_avail is not None:
            limits[0] = min(avail, float(first_avail))
        return slices, emfs, heights, limits

    def _overflow(heights: list[float], limits: list[float]) -> float:
        return max(h - lim for h, lim in zip(heights, limits, strict=True))

    slices, emfs, heights, limits = _render(header_pt)
    overflow = _overflow(heights, limits)
    if overflow > _HEIGHT_TOLERANCE_CM:
        # a medição em pt não capturou bordas/arredondamento do desenho: uma correção só,
        # somando ao cabeçalho o maior desvio entre altura real e prevista.
        drift_cm = max(h - slice_height_cm(len(s), row_pt, header_pt, width_cm,
                                           source_width_pt=width_pt, row_heights_pt=_rows_pt(s))
                       for s, h in zip(slices, heights, strict=True))
        header_pt += max(drift_cm, overflow) * width_pt / width_cm
        slices, emfs, heights, limits = _render(header_pt)
        overflow = _overflow(heights, limits)

    for k, emf in enumerate(emfs, start=1):
        add_emf_picture(paragraph_factory(), emf, width_cm, aspect=cfg["aspect"],
                        name=f"{component_id.lower()}_{k:02d}.emf")

    facts = {
        "rows": len(ordered),
        "slices": [len(s) for s in slices],
        "documents": [r.document for r in ordered],
        "physical_rows": [[physical[s[0]], physical[s[-1]]] for s in slices],
        "heights_cm": [round(h, 3) for h in heights],
        "width_cm": width_cm,
        "normalize_data_font": bool(cfg["normalize_data_font"]),
        "row_height_mode": cfg["row_height_mode"],
        "row_heights_source": heights_source,
    }
    if heights_pt is not None:
        # só as linhas acima do mínimo (DEC-010 §4): documento -> altura em pt
        facts["tall_rows"] = {ordered[i].document: round(h, 2)
                              for i, h in enumerate(heights_pt) if h > row_pt + 1e-6}
    if plan:
        facts["first_slice"] = dict(plan)
    status, detail = "OK", f"{len(ordered)} linhas em {len(slices)} recorte(s)"
    if overflow > _HEIGHT_TOLERANCE_CM:
        status = "FAILED"
        detail += f"; recorte excede a altura útil em {overflow:.3f} cm"
    return ComponentResult(component_id, status=status, detail=detail, facts=facts)
