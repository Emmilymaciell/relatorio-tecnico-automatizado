"""FASE 3 — baixa, para `tmp/downloads/`, arquivos autorizados da investigacao.

    .venv\\Scripts\\python scripts\\04_fetch.py --reports 11 12 13 14
    .venv\\Scripts\\python scripts\\04_fetch.py --work-source "00_ Lista mestre.xlsx"
    .venv\\Scripts\\python scripts\\04_fetch.py --item-id 01ZC... --purpose "anexo P2.4"

Toda transferencia:
    * e registrada em `state/download_authorizations.jsonl` ANTES de acontecer;
    * so grava em `tmp/downloads/` (a guarda de `security` recusa qualquer outro destino);
    * nunca modifica nem reenvia nada ao SharePoint.

Autorizacao vigente (Emmily, 2026-09-22): arquivos de Maio a Agosto/2026 diretamente
relacionados ao Relatorio G2 — DOCX, PDF, Lista Mestra, anexos e planilhas-fonte
necessarios —, com download dirigido pela investigacao, nao copia indiscriminada.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prog_g2_report import REPO_ROOT
from prog_g2_report.report_id import format_report
from prog_g2_report.security import DOWNLOAD_DIR
from prog_g2_report.settings import load_settings
from prog_g2_report.sharepoint.auth import build_token_provider
from prog_g2_report.sharepoint.discovery import Discovery, DownloadAuthorization
from prog_g2_report.sharepoint.graph_ro import GraphError, GraphReadOnlyClient, explain
from prog_g2_report.sharepoint.models import ItemRef

CATALOG = REPO_ROOT / "data" / "catalog"

# Autorizacao concedida pela Emmily nesta rodada (ver docstring).
GRANTED_BY = "Emmily (autorizacao da Fase 3, 2026-09-22)"
AUTHORIZED_MONTHS = {"2026-05", "2026-06", "2026-07", "2026-08"}


def load_jsonl(name: str) -> list[dict]:
    path = CATALOG / name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def pick_report_files(corpus: list[dict], numbers: list[int]) -> list[tuple[dict, str]]:
    """Escolhe, por relatorio, o DOCX de producao e o PDF de entrega (DEC-005)."""
    chosen: list[tuple[dict, str]] = []
    for entry in corpus:
        if entry["report_number"] not in numbers:
            continue
        if entry["reference_month"] not in AUTHORIZED_MONTHS:
            print(f"  ! fora da janela autorizada: {entry['label']} — pulado")
            continue

        docx = [f for f in entry["docx"] if f["tree"] == "producao"] or entry["docx"]
        # Sem sufixo de revisao no nome; em empate, o mais recente.
        docx = sorted(docx, key=lambda f: (len(f["name"]), f["modified"]))
        if docx:
            chosen.append((docx[0], entry["label"]))

        pdf = [f for f in entry["pdf"] if f["tree"] == "entregas"] or entry["pdf"]
        pdf = sorted(pdf, key=lambda f: (not f["signed"], len(f["name"])))
        if pdf:
            chosen.append((pdf[0], entry["label"]))
    return chosen


def fetch(disco: Discovery, file_row: dict, purpose: str) -> Path | None:
    item = ItemRef(
        drive_id=file_row["drive_id"],
        item_id=file_row["item_id"],
        name=file_row["name"],
        path=file_row.get("path", file_row["name"]),
        is_folder=False,
        size=file_row.get("size"),
    )
    destination = DOWNLOAD_DIR / purpose_folder(purpose) / item.name
    if destination.exists() and destination.stat().st_size == (item.size or -1):
        print(f"  = ja em tmp: {item.name[:64]}")
        return destination

    authorization = DownloadAuthorization(
        drive_id=item.drive_id,
        item_id=item.item_id,
        item_name=item.name,
        purpose=purpose,
        granted_by=GRANTED_BY,
        delete_after=True,
        max_bytes=300 * 1024 * 1024,
    )
    try:
        path = disco.download_authorized(
            item, authorization, destination_dir=destination.parent
        )
    except GraphError as exc:
        print(f"  ! falhou {item.name[:50]}: {exc}")
        return None
    print(f"  + {path.name[:64]:<66} {path.stat().st_size / 1e6:>6.1f} MB")
    return path


def purpose_folder(purpose: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in purpose.lower())[:60].strip("_")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports", type=int, nargs="*", default=[], help="números dos relatórios")
    parser.add_argument("--work-source", nargs="*", default=[], help="arquivo da pasta de trabalho")
    parser.add_argument("--item-id", nargs="*", default=[], help="item_id avulso (usa o catálogo)")
    parser.add_argument("--purpose", default="investigacao fase 3", help="motivo registrado")
    args = parser.parse_args()

    corpus = load_jsonl("report_corpus.jsonl")
    work = load_jsonl("work_sources.jsonl")
    items = load_jsonl("items_entregas.jsonl") + load_jsonl("items_producao.jsonl")
    if not corpus:
        print("catálogo ausente: rode scripts/02 e 03 antes")
        return 2

    targets: list[tuple[dict, str]] = []
    if args.reports:
        targets += [
            (row, f"relatorios {min(args.reports)}-{max(args.reports)}")
            for row, _label in pick_report_files(corpus, args.reports)
        ]
    for name in args.work_source:
        match = [s for s in work if s["name"].strip().lower() == name.strip().lower()]
        if not match:
            print(f"  ! nao encontrado na pasta de trabalho: {name}")
            continue
        targets.append((match[0], "fontes de trabalho"))
    for item_id in args.item_id:
        match = [i for i in items if i["item_id"] == item_id and not i["is_folder"]]
        if not match:
            print(f"  ! item_id nao esta no catalogo: {item_id}")
            continue
        targets.append((match[0], args.purpose))

    if not targets:
        print("nada a baixar: use --reports, --work-source ou --item-id")
        return 1

    total = sum(t[0].get("size") or 0 for t in targets)
    print(f"baixando {len(targets)} arquivo(s), {total / 1e6:.1f} MB, para tmp/downloads/")
    if args.reports:
        print("  relatórios: " + ", ".join(format_report(n) for n in sorted(args.reports)))

    settings = load_settings()
    provider = build_token_provider(settings)
    saved = 0
    with GraphReadOnlyClient(provider.token, min_pause_seconds=0.1) as client:
        disco = Discovery(client)
        try:
            for row, purpose in targets:
                if fetch(disco, row, purpose):
                    saved += 1
        except GraphError as exc:
            print(f"ERRO Graph: {exc}\n  -> {explain(exc)}")
            return 3
        print(f"\n  {saved}/{len(targets)} arquivos em tmp/downloads/")
        print(f"  chamadas Graph: {client.calls}  bytes lidos: {client.bytes_read / 1e6:.1f} MB")
    print("  autorizações registradas em state/download_authorizations.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
