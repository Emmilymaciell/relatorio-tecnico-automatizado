"""Comando único da produção mensal: gera o Relatório G2 nº N — Mês/AAAA (DOCX + PDF).

    .venv\\Scripts\\python scripts\\17_generate_report.py --report-number 15 \\
        --reference-month 2026-09 --inputs tmp\\producao\\15_2026-09\\entradas_15.yaml \\
        --master-list tmp\\producao\\15_2026-09\\lista_mestre.xlsx

É o `generate_report(report_number, reference_month)` da Fase 11
(`prog_g2_report.builder.generate.generate_report`):

- Lista Mestra: o ARQUIVO local que a Emmily baixou (o Controle de Produtos é exportado pelo
  Excel COM a partir dele; DEC-010, GAP-015). Ele é conferido contra a versão vigente lida em
  memória do SharePoint (`--master-list-version`, padrão `current`): linhas diferentes = erro
  (alguém editou depois do download; baixe de novo).
- Planilha de projetos e planilha ambiental: a versão vigente (`current`) lida EM MEMÓRIA do
  SharePoint (graph_ro, só GET; nada gravado em disco). `--projects-version` e
  `--environmental-version` fixam outra versão (reconstrução histórica).
- Datas e signatário: `issue_date`, `signature_date` e `signatory_name` do YAML de entradas
  (`config/g2_report_model.yaml: inputs`, obrigatórios).
- Saída (padrão `output\\<NN>_<AAAA-MM>\\`): DOCX, DOCX final com campos atualizados
  (`<stem>_final.docx`), PDF, `manifest.json` (versões com id e lastModified, validações,
  pendências) e `review_brief_<slot>.md` para cada texto interpretativo sem revisão.

No fim imprime o resumo (ok, páginas, fontes, validações, pendências, avisos, caminhos). Código
de saída: 0 = pronto (`ok=True`); 1 = há pendência, falha ou validação com erro; 2 = entrada
obrigatória ausente ou cópia da Lista Mestra diferente da versão pedida.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prog_g2_report.builder.generate import (
    InputError,
    SourceMismatchError,
    generate_report,
    summary_lines,
)
from prog_g2_report.sources.versions import CURRENT


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--report-number", type=int, required=True)
    p.add_argument("--reference-month", required=True, help="AAAA-MM")
    p.add_argument("--inputs", type=Path, required=True,
                   help="YAML de entradas humanas (issue_date, signature_date, signatory_name…)")
    p.add_argument("--master-list", type=Path, required=True,
                   help="Lista Mestra .xlsx baixada pela Emmily (o Excel COM exige o arquivo)")
    p.add_argument("--out", type=Path, default=None, help="padrão: output/<NN>_<AAAA-MM>/")
    p.add_argument("--master-list-version", default=CURRENT,
                   help="versão que a cópia local deve ser (padrão: current)")
    p.add_argument("--projects-version", default=CURRENT, help="padrão: current")
    p.add_argument("--environmental-version", default=CURRENT, help="padrão: current")
    p.add_argument("--mode", choices=["production", "reconstruction"], default="production")
    p.add_argument("--env-file", type=Path, default=None,
                   help="opcional: .env da credencial (padrão: .env da raiz do repositório)")
    p.add_argument("--assets-dir", type=Path, default=None)
    p.add_argument("--no-office", action="store_true",
                   help="sem Excel/Word: só o DOCX, para colher os rascunhos (nunca é entrega)")
    return p


def main(argv: list[str] | None = None, *, client: object = None, build: object = None) -> int:
    args = parser().parse_args(argv)
    try:
        generated = generate_report(
            args.report_number, args.reference_month, inputs_path=args.inputs,
            master_list=args.master_list, out=args.out,
            master_list_version=args.master_list_version,
            projects_version=args.projects_version,
            environmental_version=args.environmental_version, mode=args.mode,
            office=not args.no_office, env_file=args.env_file, assets_dir=args.assets_dir,
            client=client, build=build)  # type: ignore[arg-type]
    except (InputError, SourceMismatchError, LookupError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    for line in summary_lines(generated):
        print(line)
    return 0 if generated.result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
