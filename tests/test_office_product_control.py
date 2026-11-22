"""Excel real (marcador `office`): gera o Controle de Produtos 2.1 do Relatório G2 nº 14 a partir
do snapshot v335.0 da Lista Mestra (DEC-008) e compara o frame com o EMF histórico.

Pula se não houver Windows/pywin32/Excel ou se as fontes locais (gitignored, em `tmp/`) faltarem.
As fontes são só lidas; a planilha é aberta ReadOnly e nunca salva. Saída só em `tmp_path`.
"""

import os
import re
import struct
import sys
from pathlib import Path

import pytest
import yaml

from prog_g2_report import REPO_ROOT
from prog_g2_report.render.docx_emf import emf_bounds
from prog_g2_report.render.product_control import build_product_control
from prog_g2_report.sources import master_list

pytestmark = pytest.mark.office

CODE = re.compile(r"^[A-Z]{2,3}-\d{3}\.\d$")


def _tmp_roots():
    env = os.environ.get("PROG_G2_TMP_DIR")
    if env:
        yield Path(env)
    yield REPO_ROOT / "tmp"
    if REPO_ROOT.parent.name == "worktrees":            # worktree: fontes no checkout principal
        yield REPO_ROOT.parents[2] / "tmp"


def _find(relative):
    for root in _tmp_roots():
        if (root / relative).is_file():
            return root / relative
    pytest.skip(f"fonte local ausente: tmp/{relative}")


def _texts(emf):
    out, off = [], 0
    while off + 8 <= len(emf):
        rtype, rsize = struct.unpack_from("<II", emf, off)
        if rsize < 8:
            break
        if rtype == 84:  # EMR_EXTTEXTOUTW
            nchars, offstr = struct.unpack_from("<II", emf, off + 44)
            out.append(emf[off + offstr:off + offstr + 2 * nchars].decode("utf-16-le", "replace"))
        off += rsize
    return out


def test_excel_renders_p21_of_report_14_like_history(tmp_path):
    if sys.platform != "win32":
        pytest.skip("Excel COM só no Windows")
    pytest.importorskip("win32com.client")
    pytest.importorskip("win32clipboard")
    from docx import Document

    from prog_g2_report.office.excel_emf import ExcelEmfRenderer, _wait_process_exit

    source = _find("historical_sources/lista_mestre_v335.0.xlsx")
    historical = _find("agent_A/hist_14/01_image11.emf").read_bytes()
    model = yaml.safe_load((REPO_ROOT / "config" / "g2_report_model.yaml").read_text("utf-8"))

    rows = master_list.select(master_list.load(source), 14, "2.1")
    assert rows, "snapshot sem linhas do 2.1 no nº 14"

    doc = Document()
    try:
        renderer = ExcelEmfRenderer()
        renderer.__enter__()
    except Exception as exc:  # Excel ausente ou sessão sem COM
        pytest.skip(f"Excel indisponível: {type(exc).__name__}")
    pid = renderer._pid
    try:
        result = build_product_control(doc.add_paragraph, rows, source, model, renderer)
        header_pt = renderer.measure(source, "Controle Geral", "D:I", (1, 3)).header_height_pt
    finally:
        renderer.__exit__(None, None, None)

    assert result.status == "OK", result.detail
    assert result.facts["slices"] == [len(rows)]
    assert result.facts["documents"] == [r.document for r in rows]
    # DEC-010 §4 (min_autofit): o histórico tem altura uniforme 27,6 pt e corta a 3ª linha do
    # NT-765.1; o gerado cresce só as linhas que precisam (AutoFit medido via COM).
    assert result.facts["row_heights_source"] == "excel_autofit"
    extra_pt = sum(h - 27.6 for h in result.facts["tall_rows"].values())

    out = tmp_path / "p21.docx"
    doc.save(out)
    blobs = [p.blob for p in Document(out).part.package.parts if p.content_type == "image/x-emf"]
    assert len(blobs) == 1
    generated, hist = emf_bounds(blobs[0]), emf_bounds(historical)

    # largura e topo idênticos ao histórico (0,01 mm / 1 px); a altura cresce exatamente o que
    # as linhas acima do mínimo somam, na escala do próprio histórico
    hist_w, hist_h = hist.frame_cm
    gen_w, gen_h = generated.frame_cm
    assert gen_w == pytest.approx(hist_w, abs=0.001)
    uniform_pt = header_pt + 27.6 * len(rows)
    assert gen_h == pytest.approx(hist_h * (uniform_pt + extra_pt) / uniform_pt, abs=0.005)
    for a, b in zip(generated[:3], hist[:3], strict=True):
        assert abs(a - b) <= 1
    px_per_pt = (hist.bottom - hist.top) / uniform_pt
    assert abs((generated.bottom - hist.bottom) - extra_pt * px_per_pt) <= 1.5
    assert generated.device_px == hist.device_px
    # mesmos documentos, na mesma ordem, no conteúdo vetorial
    assert [t for t in _texts(blobs[0]) if CODE.match(t)] == [t for t in _texts(historical)
                                                             if CODE.match(t)]
    assert [t for t in _texts(blobs[0]) if CODE.match(t)] == result.facts["documents"]
    if pid:  # o __exit__ já esperou (e encerrou, se preciso): aqui o processo tem de ter saído
        assert _wait_process_exit(pid, 2.0), "processo do Excel continuou vivo após o __exit__"


