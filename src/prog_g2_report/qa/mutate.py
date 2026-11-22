"""Mutações adversariais do golden test (QA-E, QA2-E, QA3-E) e varredura de palavras.

Ferramenta de QA, não do builder: aplica uma mutação conhecida a uma CÓPIA do PDF gerado (ou
aos fatos extraídos dele, recalculando os derivados com o próprio extrator) e compara com a
referência. Prova que o comparador pega a regressão: a mutação tem de criar diferença
bloqueante NOVA em relação ao controle (o gerado sem mutação).

As mutações são declarativas (dicts, `op` + parâmetros) para rodarem em processos paralelos:

    PDF   sub, subs, del_page, drop_image, blank_image, wipe_body, redact_image, swap_images,
          paint, redact_pc_row, toc_page, redact_line, signer, rewrite_lines, cover_text
    fatos f_sub, f_del_seg, f_dup_seg, f_swap_segs, f_swap_substr, f_merge_seg, pc_drop,
          pc_dup, pc_swap, pc_cell, word, chain

`word` é a varredura: troca UMA palavra do texto gerado (seção ou célula do Controle de
Produtos) por outra palavra plausível do próprio documento (`word_sweep_specs`, semente fixa).
`relocation_specs` (comparador 4.1, QA4-E) é a varredura de REALOCAÇÃO: para cada hunk
aprovado num bloco repetido (o mesmo grupo em outra rodovia, o mesmo item em outra lista), o
lado gerado vai para o bloco irmão (troca do parágrafo gerado com o do irmão) — tem de reprovar.

Nada é escrito fora do diretório temporário dado; os PDFs de entrada só são lidos. O nome do
signatário nunca entra num resumo (a mutação `signer` o lê do próprio PDF em tempo de execução).
"""

from __future__ import annotations

import copy
import io
import os
import random
import re
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from prog_g2_report.qa.extract import (
    ROAD_LEAD_RE,
    SIGNATORY_RE,
    extract_facts,
    finish_section,
    section_masks,
)

CRITICAL, MAJOR = "CRITICAL", "MAJOR"
DEFAULT_WORKERS = 3
WORDS = {42: "e dois)", 43: "e três)", 44: "e quatro)"}
_WORD_RE = re.compile(r"[^\W_]+")


def diff_key(diff) -> tuple:
    return (diff.check, diff.scope, diff.kind, str(diff.value), str(diff.reference),
            str(diff.generated))


def blocking_keys(report) -> set[tuple]:
    return {diff_key(d) for d in report.differences if d.severity in (CRITICAL, MAJOR)}


# --------------------------------------------------------------------------- PDF


def replace_text(doc, page_no: int | None, old: str, new: str, max_hits: int = 1) -> int:
    """Redige `old` (dentro de um span) e escreve `new` no mesmo lugar (QA-E)."""
    import pymupdf

    hits = 0
    pages = range(len(doc)) if page_no is None else [page_no - 1]
    for i in pages:
        page = doc[i]
        found = [s for b in page.get_text("dict")["blocks"] for ln in b.get("lines", [])
                 for s in ln["spans"] if old in s["text"]]
        for span in found:
            if hits >= max_hits:
                break
            rects = page.search_for(old, clip=pymupdf.Rect(span["bbox"]))
            if not rects:
                continue
            page.add_redact_annot(rects[0], text=new, fontsize=span["size"] * 0.95,
                                  fontname="helv", align=pymupdf.TEXT_ALIGN_LEFT)
            hits += 1
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        if hits >= max_hits:
            break
    return hits


class MutationTargetError(RuntimeError):
    """O texto/alvo da mutação não existe no gerado atual (a mutação não foi aplicada)."""


def _sub(doc, page, old, new, hits=1):
    n = replace_text(doc, page, old, new, hits)
    if n == 0:
        raise MutationTargetError(f"{old!r} (p. {page})")
    return n


