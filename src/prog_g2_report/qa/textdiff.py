"""Diff de texto ESTRITO do golden test (comparador 4.x): toda palavra divergente é diferença.

Três rodadas de QA adversarial (docs/qa/GATES.md, QA-E a QA3-E) mostraram que comparar "fatos
reconhecidos" por vocabulário sempre deixa lacunas. Aqui o texto inteiro de cada unidade é
comparado token a token, depois de uma normalização que só apaga o que é LEIAUTE:

    - espaços (inclusive os especiais) colapsados; NFC;
    - hifenização de fim de linha: "encontram- se" -> "encontram-se"; códigos e rodovias
      quebrados pelo Word ("NC- 525.1", "RD- 101") são juntados, como no extrator 3.1;
    - aspas tipográficas e travessões unificados ('"', "'", "-");
    - marcadores de lista (•, ▪, ◦, ‣, ●) unificados em "•";
    - pontilhado do sumário (4+ pontos) apagado;
    - caixa e acentos PRESERVADOS; pontuação é token.

Unidades de texto (uma por âncora; o nome é o escopo das verificações v3):

    section:<chave>   texto de cada seção (parágrafos do corpo e linhas de quadro, na ordem),
                      inclusive CAPA e SUMARIO (títulos e números de página do sumário); no
                      Encerramento o nome do signatário vira um token com o hash (o nome nunca
                      sai no relatório nem no conjunto de hunks)
    headings          rótulos dos títulos, na ordem do documento
    block:<bloco>     Controle de Produtos: rótulos das colunas e as seis células de cada
                      linha, na ordem (linha = "parágrafo" da âncora)

Cada trecho divergente (substituição, inserção ou remoção) é um HUNK: unidade, âncora do
parágrafo (sha256[:12] do parágrafo de REFERÊNCIA normalizado), 6 tokens de contexto antes e
depois (do lado da referência) e os textos exatos dos dois lados. O comparador marca cada hunk
como CRITICAL, salvo se ele estiver no conjunto CONGELADO de hunks aprovados
(docs/qa/approved_hunks/nNN.yaml), cada um com a anomalia catalogada ou a DEC que o justifica.

Comparador 4.1 (QA4-E): a âncora do hunk passa a ser também POSICIONAL. Hash e contexto não
bastam: o mesmo parágrafo padronizado se repete nas 4 rodovias ("Aprovação: Todas as
disciplinas encontram-se aprovadas;"), e a ressalva da DUP movida da RD-103 para a RD-102A
casava com a mesma aprovação. A posição tem quatro partes:

    block            bloco estrutural do parágrafo de REFERÊNCIA, como o extrator o rotula
                     (`segment.block`): rodovia > grupo no 2.2 ('RD-103#1 > DISCIPLINAS DA
                     FASE DE ESTUDOS'), rodovia nas listas do 2.4 ('RD-104#2'); no Controle de
                     Produtos, o código da linha; '' fora de bloco
    block_paragraph  índice do parágrafo dentro do bloco (o item da lista: 'I. BM-007.1' = 1)
    reference_span   intervalo de tokens na unidade de REFERÊNCIA (fixa: o PDF publicado)
    generated_block  bloco do parágrafo GERADO em que está o texto do hunk

Um hunk aprovado só cobre a diferença no mesmo lugar estrutural. O mesmo texto em outro bloco
é hunk novo (CRITICAL).

Este módulo só lê os fatos do extrator (`prog_g2_report.qa.extract`); não importa o builder.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from itertools import pairwise

from prog_g2_report.qa.extract import SIGNATORY_RE, fold

# Tokens de contexto guardados de cada lado do hunk.
CONTEXT_TOKENS = 6
# Dois trechos divergentes separados por menos de N tokens iguais formam um hunk só: o
# SequenceMatcher casa palavras soltas ("de", "o") no meio de uma frase reescrita, o que
# picaria a mesma mudança em vários hunks sem ganho de rigor (os tokens iguais do meio entram
# nos dois textos do hunk, exatos).
MERGE_GAP_TOKENS = 3
PARAGRAPH_SEPARATOR = "¶"
CELL_SEPARATOR = "|"
# Bloco das linhas de rótulos das colunas no Controle de Produtos.
LABELS_BLOCK = "⟨rótulos⟩"

_QUOTES = str.maketrans(dict.fromkeys("“”„‟″«»", '"') | dict.fromkeys("‘’‚‛′`´", "'"))
_DASHES = str.maketrans(dict.fromkeys("‐‑‒–—―−", "-"))
_BULLETS = str.maketrans(dict.fromkeys("▪◦‣●", "•"))
_SPACES = re.compile(r"[\s  -​  　]+")
# Hífen de fim de linha (o extrator junta as linhas com espaço): letra/dígito + "- " +
# letra/dígito. Travessão/hífen com espaço dos dois lados ("Grupo 2 - Gestão") não casa.
_LINE_HYPHEN = re.compile(r"(?<=[^\W_])- (?=[^\W_])")
_LEADER = re.compile(r"\.{4,}")
# Palavra (com hífen, ponto, vírgula, barra ou apóstrofo internos: "encontram-se", "NC-525.1",
# "01/08/2026", "1.234,56") ou qualquer outro caractere visível (pontuação, "_", símbolos):
# nenhum caractere que não seja espaço fica fora de algum token.
_TOKEN = re.compile(r"[^\W_]+(?:[-'./,][^\W_]+)*|\S")
TOC_LINE_RE = re.compile(r"^(?P<title>.*?\S)\s*\.{4,}\s*(?P<page>\d{1,4})$")
SIGNATORY_TOKEN = "⟨signatário:{}⟩"


def normalize_strict(text: str) -> str:
    """Normalização do diff estrito (ver docstring do módulo): só apaga leiaute."""
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("­", "")  # hífen discricionário
    text = text.translate(_QUOTES).translate(_DASHES).translate(_BULLETS)
    text = _SPACES.sub(" ", text)
    text = _LEADER.sub(" ", text)
    text = _LINE_HYPHEN.sub("-", text)
    return _SPACES.sub(" ", text).strip()


def tokens(text: str) -> list[str]:
    """Tokens do texto já normalizado por `normalize_strict` (caixa preservada)."""
    return _TOKEN.findall(normalize_strict(text))


def paragraph_anchor(text: str) -> str:
    """Âncora do parágrafo: sha256[:12] do texto de referência normalizado (tokens com um
    espaço)."""
    return hashlib.sha256(" ".join(tokens(text)).encode("utf-8")).hexdigest()[:12]


def mask_signatory(texts: list[str]) -> list[str]:
    """Textos do Encerramento com o nome do signatário (SIGNATORY_RE, procurado no texto
    inteiro) trocado por um token com o hash do nome, em todas as ocorrências. Se o nome
    estiver quebrado entre dois textos, devolve um texto só, já mascarado."""
    joined = " ".join(texts)
    match = SIGNATORY_RE.search(joined)
    if not match:
        return list(texts)
    name = match.group("name").strip()
    digest = hashlib.sha256(fold(name).encode("utf-8")).hexdigest()[:10]
    token = SIGNATORY_TOKEN.format(digest)
    if any(name in t for t in texts):
        return [t.replace(name, token) for t in texts]
    return [joined.replace(name, token)]


# --------------------------------------------------------------------------- unidades


@dataclass
class TextUnit:
    """Uma âncora de texto: parágrafos (texto bruto), o bloco estrutural de cada parágrafo e o
    índice dele no bloco, a origem (índice do segmento/linha nos fatos; -1 = desconhecida) e o
    fluxo de tokens com o parágrafo de cada token."""

    scope: str
    paragraphs: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    token_paragraph: list[int] = field(default_factory=list)
    paragraph_block: list[str] = field(default_factory=list)
    paragraph_index: list[int] = field(default_factory=list)
    paragraph_source: list[int] = field(default_factory=list)

    def add(self, text: str, block: str = "", source: int = -1) -> None:
        toks = tokens(text)
        if not toks:
            return
        n = len(self.paragraphs)
        same = bool(self.paragraph_block) and self.paragraph_block[-1] == block
        self.paragraphs.append(text)
        self.paragraph_block.append(block)
        self.paragraph_index.append(self.paragraph_index[-1] + 1 if same else 0)
        self.paragraph_source.append(source)
        self.tokens += toks
        self.token_paragraph += [n] * len(toks)

    def paragraph_at(self, start: int, end: int) -> int:
        """Parágrafo do trecho [start, end) de tokens. Trecho vazio (inserção ou remoção do
        outro lado) = o parágrafo do token anterior, ou o primeiro."""
        if end > start:
            return self.token_paragraph[start]
        if start > 0:
            return self.token_paragraph[start - 1]
        return self.token_paragraph[0] if self.token_paragraph else -1

    def block_of(self, paragraph: int) -> str:
        return self.paragraph_block[paragraph] if paragraph >= 0 else ""


def text_units(facts: dict) -> dict[str, TextUnit]:
    """Unidades de texto de um PDF extraído, na ordem do documento (ver docstring)."""
    units: dict[str, TextUnit] = {}
    for key, section in facts.get("sections", {}).items():
        unit = TextUnit(f"section:{key}")
        segments = section.get("segments")
        if segments is None:  # fatos de extrator < 3.0: só o texto da seção
            segments = [{"text": section.get("text", "")}]
        texts = [s.get("text", "") for s in segments]
        blocks = [s.get("block") or "" for s in segments]
        sources = list(range(len(segments)))
        if key.split("#")[0] == "ENCERRAMENTO":
            masked = mask_signatory(texts)
            if len(masked) != len(texts):  # nome quebrado entre segmentos: um texto só
                blocks, sources = [""], [-1]
            texts = masked
        for text, block, source in zip(texts, blocks, sources, strict=True):
            unit.add(text, block, source)
        units[unit.scope] = unit
    headings = TextUnit("headings")
    for n, h in enumerate(facts.get("headings", [])):
        headings.add(f"{h['label']} {PARAGRAPH_SEPARATOR}", "", n)
    units[headings.scope] = headings
    pc = facts.get("product_control") or {}
    for block in pc.get("block_order") or list(pc.get("rows", {})):
        unit = TextUnit(f"block:{block}")
        variants = list(dict.fromkeys(tuple(c.get("labels") or ()) for c in pc.get("crops", [])
                                      if c.get("block") == block))
        for labels in variants:
            unit.add(f" {CELL_SEPARATOR} ".join(labels) + f" {PARAGRAPH_SEPARATOR}",
                     LABELS_BLOCK)
        for n, row in enumerate(pc.get("rows", {}).get(block, [])):
            cells = row.get("cells") or [row.get("code", "")]
            unit.add(f" {CELL_SEPARATOR} ".join(cells) + f" {PARAGRAPH_SEPARATOR}",
                     str(row.get("code") or (cells[0] if cells else "")), n)
        units[unit.scope] = unit
    return units


# --------------------------------------------------------------------------- hunks


@dataclass(frozen=True)
class Hunk:
    unit: str
    kind: str  # replace | insert | delete
    anchor: str
    paragraph: int
    context_before: tuple[str, ...]
    context_after: tuple[str, ...]
    reference_text: str
    generated_text: str
    reference_span: tuple[int, int]
    generated_span: tuple[int, int]
    # v4.1: posição estrutural (ver docstring do módulo)
    block: str = ""
    block_paragraph: int = 0
    generated_block: str = ""
    generated_paragraph: int = -1

    @property
    def key(self) -> tuple:
        """Identidade EXATA e POSICIONAL do hunk: o que um hunk aprovado tem de repetir."""
        return (self.unit, self.anchor, self.block, self.block_paragraph,
                tuple(self.reference_span), self.generated_block, self.context_before,
                self.context_after, self.reference_text, self.generated_text)

    @property
    def position(self) -> dict:
        return {"block": self.block, "paragraph": self.block_paragraph,
                "tokens": list(self.reference_span), "generated_block": self.generated_block}

    def describe(self) -> str:
        ref = self.reference_text or "∅"
        gen = self.generated_text or "∅"
        before = " ".join(self.context_before[-3:])
        after = " ".join(self.context_after[:3])
        where = f" {self.block}" if self.block else ""
        return f"[{self.anchor}{where}] …{before} «{ref}» → «{gen}» {after}…"


def _merged_opcodes(ref: list[str], gen: list[str]) -> list[tuple[int, int, int, int]]:
    matcher = SequenceMatcher(None, ref, gen, autojunk=False)
    spans: list[list[int]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if spans and i1 - spans[-1][1] < MERGE_GAP_TOKENS and j1 - spans[-1][3] < MERGE_GAP_TOKENS:
            spans[-1][1], spans[-1][3] = i2, j2
        else:
            spans.append([i1, i2, j1, j2])
    return [tuple(s) for s in spans]


def diff_unit(ref: TextUnit | None, gen: TextUnit | None, scope: str) -> list[Hunk]:
    """Hunks de uma unidade. Unidade só de um lado = um hunk com o texto inteiro."""
    ref = ref if ref is not None else TextUnit(scope)
    gen = gen if gen is not None else TextUnit(scope)
    rt, gt = ref.tokens, gen.tokens
    if rt == gt:
        return []
    hunks = []
    for i1, i2, j1, j2 in _merged_opcodes(rt, gt):
        par = ref.paragraph_at(i1, i2)
        gpar = gen.paragraph_at(j1, j2)
        anchor = paragraph_anchor(ref.paragraphs[par]) if par >= 0 else ""
        kind = "replace" if i2 > i1 and j2 > j1 else ("delete" if i2 > i1 else "insert")
        hunks.append(Hunk(
            unit=scope, kind=kind, anchor=anchor, paragraph=par,
            context_before=tuple(rt[max(0, i1 - CONTEXT_TOKENS):i1]),
            context_after=tuple(rt[i2:i2 + CONTEXT_TOKENS]),
            reference_text=" ".join(rt[i1:i2]), generated_text=" ".join(gt[j1:j2]),
            reference_span=(i1, i2), generated_span=(j1, j2),
            block=ref.block_of(par),
            block_paragraph=ref.paragraph_index[par] if par >= 0 else 0,
            generated_block=gen.block_of(gpar), generated_paragraph=gpar))
    return hunks


def diff_facts(reference: dict, generated: dict) -> dict[str, list[Hunk]]:
    """Hunks por unidade (todas as unidades dos dois lados, na ordem do documento)."""
    ref_units, gen_units = text_units(reference), text_units(generated)
    scopes = list(dict.fromkeys(list(ref_units) + list(gen_units)))
    return {s: diff_unit(ref_units.get(s), gen_units.get(s), s) for s in scopes}


def paragraph_groups(ref: TextUnit | None, gen: TextUnit | None,
                     hunks: list[Hunk]) -> list[tuple[set[int], set[int], list[Hunk]]]:
    """Grupos de parágrafos correspondentes (referência, gerado) tocados por `hunks`.

    O grupo é o fecho transitivo de duas ligações: o alinhamento token a token (um token igual
    liga o parágrafo de referência ao gerado) e os próprios hunks (todos os parágrafos dos dois
    trechos; trecho vazio liga os parágrafos vizinhos). Assim cada grupo é fechado: o que muda
    nos fatos entre os dois lados de um grupo é efeito exato dos hunks dele
    (`compare._cover_by_hunks`)."""
    ref = ref if ref is not None else TextUnit("")
    gen = gen if gen is not None else TextUnit("")
    parent: dict[tuple[str, int], tuple[str, int]] = {}

    def find(x: tuple[str, int]) -> tuple[str, int]:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: tuple[str, int], b: tuple[str, int]) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    matcher = SequenceMatcher(None, ref.tokens, gen.tokens, autojunk=False)
    for a, b, size in matcher.get_matching_blocks():
        for k in range(size):
            union(("r", ref.token_paragraph[a + k]), ("g", gen.token_paragraph[b + k]))

    def side(unit: TextUnit, tag: str, start: int, end: int) -> list[tuple[str, int]]:
        if end > start:
            return [(tag, p) for p in dict.fromkeys(unit.token_paragraph[start:end])]
        return [(tag, unit.token_paragraph[k]) for k in (start - 1, start)
                if 0 <= k < len(unit.tokens)]

    touched: dict[tuple[str, int], list[Hunk]] = {}
    for h in hunks:
        nodes = side(ref, "r", *h.reference_span) + side(gen, "g", *h.generated_span)
        for node in nodes:
            find(node)
        for a, b in pairwise(nodes):
            union(a, b)
        if nodes:
            touched.setdefault(nodes[0], []).append(h)
    groups: dict[tuple[str, int], tuple[set[int], set[int], list[Hunk]]] = {}
    for node, hs in touched.items():
        groups.setdefault(find(node), (set(), set(), []))[2].extend(hs)
    for node in list(parent):
        root = find(node)
        if root in groups:
            groups[root][0 if node[0] == "r" else 1].add(node[1])
    return list(groups.values())


# --------------------------------------------------------------------------- sumário


def toc_entries(facts: dict) -> list[tuple[str, int]]:
    """Linhas do sumário: (título normalizado, página). Lê os segmentos da seção SUMARIO; um
    título quebrado em duas linhas é juntado até achar o número de página."""
    section = (facts.get("sections") or {}).get("SUMARIO") or {}
    out: list[tuple[str, int]] = []
    pending = ""
    for segment in section.get("segments") or []:
        text = f"{pending} {segment.get('text', '')}".strip()
        match = TOC_LINE_RE.match(text)
        if match:
            out.append((normalize_strict(match.group("title")), int(match.group("page"))))
            pending = ""
        else:
            pending = text
    return out
