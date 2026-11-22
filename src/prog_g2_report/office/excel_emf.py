"""Recortes do Controle de Produtos como EMF, gerados pelo próprio Excel (DEC-010).

Produção da cadeia provada em `scripts/12_probe_emf_export.py`:

    Lista Mestra (cópia local, ReadOnly) → filtro salvo descartado (DEC-009)
    → alturas por linha = max(mínimo, AutoFit) medidas só em memória (`measure_row_heights`)
    → linhas fora do recorte ocultas, alturas aplicadas só em memória (DEC-010 §4)
    → linhas de dados sem negrito, só em memória (`normalize_data_font`, DEC-007)
    → Range.CopyPicture(xlScreen, xlPicture) → CF_ENHMETAFILE (14) → bytes EMF

Segurança e ambiente:
- instância própria do Excel (`DispatchEx`), invisível, nunca a da usuária;
- pasta aberta com `ReadOnly=True`; **nunca salva**; fecha com `SaveChanges=False`; `Quit`
  garantido no `__exit__`: espera o processo sair e o encerra se o `Quit` falhar ou travar;
- a área de transferência é recurso exclusivo: um renderizador por vez (DEC-010, consequências);
- `win32com`/`win32clipboard` só são importados aqui dentro, para o pacote importar sem pywin32.

Ciclo de vida entre passadas do montador: a instância fica viva do 1º recorte até o `close()`
final (o montador garante o `close` num `finally`). Entre uma passada e outra o Word exporta o
PDF; observado neste ambiente (2026-10): a pasta guardada em cache pode voltar desconectada
(`CO_E_OBJNOTCONNECTED`, "Objeto não conectado ao servidor") e o próprio Excel pode ter morrido.
Por isso toda pasta em cache é testada antes do uso e reaberta se caiu; se o Excel não responde,
o processo antigo é encerrado (só o PID desta instância) e outra instância própria é aberta.
Uma operação interrompida por desconexão é refeita uma única vez do zero (`render_slices` e
`measure` não dependem de estado anterior: cada chamada repõe o que alterou).
"""

from __future__ import annotations

import contextlib
import ctypes
import gc
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CF_ENHMETAFILE = 14
XL_PICTURE = -4147
XL_UP = -4162
APPEARANCE = {"screen": 1, "printer": 2}   # xlScreen, xlPrinter (só xlScreen reproduz, DEC-010 §1)

# HRESULTs de "o objeto/servidor COM sumiu" (o proxy guardado não serve mais).
DISCONNECTED_HRESULTS = frozenset({
    -2147220995,   # 0x800401FD CO_E_OBJNOTCONNECTED  "Objeto não conectado ao servidor"
    -2147417848,   # 0x80010108 RPC_E_DISCONNECTED
    -2147418105,   # 0x80010007 RPC_E_SERVER_DIED
    -2147418094,   # 0x80010012 RPC_E_SERVER_DIED_DNE
    -2147023174,   # 0x800706BA RPC_S_SERVER_UNAVAILABLE
    -2147023170,   # 0x800706BE RPC_S_CALL_FAILED
})


def is_disconnected(exc: BaseException) -> bool:
    """True se `exc` é um erro COM de desconexão (pywintypes.com_error ou equivalente: o
    HRESULT é o 1º argumento; o `scode` do excepinfo também conta)."""
    args = getattr(exc, "args", ()) or ()
    codes = [getattr(exc, "hresult", None)]
    if args:
        codes.append(args[0])
    if len(args) > 2 and isinstance(args[2], tuple) and len(args[2]) > 5:
        codes.append(args[2][5])
    return any(isinstance(c, int) and c in DISCONNECTED_HRESULTS for c in codes)


@dataclass(frozen=True)
class SheetGeometry:
    """Medidas naturais do intervalo, em pontos (a unidade do Excel)."""

    width_pt: float            # largura das colunas do recorte
    header_height_pt: float    # soma das alturas das linhas de título/cabeçalho


def parse_columns(columns: str) -> tuple[str, str]:
    """'D:I' -> ('D', 'I')."""
    first, sep, last = columns.partition(":")
    first, last = first.strip().upper(), (last or first).strip().upper()
    if not (first.isalpha() and last.isalpha()) or (sep and not last):
        raise ValueError(f"intervalo de colunas inválido: {columns!r}")
    return first, last


# ---------------------------------------------------------------- área de transferência
def _open_clipboard(cb: Any, tries: int = 50) -> None:
    for _ in range(tries):
        try:
            cb.OpenClipboard(0)
            return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("não foi possível abrir a área de transferência")


