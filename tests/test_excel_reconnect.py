"""Ciclo de vida do Excel entre as passadas do montador (offline, COM falso).

Bug reproduzido no nº 14: o `pythoncom.CoUninitialize` da exportação do Word derrubava o
apartamento COM da thread; com `first_slice_fill` os recortes da 2ª passada mudam, saem do cache
e a pasta guardada respondia CO_E_OBJNOTCONNECTED. Aqui: inicialização balanceada
(`office.com_apartment`), reabertura de pasta/Excel desconectados (`office.excel_emf`) e
recriação da instância pelo cache do montador (`builder.assemble.CachingEmfRenderer`).
"""

from __future__ import annotations

import pytest

from prog_g2_report.builder.assemble import CachingEmfRenderer
from prog_g2_report.office.com_apartment import (
    RPC_E_CHANGED_MODE,
    S_FALSE,
    S_OK,
    ComApartment,
    com_apartment,
)
from prog_g2_report.office.excel_emf import ExcelEmfRenderer, is_disconnected

CO_E_OBJNOTCONNECTED = -2147220995
RPC_E_DISCONNECTED = -2147417848
RPC_E_CALL_REJECTED = -2147418111


class FakeComError(Exception):
    """Mesma forma do pywintypes.com_error: (hresult, texto, excepinfo, argerr)."""

    def __init__(self, hresult: int, excepinfo=None):
        super().__init__(hresult, "erro COM sintético", excepinfo, None)


# ------------------------------------------------------------------ is_disconnected
def test_disconnection_is_recognised_by_hresult_and_scode():
    assert is_disconnected(FakeComError(CO_E_OBJNOTCONNECTED))
    assert is_disconnected(FakeComError(RPC_E_DISCONNECTED))
    excepinfo = (0, "Excel", "x", None, 0, CO_E_OBJNOTCONNECTED)
    assert is_disconnected(FakeComError(-2147352567, excepinfo))     # DISP_E_EXCEPTION
    assert not is_disconnected(FakeComError(RPC_E_CALL_REJECTED))     # ocupado ≠ morto
    assert not is_disconnected(ValueError("x"))
    assert not is_disconnected(RuntimeError())


# ------------------------------------------------------------------ apartamento balanceado
class FakeOle32:
    def __init__(self, hr: int):
        self.hr = hr
        self.inits = 0
        self.uninits = 0

    def CoInitializeEx(self, reserved, flags):  # noqa: N802 (nome da API)
        self.inits += 1
        return self.hr

    def CoUninitialize(self):  # noqa: N802
        self.uninits += 1


@pytest.mark.parametrize("hr", [S_OK, S_FALSE])
def test_apartment_undoes_exactly_what_it_did(hr):
    ole32 = FakeOle32(hr)
    apartment = ComApartment(ole32).enter()
    apartment.enter()                         # idempotente: não conta duas vezes
    assert apartment.owned and ole32.inits == 1
    apartment.leave()
    apartment.leave()
    assert ole32.uninits == 1


def test_apartment_in_another_model_is_used_but_not_undone():
    ole32 = FakeOle32(RPC_E_CHANGED_MODE)
    with com_apartment(ole32) as apartment:
        assert not apartment.owned
    assert ole32.uninits == 0


def test_apartment_failure_raises():
    with pytest.raises(OSError, match="CoInitializeEx"):
        ComApartment(FakeOle32(-2147024882)).enter()       # E_OUTOFMEMORY


def test_nested_apartments_never_drop_below_the_callers_count():
    """Excel (externo) + Word (interno): a saída do Word não desfaz a entrada do Excel."""
    ole32 = FakeOle32(S_FALSE)
    excel = ComApartment(ole32).enter()
    with com_apartment(ole32):
        pass
    assert ole32.inits - ole32.uninits == 1
    excel.leave()
    assert ole32.inits == ole32.uninits


# ------------------------------------------------------------------ ExcelEmfRenderer
class FakeSheet:
    AutoFilterMode = False


class FakeWorkbook:
    def __init__(self):
        self.dead = False
        self.closed = False

    @property
    def Name(self):  # noqa: N802
        if self.dead:
            raise FakeComError(CO_E_OBJNOTCONNECTED)
        return "lista.xlsx"

    def Worksheets(self, name):  # noqa: N802
        if self.dead:
            raise FakeComError(CO_E_OBJNOTCONNECTED)
        return FakeSheet()

    def Close(self, SaveChanges):  # noqa: N802, N803
        if self.dead:
            raise FakeComError(CO_E_OBJNOTCONNECTED)
        assert SaveChanges is False
        self.closed = True


class FakeWorkbooks:
    def __init__(self, app):
        self.app = app

    def Open(self, path, **kwargs):  # noqa: N802
        assert kwargs["ReadOnly"] is True
        workbook = FakeWorkbook()
        self.app.opened.append(workbook)
        return workbook


class FakeApp:
    def __init__(self):
        self.dead = False
        self.opened: list[FakeWorkbook] = []
        self.quits = 0
        self.Workbooks = FakeWorkbooks(self)

    @property
    def Name(self):  # noqa: N802
        if self.dead:
            raise FakeComError(RPC_E_DISCONNECTED)
        return "Microsoft Excel"

    def Quit(self):  # noqa: N802
        if self.dead:
            raise FakeComError(RPC_E_DISCONNECTED)
        self.quits += 1


