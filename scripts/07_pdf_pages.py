"""FASE 3 — geometria e conteudo pagina a pagina dos PDF do Relatorio G2.

    .venv\\Scripts\\python scripts\\07_pdf_pages.py
    .venv\\Scripts\\python scripts\\07_pdf_pages.py --render 1 2 3   # render de paginas

O PDF e a REFERENCIA VISUAL (DEC-005): e o que o leitor recebe. Este script mede, sem
OCR, usando a camada de texto vetorial e os objetos de imagem:

    por pagina   tamanho, orientacao, rotacao, nº de imagens, nº de blocos de texto,
                 caracteres, fontes usadas, texto do cabecalho e do rodape, area coberta
                 por imagem, primeira linha util (titulo aparente)
    por arquivo  totais, contagem de paginas retrato/paisagem, inventario de fontes

Saidas: `tmp/extracted/<relatorio>/pages.json` e, com --render, PNG em `tmp/renders/`.

So le arquivos ja baixados em tmp/. Nao acessa o SharePoint.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prog_g2_report import REPO_ROOT
from prog_g2_report.report_id import format_report, parse_report_filename
from prog_g2_report.security import assert_write_allowed

DOWNLOADS = REPO_ROOT / "tmp" / "downloads"
EXTRACTED = REPO_ROOT / "tmp" / "extracted"
RENDERS = REPO_ROOT / "tmp" / "renders"

PT_PER_CM = 28.3465
# Faixas verticais (fracao da altura) tratadas como cabecalho e rodape.
HEADER_BAND = 0.08
FOOTER_BAND = 0.92


def band_text(page, top: float, bottom: float) -> str:
    rect = fitz.Rect(0, page.rect.height * top, page.rect.width, page.rect.height * bottom)
    return " ".join(page.get_text("text", clip=rect).split())[:200]


def page_record(page, index: int) -> dict:
    rect = page.rect
    width_cm = round(rect.width / PT_PER_CM, 2)
    height_cm = round(rect.height / PT_PER_CM, 2)
    text = page.get_text("text")
    blocks = page.get_text("dict")["blocks"]
    image_blocks = [b for b in blocks if b.get("type") == 1]
    fonts = Counter()
    for block in blocks:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                fonts[f"{span['font']}|{round(span['size'], 1)}"] += len(span.get("text", ""))

    image_area = sum(
        (b["bbox"][2] - b["bbox"][0]) * (b["bbox"][3] - b["bbox"][1]) for b in image_blocks
    )
    body = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return {
        "page": index + 1,
        "width_cm": width_cm,
        "height_cm": height_cm,
        "orientation": "landscape" if rect.width > rect.height else "portrait",
        "rotation": page.rotation,
        "text_chars": len(text.strip()),
        "text_blocks": len([b for b in blocks if b.get("type") == 0]),
        "images": len(image_blocks),
        "image_area_ratio": round(image_area / (rect.width * rect.height), 3),
        "header_text": band_text(page, 0, HEADER_BAND),
        "footer_text": band_text(page, FOOTER_BAND, 1),
        "first_line": body[0][:110] if body else "",
        "fonts": [f for f, _ in fonts.most_common(5)],
        "dominant_font": fonts.most_common(1)[0][0] if fonts else None,
    }


def analyse(path: Path, render_pages: list[int]) -> dict:
    document = fitz.open(path)
    pages = [page_record(page, index) for index, page in enumerate(document)]
    parsed = parse_report_filename(path.name)
    slug = f"relatorio_{parsed.report_number:02d}" if parsed else path.stem[:40]

    if render_pages:
        target = RENDERS / slug
        assert_write_allowed(target / "x.png")
        target.mkdir(parents=True, exist_ok=True)
        for number in render_pages:
            if 1 <= number <= len(document):
                pixmap = document[number - 1].get_pixmap(dpi=110)
                pixmap.save(target / f"page_{number:03d}.png")

    all_fonts = Counter(f for p in pages for f in p["fonts"])
    document.close()
    return {
        "file": path.name,
        "report_number": parsed.report_number if parsed else None,
        "reference_month": parsed.reference_month if parsed else None,
        "label": format_report(parsed.report_number, parsed.reference_month) if parsed else None,
        "page_count": len(pages),
        "portrait_pages": len([p for p in pages if p["orientation"] == "portrait"]),
        "landscape_pages": len([p for p in pages if p["orientation"] == "landscape"]),
        "pages_with_images": len([p for p in pages if p["images"]]),
        "total_images": sum(p["images"] for p in pages),
        "fonts": dict(all_fonts.most_common(12)),
        "pages": pages,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", nargs="*", default=[])
    parser.add_argument("--render", type=int, nargs="*", default=[], help="páginas a renderizar")
    args = parser.parse_args()

    files = [Path(f) for f in args.file] if args.file else sorted(DOWNLOADS.rglob("*.pdf"))
    if not files:
        print("nenhum .pdf em tmp/downloads/ — rode scripts/04_fetch.py antes")
        return 1

    for path in files:
        data = analyse(path, args.render)
        slug = f"relatorio_{data['report_number']:02d}" if data["report_number"] else path.stem[:40]
        out = assert_write_allowed(EXTRACTED / slug / "pages.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(
            f"{data['label'] or path.name}: {data['page_count']} páginas "
            f"({data['portrait_pages']} retrato, {data['landscape_pages']} paisagem), "
            f"{data['total_images']} imagens em {data['pages_with_images']} páginas"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
