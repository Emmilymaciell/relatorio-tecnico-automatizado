"""PDFs SINTÉTICOS com a anatomia do Relatório G2, gerados em memória pelo PyMuPDF.

Nada aqui vem de documento corporativo: códigos, rodovias e textos são inventados no formato
do relatório (WAVE1_FINDINGS), só para exercitar extração e comparador. Fontes Base-14
(Helvetica / Helvetica-Bold), por isso os textos evitam caracteres fora do Latin-1 (travessão,
marcador): "-" no lugar de "–".

Uso típico nos testes:

    pages = synthetic_pages()                 # referência coerente
    pages[4].orientation = "portrait"         # mutação = regressão que o comparador deve pegar
    facts = facts_of(pages, tmp_path / "g.pdf")
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

PT_PER_CM = 72 / 2.54
A4 = (595.28, 841.89)
HEADER = "PROGRAMA | CONSÓRCIO ESTRUTURADOR DO PROGRAMA"
FOOTER = "-CONFIDENCIAL-"
LABELS = ["Documento", "Manifestação", "Descrição", "Empreendimento", "Data Entrega",
          "Status Entrega"]
COLUMNS_X = [60, 115, 205, 375, 440, 500]

ROWS_21 = [("PA-901.1", "RD-104"), ("NT-902.1", "Geral"), ("NT-903.1", "RD-102A")]
ROWS_24 = [("RO-545.1", "RD-103"), ("RO-546.1", "RD-103"), ("BM-007.1", "RD-104"),
           ("RI-509.1", "RD-101")]

MONTHS = {"2026-07": ("Julho/2026", "11 de Agosto de 2026", "12 de Agosto de 2026"),
          "2026-08": ("Agosto/2026", "08 de Setembro de 2026", "09 de Setembro de 2026")}
EXTENSO = {7: "sete", 8: "oito", 9: "nove", 10: "dez", 11: "onze"}


@dataclass
class Item:
    kind: str  # heading | text | table | image | boxed
    text: str = ""
    # Linha do Controle de Produtos: (código, rodovia) com as demais células padrão, ou as seis
    # células (código, manifestação, descrição, rodovia, data, status); "\n" na descrição quebra
    # a célula em duas linhas.
    rows: list[tuple[str, ...]] = field(default_factory=list)
    labels: list[str] = field(default_factory=lambda: list(LABELS))
    size_cm: tuple[float, float] = (10.0, 5.0)
    # Painel (figura raster com conteúdo): selo no canto inferior esquerdo e leiaute por semente;
    # `blank` = painel todo branco.
    badge: str | None = None
    seed: int = 0
    blank: bool = False
    # v3: seletor de rodovia (4 abas no topo à esquerda; `tab` = aba destacada, 1..4) e um
    # numeral de KPI na região `kpi_pendentes` do painel de índices (raster_regions.yaml).
    tab: int | None = None
    kpi: str | None = None


@dataclass
class Page:
    items: list[Item] = field(default_factory=list)
    orientation: str = "portrait"
    cover: bool = False
    header: str = HEADER
    footer: str = FOOTER
    numbered: bool = True


def heading(text: str) -> Item:
    return Item("heading", text)


def text(value: str) -> Item:
    return Item("text", value)


def table(rows: list[tuple[str, str]], labels: list[str] | None = None) -> Item:
    return Item("table", rows=list(rows), labels=list(labels or LABELS))


def image(width_cm: float, height_cm: float) -> Item:
    return Item("image", size_cm=(width_cm, height_cm))


def panel(badge: str | None, *, seed: int = 0, width_cm: float = 16.0, height_cm: float = 9.0,
          blank: bool = False, tab: int | None = None, kpi: str | None = None) -> Item:
    """Painel raster no estilo dos quadros do 2.2.2: blocos de leiaute (pela semente) e o selo
    da rodovia no canto inferior esquerdo; opcionalmente o seletor de abas e um KPI."""
    return Item("image", size_cm=(width_cm, height_cm), badge=badge, seed=seed, blank=blank,
                tab=tab, kpi=kpi)


def row(code: str, kind: str = "Parecer", description: str = "Descrição sintética do documento",
        road: str = "RD-101", date: str = "01/08/2026", status: str = "Entregue") -> tuple:
    return (code, kind, description, road, date, status)


def boxed(value: str) -> Item:
    """Texto negrito 13 pt dentro de um quadro vetorial (cabeçalho de diagrama em EMF)."""
    return Item("boxed", value)


def synthetic_pages(
    *,
    number: int = 14,
    month: str = "2026-08",
    presentation_number: int | None = None,
    closing_number: int | None = None,
    rows_21: list[tuple[str, str]] | None = None,
    rows_24: list[tuple[str, str]] | None = None,
    annex_rows: list[tuple[str, str]] | None = None,
    declared_pages: int | None = None,
    declared_annexes: int | None = None,
    signatory: str | None = None,
) -> list[Page]:
    """Relatório sintético coerente de 9 páginas (capa, sumário, 1, 2, paisagem, 2.1 tabela,
    2.4, Encerramento, ANEXOS). `signatory`: nome (inventado) assinando o Encerramento."""
    label, cover_date, signature = MONTHS[month]
    r21 = list(ROWS_21 if rows_21 is None else rows_21)
    r24 = list(ROWS_24 if rows_24 is None else rows_24)
    annex = list(r21 + r24 if annex_rows is None else annex_rows)
    n_pages = 9 if declared_pages is None else declared_pages
    n_annex = len(annex) if declared_annexes is None else declared_annexes
    p_number = number if presentation_number is None else presentation_number
    c_number = number if closing_number is None else closing_number
    return [
        Page(cover=True, items=[
            image(21.0, 29.7),
            heading("RELATÓRIO PROGRAMA"),
            text(f"Relatório Mensal N° {number}"),
            text(cover_date),
        ]),
        Page(items=[heading("SUMÁRIO"), text("1 APRESENTAÇÃO ........ 3"),
                    text("2 GESTÃO DE ENGENHARIA E SOCIOAMBIENTAL ........ 4")]),
        Page(items=[
            heading("1 APRESENTAÇÃO"),
            text("O Consórcio Estruturador apresenta ao Parceiro o Relatório Mensal "
                 f"N° {p_number}, referente ao período de {label}, em conformidade ao "
                 "Contrato N° 00/0000-PARC."),
            image(16.0, 5.0),
        ]),
        Page(items=[
            heading("2 GESTÃO DE ENGENHARIA E SOCIOAMBIENTAL"),
            heading("2.1 Produto 2.1 - Relatório de Coordenação Setorial dos Serviços de"),
            heading("Engenharia"),
            heading("2.1.1 Descrição das atividades atribuídas"),
            text("Reuniões de alinhamento técnico com as executoras da RD-101 e da RD-104."),
            heading("2.1.2 Produtos desenvolvidos no período"),
            text("A relação dos produtos desenvolvidos no período se encontra a seguir."),
        ]),
        Page(orientation="landscape", items=[image(25.0, 12.0)]),
        Page(items=[table(r21)]),
        Page(items=[
            heading("2.4 Produto 2.4 - Relatório de Gerenciamento Técnico de Obra"),
            heading("2.4.2 Produtos desenvolvidos no período"),
            text("Relatórios semanais de cada obra: RD-103: RO-545.1 a RO-548.1; "
                 "RD-101: RO-544.1 a RO-547.1."),
            table(r24),
        ]),
        Page(items=[
            heading("ENCERRAMENTO"),
            text(f"O Relatório Mensal N° {c_number}, referente à consolidação e à apresentação "
                 f"das atividades desenvolvidas durante o mês de {label}, no âmbito do "
                 f"Contrato N°00/0000-PARC, apresenta-se constituído de {n_pages} "
                 f"({EXTENSO.get(n_pages, 'nove')}) páginas e {n_annex} "
                 f"({EXTENSO.get(n_annex, 'sete')}) anexos e adotou metodologia "
                 "tecnicamente adequada."),
            text(f"Capital, {signature}"),
            *([text(f"Eng° {signatory}"),
               text("Programa - Consórcio Estruturador do Programa")]
              if signatory else []),
        ]),
        Page(items=[heading("ANEXOS"), table(annex)]),
    ]


# --------------------------------------------------------------------------- render


def _wrap(value: str, width: int = 88) -> list[str]:
    lines, current = [], ""
    for word in value.split():
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def _render_table(page, y: float, item: Item) -> float:
    top = y
    page.insert_text((60, y + 10), "Programa | Controle de Produtos", fontname="hebo", fontsize=9)
    y += 22
    for x, label in zip(COLUMNS_X, item.labels, strict=False):
        page.insert_text((x, y + 8), label, fontname="hebo", fontsize=7)
    y += 13
    for spec in item.rows:
        if len(spec) == 2:
            values = [spec[0], "Parecer", "Descrição sintética do documento", spec[1],
                      "01/08/2026", "Entregue"]
        else:
            values = list(spec)
        for x, value in zip(COLUMNS_X, values, strict=True):
            lines = value.split("\n")
            if len(lines) == 1:
                page.insert_text((x, y + 8), value, fontname="helv", fontsize=7)
            else:  # célula quebrada: duas linhas em torno da linha do código
                page.insert_text((x, y + 4), lines[0], fontname="helv", fontsize=7)
                page.insert_text((x, y + 12), lines[1], fontname="helv", fontsize=7)
        y += 13 if all("\n" not in v for v in values) else 17
    # Grade vetorial (o EMF do Excel chega ao PDF como desenho + texto).
    page.draw_rect(pymupdf.Rect(57, top, 555, y + 2), color=(0, 0, 0), width=0.5)
    for line_y in range(int(top + 22), int(y), 13):
        page.draw_line((57, line_y), (555, line_y), color=(0.5, 0.5, 0.5), width=0.3)
    return y + 12


def _panel_pixmap(item: Item, w: float, h: float):
    """Renderiza o painel numa página auxiliar e devolve o pixmap (o PDF final só tem a
    imagem, como um print de painel Power BI)."""
    aux = pymupdf.open()
    sheet = aux.new_page(width=w, height=h)
    if not item.blank:
        state = item.seed * 7919 + 17
        for n in range(14):  # leiaute pseudoaleatório determinístico pela semente
            state = (state * 1103515245 + 12345) % (2 ** 31)
            bx = 0.2 * w + (state % 1000) / 1000 * 0.7 * w
            by = 0.05 * h + ((state // 1000) % 1000) / 1000 * 0.75 * h
            shade = 0.25 + (n % 4) * 0.15
            sheet.draw_rect(pymupdf.Rect(bx, by, min(w - 2, bx + 0.12 * w), by + 0.06 * h),
                            color=None, fill=(shade, shade, 0.6))
        sheet.draw_rect(pymupdf.Rect(2, 2, w - 2, h - 2), color=(0.1, 0.1, 0.4), width=1.5)
        if item.tab is not None:  # 4 abas na faixa do seletor (fração da largura)
            step = 0.235 * w / 4
            for n in range(4):
                x0 = 0.011 * w + n * step
                shade = 0.2 if n + 1 == item.tab else 0.75
                sheet.draw_rect(pymupdf.Rect(x0, 0.012 * w, x0 + step - 2, 0.036 * w),
                                color=None, fill=(shade, shade, shade))
        if item.kpi is not None:  # região kpi_pendentes do painel de índices
            sheet.draw_rect(pymupdf.Rect(0.77 * w, 0.075 * w, 0.89 * w, 0.14 * w), color=None,
                            fill=(1, 1, 1))
            sheet.insert_text((0.80 * w, 0.128 * w), item.kpi, fontname="hebo",
                              fontsize=0.045 * w, color=(0, 0, 0))
        if item.badge:
            sheet.insert_text((0.03 * w, 0.972 * h), item.badge, fontname="hebo",
                              fontsize=0.06 * h, color=(0.05, 0.1, 0.4))
    pix = sheet.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
    aux.close()
    return pix


def _render_image(page, y: float, item: Item, x: float = 57.0) -> float:
    w, h = item.size_cm[0] * PT_PER_CM, item.size_cm[1] * PT_PER_CM
    if item.badge is not None or item.blank or item.tab is not None or item.kpi is not None:
        pix = _panel_pixmap(item, w, h)
    else:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 20), False)
        pix.clear_with(200)
    page.insert_image(pymupdf.Rect(x, y, x + w, y + h), pixmap=pix, keep_proportion=False)
    return y + h + 10


def render(pages: list[Page]) -> bytes:
    doc = pymupdf.open()
    for index, spec in enumerate(pages, start=1):
        width, height = A4 if spec.orientation == "portrait" else (A4[1], A4[0])
        page = doc.new_page(width=width, height=height)
        if spec.cover:
            y = 0.0
            for item in spec.items:
                if item.kind == "image":
                    _render_image(page, 0, item, x=0)
                    y = 500
                elif item.kind == "heading":
                    page.insert_text((94, y + 20), item.text, fontname="hebo", fontsize=20)
                    y += 40
                else:
                    page.insert_text((94, y + 16), item.text, fontname="helv", fontsize=16)
                    y += 36
            continue
        if spec.header:
            page.insert_text((55, 42), spec.header, fontname="helv", fontsize=11)
        if spec.footer:
            page.insert_text((60, height - 20), spec.footer, fontname="helv", fontsize=11)
        if spec.numbered:
            page.insert_text((width - 60, height - 20), str(index), fontname="helv", fontsize=11)
        y = 62.0
        for item in spec.items:
            if item.kind == "heading":
                page.insert_text((57, y + 13), item.text, fontname="hebo", fontsize=13)
                y += 20
            elif item.kind == "text":
                y += 6
                for line in _wrap(item.text):
                    page.insert_text((57, y + 11), line, fontname="helv", fontsize=11)
                    y += 16
            elif item.kind == "table":
                y = _render_table(page, y + 6, item)
            elif item.kind == "image":
                y = _render_image(page, y + 6, item)
            elif item.kind == "boxed":
                top = y + 6
                page.draw_rect(pymupdf.Rect(57, top, 555, top + 60), color=(0, 0, 0), width=0.5)
                page.draw_line((57, top + 30), (555, top + 30), color=(0, 0, 0), width=0.3)
                page.insert_text((70, top + 20), item.text, fontname="hebo", fontsize=13)
                y = top + 70
    data = doc.tobytes()
    doc.close()
    return data


def write_pdf(pages: list[Page], path: Path) -> Path:
    path.write_bytes(render(pages))
    return path


def facts_of(pages: list[Page], path: Path) -> dict:
    from prog_g2_report.qa.extract import extract_facts

    return extract_facts(write_pdf(pages, path))


def clone(pages: list[Page]) -> list[Page]:
    return copy.deepcopy(pages)


def approve_all(reference: dict, generated: dict, justification: dict, *,
                report_number: int = 14, allowances=None):
    """Conjunto CONGELADO de hunks aprovados com TODOS os hunks do diff atual, cada um com a
    `justification` dada (anomalia/DEC). Para os testes sintéticos que exercitam outra
    verificação: o texto diferente sai ALLOWED pelo caminho real (hunk exato), não por atalho."""
    from prog_g2_report.qa.compare import (
        AllowanceSet,
        HunkSet,
        compare,
        draft_hunks,
        parse_approved_hunks,
    )

    report = compare(reference, generated, allowances or AllowanceSet.empty(),
                     report_number=report_number, approved_hunks=HunkSet.empty(report_number))
    draft = draft_hunks(report)
    for hunk in draft["hunks"]:
        hunk["reference"] = dict(justification)
    draft.update(status="FROZEN", version="test", generated_from=None)
    return parse_approved_hunks(draft)
