"""FASE 2 — inventario por METADADOS das pastas mensais do G2.

O acervo do G2 tem DUAS arvores mensais, e as duas sao inventariadas por este script:

    entregas   4. Produtos/NN. Mes AAAA/G2/            (PDF entregue + Anexos)
    producao   3. Desenvolvimento/G2 -  Engenharia/_Produto/NN. Mes AAAA/   (DOCX de trabalho)

    .venv\\Scripts\\python scripts\\02_inventory_monthly_folders.py --tree entregas
    .venv\\Scripts\\python scripts\\02_inventory_monthly_folders.py --tree producao
    .venv\\Scripts\\python scripts\\02_inventory_monthly_folders.py --tree ambas

Somente leitura: lista pastas e arquivos e grava os metadados localmente. Nao baixa
conteudo, nao altera nada no SharePoint.

Saidas (uma por arvore, sufixadas com o nome da arvore):
    data/catalog/monthly_folders_<arvore>.jsonl   uma linha por pasta mensal, com resumo
    data/catalog/items_<arvore>.jsonl             uma linha por item encontrado
    state/inventory_summary.yaml                  panorama para leitura humana

Cada relatorio e identificado por `report_number` + `reference_month` (ver
`prog_g2_report.report_id`). Os dois vem do nome da pasta mensal ("14. Agosto 2026" ->
numero 14, mes 2026-08); a Fase 3 confere contra o numero declarado dentro do documento.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prog_g2_report import REPO_ROOT
from prog_g2_report.report_id import format_report, parse_monthly_folder
from prog_g2_report.security import assert_write_allowed
from prog_g2_report.settings import load_settings
from prog_g2_report.sharepoint.auth import build_token_provider
from prog_g2_report.sharepoint.discovery import Discovery
from prog_g2_report.sharepoint.graph_ro import (
    GraphError,
    GraphReadOnlyClient,
    explain,
)
from prog_g2_report.sharepoint.models import DriveRef, ItemRef

CATALOG = REPO_ROOT / "data" / "catalog"
STATE = REPO_ROOT / "state"

# As duas arvores mensais do G2. `group` e a subpasta dentro da pasta mensal (None = a
# propria pasta mensal ja e o conteudo do G2).
TREES = {
    "entregas": {
        "root": "4. Produtos",
        "group": "G2",
        "note": "PDF entregue e anexos oficiais",
    },
    "producao": {
        "root": "3. Desenvolvimento/G2 -  Engenharia/_Produto",
        "group": None,
        "note": "DOCX de trabalho e documentos produzidos no mes",
    },
}

def write_jsonl(path: Path, rows: list[dict]) -> Path:
    target = assert_write_allowed(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return target


def item_row(item: ItemRef, context: dict) -> dict:
    return {
        **context,
        "drive_id": item.drive_id,
        "item_id": item.item_id,
        "name": item.name,
        "path": item.path,
        "is_folder": item.is_folder,
        "size": item.size,
        "child_count": item.child_count,
        "extension": item.extension,
        "quick_xor_hash": item.quick_xor_hash,
        "created": item.created,
        "modified": item.modified,
        "web_url": item.web_url,
        "parent_item_id": item.parent_item_id,
    }


def inventory(
    disco: Discovery, drive: DriveRef, tree: str, depth: int
) -> tuple[list, list]:
    config = TREES[tree]
    group = config["group"]
    root = disco.item_by_path(drive, config["root"])
    monthly_rows: list[dict] = []
    item_rows: list[dict] = []

    for folder in sorted(disco.children(drive.id, root.item_id), key=lambda i: i.name):
        if not folder.is_folder:
            continue
        parsed = parse_monthly_folder(folder.name)
        if parsed is None:
            print(f"  (ignorada, nao e pasta mensal) {folder.name}")
            continue

        if group is None:
            # A propria pasta mensal ja e o conteudo; nao ha subpasta de grupo.
            target: ItemRef | None = folder
            siblings: list[str] = []
        else:
            children = {c.name.strip().upper(): c for c in disco.children(drive.id, folder.item_id)}
            target = children.get(group.upper())
            siblings = sorted(children)

        row = {
            **parsed.as_dict(),
            "tree": tree,
            "folder_name": folder.name,
            "drive_id": folder.drive_id,
            "folder_item_id": folder.item_id,
            "path": folder.path,
            "modified": folder.modified,
            "siblings_present": siblings,
            "group_found": target is not None,
            "group_item_id": target.item_id if target else None,
            "files": 0,
            "folders": 0,
            "total_size": 0,
            "extensions": {},
        }

        if target is not None:
            context = {
                "tree": tree,
                **parsed.as_dict(),
                "monthly_folder": folder.name,
                "group": "G2",
            }
            item_rows.append(item_row(target, context))
            for _depth, item in disco.walk(drive.id, target.item_id, max_depth=depth):
                item_rows.append(item_row(item, context))
                if item.is_folder:
                    row["folders"] += 1
                else:
                    row["files"] += 1
                    row["total_size"] += item.size or 0
                    ext = item.extension or "(sem extensao)"
                    row["extensions"][ext] = row["extensions"].get(ext, 0) + 1

        monthly_rows.append(row)
        status = (
            f"{row['files']:>4} arq, {row['folders']:>3} pastas, {row['total_size'] / 1e6:>8.1f} MB"
            if target
            else "SEM G2"
        )
        print(f"  {folder.name:<28} {status}")

    return monthly_rows, item_rows


def tree_summary(tree: str, monthly_rows: list[dict], item_rows: list[dict]) -> dict:
    found = [r for r in monthly_rows if r["group_found"]]
    numbers = {r["report_number"] for r in monthly_rows}
    return {
        "root": TREES[tree]["root"],
        "note": TREES[tree]["note"],
        "monthly_folders": len(monthly_rows),
        "folder_numbers": sorted(numbers),
        "missing_numbers": sorted(set(range(1, max(numbers, default=0) + 1)) - numbers),
        "with_content": len([r for r in found if r["files"]]),
        "empty_folders": [r["folder_name"] for r in found if r["files"] == 0],
        "items": len(item_rows),
        "per_month": [
            {
                "folder": r["folder_name"],
                "report": format_report(r["report_number"], r["reference_month"]),
                "files": r["files"],
                "folders": r["folders"],
                "size_mb": round(r["total_size"] / 1e6, 2),
                "extensions": r["extensions"],
            }
            for r in sorted(monthly_rows, key=lambda r: r["report_number"])
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tree", default="ambas", choices=[*TREES, "ambas"], help="arvore a inventariar"
    )
    parser.add_argument("--depth", type=int, default=8, help="profundidade dentro da pasta mensal")
    parser.add_argument("--drive", default="Programa", help="biblioteca (padrao: Programa)")
    args = parser.parse_args()

    trees = list(TREES) if args.tree == "ambas" else [args.tree]
    settings = load_settings()
    provider = build_token_provider(settings)
    outputs: list[Path] = []
    summaries: dict[str, dict] = {}

    with GraphReadOnlyClient(provider.token, min_pause_seconds=0.1) as client:
        disco = Discovery(client)
        try:
            site = disco.resolve_site(settings.sharepoint_hostname, settings.sharepoint_site_path)
            drive = disco.find_drive(site, args.drive)
            if drive is None:
                print(f"biblioteca {args.drive!r} nao encontrada")
                return 2
            for tree in trees:
                print(f"\n[{tree}] {args.drive}/{TREES[tree]['root']}")
                monthly_rows, item_rows = inventory(disco, drive, tree, args.depth)
                outputs.append(
                    write_jsonl(CATALOG / f"monthly_folders_{tree}.jsonl", monthly_rows)
                )
                outputs.append(write_jsonl(CATALOG / f"items_{tree}.jsonl", item_rows))
                summaries[tree] = tree_summary(tree, monthly_rows, item_rows)
        except GraphError as exc:
            print(f"ERRO Graph: {exc}\n  -> {explain(exc)}")
            return 3
        calls = client.calls

    summary_path = assert_write_allowed(STATE / "inventory_summary.yaml")
    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "drive": {"name": drive.name, "id": drive.id},
        "group": "G2",
        "graph_calls": calls,
        "trees": summaries,
    }
    summary_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    outputs.append(summary_path)

    print(f"\n  chamadas Graph: {calls}")
    for path in outputs:
        print(f"  -> {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