def _bold_workbook(path):
    """Planilha SINTÉTICA no layout do Controle Geral: título e cabeçalho (linhas 1–3) em
    negrito e células de dados com negrito herdado na 2ª coluna (E), como no QA-D do nº 14."""
    openpyxl = pytest.importorskip("openpyxl")
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Controle Geral"
    ws["D1"] = "Programa | Controle Sintético"
    ws["D1"].font = Font(bold=True)
    for col, label in zip("DEFGHI", ["Doc", "Tipo", "Descr", "Obra", "Data", "Status"],
                          strict=True):
        ws[f"{col}3"] = label
        ws[f"{col}3"].font = Font(bold=True)
    data = []
    for r in range(4, 10):
        values = [f"NT-{r:03d}.1", f"Tipo {r}", f"Descrição {r}", "RD-000", "01/01/2027", "Ok"]
        for col, value in zip("DEFGHI", values, strict=True):
            ws[f"{col}{r}"] = value
        if r % 2 == 0:
            ws[f"E{r}"].font = Font(bold=True)                 # negrito espúrio
        data += values
    wb.save(path)
    return ["Programa | Controle Sintético", "Doc", "Tipo", "Descr", "Obra", "Data", "Status"], data


def test_excel_normalizes_data_font_only_in_memory(tmp_path):
    """`render_params.normalize_data_font` (DEC-007): no EMF, só título e cabeçalho em negrito;
    a planilha não é alterada no disco."""
    if sys.platform != "win32":
        pytest.skip("Excel COM só no Windows")
    pytest.importorskip("win32com.client")
    pytest.importorskip("win32clipboard")
    import hashlib

    from prog_g2_report.office.excel_emf import ExcelEmfRenderer
    from prog_g2_report.render.docx_emf import emf_text_runs

    path = tmp_path / "controle_sintetico.xlsx"
    header, data = _bold_workbook(path)
    before = hashlib.sha1(path.read_bytes()).hexdigest()
    try:
        renderer = ExcelEmfRenderer()
        renderer.__enter__()
    except Exception as exc:
        pytest.skip(f"Excel indisponível: {type(exc).__name__}")
    try:
        rows = list(range(4, 10))
        kwargs = {"columns": "D:I", "header_rows": (1, 3), "row_height_pt": 27.6,
                  "filter_columns": None}
        raw = renderer.render_slices(path, "Controle Geral", rows, [range(0, 6)], **kwargs)[0]
        fixed = renderer.render_slices(path, "Controle Geral", rows, [range(0, 6)],
                                       normalize_data_font=True, **kwargs)[0]
        again = renderer.render_slices(path, "Controle Geral", rows, [range(0, 6)], **kwargs)[0]
    finally:
        renderer.__exit__(None, None, None)

    def bold_texts(emf):
        return {r.text.strip() for r in emf_text_runs(emf) if r.bold and r.text.strip()}

    def plain_texts(emf):
        return {r.text.strip() for r in emf_text_runs(emf) if not r.bold and r.text.strip()}

    assert bold_texts(raw) & set(data), "controle: sem normalizar, o negrito herdado aparece"
    assert bold_texts(fixed) == set(header)            # só título e cabeçalho
    assert set(data) <= plain_texts(fixed)
    assert bold_texts(again) == bold_texts(raw)        # restaurado na cópia em memória
    assert hashlib.sha1(path.read_bytes()).hexdigest() == before   # nunca salva


