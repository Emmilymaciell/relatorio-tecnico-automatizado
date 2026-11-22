"""Fixtures SINTÉTICAS da planilha de projetos (nenhum dado corporativo).

Cabeçalhos com a mesma grafia da planilha real (24 colunas A:X), valores inventados.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

PROJECTS_HEADER = [
    "Ordem Disciplina", "Obra", "GRUPO", "Disciplina ", "Previsão de Entrega", "HOJE",
    "Data de Recebimento", "Status (PRAZO)", "Status (SITUAÇÃO)", "GED Nº", "REVISÃO",
    "Início da Análise - GED", "Devolutiva - GED", "Documento de Recebimento de GED",
    "Disciplina ACEITA?", "Início da Análise - Aprovação", "Devolutiva - Aprovação",
    "Documento de Análise de 2º Nível", "Status (AVALIAÇÃO)",
    "Status (SITUAÇÃO) - Coluna Auxiliar", "Status (AVALIAÇÃO) - Coluna Auxiliar",
    "LINHA_GED_ATUAL", "Entrega da Revisão", "Resumo Disciplina",
]
GED_HEADER = [
    "GED Nº", "RODOVIA", "CODIFICAÇÃO", "TIPO DE DOCUMENTO", "FASE E/OU EVENTO", "DISCIPLINA",
    "REVISÃO", "Data de Recebimento", "Início da Análise - GED",
]

EST = "Fase de Estudos"
PRI = "Projeto Executivo Viário Principal"
SEC = "Projeto Executivo Viário Secundário"
OAE = "OAE"


def project(
    order: str, road: str, group: str, discipline: str, *,
    forecast: Any = date(2026, 5, 1), received: Any = None, revision: Any = None,
    analysis: Any = None, accepted: Any = None, evaluation: Any = None,
    revision_delivery: Any = None, situation_cached: str = "cache", summary: str = "",
) -> list[Any]:
    """Uma linha da aba Projetos (colunas A:X)."""
    row: list[Any] = [None] * len(PROJECTS_HEADER)
    row[0], row[1], row[2], row[3] = order, road, group, discipline
    row[4], row[5], row[6] = forecast, datetime(2000, 1, 1), received
    row[7], row[8] = "cache de TODAY()", situation_cached
    row[10], row[11] = revision, analysis
    row[14], row[18], row[22], row[23] = accepted, evaluation, revision_delivery, summary
    return row


def approved(order, road, group, discipline, **kw) -> list[Any]:
    base = {"received": date(2026, 3, 1), "revision": 2, "analysis": date(2026, 3, 2),
            "accepted": "Sim", "evaluation": "Aprovado", "revision_delivery": "Concluído"}
    base.update(kw)
    return project(order, road, group, discipline, **base)


def in_analysis(order, road, group, discipline, **kw) -> list[Any]:
    base = {"received": date(2026, 3, 1), "revision": 1, "analysis": date(2026, 3, 2),
            "accepted": "Sim", "revision_delivery": "Em análise"}
    base.update(kw)
    return project(order, road, group, discipline, **base)


def rejected(order, road, group, discipline, delivery, **kw) -> list[Any]:
    base = {"received": date(2026, 3, 1), "revision": 1, "analysis": date(2026, 3, 2),
            "accepted": "Sim", "evaluation": "Reprovado", "revision_delivery": delivery}
    base.update(kw)
    return project(order, road, group, discipline, **base)


def late(order, road, group, discipline, **kw) -> list[Any]:
    base = {"forecast": date(2026, 5, 1)}
    base.update(kw)
    return project(order, road, group, discipline, **base)


def ged(road: str, group: str, discipline: str, received: Any) -> list[Any]:
    return ["001/2026", road, "COD", "Relatório Técnico", group, discipline, "0", received, None]


def panel(*labels: str) -> list[list[Any]]:
    """Aba Painel de Controle: título, linha de rodovias (com 'DISCIPLINA'), subtítulos."""
    road_row: list[Any] = [None, "ID", "FASE", "DISCIPLINA", "PREDECESSORES\nMÍNIMOS"]
    for label in labels:
        road_row += [label, None, None]
    return [
        [None, "Programa | Análise e Status de Projetos"],
        [],
        road_row,
        [None, None, None, None, None] + ["RESPONSÁVEL", "AÇÃO", "STATUS"] * len(labels),
    ]


def sheet(*rows: list[Any]) -> list[list[Any]]:
    return [list(PROJECTS_HEADER), *rows]


def ged_sheet(*rows: list[Any]) -> list[list[Any]]:
    return [list(GED_HEADER), *rows]
