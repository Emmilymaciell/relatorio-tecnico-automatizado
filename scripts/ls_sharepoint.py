"""Lista o conteudo de uma pasta do SharePoint. SOMENTE LEITURA, so metadados.

    .venv\\Scripts\\python scripts\\ls_sharepoint.py                      # raiz do drive Programa
    .venv\\Scripts\\python scripts\\ls_sharepoint.py "4. Produtos"
    .venv\\Scripts\\python scripts\\ls_sharepoint.py "4. Produtos" --depth 2
    .venv\\Scripts\\python scripts\\ls_sharepoint.py --drive Documentos

Ferramenta de navegacao usada ao longo de toda a descoberta. Nao baixa conteudo,
nao grava nada, nao altera nada no SharePoint.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prog_g2_report.settings import load_settings
from prog_g2_report.sharepoint.auth import build_token_provider
from prog_g2_report.sharepoint.discovery import Discovery
from prog_g2_report.sharepoint.graph_ro import (
    GraphError,
    GraphReadOnlyClient,
    explain,
)


def human(size: int | None) -> str:
    if not size:
        return ""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:,.0f} {unit}" if unit == "B" else f"{value:,.1f} {unit}"
        value /= 1024
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Lista uma pasta do SharePoint (read-only).")
    parser.add_argument("path", nargs="?", default="", help="caminho relativo a raiz do drive")
    parser.add_argument("--drive", default="Programa", help="nome da biblioteca (padrao: Programa)")
    parser.add_argument("--depth", type=int, default=1, help="profundidade (padrao: 1)")
    parser.add_argument("--ids", action="store_true", help="mostrar item_id")
    args = parser.parse_args()

    settings = load_settings()
    provider = build_token_provider(settings)
    with GraphReadOnlyClient(provider.token, min_pause_seconds=0.1) as client:
        disco = Discovery(client)
        try:
            site = disco.resolve_site(settings.sharepoint_hostname, settings.sharepoint_site_path)
            drive = disco.find_drive(site, args.drive)
            if drive is None:
                print(f"biblioteca {args.drive!r} nao encontrada")
                return 2
            root = disco.item_by_path(drive, args.path)
            print(f"{drive.name}/{args.path}".rstrip("/"))
            print(f"  (folder item_id={root.item_id})\n")

            folders = files = 0
            total = 0
            base = root.path.rstrip("/")
            for _depth, item in disco.walk(drive.id, root.item_id, max_depth=args.depth):
                # Caminho relativo a pasta consultada: em profundidade > 1, so a indentacao
                # nao diz de qual pasta o item veio (ha varios "Anexos" irmaos, por exemplo).
                relative = item.path[len(base) :].lstrip("/") if base else item.path
                kind = "[dir]" if item.is_folder else "     "
                extra = f"  {item.item_id}" if args.ids else ""
                modified = item.modified.date().isoformat() if item.modified else ""
                size = human(item.size) if not item.is_folder else ""
                count = f"({item.child_count} itens)" if item.is_folder and item.child_count else ""
                print(f"{kind} {relative:<70.70} {size:>10}  {modified}  {count}{extra}")
                if item.is_folder:
                    folders += 1
                else:
                    files += 1
                    total += item.size or 0
            print(f"\n  {folders} pastas, {files} arquivos, {human(total)}")
            print(f"  chamadas Graph: {client.calls}")
        except GraphError as exc:
            print(f"ERRO Graph: {exc}\n  -> {explain(exc)}")
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
