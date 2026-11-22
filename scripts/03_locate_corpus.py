"""FASE 2 — consolida o corpus de Relatorios G2 e localiza as fontes de trabalho.

    .venv\\Scripts\\python scripts\\03_locate_corpus.py

Le os inventarios gravados por `02_inventory_monthly_folders.py` e consulta a pasta de
trabalho do G2 para produzir:

    data/catalog/report_corpus.jsonl   um registro por Relatorio G2 (numero + mes de
                                       referencia), com os arquivos das duas arvores
    data/catalog/work_sources.jsonl    planilhas e documentos da pasta de trabalho do G2
                                       (candidatos a fonte: Lista Mestra, controles, etc.)
    state/corpus_summary.yaml          panorama para leitura humana

Somente leitura. Nao baixa conteudo, nao altera nada no SharePoint.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prog_g2_report import REPO_ROOT
from prog_g2_report.report_id import format_report, parse_report_filename
from prog_g2_report.security import assert_write_allowed
from prog_g2_report.settings import load_settings
from prog_g2_report.sharepoint.auth import build_token_provider
from prog_g2_report.sharepoint.discovery import Discovery
from prog_g2_report.sharepoint.graph_ro import GraphError, GraphReadOnlyClient, explain

CATALOG = REPO_ROOT / "data" / "catalog"
STATE = REPO_ROOT / "state"

WORK_ROOT = "3. Desenvolvimento/G2 -  Engenharia"

SIGNED = re.compile(r"assinad", re.IGNORECASE)


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    target = assert_write_allowed(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return target


def file_ref(row: dict) -> dict:
    """Referencia minima e estavel de um arquivo: identidade + o que ajuda a escolher."""
    return {
        "name": row["name"],
        "drive_id": row["drive_id"],
        "item_id": row["item_id"],
        "path": row["path"],
        "size": row["size"],
        "modified": row["modified"],
        "signed": bool(SIGNED.search(row["name"])),
        "tree": row["tree"],
    }


def build_corpus(entregas: list[dict], producao: list[dict]) -> list[dict]:
    """Agrupa por numero do Relatório G2 declarado NO NOME DO ARQUIVO, nao pela pasta.

    Pasta e nome podem discordar — se discordarem, o registro guarda os dois, e a
    divergencia vira evidencia para a Fase 3.
    """
    corpus: dict[int, dict] = {}
    for row in [*entregas, *producao]:
        if row["is_folder"]:
            continue
        parsed = parse_report_filename(row["name"])
        if parsed is None:
            continue
        number = parsed.report_number
        entry = corpus.setdefault(
            number,
            {
                "report_number": number,
                "reference_month": parsed.reference_month,
                "label": format_report(number, parsed.reference_month),
                "folder_numbers": [],
                "folder_months": [],
                "docx": [],
                "pdf": [],
                "other": [],
            },
        )
        if row["report_number"] not in entry["folder_numbers"]:
            entry["folder_numbers"].append(row["report_number"])
        if row["reference_month"] not in entry["folder_months"]:
            entry["folder_months"].append(row["reference_month"])
        bucket = "docx" if row["extension"] == "docx" else "pdf" if row["extension"] == "pdf" else "other"
        entry[bucket].append(file_ref(row))

    for entry in corpus.values():
        entry["folder_matches_filename"] = entry["folder_numbers"] == [entry["report_number"]] and (
            entry["folder_months"] == [entry["reference_month"]]
        )
        entry["has_docx"] = bool(entry["docx"])
        entry["has_pdf"] = bool(entry["pdf"])
        entry["has_signed_pdf"] = any(f["signed"] for f in entry["pdf"] + entry["other"])
    return [corpus[n] for n in sorted(corpus)]


def main() -> int:
    entregas = load_jsonl(CATALOG / "items_entregas.jsonl")
    producao = load_jsonl(CATALOG / "items_producao.jsonl")
    if not entregas or not producao:
        print("inventario ausente: rode antes scripts/02_inventory_monthly_folders.py")
        return 2

    corpus = build_corpus(entregas, producao)

    settings = load_settings()
    provider = build_token_provider(settings)
    with GraphReadOnlyClient(provider.token, min_pause_seconds=0.1) as client:
        disco = Discovery(client)
        try:
            site = disco.resolve_site(settings.sharepoint_hostname, settings.sharepoint_site_path)
            drive = disco.find_drive(site, "Programa")
            if drive is None:
                print("biblioteca Programa nao encontrada")
                return 2
            work = disco.item_by_path(drive, WORK_ROOT)
            sources = [
                {
                    "name": item.name,
                    "drive_id": item.drive_id,
                    "item_id": item.item_id,
                    "path": item.path,
                    "extension": item.extension,
                    "size": item.size,
                    "modified": item.modified,
                    "web_url": item.web_url,
                    "role": "UNKNOWN",  # a Fase 4 preenche ao provar a linhagem
                }
                for item in disco.children(drive.id, work.item_id)
                if not item.is_folder
            ]
            work_folders = [
                {"name": i.name, "item_id": i.item_id, "child_count": i.child_count}
                for i in disco.children(drive.id, work.item_id)
                if i.is_folder
            ]
        except GraphError as exc:
            print(f"ERRO Graph: {exc}\n  -> {explain(exc)}")
            return 3
        calls = client.calls

    corpus_path = write_jsonl(CATALOG / "report_corpus.jsonl", corpus)
    sources_path = write_jsonl(CATALOG / "work_sources.jsonl", sources)

    numbers = [e["report_number"] for e in corpus]
    summary = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "reports_found": len(corpus),
        "report_numbers": numbers,
        "missing_numbers": sorted(set(range(1, max(numbers, default=0) + 1)) - set(numbers)),
        "without_docx": [e["report_number"] for e in corpus if not e["has_docx"]],
        "without_pdf": [e["report_number"] for e in corpus if not e["has_pdf"]],
        "folder_filename_mismatch": [
            e["label"] for e in corpus if not e["folder_matches_filename"]
        ],
        "work_root": WORK_ROOT,
        "work_folders": work_folders,
        "work_files": [
            {"name": s["name"], "ext": s["extension"], "modified": s["modified"]} for s in sources
        ],
        "graph_calls": calls,
    }
    summary_path = assert_write_allowed(STATE / "corpus_summary.yaml")
    summary_path.write_text(
        yaml.safe_dump(summary, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    print(f"Relatorios G2 no corpus: {len(corpus)}  (nº {min(numbers):02d} a nº {max(numbers):02d})")
    print(f"  sem DOCX: {summary['without_docx'] or 'nenhum'}")
    print(f"  sem PDF : {summary['without_pdf'] or 'nenhum'}")
    print(f"  pasta/nome divergentes: {summary['folder_filename_mismatch'] or 'nenhum'}")
    print(f"fontes na pasta de trabalho: {len(sources)} arquivos, {len(work_folders)} pastas")
    print(f"chamadas Graph: {calls}")
    for path in (corpus_path, sources_path, summary_path):
        print(f"  -> {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