def clear_clipboard() -> None:
    import win32clipboard as cb

    _open_clipboard(cb)
    try:
        cb.EmptyClipboard()
    finally:
        cb.CloseClipboard()


def grab_enhmetafile() -> bytes:
    """Bytes do CF_ENHMETAFILE atual. pywin32 ≥ 312 devolve bytes; se vier handle, usa GDI."""
    import win32clipboard as cb

    _open_clipboard(cb)
    try:
        if not cb.IsClipboardFormatAvailable(CF_ENHMETAFILE):
            raise RuntimeError("CF_ENHMETAFILE ausente na área de transferência")
        data = cb.GetClipboardData(CF_ENHMETAFILE)
    finally:
        cb.CloseClipboard()
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    gdi32 = ctypes.windll.gdi32
    gdi32.GetEnhMetaFileBits.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p]
    size = gdi32.GetEnhMetaFileBits(data, 0, None)
    buf = ctypes.create_string_buffer(size)
    gdi32.GetEnhMetaFileBits(data, size, buf)
    return buf.raw


def _wait_process_exit(pid: int, timeout_s: float) -> bool:
    """True se o processo `pid` não existe ou terminou dentro do prazo.

    Bombeia mensagens enquanto espera: o encerramento do Excel conversa com a thread STA
    cliente; esperar sem bombear trava o `Quit` até o prazo.
    """
    try:
        import pythoncom
        import pywintypes
        import win32api
        import win32event
    except ImportError:
        return True
    try:
        handle = win32api.OpenProcess(0x00100000, False, pid)   # SYNCHRONIZE
    except pywintypes.error:
        return True                                              # já saiu
    try:
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = max(0, int((deadline - time.monotonic()) * 1000))
            result = win32event.MsgWaitForMultipleObjects(
                [handle], False, remaining, win32event.QS_ALLINPUT)
            if result == win32event.WAIT_OBJECT_0:
                return True
            if result == win32event.WAIT_OBJECT_0 + 1 and remaining > 0:
                pythoncom.PumpWaitingMessages()
                continue
            return False
    finally:
        win32api.CloseHandle(handle)


# ---------------------------------------------------------------- renderizador
class ExcelEmfRenderer:
    """Context manager que abre um Excel próprio e devolve EMFs de recortes da Lista Mestra.

        with ExcelEmfRenderer() as renderer:
            emfs = renderer.render_slices(path, "Controle Geral", rows, slices)

    As pastas abertas ficam em cache durante o contexto; cada chamada restaura o estado que
    alterou (alturas e ocultação), então chamadas sucessivas não se contaminam. Pasta ou Excel
    desconectados entre chamadas são reabertos (ver o docstring do módulo); `reopened` conta as
    pastas reabertas e `restarts` as instâncias do Excel recriadas.
    """

    def __init__(self, appearance: str = "screen", copy_retries: int = 5,
                 quit_timeout_s: float = 20.0) -> None:
        if appearance not in APPEARANCE:
            raise ValueError(f"appearance deve ser um de {sorted(APPEARANCE)}")
        self.appearance = appearance
        self.copy_retries = copy_retries
        self.quit_timeout_s = quit_timeout_s
        self._excel: Any = None
        self._pid: int | None = None
        self._workbooks: dict[str, Any] = {}
        self._apartment: Any = None
        self._entered = False
        self.reopened = 0
        self.restarts = 0

    # -- ciclo de vida ------------------------------------------------------------------
    def __enter__(self) -> ExcelEmfRenderer:
        from prog_g2_report.office.com_apartment import ComApartment

        # ole32 direto, contagem balanceada: pythoncom.CoUninitialize de outro módulo (Word)
        # não pode derrubar o apartamento desta instância (office.com_apartment).
        self._apartment = ComApartment().enter()
        try:
            self._start_excel()
        except BaseException:
            self.close()
            raise
        self._entered = True
        return self

    def _start_excel(self) -> None:
        import win32com.client as com

        excel = com.DispatchEx("Excel.Application")   # instância própria
        self._excel = excel
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.ScreenUpdating = True                   # xlScreen precisa do desenho de tela
        self._pid = self._excel_pid(excel)

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def excel_version(self) -> str | None:
        return None if self._excel is None else str(self._excel.Version)

    @staticmethod
    def _excel_pid(excel: Any) -> int | None:
        try:
            import win32process

            return int(win32process.GetWindowThreadProcessId(excel.Hwnd)[1])
        except Exception:
            return None

    def close(self) -> None:
        """Fecha tudo sem salvar e encerra o Excel. Idempotente."""
        self._entered = False
        with contextlib.suppress(Exception):
            clear_clipboard()
        self._shutdown_excel()
        if self._apartment is not None:
            self._apartment.leave()
            self._apartment = None

    def _shutdown_excel(self) -> None:
        """Fecha as pastas sem salvar, `Quit` e espera o processo; encerra o PID desta
        instância se o `Quit` falhar ou travar. Tolera proxies já desconectados."""
        while self._workbooks:
            # pop: nenhuma variável local pode segurar o proxy até o CoUninitialize
            _, workbook = self._workbooks.popitem()
            with contextlib.suppress(Exception):
                workbook.Close(SaveChanges=False)
            del workbook
        gc.collect()                       # solta proxies COM pendentes antes do Quit
        quit_failed = False
        if self._excel is not None:
            try:
                self._excel.Quit()
            except Exception:
                quit_failed = True
            self._excel = None
            gc.collect()
        # Quit garantido: espera o processo sair; se travar (ou o Quit falhar), encerra.
        if self._pid and (quit_failed
                          or not _wait_process_exit(self._pid, self.quit_timeout_s)):
            with contextlib.suppress(Exception):
                os.kill(self._pid, 9)
            _wait_process_exit(self._pid, 5.0)
        self._pid = None

    # -- reconexão ----------------------------------------------------------------------
    @staticmethod
    def _alive(obj: Any) -> bool:
        """O proxy ainda fala com o servidor? Só desconexão conta como morto; outro erro sobe."""
        try:
            _ = obj.Name
        except Exception as exc:
            if is_disconnected(exc):
                return False
            raise
        return True

    def _restart_excel(self) -> None:
        self._shutdown_excel()
        self._start_excel()
        self.restarts += 1

    def _ensure_excel(self) -> None:
        if not self._entered:
            raise RuntimeError("ExcelEmfRenderer fora do bloco `with`")
        if self._excel is None or not self._alive(self._excel):
            self._restart_excel()

    def _recover(self) -> None:
        """Depois de uma desconexão: recria o Excel se ele caiu; senão descarta as pastas
        desconectadas (o `_sheet` seguinte as reabre)."""
        if self._excel is None or not self._alive(self._excel):
            self._restart_excel()
            return
        for key, workbook in list(self._workbooks.items()):
            if not self._alive(workbook):
                del self._workbooks[key]
        gc.collect()

    def _retrying(self, operation: Callable[[], Any]) -> Any:
        """Executa `operation`; se o COM desconectar no meio, recupera e refaz uma vez."""
        try:
            return operation()
        except Exception as exc:
            if not is_disconnected(exc):
                raise
        self._recover()
        return operation()

    # -- pasta e aba --------------------------------------------------------------------
    def _sheet(self, xlsx_path: Path | str, sheet: str) -> Any:
        self._ensure_excel()
        path = Path(xlsx_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"planilha ausente: {path}")
        key = os.path.normcase(str(path))
        workbook = self._workbooks.get(key)
        if workbook is not None and not self._alive(workbook):
            # pasta guardada desconectada (ex.: entre passadas do montador): reabre
            del self._workbooks[key]
            workbook = None
            self.reopened += 1
            gc.collect()
        if workbook is None:
            workbook = self._excel.Workbooks.Open(
                str(path), UpdateLinks=0, ReadOnly=True, IgnoreReadOnlyRecommended=True,
                Notify=False, AddToMru=False)
            self._workbooks[key] = workbook
        return workbook.Worksheets(sheet)

    @staticmethod
    def _reset(ws: Any) -> None:
        """Filtro salvo não é verdade (DEC-009): descarta e mostra todas as linhas."""
        if ws.AutoFilterMode:
            ws.AutoFilterMode = False
        ws.Rows.Hidden = False

    def measure(self, xlsx_path: Path | str, sheet: str, columns: str = "D:I",
                header_rows: tuple[int, int] = (1, 3)) -> SheetGeometry:
        """Largura natural das colunas e altura do bloco de título/cabeçalho, em pt."""
        return self._retrying(lambda: self._measure(xlsx_path, sheet, columns, header_rows))

    def _measure(self, xlsx_path: Path | str, sheet: str, columns: str,
                 header_rows: tuple[int, int]) -> SheetGeometry:
        first_col, last_col = parse_columns(columns)
        h_first, h_last = header_rows
        ws = self._sheet(xlsx_path, sheet)
        self._reset(ws)
        width = float(ws.Range(f"{first_col}{h_first}:{last_col}{h_first}").Width)
        height = float(sum(ws.Rows(r).RowHeight for r in range(h_first, h_last + 1)))
        return SheetGeometry(width_pt=width, header_height_pt=height)

    # -- alturas de linha (DEC-010 §4) ---------------------------------------------------
    def measure_row_heights(self, xlsx_path: Path | str, sheet: str,
                            selected_physical_rows: Sequence[int], *, columns: str = "D:I",
                            min_height_pt: float = 27.6,
                            normalize_data_font: bool = False) -> list[float]:
        """Altura de cada linha selecionada = `max(min_height_pt, AutoFit do Excel)`, em pt.

        `CONTROL_OF_PRODUCTS.render_params.row_height_mode: min_autofit` (DEC-010 §4): o AutoFit
        roda só sobre as células `columns` de cada linha (`Range("D r:I r").Rows.AutoFit`), na
        cópia em memória, com a mesma tipografia do desenho (`normalize_data_font` aplicado
        antes, se pedido); alturas e negrito originais são restaurados no fim e a planilha nunca
        é salva. O resultado alimenta a paginação e o `render_slices(row_heights_pt=...)`.
        """
        rows = [int(r) for r in selected_physical_rows]
        if not rows:
            return []
        if min_height_pt <= 0:
            raise ValueError("min_height_pt deve ser positivo")
        first_col, last_col = parse_columns(columns)
        return self._retrying(lambda: self._measure_row_heights(
            xlsx_path, sheet, rows, first_col, last_col, float(min_height_pt),
            normalize_data_font))

    def _measure_row_heights(self, xlsx_path: Path | str, sheet: str, rows: list[int],
                             first_col: str, last_col: str, min_height_pt: float,
                             normalize_data_font: bool) -> list[float]:
        ws = self._sheet(xlsx_path, sheet)
        self._reset(ws)                    # AutoFit em linha visível (filtro salvo descartado)
        original_heights = {r: float(ws.Rows(r).RowHeight) for r in rows}
        original_bold: dict[str, Any] = {}
        try:
            if normalize_data_font:
                original_bold.update(self._normalize_bold(ws, rows, first_col, last_col))
            out: list[float] = []
            for r in rows:
                ws.Range(f"{first_col}{r}:{last_col}{r}").Rows.AutoFit()
                out.append(max(min_height_pt, float(ws.Rows(r).RowHeight)))
            return out
        finally:
            with contextlib.suppress(Exception):
                for r, height in original_heights.items():
                    ws.Rows(r).RowHeight = height
            with contextlib.suppress(Exception):
                for address, bold in original_bold.items():
                    ws.Range(address).Font.Bold = bold

    # -- recortes -----------------------------------------------------------------------
    def render_slices(self, xlsx_path: Path | str, sheet: str,
                      selected_physical_rows: Sequence[int], slices: Sequence[range], *,
                      columns: str = "D:I", header_rows: tuple[int, int] = (1, 3),
                      row_height_pt: float | None = 27.6, filter_columns: str | None = "B:M",
                      normalize_data_font: bool = False,
                      row_heights_pt: Sequence[float] | None = None) -> list[bytes]:
        """Um EMF por recorte; `slices` indexa `selected_physical_rows` (ordem física).

        - `columns`: colunas do quadro (D:I = Documento … Status Entrega na prova);
        - `header_rows`: linhas de título/cabeçalho repetidas em todo recorte;
        - `row_height_pt`: altura uniforme das linhas selecionadas, só em memória; None mantém;
        - `row_heights_pt`: altura de CADA linha selecionada (mesma ordem), só em memória;
          prevalece sobre `row_height_pt` (`row_height_mode: min_autofit`, DEC-010 §4; vem de
          `measure_row_heights`);
        - `filter_columns`: liga um autofiltro **sem critério** nesse intervalo só para
          desenhar as setas do cabeçalho, como no histórico; None desliga. A seleção nunca
          vem do autofiltro;
        - `normalize_data_font`: `Font.Bold = False` nas células `columns` das linhas
          selecionadas (só dados; título e cabeçalho mantêm a sua formatação), só em memória e
          restaurado no fim (`CONTROL_OF_PRODUCTS.render_params.normalize_data_font`, DEC-007).
        """
        rows = [int(r) for r in selected_physical_rows]
        if not rows:
            return []
        if len(set(rows)) != len(rows):
            raise ValueError("linhas físicas repetidas na seleção")
        if rows != sorted(rows):
            raise ValueError("a seleção deve estar na ordem física da planilha")
        first_col, last_col = parse_columns(columns)
        if rows[0] <= header_rows[1]:
            raise ValueError("linha selecionada dentro do bloco de cabeçalho")
        for part in slices:
            if len(part) == 0 or part.start < 0 or part[-1] >= len(rows):
                raise ValueError(f"recorte fora da seleção: {part}")
        heights: dict[int, float] | None = None
        if row_heights_pt is not None:
            values = [float(h) for h in row_heights_pt]
            if len(values) != len(rows) or any(h <= 0 for h in values):
                raise ValueError("row_heights_pt deve ter uma altura positiva por linha")
            heights = dict(zip(rows, values, strict=True))
        elif row_height_pt is not None:
            heights = dict.fromkeys(rows, float(row_height_pt))
        return self._retrying(lambda: self._render_slices(
            xlsx_path, sheet, rows, slices, first_col, last_col, header_rows, heights,
            filter_columns, normalize_data_font))

    def _render_slices(self, xlsx_path: Path | str, sheet: str, rows: list[int],
                       slices: Sequence[range], first_col: str, last_col: str,
                       header_rows: tuple[int, int], heights: dict[int, float] | None,
                       filter_columns: str | None, normalize_data_font: bool) -> list[bytes]:
        h_first, h_last = header_rows
        ws = self._sheet(xlsx_path, sheet)
        # Tem de vir ANTES de medir a última linha: End(xlUp) pula linhas ocultas pelo
        # filtro salvo (bug corrigido na prova).
        self._reset(ws)
        last = max(int(ws.Cells(ws.Rows.Count, first_col).End(XL_UP).Row), rows[-1])
        original_heights: dict[int, float] = {}
        original_bold: dict[str, Any] = {}
        try:
            if filter_columns:
                f_first, f_last = parse_columns(filter_columns)
                ws.Range(f"{f_first}{h_last}:{f_last}{last}").AutoFilter(Field=1)
            if h_last + 1 <= last:
                ws.Range(f"A{h_last + 1}:A{last}").EntireRow.Hidden = True
            for r in rows:
                ws.Rows(r).Hidden = False
            if heights is not None:
                for r in rows:
                    original_heights[r] = float(ws.Rows(r).RowHeight)
                    ws.Rows(r).RowHeight = heights[r]
            if normalize_data_font:
                original_bold.update(self._normalize_bold(ws, rows, first_col, last_col))
            out: list[bytes] = []
            for part in slices:
                wanted = {rows[i] for i in part}
                for r in rows:
                    ws.Rows(r).Hidden = r not in wanted
                rng = ws.Range(f"{first_col}{h_first}:{last_col}{rows[part[-1]]}")
                out.append(self._copy_picture(rng))
            return out
        finally:
            with contextlib.suppress(Exception):
                for r, height in original_heights.items():
                    ws.Rows(r).RowHeight = height
            with contextlib.suppress(Exception):
                for address, bold in original_bold.items():
                    ws.Range(address).Font.Bold = bold
            with contextlib.suppress(Exception):
                self._reset(ws)

    @staticmethod
    def _normalize_bold(ws: Any, rows: Sequence[int], first_col: str,
                        last_col: str) -> dict[str, Any]:
        """Tira o negrito das linhas de dados; devolve {endereço: negrito original} para
        restaurar (linha inteira quando uniforme; célula a célula quando misto)."""
        saved: dict[str, Any] = {}
        for r in rows:
            rng = ws.Range(f"{first_col}{r}:{last_col}{r}")
            bold = rng.Font.Bold
            if bold is None:                         # misto: guarda célula a célula
                for cell in rng.Cells:
                    saved[str(cell.Address)] = cell.Font.Bold
            elif bold:
                saved[str(rng.Address)] = bold
            else:
                continue
            rng.Font.Bold = False
        return saved

    def _copy_picture(self, rng: Any) -> bytes:
        clear_clipboard()
        for _attempt in range(self.copy_retries):
            try:
                rng.CopyPicture(Appearance=APPEARANCE[self.appearance], Format=XL_PICTURE)
                break
            except Exception:
                time.sleep(0.3)
        else:
            raise RuntimeError(f"CopyPicture falhou em {rng.Address}")
        return grab_enhmetafile()
