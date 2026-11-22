from pathlib import Path

import pytest

from prog_g2_report import REPO_ROOT
from prog_g2_report.security import (
    DOWNLOAD_DIR,
    ProtectedPathError,
    assert_download_destination,
    assert_write_allowed,
    is_protected_path,
)


@pytest.mark.parametrize(
    "path",
    [
        r"C:\caminho\exemplo\Dynatest Engenharia\Programa - 4. Produtos\x.docx",
        r"C:\caminho\exemplo\Dynatest Engenharia",
        r"\\?\C:\caminho\exemplo\Dynatest Engenharia\Programa - 3. Desenvolvimento\a.pdf",
        r"c:\caminho\exemplo\dynatest engenharia\qualquer",
        r"C:\caminho\exemplo\PastaSincronizada\doc.xlsx",
    ],
)
def test_sharepoint_mirror_paths_are_protected(path):
    assert is_protected_path(path)
    with pytest.raises(ProtectedPathError):
        assert_write_allowed(path)


def test_lookalike_sibling_is_not_protected():
    assert not is_protected_path(r"C:\caminho\exemplo\Dynatest Engenharia Backup\x")


def test_urls_are_never_write_targets():
    with pytest.raises(ProtectedPathError):
        assert_write_allowed("https://contoso.sharepoint.com/sites/exemplo")


def test_repo_paths_are_allowed(tmp_path: Path):
    assert assert_write_allowed(REPO_ROOT / "tmp" / "a.txt")
    assert assert_write_allowed(tmp_path / "b.txt")


def test_download_destination_restricted_to_tmp_downloads():
    assert assert_download_destination(DOWNLOAD_DIR / "x" / "a.docx")
    with pytest.raises(ProtectedPathError):
        assert_download_destination(REPO_ROOT / "output" / "a.docx")
    with pytest.raises(ProtectedPathError):
        assert_download_destination(REPO_ROOT / "assets" / "a.docx")
