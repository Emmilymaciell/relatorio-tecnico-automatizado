r"""Extrai os STATIC_ASSET do Relatório G2 nº 14 e escreve o manifesto versionado.

    .venv\Scripts\python scripts\13_extract_static_assets.py

Lê os DOCX já autorizados em tmp/downloads/relatorios_11_14/ (somente leitura) e grava as mídias
em assets/discovered/raw/ (gitignored: há fotos com pessoas) com nome canônico. O manifesto
config/assets_manifest.yaml (versionado) guarda sha1, formato e dimensões; o builder recusa um
asset cujo sha1 não bata. Origem: agente I, Wave 1 (docs/discovery/WAVE1_FINDINGS.md §I).
"""
from __future__ import annotations

import glob
import hashlib
import io
import re
import struct
import zipfile
from pathlib import Path

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tmp" / "downloads" / "relatorios_11_14"
RAW = ROOT / "assets" / "discovered" / "raw"
OUT = ROOT / "config" / "assets_manifest.yaml"
MONTH = {"11": "2026-05", "12": "2026-06", "13": "2026-07", "14": "2026-08"}
EMU_CM = 360000
PPTX = "word/embeddings/Microsoft_PowerPoint_Presentation.pptx"


def docx_for(n: str) -> Path:
    return next(Path(p) for p in glob.glob(str(SRC / "*.docx")) if re.search(rf"n°{n} ", p))


def sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


ZIPS = {n: zipfile.ZipFile(docx_for(n)) for n in MONTH}
PPTXS = {n: zipfile.ZipFile(io.BytesIO(z.read(PPTX))) for n, z in ZIPS.items()}
DOCX_SHA = {n: {sha1(z.read(i)): i for i in z.namelist() if i.startswith("word/media/")} for n, z in ZIPS.items()}
PPTX_SHA = {n: {sha1(p.read(i)): i for i in p.namelist() if i.startswith("ppt/media/")} for n, p in PPTXS.items()}

# (asset_id, origem, parte, ext, extent_emu ou None, placement, pessoas, nota)
ASSETS = [
    ("presentation_coordination_strip", "docx", "word/media/image2.png", "png", (5774400, 1868400),
     "seção 0, pág. 3, Apresentação (body[8]), inline 16,04 cm", True,
     "faixa com 5 fotos + legendas das coordenações (não é logotipo); fotos ilustrativas com pessoas, 1 rosto visível"),
    ("landscape_block_01_delivery_periodicity", "docx", "word/media/image3.png", "png", None,
     "seção 1 (paisagem), pág. 7, body[58], inline jc=center", False, "tabela 'Visão geral — periodicidade de entregas'"),
    ("landscape_block_02_periodic_reports", "docx", "word/media/image4.png", "png", None,
     "seção 1, pág. 8, body[59], inline", False, "quadro 'Relatórios periódicos'"),
    ("landscape_block_03_environmental_conditions", "docx", "word/media/image5.png", "png", None,
     "seção 1, pág. 9, body[60], inline; 27,02 cm > 26,20 cm úteis (anomalia herdada)", False,
     "quadro 'Condicionantes ambientais'"),
    ("landscape_block_04_meeting_minutes", "docx", "word/media/image6.png", "png", None,
     "seção 1, pág. 10, body[61], inline; 26,45 cm > 26,20 cm úteis (anomalia herdada)", False,
     "quadro 'Atas e memórias de reunião'"),
    ("landscape_block_05_operational_org_cover", "docx", "word/media/image7.jpg", "jpg", None,
     "seção 1, pág. 11, body[62] run 1 (4 imagens no mesmo parágrafo)", False,
     "capa 'Consolidação da organização operacional' (slide exportado)"),
    ("landscape_block_06_functional_org_chart", "docx", "word/media/image8.jpg", "jpg", None,
     "seção 1, pág. 12, body[62] run 2", False, "organograma funcional: só cargos/funções, sem nomes nem fotos"),
    ("landscape_block_07_projects_coordination", "docx", "word/media/image9.jpg", "jpg", None,
     "seção 1, pág. 13, body[62] run 3", False, "Coordenação de Projetos (slide); sem nomes nem fotos"),
    ("landscape_block_08_works_field_coordination", "docx", "word/media/image10.jpg", "jpg", None,
     "seção 1, pág. 14, body[62] run 4", False, "Coordenação de Obras e Campo (slide); sem nomes nem fotos"),
    ("p22_predecessor_disciplines_diagram", "docx", "word/media/image12.emf", "emf", None,
     "seção 2, pág. 17, P2.2 (body[84]), inline 15,22 cm", False, "EMF vetorial; no nº 11 a parte se chama image9.emf"),
    ("cover_slide_template", "pptx_package", PPTX, "pptx", (7560000, 10692000),
     "parágrafo 0, objeto OLE PowerPoint.Show.12 (sangria total)", False,
     "pacote do slide de capa do nº 14; campos variáveis em ppt/slides/slide1.xml sp id=41 e id=42"),
    ("cover_photo_background", "pptx", "ppt/media/image2.jpeg", "jpeg", (7003775, 10116562),
     "dentro do pptx: slideLayout1 'Picture 3', srcRect l=14342 t=-863 r=47361 b=17886, off(-145775,-105280)", False,
     "foto aérea de rodovia/floresta, sem pessoas"),
    ("cover_logo_prog", "pptx", "ppt/media/image3.svg", "svg", (2855527, 1530798),
     "dentro do pptx: slide1 'Gráfico 2' off(1040669,983324)", False, "SVG vetorial branco; a:blip sem fallback raster"),
    ("cover_logos_partners", "pptx", "ppt/media/image4.svg", "svg", (1887636, 3214034),
     "dentro do pptx: slide1 'Gráfico 3' off(1040669,3345983)", False,
     "SVG que embute PNG 620x1064 (Dynatest, Escritório Jurídico, Consultoria de Engenharia, Certificadora)"),
    ("cover_thinkcell_placeholder", "pptx", "ppt/media/image1.emf", "emf", (894, 2294),
     "dentro do pptx: slideMaster1 'Objeto 6' hidden (think-cell)", False, "resíduo do think-cell, oculto, não aparece"),
]


