"""Visuais reconstruídos (RECONSTRUCTED_VISUAL, DEC-009): PNG determinístico a partir do dado.

    p22_road_dashboard   quadro por rodovia do produto 2.2   (P2.2_ROAD_DASHBOARDS)
    p24_environmental    painéis ambientais do produto 2.4   (P2.4_ENV_INDICES_PANEL,
                                                              P2.4_CONDITIONS_PANELS)

Todas as medidas vêm de `config/g2_render_rules.yaml`; os renderizadores recebem esse YAML
carregado (`rules`) e não leem fonte nem modelo por conta própria. Seleção, filtro e ordenação
das linhas são de outro módulo: aqui só se desenha.
"""

from prog_g2_report.render.visuals._canvas import load_render_rules, render_options

__all__ = ["load_render_rules", "render_options"]
