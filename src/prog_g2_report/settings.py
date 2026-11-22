"""Configuracao carregada do `.env` (nunca versionado) e de variaveis de ambiente.

A autenticacao e de service principal por **client secret** (DEC-004):

    AZURE_TENANT_ID + AZURE_CLIENT_ID + AZURE_CLIENT_SECRET

O segredo fica em `SecretStr` e nunca aparece em `repr`, `str`, log ou excecao.
Nenhuma credencial e hardcoded: tudo vem do `.env` ou do ambiente.
"""

from __future__ import annotations

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from prog_g2_report import REPO_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    azure_tenant_id: str = Field(alias="AZURE_TENANT_ID")
    azure_client_id: str = Field(alias="AZURE_CLIENT_ID")
    azure_client_secret: SecretStr = Field(alias="AZURE_CLIENT_SECRET")

    sharepoint_hostname: str = Field(
        default="contoso.sharepoint.com", alias="SHAREPOINT_HOSTNAME"
    )
    sharepoint_site_path: str = Field(default="/sites/exemplo", alias="SHAREPOINT_SITE_PATH")

    @field_validator("azure_tenant_id", "azure_client_id", mode="before")
    @classmethod
    def _required_and_not_blank(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("preencha esta variavel no .env")
        return value.strip() if isinstance(value, str) else value

    @field_validator("azure_client_secret", mode="before")
    @classmethod
    def _secret_present(cls, value):
        """Recusa segredo vazio. A mensagem nunca cita o valor recebido."""
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError(
                "AZURE_CLIENT_SECRET esta vazio no .env: cole o 'Valor' do segredo do "
                "cliente gerado no portal Entra ID"
            )
        return value.strip() if isinstance(value, str) else value

    def __repr__(self) -> str:  # nunca vazar segredo
        return (
            f"Settings(tenant={self.azure_tenant_id!r}, client={self.azure_client_id!r}, "
            f"secret=***, site={self.sharepoint_hostname + self.sharepoint_site_path!r})"
        )

    __str__ = __repr__


def load_settings() -> Settings:
    """Carrega o .env. Levanta erro legivel se faltar variavel obrigatoria."""
    return Settings()  # type: ignore[call-arg]
