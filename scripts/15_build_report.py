"""Gera o Relatório G2 do zero (DOCX + PDF) a partir das fontes e do modelo (opções completas).

Para a produção mensal use o comando único `scripts/17_generate_report.py` (versões vigentes).
Este script expõe todas as alternativas de fonte (extratos, cópias, overrides):

    .venv\\Scripts\\python scripts/15_build_report.py --report-number 14 --reference-month 2026-08 \\
        --mode reconstruction \\
        --master-list tmp/historical_sources/lista_mestre_v335.0.xlsx \\
        --projects-version 438.0 --environmental-version 310.0 \\
        --inputs tmp/golden_inputs_14.yaml --out output/reconstruction/14

Alternativa offline do 2.2 (extratos/cópia local; o manifesto registra como desvio as abas que
não forem do mesmo snapshot, DEC-012):

        --projects tmp/agent_N/projetos_range.json --projects-version 438.0 \\
        --projects-panel tmp/agent_N/projetos_versions.json --projects-panel-version v438.0 \\
        --projects-ged "tmp/downloads/fontes_de_trabalho/03 - acompanhamento de projetos executivo.xlsx"

Fontes (somente leitura; cópias locais autorizadas em tmp/ ou extratos derivados). Toda versão
aceita `current` = a versão vigente no SharePoint (`sources.versions`), com id e lastModified
registrados no manifesto (`sources` e `source_resolution`):
    --master-list      Lista Mestra .xlsx (manifesto, DEC-006); também alimenta o Excel do
                       Controle de Produtos (DEC-010). É o ARQUIVO local fornecido pela Emmily:
                       o Excel COM exige o arquivo (GAP-015), nada é gravado pelo builder.
    --master-list-version <id|current>
                       com --master-list: rótulo da versão; `current` CONFERE a cópia contra a
                       versão vigente lida em memória (linhas diferentes = erro, baixe de novo).
                       Sem --master-list: lê a versão EM MEMÓRIA (sources.master_list_remote);
                       o Controle de Produtos fica PENDING
    --projects         planilha de projetos .xlsx, ou extrato JSON (`projetos_range.json` /
                       `projetos_versions.json`); `--projects-version` escolhe o snapshot
    --projects-version <id|current>
                       sem --projects: lê a versão da planilha de projetos do SharePoint EM
                       MEMÓRIA (sources.projects_remote); GED, Projetos e Painel de Controle
                       saem da mesma versão
    --projects-text-version  OVERRIDE explícito: o texto do 2.2 lê outra versão do mesmo
                       arquivo (fonte `projects_text`); vai para `deviations` do manifest.json
    --projects-panel   opcional: extrato com a aba Painel de Controle (`--projects-panel-version`)
    --projects-ged     opcional: .xlsx de onde vem a aba GED (ordem dos grupos do 2.2)
    --environmental    planilha ambiental .xlsx, ou extrato JSON do agente B (snapshots/v*.json)
    --environmental-version <id|current>
                       sem --environmental: lê a versão da planilha ambiental EM MEMÓRIA
                       (sources.environmental_remote); Licenças, Condicionantes e Empresas da
                       mesma versão. Com --environmental .xlsx e `current`: confere a cópia

Entradas humanas (`--inputs`, YAML FORA do Git): as chaves de `config/g2_report_model.yaml:
inputs`. Obrigatórias: `signatory_name`, `signature_date` e `issue_date` (as datas também pela
linha de comando, que prevalece). O formato está em `tests/fixtures/golden_inputs_example.yaml`
(sintético). Nome do signatário é dado pessoal: nunca versionar o arquivo real.

Saída em `--out` (padrão output/<nº>_<mês>/, gitignored): DOCX, DOCX final com campos
atualizados (`<stem>_final.docx`), PDF, manifest.json e as pautas `review_brief_<slot>.md`. Sem
Word ou Excel, `--no-office` gera só o DOCX, com o Controle de Produtos e a contagem de páginas
PENDING. Sai com 0 se `ok`, 1 se há pendência/falha, 2 se faltar entrada ou a fonte não conferir.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prog_g2_report.builder.context import BuildMode, ReportContext
from prog_g2_report.builder.generate import (
    InputError,
    SourceMismatchError,
    SourceOptions,
    build_sources,
    default_out,
    load_inputs,
    report_dates,
    run_build,
    summary_lines,
)
from prog_g2_report.model import load_model
from prog_g2_report.report_id import ReportRef


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--report-number", type=int, required=True)
    p.add_argument("--reference-month", required=True, help="AAAA-MM")
    p.add_argument("--issue-date", type=date.fromisoformat, default=None,
                   help="data da capa (AAAA-MM-DD); sem ela, `issue_date` do YAML (obrigatória)")
    p.add_argument("--signature-date", type=date.fromisoformat, default=None,
                   help="data do Encerramento; sem ela, `signature_date` do YAML (obrigatória)")
    p.add_argument("--mode", choices=["production", "reconstruction"], default="production")
    p.add_argument("--master-list", type=Path, default=None,
                   help="arquivo .xlsx (cópia fornecida pela Emmily)")
    p.add_argument("--master-list-version", default=None,
                   help="id ou `current`; com --master-list: rótulo (current confere a cópia); "
                        "sem ele: versão lida em memória, Controle de Produtos PENDING")
    p.add_argument("--env-file", type=Path, default=None,
                   help="opcional: .env da credencial (padrão: .env da raiz do repositório)")
    p.add_argument("--projects", type=Path, default=None)
    p.add_argument("--projects-version", default=None,
                   help="snapshot da planilha de projetos (id ou `current`); sem --projects: "
                        "versão do SharePoint lida em memória (graph_ro)")
    p.add_argument("--projects-text-version", default=None,
                   help="override: versão só do texto do 2.2 (vira desvio no manifesto)")
    p.add_argument("--projects-panel", type=Path, default=None)
    p.add_argument("--projects-panel-version", default=None)
    p.add_argument("--projects-ged", type=Path, default=None)
    p.add_argument("--environmental", type=Path, default=None)
    p.add_argument("--environmental-version", default=None,
                   help="id ou `current`; sem --environmental: versão do SharePoint lida em "
                        "memória (graph_ro)")
    p.add_argument("--inputs", type=Path, required=True, help="YAML de entradas humanas")
    p.add_argument("--assets-dir", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--no-office", action="store_true", help="sem Excel/Word (só DOCX)")
    return p


def main(argv: list[str] | None = None, *, client: object = None) -> int:
    args = parser().parse_args(argv)
    try:
        inputs = load_inputs(args.inputs)
        issue, signature = report_dates(inputs, args.issue_date, args.signature_date)
        sources, resolution = build_sources(SourceOptions.from_namespace(args), load_model(),
                                            client=client, env_file=args.env_file)
    except (InputError, SourceMismatchError, LookupError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    report = ReportContext(
        ReportRef(args.report_number, args.reference_month), issue_date=issue,
        signature_date=signature,
        mode=BuildMode.RECONSTRUCTION if args.mode == "reconstruction" else BuildMode.PRODUCTION,
    )
    out = args.out or default_out(args.report_number, args.reference_month)
    generated = run_build(report, sources, inputs, out, resolution=resolution,
                          office=not args.no_office, assets_dir=args.assets_dir,
                          inputs_path=args.inputs)
    for line in summary_lines(generated):
        print(line)
    return 0 if generated.result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
