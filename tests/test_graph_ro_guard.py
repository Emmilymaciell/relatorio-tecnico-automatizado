"""O cliente Graph e somente leitura POR CONSTRUCAO. Este teste le o codigo-fonte.

Se alguem adicionar post/put/patch/delete, um endpoint de escrita ou um metodo com nome
de escrita em graph_ro.py, este teste falha antes de qualquer rede.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from prog_g2_report.security import SharePointWriteBlockedError
from prog_g2_report.sharepoint import graph_ro
from prog_g2_report.sharepoint.graph_ro import ALLOWED_OPERATIONS, GraphReadOnlyClient

SOURCE = Path(inspect.getfile(graph_ro))
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))

WRITE_HTTP_METHODS = {"post", "put", "patch", "delete", "request", "send", "stream"}
WRITE_NAME_FRAGMENTS = (
    "upload", "create", "delete", "remove", "move", "rename", "copy", "update",
    "patch", "put", "post", "write", "share", "invite", "checkout", "checkin", "restore",
)
FORBIDDEN_SOURCE_STRINGS = (
    "createUploadSession", "/copy", "createLink", "/invite", "/checkout", "/checkin",
    "/restore", "PUT ", "PATCH ", "DELETE ", "method=", "json=", "data=", "content=",
)


def _http_calls() -> list[tuple[str, int]]:
    calls = []
    for node in ast.walk(TREE):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = ast.unparse(node.func.value)
            if owner.endswith("_http") or owner.startswith("httpx"):
                calls.append((node.func.attr, node.lineno))
    return calls


def test_only_get_is_called_on_http_client():
    offenders = [(m, ln) for m, ln in _http_calls() if m in WRITE_HTTP_METHODS]
    assert not offenders, f"metodos HTTP de escrita encontrados: {offenders}"
    verbs = {m for m, _ in _http_calls()} - {"Client", "URL"}
    assert verbs <= {"get", "close"}, f"verbos inesperados: {verbs}"


def test_no_forbidden_endpoint_strings_in_source():
    source = SOURCE.read_text(encoding="utf-8")
    # Remover a docstring e comentarios: eles CITAM os termos proibidos para explicar a regra.
    code_only = "\n".join(
        line for line in source.splitlines()
        if not line.strip().startswith("#")
    )
    body = ast.get_docstring(TREE) or ""
    code_only = code_only.replace(body, "")
    # FORBIDDEN_URL_FRAGMENTS legitimamente lista os termos para bloquea-los.
    start = code_only.index("FORBIDDEN_URL_FRAGMENTS = (")
    end = code_only.index(")", start)
    code_only = code_only[:start] + code_only[end:]
    hits = [s for s in FORBIDDEN_SOURCE_STRINGS if s in code_only]
    assert not hits, f"termos de escrita no codigo: {hits}"


def test_client_exposes_no_write_named_methods():
    names = [n for n in dir(GraphReadOnlyClient) if not n.startswith("__")]
    offenders = [n for n in names if any(f in n.lower() for f in WRITE_NAME_FRAGMENTS)]
    assert not offenders, f"metodos com nome de escrita: {offenders}"


def test_allowlist_is_closed_and_read_only():
    for name, op in ALLOWED_OPERATIONS.items():
        assert not any(f in name.lower() for f in WRITE_NAME_FRAGMENTS), name
        assert op.path_pattern.pattern.startswith(("^/", "^https://graph")), name


@pytest.fixture
def client():
    return GraphReadOnlyClient(token_provider=lambda: "fake-token", min_pause_seconds=0)


@pytest.mark.parametrize(
    "op, path",
    [
        ("upload_file", "/drives/d/items/i/content"),
        ("create_folder", "/drives/d/items/i/children"),
        ("delete_item", "/drives/d/items/i"),
        ("copy_item", "/drives/d/items/i/copy"),
    ],
)
def test_unknown_operation_is_blocked(client, op, path):
    with pytest.raises(SharePointWriteBlockedError):
        client._request(op, path)


@pytest.mark.parametrize(
    "op, path",
    [
        ("drive_item", "/drives/d/items/i/createUploadSession"),
        ("next_link", "https://graph.microsoft.com/v1.0/drives/d/items/i/copy"),
        ("next_link", "https://graph.microsoft.com/v1.0/drives/d/items/i/createLink"),
        ("next_link", "https://graph.microsoft.com/v1.0/drives/d/items/i/workbook/worksheets"),
        ("drive_children", "/drives/d/items/i/permissions/children"),
    ],
)
def test_forbidden_url_fragments_are_blocked(client, op, path):
    with pytest.raises(SharePointWriteBlockedError):
        client._request(op, path)


def test_path_must_match_operation_pattern(client):
    with pytest.raises(SharePointWriteBlockedError):
        client._request("site_drives", "/drives/d/items/i")


def test_non_graph_host_is_blocked(client):
    with pytest.raises(SharePointWriteBlockedError):
        client._request("next_link", "https://graph.microsoft.com.evil.example/v1.0/x")
