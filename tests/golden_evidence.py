"""Apoio aos testes `-m golden` do Produto 2.4 (evidência local, somente leitura).

A evidência fica em `tmp/` do checkout principal (gitignored, download autorizado na Fase 3):
Lista Mestra v335.0/v134.0, DOCX nº 13/14 (só para comparar texto) e os extratos do agente B
(`tmp/agent_B/snapshots/v*.json`, linhas e agregados da planilha ambiental, sem dado pessoal).
Nada aqui escreve fora da memória. `PROG_G2_EVIDENCE_ROOT` sobrepõe o caminho.
"""

from __future__ import annotations

import io
import json
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path

import pytest

from prog_g2_report import REPO_ROOT

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Instante "Atualizado em" impresso no painel (WAVE1 §B; tmp/agent_B/b03_match_window.py)
ENV_SNAPSHOT = {13: ("v289.0", date(2026, 8, 12)), 14: ("v310.0", date(2026, 9, 7))}
# Valores lidos nos painéis dos PDFs pelo agente B (b03_match_window.PANELS):
# condicionantes = (Finalizada, No prazo, Pendente, Próximo do vencimento); licenças = (total, vigentes, pendentes)
PANELS = {
    13: {
        "cond": {"RD-101": (11, 35, 0, 0), "RD-102A": (12, 32, 0, 0), "RD-103": (11, 34, 0, 0), "RD-104": (10, 36, 0, 0)},
        "lic": (32, 24, 8), "lic_road": {"RD-103": 9, "RD-101": 8, "RD-102A": 8, "RD-104": 7},
    },
    14: {
        "cond": {"RD-101": (11, 1, 0, 34), "RD-102A": (14, 28, 0, 1), "RD-103": (14, 29, 0, 1), "RD-104": (10, 1, 0, 35)},
        "lic": (33, 25, 8), "lic_road": {"RD-103": 9, "RD-101": 8, "RD-102A": 8, "RD-104": 8},
    },
}


def evidence_root() -> Path | None:
    candidates = []
    if os.environ.get("PROG_G2_EVIDENCE_ROOT"):
        candidates.append(Path(os.environ["PROG_G2_EVIDENCE_ROOT"]))
    candidates.append(REPO_ROOT / "tmp")
    git = REPO_ROOT / ".git"
    if git.is_file():  # worktree: "gitdir: <principal>/.git/worktrees/<nome>"
        gitdir = Path(git.read_text(encoding="utf-8").split(":", 1)[1].strip())
        candidates.append(gitdir.parents[2] / "tmp")
    for candidate in candidates:
        if (candidate / "historical_sources").is_dir():
            return candidate
    return None


def require_golden(request) -> Path:
    """Golden só roda com `-m golden` explícito e com a evidência presente."""
    if "golden" not in (request.config.getoption("markexpr") or ""):
        pytest.skip("golden: rodar com -m golden")
    root = evidence_root()
    if root is None:
        pytest.skip("evidência local ausente (tmp/historical_sources)")
    return root


def snapshot(root: Path, version: str) -> dict:
    return json.loads((root / "agent_B" / "snapshots" / f"{version}.json").read_text(encoding="utf-8"))


def workbook_bytes_from_snapshot(snap: dict) -> bytes:
    """Remonta em memória as abas Licenças/Condicionantes/Empresas a partir do extrato do agente B.

    Layout da planilha real: título na linha 1, cabeçalho na linha 2 (Licenças B:P, Condicionantes
    A:L); Empresas com empresa em B e rodovia em G (e uma cópia com grafia 'RD 102a' em M).
    """
    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    dash = wb.create_sheet("Dashboard")
    dash.append(["Painel legado (não é fonte)"])

    lic = wb.create_sheet("Licenças")
    lic.append(["Acompanhamento de Licenças"])
    lic.append([None, *snap["licencas_header"]])
    for row in snap["licencas_rows"]:
        values = [None] + [row.get(h) for h in snap["licencas_header"]]
        lic.append([_cell_value(v) for v in values])

    cond = wb.create_sheet("Condicionantes")
    cond.append(["Condicionantes"])
    header = [h[:-2] if h.endswith("_2") else h for h in snap["cond_header"]]
    cond.append(header)
    for row in snap["cond_rows"]:
        cond.append([_cell_value(row.get(h)) for h in snap["cond_header"]])

    emp = wb.create_sheet("Empresas")
    emp.append(["Cadastro"])
    emp.append([])
    emp.append([None, "Razão social", None, None, None, None, "Obra", None, None, None, None, None, "Obra 2"])
    for company, road in snap["company_to_road"].items():
        emp.append([None, company, "x", None, None, None, road, None, None, None, None, None,
                    road.replace("-", " ")])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _cell_value(value):
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return date.fromisoformat(value)
    return value


