"""Paginação gulosa do Controle de Produtos com cabeçalho repetido (DEC-010 §3)."""

import pytest

from prog_g2_report.render.paginate import (
    estimate_row_height_pt,
    estimate_text_lines,
    paginate,
    rows_per_slice,
    rows_that_fit,
    slice_height_cm,
)

# geometria medida no nº 14 (D:I a 120 dpi: 1233 px = 739,8 pt; título+cabeçalho ≈ 85,8 pt)
GEOM = {"row_height_pt": 27.6, "header_height_pt": 85.8, "avail_height_cm": 26.2,
        "width_cm": 17.5, "source_width_pt": 739.8}


def _sizes(slices):
    return [len(s) for s in slices]


def test_zero_rows_has_no_slices():
    assert paginate(0, **GEOM) == []


def test_single_slice_when_it_fits():
    assert paginate(3, **GEOM) == [range(0, 3)]


def test_greedy_fill_and_remainder():
    per = rows_per_slice(**GEOM)
    assert per == 37
    slices = paginate(98, **GEOM)
    assert _sizes(slices) == [37, 37, 24]
    assert [i for s in slices for i in s] == list(range(98))     # partição contígua, em ordem


def test_exact_multiple_has_no_empty_tail():
    per = rows_per_slice(**GEOM)
    assert _sizes(paginate(2 * per, **GEOM)) == [per, per]
    assert _sizes(paginate(2 * per + 1, **GEOM)) == [per, per, 1]


def test_header_is_repeated_in_every_slice_height():
    geom = {k: GEOM[k] for k in ("row_height_pt", "header_height_pt", "width_cm", "source_width_pt")}
    for s in paginate(149, **GEOM):
        assert slice_height_cm(len(s), **geom) <= GEOM["avail_height_cm"] + 1e-9
    # uma linha a mais estoura: a quebra é gulosa
    per = rows_per_slice(**GEOM)
    assert slice_height_cm(per + 1, **geom) > GEOM["avail_height_cm"]


def test_taller_header_means_fewer_rows():
    small = rows_per_slice(**{**GEOM, "header_height_pt": 0})
    big = rows_per_slice(**{**GEOM, "header_height_pt": 200})
    assert small > big


def test_exact_fit_counts_boundary_row():
    # cabeçalho 0, linha de 1 cm no documento, 5 cm úteis: cabem exatamente 5
    geom = {"row_height_pt": 10, "header_height_pt": 0, "avail_height_cm": 5.0,
            "width_cm": 10.0, "source_width_pt": 100}
    assert rows_per_slice(**geom) == 5
    assert _sizes(paginate(11, **geom)) == [5, 5, 1]


def test_balance_keeps_page_count_and_avoids_orphan():
    greedy = paginate(149, **GEOM)
    balanced = paginate(149, **GEOM, balance=True)
    assert _sizes(greedy) == [37, 37, 37, 37, 1]
    assert _sizes(balanced) == [30, 30, 30, 30, 29]
    assert [i for s in balanced for i in s] == list(range(149))
    assert _sizes(paginate(3, **GEOM, balance=True)) == [3]


def _first_avail(rows: int) -> float:
    """Altura exata de um recorte com `rows` linhas (+ folga de arredondamento)."""
    geom = {k: GEOM[k] for k in ("row_height_pt", "header_height_pt", "width_cm", "source_width_pt")}
    return slice_height_cm(rows, **geom) + 0.01


def test_first_slice_uses_the_free_space_then_full_pages_balanced():
    # DEC-010 §3: 25 linhas cabem abaixo da frase de chamada; o resto em páginas inteiras
    slices = paginate(98, **GEOM, balance=True, first_avail_height_cm=_first_avail(25))
    assert _sizes(slices) == [25, 37, 36]
    assert [i for s in slices for i in s] == list(range(98))


def test_first_slice_takes_everything_when_it_fits():
    assert _sizes(paginate(3, **GEOM, first_avail_height_cm=_first_avail(10))) == [3]


def test_first_slice_yields_rows_so_the_tail_is_not_tiny():
    slices = paginate(27, **GEOM, balance=True, first_avail_height_cm=_first_avail(25),
                      min_rows=3)
    assert _sizes(slices) == [24, 3]


def test_first_slice_without_room_raises():
    with pytest.raises(ValueError, match="1º recorte"):
        paginate(10, **GEOM, first_avail_height_cm=1.0)


def test_impossible_geometry_raises():
    with pytest.raises(ValueError, match="nem uma linha"):
        paginate(5, **{**GEOM, "header_height_pt": 2000})
    with pytest.raises(ValueError):
        paginate(-1, **GEOM)
    with pytest.raises(ValueError):
        paginate(5, **{**GEOM, "row_height_pt": 0})
    with pytest.raises(ValueError):
        paginate(5, **{**GEOM, "header_height_pt": -1})


# ------------------------------------------------- alturas reais por linha (DEC-010 §4)
def test_uniform_heights_sequence_gives_the_same_slices():
    for n in (3, 37, 98, 149):
        for balance in (False, True):
            uniform = paginate(n, **GEOM, balance=balance)
            explicit = paginate(n, **GEOM, balance=balance, row_heights_pt=[27.6] * n)
            assert explicit == uniform
    first = _first_avail(25)
    assert paginate(98, **GEOM, balance=True, first_avail_height_cm=first,
                    row_heights_pt=[27.6] * 98) == \
        paginate(98, **GEOM, balance=True, first_avail_height_cm=first)


def test_tall_rows_reduce_the_rows_of_their_slice():
    geom = {k: GEOM[k] for k in ("header_height_pt", "width_cm", "source_width_pt")}
    heights = [27.6] * 40
    heights[5] = heights[6] = 41.4                 # duas descrições de 3 linhas no 1º recorte
    slices = paginate(40, **GEOM, row_heights_pt=heights)
    assert _sizes(slices) == [36, 4]               # 37 uniformes; 2 × 13,8 pt a mais = 1 linha
    for s in slices:
        part = [heights[i] for i in s]
        assert slice_height_cm(len(s), 27.6, row_heights_pt=part, **geom) \
            <= GEOM["avail_height_cm"] + 1e-9
    assert [i for s in slices for i in s] == list(range(40))


def test_balance_with_variable_heights_keeps_pages_and_fits():
    geom = {k: GEOM[k] for k in ("header_height_pt", "width_cm", "source_width_pt")}
    heights = [27.6] * 75
    for i in range(12):
        heights[i] = 55.2                          # o início é bem mais alto
    greedy = paginate(75, **GEOM, row_heights_pt=heights)
    balanced = paginate(75, **GEOM, balance=True, row_heights_pt=heights)
    assert len(balanced) == len(greedy)
    assert [i for s in balanced for i in s] == list(range(75))
    for s in balanced:
        part = [heights[i] for i in s]
        assert slice_height_cm(len(s), 27.6, row_heights_pt=part, **geom) \
            <= GEOM["avail_height_cm"] + 1e-9
    # mais igual que a gulosa (que deixa a cauda curta)
    assert max(_sizes(balanced)) - min(_sizes(balanced)) < \
        max(_sizes(greedy)) - min(_sizes(greedy))


def test_first_slice_counts_the_real_heights():
    heights = [41.4, 41.4] + [27.6] * 30
    free = _first_avail(3)                         # cabem 3 linhas de 27,6 pt
    slices = paginate(32, **GEOM, first_avail_height_cm=free, row_heights_pt=heights)
    assert _sizes(slices)[0] == 2                  # 2 × 41,4 = 82,8 pt; a 3ª não cabe
    assert [i for s in slices for i in s] == list(range(32))


def test_rows_that_fit_with_heights_counts_capacity_beyond_the_block():
    geom = {k: GEOM[k] for k in ("row_height_pt", "header_height_pt", "width_cm",
                                 "source_width_pt")}
    free = _first_avail(10)
    assert rows_that_fit(avail_height_cm=free, row_heights_pt=[27.6, 27.6], **geom) == 10
    assert rows_that_fit(avail_height_cm=free, row_heights_pt=[55.2] * 8, **geom) == 5


def test_row_heights_validation():
    with pytest.raises(ValueError, match="alturas"):
        paginate(3, **GEOM, row_heights_pt=[27.6, 27.6])
    with pytest.raises(ValueError):
        paginate(2, **GEOM, row_heights_pt=[27.6, 0])
    with pytest.raises(ValueError, match="nem uma linha"):
        paginate(2, **GEOM, row_heights_pt=[27.6, 2000])


def test_estimator_counts_wrapped_lines():
    assert estimate_text_lines(None, 10) == 1
    assert estimate_text_lines("curta", 10) == 1
    assert estimate_text_lines("palavra outra", 10) == 2
    assert estimate_text_lines("a\nb\nc", 10) == 3
    assert estimate_text_lines("x" * 25, 10) == 3                  # palavra maior que a linha
    cpl = {"description": 20}
    assert estimate_row_height_pt({"description": "um dois"}, cpl, 13.8, 27.6) == 27.6
    long = "um dois três quatro cinco seis sete oito nove dez onze"
    assert estimate_row_height_pt({"description": long}, cpl, 13.8, 27.6) == pytest.approx(41.4)
