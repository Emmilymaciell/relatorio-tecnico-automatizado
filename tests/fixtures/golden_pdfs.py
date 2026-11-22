"""Localiza os PDFs do golden (nunca versionados): referência publicada em
tmp/downloads/relatorios_11_14/ e builds em output/reconstruction/<build>/, neste checkout, no
principal ou num worktree irmão. Variáveis de ambiente sobrepõem: PROG_G2_REFERENCE_DIR e
PROG_G2_GENERATED_<N>_PDF."""

from __future__ import annotations

import os
from pathlib import Path

from prog_g2_report.report_id import parse_report_filename

ROOT = Path(__file__).resolve().parents[2]
GENERATED_FILES = {14: "relatorio_g2_n14_2026-08.pdf", 13: "relatorio_g2_n13_2026-07.pdf"}


def main_checkout() -> Path | None:
    parts = ROOT.parts
    for i in range(len(parts) - 1):
        if parts[i] == ".claude" and parts[i + 1] == "worktrees":
            return Path(*parts[:i])
    return None


def _bases() -> list[Path]:
    bases = [ROOT]
    main = main_checkout()
    if main:
        bases.append(main)
        worktrees = main / ".claude" / "worktrees"
        bases += sorted(worktrees.iterdir()) if worktrees.is_dir() else []
    return bases


def reference_pdf(number: int) -> Path | None:
    dirs = [Path(d) for d in [os.environ.get("PROG_G2_REFERENCE_DIR")] if d]
    dirs += [base / "tmp" / "downloads" / "relatorios_11_14" for base in _bases()[:2]]
    for d in dirs:
        for pdf in sorted(d.glob("*.pdf")) if d.is_dir() else []:
            ref = parse_report_filename(pdf.name)
            if ref and ref.report_number == number:
                return pdf
    return None


def generated_pdf(number: int, builds: tuple[str, ...]) -> Path | None:
    candidates = [Path(p) for p in [os.environ.get(f"PROG_G2_GENERATED_{number}_PDF")] if p]
    for build in builds:
        candidates += [base / "output" / "reconstruction" / build / GENERATED_FILES[number]
                       for base in _bases()]
    return next((p for p in candidates if p.is_file()), None)
