"""Autenticacao por client secret: configuracao, validacoes e nao vazamento. Sem rede.

A garantia central testada aqui: o valor do segredo nao aparece em `repr`, `str`,
mensagem de excecao ou saida de diagnostico — em nenhum caminho de codigo.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from prog_g2_report.settings import Settings, load_settings
from prog_g2_report.sharepoint.auth import (
    AuthenticationError,
    ClientSecretTokenProvider,
    _scrub,
    build_token_provider,
)

# Valor sintetico, com o formato de um segredo real do portal (nunca um segredo de verdade).
FAKE_SECRET = "Zx8Q~inventadoParaTesteSemValorReal123"
BASE = {
    "AZURE_TENANT_ID": "11111111-2222-3333-4444-555555555555",
    "AZURE_CLIENT_ID": "66666666-7777-8888-9999-000000000000",
    "AZURE_CLIENT_SECRET": FAKE_SECRET,
}


def make(**overrides) -> Settings:
    # _env_file=None ignora o .env real da maquina: o teste nao depende dele.
    return Settings(_env_file=None, **{**BASE, **overrides})  # type: ignore[call-arg]


# ----------------------------------------------------------------------
# Configuracao
# ----------------------------------------------------------------------


def test_settings_load_the_three_required_variables():
    settings = make()
    assert settings.azure_tenant_id == BASE["AZURE_TENANT_ID"]
    assert settings.azure_client_id == BASE["AZURE_CLIENT_ID"]
    assert settings.azure_client_secret.get_secret_value() == FAKE_SECRET


def test_defaults_point_to_the_prog_site():
    settings = make()
    assert settings.sharepoint_hostname == "contoso.sharepoint.com"
    assert settings.sharepoint_site_path == "/sites/exemplo"


@pytest.mark.parametrize("variable", ["AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"])
def test_missing_variable_is_rejected(variable):
    values = {k: v for k, v in BASE.items() if k != variable}
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.mark.parametrize("variable", ["AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"])
def test_blank_variable_is_rejected(variable):
    with pytest.raises(ValidationError):
        make(**{variable: "   "})


def test_empty_secret_error_explains_what_to_paste():
    with pytest.raises(ValidationError, match="Valor"):
        make(AZURE_CLIENT_SECRET="")


def test_no_credential_is_hardcoded():
    """Nenhum tenant/client/segredo fixo no codigo: tudo vem do .env."""
    import inspect

    from prog_g2_report import settings as settings_module
    from prog_g2_report.sharepoint import auth as auth_module

    for module in (settings_module, auth_module):
        source = inspect.getsource(module)
        assert "069340c0" not in source, f"client id hardcoded em {module.__name__}"
        assert "f29aad96" not in source, f"tenant id hardcoded em {module.__name__}"


def test_load_settings_reads_the_real_env_file_path():
    """load_settings aponta para o .env do repositorio (que nao e versionado)."""
    assert Settings.model_config["env_file"].name == ".env"
    assert callable(load_settings)


# ----------------------------------------------------------------------
# Provedor de token
# ----------------------------------------------------------------------


def test_build_token_provider_returns_client_secret_provider():
    assert isinstance(build_token_provider(make()), ClientSecretTokenProvider)


def test_client_credential_returns_the_secret_only_to_msal():
    provider = ClientSecretTokenProvider(make())
    assert provider._client_credential() == FAKE_SECRET


@pytest.mark.parametrize(
    "secret_id",
    [
        "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
        "3F2504E0-4F89-11D3-9A0C-0305E82C3301",
        "{3f2504e0-4f89-11d3-9a0c-0305e82c3301}",
    ],
)
def test_secret_id_pasted_instead_of_value_is_caught_before_network(secret_id):
    """O "ID Secreto" e um GUID de 36 caracteres -- NAO e um valor curto.

    A versao anterior deste teste usava "abc123" e passava pelo caminho do
    comprimento minimo, dando a impressao de que a confusao Valor/ID estava
    coberta. Nao estava: um GUID real tem 36 caracteres e passava folgado pelo
    limiar de 20, indo parar numa falha de autenticacao na rede, confusa de
    diagnosticar. A checagem de FORMA e que resolve isso.
    """
    assert len(secret_id.strip("{}")) == 36
    provider = ClientSecretTokenProvider(make(AZURE_CLIENT_SECRET=secret_id))
    with pytest.raises(AuthenticationError, match="ID Secreto"):
        provider._client_credential()


def test_secret_id_error_does_not_echo_the_value():
    secret_id = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
    provider = ClientSecretTokenProvider(make(AZURE_CLIENT_SECRET=secret_id))
    with pytest.raises(AuthenticationError) as exc:
        provider._client_credential()
    assert secret_id not in str(exc.value)
    assert "3f2504e0" not in str(exc.value)


def test_short_secret_error_does_not_echo_the_value():
    short = "abc123"
    provider = ClientSecretTokenProvider(make(AZURE_CLIENT_SECRET=short))
    with pytest.raises(AuthenticationError) as exc:
        provider._client_credential()
    assert short not in str(exc.value)


# ----------------------------------------------------------------------
# Nao vazamento
# ----------------------------------------------------------------------


def test_settings_repr_and_str_never_leak_the_secret():
    settings = make()
    for text in (repr(settings), str(settings), f"{settings}", format(settings)):
        assert FAKE_SECRET not in text
        assert "***" in text


def test_provider_repr_and_str_never_leak_the_secret():
    provider = build_token_provider(make())
    for text in (repr(provider), str(provider), f"{provider}"):
        assert FAKE_SECRET not in text
        assert "***" in text


def test_pydantic_serialization_never_leaks_the_secret():
    settings = make()
    assert FAKE_SECRET not in str(settings.model_dump())
    assert FAKE_SECRET not in settings.model_dump_json()


def test_validation_error_never_leaks_the_secret():
    """Um erro em OUTRO campo nao pode arrastar o segredo para a mensagem."""
    with pytest.raises(ValidationError) as exc:
        make(AZURE_TENANT_ID="")
    assert FAKE_SECRET not in str(exc.value)


def test_scrub_removes_the_secret_from_any_text():
    assert _scrub(f"erro: {FAKE_SECRET} invalido", FAKE_SECRET) == "erro: *** invalido"
    assert _scrub("erro comum", FAKE_SECRET) == "erro comum"
    assert _scrub("erro", "") == "erro"


def test_token_error_path_scrubs_the_secret(monkeypatch):
    """Se o servico devolvesse o segredo no corpo do erro, ele nao chegaria a excecao."""

    class FakeApp:
        def acquire_token_for_client(self, scopes):
            return {
                "error": "invalid_client",
                "error_description": f"secret {FAKE_SECRET} rejeitado",
                "correlation_id": "abc-123",
            }

    provider = ClientSecretTokenProvider(make())
    monkeypatch.setattr(provider, "_application", lambda: FakeApp())
    with pytest.raises(AuthenticationError) as exc:
        provider.token()
    message = str(exc.value)
    assert FAKE_SECRET not in message
    assert "***" in message
    assert "invalid_client" in message and "abc-123" in message


def test_token_is_cached_and_never_in_repr(monkeypatch):
    class FakeApp:
        def __init__(self):
            self.calls = 0

        def acquire_token_for_client(self, scopes):
            self.calls += 1
            return {"access_token": "token-secreto-de-teste", "expires_in": 3600}

    app = FakeApp()
    provider = ClientSecretTokenProvider(make())
    monkeypatch.setattr(provider, "_application", lambda: app)
    assert provider.token() == "token-secreto-de-teste"
    assert provider.token() == "token-secreto-de-teste"
    assert app.calls == 1, "o token precisa ser reaproveitado ate perto de expirar"
    assert "token-secreto-de-teste" not in repr(provider)
