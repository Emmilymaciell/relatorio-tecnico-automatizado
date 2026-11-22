"""Varre arquivos rastreados e staged por segredos e documentos corporativos brutos.

    python scripts/check_secrets.py          # rastreados + staged
    python scripts/check_secrets.py --all    # todos os arquivos do repo (ignora .git e .venv)

Sai com codigo 1 se encontrar algo. Rodar SEMPRE antes de commit.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS = [
    # Cabecalho PEM seguido de material base64 real (nao apenas a string do cabecalho).
    (
        re.compile(r"-----BEGIN (RSA |EC |ENCRYPTED )?PRIVATE KEY-----\s*[A-Za-z0-9+/=]{40,}"),
        "chave privada PEM",
    ),
    (re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\."), "JWT (token de acesso)"),
    (
        re.compile(r"(?i)client_secret\s*[=:]\s*['\"][A-Za-z0-9~._-]{20,}"),
        "client secret em literal",
    ),
    # Linha de arquivo .env (inicio de linha, valor sem espaco). Um kwarg Python indentado,
    # como `make(AZURE_CLIENT_SECRET=VALOR)`, nao casa — e nao e um segredo no repositorio.
    (
        re.compile(r"(?im)^(AZURE|GRAPH)_CLIENT_SECRET\s*=\s*[^\s'\"#]{8,}"),
        "segredo do cliente com valor",
    ),
    (re.compile(r"(?i)(password|senha|passwd)\s*[=:]\s*['\"][^'\"\n]{4,}['\"]"), "senha literal"),
    (re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._-]{30,}"), "cabecalho Bearer com token"),
]
FORBIDDEN_SUFFIXES = (".pfx", ".p12", ".pem", ".key", ".docx", ".xlsx", ".xlsm", ".pdf", ".pptx", ".zip")
ALLOWED_PREFIXES = ("tests/fixtures/", "assets/branding/")
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "tmp", "node_modules"}
SELF = Path(__file__).resolve()

# Amostras SINTETICAS (que existem para testar este detector) declaram-se com este
# marcador na propria linha. A isencao e por linha, nao por arquivo: um segredo real
# colado sem o marcador continua sendo barrado, inclusive dentro de um teste.
FAKE_SAMPLE_PRAGMA = "# amostra-sintetica"


def git_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True).stdout
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    ).stdout
    return sorted(set(out.splitlines()) | set(staged.splitlines()))


def all_files() -> list[str]:
    files = []
    for path in REPO_ROOT.rglob("*"):
        if path.is_file() and not (set(path.relative_to(REPO_ROOT).parts) & SKIP_DIRS):
            files.append(path.relative_to(REPO_ROOT).as_posix())
    return files


def git_ignored(paths: list[str]) -> set[str]:
    """Quais desses caminhos o Git ignora. Um `.env` ignorado nao e um vazamento.

    Usa NUL como separador na entrada e na saida (`-z`). Sem isso, no Windows o modo
    texto do subprocess transforma '\\n' em '\\r\\n' e o Git passa a ver nomes de arquivo
    terminados em '\\r' — que nao casam com nada e distorcem o resultado.
    """
    if not paths:
        return set()
    result = subprocess.run(
        ["git", "check-ignore", "-z", "--stdin"],
        cwd=REPO_ROOT,
        input=b"\0".join(p.encode("utf-8") for p in paths),
        capture_output=True,
    )
    return {
        chunk.decode("utf-8", "replace").replace("\\", "/")
        for chunk in result.stdout.split(b"\0")
        if chunk
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    files = all_files() if args.all else git_files()
    # No modo --all o disco inteiro do repo e varrido; o que o Git ignora nao pode vazar.
    ignored = git_ignored(files) if args.all else set()
    problems: list[str] = []

    for rel in files:
        path = REPO_ROOT / rel
        if not path.is_file() or path.resolve() == SELF or rel in ignored:
            continue
        if rel == ".env" or (rel.startswith(".env.") and rel != ".env.example"):
            problems.append(f"{rel}: arquivo .env nao pode ser versionado")
        if rel.lower().endswith(FORBIDDEN_SUFFIXES) and not rel.startswith(ALLOWED_PREFIXES):
            problems.append(f"{rel}: extensao proibida (certificado/documento bruto)")
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if rel == ".env.example":
            # No modelo, so a presenca de VALOR de credencial e problema.
            if re.search(r"(?im)^AZURE_CLIENT_SECRET=\S", text):
                problems.append(f"{rel}: AZURE_CLIENT_SECRET preenchido no modelo")
            continue
        lines = text.splitlines()
        for pattern, label in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                line = lines[line_no - 1] if line_no <= len(lines) else ""
                if FAKE_SAMPLE_PRAGMA in line:
                    continue
                problems.append(f"{rel}:{line_no}: possivel {label}")

    if problems:
        print("BLOQUEADO - possiveis segredos ou arquivos brutos:")
        for p in problems:
            print("  -", p)
        return 1
    print(f"ok - {len(files)} arquivos verificados, nenhum segredo ou arquivo bruto encontrado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