LONG_DESCRIPTION = ("Nota Técnica Sintética de Análise de Projeto Executivo - Projeto Fictício de "
                    "Teste e Projeto Fictício de Verificação de Altura de Linha Longa Demais")


def _long_description_workbook(path):
    """Planilha SINTÉTICA: 4 linhas de dados com quebra automática; a 2ª tem uma Descrição de
    4 linhas (o caso do NT-688.1/PA-672.1 do nº 13, exagerado)."""
    openpyxl = pytest.importorskip("openpyxl")
    from openpyxl.styles import Alignment, Font

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Controle Geral"
    ws["D1"] = "Controle Sintético"
    for col, width in {"D": 13, "E": 22, "F": 42, "G": 14, "H": 13, "I": 14}.items():
        ws.column_dimensions[col].width = width
    for col, label in zip("DEFGHI", ["Doc", "Tipo", "Descr", "Obra", "Data", "Status"],
                          strict=True):
        ws[f"{col}3"] = label
    for r in range(4, 8):
        values = [f"NT-{900 + r}.1", "Nota Técnica",
                  LONG_DESCRIPTION if r == 5 else f"Descrição curta {r}", "RD-000",
                  "01/01/2027", "Entregue"]
        for col, value in zip("DEFGHI", values, strict=True):
            cell = ws[f"{col}{r}"]
            cell.value = value
            cell.font = Font(name="Arial", size=11)
            cell.alignment = Alignment(wrap_text=True, vertical="center")
    wb.save(path)


def _text_bounds(emf):
    """(texto, rclBounds) de cada EMR_EXTTEXTOUTW, na ordem do desenho."""
    out, off = [], 0
    while off + 8 <= len(emf):
        rtype, rsize = struct.unpack_from("<II", emf, off)
        if rsize < 8:
            break
        if rtype == 84:
            bounds = struct.unpack_from("<iiii", emf, off + 8)
            nchars, offstr = struct.unpack_from("<II", emf, off + 44)
            text = emf[off + offstr:off + offstr + 2 * nchars].decode("utf-16-le", "replace")
            out.append((text, bounds))
        off += rsize
    return out


def test_long_description_grows_the_row_and_is_never_cut(tmp_path):
    """DEC-010 §4 (`row_height_mode: min_autofit`): a linha da descrição longa cresce para o
    AutoFit do Excel; no EMF todas as palavras são desenhadas e nenhum EXTTEXTOUTW sai do
    retângulo da sua linha (topo/base pelas alturas aplicadas). Controle: com a altura uniforme
    antiga (27,6 pt) a descrição sai cortada (o Excel nem desenha as linhas que não cabem)."""
    if sys.platform != "win32":
        pytest.skip("Excel COM só no Windows")
    pytest.importorskip("win32com.client")
    pytest.importorskip("win32clipboard")
    import hashlib

    from prog_g2_report.office.excel_emf import ExcelEmfRenderer

    path = tmp_path / "controle_descricao_longa.xlsx"
    _long_description_workbook(path)
    before = hashlib.sha1(path.read_bytes()).hexdigest()
    rows = [4, 5, 6, 7]
    try:
        renderer = ExcelEmfRenderer()
        renderer.__enter__()
    except Exception as exc:
        pytest.skip(f"Excel indisponível: {type(exc).__name__}")
    try:
        heights = renderer.measure_row_heights(path, "Controle Geral", rows, columns="D:I",
                                               min_height_pt=27.6)
        geometry = renderer.measure(path, "Controle Geral", "D:I", (1, 3))
        common = {"columns": "D:I", "header_rows": (1, 3), "filter_columns": None}
        grown = renderer.render_slices(path, "Controle Geral", rows, [range(0, 4)],
                                       row_heights_pt=heights, **common)[0]
        uniform = renderer.render_slices(path, "Controle Geral", rows, [range(0, 4)],
                                         row_height_pt=27.6, **common)[0]
    finally:
        renderer.__exit__(None, None, None)

    assert heights[0] == heights[2] == heights[3] == 27.6          # mínimo do nº 14
    assert heights[1] > 27.6 * 1.5                                 # 4 linhas de texto
    assert hashlib.sha1(path.read_bytes()).hexdigest() == before   # nunca salva

    def rows_and_description(emf, row_heights):
        header = emf_bounds(emf)
        total_pt = geometry.header_height_pt + sum(row_heights)
        per_pt = (header.bottom - header.top) / total_pt          # unidades lógicas por pt
        tops, y = [], geometry.header_height_pt
        for h in row_heights:
            tops.append((y * per_pt, (y + h) * per_pt))
            y += h
        description = []
        for text, (_left, top, _right, bottom) in _text_bounds(emf):
            if not text.strip() or top < geometry.header_height_pt * per_pt - 1:
                continue                                            # título e cabeçalho
            row = next(i for i, (t, b) in enumerate(tops) if t - 1 <= top <= b + 1)
            row_top, row_bottom = tops[row]
            assert row_top - 1.5 <= top and bottom <= row_bottom + 1.5, (text, tops[row])
            if row == 1 and text.strip() not in {"NT-905.1", "Nota Técnica", "RD-000",
                                                 "01/01/2027", "Entregue"}:
                description.append((top, text))
        return " ".join(t for _, t in sorted(description)).split()

    assert rows_and_description(grown, heights) == LONG_DESCRIPTION.split()
    cut = rows_and_description(uniform, [27.6] * 4)
    assert cut != LONG_DESCRIPTION.split() and cut == LONG_DESCRIPTION.split()[:len(cut)]