def _pdf(doc, spec: dict) -> None:
    import pymupdf

    op = spec["op"]
    if op == "sub":
        _sub(doc, spec.get("page"), spec["old"], spec["new"], spec.get("hits", 1))
    elif op == "subs":
        for page, old, new, hits in spec["items"]:
            _sub(doc, page, old, new, hits)
    elif op == "del_page":
        doc.delete_page(spec["page"] - 1)
        if spec.get("fix"):
            total = len(doc)
            replace_text(doc, None, "43 (quarenta", f"{total} (quarenta")
            replace_text(doc, None, "e três)", WORDS[total])
    elif op == "drop_image":
        page = doc[spec["page"] - 1]
        page.delete_image(page.get_images(full=True)[0][0])
    elif op == "blank_image":
        page = doc[spec["page"] - 1]
        info = page.get_images(full=True)[0]
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, info[2], info[3]), False)
        pix.clear_with(255)
        page.replace_image(info[0], pixmap=pix)
    elif op == "wipe_body":
        page = doc[spec["page"] - 1]
        r = page.rect
        page.add_redact_annot(pymupdf.Rect(r.x0, r.y0 + 60, r.x1, r.y1 - 40))
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
    elif op == "redact_image":
        page = doc[spec["page"] - 1]
        big = [i for i in page.get_image_info() if (i["bbox"][2] - i["bbox"][0]) > 50]
        page.add_redact_annot(pymupdf.Rect(big[0]["bbox"]))
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                              text=pymupdf.PDF_REDACT_TEXT_NONE)
    elif op == "swap_images":
        a, b = doc[spec["a"] - 1], doc[spec["b"] - 1]
        xa, xb = a.get_images(full=True)[0][0], b.get_images(full=True)[0][0]
        pa, pb = pymupdf.Pixmap(doc, xa), pymupdf.Pixmap(doc, xb)
        a.replace_image(xa, pixmap=pb)
        b.replace_image(xb, pixmap=pa)
    elif op == "paint":
        _paint(doc, spec)
    elif op == "redact_pc_row":
        page = doc[spec["page"] - 1]
        r = page.search_for(spec["code"])
        if not r:
            raise MutationTargetError(spec["code"])
        band = pymupdf.Rect(page.rect.x0, r[0].y0 - 1, page.rect.x1, r[0].y1 + 1)
        page.add_redact_annot(band)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        if spec.get("fix_annex"):
            replace_text(doc, None, "149 (cento", f"{spec['fix_annex']} (cento")
            replace_text(doc, None, "e quarenta e nove)", "e quarenta e oito)")
    elif op == "toc_page":
        _toc_page(doc, spec["line"], spec["number"])
    elif op == "redact_line":
        page = doc[spec["page"] - 1]
        r = page.search_for(spec["needle"])
        if not r:
            raise MutationTargetError(spec["needle"])
        band = pymupdf.Rect(page.rect.x0 + 30, r[0].y0 - 0.5, page.rect.x1 - 30, r[0].y1 + 0.5)
        page.add_redact_annot(band)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    elif op == "signer":
        text = " ".join(p.get_text() for p in doc)
        match = SIGNATORY_RE.search(re.sub(r"\s+", " ", text))
        if not match:
            raise MutationTargetError("assinatura")
        _sub(doc, None, match.group("name").split()[-1], spec["new"], 1)
    elif op == "rewrite_lines":
        for item in spec["items"]:
            _rewrite_lines(doc, item)
    elif op == "cover_text":
        # QA4-E: retângulo da cor do fundo POR CIMA do texto (que continua extraível)
        page = doc[spec["page"] - 1]
        hits = page.search_for(spec["needle"])
        if len(hits) <= spec.get("nth", 0):
            raise MutationTargetError(f"{spec['needle']!r} (p. {spec['page']})")
        r = hits[spec.get("nth", 0)]
        if spec.get("part"):  # só um pedaço da linha (ex.: o "Não" de "Não aprovado")
            r = page.search_for(spec["part"], clip=pymupdf.Rect(r.x0 - 1, r.y0 - 1, r.x1 + 1,
                                                               r.y1 + 1))[0]
        if spec.get("band"):  # a linha inteira da tabela
            r = pymupdf.Rect(page.rect.x0 + 40, r.y0 - 3, page.rect.x1 - 30, r.y1 + 5)
        pad = spec.get("pad", 0.5)
        page.draw_rect(pymupdf.Rect(r.x0 - pad, r.y0 - pad, r.x1 + pad, r.y1 + pad),
                       color=None, fill=tuple(spec.get("fill", (1, 1, 1))), overlay=True)
    else:  # pragma: no cover - catálogo fechado
        raise ValueError(f"op desconhecida {op!r}")


