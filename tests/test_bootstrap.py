"""Sanidade do repositorio: estrutura, .gitignore, ausencia de segredos e de arquivos brutos."""

from __future__ import annotations

import subprocess

from prog_g2_report import REPO_ROOT

REQUIRED_DIRS = [
    ".claude/agents", ".claude/rules", "assets/branding", "assets/discovered", "config",
    "data/catalog", "data/schemas", "docs/architecture", "docs/discovery", "docs/decisions",
    "docs/specs", "docs/qa", "scripts", "src/prog_g2_report/sharepoint",
    "src/prog_g2_report/security", "state", "tests", "tmp",
]
REQUIRED_FILES = [
    "CLAUDE.md", "README.md", "STATE.md", ".env.example", ".gitignore", ".gitattributes",
    "pyproject.toml", "config/project.yaml", "config/discovery.yaml",
    "docs/discovery/HISTORICAL_DEFECTS.md", "data/catalog/anomalies.jsonl",
]
GITIGNORE_MUST_HAVE = [".env", ".env.*", "!.env.example", "*.pfx", "*.p12", "*.pem", "*.key", "/tmp/*"]
FORBIDDEN_TRACKED_SUFFIXES = (".pfx", ".p12", ".pem", ".key", ".docx", ".xlsx", ".pdf", ".pptx")


def test_required_structure_exists():
    missing = [d for d in REQUIRED_DIRS if not (REPO_ROOT / d).is_dir()]
    missing += [f for f in REQUIRED_FILES if not (REPO_ROOT / f).is_file()]
    assert not missing, missing


def test_gitignore_protects_secrets():
    lines = {ln.strip() for ln in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert not [p for p in GITIGNORE_MUST_HAVE if p not in lines]


def test_env_example_is_the_client_secret_template():
    """O modelo tem as variaveis do service principal, todas vazias, e nada de certificado."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    declared = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in text.splitlines()
        if "=" in line and not line.strip().startswith("#")
    }
    assert declared["AZURE_TENANT_ID"] == ""
    assert declared["AZURE_CLIENT_ID"] == ""
    assert declared["AZURE_CLIENT_SECRET"] == ""
    assert declared["SHAREPOINT_HOSTNAME"] == "contoso.sharepoint.com"
    assert declared["SHAREPOINT_SITE_PATH"] == "/sites/exemplo"
    assert not [k for k in declared if "CERTIFICATE" in k], "certificado saiu do escopo (DEC-004)"


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    return result.stdout


def test_no_forbidden_files_tracked_or_staged():
    if not (REPO_ROOT / ".git").exists():
        return
    tracked = _git("ls-files").splitlines() + _git("diff", "--cached", "--name-only").splitlines()
    bad = [f for f in tracked if f.lower().endswith(FORBIDDEN_TRACKED_SUFFIXES) and not f.startswith("tests/fixtures/")]
    bad += [f for f in tracked if f == ".env" or (f.startswith(".env.") and f != ".env.example")]
    assert not bad, f"arquivos proibidos no Git: {bad}"