def test_excel_survives_word_export_and_reconnects(tmp_path):
    """Bug da 2ª passada (nº 14): a exportação do Word não pode desconectar o Excel aberto;
    se a pasta ou o Excel caírem mesmo assim, o renderizador reabre/recria sozinho."""
    if sys.platform != "win32":
        pytest.skip("Excel/Word COM só no Windows")
    pytest.importorskip("win32com.client")
    pytest.importorskip("win32clipboard")
    import pythoncom
    from docx import Document

    from prog_g2_report.builder import word_pdf
    from prog_g2_report.office.excel_emf import ExcelEmfRenderer, _wait_process_exit

    path = tmp_path / "controle_sintetico.xlsx"
    _bold_workbook(path)
    docx_path = tmp_path / "curto.docx"
    doc = Document()
    doc.add_paragraph("Documento sintético para a exportação do Word.")
    doc.save(docx_path)
    rows, kwargs = list(range(4, 10)), {"filter_columns": None}
    try:
        renderer = ExcelEmfRenderer()
        renderer.__enter__()
    except Exception as exc:
        pytest.skip(f"Excel indisponível: {type(exc).__name__}")
    pids = []
    try:
        first = renderer.render_slices(path, "Controle Geral", rows, [range(0, 6)], **kwargs)
        pids.append(renderer._pid)
        # 1) o par pythoncom que derrubava o apartamento + a exportação real do Word
        pythoncom.CoInitialize()
        pythoncom.CoUninitialize()
        assert word_pdf.export_pdf(docx_path, tmp_path / "curto.pdf") >= 1
        workbook = next(iter(renderer._workbooks.values()))
        assert renderer._alive(renderer._excel) and renderer._alive(workbook)
        del workbook
        split = renderer.render_slices(path, "Controle Geral", rows,
                                       [range(0, 2), range(2, 6)], **kwargs)
        assert len(split) == 2 and renderer.reopened == 0 and renderer.restarts == 0
        # 2) pasta fechada por fora: o proxy guardado fica desconectado -> reabre
        renderer._excel.Workbooks(1).Close(False)
        again = renderer.render_slices(path, "Controle Geral", rows, [range(0, 6)], **kwargs)
        assert renderer.reopened == 1 and len(again) == 1
        # 3) processo do Excel morto -> nova instância própria
        os.kill(renderer._pid, 9)
        assert _wait_process_exit(pids[0], 10.0)
        last = renderer.render_slices(path, "Controle Geral", rows, [range(0, 6)], **kwargs)
        assert renderer.restarts == 1 and len(last) == 1
        pids.append(renderer._pid)
        assert len(first[0]) > 0
    finally:
        renderer.__exit__(None, None, None)
    for pid in pids:
        if pid:
            assert _wait_process_exit(pid, 5.0), "processo do Excel continuou vivo"