def _rewrite_lines(doc, item: dict) -> None:
    """QA4-E: apaga, a partir de `needle` (n-ésima linha da página que o contém), essa linha e
    as `lines - 1` seguintes, e escreve `text` no lugar, numa linha só (o corpo diminui até
    caber na largura). O marcador de lista antes de `needle` fica."""
    import pymupdf

    page = doc[item["page"] - 1]
    rows = [(ln, "".join(s["text"] for s in ln["spans"]))
            for b in page.get_text("dict")["blocks"] for ln in b.get("lines", [])]
    hits = [k for k, (_, text) in enumerate(rows) if item["needle"] in text]
    nth = item.get("nth", 0)
    if len(hits) <= nth:
        raise MutationTargetError(f"{item['needle']!r} (p. {item['page']})")
    k = hits[nth]
    first = rows[k][0]
    found = page.search_for(item["needle"], clip=pymupdf.Rect(first["bbox"]))
    if not found:
        raise MutationTargetError(f"{item['needle']!r} (p. {item['page']})")
    x0 = found[0].x0
    span = next(s for s in first["spans"] if s["bbox"][2] > x0 + 1)
    baseline, size = span["origin"][1], item.get("fontsize") or span["size"]
    bands = [pymupdf.Rect(x0 - 0.5, first["bbox"][1], first["bbox"][2] + 1, first["bbox"][3])]
    for ln, _ in rows[k + 1:k + item.get("lines", 1)]:
        x0_, y0_, x1_, y1_ = ln["bbox"]
        bands.append(pymupdf.Rect(x0_ - 0.5, y0_, x1_ + 1, y1_))
    for band in bands:
        page.add_redact_annot(band)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    width = page.rect.x1 - 40 - x0
    size = min(size, size * width / max(1.0, pymupdf.get_text_length(item["text"], "helv",
                                                                       size)))
    page.insert_text((x0, baseline), item["text"], fontsize=size, fontname="helv",
                     color=tuple(item.get("color", (0, 0, 0))))


def _paint(doc, spec: dict) -> None:
    """Retângulo com a cor de fundo e um texto novo por cima, dentro do painel; `clean` =
    dígito centrado no mesmo corpo (troca limpa, QA3-E n16)."""
    import pymupdf
    from PIL import Image, ImageDraw, ImageFont

    page = doc[spec["page"] - 1]
    xref = page.get_images(full=True)[spec.get("image", 0)][0]
    pix = pymupdf.Pixmap(doc, xref)
    if pix.alpha or pix.n != 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    w, h = im.size
    f = spec["frac"]
    box = [int(f[0] * w), int(f[1] * h), int(f[2] * w), int(f[3] * h)]
    background = im.getpixel((box[0] + 1, box[1] + 1))
    draw = ImageDraw.Draw(im)
    draw.rectangle(box, fill=background)
    if spec.get("clean"):
        size = int((box[3] - box[1]) * 0.95)
        try:
            font = ImageFont.truetype("segoeuil.ttf", size)
        except OSError:
            font = ImageFont.load_default()
        tw = draw.textlength(spec["text"], font=font)
        draw.text(((box[0] + box[2] - tw) / 2, box[1] - size * 0.12), spec["text"],
                  fill=tuple(spec.get("fill", (255, 255, 255))), font=font)
    else:
        try:
            font = ImageFont.truetype("arial.ttf", max(10, int((box[3] - box[1]) * 0.7)))
        except OSError:
            font = ImageFont.load_default()
        draw.text((box[0] + 2, box[1] + 1), spec["text"], fill=(20, 20, 20), font=font)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    page.replace_image(xref, stream=buf.getvalue())


def _toc_page(doc, line_start: str, number: str) -> None:
    import pymupdf

    page = doc[1]
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(s["text"] for s in line["spans"])
            if not text.strip().startswith(line_start):
                continue
            last = [s for s in line["spans"] if s["text"].strip()][-1]
            current = last["text"].strip().split()[-1].lstrip(".")
            rects = page.search_for(current, clip=pymupdf.Rect(last["bbox"]))
            if not rects:
                raise MutationTargetError(f"nº de página do sumário {line_start!r}")
            page.add_redact_annot(rects[-1], text=number, fontsize=last["size"] * 0.95,
                                  fontname="helv")
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                                  graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
            return
    raise MutationTargetError(f"linha do sumário {line_start!r}")


# --------------------------------------------------------------------------- fatos


def _refinish(facts: dict, key: str) -> None:
    section = facts["sections"][key]
    finish_section(section, section_masks(key, section["title"]))


def _segments(facts: dict, key: str) -> list[dict]:
    return facts["sections"][key]["segments"]


def _seg_index(facts: dict, key: str, needle: str, start: int = 0) -> int:
    segs = _segments(facts, key)
    for i in range(start, len(segs)):
        if needle in segs[i]["text"]:
            return i
    raise MutationTargetError(f"{needle!r} em {key}")


def _facts(facts: dict, spec: dict) -> None:
    op = spec["op"]
    if op == "chain":
        for sub in spec["ops"]:
            _facts(facts, sub)
        return
    if op == "f_sub":
        key = spec["section"]
        hits = [i for i, s in enumerate(_segments(facts, key)) if spec["old"] in s["text"]]
        nth = spec.get("nth", 0)
        if len(hits) <= nth:
            raise MutationTargetError(f"{spec['old']!r} em {key}")
        seg = _segments(facts, key)[hits[nth]]
        seg["text"] = seg["text"].replace(spec["old"], spec["new"], 1)
        _refinish(facts, key)
    elif op == "f_del_seg":
        key = spec["section"]
        i = _seg_index(facts, key, spec["needle"])
        del _segments(facts, key)[i:i + spec.get("count", 1)]
        _refinish(facts, key)
    elif op == "f_dup_seg":
        key = spec["section"]
        i = _seg_index(facts, key, spec["needle"])
        _segments(facts, key).insert(i + 1, dict(_segments(facts, key)[i]))
        _refinish(facts, key)
    elif op == "f_swap_segs":
        key = spec["section"]
        segs = _segments(facts, key)
        i = _seg_index(facts, key, spec["a"])
        j = _seg_index(facts, key, spec["b"], i + 1)
        segs[i], segs[j] = segs[j], segs[i]
        _refinish(facts, key)
    elif op == "f_swap_substr":
        key = spec["section"]
        segs = _segments(facts, key)
        a, b = spec["a"], spec["b"]
        ia = _seg_index(facts, key, a)
        ib = next((i for i, s in enumerate(segs) if b in s["text"] and i != ia), None)
        if ib is None:
            raise MutationTargetError(f"{b!r} em {key}")
        segs[ia]["text"] = segs[ia]["text"].replace(a, "\0", 1)
        segs[ib]["text"] = segs[ib]["text"].replace(b, a, 1)
        segs[ia]["text"] = segs[ia]["text"].replace("\0", b, 1)
        _refinish(facts, key)
    elif op in ("pc_drop", "pc_dup", "pc_swap"):
        pc = facts["product_control"]
        rows, codes = pc["rows"][spec["block"]], pc["blocks"][spec["block"]]
        if op == "pc_drop":
            rows.pop(spec["index"])
            codes.pop(spec["index"])
        elif op == "pc_dup":
            rows.insert(spec["index"], copy.deepcopy(rows[spec["index"]]))
            codes.insert(spec["index"], codes[spec["index"]])
        else:
            i, j = spec["i"], spec["j"]
            rows[i], rows[j] = rows[j], rows[i]
            codes[i], codes[j] = codes[j], codes[i]
    elif op == "pc_cell":
        rows = [r for r in facts["product_control"]["rows"][spec["block"]]
                if r["code"] == spec["code"]]
        if len(rows) <= spec.get("nth", 0):
            raise MutationTargetError(f"{spec['code']} em {spec['block']}")
        rows[spec.get("nth", 0)]["cells"][spec["cell"]] = spec["new"]
    elif op == "word":
        _word(facts, spec)
    elif op == "f_merge_seg":
        # QA4-E: o parágrafo e o seguinte viram um só (quebra de parágrafo perdida): os
        # tokens não mudam, os blocos e os rótulos dos campos sim
        key = spec["section"]
        segs = _segments(facts, key)
        hits = [i for i, s in enumerate(segs) if spec["needle"] in s["text"]
                and spec.get("block") in (None, s.get("block"))]
        if not hits or hits[0] + 1 >= len(segs):
            raise MutationTargetError(f"{spec['needle']!r} em {key}")
        i = hits[0]
        segs[i]["text"] = f"{segs[i]['text']} {segs[i + 1]['text']}"
        del segs[i + 1]
        _refinish(facts, key)
    elif op == "f_relocate":
        key = spec["section"]
        segs = _segments(facts, key)
        a, b = segs[spec["a"]], segs[spec["b"]]
        a["text"], b["text"] = relocated_texts(a["text"], b["text"])
        _refinish(facts, key)
    else:  # pragma: no cover - catálogo fechado
        raise ValueError(f"op desconhecida {op!r}")