@pytest.fixture
def renderer(tmp_path, monkeypatch):
    """ExcelEmfRenderer 'dentro do with' com um Excel falso; sem COM, sem processo."""
    apps: list[FakeApp] = []

    def start(self):
        app = FakeApp()
        apps.append(app)
        self._excel = app
        self._pid = None                       # nada de processo real a esperar/encerrar

    monkeypatch.setattr(ExcelEmfRenderer, "_start_excel", start)
    r = ExcelEmfRenderer()
    r._start_excel()
    r._entered = True
    xlsx = tmp_path / "lista.xlsx"
    xlsx.write_bytes(b"sintetico")
    return r, apps, xlsx


def test_cached_workbook_is_reused_while_connected(renderer):
    r, apps, xlsx = renderer
    r._sheet(xlsx, "Controle Geral")
    r._sheet(xlsx, "Controle Geral")
    assert len(apps[0].opened) == 1 and r.reopened == 0


def test_disconnected_workbook_is_reopened(renderer):
    r, apps, xlsx = renderer
    r._sheet(xlsx, "Controle Geral")
    apps[0].opened[0].dead = True             # a pasta caiu entre as passadas
    assert isinstance(r._sheet(xlsx, "Controle Geral"), FakeSheet)
    assert len(apps[0].opened) == 2 and r.reopened == 1 and r.restarts == 0


def test_dead_excel_is_restarted(renderer):
    r, apps, xlsx = renderer
    r._sheet(xlsx, "Controle Geral")
    apps[0].dead = True
    apps[0].opened[0].dead = True
    assert isinstance(r._sheet(xlsx, "Controle Geral"), FakeSheet)
    assert len(apps) == 2 and r.restarts == 1 and len(apps[1].opened) == 1


def test_operation_interrupted_by_disconnection_is_redone_once(renderer):
    r, apps, xlsx = renderer
    calls = []

    def operation():
        calls.append(1)
        if len(calls) == 1:
            r._sheet(xlsx, "Controle Geral")
            apps[0].opened[0].dead = True
            raise FakeComError(CO_E_OBJNOTCONNECTED)
        return "ok"

    assert r._retrying(operation) == "ok"
    assert len(calls) == 2 and not r._workbooks       # a pasta morta saiu do cache


def test_other_errors_are_not_retried(renderer):
    r, _, _ = renderer
    calls = []

    def operation():
        calls.append(1)
        raise FakeComError(RPC_E_CALL_REJECTED)

    with pytest.raises(FakeComError):
        r._retrying(operation)
    assert len(calls) == 1


def test_close_tolerates_dead_proxies_and_runs_once(renderer):
    r, apps, xlsx = renderer
    r._sheet(xlsx, "Controle Geral")
    apps[0].opened[0].dead = True
    apps[0].dead = True
    r.close()
    r.close()
    assert r._excel is None and not r._workbooks
    with pytest.raises(RuntimeError, match="fora do bloco"):
        r._sheet(xlsx, "Controle Geral")


def test_close_quits_a_live_excel_without_saving(renderer):
    r, apps, xlsx = renderer
    r._sheet(xlsx, "Controle Geral")
    r.close()
    assert apps[0].quits == 1 and apps[0].opened[0].closed


# ------------------------------------------------------------------ cache do montador
class DyingRenderer:
    """Renderizador falso cuja conexão cai depois de `alive_calls` chamadas."""

    def __init__(self, alive_calls: int):
        self.alive_calls = alive_calls
        self.calls = 0
        self.closed = False

    def measure(self, *args, **kwargs):
        return ("geom", args)

    def render_slices(self, xlsx_path, sheet, rows, slices, **kwargs):
        self.calls += 1
        if self.calls > self.alive_calls:
            raise FakeComError(CO_E_OBJNOTCONNECTED)
        return [b"emf"] * len(slices)

    def close(self):
        self.closed = True


def test_cache_recreates_a_disconnected_renderer_once():
    made: list[DyingRenderer] = []

    def factory():
        made.append(DyingRenderer(alive_calls=1))
        return made[-1]

    cache = CachingEmfRenderer(factory)
    assert cache.render_slices("x.xlsx", "s", [5, 6], [range(0, 2)]) == [b"emf"]
    assert cache.render_slices("x.xlsx", "s", [5, 6], [range(0, 2)]) == [b"emf"]   # cache
    # 2ª passada com recortes diferentes: a 1ª instância caiu; a 2ª atende
    assert cache.render_slices("x.xlsx", "s", [5, 6], [range(0, 1), range(1, 2)]) == [b"emf"] * 2
    assert len(made) == 2 and made[0].closed and cache.instances == 2
    cache.close()
    assert made[1].closed


def test_cache_gives_up_after_one_recreation():
    made: list[DyingRenderer] = []

    def factory():
        made.append(DyingRenderer(alive_calls=0))
        return made[-1]

    cache = CachingEmfRenderer(factory)
    with pytest.raises(FakeComError):
        cache.render_slices("x.xlsx", "s", [5], [range(0, 1)])
    assert len(made) == 2
    cache.close()
    assert all(r.closed for r in made)


def test_cache_does_not_recreate_on_other_errors():
    made: list[DyingRenderer] = []

    class Broken(DyingRenderer):
        def render_slices(self, *args, **kwargs):
            raise ValueError("recorte fora da seleção")

    def factory():
        made.append(Broken(alive_calls=0))
        return made[-1]

    cache = CachingEmfRenderer(factory)
    with pytest.raises(ValueError):
        cache.render_slices("x.xlsx", "s", [5], [range(0, 1)])
    assert len(made) == 1
