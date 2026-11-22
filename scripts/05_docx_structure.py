"""FASE 3 — extrai a estrutura de um DOCX do Relatorio G2 para JSON analisavel.

    .venv\\Scripts\\python scripts\\05_docx_structure.py            # todos em tmp/downloads
    .venv\\Scripts\\python scripts\\05_docx_structure.py --file X.docx

Le o pacote OOXML direto (zip + lxml), sem depender de Word. Para cada documento grava
`tmp/extracted/<relatorio>/structure.json` com:

    sections     tamanho da pagina, orientacao, margens, distancia de header/footer
    paragraphs   texto, estilo, nivel de titulo, alinhamento, quebras
    tables       dimensoes, larguras de coluna, primeira linha
    images       relacao, arquivo de midia, dimensoes em EMU/cm, ancoragem, crop
    fields       campos (TOC, PAGE, NUMPAGES, REF...)
    headers      cabecalhos e rodapes por secao
    media        inventario de `word/media/` com sha1 (identidade de asset)

Somente leitura sobre arquivos ja baixados em tmp/. Nao acessa o SharePoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prog_g2_report import REPO_ROOT
from prog_g2_report.report_id import format_report, parse_report_filename
from prog_g2_report.security import assert_write_allowed

DOWNLOADS = REPO_ROOT / "tmp" / "downloads"
EXTRACTED = REPO_ROOT / "tmp" / "extracted"

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
EMU_PER_CM = 360000
TWIP_PER_CM = 567


def w(tag: str) -> str:
    return f"{{{NS['w']}}}{tag}"


def attr(element, name: str, default=None):
    return element.get(w(name), default) if element is not None else default


def twips_to_cm(value) -> float | None:
    try:
        return round(int(value) / TWIP_PER_CM, 2)
    except (TypeError, ValueError):
        return None


def section_properties(section_pr) -> dict:
    size = section_pr.find(w("pgSz"))
    margin = section_pr.find(w("pgMar"))
    return {
        "orientation": attr(size, "orient", "portrait"),
        "page_width_cm": twips_to_cm(attr(size, "w")),
        "page_height_cm": twips_to_cm(attr(size, "h")),
        "margin_top_cm": twips_to_cm(attr(margin, "top")),
        "margin_bottom_cm": twips_to_cm(attr(margin, "bottom")),
        "margin_left_cm": twips_to_cm(attr(margin, "left")),
        "margin_right_cm": twips_to_cm(attr(margin, "right")),
        "header_distance_cm": twips_to_cm(attr(margin, "header")),
        "footer_distance_cm": twips_to_cm(attr(margin, "footer")),
        "type": attr(section_pr.find(w("type")), "val", "nextPage"),
        "titlePg": section_pr.find(w("titlePg")) is not None,
        "header_refs": [
            {"type": attr(ref, "type"), "rel": ref.get(f"{{{NS['r']}}}id")}
            for ref in section_pr.findall(w("headerReference"))
        ],
        "footer_refs": [
            {"type": attr(ref, "type"), "rel": ref.get(f"{{{NS['r']}}}id")}
            for ref in section_pr.findall(w("footerReference"))
        ],
    }


def paragraph_info(paragraph, index: int, section: int) -> dict:
    ppr = paragraph.find(w("pPr"))
    style = attr(ppr.find(w("pStyle")), "val") if ppr is not None else None
    numpr = ppr.find(w("numPr")) if ppr is not None else None
    text = "".join(node.text or "" for node in paragraph.iter(w("t")))
    drawings = paragraph.findall(f".//{{{NS['wp']}}}inline") + paragraph.findall(
        f".//{{{NS['wp']}}}anchor"
    )
    return {
        "index": index,
        "section": section,
        "style": style,
        "outline_level": attr(ppr.find(w("outlineLvl")), "val") if ppr is not None else None,
        "alignment": attr(ppr.find(w("jc")), "val") if ppr is not None else None,
        "numbered": numpr is not None,
        "page_break_before": (ppr is not None and ppr.find(w("pageBreakBefore")) is not None)
        or any(attr(br, "type") == "page" for br in paragraph.findall(f".//{w('br')}")),
        "keep_next": ppr is not None and ppr.find(w("keepNext")) is not None,
        "keep_lines": ppr is not None and ppr.find(w("keepLines")) is not None,
        "text": text,
        "chars": len(text),
        "inline_images": len(drawings),
        "has_field": bool(paragraph.findall(f".//{w('fldChar')}") or paragraph.findall(f".//{w('fldSimple')}")),
    }


def image_info(drawing, index: int) -> dict:
    anchored = drawing.tag.endswith("anchor")
    extent = drawing.find(f".//{{{NS['wp']}}}extent")
    blip = drawing.find(f".//{{{NS['a']}}}blip")
    src_rect = drawing.find(f".//{{{NS['a']}}}srcRect")
    doc_pr = drawing.find(f".//{{{NS['wp']}}}docPr")
    width = int(extent.get("cx")) if extent is not None and extent.get("cx") else None
    height = int(extent.get("cy")) if extent is not None and extent.get("cy") else None
    crop = None
    if src_rect is not None:
        crop = {side: int(src_rect.get(side, 0)) / 1000 for side in ("l", "t", "r", "b")}
    return {
        "index": index,
        "anchored": anchored,
        "name": doc_pr.get("name") if doc_pr is not None else None,
        "description": doc_pr.get("descr") if doc_pr is not None else None,
        "rel_id": blip.get(f"{{{NS['r']}}}embed") if blip is not None else None,
        "width_emu": width,
        "height_emu": height,
        "width_cm": round(width / EMU_PER_CM, 2) if width else None,
        "height_cm": round(height / EMU_PER_CM, 2) if height else None,
        "crop_percent": crop,
    }


def table_info(table, index: int) -> dict:
    rows = table.findall(w("tr"))
    grid = table.find(w("tblGrid"))
    first_row = []
    if rows:
        for cell in rows[0].findall(w("tc")):
            first_row.append("".join(node.text or "" for node in cell.iter(w("t")))[:60])
    tblpr = table.find(w("tblPr"))
    return {
        "index": index,
        "rows": len(rows),
        "columns": len(grid.findall(w("gridCol"))) if grid is not None else None,
        "column_widths_cm": [twips_to_cm(c.get(w("w"))) for c in grid.findall(w("gridCol"))]
        if grid is not None
        else [],
        "style": attr(tblpr.find(w("tblStyle")), "val") if tblpr is not None else None,
        "first_row": first_row,
    }


def field_codes(root) -> list[str]:
    codes = []
    for instr in root.findall(f".//{w('instrText')}"):
        if instr.text and instr.text.strip():
            codes.append(instr.text.strip())
    for simple in root.findall(f".//{w('fldSimple')}"):
        value = attr(simple, "instr")
        if value:
            codes.append(value.strip())
    return codes


def analyse(path: Path) -> dict:
    with zipfile.ZipFile(path) as package:
        names = package.namelist()
        document = etree.fromstring(package.read("word/document.xml"))
        relationships = {}
        if "word/_rels/document.xml.rels" in names:
            rels = etree.fromstring(package.read("word/_rels/document.xml.rels"))
            relationships = {
                rel.get("Id"): {"target": rel.get("Target"), "type": rel.get("Type").rsplit("/", 1)[-1]}
                for rel in rels
            }
        media = []
        for name in sorted(n for n in names if n.startswith("word/media/")):
            data = package.read(name)
            media.append(
                {
                    "file": name.split("/")[-1],
                    "bytes": len(data),
                    "sha1": hashlib.sha1(data).hexdigest(),
                }
            )
        headers = {}
        for name in sorted(n for n in names if re.match(r"word/(header|footer)\d+\.xml", n)):
            root = etree.fromstring(package.read(name))
            text = " ".join(node.text or "" for node in root.iter(w("t"))).strip()
            headers[name.split("/")[-1]] = {
                "text": text[:300],
                "fields": field_codes(root),
                "images": len(root.findall(f".//{{{NS['a']}}}blip")),
            }

    body = document.find(w("body"))
    sections: list[dict] = []
    paragraphs: list[dict] = []
    tables: list[dict] = []
    images: list[dict] = []

    section_index = 0
    for index, child in enumerate(body):
        if child.tag == w("p"):
            paragraphs.append(paragraph_info(child, index, section_index))
            inner = child.find(f".//{w('sectPr')}")
            if inner is not None:
                sections.append({"index": section_index, "ends_at_paragraph": index, **section_properties(inner)})
                section_index += 1
        elif child.tag == w("tbl"):
            tables.append(table_info(child, index))
        elif child.tag == w("sectPr"):
            sections.append({"index": section_index, "ends_at_paragraph": index, "final": True, **section_properties(child)})

    for index, drawing in enumerate(
        document.findall(f".//{{{NS['wp']}}}inline") + document.findall(f".//{{{NS['wp']}}}anchor")
    ):
        info = image_info(drawing, index)
        info["media_file"] = (
            relationships.get(info["rel_id"], {}).get("target", "").rsplit("/", 1)[-1]
            if info["rel_id"]
            else None
        )
        images.append(info)

    parsed = parse_report_filename(path.name)
    return {
        "file": path.name,
        "report_number": parsed.report_number if parsed else None,
        "reference_month": parsed.reference_month if parsed else None,
        "label": format_report(parsed.report_number, parsed.reference_month) if parsed else None,
        "size_bytes": path.stat().st_size,
        "counts": {
            "sections": len(sections),
            "paragraphs": len(paragraphs),
            "non_empty_paragraphs": len([p for p in paragraphs if p["text"].strip()]),
            "tables": len(tables),
            "images": len(images),
            "media_files": len(media),
            "headers_footers": len(headers),
        },
        "sections": sections,
        "paragraphs": paragraphs,
        "tables": tables,
        "images": images,
        "media": media,
        "headers_footers": headers,
        "fields": field_codes(document),
        "relationships_external": [
            r for r in relationships.values() if r["type"] in ("hyperlink", "oleObject", "package")
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", nargs="*", default=[], help="docx específico")
    args = parser.parse_args()

    files = [Path(f) for f in args.file] if args.file else sorted(DOWNLOADS.rglob("*.docx"))
    if not files:
        print("nenhum .docx em tmp/downloads/ — rode scripts/04_fetch.py antes")
        return 1

    for path in files:
        data = analyse(path)
        slug = f"relatorio_{data['report_number']:02d}" if data["report_number"] else path.stem[:40]
        out = assert_write_allowed(EXTRACTED / slug / "structure.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        counts = data["counts"]
        print(
            f"{data['label'] or path.name}: {counts['sections']} seções, "
            f"{counts['non_empty_paragraphs']} parágrafos, {counts['tables']} tabelas, "
            f"{counts['images']} imagens, {counts['media_files']} mídias"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