def relocated_texts(a: str, b: str) -> tuple[str, str]:
    """Troca o conteúdo de dois parágrafos de blocos irmãos. Se os dois abrem com a rodovia
    ("• RD-103: …", "A) RD-103:"), cada um mantém a sua e só o resto troca de lugar."""
    ma, mb = ROAD_LEAD_RE.match(a), ROAD_LEAD_RE.match(b)
    if ma and mb:
        return a[:ma.end()] + b[mb.end():], b[:mb.end()] + a[ma.end():]
    return b, a


def _block_road_group(label: str) -> tuple[str, str] | None:
    """'RD-103#1 > DISCIPLINAS DA FASE DE ESTUDOS' -> ('RD-103', 'DISCIPLINAS DA FASE DE
    ESTUDOS'); 'RD-104#2' -> ('RD-104', ''); fora de bloco -> None."""
    match = re.match(r"^(RD-\d{3}[A-Z]?)#\d+(?: > (.*))?$", label or "")
    return (match.group(1), match.group(2) or "") if match else None


def relocation_specs(reference_facts: dict, generated_facts: dict, hunks) -> dict:
    """Varredura de REALOCAÇÃO (comparador 4.1, QA4-E): para cada hunk aprovado que casa no
    controle, num parágrafo de bloco de rodovia, e para cada bloco IRMÃO (outra rodovia, mesmo
    grupo, mesma sequência de blocos da seção), uma mutação `f_relocate` que troca o parágrafo
    gerado do hunk com o parágrafo de mesmo índice no irmão (a rodovia de cada um fica).
    Troca que não muda nada (os dois parágrafos gerados iguais) é contada em `noop` e não vira
    mutação. Devolve {"specs", "noop", "no_sibling"}."""
    from prog_g2_report.qa.textdiff import diff_unit, text_units

    approved = {ah.key: ah for ah in hunks.hunks}
    ref_units, gen_units = text_units(reference_facts), text_units(generated_facts)
    specs: list[dict] = []
    noop: list[str] = []
    no_sibling: list[str] = []
    for scope, unit in gen_units.items():
        if not scope.startswith("section:"):
            continue
        key = scope.split(":", 1)[1]
        segments = _segments(generated_facts, key)
        # sequência de blocos: parágrafos seguidos com bloco de rodovia
        run, runs = 0, []
        for p, label in enumerate(unit.paragraph_block):
            # parágrafo fora de bloco, ou o 1º de uma sequência de blocos: nova sequência
            if _block_road_group(label) is None or (
                    p and _block_road_group(unit.paragraph_block[p - 1]) is None):
                run += 1
            runs.append(run)
        for h in diff_unit(ref_units.get(scope), unit, scope):
            ah = approved.get(h.key)
            gpar = h.generated_paragraph
            if ah is None or gpar < 0:
                continue
            here = _block_road_group(unit.paragraph_block[gpar])
            if here is None or unit.paragraph_source[gpar] < 0:
                no_sibling.append(ah.id)
                continue
            index = unit.paragraph_index[gpar]
            siblings = [p for p, label in enumerate(unit.paragraph_block)
                        if runs[p] == runs[gpar] and unit.paragraph_index[p] == index
                        and (rg := _block_road_group(label)) is not None
                        and rg[1] == here[1] and rg[0] != here[0]
                        and unit.paragraph_source[p] >= 0]
            if not siblings:
                no_sibling.append(ah.id)
            for p in siblings:
                a, b = unit.paragraph_source[gpar], unit.paragraph_source[p]
                ta, tb = segments[a]["text"], segments[b]["text"]
                road = _block_road_group(unit.paragraph_block[p])[0]
                name = f"reloc_{ah.id}_{here[0]}_to_{road}"
                if relocated_texts(ta, tb) == (ta, tb):
                    noop.append(name)
                    continue
                specs.append({"name": name, "op": "f_relocate", "section": key, "a": a,
                              "b": b, "hunk": ah.id, "expect": "text"})
    return {"specs": specs, "noop": noop, "no_sibling": sorted(set(no_sibling))}


