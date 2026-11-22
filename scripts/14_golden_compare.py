"""Golden test: compara o PDF de referência (histórico) com o PDF gerado do zero.

    .venv\\Scripts\\python scripts/14_golden_compare.py \\
        --reference tmp/ref/relatorio_14.pdf --generated output/reconstruction/14/g2_14.pdf \\
        --report-number 14 --out output/reconstruction/14/golden.json

Gera `<out>.json` e `<out>.md` (métricas + diagnóstico). `--facts-dir` grava também os fatos
extraídos de cada PDF. Sai com código 0 se PASS, 1 se FAIL, 2 se as allowances forem inválidas
(inclusive `pending_decision: true`, recusada desde o comparador 3.0).
Comparador v4.x: diff de texto estrito; todo trecho divergente é CRITICAL salvo se estiver no
conjunto CONGELADO de hunks aprovados registrado nas allowances (`approved_hunks`, sha256
conferido). `--approved-hunks ARQ.yaml` só troca o CAMINHO: o arquivo tem de ter o sha256
registrado nas allowances para o relatório (4.1, QA4-E; senão sai com código 2). v4.1: o hunk
aprovado é posicional (bloco, parágrafo no bloco, tokens na referência, bloco gerado).
`--draft-hunks ARQ.yaml` grava o rascunho do diff
atual (hunks já aprovados com a referência; os novos com `reference: null`, que o parser recusa
até serem classificados). Allowances congeladas para o v1.0/v2.0/v3.0 são aceitas com aviso (não
cobrem as verificações novas). As regiões dos painéis raster vêm de
`src/prog_g2_report/qa/raster_regions.yaml` (sha256 em `metrics.figures.regions_sha256`). O
nome do signatário só entra no relatório por hash.

A extração é independente do builder (só lê PDF) e a lista de desvios permitidos é a
CONGELADA em `config/golden_allowances.yaml` (WAVE1_FINDINGS §H). Nada é escrito fora de
`--out`/`--facts-dir`; o PDF de referência é só lido.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from prog_g2_report.qa.compare import (
    DEFAULT_ALLOWANCES,
    AllowanceError,
    compare,
    draft_hunks,
    load_allowances,
)
from prog_g2_report.qa.extract import extract_facts
from prog_g2_report.security import assert_write_allowed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reference", required=True, type=Path, help="PDF histórico")
    parser.add_argument("--generated", required=True, type=Path, help="PDF gerado do zero")
    parser.add_argument("--report-number", required=True, type=int, help="nº do Relatório G2")
    parser.add_argument("--out", required=True, type=Path,
                        help="caminho base do relatório (.json e .md)")
    parser.add_argument("--allowances", type=Path, default=DEFAULT_ALLOWANCES)
    parser.add_argument("--facts-dir", type=Path, default=None,
                        help="opcional: grava reference_facts_N.json e generated_facts_N.json")
    parser.add_argument("--approved-hunks", type=Path, default=None,
                        help="caminho do conjunto de hunks aprovados (padrão: o registrado nas "
                             "allowances); o sha256 tem de ser o registrado nelas")
    parser.add_argument("--draft-hunks", type=Path, default=None,
                        help="opcional: grava o rascunho de hunks do diff atual (YAML)")
    args = parser.parse_args(argv)

    try:
        allowances = load_allowances(args.allowances)
        hunks = (allowances.load_hunks_file(args.approved_hunks, args.report_number)
                 if args.approved_hunks else allowances.approved_hunks(args.report_number))
    except AllowanceError as exc:
        print(f"allowances ou hunks aprovados inválidos: {exc}", file=sys.stderr)
        return 2
    for warning in allowances.warnings:
        print(f"aviso: {warning}", file=sys.stderr)

    reference = extract_facts(args.reference)
    generated = extract_facts(args.generated)
    report = compare(reference, generated, allowances, report_number=args.report_number,
                     approved_hunks=hunks)

    base = args.out.with_suffix("")
    json_path, md_path = base.with_suffix(".json"), base.with_suffix(".md")
    for path in (json_path, md_path):
        assert_write_allowed(path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=1),
                         encoding="utf-8")
    md_path.write_text(report.to_markdown(), encoding="utf-8")

    if args.facts_dir:
        args.facts_dir.mkdir(parents=True, exist_ok=True)
        for name, facts in (("reference", reference), ("generated", generated)):
            path = args.facts_dir / f"{name}_facts_{args.report_number}.json"
            assert_write_allowed(path)
            path.write_text(json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")

    if args.draft_hunks:
        assert_write_allowed(args.draft_hunks)
        args.draft_hunks.parent.mkdir(parents=True, exist_ok=True)
        args.draft_hunks.write_text(
            yaml.safe_dump(draft_hunks(report, approved=hunks), allow_unicode=True,
                           sort_keys=False, width=100), encoding="utf-8")

    m = report.metrics
    print(f"{report.verdict} · score estrutural {m['structural_score']:.4f} · "
          f"conteúdo {m['content_accuracy']:.4f} · {m['severity_counts']}")
    for reason in report.reasons:
        print(f"  - {reason}")
    td = m.get("text_diff") or {}
    print(f"texto estrito: {td.get('hunks')} hunks, {td.get('approved')} aprovados, "
          f"{td.get('unapproved')} não aprovados, órfãos {td.get('orphans')}")
    for warning in report.warnings[len(allowances.warnings):]:
        print(f"aviso: {warning}", file=sys.stderr)
    print(f"relatório: {json_path} e {md_path}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
