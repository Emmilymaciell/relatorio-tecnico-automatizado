"""FASE 4 — histórico de versões da Lista Mestra: a planilha de hoje é a de então?

    .venv\\Scripts\\python scripts\\10_master_list_history.py --list
    .venv\\Scripts\\python scripts\\10_master_list_history.py --snapshot 11 12 13 14

A Lista Mestra é editada retroativamente (DEC-006). Um golden test histórico que use a
planilha de HOJE pode divergir do relatório publicado por esse motivo, e não por erro do
gerador. Este script busca, para cada Relatório G2, a versão da planilha mais próxima
ANTERIOR à data de emissão, e compara a atribuição de documentos.

SOMENTE LEITURA: lê o histórico e o conteúdo das versões. **Não restaura nada**, não muda
qual versão é a atual, não altera o SharePoint.

Saídas:
    tmp/historical_sources/          cópias temporárias das versões
    data/catalog/master_list_versions.jsonl   metadados de cada versão analisada
    state/history_comparison.yaml    comparação por relatório
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prog_g2_report import REPO_ROOT
from prog_g2_report.report_id import format_report
from prog_g2_report.security import assert_write_allowed
from prog_g2_report.settings import load_settings
from prog_g2_report.sharepoint.auth import build_token_provider
from prog_g2_report.sharepoint.discovery import Discovery
from prog_g2_report.sharepoint.graph_ro import GraphError, GraphReadOnlyClient, explain

HISTORICAL = REPO_ROOT / "tmp" / "historical_sources"
CATALOG = REPO_ROOT / "data" / "catalog"
STATE = REPO_ROOT / "state"
MASTER_LIST_PATH = "3. Desenvolvimento/G2 -  Engenharia/00_ Lista mestre.xlsx"

# Data de emissão de cada relatório, lida da capa do PDF (Fase 3).
ISSUE_DATES = {
    11: "2026-06-09",
    12: "2026-07-07",
    13: "2026-08-11",
    14: "2026-09-08",
}
REFERENCE_MONTHS = {11: "2026-05", 12: "2026-06", 13: "2026-07", 14: "2026-08"}


def read_assignments(data: bytes, path: Path) -> dict[int, set[str]]:
    """Documento -> número do relatório, a partir dos bytes de uma versão da planilha."""
    path.write_bytes(data)
    workbook = load_workbook(path, data_only=True, read_only=True)
    sheet = workbook["Controle Geral"]
    rows = sheet.iter_rows(min_row=4, values_only=True)
    assignments: dict[int, set[str]] = {}
    for row in rows:
        if not row or len(row) < 11:
            continue
        document, number = row[3], row[10]
        if document and isinstance(number, (int, float)):
            assignments.setdefault(int(number), set()).add(str(document).strip())
    workbook.close()
    return assignments


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="só listar as versões")
    parser.add_argument("--snapshot", type=int, nargs="*", default=[], help="relatórios a comparar")
    args = parser.parse_args()

    settings = load_settings()
    provider = build_token_provider(settings)
    HISTORICAL.mkdir(parents=True, exist_ok=True)
    assert_write_allowed(HISTORICAL / "x")

    with GraphReadOnlyClient(provider.token, min_pause_seconds=0.1) as client:
        disco = Discovery(client)
        try:
            site = disco.resolve_site(settings.sharepoint_hostname, settings.sharepoint_site_path)
            drive = disco.find_drive(site, "Programa")
            item = disco.item_by_path(drive, MASTER_LIST_PATH)
            versions = client.versions(item.drive_id, item.item_id)
        except GraphError as exc:
            print(f"ERRO Graph: {exc}\n  -> {explain(exc)}")
            return 3

        versions = sorted(versions, key=lambda v: v.get("lastModifiedDateTime", ""))
        print(f"Lista Mestra: {len(versions)} versões no histórico")
        if versions:
            print(f"  mais antiga: {versions[0].get('lastModifiedDateTime')}")
            print(f"  mais recente: {versions[-1].get('lastModifiedDateTime')}")
        rows = [
            {
                "version_id": v.get("id"),
                "last_modified": v.get("lastModifiedDateTime"),
                "size": v.get("size"),
                "modified_by": (v.get("lastModifiedBy") or {}).get("user", {}).get("displayName"),
            }
            for v in versions
        ]
        if args.list:
            for row in rows[-25:]:
                print(f"  {row['last_modified']}  v{row['version_id']:<6} {row['size']:>9} bytes")

        comparison: dict[str, dict] = {}
        for number in args.snapshot:
            issued = ISSUE_DATES.get(number)
            if not issued:
                continue
            label = format_report(number, REFERENCE_MONTHS[number])
            # a versão vigente na emissão é a última anterior à data de emissão
            candidates = [v for v in versions if (v.get("lastModifiedDateTime") or "") <= f"{issued}T23:59:59Z"]
            if not candidates:
                comparison[label] = {"status": "SEM_VERSAO_ANTERIOR", "issued": issued}
                print(f"\n{label}: nenhuma versão anterior a {issued}")
                continue
            chosen = candidates[-1]
            print(f"\n{label} (emitido {issued})")
            print(f"  versão escolhida: {chosen.get('id')} de {chosen.get('lastModifiedDateTime')}")
            try:
                data = client.read_version_bytes(item.drive_id, item.item_id, chosen["id"])
            except GraphError as exc:
                print(f"  ! não foi possível ler: {exc}")
                comparison[label] = {"status": "LEITURA_FALHOU", "error": str(exc)}
                continue
            target = HISTORICAL / f"lista_mestre_v{chosen['id']}.xlsx"
            historical = read_assignments(data, target)
            current_path = REPO_ROOT / "tmp" / "downloads" / "fontes_de_trabalho" / "00_ lista mestre.xlsx"
            current = read_assignments(current_path.read_bytes(), HISTORICAL / "atual.xlsx")

            hist_docs = historical.get(number, set())
            curr_docs = current.get(number, set())
            only_hist = sorted(hist_docs - curr_docs)
            only_curr = sorted(curr_docs - hist_docs)
            comparison[label] = {
                "issued": issued,
                "version_id": chosen.get("id"),
                "version_date": chosen.get("lastModifiedDateTime"),
                "documents_then": len(hist_docs),
                "documents_now": len(curr_docs),
                "only_in_historical": only_hist,
                "only_in_current": only_curr,
                "identical": not only_hist and not only_curr,
            }
            print(f"  documentos então: {len(hist_docs)} | hoje: {len(curr_docs)}")
            if only_hist:
                print(f"  saíram depois: {only_hist[:8]}")
            if only_curr:
                print(f"  entraram depois: {only_curr[:8]}")
            if not only_hist and not only_curr:
                print("  IDÊNTICO — a planilha de hoje reproduz a atribuição da época")

        calls = client.calls

    versions_path = assert_write_allowed(CATALOG / "master_list_versions.jsonl")
    with versions_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    if comparison:
        out = assert_write_allowed(STATE / "history_comparison.yaml")
        out.write_text(
            yaml.safe_dump(
                {
                    "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "master_list": f"{item.drive_id}:{item.item_id}",
                    "total_versions": len(versions),
                    "comparison": comparison,
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        print(f"\n  -> {out.relative_to(REPO_ROOT)}")
    print(f"  -> {versions_path.relative_to(REPO_ROOT)}   (chamadas Graph: {calls})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