def _word(facts: dict, spec: dict) -> None:
    def swap(text: str) -> str:
        start, end = spec["start"], spec["end"]
        if text[start:end] != spec["old"]:
            raise MutationTargetError(f"palavra {spec['old']!r} fora do lugar")
        return text[:start] + spec["new"] + text[end:]

    unit = spec["unit"]
    if unit.startswith("section:"):
        key = unit.split(":", 1)[1]
        seg = _segments(facts, key)[spec["segment"]]
        seg["text"] = swap(seg["text"])
        _refinish(facts, key)
    else:
        block = unit.split(":", 1)[1]
        pc = facts["product_control"]
        row = pc["rows"][block][spec["row"]]
        row["cells"][spec["cell"]] = swap(row["cells"][spec["cell"]])
        if spec["cell"] == 0:
            row["code"] = row["cells"][0]
            pc["blocks"][block][spec["row"]] = row["code"]


# --------------------------------------------------------------------------- varredura


def _shape(word: str) -> str:
    if word.isdigit():
        return "digits"
    if word.isupper() and len(word) > 1:
        return "upper"
    if word[:1].isupper():
        return "title"
    return "lower"


def word_sweep_specs(generated: dict, n: int = 200, seed: int = 20261002) -> list[dict]:
    """`n` mutações `word` com semente fixa: palavras do texto gerado (segmentos das seções,
    exceto CAPA/SUMARIO, e células do Controle de Produtos) trocadas por outra palavra
    plausível — do próprio documento, com o mesmo formato (dígitos, maiúsculas, inicial
    maiúscula, minúsculas) e tamanho parecido; número troca um dígito."""
    rng = random.Random(seed)
    sites: list[dict] = []
    vocab: dict[str, set[str]] = {}
    for key, section in generated["sections"].items():
        if key in ("CAPA", "SUMARIO"):
            continue
        for i, seg in enumerate(section.get("segments") or []):
            for m in _WORD_RE.finditer(seg["text"]):
                word = m.group(0)
                vocab.setdefault(_shape(word), set()).add(word)
                if len(word) >= 2 or word.isdigit():
                    sites.append({"unit": f"section:{key}", "segment": i,
                                  "start": m.start(), "end": m.end(), "old": word})
    for block, rows in (generated.get("product_control") or {}).get("rows", {}).items():
        for r, row in enumerate(rows):
            for c, cell in enumerate(row.get("cells") or []):
                for m in _WORD_RE.finditer(cell):
                    word = m.group(0)
                    vocab.setdefault(_shape(word), set()).add(word)
                    if len(word) >= 2 or word.isdigit():
                        sites.append({"unit": f"block:{block}", "row": r, "cell": c,
                                      "start": m.start(), "end": m.end(), "old": word})
    pools = {shape: sorted(words) for shape, words in vocab.items()}
    specs = []
    for site in rng.sample(sites, min(n, len(sites))):
        old = site["old"]
        if old.isdigit():
            pos = rng.randrange(len(old))
            digit = rng.choice([d for d in "0123456789" if d != old[pos]])
            new = old[:pos] + digit + old[pos + 1:]
        else:
            pool = [w for w in pools[_shape(old)] if w != old and abs(len(w) - len(old)) <= 2]
            pool = pool or [w for w in pools[_shape(old)] if w != old]
            new = rng.choice(pool)
        specs.append({"name": f"word_{len(specs) + 1:03d}", "op": "word", **site, "new": new,
                      "expect": "text"})
    return specs


# --------------------------------------------------------------------------- execução

_STATE: dict = {}


def _init(state: dict) -> None:
    from prog_g2_report.qa.compare import load_allowances

    _STATE.clear()
    _STATE.update(state)
    allowances = load_allowances(state["allowances_path"]) if state.get(
        "allowances_path") else load_allowances()
    _STATE["allowances"] = allowances
    _STATE["hunks"] = allowances.approved_hunks(state["report_number"])


