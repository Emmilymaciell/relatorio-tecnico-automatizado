"""Guardas de seguranca do projeto.

Duas fronteiras sao protegidas aqui:

1. **SharePoint remoto** — `SharePointWriteBlockedError` e levantada pelo cliente Graph
   quando qualquer codigo tenta uma operacao fora da allowlist de leitura.
2. **Caminhos locais protegidos** — a biblioteca Programa tambem existe sincronizada pelo
   OneDrive em disco. Escrever la equivale a escrever no SharePoint. `assert_write_allowed`
   recusa qualquer destino de escrita dentro dessas raizes.

Regra de projeto: permissao tecnica da credencial NAO e autorizacao funcional.
"""

from __future__ import annotations

import os
from pathlib import Path

from prog_g2_report import REPO_ROOT


class SharePointWriteBlockedError(PermissionError):
    """Tentativa de operacao mutavel (ou nao allowlisted) contra o SharePoint."""


class ProtectedPathError(PermissionError):
    """Tentativa de escrita em caminho local que espelha o SharePoint."""


# Raizes locais que espelham o SharePoint corporativo (sincronizacao OneDrive).
# Qualquer escrita aqui e escrita no SharePoint. Lista fechada, sem excecoes.
PROTECTED_LOCAL_ROOTS: tuple[Path, ...] = (
    Path(r"C:\caminho\exemplo\Dynatest Engenharia"),
    Path(r"C:\caminho\exemplo\PastaSincronizada"),
    Path(r"C:\caminho\exemplo\PastaSincronizada (1)"),
    Path(r"C:\caminho\exemplo\PastaSincronizada (2)"),
)

# Unico lugar onde conteudo bruto baixado pode ser gravado (e depois apagado).
DOWNLOAD_DIR = REPO_ROOT / "tmp" / "downloads"


def _normalize(path: Path | str) -> str:
    text = str(path)
    if text.startswith("\\\\?\\"):
        text = text[4:]
    return os.path.normcase(os.path.normpath(os.path.abspath(text)))


def is_protected_path(path: Path | str) -> bool:
    """True se `path` esta dentro de uma raiz local que espelha o SharePoint."""
    target = _normalize(path)
    for root in PROTECTED_LOCAL_ROOTS:
        root_norm = _normalize(root)
        if target == root_norm or target.startswith(root_norm + os.sep):
            return True
    return False


def assert_write_allowed(path: Path | str) -> Path:
    """Garante que `path` pode receber escrita. Devolve o Path absoluto.

    Recusa raizes protegidas e URLs do SharePoint. Chamar em todo codigo que grava.
    """
    text = str(path)
    if text.lower().startswith(("http://", "https://")):
        raise ProtectedPathError(f"escrita em URL nao e permitida: {text}")
    if is_protected_path(text):
        raise ProtectedPathError(
            f"caminho espelha o SharePoint corporativo (somente leitura): {text}"
        )
    return Path(_normalize(text))


def assert_download_destination(path: Path | str) -> Path:
    """Downloads brutos so podem cair em tmp/downloads/ dentro do repositorio."""
    target = assert_write_allowed(path)
    allowed_root = _normalize(DOWNLOAD_DIR)
    if not str(target).startswith(allowed_root):
        raise ProtectedPathError(
            f"download bruto so pode ir para {DOWNLOAD_DIR}, nao para {target}"
        )
    return target
