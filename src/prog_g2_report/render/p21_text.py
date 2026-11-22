"""Produto 2.1 — resumo executivo (S0–S8), chamada da tabela e agenda de reuniões, em texto puro.

Funções PURAS: não tocam em python-docx, rede, SharePoint nem API de IA. Cada renderer recebe
as linhas do relatório e devolve um `BlockText` (parágrafos com segmentos negrito/normal + fatos);
o builder de DOCX só transcreve os segmentos.

Contrato de entrada (igual para todos os renderers de `P21_RENDERERS`):

    renderer(rows, inputs, rules) -> BlockText

    rows    `MasterListRow` do relatório inteiro, na ordem física
            (`sources.master_list.select(load(lista), report_number)` — `config/data_rules/
            p21_executive_summary.yaml: selection`)
    inputs  entradas humanas do modelo (`config/g2_report_model.yaml: inputs`):
            `ai_review` (texto aprovado dos slots AI_SYNTHESIS) e `meetings_agenda`
    rules   `load_rules()`: o YAML `p21_executive_summary.yaml` + os blocos P2.1_* de
            `config/g2_content_blocks.yaml`

Chave do modelo que define cada regra (todas em `p21_executive_summary.yaml` salvo indicação):

    S0 P2.1_SUMMARY_S0_ESCOPO        paragraphs.products_overview; render_maps.product_label
    S1 P2.1_SUMMARY_S1_P21           paragraphs.p21_coordination; config.rodovias_gerenciadas;
                                     render_maps.atas_clause (cláusula ⇔ existe AT no 2.1);
                                     render_maps.p21_meeting_topics (tratativas só com AT do
                                     2.1 que as cite na Descrição, como o S7);
                                     presença = g2_content_blocks P2.1_SUMMARY_S1_P21.presence
                                     (Produto 2.1 com linhas no relatório)
    S2 P2.1_SUMMARY_S2_PADRONIZACAO  paragraphs.p21_standardization; render_maps.standardization
                                     (slot AI_SYNTHESIS via `ai_slot`)
    S3 P2.1_SUMMARY_S3_P22           paragraphs.p22_overview; render_maps.p22_types/p22_verb/
                                     p22_disciplines/highway_exclude
    S4 P2.1_SUMMARY_S4_TEMAS         paragraphs.p22_pareceres_themes; render_maps.
                                     p22_pa_themes_draft (slot AI_SYNTHESIS via `ai_slot`)
    S5 P2.1_SUMMARY_S5_P24           paragraphs.p24_overview; render_maps.p24_types (gender/
                                     number do 1º tipo -> render_maps.p24_article);
                                     render_maps.p24_activities (frase 'Paralelamente…': só
                                     atividade com documento do 2.4 no relatório, como o S7)
    S1/S3/S5 rodovias                render_maps.highway_forms (1 rodovia: forma singular; o
                                     mesmo one/many de measurements.highways_clause no S6)
    S6 P2.1_SUMMARY_S6_MEDICOES      paragraphs.p24_measurements; render_maps.measurements
                                     (highways_clause: one_highway | many_highways)
    S7 P2.1_SUMMARY_S7_PARECERES_P24 paragraphs.p24_pareceres_themes; render_maps.p24_pa_themes;
                                     modo = g2_report_model editorial_defaults.p21_s7_mode
                                     (keyword_map: só tema com PA do 2.4 que o sustente)
    S8 P2.1_SUMMARY_S8_FECHO         paragraphs.closing; paragraphs.closing.slots.
                                     closing_themes (só a atuação com documento do relatório,
                                     como S5/S7; required/when_unsupported como no 2.4)
       P2.1_TABLE_CALL               paragraphs.table_call (se o 2.1 tem linhas)
       P2.1_MEETINGS_LIST            g2_content_blocks P2.1_MEETINGS_LIST.template;
                                     config.meetings (ordem); render_maps.meetings

Anomalias históricas que NÃO se reproduzem (seção K, `data/catalog/anomalies.jsonl`):
"Ofício" sem OF no 2.4 (P2.1_RESUMO_OFICIO_SEM_DOCUMENTO), fragmento "Na RD-101."
(P2.4_FRASE_TRUNCADA_MEDICOES), rodovias de BM copiadas de junho (P2.1_RESUMO_BM_RODOVIAS),
plural com uma rodovia só (P2.1_RESUMO_BM_CONCORDANCIA), temas do S7 sem PA
(P2.1_S7_TEMAS_SEM_SUPORTE), disciplinas do 2.2 copiadas (P2.1_RESUMO_DISCIPLINAS_P22), S0 sem
ponto final (P2.1_RESUMO_PONTO_FINAL), "RD-102:" sem A (P2.1_IDENTIFICACAO_RODOVIA). Nada aqui
lê o relatório anterior: todo valor vem das linhas do relatório, do modelo ou de `inputs`.

Slots AI_SYNTHESIS (`ai_slot`). Ordem de precedência:
    1. `inputs['ai_review'][slot_id]` aprovado pela revisão humana -> status OK;
    2. senão um RASCUNHO do `SynthesisProvider` (padrão: `KeywordDraftProvider`, determinístico,
       sobre a Descrição da Lista Mestra) -> status PENDING_HUMAN + `ReviewBrief` (pauta).
Um provedor de IA pode ser plugado depois implementando `SynthesisProvider.draft` e passando
`provider=` a `ai_slot` (ou a `render_block`/renderers via `rules['_provider']`): a saída continua
rascunho até a revisão humana gravar `ai_review`. Este módulo nunca chama API.

Formato de `inputs['ai_review'][slot_id]`: string, ou mapping `{text, documents?, approved_by?}`.
`text` aceita `**negrito**` (convenção `bold_markup` de g2_content_blocks). Se `documents` vier,
precisa ser o mesmo conjunto de códigos do slot no relatório; senão a aprovação é tratada como
de outro mês (anti copy-forward) e o slot volta a PENDING_HUMAN.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Any, Protocol

import yaml

from prog_g2_report import REPO_ROOT
from prog_g2_report.builder.context import ComponentResult
from prog_g2_report.sources.master_list import MasterListRow

RULES_PATH = REPO_ROOT / "config" / "data_rules" / "p21_executive_summary.yaml"
CONTENT_BLOCKS_PATH = REPO_ROOT / "config" / "g2_content_blocks.yaml"
MODEL_PATH = REPO_ROOT / "config" / "g2_report_model.yaml"

OK = "OK"
SKIPPED = "SKIPPED"
PENDING = "PENDING_HUMAN"

S0 = "P2.1_SUMMARY_S0_ESCOPO"
S1 = "P2.1_SUMMARY_S1_P21"
S2 = "P2.1_SUMMARY_S2_PADRONIZACAO"
S3 = "P2.1_SUMMARY_S3_P22"
S4 = "P2.1_SUMMARY_S4_TEMAS"
S5 = "P2.1_SUMMARY_S5_P24"
S6 = "P2.1_SUMMARY_S6_MEDICOES"
S7 = "P2.1_SUMMARY_S7_PARECERES_P24"
S8 = "P2.1_SUMMARY_S8_FECHO"
TABLE_CALL = "P2.1_TABLE_CALL"
MEETINGS = "P2.1_MEETINGS_LIST"

# Ordem do documento (g2_content_blocks seq 30–39); a agenda de reuniões vem antes (seq 22).
SUMMARY_ORDER = (S0, S1, S2, S3, S4, S5, S6, S7, S8, TABLE_CALL)


# ---------------------------------------------------------------------------------------------
# Texto com formatação: o contrato com o builder de DOCX
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Segment:
    """Um run de texto. Só negrito varia no resumo executivo (fmt_12..14, agente J)."""

    text: str
    bold: bool = False


@dataclass(frozen=True)
class Paragraph:
    """Um parágrafo. `style` é o styleId OOXML; `list_style` marca item de lista."""

    segments: tuple[Segment, ...]
    style: str = "Normal"
    list_style: str | None = None      # "bullet" = PargrafodaLista numId 35 lvl 0 (reuniões)

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.segments)


@dataclass(frozen=True)
class ReviewBrief:
    """Pauta de revisão humana de um slot AI_SYNTHESIS (vira arquivo com `write_review_brief`)."""

    slot_id: str
    question: str
    documents: tuple[dict[str, Any], ...]
    draft: str
    provider: str
    notes: tuple[str, ...] = ()

    def to_markdown(self) -> str:
        lines = [
            f"# Revisão do slot {self.slot_id}",
            "",
            f"**Pergunta:** {self.question}",
            "",
            f"**Rascunho ({self.provider}):** {self.draft or '(vazio)'}",
            "",
            "| Documento | Produto | Empreendimento | Descrição |",
            "|---|---|---|---|",
        ]
        for doc in self.documents:
            cells = (doc["document"], doc["product"], doc["venture"], doc["description"])
            lines.append("| " + " | ".join(str(c) for c in cells) + " |")
        lines += [""] + [f"- {note}" for note in self.notes]
        lines += [
            "",
            "Resposta: gravar em `inputs.ai_review` a chave "
            f"`{self.slot_id}` com `{{text: ..., documents: [...]}}` (aceita `**negrito**`).",
            "",
        ]
        return "\n".join(lines)


@dataclass
class BlockText:
    """O que um renderer devolve. Compatível com `ComponentResult` via `to_component_result`."""

    block_id: str
    paragraphs: list[Paragraph] = field(default_factory=list)
    status: str = OK                   # OK | SKIPPED | PENDING_HUMAN
    detail: str = ""
    facts: dict[str, Any] = field(default_factory=dict)
    rule_keys: tuple[str, ...] = ()    # chaves do modelo que definem a regra
    review_brief: ReviewBrief | None = None

    @property
    def text(self) -> str:
        return "\n".join(p.text for p in self.paragraphs)

    def to_component_result(self, component_id: str | None = None) -> ComponentResult:
        facts = {**self.facts, "block_id": self.block_id, "text": self.text}
        return ComponentResult(component_id or self.block_id, self.status, self.detail, facts)


Renderer = Callable[[Sequence[MasterListRow], Mapping[str, Any], Mapping[str, Any]], BlockText]


# ---------------------------------------------------------------------------------------------
# Regras
# ---------------------------------------------------------------------------------------------
@lru_cache(maxsize=4)
def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_rules(
    path: Path = RULES_PATH,
    content_blocks_path: Path = CONTENT_BLOCKS_PATH,
    model_path: Path = MODEL_PATH,
) -> dict[str, Any]:
    """`p21_executive_summary.yaml` + `content_blocks` = {block_id: bloco} dos blocos P2.1_* +
    `editorial_defaults` do modelo (`p21_s7_mode`: default único do S7)."""
    rules = dict(_load_yaml(path))
    rules["editorial_defaults"] = _load_yaml(model_path).get("editorial_defaults") or {}
    blocks = _load_yaml(content_blocks_path).get("blocks", [])
    rules["content_blocks"] = {
        b["block_id"]: b for b in blocks if str(b.get("block_id", "")).startswith("P2.1_")
    }
    return rules


def _maps(rules: Mapping[str, Any]) -> Mapping[str, Any]:
    return rules["render_maps"]


def _paragraph_rule(rules: Mapping[str, Any], pid: str) -> Mapping[str, Any]:
    for para in rules["paragraphs"]:
        if para["id"] == pid:
            return para
    raise KeyError(f"paragraphs.{pid} ausente em p21_executive_summary.yaml")


# ---------------------------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------------------------
_PREFIX = re.compile(r"[A-Z]+")
_SLOT = re.compile(r"\{(\w+)\}")
_CODE_NUM = re.compile(r"^[A-Z]+-(\d+)")


def fold(text: Any) -> str:
    """Minúsculas, sem acento, travessões como hífen, espaços colapsados (para regex de mapa)."""
    norm = unicodedata.normalize("NFD", str(text or ""))
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    norm = norm.replace("–", "-").replace("—", "-").replace("\xa0", " ")
    return " ".join(norm.lower().split())


def doc_prefix(row: MasterListRow) -> str:
    """Prefixo do campo Documento (`type_key`): 'PA-680.1' -> 'PA'. Nunca a Manifestação."""
    match = _PREFIX.match(row.document.strip().upper())
    return match.group(0) if match else ""


def highway(value: Any) -> str:
    """'RD-102 A' / NBSP -> 'RD-102A' (mesma normalização de p22_highway_block)."""
    return "".join(str(value or "").replace("\xa0", " ").split())


def enumerate_pt(items: Sequence[str], serial_comma: bool = False) -> str:
    """'A', 'A e B', 'A, B e C' (ou 'A, B, e C' quando os itens já têm vírgula)."""
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    last_sep = ", e " if serial_comma else " e "
    return ", ".join(items[:-1]) + last_sep + items[-1]


def _enumerate_segments(
    items: Sequence[Sequence[Segment]], serial_comma: bool = False
) -> list[Segment]:
    out: list[Segment] = []
    for index, item in enumerate(items):
        if index:
            last = index == len(items) - 1
            out.append(Segment((", e " if serial_comma else " e ") if last else ", "))
        out.extend(item)
    return out


def parse_bold_markup(text: str) -> list[Segment]:
    """'a **CT-501.1**, ...' -> segmentos (convenção bold_markup de g2_content_blocks)."""
    parts = text.split("**")
    return [Segment(part, bold=bool(i % 2)) for i, part in enumerate(parts) if part]


def segments_to_markup(segments: Iterable[Segment]) -> str:
    return "".join(f"**{s.text}**" if s.bold else s.text for s in segments)


def _literal(text: str, bold_literals: Sequence[str]) -> list[Segment]:
    if not text:
        return []
    for lit in bold_literals:
        pos = text.find(lit)
        if pos >= 0:
            return [
                *_literal(text[:pos], bold_literals),
                Segment(lit, True),
                *_literal(text[pos + len(lit) :], bold_literals),
            ]
    return [Segment(text)]


def _merge(segments: Iterable[Segment]) -> tuple[Segment, ...]:
    """Funde runs vizinhos de mesma formatação e colapsa espaços duplos entre eles."""
    out: list[Segment] = []
    for seg in segments:
        text = re.sub(r" {2,}", " ", seg.text)
        if not text:
            continue
        if out and out[-1].text.endswith(" ") and text.startswith(" "):
            text = text[1:]
            if not text:
                continue
        if out and out[-1].bold == seg.bold:
            out[-1] = Segment(out[-1].text + text, seg.bold)
        else:
            out.append(Segment(text, seg.bold))
    if out:
        out[0] = Segment(out[0].text.lstrip(), out[0].bold)
        out[-1] = Segment(out[-1].text.rstrip(), out[-1].bold)
    return tuple(s for s in out if s.text)


def render_template(
    template: str,
    slots: Mapping[str, str | Sequence[Segment]],
    bold_literals: Sequence[str] = (),
) -> tuple[Segment, ...]:
    """Preenche `{slot}` com texto ou segmentos; `bold_literals` marcam negrito do texto fixo."""
    segments: list[Segment] = []
    pos = 0
    for match in _SLOT.finditer(template):
        segments += _literal(template[pos : match.start()], bold_literals)
        value = slots[match.group(1)]
        segments += [Segment(value)] if isinstance(value, str) else list(value)
        pos = match.end()
    segments += _literal(template[pos:], bold_literals)
    return _merge(segments)


def _code_key(code: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", code))


def _code_number(document: str) -> int | None:
    match = _CODE_NUM.match(document.strip().upper())
    return int(match.group(1)) if match else None


def _of(rows: Iterable[MasterListRow], product: str | None = None, prefixes: Iterable[str] = ()):
    wanted = set(prefixes)
    return [
        r
        for r in rows
        if (product is None or r.product_code == product)
        and (not wanted or doc_prefix(r) in wanted)
    ]


def _highways(rows: Iterable[MasterListRow], rules: Mapping[str, Any]) -> list[str]:
    exclude = {fold(x) for x in _maps(rules)["highway_exclude"]}
    found = {highway(r.venture) for r in rows if r.venture and fold(r.venture) not in exclude}
    return sorted(h for h in found if h)


def highway_clause(forms: Mapping[str, str], highways: Sequence[str]) -> str:
    """Forma 1 × 2+ rodovias: `one_highway` ({highway}) ou `many_highways` ({highways} unidas).

    Mecanismo único dos slots de lista de rodovias (render_maps.highway_forms e
    measurements.highways_clause)."""
    if len(highways) == 1:
        return forms["one_highway"].format(highway=highways[0])
    return forms["many_highways"].format(highways=enumerate_pt(list(highways)))


def _with_highway_form(text: str, rules: Mapping[str, Any], slot: str,
                       highways: Sequence[str]) -> str:
    """Troca o trecho `render_maps.highway_forms.<slot>.literal` do texto-base pela forma que
    concorda com o número de rodovias ('do trecho RD-x' × 'dos trechos RD-x e RD-y')."""
    forms = _maps(rules)["highway_forms"][slot]
    if forms["literal"] not in text:
        raise KeyError(f"render_maps.highway_forms.{slot}.literal ausente do texto: "
                       f"{forms['literal']!r}")
    return text.replace(forms["literal"], highway_clause(forms, highways), 1)


def _doc_dict(row: MasterListRow) -> dict[str, Any]:
    return {
        "document": row.document,
        "product": row.product_code,
        "venture": row.venture,
        "description": " ".join(str(row.description or "").split()),
        "physical_row": row.physical_row,
    }


_PRESENCE_PRODUCT = re.compile(r"^if Produto (2\.[1-6]) tem documentos")


def _presence_product(rules: Mapping[str, Any], block_id: str) -> str | None:
    """Produto da presença 'if Produto 2.X tem documentos' do bloco em g2_content_blocks (a
    mesma frase que o motor de blocos traduz em product_has_rows); None = sem condição."""
    presence = str((rules.get("content_blocks") or {}).get(block_id, {}).get("presence") or "")
    match = _PRESENCE_PRODUCT.match(presence)
    return match.group(1) if match else None


def _block(block_id: str, segments: Sequence[Segment], **kwargs: Any) -> BlockText:
    return BlockText(block_id, [Paragraph(tuple(segments))], **kwargs)


def _skipped(block_id: str, detail: str, rule_keys: tuple[str, ...], **facts: Any) -> BlockText:
    return BlockText(block_id, [], SKIPPED, detail, dict(facts), rule_keys)


# ---------------------------------------------------------------------------------------------
# Slots AI_SYNTHESIS
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SlotText:
    """Conteúdo de um slot AI_SYNTHESIS: aprovado (OK) ou rascunho (PENDING_HUMAN)."""

    slot_id: str
    status: str
    text: str                          # com marcação **negrito**
    source: str                        # "ai_review" ou nome do provedor do rascunho
    documents: tuple[str, ...] = ()
    review_brief: ReviewBrief | None = None
    detail: str = ""

    @property
    def segments(self) -> list[Segment]:
        return parse_bold_markup(self.text)


class SynthesisProvider(Protocol):
    """Gera o RASCUNHO de um slot. Plugar aqui um provedor de IA no futuro (mesma interface)."""

    name: str

    def draft(
        self, slot_id: str, documents: Sequence[MasterListRow], rules: Mapping[str, Any]
    ) -> tuple[str, tuple[str, ...]]:
        """Devolve (texto com **negrito**, notas para a pauta)."""
        ...


def _slot_documents(slot_id: str, rows: Sequence[MasterListRow], rules: Mapping[str, Any]):
    maps = _maps(rules)
    if slot_id == S2:
        trig = maps["standardization"]["trigger"]
        return _of(rows, trig["product"], trig["prefixes"])
    if slot_id == S4:
        return _of(rows, "2.2", ["PA"])
    raise KeyError(f"slot AI_SYNTHESIS desconhecido: {slot_id}")


_QUESTIONS = {
    S2: (
        "Confirme a enumeração dos documentos de padronização (IT/CT/POP) entregues no período, "
        "o tema de cada Circular Técnica e se há documento 'em elaboração' a citar."
    ),
    S4: (
        "Quais temas dos Pareceres Técnicos do Produto 2.2 devem ser citados em "
        "'abrangendo temas como ...'?"
    ),
}


class KeywordDraftProvider:
    """Rascunho determinístico a partir da Descrição da Lista Mestra (sem IA)."""

    name = "keyword_map"

    def draft(
        self, slot_id: str, documents: Sequence[MasterListRow], rules: Mapping[str, Any]
    ) -> tuple[str, tuple[str, ...]]:
        if slot_id == S2:
            return _draft_standardization(documents, rules)
        if slot_id == S4:
            return _draft_p22_themes(documents, rules)
        raise KeyError(f"slot AI_SYNTHESIS desconhecido: {slot_id}")


def _approved(entry: Any) -> tuple[str | None, tuple[str, ...] | None]:
    if entry is None:
        return None, None
    if isinstance(entry, str):
        return entry, None
    text = entry.get("text")
    docs = entry.get("documents")
    return text, (tuple(docs) if docs is not None else None)


def ai_slot(
    slot_id: str,
    inputs: Mapping[str, Any],
    rows: Sequence[MasterListRow],
    *,
    rules: Mapping[str, Any] | None = None,
    provider: SynthesisProvider | None = None,
) -> SlotText:
    """Texto aprovado (`inputs['ai_review'][slot_id]`) ou rascunho PENDING_HUMAN com pauta.

    Regra: `g2_report_model.yaml` EXECUTIVE_SUMMARY_PARECER_THEMES (AI_SYNTHESIS,
    `human_review: true`, `input: ai_review`).
    """
    rules = rules if rules is not None else load_rules()
    provider = provider or KeywordDraftProvider()
    documents = _slot_documents(slot_id, rows, rules)
    codes = tuple(r.document for r in documents)
    text, approved_docs = _approved((inputs.get("ai_review") or {}).get(slot_id))
    notes: list[str] = []
    if text is not None:
        if approved_docs is None or set(approved_docs) == set(codes):
            return SlotText(slot_id, OK, text.strip(), "ai_review", codes)
        notes.append(
            "Aprovação existente cita outros documentos "
            f"({', '.join(approved_docs)}): tratada como de outro relatório."
        )
    if not documents:
        return SlotText(slot_id, SKIPPED, "", provider.name, codes, detail="sem documentos")
    draft, extra = provider.draft(slot_id, documents, rules)
    notes += list(extra)
    brief = ReviewBrief(
        slot_id=slot_id,
        question=_QUESTIONS[slot_id],
        documents=tuple(_doc_dict(r) for r in documents),
        draft=draft,
        provider=provider.name,
        notes=tuple(notes),
    )
    return SlotText(slot_id, PENDING, draft, provider.name, codes, brief, "rascunho sem revisão")


def write_review_brief(brief: ReviewBrief, directory: Path, *, prefix: str = "review_") -> Path:
    """Grava a pauta em `directory/<prefix><slot>.md` (só em caminho permitido; nunca SharePoint).
    O builder usa `prefix='review_brief_'` (`assemble.REVIEW_BRIEF_PREFIX`)."""
    from prog_g2_report.security import assert_write_allowed

    target = Path(directory) / f"{prefix}{brief.slot_id}.md"
    assert_write_allowed(target)         # devolve o caminho normcase; grava-se no original
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(brief.to_markdown(), encoding="utf-8")
    return target


# rascunho S2 ---------------------------------------------------------------------------------
_CIRCULAR = re.compile(r"circular tecnica\W*n[º°o]?\W*(\d+\s*/\s*\d{4})")
_NO_DE = {"de", "da", "do", "das", "dos", "para", "em", "e"}


def _title_from_description(description: Any, cfg: Mapping[str, Any]) -> str:
    """'Procedimento Operacional Padrão Gestão de NC.' -> '... Padrão de Gestão de NC'."""
    desc = " ".join(str(description or "").split()).rstrip(" .")
    match = _CIRCULAR.search(fold(desc))
    if match:
        return f"Circular Técnica nº {match.group(1).replace(' ', '')}"
    for phrase in cfg["insert_de_after"]:
        if fold(desc).startswith(fold(phrase) + " "):
            rest = desc[len(phrase) + 1 :]
            if fold(rest).split()[0] not in _NO_DE:
                desc = f"{desc[: len(phrase)]} de {rest}"
            break
    return desc


def _title_gender(title: str, cfg: Mapping[str, Any]) -> str:
    first = fold(title).split()[0] if title else ""
    return cfg["title_genders"].get(first, "m")


def _consecutive(numbers: Sequence[int | None]) -> bool:
    nums = [n for n in numbers if n is not None]
    return len(nums) == len(numbers) and all(b == a + 1 for a, b in pairwise(nums))


def _draft_standardization(
    documents: Sequence[MasterListRow], rules: Mapping[str, Any]
) -> tuple[str, tuple[str, ...]]:
    cfg = _maps(rules)["standardization"]
    groups: dict[str, list[MasterListRow]] = {}
    for row in documents:                          # ordem física; grupos na 1ª aparição
        groups.setdefault(doc_prefix(row), []).append(row)
    items: list[list[Segment]] = []
    notes: list[str] = []
    for prefix, group in groups.items():
        kind = cfg["kinds"].get(prefix, {"article_singular": "o", "ranges": False})
        if kind.get("ranges") and len(group) > 1:
            codes = [r.document for r in group]
            if _consecutive([_code_number(c) for c in codes]):
                code_text = f"{codes[0]} a {codes[-1]}"
            else:
                code_text = enumerate_pt(codes)
            items.append(
                [
                    Segment(f"{kind['article_plural']} "),
                    Segment(f"{kind['label_plural']} {code_text}", True),
                ]
            )
            notes.append(f"{prefix}: tema das {kind['label_plural']} exige leitura do conteúdo.")
            continue
        for row in group:
            title = _title_from_description(row.description, cfg)
            if "label_singular" in kind:
                head = [
                    Segment(f"{kind['article_singular']} "),
                    Segment(f"{kind['label_singular']} {row.document}", True),
                ]
                same = fold(title).startswith(fold(kind["label_singular"]))
                if not same or not _CIRCULAR.search(fold(row.description)):
                    notes.append(f"{row.document}: tema da circular exige leitura do conteúdo.")
            else:
                head = [Segment(f"{kind['article_singular']} "), Segment(row.document, True)]
            if title:
                ref = cfg["referente"][_title_gender(title, cfg)]
                head.append(Segment(f", {ref} {title}"))
            items.append(head)
    # vírgula antes do 'e' final só quando um item anterior já tem vírgula (nº 12 e nº 13)
    serial = any("," in "".join(s.text for s in item) for item in items[:-1])
    return segments_to_markup(_merge(_enumerate_segments(items, serial))), tuple(notes)


# rascunho S4 ---------------------------------------------------------------------------------
def _match_any(patterns: Iterable[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def _draft_p22_themes(
    documents: Sequence[MasterListRow], rules: Mapping[str, Any]
) -> tuple[str, tuple[str, ...]]:
    themes = _maps(rules)["p22_pa_themes_draft"]["themes"]
    hit: set[str] = set()
    notes: list[str] = []
    for row in documents:
        desc = fold(row.description)
        label = next((t["label"] for t in themes if _match_any(t["any"], desc)), None)
        if label is None:
            notes.append(f"{row.document}: descrição sem tema no mapa ({row.description!r}).")
        else:
            hit.add(label)
    labels = [t["label"] for t in themes if t["label"] in hit]   # ordem do mapa
    return enumerate_pt(labels), tuple(notes)


# ---------------------------------------------------------------------------------------------
# Renderers S0–S8
# ---------------------------------------------------------------------------------------------
def render_s0_scope(rows, inputs, rules) -> BlockText:
    keys = ("paragraphs.products_overview", "render_maps.product_label")
    codes = sorted({r.product_code for r in rows if r.product_code}, key=_code_key)
    if not codes:
        return _skipped(S0, "relatório sem linhas na Lista Mestra", keys)
    labels = [_maps(rules)["product_label"].format(code=c) for c in codes]
    text = _paragraph_rule(rules, "products_overview")["text"]
    segs = render_template(text, {"products_with_rows": enumerate_pt(labels)})
    return _block(S0, segs, facts={"products": labels}, rule_keys=keys)


def render_s1_p21(rows, inputs, rules) -> BlockText:
    keys = (
        "paragraphs.p21_coordination",
        "config.rodovias_gerenciadas",
        "render_maps.atas_clause",
        "render_maps.highway_forms.rodovias_gerenciadas",
        "g2_content_blocks P2.1_SUMMARY_S1_P21.presence",
    )
    maps = _maps(rules)
    trig = maps["atas_clause"]["trigger"]
    product = _presence_product(rules, S1)
    if product and not _of(rows, product):
        # a frase afirma atividades do Produto 2.1: só com linhas dele no relatório
        return _skipped(S1, f"Produto {product} sem linhas no relatório", keys)
    atas = _of(rows, trig["product"], [trig["prefix"]])
    clause = [Segment(s["text"], bool(s.get("bold"))) for s in maps["atas_clause"]["segments"]]
    highways = list(rules["config"]["rodovias_gerenciadas"])
    text = _with_highway_form(_paragraph_rule(rules, "p21_coordination")["text"], rules,
                              "rodovias_gerenciadas", highways)
    topics, topic_hits = p21_meeting_topics(rows, rules)
    segs = render_template(
        text,
        {"atas_clause": clause if atas else "", "p21_meeting_topics": topics},
        maps["bold_literals"]["p21_coordination"],
    )
    facts = {"highways": highways, "atas_clause": bool(atas), "atas": [r.document for r in atas],
             "meeting_topics": topic_hits}
    return _block(S1, segs, facts=facts, rule_keys=(*keys, "render_maps.p21_meeting_topics"))


def p21_meeting_topics(
    rows: Sequence[MasterListRow], rules: Mapping[str, Any]
) -> tuple[str, dict[str, list[str]]]:
    """Cláusula ', as quais contemplaram tratativas relacionadas …' do S1
    (render_maps.p21_meeting_topics): só as tratativas citadas na Descrição das AT do 2.1 do
    relatório, na ordem do mapa; `lead` no 1º item, `bare` nos demais. Devolve (cláusula,
    {tratativa: códigos}); cláusula vazia = nenhuma sustentada (anomalia
    P2.1_S1_TEMAS_REUNIOES_SEM_SUPORTE: a frase fixa citava as seis sem AT que as sustente)."""
    cfg = _maps(rules)["p21_meeting_topics"]
    trig = cfg["trigger"]
    docs = _of(rows, trig["product"], [trig["prefix"]])
    hits: dict[str, list[str]] = {}
    chosen = []
    for theme in cfg["themes"]:
        codes = sorted({r.document for r in docs if _match_any(theme["any"], fold(r.description))},
                       key=_code_key)
        if codes:
            hits[theme["label"]] = codes
            chosen.append(theme)
    if not chosen:
        return "", hits
    items = [chosen[0]["lead"], *(t["bare"] for t in chosen[1:])]
    join = cfg["join"]
    body = items[0] if len(items) == 1 else (
        join["sep"].join(items[:-1]) + join["last_sep"] + items[-1])
    return cfg["sentence"].format(p21_meeting_topics=body), hits


def render_s2_standardization(rows, inputs, rules) -> BlockText:
    keys = ("paragraphs.p21_standardization", "render_maps.standardization", "inputs.ai_review")
    trig = _maps(rules)["standardization"]["trigger"]
    if not _of(rows, trig["product"], trig["prefixes"]):
        return _skipped(S2, "sem IT/CT/POP no Produto 2.1", keys)
    slot = ai_slot(S2, inputs, rows, rules=rules, provider=rules.get("_provider"))
    body = slot.text.strip()
    body = body[:-1] if body.endswith(".") else body
    segs = render_template(
        _paragraph_rule(rules, "p21_standardization")["text"],
        {"standard_docs": parse_bold_markup(body), "in_progress": ""},
    )
    facts = {"documents": list(slot.documents), "slot_source": slot.source}
    return BlockText(
        S2, [Paragraph(segs)], slot.status, slot.detail, facts, keys, slot.review_brief
    )


def render_s3_p22(rows, inputs, rules) -> BlockText:
    keys = (
        "paragraphs.p22_overview",
        "render_maps.p22_types",
        "render_maps.p22_verb",
        "render_maps.p22_disciplines",
        "render_maps.highway_exclude",
        "render_maps.highway_forms.p22_rodovias",
    )
    maps = _maps(rules)
    p22 = _of(rows, "2.2")
    if not p22:
        return _skipped(S3, "Produto 2.2 sem linhas", keys)
    present = {doc_prefix(r) for r in p22}
    types = [t for t in maps["p22_types"] if t["prefix"] in present]
    if not types:
        return BlockText(S3, [], PENDING, "2.2 sem NT/PA: tipos fora do mapa", {}, keys)
    verb = maps["p22_verb"]
    text = _paragraph_rule(rules, "p22_overview")["text"]
    text = text.replace(verb["literal"], verb[types[0]["gender"]], 1)
    highways = _highways(p22, rules)
    text = _with_highway_form(text, rules, "p22_rodovias", highways)
    segs = render_template(
        text,
        {
            "p22_types": [Segment(enumerate_pt([t["label"] for t in types]), True)],
            "p22_disciplines": "",                 # render_maps.p22_disciplines.emit = false
        },
        maps["bold_literals"]["p22_overview"],
    )
    facts = {"types": [t["prefix"] for t in types], "highways": highways}
    return _block(S3, segs, facts=facts, rule_keys=keys)


def render_s4_p22_themes(rows, inputs, rules) -> BlockText:
    keys = (
        "paragraphs.p22_pareceres_themes",
        "render_maps.p22_pa_themes_draft",
        "inputs.ai_review",
    )
    if not _of(rows, "2.2", ["PA"]):
        return _skipped(S4, "sem PA no Produto 2.2", keys)
    slot = ai_slot(S4, inputs, rows, rules=rules, provider=rules.get("_provider"))
    segs = render_template(
        _paragraph_rule(rules, "p22_pareceres_themes")["text"],
        {"p22_pa_themes": parse_bold_markup(slot.text.strip().rstrip("."))},
    )
    facts = {"documents": list(slot.documents), "slot_source": slot.source}
    return BlockText(
        S4, [Paragraph(segs)], slot.status, slot.detail, facts, keys, slot.review_brief
    )


def p24_activities(
    p24_rows: Sequence[MasterListRow], rules: Mapping[str, Any]
) -> tuple[str, dict[str, list[str]]]:
    """Frase 'Paralelamente…' do S5 (render_maps.p24_activities): só as atividades com documento
    do 2.4 que as sustente — prefixo do Documento em `prefixes` ou Descrição normalizada casando
    `any` —, na ordem do mapa; `lead` no 1º item, `bare` nos demais. Devolve (frase, {atividade:
    códigos}); frase vazia = nenhuma atividade sustentada (a frase sai inteira)."""
    cfg = _maps(rules)["p24_activities"]
    hits: dict[str, list[str]] = {}
    chosen = []
    for theme in cfg["themes"]:
        prefixes = set(theme.get("prefixes") or ())
        codes = sorted(
            {r.document for r in p24_rows
             if doc_prefix(r) in prefixes or _match_any(theme["any"], fold(r.description))},
            key=_code_key,
        )
        if codes:
            hits[theme["label"]] = codes
            chosen.append(theme)
    if not chosen:
        return "", hits
    items = [chosen[0]["lead"], *(t["bare"] for t in chosen[1:])]
    join = cfg["join"]
    body = items[0] if len(items) == 1 else (
        join["sep"].join(items[:-1]) + join["last_sep"] + items[-1])
    return cfg["sentence"].format(p24_activities=body), hits


def render_s5_p24(rows, inputs, rules) -> BlockText:
    keys = ("paragraphs.p24_overview", "render_maps.p24_types", "render_maps.p24_article",
            "render_maps.highway_exclude", "render_maps.highway_forms.p24_rodovias",
            "render_maps.p24_activities")
    maps = _maps(rules)
    p24 = _of(rows, "2.4")
    if not p24:
        return _skipped(S5, "Produto 2.4 sem linhas", keys)
    present = {doc_prefix(r) for r in p24}
    types = [t for t in maps["p24_types"] if t["prefix"] in present]
    if not types:
        return BlockText(S5, [], PENDING, "2.4 sem tipos do mapa", {}, keys)
    highways = _highways(p24, rules)
    # artigo concorda com o 1º tipo citado (render_maps.p24_article; 'dos Relatórios', 'das
    # Notificações'); gênero/número declarados em render_maps.p24_types
    article = maps["p24_article"]
    form = f"{types[0]['gender']}{types[0]['number']}"
    text = _paragraph_rule(rules, "p24_overview")["text"]
    if article["literal"] not in text:
        raise KeyError(f"render_maps.p24_article.literal ausente do texto: {article['literal']!r}")
    text = text.replace(article["literal"], article[form], 1)
    text = _with_highway_form(text, rules, "p24_rodovias", highways)
    sentence, activities = p24_activities(p24, rules)
    segs = render_template(
        text,
        {
            "p24_types": _enumerate_segments([[Segment(t["label"], True)] for t in types]),
            "p24_activities_sentence": sentence,
        },
        maps["bold_literals"]["p24_overview"],
    )
    not_cited = sorted(present & set(maps["p24_types_not_cited"]))
    unknown = sorted(present - {t["prefix"] for t in maps["p24_types"]} - set(not_cited))
    facts = {
        "types": [t["prefix"] for t in types],
        "highways": highways,
        "activities": activities,
        "not_cited": not_cited,
        "unknown_prefixes": unknown,
    }
    detail = f"prefixos fora do mapa: {', '.join(unknown)}" if unknown else ""
    return _block(S5, segs, facts=facts, rule_keys=keys, detail=detail)


def _month_label(description: Any, prefix: str) -> str:
    desc = " ".join(str(description or "").split())
    if fold(desc).startswith(fold(prefix)):
        desc = desc[len(prefix) :]
    return desc[:1].lower() + desc[1:] if desc else ""


def render_s6_measurements(rows, inputs, rules) -> BlockText:
    keys = ("paragraphs.p24_measurements", "render_maps.measurements")
    cfg = _maps(rules)["measurements"]
    status = fold(cfg["query"]["delivery_status"])
    bms = [
        r
        for r in _of(rows, None, [cfg["query"]["prefix"]])
        if fold(r.delivery_status) == status
    ]
    if not bms:
        return _skipped(S6, "sem Boletim de Medição entregue no relatório", keys)
    highways = _highways(bms, rules)
    details: list[str] = []
    per_highway: dict[str, list[str]] = {}
    for hw in highways:
        group = sorted(
            (r for r in bms if highway(r.venture) == hw),
            key=lambda r: (_code_number(r.document) or 0, r.physical_row),
        )
        numbers = [cfg["number_format"].format(n=_code_number(r.document) or 0) for r in group]
        months = [_month_label(r.description, cfg["description_prefix"]) for r in group]
        template = cfg["detail_plural"] if len(group) > 1 else cfg["detail_singular"]
        details.append(
            template.format(
                highway=hw, numbers=enumerate_pt(numbers), months=enumerate_pt(months)
            )
        )
        per_highway[hw] = [r.document for r in group]
    # one_highway | many_highways (como P2.4_RM e render_maps.highway_forms)
    clause = highway_clause(cfg["highways_clause"], highways)
    segs = render_template(
        _paragraph_rule(rules, "p24_measurements")["text"],
        {"bm_rodovias_clause": clause, "bm_detail": " ".join(details)},
    )
    return _block(S6, segs, facts={"highways": highways, "bm": per_highway}, rule_keys=keys)


def s7_mode(rules: Mapping[str, Any]) -> str:
    """Modo do S7: `g2_report_model.yaml editorial_defaults.p21_s7_mode.value` (único default;
    o data_rule não o repete). `fixed` = os temas do mapa, todos, na ordem do mapa (frase
    idêntica nº 12–14); `keyword_map` = só temas com PA do 2.4 no relatório."""
    try:
        mode = rules["editorial_defaults"]["p21_s7_mode"]["value"]
    except (KeyError, TypeError) as exc:
        raise KeyError("editorial_defaults.p21_s7_mode ausente no modelo") from exc
    if mode not in ("fixed", "keyword_map"):
        raise ValueError(f"editorial_defaults.p21_s7_mode desconhecido: {mode!r}")
    return mode


def render_s7_p24_themes(rows, inputs, rules) -> BlockText:
    keys = ("paragraphs.p24_pareceres_themes", "render_maps.p24_pa_themes",
            "g2_report_model editorial_defaults.p21_s7_mode")
    cfg = _maps(rules)["p24_pa_themes"]
    mode = s7_mode(rules)
    pas = _of(rows, "2.4", ["PA"])
    if not pas:
        return _skipped(S7, "sem PA no Produto 2.4", keys)
    by_theme: dict[str, list[str]] = {t["label"]: [] for t in cfg["themes"]}
    covered: dict[str, list[str]] = {c["topic"]: [] for c in cfg["covered_elsewhere"]}
    unmatched: list[str] = []
    for row in pas:
        desc = fold(row.description)
        hits = [t["label"] for t in cfg["themes"] if _match_any(t["any"], desc)]
        for label in hits:
            by_theme[label].append(row.document)
        if hits:
            continue
        topic = next(
            (c["topic"] for c in cfg["covered_elsewhere"] if _match_any(c["any"], desc)), None
        )
        if topic:
            covered[topic].append(row.document)
        else:
            unmatched.append(row.document)
    if mode == "fixed":
        labels = list(by_theme)
    else:
        labels = [label for label, docs in by_theme.items() if docs]
    facts = {
        "mode": mode,
        "themes": {k: v for k, v in by_theme.items() if v},
        "covered_elsewhere": {k: v for k, v in covered.items() if v},
        "unmatched": unmatched,
    }
    if not labels:
        return BlockText(S7, [], PENDING, "PA do 2.4 sem tema no mapa", facts, keys)
    segs = render_template(
        _paragraph_rule(rules, "p24_pareceres_themes")["text"],
        {"p24_pa_themes": enumerate_pt(labels)},
    )
    detail = f"PA sem tema no mapa: {', '.join(unmatched)}" if unmatched else ""
    return _block(S7, segs, facts=facts, rule_keys=keys, detail=detail)


CLOSING_SLOT = "closing_themes"


def closing_spec(rules: Mapping[str, Any]) -> Mapping[str, Any]:
    """Mapa de temas do fecho: `paragraphs.closing.slots.closing_themes` (mesmo formato
    `slots.<nome>.themes` dos blocos do 2.4: `themes`, `join`, `required`, `empty`,
    `when_unsupported`)."""
    spec = (_paragraph_rule(rules, "closing").get("slots") or {}).get(CLOSING_SLOT)
    if not isinstance(spec, Mapping) or not isinstance(spec.get("themes"), list):
        raise KeyError(f"paragraphs.closing.slots.{CLOSING_SLOT}.themes ausente")
    return spec


def closing_themes(
    rows: Sequence[MasterListRow], rules: Mapping[str, Any]
) -> tuple[str, dict[str, list[str]]]:
    """Atuações do fecho (`paragraphs.closing.slots.closing_themes`): só as sustentadas por
    documento do relatório — Produto em `products`, prefixo do Documento em `prefixes` ou
    Descrição normalizada casando `any` —, na ordem do mapa. Devolve (enumeração, {atuação:
    códigos}); enumeração vazia = nenhuma sustentada."""
    cfg = closing_spec(rules)
    hits: dict[str, list[str]] = {}
    for theme in cfg["themes"]:
        products = {str(p) for p in theme.get("products") or ()}
        prefixes = set(theme.get("prefixes") or ())
        codes = sorted(
            {r.document for r in rows
             if r.product_code in products or doc_prefix(r) in prefixes
             or _match_any(theme.get("any") or (), fold(r.description))},
            key=_code_key,
        )
        if codes:
            hits[theme["label"]] = codes
    labels = list(hits)
    join = cfg["join"]
    body = labels[0] if len(labels) == 1 else (
        join["sep"].join(labels[:-1]) + join["last_sep"] + labels[-1] if labels else "")
    return body, hits


def render_s8_closing(rows, inputs, rules) -> BlockText:
    """S8: moldura fixa + `{closing_themes}` (só atuação com documento). Sem atuação
    sustentada: `required: false` -> `empty`; obrigatório -> `when_unsupported` (SKIPPED: o
    parágrafo não se aplica; padrão PENDING_HUMAN), como `_themed` do 2.4."""
    keys = ("paragraphs.closing", f"paragraphs.closing.slots.{CLOSING_SLOT}")
    spec = closing_spec(rules)
    body, hits = closing_themes(rows, rules)
    unsupported = [t["label"] for t in spec["themes"] if t["label"] not in hits]
    facts = {"themes": hits, "unsupported": unsupported}
    if not body:
        reason = f"nenhuma atuação do fecho sustentada por documento (slots.{CLOSING_SLOT})"
        if spec.get("required", True):
            status = str(spec.get("when_unsupported") or PENDING)
            if status == SKIPPED:
                return _skipped(S8, reason, keys, **facts)
            return BlockText(S8, [], status, reason, facts, keys)
        body = str(spec.get("empty") or "")
    segs = render_template(_paragraph_rule(rules, "closing")["text"], {"closing_themes": body})
    return _block(S8, segs, facts=facts, rule_keys=keys)


def render_table_call(rows, inputs, rules) -> BlockText:
    keys = ("paragraphs.table_call", "g2_report_model TABLE_CALL_SENTENCE.presence")
    if not _of(rows, "2.1"):
        return _skipped(TABLE_CALL, "Produto 2.1 sem linhas", keys)
    segs = render_template(_paragraph_rule(rules, "table_call")["text"], {})
    return _block(TABLE_CALL, segs, rule_keys=keys)


# ---------------------------------------------------------------------------------------------
# Agenda de reuniões (P2.1_MEETINGS_LIST)
# ---------------------------------------------------------------------------------------------
def derive_meeting_weekdays(
    rows: Sequence[MasterListRow], rules: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """Moda do dia da semana de Data Entrega das atas de alinhamento por Empreendimento.

    Regra: render_maps.meetings.weekday_from (seção K: bate nº 11, 12 e 13). Empate -> None.
    """
    cfg = _maps(rules)["meetings"]
    src = cfg["weekday_from"]
    pattern = re.compile(src["description_regex"])
    counts: dict[str, Counter] = {}
    for row in _of(rows, src["product"], [src["prefix"]]):
        if row.delivery_date is None or not pattern.search(fold(row.description)):
            continue
        counts.setdefault(highway(row.venture), Counter())[row.delivery_date.weekday()] += 1
    out: dict[str, dict[str, Any]] = {}
    for hw, counter in counts.items():
        ranked = counter.most_common()
        tie = len(ranked) > 1 and ranked[0][1] == ranked[1][1]
        out[hw] = {
            "weekday": None if tie else cfg["weekday_plural"][ranked[0][0]],
            "counts": {cfg["weekday_plural"][d]: n for d, n in sorted(counter.items())},
        }
    return out


def _field(entry: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if entry.get(name) not in (None, ""):
            return entry[name]
    return None


def render_meetings(rows, inputs, rules) -> BlockText:
    keys = (
        "g2_content_blocks P2.1_MEETINGS_LIST.template",
        "config.meetings (ordem)",
        "render_maps.meetings",
        "inputs.meetings_agenda",
    )
    cfg = _maps(rules)["meetings"]
    template = rules["content_blocks"][MEETINGS]["template"]
    pending_mark = cfg["pending_marker"]
    agenda = {
        highway(_field(e, "highway", "rodovia")): e for e in (inputs.get("meetings_agenda") or [])
    }
    order = [highway(m["rodovia"]) for m in rules["config"]["meetings"]]
    order += [hw for hw in agenda if hw not in order]
    derived = derive_meeting_weekdays(rows, rules)
    paragraphs: list[Paragraph] = []
    pending: list[str] = []
    items: list[dict[str, Any]] = []
    for hw in order:
        entry = agenda.get(hw, {})
        executora = _field(entry, "executora", "company")
        weekday = _field(entry, "weekday", "dia_semana")
        weekday_source = "input"
        if weekday is None:
            weekday = (derived.get(hw) or {}).get("weekday")
            weekday_source = "atas" if weekday else "pending"
        hour = _field(entry, "hour", "hora")
        for name, value in (("executora", executora), ("weekday", weekday), ("hour", hour)):
            if value is None:
                pending.append(f"{hw}.{name}")
        if executora is None:
            article = ""
        else:
            article = _field(entry, "article", "artigo") or next(
                (a for p, a in cfg["article_by_prefix"].items() if str(executora).startswith(p)),
                cfg["default_article"],
            )
        text = template.format(
            highway=hw,
            executora_artigo=article,
            executora=executora or pending_mark,
            dia_semana_plural=weekday or pending_mark,
            hora=hour or pending_mark,
        )
        paragraphs.append(
            Paragraph(_merge([Segment(text)]), style="PargrafodaLista", list_style="bullet")
        )
        check = (derived.get(hw) or {}).get("weekday")
        items.append(
            {
                "highway": hw,
                "executora": executora,
                "weekday": weekday,
                "weekday_source": weekday_source,
                "weekday_from_atas": check,
                "weekday_matches_atas": None if check is None else check == weekday,
                "hour": hour,
            }
        )
    status = PENDING if pending else OK
    detail = f"pendente de entrada humana: {', '.join(pending)}" if pending else ""
    facts = {"items": items, "pending": pending, "derived": derived}
    return BlockText(MEETINGS, paragraphs, status, detail, facts, keys)


# ---------------------------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------------------------
P21_RENDERERS: dict[str, Renderer] = {
    MEETINGS: render_meetings,
    S0: render_s0_scope,
    S1: render_s1_p21,
    S2: render_s2_standardization,
    S3: render_s3_p22,
    S4: render_s4_p22_themes,
    S5: render_s5_p24,
    S6: render_s6_measurements,
    S7: render_s7_p24_themes,
    S8: render_s8_closing,
    TABLE_CALL: render_table_call,
}


def render_block(
    block_id: str,
    rows: Sequence[MasterListRow],
    inputs: Mapping[str, Any] | None = None,
    rules: Mapping[str, Any] | None = None,
) -> BlockText:
    return P21_RENDERERS[block_id](rows, inputs or {}, rules if rules is not None else load_rules())


def render_executive_summary(
    rows: Sequence[MasterListRow],
    inputs: Mapping[str, Any] | None = None,
    rules: Mapping[str, Any] | None = None,
) -> list[BlockText]:
    """S0–S8 + chamada da tabela, na ordem do documento (blocos SKIPPED vêm sem parágrafos)."""
    rules = rules if rules is not None else load_rules()
    return [render_block(b, rows, inputs, rules) for b in SUMMARY_ORDER]
