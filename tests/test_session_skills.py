"""As skills de ciclo de sessao sao infraestrutura: quebram em silencio se ninguem olhar.

Este teste falha se o frontmatter sair do formato oficial, se uma referencia auxiliar
apontar para arquivo inexistente, ou se o session-start deixar de ser read-only no texto.
"""

from __future__ import annotations

import re

import pytest
import yaml

from prog_g2_report import REPO_ROOT

SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
EXPECTED = {"session-start", "session-close"}

# Campos do frontmatter oficialmente suportados pelo Claude Code.
SUPPORTED_FIELDS = {
    "name", "description", "when_to_use", "argument-hint", "arguments",
    "disable-model-invocation", "user-invocable", "allowed-tools", "disallowed-tools",
    "model", "effort", "context", "agent", "background", "hooks", "paths", "shell",
    "metadata", "license", "compatibility",
}
DESCRIPTION_LIMIT = 1536  # description + when_to_use, somados
LINK = re.compile(r"\]\((?!https?://)([^)]+\.md)\)")


def skill_files() -> list:
    return sorted(SKILLS_DIR.glob("*/SKILL.md"))


def frontmatter(path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} não começa com frontmatter"
    return yaml.safe_load(text.split("---", 2)[1])


def test_both_session_skills_exist():
    assert {p.parent.name for p in skill_files()} >= EXPECTED


@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_frontmatter_uses_only_supported_fields(path):
    data = frontmatter(path)
    unsupported = set(data) - SUPPORTED_FIELDS
    assert not unsupported, f"campos não suportados: {unsupported}"


@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_name_matches_directory(path):
    """O nome define o comando: /session-start precisa vir da pasta session-start."""
    assert frontmatter(path)["name"] == path.parent.name


@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_description_within_limit(path):
    data = frontmatter(path)
    total = len(data.get("description", "")) + len(data.get("when_to_use") or "")
    assert 0 < total <= DESCRIPTION_LIMIT


@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_auxiliary_references_exist(path):
    """Progressive disclosure só funciona se o arquivo referenciado existir."""
    missing = [
        target
        for target in LINK.findall(path.read_text(encoding="utf-8"))
        if not (path.parent / target).is_file()
    ]
    assert not missing, f"referências quebradas: {missing}"


def test_session_start_declares_itself_read_only():
    """A garantia de não escrever é textual: se sumir do SKILL.md, deixa de existir."""
    text = (SKILLS_DIR / "session-start" / "SKILL.md").read_text(encoding="utf-8")
    assert "Proibido nesta fase" in text
    assert "Nenhuma escrita em arquivo" in text
    assert "Contexto reconstruído. Nenhuma alteração foi realizada." in text


def test_session_close_stops_before_new_work():
    text = (SKILLS_DIR / "session-close" / "SKILL.md").read_text(encoding="utf-8")
    assert "Proibido nesta fase" in text
    assert "Handoff concluído. Nenhuma nova implementação foi iniciada." in text
    # A política Git do projeto proíbe commit automático por fim de sessão.
    assert "Não commite só porque a sessão terminou" in text


def test_session_log_exists_and_is_history_not_state():
    log = REPO_ROOT / "docs" / "sessions" / "LOG.md"
    assert log.is_file()
    text = log.read_text(encoding="utf-8")
    assert "append-only" in text
    assert "STATE.md" in text, "o log precisa apontar que o estado atual mora em outro lugar"
