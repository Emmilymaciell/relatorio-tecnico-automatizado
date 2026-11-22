"""FASE 4 / GAP-001 — sonda: gerar o EMF do Controle de Produtos pelo Excel.

    .venv\\Scripts\\python scripts\\12_probe_emf_export.py --report 14
    .venv\\Scripts\\python scripts\\12_probe_emf_export.py --report 14 --split 2.2=25,23 --appearance screen,printer
    .venv\\Scripts\\python scripts\\12_probe_emf_export.py --report 14 --appearance screen --row-height 27.6 \\
        --tag _h276 --split 2.2=25,23 --split 2.4=32,34,32 --split ANEXOS=31,31,39,33,15

Resultado medido (2026-10-01, snapshot v335.0): xlScreen + linhas a 27,6 pt reproduz os 11 recortes
do Relatório G2 nº 14 com rclFrame idêntico ao histórico (22,091 cm × altura, 0,001 cm) e as mesmas
linhas; xlPrinter não serve (frame 26,694 cm, quebra de texto e altura diferentes).

O Controle de Produtos do relatório é um recorte do Excel colado como **metarquivo (EMF)**.
Esta sonda prova a cadeia completa, sem construir nada definitivo:

    Lista Mestra (cópia local, ReadOnly) → filtro explícito em memória
      (N° Relatório == N e Produto começa com 2.X; índice dos anexos só N° Relatório == N)
    → intervalo D:I da aba 'Controle Geral' (linhas 1..3 de título/cabeçalho + linhas do recorte)
    → Range.CopyPicture(Appearance, xlPicture) → área de transferência
    → CF_ENHMETAFILE (14) lido com win32clipboard → bytes EMF gravados em disco.

Achado que motivou a reescrita: o caminho antigo `Chart.Paste` + `Chart.Export(..., "EMF")`
**não funciona** — gera arquivo de 0 bytes (o filtro gráfico de exportação do Excel não tem
EMF). Ele foi removido. O caminho correto é ler o metarquivo direto da área de transferência.

Segurança:
- abre sempre uma cópia em tmp/ com ReadOnly=True; o filtro salvo no arquivo é descartado e
  substituído pelo filtro explícito (DEC-009: filtro salvo não é verdade); **nunca salva**;
- usa uma instância própria do Excel (DispatchEx), fecha com SaveChanges=False e chama Quit;
- grava somente em tmp/renders/emf_probe/ (assert_write_allowed).
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import json
import struct
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prog_g2_report import REPO_ROOT
from prog_g2_report.security import assert_write_allowed

DEFAULT_SOURCES = {
    14: REPO_ROOT / "tmp" / "historical_sources" / "lista_mestre_v335.0.xlsx",  # DEC-008
    13: REPO_ROOT / "tmp" / "historical_sources" / "lista_mestre_v134.0.xlsx",  # DEC-008
}
CURRENT_SOURCE = REPO_ROOT / "tmp" / "downloads" / "fontes_de_trabalho" / "00_ lista mestre.xlsx"
OUT = REPO_ROOT / "tmp" / "renders" / "emf_probe"

SHEET = "Controle Geral"
HEADER_ROW = 3          # linha de cabeçalho; linhas 1..3 entram em todo recorte (título + cabeçalho)
FIRST_COL, LAST_COL = "D", "I"   # Documento .. Status Entrega
FILTER_FIRST_COL = "B"  # autofiltro histórico cobre B..M
COL_PRODUTO = 2         # B
COL_RELATORIO = 11      # K

CF_ENHMETAFILE = 14
XL_PICTURE = -4147
APPEARANCE = {"screen": 1, "printer": 2}   # xlScreen, xlPrinter
BLOCKS = ("2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "ANEXOS")


# ---------------------------------------------------------------- seleção (pura, testável offline)
def _as_int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def select_rows(values: list[tuple], first_row: int, report: int, block: str) -> list[int]:
    """Linhas físicas (1-based) do bloco, na ordem física da planilha (ordem canônica).

    `values` são as linhas a partir de `first_row`, colunas A.. (tupla 0-based).
    """
    out = []
    for offset, row in enumerate(values):
        if _as_int(row[COL_RELATORIO - 1]) != report:
            continue
        produto = str(row[COL_PRODUTO - 1] or "").strip()
        if block != "ANEXOS" and not produto.startswith(block):
            continue
        out.append(first_row + offset)
    return out


def chunk(rows: list[int], sizes: list[int] | None) -> list[list[int]]:
    if not sizes:
        return [rows]
    if sum(sizes) != len(rows):
        raise ValueError(f"split {sizes} soma {sum(sizes)} ≠ {len(rows)} linhas")
    out, i = [], 0
    for n in sizes:
        out.append(rows[i:i + n])
        i += n
    return out


# ---------------------------------------------------------------- área de transferência
def _open_clipboard(cb, tries: int = 50) -> None:
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
    """Bytes do CF_ENHMETAFILE atual. pywin32 312 devolve bytes; se vier handle, usa GDI."""
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


# ---------------------------------------------------------------- inspeção mínima do EMF
def emf_summary(data: bytes) -> dict:
    off, counts, fonts, texts = 0, Counter(), Counter(), 0
    head = {}
    while off + 8 <= len(data):
        rtype, rsize = struct.unpack_from("<II", data, off)
        if rsize < 8:
            break
        counts[rtype] += 1
        if rtype == 1:
            frame = struct.unpack_from("<4i", data, off + 24)
            head = {
                "bounds_px": struct.unpack_from("<4i", data, off + 8),
                "frame_01mm": frame,
                "frame_cm": [(frame[2] - frame[0]) / 1000, (frame[3] - frame[1]) / 1000],
                "device_px": struct.unpack_from("<2i", data, off + 72),
                "device_mm": struct.unpack_from("<2i", data, off + 80),
            }
        elif rtype == 82:  # EXTCREATEFONTINDIRECTW
            height, weight = struct.unpack_from("<i", data, off + 12)[0], struct.unpack_from("<i", data, off + 28)[0]
            face = data[off + 40:off + 104].decode("utf-16-le", "replace").split("\x00")[0]
            fonts[f"{face}|{height}|{weight}"] += 1
        elif rtype == 84:  # EXTTEXTOUTW
            texts += 1
        off += rsize
    return {
        "bytes": len(data), **head, "records": sum(counts.values()), "exttextoutw": texts,
        "bitmap_records": sum(counts[t] for t in (76, 77, 80, 81, 114, 116)),
        "fonts": dict(fonts),
    }


# ---------------------------------------------------------------- Excel
def _excel_pid(excel) -> int | None:
    try:
        import win32process

        return win32process.GetWindowThreadProcessId(excel.Hwnd)[1]
    except Exception:
        return None


def run(source: Path, report: int, blocks: list[str], appearances: list[str],
        splits: dict[str, list[int]], arrows: bool, row_height: float | None = None,
        tag: str = "") -> int:
    import pythoncom
    import win32com.client as com

    assert_write_allowed(OUT / "x")
    OUT.mkdir(parents=True, exist_ok=True)
    pythoncom.CoInitialize()
    excel = workbook = None
    manifest = {"source": str(source.relative_to(REPO_ROOT)), "report": report, "outputs": []}
    try:
        excel = com.DispatchEx("Excel.Application")   # instância própria, nunca a da usuária
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.ScreenUpdating = True
        manifest["excel_version"] = excel.Version
        manifest["excel_pid"] = _excel_pid(excel)
        print(f"[1] Excel {excel.Version} (pid {manifest['excel_pid']})")

        workbook = excel.Workbooks.Open(str(source.resolve()), UpdateLinks=0, ReadOnly=True,
                                        IgnoreReadOnlyRecommended=True, Notify=False, AddToMru=False)
        sheet = workbook.Worksheets(SHEET)
        # Filtro salvo NÃO é verdade (DEC-009): descarta e refaz, só em memória. Tem de vir
        # ANTES de medir a última linha: End(xlUp) pula linhas ocultas pelo filtro salvo.
        manifest["saved_autofilter"] = sheet.AutoFilter.Range.Address if sheet.AutoFilterMode else None
        if sheet.AutoFilterMode:
            sheet.AutoFilterMode = False
        sheet.Rows.Hidden = False
        last = sheet.Cells(sheet.Rows.Count, FIRST_COL).End(-4162).Row   # xlUp
        values = sheet.Range(f"A{HEADER_ROW + 1}:M{last}").Value2
        header = [sheet.Cells(HEADER_ROW, c).Value2 for c in range(4, 10)]
        print(f"[2] {source.name}: aba {SHEET!r}, dados até a linha {last}; cabeçalho D:I = {header}")
        manifest["header_D_I"] = header
        filt = sheet.Range(f"{FILTER_FIRST_COL}{HEADER_ROW}:M{last}")
        rel_field = COL_RELATORIO - (ord(FILTER_FIRST_COL) - ord("A"))
        prod_field = COL_PRODUTO - (ord(FILTER_FIRST_COL) - ord("A"))

        for block in blocks:
            rows = select_rows(list(values), HEADER_ROW + 1, report, block)
            print(f"[3] bloco {block}: {len(rows)} linhas (Lista Mestra, filtro explícito)")
            if not rows:
                manifest["outputs"].append({"block": block, "rows": 0})
                continue
            # autofiltro só para reproduzir as setas do histórico; a seleção é a de select_rows
            if sheet.AutoFilterMode:
                sheet.AutoFilterMode = False
            sheet.Rows.Hidden = False
            if arrows:
                filt.AutoFilter(Field=rel_field, Criteria1=str(report))
                if block != "ANEXOS":
                    filt.AutoFilter(Field=prod_field, Criteria1=f"{block}*")
            wanted = set(rows)
            diverge = []
            for r in range(HEADER_ROW + 1, last + 1):
                hidden = bool(sheet.Rows(r).Hidden)
                if (r in wanted) == hidden:
                    diverge.append(r)
                    sheet.Rows(r).Hidden = r not in wanted
            if arrows and diverge:
                raise RuntimeError(f"autofiltro do Excel diverge da seleção em {len(diverge)} linhas: {diverge[:10]}")
            if row_height:
                # nº 14 histórico: todas as linhas com 27,6 pt; o snapshot salvo mistura 13,8 e 27,6.
                for r in rows:
                    sheet.Rows(r).RowHeight = row_height
            for k, part in enumerate(chunk(rows, splits.get(block)), start=1):
                # esconde as linhas selecionadas que não são deste recorte
                for r in rows:
                    sheet.Rows(r).Hidden = r not in part
                rng = sheet.Range(f"{FIRST_COL}1:{LAST_COL}{part[-1]}")
                for app in appearances:
                    clear_clipboard()
                    for _attempt in range(5):
                        try:
                            rng.CopyPicture(Appearance=APPEARANCE[app], Format=XL_PICTURE)
                            break
                        except Exception:
                            time.sleep(0.3)
                    else:
                        raise RuntimeError(f"CopyPicture falhou ({block} {k} {app})")
                    data = grab_enhmetafile()
                    name = f"r{report:02d}_{block.replace('.', '')}_{k:02d}_{app}{tag}.emf"
                    dest = OUT / name
                    assert_write_allowed(dest)
                    dest.write_bytes(data)
                    info = {"block": block, "slice": k, "appearance": app, "file": name,
                            "excel_rows": [part[0], part[-1]], "rows": len(part),
                            "range": rng.Address.replace("$", ""), **emf_summary(data)}
                    manifest["outputs"].append(info)
                    print(f"    {name}: {info['bytes']} B, frame {info['frame_cm']} cm, "
                          f"{info['exttextoutw']} textos, {info['bitmap_records']} reg. bitmap")
                for r in rows:
                    sheet.Rows(r).Hidden = False
        manifest["row_height_pt"] = row_height
        (OUT / f"r{report:02d}_manifest{tag}.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1, default=list), encoding="utf-8")
        print(f"\nRESULTADO: {len([o for o in manifest['outputs'] if o.get('bytes')])} EMF(s) "
              f"capturados de CF_ENHMETAFILE em {OUT.relative_to(REPO_ROOT)}")
        return 0
    except Exception as exc:
        print(f"  falhou: {type(exc).__name__}: {exc}")
        return 4
    finally:
        with contextlib.suppress(Exception):
            clear_clipboard()
        try:
            if workbook is not None:
                workbook.Close(SaveChanges=False)
        finally:
            if excel is not None:
                excel.Quit()
            excel = workbook = None
            pythoncom.CoUninitialize()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", type=int, default=14)
    ap.add_argument("--source", type=Path, help="cópia local da Lista Mestra (default: snapshot DEC-008)")
    ap.add_argument("--blocks", default="2.1,2.2,2.4,ANEXOS")
    ap.add_argument("--appearance", default="screen,printer")
    ap.add_argument("--split", action="append", default=[],
                    help="BLOCO=n1,n2,... linhas por recorte (ex.: 2.2=25,23); default: recorte único")
    ap.add_argument("--no-arrows", action="store_true", help="não aplicar autofiltro (sem setas)")
    ap.add_argument("--row-height", type=float, help="altura uniforme (pt) das linhas do recorte, só em memória")
    ap.add_argument("--tag", default="", help="sufixo dos arquivos gerados")
    a = ap.parse_args()
    source = a.source or DEFAULT_SOURCES.get(a.report, CURRENT_SOURCE)
    if not source.exists():
        print(f"planilha ausente: {source}")
        return 1
    try:
        import win32clipboard  # noqa: F401
        import win32com.client  # noqa: F401
    except ImportError:
        print("pywin32 não instalado: `pip install -e \".[office]\"`")
        return 2
    splits = {}
    for s in a.split:
        block, sizes = s.split("=")
        splits[block] = [int(n) for n in sizes.split(",")]
    blocks = [b for b in a.blocks.split(",") if b in BLOCKS]
    return run(source, a.report, blocks, a.appearance.split(","), splits, not a.no_arrows,
               a.row_height, a.tag)


if __name__ == "__main__":
    sys.exit(main())
