"""Atualização de campos e exportação PDF pelo Microsoft Word (COM), dependência de ambiente.

TOC e PAGE só são calculados pelo Word (BUILDER_PLAN, "Riscos já conhecidos"). Usa uma instância
própria e isolada (`DispatchEx`), invisível, sem alertas, e sempre a encerra. Não toca na área
de transferência. O DOCX gerado é aberto somente leitura e nunca sobrescrito.

Cópia final (`final_docx_path`): depois de atualizar campos e sumário, o Word salva o documento
como um ARQUIVO NOVO (`SaveAs2`, `<stem>_final.docx`), antes da exportação do PDF (que pode
desconectar a instância). O builder tira dessa cópia o `w:updateFields` de `settings.xml`
(`strip_update_fields`): os campos já estão atualizados, então o Word não pergunta nada ao
abri-la. O DOCX gerado mantém o `updateFields` (ooxml_base.settings), porque os campos dele são
provisórios.

Comportamento observado neste ambiente (Word 16, 2026-10): depois de `ExportAsFixedFormat` de um
documento com SDT de sumário — inclusive o DOCX histórico do nº 14 — a instância se desconecta
(RPC_E_DISCONNECTED) e o processo pode ficar órfão. O PDF sai íntegro. Por isso a contagem de
páginas é lida antes da exportação, o fechamento tolera a desconexão e o processo da instância
criada aqui (identificado pelo PID) é encerrado se sobreviver.

COM: a inicialização é a balanceada de `office.com_apartment` (ole32 direto), nunca o par
`pythoncom.CoInitialize`/`CoUninitialize`: na thread que importou o pythoncom, esse
`CoUninitialize` desfaz a inicialização inteira e desconectava o Excel do Controle de Produtos,
que fica aberto entre as passadas do montador (CO_E_OBJNOTCONNECTED na 2ª passada).
"""

from __future__ import annotations

import contextlib
import os
import re
import time
import zipfile
from pathlib import Path

WD_EXPORT_FORMAT_PDF = 17
WD_STATISTIC_PAGES = 2
WD_DO_NOT_SAVE_CHANGES = 0
WD_ALERTS_NONE = 0
WD_EXPORT_CREATE_HEADING_BOOKMARKS = 1
WD_FORMAT_DOCUMENT_DEFAULT = 16           # .docx
RPC_E_DISCONNECTED = -2147417848
SETTINGS_PART = "word/settings.xml"
_UPDATE_FIELDS = re.compile(rb"<w:updateFields\b[^>]*/>")


def strip_update_fields(docx_path: Path) -> bool:
    """Remove `<w:updateFields …/>` de `word/settings.xml` (reescreve o pacote no mesmo caminho,
    que é saída do builder, nunca fonte). Devolve True se havia o elemento."""
    from prog_g2_report.security import assert_write_allowed

    docx_path = Path(docx_path)
    assert_write_allowed(docx_path)
    with zipfile.ZipFile(docx_path) as source:
        items = [(info, source.read(info.filename)) for info in source.infolist()]
    changed = False
    out: list[tuple[zipfile.ZipInfo, bytes]] = []
    for info, data in items:
        if info.filename == SETTINGS_PART:
            data, count = _UPDATE_FIELDS.subn(b"", data)
            changed = count > 0
        out.append((info, data))
    if not changed:
        return False
    tmp = docx_path.with_name(docx_path.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as target:
        for info, data in out:
            target.writestr(info, data)
    os.replace(tmp, docx_path)
    return True


def word_available() -> bool:
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        return False
    return True


def _word_pids() -> set[int]:
    import win32com.client

    wmi = win32com.client.GetObject("winmgmts:")
    query = "select ProcessId from Win32_Process where Name='WINWORD.EXE'"
    return {int(p.ProcessId) for p in wmi.ExecQuery(query)}


def _terminate(pids: set[int], grace_s: float = 5.0) -> None:
    """Encerra só as instâncias criadas por esta chamada, se não saírem sozinhas."""
    import subprocess

    deadline = time.monotonic() + grace_s
    while pids and time.monotonic() < deadline:
        pids &= _word_pids()
        if pids:
            time.sleep(0.5)
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, check=False)


def export_pdf(docx_path: Path, pdf_path: Path, *, update_fields: bool = True,
               final_docx_path: Path | None = None) -> int:
    """Abre `docx_path` no Word, atualiza TOC e campos, exporta `pdf_path`; devolve as páginas.
    `final_docx_path`: salva também a cópia com os campos atualizados (`SaveAs2`, arquivo novo,
    nunca o `docx_path`)."""
    import pywintypes
    import win32com.client

    from prog_g2_report.office.com_apartment import ComApartment

    docx_path, pdf_path = Path(docx_path).resolve(), Path(pdf_path).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if pdf_path.exists():
        pdf_path.unlink()
    final = Path(final_docx_path).resolve() if final_docx_path is not None else None
    if final is not None:
        if final == docx_path:
            raise ValueError("a cópia final não pode sobrescrever o DOCX gerado")
        if final.exists():
            final.unlink()
    apartment = ComApartment().enter()
    try:
        before = _word_pids()
    except BaseException:
        apartment.leave()
        raise
    word = None
    pages = 0
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = WD_ALERTS_NONE
        # Open(FileName, ConfirmConversions, ReadOnly, AddToRecentFiles)
        doc = word.Documents.Open(str(docx_path), False, True, False)
        try:
            if update_fields:
                doc.Fields.Update()
                for i in range(1, doc.TablesOfContents.Count + 1):
                    doc.TablesOfContents(i).Update()
                doc.Repaginate()
                for i in range(1, doc.TablesOfContents.Count + 1):
                    doc.TablesOfContents(i).UpdatePageNumbers()
            pages = int(doc.ComputeStatistics(WD_STATISTIC_PAGES))
            if final is not None:
                # arquivo NOVO; antes da exportação, que pode desconectar a instância
                doc.SaveAs2(FileName=str(final), FileFormat=WD_FORMAT_DOCUMENT_DEFAULT,
                            AddToRecentFiles=False)
            doc.ExportAsFixedFormat(
                OutputFileName=str(pdf_path),
                ExportFormat=WD_EXPORT_FORMAT_PDF,
                OpenAfterExport=False,
                CreateBookmarks=WD_EXPORT_CREATE_HEADING_BOOKMARKS,
                DocStructureTags=True,
            )
        finally:
            with contextlib.suppress(pywintypes.com_error):
                doc.Close(WD_DO_NOT_SAVE_CHANGES)
    finally:
        if word is not None:
            with contextlib.suppress(pywintypes.com_error):
                word.Quit(WD_DO_NOT_SAVE_CHANGES)
        word = None
        _terminate(_word_pids() - before)
        apartment.leave()
    if not pdf_path.exists():
        raise RuntimeError(f"o Word não gerou o PDF: {pdf_path}")
    return pages