# --------------------------------------------------------------------------- DOCX real
def docx_paragraphs(path: Path) -> list[dict]:
    """Parágrafos do corpo: texto, negrito por run, numId/ilvl (zip + XML, sem python-docx)."""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    out = []
    for p in root.find(W + "body").iter(W + "p"):
        ppr = p.find(W + "pPr")
        num_id = ilvl = None
        if ppr is not None and ppr.find(W + "numPr") is not None:
            num = ppr.find(W + "numPr")
            num_id = num.find(W + "numId").get(W + "val")
            ilvl = int(num.find(W + "ilvl").get(W + "val"))
        text = "".join(t.text or "" for t in p.iter(W + "t"))
        out.append({"text": text, "numId": num_id, "ilvl": ilvl})
    return out


_LETTER = re.compile(r"^[a-z]\) ")


def real_blocks(paragraphs: list[dict]) -> dict[str, list[str]]:
    """Texto real de cada bloco do 2.4, localizado pelo início fixo do bloco (como o agente O)."""
    texts = [p["text"] for p in paragraphs]
    start = max(i for i, t in enumerate(texts) if t.startswith("Durante o período de referência do presente relatório, deu-se"))
    end = next(i for i in range(start, len(texts)) if texts[i].startswith("A relação dos produtos desenvolvidos"))
    body = [p for p in paragraphs[start:end] if p["text"].strip()]

    def first(prefix: str) -> list[str]:
        return [p["text"].strip() for p in body if p["text"].startswith(prefix)][:1]

    def after(prefix: str, keep) -> list[str]:
        index = next((i for i, p in enumerate(body) if p["text"].startswith(prefix)), None)
        if index is None:
            return []
        out = []
        for p in body[index + 1 :]:
            if not keep(p):
                break
            out.append(p["text"].strip())
        return out

    return {
        "P2.4_RO_PERIODO": first("Os relatórios semanais contemplam"),
        "P2.4_RO_LIST": after("Dessa forma, o relatório mensal em questão", lambda p: p["numId"] is not None),
        "P2.4_RM": first("Foram emitidos, ainda, os Relatórios Mensais"),
        "P2.4_NC": first("As notificações de não conformidade"),
        "P2.4_ATAS": first("Encaminham-se"),
        "P2.4_BM_LEAD": first("Foram realizadas as medições"),
        "P2.4_BM_LIST": after("Foram realizadas as medições", lambda p: p["numId"] is not None),
        "P2.4_BM_EM_ELABORACAO": first("Paralelamente, permanecem em elaboração")
        + after("Paralelamente, permanecem em elaboração", lambda p: p["numId"] is not None),
        "P2.4_PARECERES_MEDICAO": first("Em complementação às medições"),
        "P2.4_PARECERES_MEDICAO_2": first("Os documentos contemplam a análise dos ensaios"),
        "P2.4_RI": first("Foram realizadas inspeções"),
        "P2.4_LIC_LEAD": first("Conforme pode ser observado na imagem a seguir"),
        "P2.4_LIC_LIST": after("Conforme pode ser observado na imagem a seguir", lambda p: p["text"].startswith("RD-")),
        "P2.4_LAU_LEAD": first("Conforme pode ser observado nas imagens a seguir"),
        "P2.4_LAU_LIST": [p["text"].strip() for p in body
                          if p["text"].startswith("RD-") and "condicionantes em atraso" in p["text"]],
        "P2.4_PARECERES_AMB": first("Adicionalmente, no mês de referência, foram emitidos pareceres")
        + first("Os pareceres emitidos tiveram"),
        "P2.4_RCA_HEAD": first("Referente aos Relatórios de Controle Ambiental"),
        "P2.4_RCA_LIST": after("Referente aos Relatórios de Controle Ambiental", lambda p: bool(_LETTER.match(p["text"]))),
        "P2.4_RA": first("Adicionalmente, foram emitidos os relatórios consolidados")
        + after("Adicionalmente, foram emitidos os relatórios consolidados", lambda p: p["text"].startswith("RD-")),
    }


def soft(text: str) -> str:
    """Comparação tolerante (agente O): meia-risca = hífen, espaços colapsados, sem ';'/'.' final."""
    text = " ".join((text or "").replace("–", "-").split())
    return re.sub(r"[;.]+$", "", text).strip()


_FACT = re.compile(
    r"\b[A-Z]{2,3}-\d{3}\.\d\b|\bRD-\d+A?\b|\b\d{2}/\d{2}/\d{4}\b|\b[A-ZÇ][a-zç]+/\d{4}\b"
    r"|\b(?:um|uma|dois|duas|três|quatro|cinco|seis|sete|oito|nove|dez)\b"
)


def facts_of(text: str) -> list[str]:
    """Fatos verificáveis de uma linha: códigos, rodovias, datas, meses e numerais, em ordem."""
    return _FACT.findall(text or "")


def report_docx(root: Path, number: int) -> Path:
    folder = root / "downloads" / "relatorios_11_14"
    return next(p for p in folder.glob("*.docx") if f"n°{number} " in p.name or f"n°{number}-" in p.name)