def emf_dims(b: bytes) -> dict:
    bx = struct.unpack_from("<4i", b, 8)
    fr = struct.unpack_from("<4i", b, 24)
    return {"bounds_px": [bx[2] - bx[0] + 1, bx[3] - bx[1] + 1],
            "frame_cm": [round((fr[2] - fr[0]) / 1000, 2), round((fr[3] - fr[1]) / 1000, 2)]}


def inline_extent(part: str) -> tuple[int, int] | None:
    z = ZIPS["14"]
    rels = z.read("word/_rels/document.xml.rels").decode()
    rid = re.search(rf'Id="(rId\d+)"[^>]*Target="{re.escape(part[5:])}"', rels) or \
        re.search(rf'Target="{re.escape(part[5:])}"[^>]*Id="(rId\d+)"', rels)
    xml = z.read("word/document.xml").decode()
    m = re.search(rf'<wp:extent cx="(\d+)" cy="(\d+)"/>(?:(?!</wp:inline>).)*?r:embed="{rid.group(1)}"', xml, re.S)
    return (int(m.group(1)), int(m.group(2))) if m else None


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = []
    for aid, origin, part, ext, extent, placement, people, note in ASSETS:
        if origin == "docx":
            data = ZIPS["14"].read(part)
            same = {MONTH[n]: DOCX_SHA[n].get(sha1(data)) for n in MONTH}
            extent = extent or inline_extent(part)
        elif origin == "pptx":
            data = PPTXS["14"].read(part)
            same = {MONTH[n]: PPTX_SHA[n].get(sha1(data)) for n in MONTH}
        else:
            data = ZIPS["14"].read(part)
            same = {MONTH[n]: ("idêntico" if sha1(ZIPS[n].read(PPTX)) == sha1(data) else
                               "difere (só slide1/thumbnail/props; ver cover_media)") for n in MONTH}
        f = RAW / f"{aid}.{ext}"
        f.write_bytes(data)
        months_present = [m for m, v in same.items() if v and not str(v).startswith("difere")]
        if ext in ("png", "jpg", "jpeg"):
            im = Image.open(io.BytesIO(data))
            intrinsic = {"px": list(im.size), "mode": im.mode,
                         "dpi": [round(float(x), 1) for x in im.info["dpi"]] if "dpi" in im.info else None}
        elif ext == "emf":
            intrinsic = emf_dims(data)
        elif ext == "svg":
            vb = re.search(rb'viewBox="([^"]+)"', data[:400]) or re.search(rb'width="(\d+)" height="(\d+)"', data[:400])
            intrinsic = {"svg_header": vb.group(0).decode()}
        else:
            intrinsic = {"bytes": len(data)}
        manifest.append({
            "asset_id": aid,
            "file": f"assets/discovered/raw/{aid}.{ext}",
            "source_part": f"nº 14 DOCX :: {part}" if origin != "pptx" else f"nº 14 DOCX :: {PPTX} :: {part}",
            "sha1": sha1(data), "bytes": len(data), "format": ext.upper().replace("JPG", "JPEG"),
            "intrinsic": intrinsic,
            "width_cm": round(extent[0] / EMU_CM, 2) if extent else None,
            "height_cm": round(extent[1] / EMU_CM, 2) if extent else None,
            "placement": placement,
            "identical_sha1_in": same,
            "stable_since": (months_present[0] if months_present else None),
            "stable_since_note": "janela de evidência começa em 2026-05 (nº 11); antes disso não verificado",
            "contains_people_photos": people,
            "classification": "STATIC_ASSET",
            "note": note,
        })
    OUT.write_text(yaml.safe_dump({
        "_meta": {
            "generated_by": "scripts/13_extract_static_assets.py",
            "source": "Relatório G2 nº 14 — Agosto/2026 (DOCX), comparado com nº 11, 12, 13",
            "raw_dir_gitignored": "assets/discovered/raw/ (.gitignore: /assets/discovered/raw/)",
            "personal_data": "contains_people_photos=true NÃO pode ir para assets/branding versionado sem decisão da Emmily",
            "width_height": "extent do DOCX (EMU/360000); para mídias internas do pptx, xfrm do slide/layout",
        },
        "assets": manifest,
    }, allow_unicode=True, sort_keys=False, width=140), encoding="utf-8")
    for m in manifest:
        print(m["asset_id"], m["sha1"][:12], m["width_cm"], m["height_cm"], m["stable_since"], m["identical_sha1_in"])


if __name__ == "__main__":
    main()
