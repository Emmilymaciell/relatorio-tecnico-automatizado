"""Paginação do Controle de Produtos em recortes de uma página (DEC-010 §3–4).

Cada recorte é um EMF próprio que repete o título e o cabeçalho da planilha; por isso a altura
de um recorte é `header + soma das alturas das suas linhas`. A largura do recorte no documento é
fixa (`control_of_products.width_cm`), então a escala sai da largura natural do intervalo.

Altura de linha (DEC-010 §4, `CONTROL_OF_PRODUCTS.render_params.row_height_mode`):
- `uniform`: todas as linhas com `row_height_pt` (forma antiga);
- `min_autofit`: cada linha com `max(row_height_pt, AutoFit do Excel)`; as alturas reais vêm do
  chamador em `row_heights_pt` (medidas via COM na 1ª passada ou, offline, pelo estimador
  `estimate_row_height_pt` abaixo).

Todas as grandezas vêm do modelo ou da medição da planilha; os defaults abaixo só documentam o
padrão vigente (Relatório G2 nº 14 — Agosto/2026) e não são usados se o modelo informar:

- `row_height_pt` 27,6 (DEC-010 §4: mínimo; MEDIUM);
- `avail_height_cm` 26,2 = 29,7 − 2,0 − 1,5 (corpo da seção retrato, `page.sections[*]`);
- `width_cm` 17,5 (`control_of_products.width_cm`).

A quebra histórica foi manual (31–34 linhas); a gulosa é padronização (DEC-007), não fato.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

DEFAULT_ROW_HEIGHT_PT = 27.6
DEFAULT_AVAIL_HEIGHT_CM = 26.2
DEFAULT_WIDTH_CM = 17.5
_EPS = 1e-9


def rows_per_slice(row_height_pt: float, header_height_pt: float, avail_height_cm: float,
                   width_cm: float, *, source_width_pt: float) -> int:
    """Máximo de linhas de dados (altura uniforme) por recorte com o cabeçalho repetido."""
    if min(row_height_pt, width_cm, source_width_pt, avail_height_cm) <= 0:
        raise ValueError("alturas e larguras devem ser positivas")
    if header_height_pt < 0:
        raise ValueError("header_height_pt não pode ser negativo")
    scale = width_cm / source_width_pt          # cm no documento por pt da planilha
    capacity = (avail_height_cm - header_height_pt * scale) / (row_height_pt * scale)
    count = math.floor(capacity + _EPS)
    if count < 1:
        raise ValueError(
            f"nem uma linha cabe na página: cabeçalho {header_height_pt * scale:.2f} cm + linha "
            f"{row_height_pt * scale:.2f} cm > {avail_height_cm:.2f} cm úteis")
    return count


def _capacity_pt(header_height_pt: float, avail_height_cm: float, width_cm: float,
                 source_width_pt: float) -> float:
    """Altura disponível para as linhas de dados, em pt da planilha."""
    if min(width_cm, source_width_pt) <= 0:
        raise ValueError("alturas e larguras devem ser positivas")
    if header_height_pt < 0:
        raise ValueError("header_height_pt não pode ser negativo")
    return avail_height_cm * source_width_pt / width_cm - header_height_pt


def _validate_heights(heights: Sequence[float], n_rows: int) -> list[float]:
    out = [float(h) for h in heights]
    if len(out) != n_rows:
        raise ValueError(f"row_heights_pt tem {len(out)} alturas para {n_rows} linhas")
    if any(h <= 0 for h in out):
        raise ValueError("alturas e larguras devem ser positivas")
    return out


def _prefix_fit(heights: Sequence[float], capacity_pt: float) -> int:
    """Quantas linhas do início cabem em `capacity_pt` (tolerância relativa `_EPS`)."""
    total, count = 0.0, 0
    for h in heights:
        if total + h > capacity_pt + _EPS * h:
            break
        total += h
        count += 1
    return count


def rows_that_fit(row_height_pt: float, header_height_pt: float, avail_height_cm: float,
                  width_cm: float, *, source_width_pt: float,
                  row_heights_pt: Sequence[float] | None = None) -> int:
    """Como `rows_per_slice`, mas devolve 0 (sem erro) quando nem uma linha cabe.

    Com `row_heights_pt` (alturas reais por linha, DEC-010 §4), conta quantas linhas do INÍCIO
    da sequência cabem; se todas cabem, o espaço que sobra é contado em linhas de
    `row_height_pt` (a capacidade, como na altura uniforme, não o tamanho do bloco)."""
    if avail_height_cm <= 0:
        return 0
    if row_heights_pt is not None:
        heights = [float(h) for h in row_heights_pt]
        cap = _capacity_pt(header_height_pt, avail_height_cm, width_cm, source_width_pt)
        if cap <= 0:
            return 0
        count = _prefix_fit(heights, cap)
        if count == len(heights) and row_height_pt > 0:
            count += math.floor((cap - sum(heights)) / row_height_pt + _EPS)
        return count
    try:
        return rows_per_slice(row_height_pt, header_height_pt, avail_height_cm, width_cm,
                              source_width_pt=source_width_pt)
    except ValueError:
        return 0


def _greedy_sizes(heights: Sequence[float], capacity_pt: float) -> list[int]:
    sizes: list[int] = []
    total, count = 0.0, 0
    for h in heights:
        if count and total + h > capacity_pt + _EPS * h:
            sizes.append(count)
            total, count = 0.0, 0
        total += h
        count += 1
    if count:
        sizes.append(count)
    return sizes


def _fits(heights: Sequence[float], sizes: Sequence[int], capacity_pt: float) -> bool:
    start = 0
    for size in sizes:
        part = heights[start:start + size]
        if sum(part) > capacity_pt + _EPS * max(part):
            return False
        start += size
    return True


def _even_sizes(n_rows: int, pages: int) -> list[int]:
    """Diferença máxima de 1 entre os recortes, os maiores primeiro."""
    base, extra = divmod(n_rows, pages)
    return [base + (1 if k < extra else 0) for k in range(pages)]


def _balanced_sizes(heights: Sequence[float], pages: int, capacity_pt: float) -> list[int]:
    """Partição contígua em `pages` recortes que cabem, o mais igual possível em nº de linhas.

    Altura uniforme (ou alturas variáveis que ainda cabem): diferença máxima de 1, os maiores
    primeiro — o mesmo resultado de sempre. Senão, programação dinâmica que minimiza a soma dos
    quadrados do desvio de `n/pages` (desempate: recortes maiores primeiro). Sempre existe
    solução: a gulosa com `pages` recortes é uma delas."""
    n = len(heights)
    even = _even_sizes(n, pages)
    if _fits(heights, even, capacity_pt):
        return even
    prefix = [0.0]
    for h in heights:
        prefix.append(prefix[-1] + h)
    target = n / pages

    def fits(i: int, j: int) -> bool:          # linhas i..j-1 num recorte
        part_max = max(heights[i:j])
        return prefix[j] - prefix[i] <= capacity_pt + _EPS * part_max

    inf = float("inf")
    # best[k][j]: melhor custo para as j primeiras linhas em k recortes; choice guarda o início
    best = [[inf] * (n + 1) for _ in range(pages + 1)]
    choice = [[-1] * (n + 1) for _ in range(pages + 1)]
    best[0][0] = 0.0
    for k in range(1, pages + 1):
        for j in range(1, n + 1):
            for i in range(j - 1, -1, -1):      # i decrescente: recorte k menor primeiro
                if not fits(i, j):
                    break
                if best[k - 1][i] == inf:
                    continue
                cost = best[k - 1][i] + (j - i - target) ** 2
                # desempate por recortes maiores primeiro: prefere o maior início `i`
                if cost < best[k][j] - 1e-12 or (abs(cost - best[k][j]) <= 1e-12
                                                  and i > choice[k][j]):
                    best[k][j] = cost
                    choice[k][j] = i
    if best[pages][n] == inf:                   # não acontece (a gulosa é viável)
        raise ValueError("paginação balanceada sem solução")
    sizes, j = [], n
    for k in range(pages, 0, -1):
        i = choice[k][j]
        sizes.append(j - i)
        j = i
    return sizes[::-1]


def paginate(n_rows: int, row_height_pt: float = DEFAULT_ROW_HEIGHT_PT,
             header_height_pt: float = 0.0, avail_height_cm: float = DEFAULT_AVAIL_HEIGHT_CM,
             width_cm: float = DEFAULT_WIDTH_CM, *, source_width_pt: float,
             balance: bool = False, first_avail_height_cm: float | None = None,
             min_rows: int = 1, row_heights_pt: Sequence[float] | None = None) -> list[range]:
    """Recortes sobre os índices `0..n_rows-1`, cada um cabendo em `avail_height_cm`.

    `source_width_pt` é a largura natural do intervalo (pt), necessária para a escala; o
    cabeçalho (`header_height_pt`) entra em todo recorte.

    `row_heights_pt` (DEC-010 §4, `row_height_mode: min_autofit`): altura real de cada linha,
    na ordem; sem ele, todas têm `row_height_pt`.

    `balance=True` mantém o número de páginas da gulosa e distribui as linhas por igual
    (diferença máxima de 1, os maiores primeiro; com alturas variáveis, o mais perto disso que
    couber), evitando um último recorte de 1 linha (`CONTROL_OF_PRODUCTS.render_params.balance`,
    DEC-010 §3).

    `first_avail_height_cm` (DEC-010 §3, 1º recorte): altura disponível só para o primeiro
    recorte — o espaço livre abaixo da frase de chamada, medido no PDF da 1ª passada. O 1º
    recorte leva tantas linhas quanto couberem ali; o resto segue a regra acima em páginas
    inteiras. `min_rows` (`first_slice_min_rows`) protege a cauda: se sobrarem menos que
    `min_rows` linhas para depois, o 1º recorte cede linhas a ela. Quem decide se o espaço
    serve (ao menos `min_rows` linhas) é o chamador; aqui, sem nenhuma linha, é erro.
    """
    if n_rows < 0:
        raise ValueError("n_rows não pode ser negativo")
    if n_rows == 0:
        return []
    if row_heights_pt is None:
        rows_per_slice(row_height_pt, header_height_pt, avail_height_cm, width_cm,
                       source_width_pt=source_width_pt)       # valida a geometria
        heights = [float(row_height_pt)] * n_rows
    else:
        heights = _validate_heights(row_heights_pt, n_rows)
        if min(avail_height_cm, width_cm, source_width_pt) <= 0:
            raise ValueError("alturas e larguras devem ser positivas")
    capacity = _capacity_pt(header_height_pt, avail_height_cm, width_cm, source_width_pt)
    tallest = max(heights)
    if tallest > capacity + _EPS * tallest:
        scale = width_cm / source_width_pt
        raise ValueError(
            f"nem uma linha cabe na página: cabeçalho {header_height_pt * scale:.2f} cm + linha "
            f"{tallest * scale:.2f} cm > {avail_height_cm:.2f} cm úteis")
    if first_avail_height_cm is not None:
        first = 0
        if first_avail_height_cm > 0:
            first_cap = _capacity_pt(header_height_pt, first_avail_height_cm, width_cm,
                                     source_width_pt)
            first = min(n_rows, _prefix_fit(heights, first_cap)) if first_cap > 0 else 0
        if first < 1:
            raise ValueError(f"nem uma linha cabe no 1º recorte ({first_avail_height_cm:.2f} cm)")
        rest = n_rows - first
        if 0 < rest < min_rows:
            first -= min(min_rows - rest, max(0, first - 1))
            rest = n_rows - first
        tail = paginate(rest, row_height_pt, header_height_pt, avail_height_cm, width_cm,
                        source_width_pt=source_width_pt, balance=balance,
                        row_heights_pt=heights[first:] if row_heights_pt is not None else None)
        return [range(0, first)] + [range(s.start + first, s.stop + first) for s in tail]
    sizes = _greedy_sizes(heights, capacity)
    if balance:
        sizes = _balanced_sizes(heights, len(sizes), capacity)
    out, start = [], 0
    for size in sizes:
        out.append(range(start, start + size))
        start += size
    return out


def slice_height_cm(n_rows: int, row_height_pt: float, header_height_pt: float,
                    width_cm: float, *, source_width_pt: float,
                    row_heights_pt: Sequence[float] | None = None) -> float:
    """Altura prevista (cm) de um recorte com `n_rows` linhas de dados (ou com as alturas
    `row_heights_pt` dessas linhas, DEC-010 §4)."""
    rows_pt = n_rows * row_height_pt if row_heights_pt is None else float(sum(row_heights_pt))
    return (header_height_pt + rows_pt) * width_cm / source_width_pt


# ------------------------------------------------------------------ estimador offline (§4)
def estimate_text_lines(text: str | None, chars_per_line: int) -> int:
    """Linhas de um texto com quebra automática, por contagem de caracteres (sem Excel).

    Quebra por palavra: uma palavra vai para a linha seguinte quando a linha passaria de
    `chars_per_line` caracteres (contando o espaço); palavra maior que a linha é partida.
    Quebras explícitas (`\\n`) abrem linha. Texto vazio = 1 linha."""
    if chars_per_line < 1:
        raise ValueError("chars_per_line deve ser positivo")
    if text is None or not str(text).strip():
        return 1
    total = 0
    for paragraph in str(text).split("\n"):
        lines, current = 1, 0
        for word in paragraph.split():
            if current and current + 1 + len(word) > chars_per_line:
                lines += 1
                current = 0
            current = len(word) if current == 0 else current + 1 + len(word)
            while current > chars_per_line:          # palavra maior que a linha
                lines += 1
                current -= chars_per_line
        total += lines
    return total


def estimate_row_height_pt(texts: Mapping[str, str | None], chars_per_line: Mapping[str, int],
                           line_height_pt: float, min_height_pt: float) -> float:
    """Altura estimada de uma linha: `max(min_height_pt, line_height_pt × maior nº de linhas)`
    entre as colunas com quebra (`chars_per_line`: campo -> caracteres por linha).

    É o substituto OFFLINE do AutoFit do Excel (DEC-010 §4); os parâmetros vêm de
    `CONTROL_OF_PRODUCTS.render_params.row_height_estimate` (calibração documentada lá)."""
    if line_height_pt <= 0 or min_height_pt <= 0:
        raise ValueError("alturas devem ser positivas")
    lines = max((estimate_text_lines(texts.get(field), int(cpl))
                 for field, cpl in chars_per_line.items()), default=1)
    return max(float(min_height_pt), lines * float(line_height_pt))
