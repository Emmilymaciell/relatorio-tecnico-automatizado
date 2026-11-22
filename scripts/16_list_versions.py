"""Lista o histórico de versões de uma fonte do Relatório G2 no SharePoint (SOMENTE LEITURA).

    .venv\\Scripts\\python scripts\\16_list_versions.py --source master_list --last 5
    .venv\\Scripts\\python scripts\\16_list_versions.py --source projects
    .venv\\Scripts\\python scripts\\16_list_versions.py --source environmental --last 3

Fonte = chave de `config/g2_report_model.yaml: sources` (master_list, projects, environmental);
a identidade (drive_id, item_id) vem do catálogo `data/catalog/work_sources.jsonl` pelo nome do
arquivo no modelo. Lê só o histórico (`GET …/versions`, graph_ro): não lê conteúdo, não grava
nada no repositório nem no SharePoint. A saída vai SÓ para o terminal (stdout): id da versão,
lastModified (UTC) e autor da modificação, da mais recente para a mais antiga; a 1ª linha é a
versão vigente (`current` nos scripts 15 e 17).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prog_g2_report.builder.generate import default_env_file
from prog_g2_report.model import load_model
from prog_g2_report.sources import master_list_remote
from prog_g2_report.sources.versions import version_rows

SOURCES = ("master_list", "projects", "environmental")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--source", choices=SOURCES, required=True)
    p.add_argument("--last", type=int, default=None, help="só as N versões mais recentes")
    p.add_argument("--env-file", type=Path, default=None,
                   help="opcional: .env da credencial (padrão: .env da raiz do repositório)")
    return p


def main(argv: list[str] | None = None, *, client: object = None) -> int:
    args = parser().parse_args(argv)
    if args.last is not None and args.last <= 0:
        print("erro: --last deve ser positivo", file=sys.stderr)
        return 2
    name = str(load_model()["sources"][args.source]["name"])
    drive_id, item_id = master_list_remote.catalog_identity(name)
    reader = client or master_list_remote.default_client(args.env_file or default_env_file())
    try:
        rows = version_rows(reader, drive_id, item_id, args.last)  # type: ignore[arg-type]
    finally:
        if client is None:
            reader.close()  # type: ignore[attr-defined]
    print(f"{name} — {len(rows)} versão(ões), mais recente primeiro")
    print(f"{'versão':>8}  {'lastModified (UTC)':<21} autor")
    for row in rows:
        print(f"{row.version_id:>8}  {row.last_modified or '-':<21} {row.author or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
