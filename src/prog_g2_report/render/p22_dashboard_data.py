"""Dados do quadro visual por rodovia do produto 2.2 (função pura, sem desenho).

Spec: `config/data_rules/p22_highway_block.yaml` → `quadro_visual` (classe RECONSTRUCTED_VISUAL,
DEC-009: reconstruir a partir do dado). Componente `P2.2_ROAD_DASHBOARDS` do modelo. O desenho é
do renderizador visual (builder V); este módulo só entrega os valores.

Formato devolvido por `road_dashboard_data` (dict serializável em JSON)::

    {
      "highway": "RD-102A",                 # rodovia normalizada (quadro_visual.header.road_label)
      "updated_at": "07/09/2026",           # 'Atualizado em' = reference_date em dd/mm/aaaa
      "reference_date": "2026-09-07",
      "columns": ["Disciplina", "Previsão", "Entrega", "REV", "1º Nível", "2º Nível",
                  "Entrega da Revisão"],     # quadro_visual.columns[].header
      "rows": [[<7 strings>], ...],         # uma lista de 7 valores por disciplina
      "donut_title": "Entrega",             # quadro_visual.donut.title
      "donut": {"Analisada": 15, "Atrasado": 3, "Em análise": 2},
      "groups": ["Fase de Estudos", ...],   # slicer GRUPO, ordem alfabética (decorativo)
      "facts": {...}                        # contagens e chaves usadas, para o QA
    }

Regras (chave da spec):

- filtro: rodovia normalizada, sem `exclusions.quadro.by_prefix_of_discipline`, todas as linhas;
- ordem das linhas: Ordem Disciplina numérica (`quadro_visual.row_order`), não a ordem do texto;
- células (`quadro_visual.columns`): Previsão e Entrega em dd/mm/aa; REV inteiro, vazio se não
  recebida; 1º Nível capitalizado ('sim' → 'Sim'); 2º Nível em caixa de frase ('Aprovado com
  Ressalvas' → 'Aprovado com ressalvas'); Entrega da Revisão: texto como digitado ou data em
  dd/mm/aa (`display_proposed`; o M/D/AAAA histórico é anomalia `P2.2_QUADRO_DATA_MDY`);
- rosca: contagem pela SITUAÇÃO recalculada com `reference_date` (`quadro_visual.donut.measure`),
  categorias de `categories_legend_order` sempre presentes (0 se vazias) e outras situações
  acrescentadas em ordem alfabética (`categories_note`).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from prog_g2_report.render.p22_text import P22Rules, coerce_rules, is_excluded
from prog_g2_report.sources.projects import ProjectRow, ProjectsWorkbook, normalize_road


def _short_date(value: date | None) -> str:
    return value.strftime("%d/%m/%y") if value else ""


def sentence_case(value: str) -> str:
    """Primeira letra maiúscula, o resto minúsculo ('SIm' → 'Sim'; 'Aprovado com Ressalvas' →
    'Aprovado com ressalvas'): a caixa canônica do quadro (`quadro_visual.columns`)."""
    text = " ".join(str(value or "").split())
    return text[:1].upper() + text[1:].lower() if text else ""


def dashboard_row(row: ProjectRow) -> list[str]:
    """As 7 células de uma disciplina, na ordem de `quadro_visual.columns`."""
    delivery = row.revision_delivery
    delivery_text = _short_date(delivery) if isinstance(delivery, date) else delivery or ""
    revision = "" if row.received_date is None or row.revision is None else str(row.revision)
    return [
        row.discipline,
        _short_date(row.forecast_date),
        _short_date(row.received_date),
        revision,
        sentence_case(row.accepted_raw),
        sentence_case(row.evaluation_raw),
        delivery_text,
    ]


def dashboard_rows(
    projects: ProjectsWorkbook | Iterable[ProjectRow], highway: str, rules: P22Rules
) -> list[ProjectRow]:
    rows = projects.projects if isinstance(projects, ProjectsWorkbook) else tuple(projects)
    road = normalize_road(highway)
    chosen = [r for r in rows
              if r.road == road and not is_excluded(r.discipline, rules.dashboard_exclusions)]
    return sorted(chosen, key=lambda r: (r.order_key, r.physical_row))


def donut_counts(
    rows: Iterable[ProjectRow], reference_date: date, rules: P22Rules
) -> dict[str, int]:
    counts = Counter(r.situation(reference_date) for r in rows)
    out = {category: counts.get(category, 0) for category in rules.donut_categories}
    for category in sorted(c for c in counts if c not in out):
        out[category] = counts[category]
    return out


def road_dashboard_data(
    projects: ProjectsWorkbook | Iterable[ProjectRow],
    highway: str,
    reference_date: date,
    rules: P22Rules | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Dados do quadro de uma rodovia (formato no docstring do módulo)."""
    resolved = coerce_rules(rules)
    rows = dashboard_rows(projects, highway, resolved)
    donut = donut_counts(rows, reference_date, resolved)
    return {
        "highway": normalize_road(highway),
        "updated_at": reference_date.strftime("%d/%m/%Y"),
        "reference_date": reference_date.isoformat(),
        "columns": list(resolved.dashboard_columns),
        "rows": [dashboard_row(r) for r in rows],
        "donut_title": resolved.donut_title,
        "donut": donut,
        "groups": sorted({r.group for r in rows}),
        "facts": {
            "row_count": len(rows),
            "donut_total": sum(donut.values()),
            "excluded_prefixes": list(resolved.dashboard_exclusions),
            "rule_source": "config/data_rules/p22_highway_block.yaml#quadro_visual",
        },
    }
