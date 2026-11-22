"""Validações do modelo sobre o DOCX gerado (`config/g2_report_model.yaml: validations`).

Rodam ao fim do build (`assemble.build_report`), sobre o documento montado e as fontes do
relatório; cada uma vira um `ComponentResult` com o `id` da validação:

    V_NUMBER_MONTH_CONSISTENT  número (e mês) do relatório iguais na capa, na Apresentação e no
                               Encerramento do DOCX. A capa só traz o número (componente COVER:
                               número + data de emissão); Apresentação e Encerramento trazem
                               número e mês. Divergência = erro.
    V_ALL_DOCS_IN_MASTER_LIST  todo código de documento citado no texto (forma `XX-NNN.N`, a dos
                               códigos da Lista Mestra) ∈ body_rows. Exceção declarada: códigos
                               de `inputs.p24_bm_in_progress` (BM externos, que por definição não
                               estão na Lista Mestra). Código fora = erro.
    V_NO_DELIVERY_AFTER_ISSUE  nenhuma `Data Entrega` de body_rows depois da data de emissão
                               (DEC-006 §5). `severity: warning`: aviso, não bloqueia.
    V_EMF_FRAME                cada EMF do Controle de Produtos com `rclFrame` e dispositivo de
                               referência dentro da tolerância do histórico
                               (`validations[V_EMF_FRAME].expected` / `tolerance_pct`; DEC-010:
                               xlScreen depende do DPI da sessão). `severity: warning`.

Severidade = `validations[].severity` do modelo (ausente = erro). Erro -> status FAILED (bloqueia
`BuildResult.ok`); aviso -> status OK com `facts.outcome = warning` e uma linha em `warnings`.
Sem o que conferir (ex.: nenhum EMF com office=False) -> SKIPPED; parte do texto ainda pendente
(marcador `[PENDENTE`) -> PENDING (o build já não está pronto por outro motivo).

`validation_summary` monta a lista `validations` do manifest.json com o resultado de TODAS as
validações do modelo (inclusive V_ANNEX_COUNT, V_PAGE_COUNT = CLOSING_PAGE_COUNT e
V_WEEK_START_25, que já existiam em outros pontos do build).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from docx.oxml.ns import qn

from prog_g2_report.builder.context import ComponentResult, ReportContext
from prog_g2_report.report_id import MONTH_NAMES, strip_accents

ERROR, WARNING = "error", "warning"
V_NUMBER_MONTH = "V_NUMBER_MONTH_CONSISTENT"
V_ALL_DOCS = "V_ALL_DOCS_IN_MASTER_LIST"
V_DELIVERY = "V_NO_DELIVERY_AFTER_ISSUE"
V_EMF_FRAME = "V_EMF_FRAME"
# Validações implementadas em outros pontos do build -> componente que traz o resultado.
RESULT_OF = {"V_PAGE_COUNT": "CLOSING_PAGE_COUNT", "V_ANNEX_COUNT": "V_ANNEX_COUNT"}
# Validação que vive nos avisos de um componente (render.p24_text, P2.4_RO_PERIODO).
WARNING_PREFIXED = ("V_WEEK_START_25",)

# Código de documento da Lista Mestra: prefixo (2–5 letras, ex. PA, RCA, LA.FA, Carta) + '-' +
# número de 3 dígitos + '.' + revisão (ex. 'PA-604.1', 'LA.RC-001.1'). Rodovias ('RD-101') não
# têm revisão e não casam.
DOC_CODE = re.compile(r"(?<![\w.-])([A-Za-z]{2,5}(?:\.[A-Za-z]{2})?-\d{3}\.\d+)(?![\w])")
REPORT_NUMBER = re.compile(r"Relat[óo]rio\s+Mensal\s+N\s*[°º.]?\s*(\d+)", re.IGNORECASE)
_MONTHS = {strip_accents(name).lower(): number for number, name in MONTH_NAMES.items()}
MONTH_LABEL = re.compile(r"\b([A-Za-zÀ-ÿ]+)\s*/\s*(\d{4})\b")
PENDING_MARK = "[PENDENTE"


# --------------------------------------------------------------------------- modelo
def model_validations(model: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(v.get("id")): v for v in model.get("validations") or [] if v.get("id")}


def severity(model: Mapping[str, Any], validation_id: str) -> str:
    """`validations[].severity` (warning) ou erro, quando ausente."""
    spec = model_validations(model).get(validation_id) or {}
    return WARNING if str(spec.get("severity") or "").lower() == WARNING else ERROR


def _result(model: Mapping[str, Any], validation_id: str, problems: Sequence[str],
            ok_detail: str, facts: dict[str, Any], warnings: list[str]) -> ComponentResult:
    level = severity(model, validation_id)
    facts = {"severity": level, **facts}
    if not problems:
        facts["outcome"] = "pass"
        return ComponentResult(validation_id, "OK", detail=ok_detail, facts=facts)
    detail = "; ".join(problems)
    if level == WARNING:
        facts["outcome"] = WARNING
        warnings.append(f"{validation_id}: {detail}")
        return ComponentResult(validation_id, "OK", detail=f"aviso: {detail}", facts=facts)
    facts["outcome"] = ERROR
    return ComponentResult(validation_id, "FAILED", detail=detail, facts=facts)


# --------------------------------------------------------------------------- documento
@dataclass
class DocText:
    """Parágrafos do corpo do DOCX (fora do sumário), com estilo, na ordem; `cover` = os que
    vêm antes do sumário (SDT)."""

    paragraphs: list[tuple[str, str]] = field(default_factory=list)    # (styleId, texto)
    cover: list[str] = field(default_factory=list)

    @property
    def texts(self) -> list[str]:
        return [t for _, t in self.paragraphs]


def _text(p: Any) -> str:
    return "".join(t.text or "" for t in p.iter(qn("w:t")))


def _style(p: Any) -> str:
    ppr = p.find(qn("w:pPr"))
    style = ppr.find(qn("w:pStyle")) if ppr is not None else None
    return str(style.get(qn("w:val"))) if style is not None else ""


def read_document(docx_path: Path) -> DocText:
    from docx import Document

    body = Document(str(docx_path)).element.body
    out = DocText()
    seen_toc = False
    for child in body.iterchildren():
        if child.tag == qn("w:sdt"):
            seen_toc = True                     # sumário (foundation.add_toc): fora da conferência
            continue
        if child.tag == qn("w:p"):
            items = [child]
        elif child.tag == qn("w:tbl"):
            items = list(child.iter(qn("w:p")))
        else:
            continue
        for p in items:
            text = _text(p)
            out.paragraphs.append((_style(p), text))
            if not seen_toc:
                out.cover.append(text)
    return out


def section_texts(doc: DocText, title: str, heading_styles: Iterable[str]) -> list[str] | None:
    """Parágrafos entre o título `title` (estilo de título) e o próximo título; None se o título
    não estiver no documento."""
    styles = set(heading_styles)
    wanted = title.strip().casefold()
    start = next((i for i, (s, t) in enumerate(doc.paragraphs)
                  if s in styles and t.strip().casefold() == wanted), None)
    if start is None:
        return None
    out: list[str] = []
    for style, text in doc.paragraphs[start + 1:]:
        if style in styles and text.strip():
            break
        out.append(text)
    return out


def number_and_month(texts: Sequence[str]) -> tuple[int | None, str | None, bool]:
    """(número, 'AAAA-MM', tem marcador pendente) do 1º 'Relatório Mensal N° …' dos textos; o
    mês é o 1º 'Mês/AAAA' do mesmo parágrafo depois do número."""
    pending = any(PENDING_MARK in t for t in texts)
    for text in texts:
        match = REPORT_NUMBER.search(text)
        if match is None:
            continue
        month = None
        for m in MONTH_LABEL.finditer(text, match.end()):
            number = _MONTHS.get(strip_accents(m.group(1)).lower())
            if number:
                month = f"{m.group(2)}-{number:02d}"
                break
        return int(match.group(1)), month, pending
    return None, None, pending


# --------------------------------------------------------------------------- validações
def validate_number_month(doc: DocText, report: ReportContext, model: Mapping[str, Any],
                          blocks: Mapping[str, Any], warnings: list[str]) -> ComponentResult:
    """V_NUMBER_MONTH_CONSISTENT. Seções pelos títulos do modelo (g2_content_blocks.yaml:
    APRES_TITLE, ENC_TITLE e o estilo de título deles)."""
    titles = {name: blocks[bid] for name, bid in (("Apresentação", "APRES_TITLE"),
                                                   ("Encerramento", "ENC_TITLE"))}
    heading_styles = {str(b.raw.get("style")) for b in blocks.values()
                      if str(b.raw.get("style") or "").startswith("Ttulo")}
    parts: dict[str, list[str] | None] = {"capa": doc.cover}
    for name, block in titles.items():
        parts[name] = section_texts(doc, str(block.raw.get("text") or ""), heading_styles)
    problems: list[str] = []
    found: dict[str, dict[str, Any]] = {}
    pending = False
    for name, texts in parts.items():
        if texts is None:
            problems.append(f"{name}: título ausente no documento")
            continue
        number, month, has_pending = number_and_month(texts)
        found[name] = {"report_number": number, "reference_month": month}
        if number is None:
            if has_pending:
                pending = True
                found[name]["pending"] = True
                continue
            problems.append(f"{name}: 'Relatório Mensal N°' não encontrado")
            continue
        if number != report.report_number:
            problems.append(f"{name}: N° {number} ≠ {report.report_number}")
        if name == "capa":
            continue                       # COVER: número + data de emissão (sem mês)
        if month is None:
            problems.append(f"{name}: mês de referência não encontrado")
        elif month != report.reference_month:
            problems.append(f"{name}: mês {month} ≠ {report.reference_month}")
    facts = {"found": found}
    if pending and not problems:
        return ComponentResult(V_NUMBER_MONTH, "PENDING",
                               detail="texto do Encerramento/Apresentação ainda pendente",
                               facts={"severity": severity(model, V_NUMBER_MONTH), **facts})
    return _result(model, V_NUMBER_MONTH, problems,
                   f"N° {report.report_number} e {report.reference_month} em capa, "
                   "Apresentação e Encerramento", facts, warnings)


def cited_codes(texts: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for text in texts:
        for match in DOC_CODE.finditer(text):
            seen.setdefault(match.group(1), None)
    return list(seen)


def validate_docs_in_master_list(doc: DocText, body_rows: Sequence[Any],
                                 external_codes: Iterable[str], model: Mapping[str, Any],
                                 warnings: list[str]) -> ComponentResult:
    """V_ALL_DOCS_IN_MASTER_LIST: códigos citados ⊆ body_rows ∪ BM externos declarados."""
    known = {str(r.document).strip() for r in body_rows if r.document}
    external = {str(c).strip() for c in external_codes}
    codes = cited_codes(doc.texts)
    outside = [c for c in codes if c not in known and c not in external]
    facts = {"cited": len(codes), "external_inputs": sorted(external & set(codes)),
             "outside": outside}
    problems = [f"citado(s) fora de body_rows: {', '.join(outside)}"] if outside else []
    return _result(model, V_ALL_DOCS, problems,
                   f"{len(codes)} código(s) citado(s), todos em body_rows", facts, warnings)


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def validate_delivery_dates(body_rows: Sequence[Any], issue_date: date,
                            model: Mapping[str, Any], warnings: list[str]) -> ComponentResult:
    """V_NO_DELIVERY_AFTER_ISSUE (DEC-006 §5): Data Entrega <= data de emissão."""
    late = [(r.document, d.isoformat()) for r in body_rows
            if (d := _as_date(getattr(r, "delivery_date", None))) is not None and d > issue_date]
    problems = [f"Data Entrega depois da emissão ({issue_date.isoformat()}): "
                + ", ".join(f"{doc} {d}" for doc, d in late)] if late else []
    return _result(model, V_DELIVERY, problems,
                   f"nenhuma Data Entrega depois de {issue_date.isoformat()}",
                   {"late": [list(x) for x in late]}, warnings)


def control_emfs(docx_path: Path, block_ids: Iterable[str]) -> list[tuple[str, bytes]]:
    """(nome, bytes) dos EMF do Controle de Produtos: imagens cujo `pic:cNvPr/@name` é
    '<bloco em minúsculas>_NN.emf' (render.product_control)."""
    from docx import Document

    names = "|".join(re.escape(b.lower()) for b in block_ids)
    if not names:
        return []
    pattern = re.compile(rf"^(?:{names})_\d+\.emf$")
    document = Document(str(docx_path))
    part = document.part
    out: list[tuple[str, bytes]] = []
    pic = "{http://schemas.openxmlformats.org/drawingml/2006/picture}"
    a = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    for pic_el in document.element.body.iter(f"{pic}pic"):
        c_nv = pic_el.find(f"{pic}nvPicPr/{pic}cNvPr")
        name = c_nv.get("name") if c_nv is not None else ""
        if not pattern.match(str(name)):
            continue
        blip = pic_el.find(f"{pic}blipFill/{a}blip")
        r_id = blip.get(qn("r:embed")) if blip is not None else None
        if r_id and r_id in part.related_parts:
            out.append((str(name), part.related_parts[r_id].blob))
    return out


def validate_emf_frame(docx_path: Path, block_ids: Iterable[str], model: Mapping[str, Any],
                       warnings: list[str]) -> ComponentResult:
    """V_EMF_FRAME: largura do `rclFrame` e dispositivo de referência de cada EMF do Controle
    de Produtos contra `validations[V_EMF_FRAME].expected` (± `tolerance_pct`)."""
    from prog_g2_report.render.docx_emf import emf_bounds

    spec = model_validations(model).get(V_EMF_FRAME) or {}
    expected = spec.get("expected") or {}
    width_mm = expected.get("frame_width_mm")
    device = tuple(expected.get("device_px") or ())
    tolerance = float(spec.get("tolerance_pct", 0.5))
    emfs = control_emfs(docx_path, block_ids)
    if not emfs:
        return ComponentResult(V_EMF_FRAME, "SKIPPED",
                               detail="nenhum EMF do Controle de Produtos no documento",
                               facts={"severity": severity(model, V_EMF_FRAME), "emfs": 0})
    if width_mm is None:
        raise KeyError("validations[V_EMF_FRAME].expected.frame_width_mm ausente no modelo")
    problems: list[str] = []
    widths: list[float] = []
    for name, data in emfs:
        header = emf_bounds(data)
        widths.append(round(header.frame_width_mm, 2))
        deviation = abs(header.frame_width_mm - float(width_mm)) / float(width_mm) * 100
        if deviation > tolerance:
            problems.append(f"{name}: frame {header.frame_width_mm:.2f} mm "
                            f"(esperado {float(width_mm):.2f} ± {tolerance}%)")
        if device and tuple(header.device_px) != device:
            problems.append(f"{name}: dispositivo {header.device_px[0]}×{header.device_px[1]} px "
                            f"(esperado {device[0]}×{device[1]})")
    facts = {"emfs": len(emfs), "frame_width_mm": sorted(set(widths)),
             "expected_frame_width_mm": width_mm, "tolerance_pct": tolerance}
    if problems:
        problems.append("confira tela 1920×1080 a 125 % (120 dpi) e gere de novo")
    return _result(model, V_EMF_FRAME, problems,
                   f"{len(emfs)} EMF com frame {float(width_mm):.2f} mm ± {tolerance}%",
                   facts, warnings)


def run_validations(docx_path: Path, report: ReportContext, body_rows: Sequence[Any],
                    external_codes: Iterable[str], model: Mapping[str, Any],
                    blocks: Mapping[str, Any], control_blocks: Iterable[str]
                    ) -> tuple[list[ComponentResult], list[str]]:
    """As quatro validações acima, na ordem do modelo; devolve (resultados, avisos)."""
    warnings: list[str] = []
    doc = read_document(docx_path)
    declared = model_validations(model)
    results: dict[str, ComponentResult] = {
        V_NUMBER_MONTH: validate_number_month(doc, report, model, blocks, warnings),
        V_ALL_DOCS: validate_docs_in_master_list(doc, body_rows, external_codes, model,
                                                 warnings),
        V_DELIVERY: validate_delivery_dates(body_rows, report.issue_date, model, warnings),
        V_EMF_FRAME: validate_emf_frame(docx_path, control_blocks, model, warnings),
    }
    ordered = [results[v] for v in declared if v in results]
    ordered += [r for k, r in results.items() if k not in declared]
    return ordered, warnings


def _outcome(result: ComponentResult | None) -> str:
    if result is None:
        return "not_run"
    if result.status == "FAILED":
        return ERROR
    if result.status.startswith("PENDING"):
        return "pending"
    if result.status == "SKIPPED":
        return "skipped"
    return str(result.facts.get("outcome") or "pass")


def validation_summary(model: Mapping[str, Any],
                       components: Sequence[ComponentResult]) -> list[dict[str, Any]]:
    """`validations` do manifest.json: uma linha por validação do modelo."""
    by_id = {c.component_id: c for c in components}
    out: list[dict[str, Any]] = []
    for vid, spec in model_validations(model).items():
        level = severity(model, vid)
        if vid in WARNING_PREFIXED:
            hits = [w for c in components for w in (c.facts.get("warnings") or ())
                    if str(w).startswith(vid)]
            out.append({"id": vid, "severity": level, "outcome": WARNING if hits else "pass",
                        "component": None, "detail": "; ".join(hits)})
            continue
        component = RESULT_OF.get(vid, vid)
        result = by_id.get(component)
        out.append({"id": vid, "severity": level, "outcome": _outcome(result),
                    "component": component if result is not None else None,
                    "detail": result.detail if result is not None else "",
                    "rule": spec.get("rule")})
    return out
