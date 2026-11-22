"""Posição de parágrafos no PDF de uma passada do Word (para a paginação da passada seguinte).

O builder exporta o PDF em passadas (`builder.assemble`). Para o 1º recorte do Controle de
Produtos usar o espaço que sobra na página da frase de chamada (DEC-010 §3), é preciso saber
onde essa frase caiu: só o Word sabe, e o PDF da passada anterior é a medida.

`locate_paragraphs` acha cada parágrafo pelo TEXTO e pela ORDEM de ocorrência (o mesmo texto
aparece em vários produtos), comparando sem espaços e em NFKC (o Word justifica, quebra linhas e
pode usar ligaduras). Só conta linhas dentro do corpo da página (`body_top_cm`..`body_bottom_cm`),
fora de cabeçalho e rodapé.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

PT_PER_CM = 72 / 2.54
_SPACE = re.compile(r"\s+")


def normalize_for_match(text: str) -> str:
    """Forma de busca: NFKC, sem espaço nenhum."""
    return _SPACE.sub("", unicodedata.normalize("NFKC", text or ""))


@dataclass(frozen=True)
class ParagraphBox:
    """Onde o parágrafo terminou: página (1-based) e caixa das suas linhas nessa página (cm)."""

    page: int
    top_cm: float          # topo da 1ª linha do parágrafo na página em que ele termina
    bottom_cm: float       # base da última linha
    lines: int             # linhas do parágrafo (todas as páginas)
    line_height_cm: float  # altura média de uma linha

    @property
    def height_cm(self) -> float:
        """Altura do parágrafo como bloco (todas as linhas, mesmo se partido entre páginas)."""
        return max(self.bottom_cm - self.top_cm, self.lines * self.line_height_cm)


def _body_lines(pdf_path: Path, body_top_cm: float, body_bottom_cm: float
                ) -> list[tuple[int, str, float, float]]:
    import pymupdf

    out: list[tuple[int, str, float, float]] = []
    top, bottom = body_top_cm * PT_PER_CM, body_bottom_cm * PT_PER_CM
    with pymupdf.open(str(pdf_path)) as doc:
        for index, page in enumerate(doc, start=1):
            lines = []
            for block in page.get_text("dict")["blocks"]:
                if block.get("type") != 0:
                    continue
                for line in block["lines"]:
                    text = "".join(s["text"] for s in line["spans"])
                    if not text.strip():
                        continue
                    x0, y0, _x1, y1 = line["bbox"]
                    if y1 <= top or y0 >= bottom:
                        continue
                    lines.append((round(y0, 1), x0, text, y0, y1))
            for _ry, _x0, text, y0, y1 in sorted(lines):
                out.append((index, text, y0 / PT_PER_CM, y1 / PT_PER_CM))
    return out


def locate_paragraphs(pdf_path: Path | str, anchors: Sequence[tuple[str, int]], *,
                      body_top_cm: float, body_bottom_cm: float
                      ) -> list[ParagraphBox | None]:
    """Para cada (texto, ordem) devolve a caixa do parágrafo ou None se não achou.

    `ordem` = quantas vezes o mesmo texto aparece ANTES no documento (0 = primeira).
    """
    lines = _body_lines(Path(pdf_path), body_top_cm, body_bottom_cm)
    stream_parts: list[str] = []
    owners: list[int] = []
    for n, (_page, text, _y0, _y1) in enumerate(lines):
        norm = normalize_for_match(text)
        stream_parts.append(norm)
        owners.extend([n] * len(norm))
    stream = "".join(stream_parts)
    out: list[ParagraphBox | None] = []
    for text, ordinal in anchors:
        needle = normalize_for_match(text)
        if not needle:
            out.append(None)
            continue
        start, found = -1, -1
        for _ in range(int(ordinal) + 1):
            found = stream.find(needle, start + 1)
            if found < 0:
                break
            start = found
        if found < 0:
            out.append(None)
            continue
        first, last = owners[found], owners[found + len(needle) - 1]
        span = lines[first:last + 1]
        page = span[-1][0]
        on_page = [ln for ln in span if ln[0] == page]
        heights = [ln[3] - ln[2] for ln in span]
        out.append(ParagraphBox(page=page, top_cm=round(min(ln[2] for ln in on_page), 3),
                                bottom_cm=round(max(ln[3] for ln in on_page), 3),
                                lines=len(span),
                                line_height_cm=round(sum(heights) / len(heights), 3)))
    return out
