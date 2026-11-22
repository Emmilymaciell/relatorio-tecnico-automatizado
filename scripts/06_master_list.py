"""FASE 3 — mapeia a Lista Mestra: abas, colunas, tipos e o campo que liga documento
ao Relatorio G2.

    .venv\\Scripts\\python scripts\\06_master_list.py
    .venv\\Scripts\\python scripts\\06_master_list.py --file tmp/downloads/.../x.xlsx --dump-rows 40

Objetivo: descobrir se a planilha funciona como MANIFESTO do relatorio — isto e, se e
ela que decide quais documentos pertencem a cada Relatorio G2. A hipotese a testar e que
a selecao vem de um campo de numero de relatorio, NAO do mes civil da data de entrega.

Saidas:
    tmp/extracted/master_list/schema.json    abas, colunas, tipos, preenchimento
    tmp/extracted/master_list/rows.json      linhas normalizadas (para cruzamento)

So le arquivos ja baixados em tmp/. Nao acessa o SharePoint, nao altera a planilha.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prog_g2_report import REPO_ROOT
from prog_g2_report.security import assert_write_allowed

DOWNLOADS = REPO_ROOT / "tmp" / "downloads"
EXTRACTED = REPO_ROOT / "tmp" / "extracted" / "master_list"

# Colunas que podem carregar o vinculo com o relatorio. Procuramos por nome, sem assumir.
REPORT_LINK_HINTS = re.compile(
    r"relat|mensal|\bn[ºo°]\b|\bnumero\b|\bn[uú]mero\b|entrega|produto|m[eê]s", re.IGNORECASE
)


def cell_type(value) -> str:
    if value is None:
        return "empty"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (datetime, date)):
        return "date"
    if isinstance(value, (int, float)):
        return "number"
    return "text"


def normalise(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def header_row_of(sheet, scan_rows: int = 12) -> int:
    """A linha de cabecalho e a primeira com varias celulas de texto distintas."""
    best_row, best_score = 1, -1
    for row_index in range(1, min(scan_rows, sheet.max_row or 1) + 1):
        values = [
            c.value
            for c in next(sheet.iter_rows(min_row=row_index, max_row=row_index))
            if c.value is not None
        ]
        texts = [v for v in values if isinstance(v, str) and v.strip()]
        score = len(set(texts))
        if score > best_score:
            best_row, best_score = row_index, score
    return best_row


def analyse_sheet(sheet, max_rows: int) -> dict:
    header_index = header_row_of(sheet)
    header_cells = next(sheet.iter_rows(min_row=header_index, max_row=header_index))
    headers = [
        (str(c.value).strip() if c.value is not None else f"(col {c.column_letter})")
        for c in header_cells
    ]

    rows: list[dict] = []
    for excel_row in sheet.iter_rows(min_row=header_index + 1, max_row=min(sheet.max_row, header_index + max_rows)):
        values = [c.value for c in excel_row]
        if all(v is None for v in values):
            continue
        rows.append({headers[i]: normalise(v) for i, v in enumerate(values) if i < len(headers)})

    columns = []
    for index, name in enumerate(headers):
        sample = [r.get(name) for r in rows]
        filled = [v for v in sample if v not in (None, "")]
        types = Counter(cell_type(v) for v in filled)
        distinct = {str(v) for v in filled}
        columns.append(
            {
                "index": index,
                "name": name,
                "filled": len(filled),
                "fill_rate": round(len(filled) / len(rows), 3) if rows else 0,
                "types": dict(types),
                "distinct_values": len(distinct),
                "examples": [str(v)[:60] for v in list(dict.fromkeys(str(v) for v in filled))[:6]],
                "looks_like_report_link": bool(REPORT_LINK_HINTS.search(name)),
            }
        )

    return {
        "sheet": sheet.title,
        "state": sheet.sheet_state,
        "dimensions": sheet.dimensions,
        "max_row": sheet.max_row,
        "max_column": sheet.max_column,
        "header_row": header_index,
        "data_rows": len(rows),
        "columns": columns,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="planilha (padrão: a Lista Mestra em tmp/downloads)")
    parser.add_argument("--max-rows", type=int, default=5000)
    parser.add_argument("--dump-rows", type=int, default=0, help="imprime N linhas da maior aba")
    args = parser.parse_args()

    if args.file:
        path = Path(args.file)
    else:
        candidates = [p for p in DOWNLOADS.rglob("*.xlsx") if "lista" in p.name.lower()]
        if not candidates:
            print("Lista Mestra não encontrada em tmp/downloads — rode scripts/04_fetch.py")
            return 1
        path = candidates[0]

    print(f"planilha: {path.name}  ({path.stat().st_size / 1024:.0f} KB)")
    workbook = load_workbook(path, data_only=True, read_only=False)
    sheets = [analyse_sheet(workbook[name], args.max_rows) for name in workbook.sheetnames]

    schema = {
        "file": path.name,
        "sheets": [
            {k: v for k, v in sheet.items() if k != "rows"} for sheet in sheets
        ],
    }
    out_schema = assert_write_allowed(EXTRACTED / "schema.json")
    out_schema.parent.mkdir(parents=True, exist_ok=True)
    out_schema.write_text(json.dumps(schema, ensure_ascii=False, indent=1), encoding="utf-8")

    out_rows = assert_write_allowed(EXTRACTED / "rows.json")
    out_rows.write_text(
        json.dumps({s["sheet"]: s["rows"] for s in sheets}, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8",
    )

    for sheet in sheets:
        marker = "" if sheet["state"] == "visible" else f"  [{sheet['state']}]"
        print(f"\n  aba {sheet['sheet']!r}{marker}: {sheet['data_rows']} linhas, "
              f"{len(sheet['columns'])} colunas (cabeçalho na linha {sheet['header_row']})")
        for column in sheet["columns"]:
            if column["filled"] == 0:
                continue
            flag = " <== possível vínculo com o relatório" if column["looks_like_report_link"] else ""
            types = ",".join(f"{k}:{v}" for k, v in column["types"].items())
            print(f"      {column['name'][:42]:<44} {column['filled']:>5} preench. "
                  f"{column['distinct_values']:>5} distintos  [{types}]{flag}")
            if column["looks_like_report_link"]:
                print(f"        exemplos: {column['examples']}")

    if args.dump_rows:
        biggest = max(sheets, key=lambda s: s["data_rows"])
        print(f"\n  primeiras {args.dump_rows} linhas de {biggest['sheet']!r}:")
        for row in biggest["rows"][: args.dump_rows]:
            compact = {k: v for k, v in row.items() if v not in (None, "")}
            print("   ", json.dumps(compact, ensure_ascii=False, default=str)[:300])

    print(f"\n  -> {out_schema.relative_to(REPO_ROOT)}")
    print(f"  -> {out_rows.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
