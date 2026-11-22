"""Cliente Microsoft Graph SOMENTE LEITURA, com allowlist explicita de operacoes.

Seguranca por construcao, em tres camadas:

1. **Allowlist de operacoes** (`ALLOWED_OPERATIONS`): cada chamada passa por
   `_request(op, ...)`, que so aceita nomes cadastrados. A allowlist e fechada:
   listar, resolver, pesquisar, ler metadados, ler conteudo em memoria.
2. **Um unico verbo HTTP**: o modulo so chama `httpx.Client.get`. Nao existe
   post/put/patch/delete aqui e `tests/test_graph_ro_guard.py` le a AST para garantir.
   (A autenticacao, que usa POST no endpoint de login do Entra ID, esta em `auth.py`
   e nao toca em documento nenhum.)
3. **Endpoints de escrita proibidos por nome**: mesmo via GET, nenhum caminho pode
   conter `createUploadSession`, `/copy`, `/createLink`, `/invite`, `/checkout`,
   `/checkin`, `/restore`, `/preview` etc. — `_assert_readonly_url()` recusa.

Qualquer violacao levanta `SharePointWriteBlockedError`. Nao existe metodo de escrita
"para o futuro": este projeto nao precisa dele.

Nota: pesquisa via `POST /search/query` tambem e leitura, mas NAO esta na allowlist.
Se vier a ser necessaria, entra como decisao registrada (DEC) com endpoint fixo, nunca
como abertura generica do verbo POST.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from prog_g2_report.security import SharePointWriteBlockedError

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_HOST = "graph.microsoft.com"

DEFAULT_ITEM_FIELDS = (
    "id,name,size,file,folder,parentReference,eTag,cTag,webUrl,"
    "createdDateTime,lastModifiedDateTime"
)

# Segmentos que denunciam operacao mutavel ou de efeito colateral, mesmo em GET.
FORBIDDEN_URL_FRAGMENTS = (
    "createuploadsession",
    "/copy",
    "/createlink",
    "/invite",
    "/checkout",
    "/checkin",
    "/restore",
    "/permissions/",  # leitura de permissoes nao e necessaria; escrita jamais
    "/subscriptions",
    "/workbook/",  # sessao do Excel online pode persistir alteracoes
    "/thumbnails",  # gera artefato remoto; render local e suficiente
)


@dataclass(frozen=True)
class AllowedOperation:
    name: str
    path_pattern: re.Pattern[str]
    description: str


def _op(name: str, pattern: str, description: str) -> AllowedOperation:
    return AllowedOperation(name, re.compile(pattern), description)


ALLOWED_OPERATIONS: dict[str, AllowedOperation] = {
    op.name: op
    for op in (
        _op("site_by_path", r"^/sites/[^/]+:/[^?]*$", "resolver site pelo hostname:caminho"),
        _op("site_drives", r"^/sites/[^/]+/drives(\?.*)?$", "listar bibliotecas do site"),
        _op("site_lists", r"^/sites/[^/]+/lists(\?.*)?$", "listar listas do site"),
        _op("list_columns", r"^/sites/[^/]+/lists/[^/]+/columns(\?.*)?$", "colunas de uma lista"),
        _op("list_items", r"^/sites/[^/]+/lists/[^/]+/items(\?.*)?$", "itens de uma lista"),
        _op("drive_root", r"^/drives/[^/]+/root(\?.*)?$", "raiz de um drive"),
        _op("drive_item", r"^/drives/[^/]+/items/[^/:?]+(\?.*)?$", "metadados de um item"),
        _op("drive_item_by_path", r"^/drives/[^/]+/root:/.*:(\?.*)?$", "item por caminho"),
        _op(
            "drive_children",
            r"^/drives/[^/]+/(root|items/[^/:?]+)/children(\?.*)?$",
            "filhos de uma pasta",
        ),
        _op("drive_item_versions", r"^/drives/[^/]+/items/[^/]+/versions(\?.*)?$", "versoes"),
        _op(
            "drive_item_version_content",
            r"^/drives/[^/]+/items/[^/]+/versions/[^/]+/content$",
            "conteudo de uma versao historica (leitura; nao restaura nada)",
        ),
        _op("drive_search", r"^/drives/[^/]+/root/search\(q='.*'\)(\?.*)?$", "pesquisa no drive"),
        _op(
            "drive_item_content",
            r"^/drives/[^/]+/items/[^/]+/content$",
            "conteudo do arquivo (leitura em memoria ou download autorizado)",
        ),
        _op("next_link", r"^https://graph\.microsoft\.com/v1\.0/.*$", "paginacao @odata.nextLink"),
    )
}


class GraphError(RuntimeError):
    def __init__(self, status: int, code: str, message: str, url: str = ""):
        self.status, self.code, self.message, self.url = status, code, message, url
        super().__init__(f"HTTP {status} {code}: {message}")


def explain(error: GraphError) -> str:
    if error.status == 401:
        return (
            "Credencial nao aceita: conferir AZURE_TENANT_ID, AZURE_CLIENT_ID e o "
            "AZURE_CLIENT_SECRET no .env (segredo expirado? foi colado o 'Valor' e "
            "nao o 'ID Secreto'?)."
        )
    if error.status == 403:
        return (
            "Autenticou, mas o aplicativo nao tem acesso a este recurso "
            "(Sites.Selected / permissao de aplicativo)."
        )
    if error.status == 404:
        return "Recurso nao existe: conferir hostname/site/caminho."
    if error.status == 429:
        return "Graph limitou a taxa: aumentar min_pause_seconds e repetir."
    return error.message


class GraphReadOnlyClient:
    """Porta unica para o Graph. Somente `get`. Somente operacoes da allowlist."""

    def __init__(
        self,
        token_provider: Callable[[], str],
        min_pause_seconds: float = 0.15,
        timeout_seconds: float = 120.0,
        max_retries: int = 5,
    ):
        self._token_provider = token_provider
        self._pause = min_pause_seconds
        self._retries = max_retries
        self._last_call = 0.0
        self._http = httpx.Client(timeout=timeout_seconds, follow_redirects=False)
        self.calls = 0
        self.throttled = 0
        self.bytes_read = 0

    # ------------------------------------------------------------------ guardas
    @staticmethod
    def _assert_readonly_url(url: str) -> None:
        lowered = url.lower()
        for fragment in FORBIDDEN_URL_FRAGMENTS:
            if fragment in lowered:
                raise SharePointWriteBlockedError(
                    f"endpoint fora da allowlist de leitura ({fragment!r}): {url}"
                )

    def _resolve(self, op_name: str, path_or_url: str) -> str:
        op = ALLOWED_OPERATIONS.get(op_name)
        if op is None:
            raise SharePointWriteBlockedError(
                f"operacao {op_name!r} nao esta na allowlist; este cliente e somente leitura"
            )
        if not op.path_pattern.match(path_or_url):
            raise SharePointWriteBlockedError(
                f"caminho nao corresponde a operacao {op_name!r}: {path_or_url}"
            )
        url = path_or_url if path_or_url.startswith("http") else GRAPH_BASE + path_or_url
        if httpx.URL(url).host != GRAPH_HOST:
            raise SharePointWriteBlockedError(f"host fora do Graph: {url}")
        self._assert_readonly_url(url)
        return url

    def _throttle(self) -> None:
        if self._pause <= 0:
            return
        wait = self._pause - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    # ------------------------------------------------------------------ nucleo
    def _request(self, op_name: str, path_or_url: str, *, stream: bool = False) -> httpx.Response:
        """Unica saida HTTP do modulo. Sempre GET."""
        url = self._resolve(op_name, path_or_url)
        for attempt in range(1, self._retries + 1):
            self._throttle()
            headers = {
                "Authorization": f"Bearer {self._token_provider()}",
                "Accept": "application/octet-stream" if stream else "application/json",
            }
            try:
                response = self._http.get(url, headers=headers)
            except httpx.TransportError as exc:
                if attempt < self._retries:
                    time.sleep(3 * attempt)
                    continue
                raise GraphError(0, "network", str(exc), url) from exc
            self.calls += 1
            if response.status_code in (429, 500, 502, 503, 504) and attempt < self._retries:
                self.throttled += 1
                retry_after = float(response.headers.get("Retry-After", 5 * attempt))
                time.sleep(min(retry_after, 120))
                continue
            if response.status_code == 302 and stream:
                # /content redireciona para URL pre-autenticada do CDN; seguir com GET.
                return self._follow_content_redirect(response.headers["Location"])
            if response.is_error:
                code, message = _error_detail(response)
                raise GraphError(response.status_code, code, message, url)
            return response
        raise GraphError(0, "retries_exhausted", "tentativas esgotadas", url)

    def _follow_content_redirect(self, location: str) -> httpx.Response:
        # URL pre-autenticada (sem token no header). Continua sendo GET e leitura.
        response = self._http.get(location)
        self.calls += 1
        if response.is_error:
            code, message = _error_detail(response)
            raise GraphError(response.status_code, code, message, location)
        return response

    def get_json(self, op_name: str, path_or_url: str) -> dict:
        return self._request(op_name, path_or_url).json()

    def paginate(self, op_name: str, path: str) -> Iterator[dict]:
        page = self.get_json(op_name, path)
        while True:
            yield from page.get("value", [])
            next_link = page.get("@odata.nextLink")
            if not next_link:
                return
            page = self.get_json("next_link", next_link)

    # ------------------------------------------------------------------ leitura
    def site_by_path(self, hostname: str, site_path: str) -> dict:
        site_path = "/" + site_path.strip("/")
        return self.get_json("site_by_path", f"/sites/{hostname}:{site_path}")

    def site_drives(self, site_id: str) -> list[dict]:
        return list(self.paginate("site_drives", f"/sites/{site_id}/drives"))

    def site_lists(self, site_id: str) -> list[dict]:
        return list(self.paginate("site_lists", f"/sites/{site_id}/lists"))

    def list_columns(self, site_id: str, list_id: str) -> list[dict]:
        return list(self.paginate("list_columns", f"/sites/{site_id}/lists/{list_id}/columns"))

    def list_items(self, site_id: str, list_id: str, top: int = 200) -> Iterator[dict]:
        return self.paginate(
            "list_items", f"/sites/{site_id}/lists/{list_id}/items?$expand=fields&$top={top}"
        )

    def drive_root(self, drive_id: str) -> dict:
        return self.get_json("drive_root", f"/drives/{drive_id}/root?$select={DEFAULT_ITEM_FIELDS}")

    def item(self, drive_id: str, item_id: str) -> dict:
        return self.get_json(
            "drive_item", f"/drives/{drive_id}/items/{item_id}?$select={DEFAULT_ITEM_FIELDS}"
        )

    def item_by_path(self, drive_id: str, relative_path: str) -> dict:
        """Resolve 'pasta/sub/arquivo.ext' codificando segmento a segmento."""
        clean = relative_path.replace("\\", "/").strip("/")
        if not clean:
            return self.drive_root(drive_id)
        encoded = "/".join(quote(part, safe="") for part in clean.split("/"))
        return self.get_json(
            "drive_item_by_path",
            f"/drives/{drive_id}/root:/{encoded}:?$select={DEFAULT_ITEM_FIELDS}",
        )

    def children(self, drive_id: str, item_id: str | None = None, top: int = 200) -> Iterator[dict]:
        target = "root" if item_id in (None, "root") else f"items/{item_id}"
        return self.paginate(
            "drive_children",
            f"/drives/{drive_id}/{target}/children?$top={top}&$select={DEFAULT_ITEM_FIELDS}",
        )

    def versions(self, drive_id: str, item_id: str) -> list[dict]:
        return list(
            self.paginate("drive_item_versions", f"/drives/{drive_id}/items/{item_id}/versions")
        )

    def search(self, drive_id: str, query: str, top: int = 200) -> Iterator[dict]:
        safe_query = query.replace("'", "''")
        return self.paginate(
            "drive_search",
            f"/drives/{drive_id}/root/search(q='{quote(safe_query, safe='')}')"
            f"?$top={top}&$select={DEFAULT_ITEM_FIELDS}",
        )

    def read_bytes(self, drive_id: str, item_id: str, max_bytes: int = 50 * 1024 * 1024) -> bytes:
        """Le o conteudo EM MEMORIA (sem gravar em disco). Uso: analise pontual.

        Para persistir em disco, use `discovery.download_authorized()`, que exige
        autorizacao registrada e destino em tmp/downloads/.
        """
        meta = self.item(drive_id, item_id)
        size = int(meta.get("size") or 0)
        if size > max_bytes:
            raise GraphError(0, "too_large", f"{size} bytes acima do teto {max_bytes}")
        response = self._request(
            "drive_item_content", f"/drives/{drive_id}/items/{item_id}/content", stream=True
        )
        self.bytes_read += len(response.content)
        return response.content

    def read_version_bytes(self, drive_id: str, item_id: str, version_id: str) -> bytes:
        """Le EM MEMORIA o conteudo de uma VERSAO HISTORICA do arquivo.

        Isto e leitura pura: nao restaura a versao, nao altera o item, nao muda qual
        versao e a atual. Serve para comparar a planilha de hoje com a de uma data
        passada (DEC-007).
        """
        response = self._request(
            "drive_item_version_content",
            f"/drives/{drive_id}/items/{item_id}/versions/{version_id}/content",
            stream=True,
        )
        self.bytes_read += len(response.content)
        return response.content

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> GraphReadOnlyClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _error_detail(response: httpx.Response) -> tuple[str, str]:
    try:
        error = response.json().get("error", {})
        return error.get("code", "unknown"), str(error.get("message", ""))[:400]
    except ValueError:
        return "unknown", response.text[:400]
