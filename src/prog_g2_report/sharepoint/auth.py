"""Autenticacao de service principal no Entra ID por **client secret** (DEC-004).

Fluxo:
    .env -> Settings -> ClientSecretTokenProvider -> msal.ConfidentialClientApplication
         -> provider.token() -> Bearer token (em memoria, nunca logado)

Regras deste modulo, sem excecao:
    * o segredo so sai do `SecretStr` dentro de `_client_credential()`, para o msal;
    * nada aqui imprime, loga ou grava segredo, token ou fragmento deles;
    * a mensagem de qualquer excecao passa por `_scrub()`, que substitui o segredo por
      `***` caso algum dia um servico o devolva no corpo do erro.

`msal` e importado tardiamente para que os testes offline rodem sem ele.
"""

from __future__ import annotations

import re
import time

from prog_g2_report.settings import Settings

GRAPH_SCOPE = "https://graph.microsoft.com/.default"
AUTHORITY_TEMPLATE = "https://login.microsoftonline.com/{tenant}"

# Barrar credencial errada ANTES de ir a rede.
#
# O portal mostra, lado a lado, duas colunas facilmente confundidas: "Valor" (o
# segredo de verdade) e "ID Secreto" (um GUID que nao autentica nada). So o
# comprimento minimo NAO separa os dois -- um GUID tem 36 caracteres e passaria
# folgado por qualquer limiar razoavel. Por isso ha duas checagens:
#
#   comprimento  pega campo truncado ou meio colado;
#   forma GUID   pega o "ID Secreto" colado no lugar do "Valor".
MIN_SECRET_LENGTH = 20
_RE_GUID = re.compile(
    r"^\{?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}?$",
    re.IGNORECASE,
)


class AuthenticationError(RuntimeError):
    """Falha ao obter token. A mensagem nunca contem segredo."""


def _scrub(text: str, secret: str) -> str:
    """Remove qualquer ocorrencia do segredo de um texto antes de ele ser exibido."""
    if secret and secret in text:
        text = text.replace(secret, "***")
    return text


class ClientSecretTokenProvider:
    """Fornece Bearer tokens para o Graph, renovando com antecedencia.

    `token()` devolve a string do cabecalho Authorization. Nao usar para outra coisa;
    nao imprimir; nao gravar.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._app = None
        self._token: str | None = None
        self._expires_at: float = 0.0

    def _client_credential(self) -> str:
        """Unico ponto em que o segredo sai do SecretStr. O retorno vai so para o msal."""
        secret = self._settings.azure_client_secret.get_secret_value()
        if _RE_GUID.match(secret):
            # nunca citar o valor recebido, nem parcialmente -- so a forma
            raise AuthenticationError(
                "AZURE_CLIENT_SECRET tem a forma de um GUID: e o 'ID Secreto', nao o "
                "'Valor' do segredo do cliente. No portal Entra ID, copie a coluna "
                "'Valor' (visivel apenas no momento da criacao do segredo)."
            )
        if len(secret) < MIN_SECRET_LENGTH:
            raise AuthenticationError(
                "AZURE_CLIENT_SECRET curto demais para ser o 'Valor' de um segredo do "
                "cliente. Confira se o campo nao foi truncado ao colar."
            )
        return secret

    def _application(self):
        if self._app is not None:
            return self._app
        import msal  # importado aqui para os testes offline nao exigirem msal

        self._app = msal.ConfidentialClientApplication(
            client_id=self._settings.azure_client_id,
            authority=AUTHORITY_TEMPLATE.format(tenant=self._settings.azure_tenant_id),
            client_credential=self._client_credential(),
        )
        return self._app

    def token(self) -> str:
        if self._token and time.time() < self._expires_at - 120:
            return self._token
        result = self._application().acquire_token_for_client(scopes=[GRAPH_SCOPE])
        if "access_token" not in result:
            # error/error_description do Entra nao trazem o segredo; ainda assim o texto
            # passa por _scrub antes de virar mensagem de excecao.
            detail = _scrub(
                str(result.get("error_description", ""))[:300],
                self._settings.azure_client_secret.get_secret_value(),
            )
            raise AuthenticationError(
                f"{result.get('error')}: {detail} (correlation_id={result.get('correlation_id')})"
            )
        self._token = result["access_token"]
        self._expires_at = time.time() + int(result.get("expires_in", 3600))
        return self._token

    def __repr__(self) -> str:
        state = "cached" if self._token else "none"
        return (
            f"ClientSecretTokenProvider(client={self._settings.azure_client_id!r}, "
            f"secret=***, token={state})"
        )

    __str__ = __repr__


def build_token_provider(settings: Settings) -> ClientSecretTokenProvider:
    """Ponto unico de construcao do provedor, usado pelos scripts."""
    return ClientSecretTokenProvider(settings)
