"""O detector de segredos e codigo de seguranca: ele tambem precisa de teste.

Garante que ele pega o que importa (linha de .env com credencial, chave privada, token)
e que nao acusa o que nao e segredo (kwarg de teste, modelo vazio, .env ignorado).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from prog_g2_report import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_secrets


def matches(text: str) -> list[str]:
    return [label for pattern, label in check_secrets.SECRET_PATTERNS if pattern.search(text)]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("AZURE_CLIENT_SECRET=Abc8Q~valorLongoInventado123", "segredo do cliente com valor"),  # amostra-sintetica
        ("GRAPH_CLIENT_SECRET=Abc8Q~valorLongoInventado123", "segredo do cliente com valor"),  # amostra-sintetica
        ('client_secret: "Abc8Q~valorLongoInventado123"', "client secret em literal"),  # amostra-sintetica
        ("Authorization: Bearer " + "a" * 40, "cabecalho Bearer com token"),
        ("token=eyJ" + "a" * 25 + ".eyJ" + "b" * 25 + ".sig", "JWT (token de acesso)"),
        ('senha = "valor-inventado-aqui"', "senha literal"),  # amostra-sintetica
    ],
)
def test_real_secrets_are_detected(text: str, expected: str):
    assert expected in matches(text)


@pytest.mark.parametrize(
    "text",
    [
        # linha do modelo, sem valor
        "AZURE_CLIENT_SECRET=",
        # kwarg Python de teste, indentado: nao e credencial no repositorio
        "    settings = make(AZURE_CLIENT_SECRET=SECRET_VALUE)",
        '    make(AZURE_CLIENT_SECRET="abc123")',
        # mencao em documentacao
        "Preencha AZURE_CLIENT_SECRET com o campo 'Valor' do portal.",
        # cabecalho PEM citado em texto, sem material de chave
        "o arquivo comeca com -----BEGIN PRIVATE KEY----- e termina com END",
    ],
)
def test_non_secrets_are_not_flagged(text: str):
    assert matches(text) == []


def test_private_key_with_material_is_detected():
    pem = "-----BEGIN PRIVATE KEY-----\n" + "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSj" * 2
    assert "chave privada PEM" in matches(pem)


def test_env_example_template_passes_the_real_check():
    """O modelo versionado nao pode ter valor de credencial."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("AZURE_CLIENT_SECRET="):
            assert line.strip() == "AZURE_CLIENT_SECRET=", line


def test_git_ignored_uses_nul_and_finds_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """O .env real e ignorado pelo Git; o modelo .env.example nao.

    Roda num repositorio Git proprio (tmp_path + git init) com o .gitignore do projeto, para nao
    depender de a pasta do projeto ser um repositorio (a copia publica pode nao ser).
    """
    if shutil.which("git") is None:
        pytest.skip("git nao esta no PATH")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    shutil.copyfile(REPO_ROOT / ".gitignore", tmp_path / ".gitignore")
    monkeypatch.setattr(check_secrets, "REPO_ROOT", tmp_path)
    ignored = check_secrets.git_ignored([".env", ".env.example", "README.md"])
    assert ".env" in ignored
    assert ".env.example" not in ignored
    assert "README.md" not in ignored


def test_forbidden_suffixes_cover_credentials_and_office_files():
    for suffix in (".pfx", ".p12", ".pem", ".key", ".docx", ".xlsx", ".pdf"):
        assert suffix in check_secrets.FORBIDDEN_SUFFIXES


def test_pragma_does_not_weaken_the_patterns():
    """O marcador e aplicado por linha em main(), nao afrouxa o regex.

    Isso importa: se o marcador desativasse o padrao, bastaria alguem escrever o
    comentario ao lado de um segredo real para escondê-lo do detector em qualquer arquivo.
    """
    marked = f"AZURE_CLIENT_SECRET=Abc8Q~valorLongoInventado123  {check_secrets.FAKE_SAMPLE_PRAGMA}"
    assert matches(marked), "o regex tem de casar mesmo com o marcador na linha"


def test_this_test_file_passes_the_repository_check():
    """Este arquivo tem amostras marcadas; o detector nao pode barra-lo por isso."""
    import subprocess

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_secrets.py")],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout
