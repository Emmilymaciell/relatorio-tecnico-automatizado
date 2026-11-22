"""FASE 1 — verifica a autenticacao do aplicativo e o acesso READ-ONLY ao site Programa.

    .venv\\Scripts\\python scripts\\01_verify_readonly_access.py
    .venv\\Scripts\\python scripts\\01_verify_readonly_access.py --save-ids

O que faz (tudo leitura):
    1. carrega .env (sem imprimir segredo);
    2. autentica o service principal por client secret;
    3. obtem token (nunca exibido) e resolve o site pelo hostname:caminho;
    4. lista as bibliotecas (drives) do site com nome e id;
    5. com --save-ids, grava site_id e drives em state/sharepoint_ids.yaml.

Nunca imprime token nem segredo. Nunca escreve no SharePoint.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prog_g2_report import REPO_ROOT
from prog_g2_report.security import assert_write_allowed
from prog_g2_report.settings import load_settings
from prog_g2_report.sharepoint.auth import (
    AuthenticationError,
    build_token_provider,
)
from prog_g2_report.sharepoint.discovery import Discovery
from prog_g2_report.sharepoint.graph_ro import (
    GraphError,
    GraphReadOnlyClient,
    explain,
)

IDS_FILE = REPO_ROOT / "state" / "sharepoint_ids.yaml"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save-ids", action="store_true", help="gravar IDs canonicos em state/")
    args = parser.parse_args()

    print("[1/4] carregando .env ...")
    try:
        settings = load_settings()
    except Exception as exc:
        print(f"  ERRO: {exc}")
        print("  Copie .env.example para .env e preencha AZURE_TENANT_ID, AZURE_CLIENT_ID")
        print("  e AZURE_CLIENT_SECRET (o campo 'Valor' do segredo do cliente).")
        return 2
    print(f"  {settings!r}")

    print("[2/4] obtendo token por client secret (token nao exibido) ...")
    provider = build_token_provider(settings)
    try:
        provider.token()
    except AuthenticationError as exc:
        print(f"  ERRO de autenticacao: {exc}")
        return 3
    print("  token obtido (em memoria).")

    print("[3/4] resolvendo site (operacao read-only) ...")
    with GraphReadOnlyClient(provider.token) as client:
        disco = Discovery(client)
        try:
            site = disco.resolve_site(settings.sharepoint_hostname, settings.sharepoint_site_path)
            drives = disco.list_drives(site)
        except GraphError as exc:
            print(f"  ERRO Graph: {exc}")
            print(f"  -> {explain(exc)}")
            return 4
        print(f"  site: {site.display_name!r}  id={site.id}")
        print(f"  {site.web_url}")

        print(f"[4/4] bibliotecas do site: {len(drives)}")
        for d in drives:
            print(f"  - {d.name!r:40} type={d.drive_type!s:14} id={d.id}")
        print(f"  chamadas Graph: {client.calls}  throttles: {client.throttled}")

    if args.save_ids:
        payload = {
            "resolved_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "hostname": settings.sharepoint_hostname,
            "site_path": settings.sharepoint_site_path,
            "site": site.model_dump(),
            "drives": [d.model_dump() for d in drives],
        }
        target = assert_write_allowed(IDS_FILE)
        target.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"IDs gravados em {target.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