def _summary(spec: dict, report, error: str | None = None) -> dict:
    private = spec.get("op") == "signer" or str(spec.get("unit", "")).endswith("ENCERRAMENTO")
    out = {"name": spec["name"], "expect": spec.get("expect", "text"), "error": error,
           "verdict": None, "new": []}
    if report is None:
        return out
    control = _STATE["control"]
    new = [d for d in report.differences if d.severity in (CRITICAL, MAJOR)
           and diff_key(d) not in control]
    out["verdict"] = report.verdict
    out["new"] = [{"check": d.check, "scope": d.scope, "kind": d.kind,
                   "severity": d.severity,
                   "message": "" if private else d.message[:200]} for d in new]
    out["warnings"] = len(report.warnings)
    return out


def run_one(spec: dict) -> dict:
    """Aplica uma mutação e compara (no processo atual, depois de `_init`)."""
    from prog_g2_report.qa.compare import compare

    try:
        if spec["op"] in _FACT_OPS:
            gen = copy.deepcopy(_STATE["generated_facts"])
            _facts(gen, spec)
        else:
            import pymupdf

            tmp = Path(_STATE["tmp_dir"]) / f"{spec['name']}_{os.getpid()}"
            tmp.mkdir(parents=True, exist_ok=True)
            work = tmp / "mutado.pdf"
            shutil.copy(_STATE["generated_pdf"], work)
            doc = pymupdf.open(work)
            try:
                _pdf(doc, spec)
                doc.save(tmp / "mutado_salvo.pdf", garbage=3)
            finally:
                doc.close()
            gen = extract_facts(tmp / "mutado_salvo.pdf")
            shutil.rmtree(tmp, ignore_errors=True)
            if spec.get("renumber"):
                # total coerente: numeração impressa refeita depois da página apagada
                for page in gen["pages"]:
                    if page["printed_page_number"] == page["index"] + 1:
                        page["printed_page_number"] = page["index"]
        report = compare(_STATE["reference_facts"], gen, _STATE["allowances"],
                         report_number=_STATE["report_number"],
                         approved_hunks=_STATE["hunks"])
    except MutationTargetError as exc:
        return _summary(spec, None, f"alvo ausente: {exc}")
    except (MemoryError, OSError, RuntimeError, ValueError) as exc:  # registra; não derruba o lote
        return _summary(spec, None, f"erro: {type(exc).__name__}: {exc}"[:300])
    return _summary(spec, report)


_FACT_OPS = frozenset({"f_sub", "f_del_seg", "f_dup_seg", "f_swap_segs", "f_swap_substr",
                       "f_merge_seg", "f_relocate", "pc_drop", "pc_dup", "pc_swap", "pc_cell",
                       "word", "chain"})


def run_mutations(specs: list[dict], *, reference_facts: dict, generated_facts: dict,
                  generated_pdf: Path | str, report_number: int, tmp_dir: Path | str,
                  control_keys: set[tuple], allowances_path: Path | str | None = None,
                  workers: int | None = None) -> dict[str, dict]:
    """Roda as mutações (em paralelo se `workers` > 1) e devolve o resumo por nome."""
    from prog_g2_report.security import assert_write_allowed

    assert_write_allowed(Path(tmp_dir))
    state = {"reference_facts": reference_facts, "generated_facts": generated_facts,
             "generated_pdf": str(generated_pdf), "report_number": report_number,
             "tmp_dir": str(tmp_dir), "control": set(control_keys),
             "allowances_path": str(allowances_path) if allowances_path else None}
    # Cada processo extrai um PDF inteiro (mapas de tinta a 300 dpi): memória, não CPU, limita.
    workers = workers or int(os.environ.get("PROG_QA_WORKERS", "0")) or max(
        1, min(len(specs), DEFAULT_WORKERS, (os.cpu_count() or 2) - 1))
    if workers == 1:
        _init(state)
        return {s["name"]: run_one(s) for s in specs}
    with ProcessPoolExecutor(max_workers=workers, initializer=_init,
                             initargs=(state,)) as pool:
        return {r["name"]: r for r in pool.map(run_one, specs, chunksize=1)}
