"""G2_REPORT_MODEL — carga e validação do modelo do Relatório G2.

O modelo vive em `config/g2_report_model.yaml`. Este módulo é o Gate B em código: um modelo só
serve ao builder se `validate_model()` não devolver nenhuma violação. Pendências conhecidas
(arquivos citados ainda não entregues, `pending_files`) saem em `model_pendencies()`, separadas.

O validador confere o modelo contra os arquivos que o builder realmente lê (content_blocks,
data_rules, ooxml_base, manifesto de assets, catálogo de anomalias), nunca contra ele mesmo.

Invariantes verificados:
    identidade
    - `model.reference` == `report_id.format_report(...)` do golden de papel `reference` (único);
    - nenhuma sigla "RM" como identificador ("RM14", "RM 14", "RM-14", "RM_14", "RM nº 14",
      "RM n.º 14");
    componentes
    - `component_id` único, em MAIÚSCULAS, e todo componente da matriz de reprodutibilidade
      está no modelo ou em `discontinued`;
    - nenhuma anomalia histórica é citada como proveniência de regra (com ou sem `anomaly:`);
    - STATIC_ASSET tem `asset`; STRUCTURED_DATA tem `source`; RECONSTRUCTED_VISUAL tem `source` e
      `render` com referência `arquivo#chave`; TEMPLATE tem `fields`, `blocks` ou `source`;
      AI_SYNTHESIS tem `allowed_sources`, `human_review` booleano `true` e `input` declarado;
    - `source` é chave de `sources` que não é `not_sources` (nem nome de uma não-fonte);
    - `render`/`source`/`default` sem texto vago ("a definir", "TBD", "TODO", "??");
    - CONFIRMED tem `evidence_months` com ≥ 2 meses distintos, todos dentro de
      `model.evidence_window` (nenhum mês no futuro da referência);
    - confiança do componente ≤ menor confiança declarada nos seus blocos (`evidence.confidence`)
      e nas regras que ele cita (`confidence` em toda a subárvore da chave `arquivo#chave`);
    - classe do bloco × classe do componente: bloco MANUAL_INPUT só em componente MANUAL_INPUT,
      bloco AI_SYNTHESIS só em AI_SYNTHESIS (nada manual ou de IA escondido em CODE/TEMPLATE);
    entradas humanas
    - todo MANUAL_INPUT e AI_SYNTHESIS aponta uma entrada de `inputs` que o lista em `used_by`;
      todo `used_by` é componente do modelo;
    - todo nó `class: MANUAL_INPUT|AI_SYNTHESIS` dentro de data_rules ou de um slot de bloco é
      citado por uma entrada de `inputs` ou por um componente da mesma classe;
    blocos e textos
    - `blocks` existem em `config/g2_content_blocks.yaml` e todo bloco pertence a exatamente um
      componente (ou a `discontinued`); todo produto tem o seu bloco de título `P<código>_TITLE`;
    - desvio `kind: ANOMALY` de bloco cita uma anomalia que existe em `anomalies.jsonl`;
    - texto emitido — content_blocks (todas as classes) e os textos dos data_rules
      (`p21_executive_summary.yaml#paragraphs`/`render_maps`, `p24_blocks.yaml#blocks`,
      `p22_highway_block.yaml#templates`) — não contém o trecho anômalo de nenhuma anomalia
      (derivado de `observed_value` × `expected_value`, ver `anomaly_needles`), nem mês, data ou
      número de relatório literais (vêm de `{month_label}`, `{report_number}`…);
    referências e coerência entre arquivos
    - toda referência `config/....yaml#chave/subchave` aponta arquivo e chave existentes; em
      `render`/`source`/`default` a referência a arquivo exige `#chave`; a forma antiga
      `arquivo.yaml: chave` é recusada;
    - assets do modelo existem no manifesto com sha1 válido, repetido e igual no modelo; se o
      arquivo existe em disco, o sha1 dele confere;
    - as ordens de rodovia (`contract.highway_orders`) são permutações de `contract.highways`;
    - seções 2.1 a 2.6 presentes; orientação retrato → paisagem → retrato, igual em
      `config/ooxml_base.yaml#page/sections` (orientação e margens);
    - `editorial_defaults.nc_enumeration`: valor `always_when_present | never | up_to_<N>`, N ==
      `enumerate_max` == `enumerate_max` da regra citada;
    - `editorial_defaults.p21_s7_mode` é o único default do S7 (o data_rule não repete `mode`);
    - contagem de anexos = `len(index_rows)` (DEC-012) em V_ANNEX_COUNT, CLOSING_ANNEX_COUNT e no
      placeholder `annex_count`; nunca `len(body_rows)` nem com aritmética (`+ 1`);
    Gate B tentativa 4 (revisor W3, QA-C, QA-E)
    - texto emitido inclui `editorial_defaults.*`, `inputs.*.schema.no_information.text` e os
      textos do ooxml_base (cabeçalho, rodapé, sumário, capa); hardcode também por extenso
      ('agosto de 2026', 'décimo quarto relatório'), 'MM/AAAA' e 'AAAA-MM';
    - trecho anômalo com localizador (1º pedaço antes de '...') só conta no mesmo texto; falta de
      pontuação final é ancorada no fim;
    - CONFIRMED (≥ 2 meses na janela) vale para QUALQUER nó do modelo com `confidence`;
    - `positioning`: blocos, assets, modos de âncora, alinhamentos e contagem de vazios válidos;
    - ooxml_base: pgSz coerente com a orientação e com `model.page` (A4);
    - um default por parâmetro (`editorial_defaults` não repete `render_params`);
    - `fields` existem (placeholder, entrada ou slot); `review_key` é o bloco citado no render;
    - desvio ANOMALY não cita anomalia só TRUE_MODEL_CHANGE/METHOD_ERROR;
    - mapa de temas declara `fills` e nenhum texto preenchido traz tema literal (afirmação
      temática sem documento, QA-C); `contract.environmental_processes` declarado e completo.
    Pendências do Gate B tentativa 4 (revisor W4)
    - toda `presence` de bloco se traduz em predicado nomeado (`builder.presence`); nenhuma
      fica 'presente por padrão';
    - entrada humana do P2.2 externo: `schema.empty_value`/`missing_field` declaram
      PENDING_HUMAN e o sentinela `schema.no_information` tem chave e texto padronizado.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from prog_g2_report import REPO_ROOT
from prog_g2_report.report_id import format_report, month_label

MODEL_PATH = REPO_ROOT / "config" / "g2_report_model.yaml"
CONTENT_BLOCKS_PATH = REPO_ROOT / "config" / "g2_content_blocks.yaml"
ASSETS_MANIFEST_PATH = REPO_ROOT / "config" / "assets_manifest.yaml"
CATALOG = REPO_ROOT / "data" / "catalog"
OOXML_BASE = "config/ooxml_base.yaml"
CONTENT_BLOCKS = "config/g2_content_blocks.yaml"
ASSETS_MANIFEST = "config/assets_manifest.yaml"
P21_RULES = "config/data_rules/p21_executive_summary.yaml"

STATUSES = ("NONE", "CANDIDATE", "BUILDER_READY", "FROZEN", "CERTIFIED")
CLASSES = {
    "CODE", "STATIC_ASSET", "TEMPLATE", "STRUCTURED_DATA", "RECONSTRUCTED_VISUAL",
    "AI_SYNTHESIS", "MANUAL_INPUT",
}
CONFIDENCES = {"CONFIRMED", "HIGH_CONFIDENCE", "MEDIUM_CONFIDENCE", "LOW_CONFIDENCE"}
RANK = {"CONFIRMED": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}
REFERENCE = "Relatório G2 nº 14 — Agosto/2026"
NC_POLICIES = ("always_when_present", "never")
S7_MODES = ("fixed", "keyword_map")
# classes de bloco que exigem componente da mesma classe (entrada humana / síntese revisada)
HUMAN_CLASSES = ("MANUAL_INPUT", "AI_SYNTHESIS")

# "RM14", "RM 14", "RM-14", "RM_14", "RM nº 14", "RM n° 14", "RM n.º 14"; não pega códigos de
# documento ("RM-011.1") nem o sufixo de id "P2.4_RM"
_RM = re.compile(r"\bRM(?:[\s_]?-?\s?)?(?:[nN]\.?\s?[º°o]\.?\s?)?\d{1,2}(?![\d.]\d|\d)")
_ID = re.compile(r"^[A-Z0-9_.]+$")
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_REF = re.compile(r"(config/[\w./-]+?\.ya?ml)(?:#([\w./-]*[\w-]))?")
_OLD_REF = re.compile(r"config/[\w./-]+?\.ya?ml:\s*\w")
_REF_FIELDS = ("render", "source", "default", "ref")
_ID_FIELDS = ("block_id", "component_id", "asset_id", "id", "code", "prefix")
_VAGUE = re.compile(r"\b(a definir|tbd|todo|fixme)\b|\?\?", re.IGNORECASE)
_ANOMALY_REF = re.compile(r"anomalies\.jsonl\s+([A-Z0-9_.]+)")

# texto que o builder emite (o resto do bloco é evidência, observação ou metadado)
_EMITTED_KEYS = {
    "text", "template", "templates", "items", "texts", "paragraphs", "lead", "fixed_parts",
    "text_standardized", "text_template", "value_if_true", "value_if_false", "form", "forms",
    "one_highway", "many_highways",
}
_NOT_EMITTED = re.compile(
    r"^(evidence|deviations|observed.*|notes?|history|provenance|variants|examples|"
    r"standardization|dec007|rule|trigger.*|validated|.*_no\d+|.*_nº\d+|.*historical.*)$")
# data_rules: raiz varrida e chaves cujo valor o renderizador emite (além de _EMITTED_KEYS)
DATA_RULE_TEXTS: dict[str, tuple[tuple[str, ...], frozenset[str]]] = {
    P21_RULES: (("paragraphs", "render_maps"), frozenset({
        "label", "label_singular", "label_plural", "segments", "detail_plural",
        "detail_singular", "literal", "m", "f", "mp", "fp", "ms", "fs", "sentence", "bare"})),
    "config/data_rules/p24_blocks.yaml": (("blocks",), frozenset({
        "nc_base", "lau_status_clause", "near_due_clause", "phase_label",
        "phase_label_multi_variant", "highway_item", "bm_item", "sent", "single_phase",
        "multi_phase", "one_code", "many_codes", "next_one_code", "next_many_codes",
        "singular_part", "phase_part", "standard", "label", "follow", "bare"})),
    "config/data_rules/p22_highway_block.yaml": (("templates",), frozenset({
        "runs", "universal", "plural", "singular", "empty", "any"})),
}
_RULE_NOT_EMITTED = re.compile(
    r"^(evidence|deviations|observed.*|notes?|.*_note|.*_ref|.*_condition|.*_qualifier|"
    r"history|provenance|variants|examples|rule|trigger.*|validated|.*_no\d+|.*_nº\d+|nº\d+|"
    r".*historical.*|.*_evidence|style|class|policy|confidence.*|presence.*|query|reproduction|"
    r"divergences|order.*|terminator|punctuation|enumeration|article_table|display_name|"
    r"preceded_by|unobserved|open|bold|numId|ilvl|grouping|position|after|not_emit|"
    r"rendered_.*|adjacent_note|source|nc_groups|any_regex|themes_regex)$")
# textos emitidos a partir de config/ooxml_base.yaml (cabeçalho, rodapé, sumário, capa)
OOXML_TEXT_ROOTS = ("header", "footer", "toc", "cover")
OOXML_TEXT_KEYS = frozenset({"text", "lines", "template", "title", "placeholder"})
# classes de anomalia que não descrevem texto errado (mudança de padrão, erro do diagnóstico)
_NOT_TEXT_DEFECTS = {"TRUE_MODEL_CHANGE", "METHOD_ERROR"}
_MIN_NEEDLE = 6
_SIMILAR = 0.6
_QUOTE = re.compile(r"'([^']+)'")
_ELLIPSIS = re.compile(r"\.\.\.|…")

# número, mês e data do relatório nunca são literais em texto emitido (vêm do contexto)
_MONTHS = ("janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|"
           "novembro|dezembro")
_HARDCODE = (
    (re.compile(rf"\b(?:{_MONTHS})\s?/\s?\d{{4}}\b", re.IGNORECASE),
     "mês/ano literal (usar {month_label})"),
    (re.compile(rf"\b\d{{1,2}}\s?de\s+(?:{_MONTHS})\s+de\s+\d{{4}}\b", re.IGNORECASE),
     "data literal (usar o placeholder da data)"),
    (re.compile(r"\b[nN]\.?\s?[º°]\.?\s?\d{1,3}\b(?![/\d])"),
     "número de relatório literal (usar {report_number})"),
    (re.compile(rf"\b(?:{_MONTHS})\s+de\s+\d{{4}}\b", re.IGNORECASE),
     "mês/ano literal por extenso (usar {month_label})"),
    # 'mês 08/2026'; não pega número de documento ('nº 00/0000', '00/0000-PARC') nem data
    # dd/mm/aaaa
    (re.compile(r"(?<![º°]\s)(?<![º°])(?<![\d/])(?:0[1-9]|1[0-2])/(?:19|20)\d{2}(?![\d-])"),
     "mês/ano numérico literal (usar {month_label})"),
    (re.compile(r"(?<![\d-])(?:19|20)\d{2}-(?:0[1-9]|1[0-2])(?![\d-])"),
     "mês de referência literal AAAA-MM (vem do contexto)"),
    (re.compile(r"\b(?:primeiro|segundo|terceiro|quarto|quinto|sexto|s[ée]timo|oitavo|nono|"
                r"d[ée]cimo|vig[ée]simo|trig[ée]simo)(?:\s+(?:primeiro|segundo|terceiro|quarto|"
                r"quinto|sexto|s[ée]timo|oitavo|nono))?\s+relat[óo]rio\b", re.IGNORECASE),
     "número de relatório por extenso (usar {report_number})"),
)


# --------------------------------------------------------------------------- carga
def _yaml(path: Path) -> Any:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def load_model(path: Path = MODEL_PATH) -> dict[str, Any]:
    return _yaml(path)


def load_content_blocks(path: Path = CONTENT_BLOCKS_PATH) -> dict[str, Any]:
    return _yaml(path) if Path(path).exists() else {}


def load_assets_manifest(path: Path = ASSETS_MANIFEST_PATH) -> dict[str, dict[str, Any]]:
    """{asset_id: entrada} de `config/assets_manifest.yaml`."""
    if not Path(path).exists():
        return {}
    return _manifest_by_id(_yaml(path))


def _manifest_by_id(data: Any) -> dict[str, dict[str, Any]]:
    entries = data.get("assets", data) if isinstance(data, dict) else data
    if isinstance(entries, dict):
        return {k: (v or {}) for k, v in entries.items()}
    return {e.get("asset_id"): e for e in entries or [] if isinstance(e, dict)}


def _jsonl(name: str) -> list[dict]:
    path = CATALOG / name
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _walk_strings(node: Any):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _walk_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_strings(value)


# --------------------------------------------------------------------------- referências
_MISSING = object()


def resolve_key(data: Any, key: str) -> Any:
    """Segue `a/b/c` num YAML: chave de mapeamento, item de lista por id (`block_id`, `id`…)
    ou índice. Um segmento ausente no mapeamento procura nas listas filhas por id."""
    node = data
    for seg in [s for s in key.split("/") if s]:
        node = _step(node, seg)
        if node is _MISSING:
            return _MISSING
    return node


def _match_item(items: list, seg: str) -> Any:
    for item in items:
        if isinstance(item, dict) and any(str(item.get(f)) == seg for f in _ID_FIELDS if f in item):
            return item
    if seg.isdigit() and int(seg) < len(items):
        return items[int(seg)]
    return _MISSING


def _step(node: Any, seg: str) -> Any:
    if isinstance(node, dict):
        if seg in node:
            return node[seg]
        for value in node.values():
            if isinstance(value, list):
                found = _match_item(value, seg)
                if found is not _MISSING:
                    return found
        return _MISSING
    if isinstance(node, list):
        return _match_item(node, seg)
    return _MISSING


def _pending_paths(model: dict[str, Any]) -> set[str]:
    out = set()
    for item in model.get("pending_files") or []:
        out.add(item.get("path") if isinstance(item, dict) else str(item))
    return out


class _Files:
    """YAMLs citados pelo modelo, lidos uma vez a partir de `root`."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._cache: dict[str, Any] = {}

    def exists(self, path: str) -> bool:
        return (self.root / path).exists()

    def get(self, path: str) -> Any:
        if path not in self._cache:
            self._cache[path] = _yaml(self.root / path) if self.exists(path) else None
        return self._cache[path]

    def put(self, path: str, data: Any) -> None:
        self._cache[path] = data

    def node(self, path: str, key: str) -> Any:
        data = self.get(path)
        return _MISSING if data is None else resolve_key(data, key)


def _check_ref(path: str, key: str | None, files: _Files, pending: set[str],
               where: str) -> list[str]:
    if not files.exists(path):
        return [] if path in pending else [f"{where}: arquivo citado não existe: {path}"]
    if key is None:
        return []
    if files.node(path, key) is _MISSING:
        return [f"{where}: chave inexistente {path}#{key}"]
    return []


def _refs_in(text: str):
    for match in _REF.finditer(text):
        yield match.group(1), match.group(2)


def model_pendencies(model: dict[str, Any], root: Path = REPO_ROOT) -> list[str]:
    """Pendências declaradas (não violações): arquivos de `pending_files` ainda não entregues."""
    out = []
    for path in sorted(_pending_paths(model)):
        if (root / path).exists():
            out.append(f"{path}: entregue — retirar de pending_files")
        else:
            out.append(f"{path}: pendente (citado pelo modelo, ainda não entregue)")
    return out


# --------------------------------------------------------------------------- texto emitido
def _emitted_strings(node: Any, emit: bool = False, keys: frozenset[str] | set[str] = frozenset(),
                     skip: re.Pattern = _NOT_EMITTED):
    keys = keys or _EMITTED_KEYS
    if isinstance(node, dict):
        has_text = any(k in node for k in ("text", "text_standardized", "template"))
        for key, value in node.items():
            if key == "text_historical" and not has_text:
                yield from _emitted_strings(value, True, keys, skip)
            elif not skip.match(str(key)):
                yield from _emitted_strings(value, emit or key in keys, keys, skip)
    elif isinstance(node, list):
        for value in node:
            yield from _emitted_strings(value, emit, keys, skip)
    elif isinstance(node, str) and emit:
        yield node


def model_emitted_texts(model: dict[str, Any] | None,
                        ooxml: dict[str, Any] | None) -> list[tuple[str, str]]:
    """(onde, texto) que o builder emite a partir do PRÓPRIO modelo e do ooxml_base:
    `editorial_defaults.*` (valores textuais: contract_ref, p22_empty_set…), os textos das
    entradas (`inputs.*.schema.no_information.text`) e os textos de `config/ooxml_base.yaml`
    (cabeçalho, rodapé, sumário, capa: `MODEL_TEXTS`/`OOXML_TEXTS`)."""
    out: list[tuple[str, str]] = []
    for name, spec in ((model or {}).get("editorial_defaults") or {}).items():
        value = spec.get("value") if isinstance(spec, dict) else spec
        if isinstance(value, str):
            out.append((f"editorial_defaults.{name}", value))
    for name, spec in ((model or {}).get("inputs") or {}).items():
        info = ((spec or {}).get("schema") or {}).get("no_information") \
            if isinstance(spec, dict) else None
        if isinstance(info, dict) and isinstance(info.get("text"), str):
            out.append((f"inputs.{name}.schema.no_information.text", info["text"]))
    for root in OOXML_TEXT_ROOTS:
        node = (ooxml or {}).get(root)
        out += [(f"{OOXML_BASE}#{root}", text)
                for text in _emitted_strings(node, False, OOXML_TEXT_KEYS, _RULE_NOT_EMITTED)]
    return out


def emitted_texts(content: dict[str, Any], rules: dict[str, Any],
                  model: dict[str, Any] | None = None,
                  ooxml: dict[str, Any] | None = None) -> list[tuple[str, str]]:
    """(onde, texto) de tudo que o builder emite: blocos do content_blocks de TODAS as classes,
    os textos dos data_rules (`DATA_RULE_TEXTS`) e, com `model`/`ooxml`, os textos do próprio
    modelo e do ooxml_base (`model_emitted_texts`). `rules` = {caminho: YAML carregado}."""
    out: list[tuple[str, str]] = model_emitted_texts(model, ooxml) if (model or ooxml) else []
    for block in content.get("blocks") or []:
        body = {k: v for k, v in block.items() if k != "block_id"}
        out += [(str(block.get("block_id")), text) for text in _emitted_strings(body)]
    for path, (roots, extra) in DATA_RULE_TEXTS.items():
        data = rules.get(path)
        if not isinstance(data, dict):
            continue
        keys = frozenset(_EMITTED_KEYS | extra)
        for root_key in roots:
            node = data.get(root_key)
            items = node if isinstance(node, list) else [node]
            for i, item in enumerate(items):
                label = (item.get("block_id") or item.get("id") or i) if isinstance(item, dict) \
                    else i
                where = f"{path}#{root_key}" + (f"/{label}" if isinstance(node, list) else "")
                out += [(where, text) for text in _emitted_strings(item, False, keys,
                                                                   _RULE_NOT_EMITTED)]
    return out


# --------------------------------------------------------------------------- anomalias
def _word_start(text: str, i: int) -> int:
    while i > 0 and not text[i - 1].isspace():
        i -= 1
    return i


def _word_end(text: str, j: int) -> int:
    while j < len(text) and not text[j].isspace():
        j += 1
    return j


def _expand(text: str, a: int, b: int) -> tuple[int, int]:
    """Trecho divergente [a, b) → palavras inteiras; inserção pura (a == b) inclui a palavra de
    cada lado (a ausência só existe entre duas palavras); depois, contexto até `_MIN_NEEDLE`."""
    s, e = _word_start(text, a), _word_end(text, b)
    if a == b:
        if s == a:
            k = a
            while k > 0 and text[k - 1].isspace():
                k -= 1
            s = _word_start(text, k)
        if e == b:
            k = b
            while k < len(text) and text[k].isspace():
                k += 1
            e = _word_end(text, k)
    while len(text[s:e].strip()) < _MIN_NEEDLE and (s > 0 or e < len(text)):
        if s > 0:
            k = s
            while k > 0 and text[k - 1].isspace():
                k -= 1
            s = _word_start(text, k)
        else:
            k = e
            while k < len(text) and text[k].isspace():
                k += 1
            e = _word_end(text, k)
    return s, e


def _diff_spans(observed: str, expected: str) -> list[tuple[str, bool]]:
    """Trechos de `observed` que divergem de `expected`, em palavras inteiras, fundidos, com
    `ancorado no fim`: uma inserção pura no fim do observado (falta pontuação final, ex.:
    P2.1_RESUMO_PONTO_FINAL) só é anômala quando o texto TERMINA ali."""
    matcher = difflib.SequenceMatcher(None, observed, expected, autojunk=False)
    end = len(observed.rstrip())
    spans = sorted((*_expand(observed, i1, i2), tag == "insert" and i1 >= end)
                   for tag, i1, i2, _, _ in matcher.get_opcodes() if tag != "equal")
    merged: list[list[Any]] = []
    for s, e, at_end in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
            merged[-1][2] = merged[-1][2] and at_end
        else:
            merged.append([s, e, at_end])
    return [(observed[s:e], at_end) for s, e, at_end in merged]


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _fragment(observed: str, expected: str) -> str | None:
    """`expected` curto (≤ 3 palavras) que corrige uma janela de `observed`: devolve a janela
    observada mais parecida (≥ `_SIMILAR`), com contexto até `_MIN_NEEDLE`."""
    words = list(re.finditer(r"\S+", observed))
    n = len(expected.split())
    best, best_ratio = None, _SIMILAR
    for i in range(len(words) - n + 1):
        a, b = words[i].start(), words[i + n - 1].end()
        r = _ratio(observed[a:b], expected)
        if r >= best_ratio and observed[a:b] != expected:
            best, best_ratio = (a, b), r
    if best is None:
        return None
    s, e = _expand(observed, *best)
    return observed[s:e]


def _anomaly_needles(anomalies: list[dict]) -> list[tuple[str, str, bool, str]]:
    """(componente, trecho anômalo, ancorado no fim do texto, localizador).

    O trecho é derivado de `observed_value` × `expected_value`, nunca o valor observado inteiro
    quando parte dele é legítima:
    - citações entre aspas simples são o texto observado; sem aspas, o valor inteiro;
    - com reticências, o 1º pedaço (antes de '...') localiza o parágrafo e não é anômalo: ele
      vira o `localizador`, e o trecho só conta num texto que também o contenha (ex.: 'da rodovia
      RD-102A' só é anômalo no item 'a) RD-104:');
    - esperado parecido com o observado (≥ 60%): o trecho divergente (`_diff_spans`);
    - esperado curto (≤ 3 palavras): a janela observada que ele corrige (`_fragment`);
    - esperado descritivo: o pedaço inteiro, salvo um termo único entre aspas (é menção de termo,
      não texto); um pedaço terminado em ':' é ancorado no fim (valor ausente depois do ':').
    """
    out: list[tuple[str, str, bool, str]] = []
    for item in anomalies:
        if item.get("classification") in _NOT_TEXT_DEFECTS:
            continue
        comp = item.get("component", "?")
        observed = str(item.get("observed_value") or "")
        expected = str(item.get("expected_value") or "")
        quotes = _QUOTE.findall(observed)
        expected_texts = [_ELLIPSIS.sub("", e).strip(" ,;")
                          for e in (_QUOTE.findall(expected) or [expected])]
        for text in quotes or [observed]:
            parts = _ELLIPSIS.split(text)
            ellipsis = len(parts) > 1
            locator = parts[0].strip(" ,;") if ellipsis else ""
            for i, raw in enumerate(parts):
                part = raw.strip(" ,;") if ellipsis else raw
                if not part.strip():
                    continue
                if ellipsis and i == 0 and any(p.strip(" ,;") for p in parts[1:]):
                    continue
                best = max(expected_texts, key=lambda e, p=part: _ratio(p, e))
                if best and _ratio(part, best) >= _SIMILAR:
                    out += [(comp, n, at_end, locator) for n, at_end in _diff_spans(part, best)]
                    continue
                if best and len(best.split()) <= 3 and len(best) < len(part):
                    window = _fragment(part, best)
                    if window:
                        out.append((comp, window, False, locator))
                        continue
                if quotes and len(part.split()) == 1:
                    continue
                out.append((comp, part, part.rstrip().endswith(":"), locator))
    seen: set[tuple[str, str, bool, str]] = set()
    return [x for x in out if len(x[1].strip()) >= _MIN_NEEDLE and not (x in seen or seen.add(x))]


def anomaly_needles(anomalies: list[dict]) -> list[tuple[str, str]]:
    """(componente da anomalia, trecho anômalo) com ≥ 6 caracteres (`_anomaly_needles`)."""
    return [(comp, needle) for comp, needle, _, _ in _anomaly_needles(anomalies)]


def _anomaly_text_errors(texts: list[tuple[str, str]], anomalies: list[dict]) -> list[str]:
    needles = []
    for comp, needle, at_end, locator in _anomaly_needles(anomalies):
        tail = r"(?=\s*$)" if at_end else r"(?!\w)"
        rx = re.compile(r"(?<!\w)" + re.escape(needle) + tail)
        needles.append((comp, needle, rx, locator))
    errors = []
    for where, text in texts:
        for comp, needle, rx, locator in needles:
            if rx.search(text) and (not locator or locator in text):
                errors.append(f"{where}: texto emitido contém valor observado da "
                              f"anomalia {comp}: {needle[:50]!r}")
    return errors


def _allowed_literals(model: dict[str, Any], content: dict[str, Any]) -> tuple[dict[str, set[str]],
                                                                             list[str]]:
    """`allowed_literals` de cada bloco: referência fixa a OUTRO relatório (ex.: 'N° 09' em
    P2.1_ATAS_REALOC). Nunca o número de um golden nem um mês da janela de evidência."""
    meta = model.get("model") or {}
    numbers = {int(g["report_number"]) for g in meta.get("golden_tests") or []
               if str(g.get("report_number", "")).isdigit()}
    months = {month_label(m) for m in meta.get("evidence_window") or [] if _MONTH.match(str(m))}
    allowed: dict[str, set[str]] = {}
    errors = []
    for block in content.get("blocks") or []:
        for item in block.get("allowed_literals") or []:
            literal = str(item.get("literal") if isinstance(item, dict) else item)
            digits = {int(d) for d in re.findall(r"\d+", literal)}
            if not (isinstance(item, dict) and item.get("reason")):
                errors.append(f"{block.get('block_id')}: allowed_literals {literal!r} sem reason")
            if digits & numbers or any(m.lower() in literal.lower() for m in months):
                errors.append(f"{block.get('block_id')}: allowed_literals {literal!r} é número ou "
                              "mês de relatório da janela (hardcode)")
                continue
            allowed.setdefault(str(block.get("block_id")), set()).add(literal)
    return allowed, errors


def _hardcode_errors(texts: list[tuple[str, str]], allowed: dict[str, set[str]]) -> list[str]:
    errors = []
    for where, text in texts:
        for rx, what in _HARDCODE:
            for found in rx.finditer(text):
                if found.group(0) not in allowed.get(where, set()):
                    errors.append(f"{where}: {what} em texto emitido: {found.group(0)!r}")
    return errors


# --------------------------------------------------------------------------- confiança
def _rank(value: Any) -> int | None:
    token = str(value).split()[0] if str(value).split() else ""
    return RANK.get(token.removesuffix("_CONFIDENCE"))


def _declared(value: Any):
    if isinstance(value, dict):
        for item in value.values():
            yield from _declared(item)
    elif isinstance(value, list):
        for item in value:
            yield from _declared(item)
    else:
        rank = _rank(value)
        if rank is not None:
            yield rank, str(value)


def _subtree_confidences(node: Any):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "confidence":
                yield from _declared(value)
            else:
                yield from _subtree_confidences(value)
    elif isinstance(node, list):
        for value in node:
            yield from _subtree_confidences(value)


def _confidence_errors(comp: dict, blocks: dict[str, dict], files: _Files) -> list[str]:
    cid = comp.get("component_id")
    own = _rank(comp.get("confidence"))
    if own is None:
        return []
    found: list[tuple[int, str]] = []
    for block_id in comp.get("blocks") or []:
        evidence = (blocks.get(block_id) or {}).get("evidence") or {}
        if "confidence" in evidence:
            found += [(r, f"bloco {block_id} ({v})") for r, v in _declared(evidence["confidence"])]
    for field in _REF_FIELDS:
        value = comp.get(field)
        if not isinstance(value, str):
            continue
        for path, key in _refs_in(value):
            node = files.node(path, key) if key else _MISSING
            if node is not _MISSING:
                found += [(r, f"{path}#{key} ({v})") for r, v in _subtree_confidences(node)]
    if not found:
        return []
    low = min(found)
    if own > low[0]:
        return [f"{cid}: confidence {comp.get('confidence')} acima da evidência declarada em "
                f"{low[1]}"]
    return []


# --------------------------------------------------------------------------- rodovias
def _highway_errors(model: dict[str, Any], files: _Files, pending: set[str]) -> list[str]:
    contract = model.get("contract") or {}
    highways = contract.get("highways") or []
    if not highways:
        return ["contract.highways ausente: o domínio de rodovias é declarado uma vez no modelo"]
    codes = [h.get("code") for h in highways]
    if len(set(codes)) != len(codes):
        return [f"contract.highways com código repetido: {codes}"]
    alias = {a: h["code"] for h in highways for a in (h.get("aliases") or [])}
    errors = []
    for name, spec in (contract.get("highway_orders") or {}).items():
        ref = (spec or {}).get("ref", "")
        match = _REF.fullmatch(ref.strip())
        if not match or not match.group(2):
            errors.append(f"contract.highway_orders.{name}: ref fora do formato arquivo#chave")
            continue
        path, key = match.group(1), match.group(2)
        if not files.exists(path):
            if path not in pending:
                errors.append(f"contract.highway_orders.{name}: arquivo citado não existe: {path}")
            continue
        value = files.node(path, key)
        if value is _MISSING or not isinstance(value, list):
            errors.append(f"contract.highway_orders.{name}: chave inexistente {path}#{key}")
            continue
        item_key = spec.get("item_key")
        seq = [v.get(item_key) if isinstance(v, dict) else v for v in value]
        seq = [alias.get(str(v).strip(), str(v).strip()) for v in seq]
        if sorted(seq) != sorted(codes):
            errors.append(f"contract.highway_orders.{name}: {seq} não é permutação de "
                          f"contract.highways {codes}")
    return errors


# --------------------------------------------------------------------------- coerência
def _identity_errors(model: dict[str, Any]) -> list[str]:
    meta = model.get("model", {})
    errors = []
    if meta.get("name") != "G2_REPORT_MODEL":
        errors.append("model.name deve ser G2_REPORT_MODEL")
    if meta.get("status") not in STATUSES:
        errors.append(f"model.status inválido: {meta.get('status')}")
    if meta.get("reference") != REFERENCE:
        errors.append(f"model.reference deve ser {REFERENCE!r}")
    refs = [g for g in meta.get("golden_tests") or [] if g.get("role") == "reference"]
    if len(refs) != 1:
        errors.append(f"model.golden_tests: exatamente um golden 'reference' ({len(refs)})")
    for golden in refs:
        try:
            label = format_report(int(golden.get("report_number")), golden.get("reference_month"))
        except (TypeError, ValueError, KeyError):
            label = repr(golden)
        if label != meta.get("reference"):
            errors.append(f"model.golden_tests: golden 'reference' ({label}) difere de "
                          f"model.reference ({meta.get('reference')})")
    return errors


def _page_errors(model: dict[str, Any], files: _Files) -> list[str]:
    sections = model.get("page", {}).get("sections", [])
    orientations = [s.get("orientation") for s in sections]
    errors = []
    if orientations != ["portrait", "landscape", "portrait"]:
        errors.append(f"orientação das seções deve ser retrato/paisagem/retrato: {orientations}")
    base = files.get(OOXML_BASE)
    if base is None:
        return errors
    base_sections = (base.get("page") or {}).get("sections") or []
    if [s.get("orientation") for s in base_sections] != orientations:
        errors.append(f"{OOXML_BASE}#page/sections: orientação "
                      f"{[s.get('orientation') for s in base_sections]} difere do modelo "
                      f"{orientations}")
        return errors
    twips_per_cm = 1440 / 2.54
    for sec, ox in zip(sections, base_sections, strict=True):
        margins = sec.get("margins_cm") or {}
        pg_mar = ox.get("pgMar") or {}
        for side, cm in margins.items():
            if side in pg_mar and abs(pg_mar[side] / twips_per_cm - float(cm)) > 0.02:
                errors.append(f"{OOXML_BASE}#page/sections/{sec.get('index')}: margem {side} "
                              f"{pg_mar[side] / twips_per_cm:.2f} cm difere do modelo {cm} cm")
    return errors


def _editorial_errors(model: dict[str, Any], files: _Files) -> list[str]:
    defaults = model.get("editorial_defaults") or {}
    errors = []
    nc = defaults.get("nc_enumeration") or {}
    value = str(nc.get("value", ""))
    up_to = re.fullmatch(r"up_to_(\d+)", value)
    emax = nc.get("enumerate_max")
    if value not in NC_POLICIES and not up_to:
        errors.append(f"editorial_defaults.nc_enumeration: valor inválido {value!r}")
    elif up_to and emax != int(up_to.group(1)):
        errors.append(f"editorial_defaults.nc_enumeration: {value} diverge de enumerate_max {emax}")
    elif not up_to and emax is not None:
        errors.append(f"editorial_defaults.nc_enumeration: {value} com enumerate_max {emax} "
                      "(limite só vale para up_to_<N>)")
    match = _REF.fullmatch(str(nc.get("rule", "")).strip())
    if match and match.group(2):
        node = files.node(match.group(1), match.group(2))
        if isinstance(node, dict) and "enumerate_max" in node and node["enumerate_max"] != emax:
            errors.append(f"editorial_defaults.nc_enumeration: enumerate_max {emax} difere de "
                          f"{match.group(1)}#{match.group(2)} ({node['enumerate_max']})")
    s7 = defaults.get("p21_s7_mode") or {}
    if s7.get("value") not in S7_MODES:
        errors.append(f"editorial_defaults.p21_s7_mode: valor inválido {s7.get('value')!r} "
                      f"(esperado {' | '.join(S7_MODES)})")
    themes = files.node(P21_RULES, "render_maps/p24_pa_themes")
    if isinstance(themes, dict) and "mode" in themes:
        errors.append(f"{P21_RULES}#render_maps/p24_pa_themes declara 'mode': o default do S7 é "
                      "único (editorial_defaults.p21_s7_mode)")
    return errors


def _annex_errors(model: dict[str, Any], content: dict[str, Any]) -> list[str]:
    texts = []
    for item in model.get("validations") or []:
        if item.get("id") == "V_ANNEX_COUNT":
            texts.append(("validations.V_ANNEX_COUNT", str(item.get("rule", ""))))
    for comp in model.get("components") or []:
        if comp.get("component_id") == "CLOSING_ANNEX_COUNT":
            texts.append(("CLOSING_ANNEX_COUNT.render", str(comp.get("render", ""))))
    placeholder = ((content.get("placeholders") or {}).get("annex_count") or {}).get("source")
    if content:
        texts.append(("content_blocks placeholders.annex_count", str(placeholder or "")))
    errors = []
    for where, text in texts:
        if "len(index_rows)" not in text or "len(body_rows)" in text:
            errors.append(f"{where}: contagem de anexos deve ser len(index_rows) (DEC-012): "
                          f"{text[:60]!r}")
        elif _ARITH.search(text):
            errors.append(f"{where}: contagem de anexos é len(index_rows) sem aritmética "
                          f"(DEC-012): {text[:60]!r}")
    return errors


def _asset_errors(model: dict[str, Any], manifest: dict[str, dict], root: Path) -> list[str]:
    errors = []
    model_assets = {k: (v or {}) for k, v in (model.get("assets") or {}).items() if k != "manifest"}
    for aid, entry in model_assets.items():
        found = manifest.get(aid)
        if found is None:
            errors.append(f"asset {aid!r} não existe em {ASSETS_MANIFEST}")
            continue
        sha1 = str(found.get("sha1") or "")
        if not _SHA1.match(sha1):
            errors.append(f"asset {aid!r} sem sha1 válido no manifesto")
            continue
        if not entry.get("sha1"):
            errors.append(f"asset {aid!r} sem sha1 no modelo (o builder confere o arquivo)")
        elif entry["sha1"] != sha1:
            errors.append(f"asset {aid!r}: sha1 do modelo difere do manifesto")
        file = root / str(found.get("file") or "")
        if found.get("file") and file.is_file() and \
                hashlib.sha1(file.read_bytes()).hexdigest() != sha1:
            errors.append(f"asset {aid!r}: sha1 do arquivo {found['file']} difere do manifesto")
    return errors


def _human_nodes(node: Any, path: str = ""):
    """(caminho#chave, classes humanas) de todo nó com `class` MANUAL_INPUT/AI_SYNTHESIS."""
    if isinstance(node, dict):
        cls = node.get("class")
        if isinstance(cls, str):
            found = [c for c in HUMAN_CLASSES if c in cls]
            if found and path:
                yield path, found
        for key, value in node.items():
            if _NOT_EMITTED.match(str(key)) or key in ("evidence", "observed"):
                continue
            yield from _human_nodes(value, f"{path}/{key}".strip("/"))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            label = i
            if isinstance(value, dict):
                label = next((value[f] for f in _ID_FIELDS if f in value), i)
            yield from _human_nodes(value, f"{path}/{label}".strip("/"))


def _human_input_errors(model: dict[str, Any], content: dict[str, Any], files: _Files,
                        block_class: dict[str, str]) -> list[str]:
    components = model.get("components") or []
    ids = {c.get("component_id") for c in components}
    inputs = model.get("inputs") or {}
    errors = []
    for name, spec in inputs.items():
        for cid in (spec or {}).get("used_by") or []:
            if cid not in ids:
                errors.append(f"inputs.{name}.used_by: componente inexistente {cid}")
    by_class: dict[str, set[tuple[str, str]]] = {c: set() for c in HUMAN_CLASSES}
    for spec in inputs.values():
        for text in _walk_strings(spec):
            by_class["MANUAL_INPUT"] |= {(p, k) for p, k in _refs_in(text) if k}
    for comp in components:
        cid, cls = comp.get("component_id"), comp.get("automation_class")
        if cls in HUMAN_CLASSES:
            name = comp.get("input")
            if name not in inputs:
                errors.append(f"{cid}: {cls} sem entrada em inputs ({name!r})")
            elif cid not in ((inputs[name] or {}).get("used_by") or []):
                errors.append(f"{cid}: inputs.{name}.used_by não lista o componente")
            for field in _REF_FIELDS:
                if isinstance(comp.get(field), str):
                    by_class[cls] |= {(p, k) for p, k in _refs_in(comp[field]) if k}
        elif comp.get("input"):
            name = comp["input"]
            if name not in inputs or cid not in ((inputs[name] or {}).get("used_by") or []):
                errors.append(f"{cid}: input {name!r} não declarado em inputs com used_by")
    owner_class = {b: c.get("automation_class") for c in components for b in c.get("blocks") or []}
    sources = [(CONTENT_BLOCKS, content), *((p, files.get(p)) for p in DATA_RULE_TEXTS),
               *((p, files.get(p)) for p in sorted({p for refs in by_class.values()
                                                    for p, _ in refs} - set(DATA_RULE_TEXTS)
                                                   - {CONTENT_BLOCKS}))]
    for path, data in sources:
        if not isinstance(data, dict):
            continue
        for node_path, classes in _human_nodes(data):
            block_id = node_path.split("/", 2)[1] if path == CONTENT_BLOCKS and \
                node_path.startswith("blocks/") else None
            if path == CONTENT_BLOCKS and node_path.count("/") <= 1:
                continue                                   # o próprio bloco: ver classe × classe
            for cls in classes:
                if block_id and owner_class.get(block_id) == cls:
                    continue
                key = node_path.split("/", 1)[1] if path == CONTENT_BLOCKS else node_path
                cited = any(p == path and (k == key or k.startswith(key + "/")
                                           or key.endswith("/" + k) or k.endswith("/" + key))
                            for p, k in by_class[cls])
                if not cited:
                    errors.append(f"{path}#{key}: nó {cls} sem entrada em model.inputs nem "
                                  f"componente {cls} que o cite")
    return errors


# --------------------------------------------------------------------------- Gate B tentativa 4
def _walk_nodes(node: Any, path: str = ""):
    """(caminho, dict) de todo mapeamento da árvore; itens de lista rotulados pelo id."""
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from _walk_nodes(value, f"{path}.{key}".strip("."))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            label = i
            if isinstance(value, dict):
                label = next((value[f] for f in _ID_FIELDS if f in value), i)
            yield from _walk_nodes(value, f"{path}[{label}]")


def _evidence_errors(model: dict[str, Any]) -> list[str]:
    """Todo nó do modelo com `confidence` (fora de `components`, que têm checagem própria):
    valor válido; CONFIRMED exige `evidence_months` com ≥ 2 meses distintos; todo
    `evidence_months` dentro de `model.evidence_window`."""
    window = set((model.get("model") or {}).get("evidence_window") or [])
    errors = []
    tree = {k: v for k, v in model.items() if k != "components"}
    for path, node in _walk_nodes(tree):
        conf = node.get("confidence")
        months_raw = [str(m) for m in node.get("evidence_months") or []]
        if isinstance(conf, str):
            if conf not in CONFIDENCES:
                errors.append(f"{path}: confidence inválida {conf!r}")
            elif conf == "CONFIRMED":
                months = {m for m in months_raw if _MONTH.match(m)}
                if len(months) < 2:
                    errors.append(f"{path}: CONFIRMED exige evidence_months com ≥ 2 meses "
                                  f"({sorted(months)})")
        outside = sorted(m for m in months_raw if window and m not in window)
        if outside:
            errors.append(f"{path}: evidence_months fora de model.evidence_window "
                          f"{sorted(window)}: {outside}")
    return errors


ANCHOR_MODES = ("after", "per_item")
ALIGNS = ("left", "center", "right", "both")
LANDSCAPE_WIDTH = ("manifest", "limit_to_usable_area")


def _positioning_errors(model: dict[str, Any], block_ids: set[str], files: _Files) -> list[str]:
    """`positioning`: blocos citados existem no content_blocks, contagem de vazios inteira ≥ 1,
    assets do modelo, modos/alinhamentos do vocabulário do builder (assemble), `ref` da âncora
    = prefixo de uma chave de `config/g2_render_rules.yaml`."""
    pos = model.get("positioning") or {}
    errors = []
    if not block_ids:
        return errors
    for i, rule in enumerate((pos.get("spacers") or {}).get("between") or []):
        where = f"positioning.spacers.between[{i}]"
        for side in ("after", "before"):
            if str(rule.get(side)) not in block_ids:
                errors.append(f"{where}: bloco inexistente em g2_content_blocks ({side}: "
                              f"{rule.get(side)!r})")
        count = rule.get("count", 1)
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            errors.append(f"{where}: count deve ser inteiro ≥ 1 ({count!r})")
    model_assets = {k for k in (model.get("assets") or {}) if k != "manifest"}
    for asset, spec in (pos.get("static_assets") or {}).items():
        if asset not in model_assets:
            errors.append(f"positioning.static_assets.{asset}: asset não registrado no modelo")
        align = (spec or {}).get("align")
        if align is not None and align not in ALIGNS:
            errors.append(f"positioning.static_assets.{asset}: align inválido {align!r} "
                          f"({' | '.join(ALIGNS)})")
    render_keys = list(files.get("config/g2_render_rules.yaml") or {})
    for i, anchor in enumerate((pos.get("visual_anchors") or {}).get("anchors") or []):
        where = f"positioning.visual_anchors.anchors[{i}]"
        if str(anchor.get("block")) not in block_ids:
            errors.append(f"{where}: bloco inexistente em g2_content_blocks "
                          f"({anchor.get('block')!r})")
        if anchor.get("mode") not in ANCHOR_MODES:
            errors.append(f"{where}: modo inválido {anchor.get('mode')!r} "
                          f"({' | '.join(ANCHOR_MODES)})")
        ref = str(anchor.get("ref") or "")
        if render_keys and not (ref and any(k.startswith(ref) for k in render_keys)):
            errors.append(f"{where}: ref {ref!r} não é visual de config/g2_render_rules.yaml")
    width = (pos.get("landscape_width") or {}).get("value")
    if width is not None and width not in LANDSCAPE_WIDTH:
        errors.append(f"positioning.landscape_width: valor inválido {width!r}")
    return errors


def _page_size_errors(model: dict[str, Any], files: _Files) -> list[str]:
    """`ooxml_base` page.sections[].pgSz: paisagem w > h, retrato w < h, e as medidas são as
    de `model.page` (A4) — o builder usa o pgSz, não o rótulo `orientation`."""
    base = files.get(OOXML_BASE)
    if base is None:
        return []
    page = model.get("page") or {}
    twips = sorted(round(float(page[k]) * 1440 / 2.54) for k in ("width_cm", "height_cm")
                   if k in page)
    errors = []
    for sec in (base.get("page") or {}).get("sections") or []:
        size = sec.get("pgSz") or {}
        w, h = size.get("w"), size.get("h")
        where = f"{OOXML_BASE}#page/sections/{sec.get('index')}"
        if not (isinstance(w, int) and isinstance(h, int)):
            errors.append(f"{where}: pgSz sem w/h inteiros")
            continue
        if sec.get("orientation") == "landscape" and not w > h:
            errors.append(f"{where}: orientation landscape com pgSz retrato (w {w} ≤ h {h})")
        if sec.get("orientation") == "portrait" and not w < h:
            errors.append(f"{where}: orientation portrait com pgSz paisagem (w {w} ≥ h {h})")
        if len(twips) == 2 and any(abs(a - b) > 20 for a, b in zip(sorted((w, h)), twips,
                                                                     strict=True)):
            errors.append(f"{where}: pgSz {w}×{h} difere de model.page "
                          f"{page.get('width_cm')}×{page.get('height_cm')} cm")
    return errors


def _duplicate_default_errors(model: dict[str, Any]) -> list[str]:
    """Um default por parâmetro: `editorial_defaults.<x>` não repete um `render_params.<k>` de
    componente (mesma chave ou `<prefixo>_<k>`), mesmo com o mesmo valor."""
    defaults = model.get("editorial_defaults") or {}
    errors = []
    for comp in model.get("components") or []:
        for key in comp.get("render_params") or {}:
            for name in defaults:
                if name == key or name.endswith(f"_{key}"):
                    errors.append(f"default duplicado: editorial_defaults.{name} repete "
                                  f"{comp.get('component_id')}.render_params.{key} (um só default)")
    return errors


def _field_errors(model: dict[str, Any], content: dict[str, Any],
                  blocks: dict[str, dict]) -> list[str]:
    """`fields` de componente = placeholder do content_blocks, entrada de `model.inputs` ou slot
    de um dos blocos do componente."""
    if not content:
        return []
    known = set(content.get("placeholders") or {}) | set(model.get("inputs") or {})
    errors = []
    for comp in model.get("components") or []:
        slots = {s for b in comp.get("blocks") or []
                 for s in ((blocks.get(b) or {}).get("slots") or {})}
        for field in comp.get("fields") or []:
            if field not in known | slots:
                errors.append(f"{comp.get('component_id')}.fields: campo inexistente {field!r} "
                              "(nem placeholder, nem entrada, nem slot dos blocos)")
    return errors


def _review_key_errors(model: dict[str, Any], block_ids: set[str]) -> list[str]:
    """`review_key` (chave de `inputs.ai_review` lida pelo builder) = bloco do content_blocks
    citado pelo `render` do próprio componente."""
    errors = []
    for comp in model.get("components") or []:
        key = comp.get("review_key")
        if key is None:
            continue
        cid = comp.get("component_id")
        if block_ids and str(key) not in block_ids:
            errors.append(f"{cid}.review_key {key!r}: bloco inexistente em g2_content_blocks "
                          "(o builder lê inputs.ai_review[review_key])")
        elif f"#{key}/" not in str(comp.get("render", "")):
            errors.append(f"{cid}.review_key {key!r} não é o bloco citado no render")
    return errors


def _environmental_process_errors(model: dict[str, Any], block_ids: set[str]) -> list[str]:
    contract = model.get("contract") or {}
    spec = contract.get("environmental_processes")
    if spec is None:
        return []
    field = spec.get("field")
    errors = []
    for highway in contract.get("highways") or []:
        if not str(highway.get(field) or "").strip():
            errors.append(f"contract.highways[{highway.get('code')}]: sem {field} "
                          "(contract.environmental_processes)")
    for block_id in spec.get("used_by") or []:
        if block_ids and block_id not in block_ids:
            errors.append(f"contract.environmental_processes.used_by: bloco inexistente {block_id}")
    if not spec.get("provenance") or spec.get("confidence") not in CONFIDENCES:
        errors.append("contract.environmental_processes: exige provenance e confidence")
    return errors


def _deviation_class_errors(content: dict[str, Any], anomalies: list[dict]) -> list[str]:
    """Desvio `kind: ANOMALY` cita anomalia que descreve texto errado: se todas as entradas do
    catálogo para aquele componente forem TRUE_MODEL_CHANGE/METHOD_ERROR, o trecho some da
    varredura (`_anomaly_needles`) e o desvio vira regra escondida."""
    classes: dict[str, set[str]] = {}
    for item in anomalies:
        classes.setdefault(str(item.get("component")), set()).add(str(item.get("classification")))
    errors = []
    for block in content.get("blocks") or []:
        for dev in block.get("deviations") or []:
            if dev.get("kind") != "ANOMALY":
                continue
            ref = _ANOMALY_REF.search(str(dev.get("ref", "")))
            if ref and ref.group(1) in classes and classes[ref.group(1)] <= _NOT_TEXT_DEFECTS:
                errors.append(f"{block.get('block_id')}: desvio ANOMALY {ref.group(1)} "
                              f"classificado só como {sorted(classes[ref.group(1)])} no catálogo "
                              "(não é defeito de texto)")
    return errors


_ARITH = re.compile(r"[-+*/%]\s*len\(index_rows\)|len\(index_rows\)\s*[-+*/%]")
THEME_FORMS = ("label", "lead", "follow", "bare")


def _theme_maps(data: Any, path: str):
    """(caminho, nó) de todo mapa de temas (`themes`: lista de {label, any})."""
    for node_path, node in _walk_nodes(data, path):
        themes = node.get("themes")
        if isinstance(themes, list) and themes and all(
                isinstance(t, dict) and "label" in t and "any" in t for t in themes):
            yield node_path, node


def _thematic_errors(files: _Files) -> list[str]:
    """Afirmação temática sem documento: todo mapa de temas (`themes` com `any`) declara em
    `fills` os textos que ele preenche, e nenhum desses textos traz um tema LITERAL (o tema só
    sai pelo mapa, quando há documento que o sustente — QA-C: S7, PARECERES_MEDICAO/AMB)."""
    errors = []
    for path in DATA_RULE_TEXTS:
        data = files.get(path)
        if not isinstance(data, dict):
            continue
        for node_path, node in _theme_maps(data, path):
            fills = node.get("fills")
            if not isinstance(fills, list) or not fills:
                errors.append(f"{node_path}: mapa de temas sem `fills` (textos que ele preenche)")
                continue
            forms = {str(t[f]).casefold() for t in node["themes"] for f in THEME_FORMS
                     if t.get(f)}
            for ref in fills:
                match = _REF.fullmatch(str(ref).strip())
                if not match or not match.group(2):
                    errors.append(f"{node_path}.fills: referência fora do formato arquivo#chave "
                                  f"{ref!r}")
                    continue
                target = files.node(match.group(1), match.group(2))
                if target is _MISSING:
                    errors.append(f"{node_path}.fills: chave inexistente {ref}")
                    continue
                texts = [target] if isinstance(target, str) else list(
                    _emitted_strings(target, False, _EMITTED_KEYS, _NOT_EMITTED))
                for text in texts:
                    found = sorted(f for f in forms if f in str(text).casefold())
                    if found:
                        errors.append(f"{ref}: afirmação temática sem documento — tema literal "
                                      f"{found[0]!r} (o tema só sai por {node_path})")
    return errors


def _presence_errors(content: dict[str, Any], root: Path) -> list[str]:
    """Toda presença de bloco vira predicado nomeado (`builder.presence.parse_condition`, com o
    fallback de data_rules): presença que não se traduz seria 'presente por padrão' em silêncio
    (revisor W4, MINOR 2)."""
    from prog_g2_report.builder.presence import (
        UntranslatableConditionError,
        load_data_rule_presences,
        parse_condition,
    )

    fallbacks = load_data_rule_presences(Path(root) / "config" / "data_rules")
    errors = []
    for block in content.get("blocks") or []:
        block_id = str(block.get("block_id"))
        match = re.match(r"^P(2\.[1-6])_", block_id)
        presence = " ".join(str(block.get("presence") or "always").split())
        try:
            parse_condition(presence, block_id, match.group(1) if match else None, fallbacks)
        except UntranslatableConditionError:
            errors.append(f"{block_id}: presença não traduzida em predicado (nunca 'presente "
                          f"por padrão'): {presence!r}")
    return errors


_PENDING_HUMAN = "PENDING_HUMAN"


def _external_status_errors(model: dict[str, Any]) -> list[str]:
    """Contrato da entrada humana do P2.2 externo (`render.p22_external`): campo vazio/ausente
    vira PENDING_HUMAN com marcador visível (`schema.empty_value`, `schema.missing_field`) e
    'sem informação' só pelo sentinela com texto padronizado (`schema.no_information.key/text`).
    Tirar o texto ou a chave do sentinela, ou a regra de pendência, reprova (revisor W4, MINOR 3);
    vale para toda entrada cujo schema declare uma dessas chaves."""
    from prog_g2_report.render.p22_external import INPUT_KEY

    errors = []
    inputs = model.get("inputs") or {}
    guarded = ("empty_value", "missing_field", "no_information")
    for name, spec in inputs.items():
        schema = (spec or {}).get("schema") if isinstance(spec, dict) else None
        if name != INPUT_KEY and not (isinstance(schema, dict)
                                      and any(k in schema for k in guarded)):
            continue
        where = f"inputs.{name}.schema"
        if not isinstance(schema, dict):
            errors.append(f"{where}: ausente (o renderizador do P2.2 externo exige o schema)")
            continue
        for key in ("empty_value", "missing_field"):
            if _PENDING_HUMAN not in str(schema.get(key) or ""):
                errors.append(f"{where}.{key}: deve declarar {_PENDING_HUMAN} com marcador "
                              f"visível (o rótulo nunca sai sem valor)")
        info = schema.get("no_information")
        if not isinstance(info, dict):
            errors.append(f"{where}.no_information: sentinela de 'sem informação' ausente")
            continue
        if not re.fullmatch(r"[a-z][a-z0-9_]*", str(info.get("key") or "")):
            errors.append(f"{where}.no_information.key: chave do sentinela ausente ou inválida "
                          f"({info.get('key')!r})")
        if not re.sub(r"[\s;.,:]+", "", str(info.get("text") or "")):
            errors.append(f"{where}.no_information.text: texto padronizado do sentinela vazio "
                          f"(o campo sairia rótulo sem valor)")
        if str(info.get("status", "OK")) != "OK":
            errors.append(f"{where}.no_information.status: declaração humana é OK, não "
                          f"{info.get('status')!r}")
    return errors


# --------------------------------------------------------------------------- validação
def validate_model(
    model: dict[str, Any],
    matrix: list[dict] | None = None,
    anomalies: list[dict] | None = None,
    assets: Any = None,
    content_blocks: dict[str, Any] | None = None,
    root: Path = REPO_ROOT,
) -> list[str]:
    """Devolve a lista de violações. Lista vazia = Gate B estrutural aprovado.

    `assets` substitui o manifesto (`{id: entrada}` ou a lista do YAML); `content_blocks`
    substitui `config/g2_content_blocks.yaml`; `root` é de onde se leem os demais arquivos
    (data_rules, ooxml_base, render rules, manifesto).
    """
    root = Path(root)
    matrix = _jsonl("reproducibility_matrix.jsonl") if matrix is None else matrix
    anomalies = _jsonl("anomalies.jsonl") if anomalies is None else anomalies
    manifest = load_assets_manifest(root / ASSETS_MANIFEST) if assets is None \
        else _manifest_by_id(assets)
    content = load_content_blocks(root / CONTENT_BLOCKS) if content_blocks is None \
        else content_blocks
    files = _Files(root)
    files.put(CONTENT_BLOCKS, content)
    pending = _pending_paths(model)
    errors: list[str] = _identity_errors(model) + _page_errors(model, files)

    products = {p.get("code") for p in model.get("products", [])}
    missing = {f"2.{i}" for i in range(1, 7)} - products
    if missing:
        errors.append(f"produtos ausentes: {sorted(missing)}")

    components = model.get("components", [])
    ids = [c.get("component_id") for c in components]
    duplicated = {i for i in ids if ids.count(i) > 1}
    if duplicated:
        errors.append(f"component_id duplicado: {sorted(duplicated)}")
    all_sources = model.get("sources") or {}
    not_sources = {str(n.get("name")) for n in all_sources.get("not_sources") or []
                   if isinstance(n, dict)}
    sources = (set(all_sources) - {"not_sources"} - not_sources) | {"contract"}
    window = set((model.get("model") or {}).get("evidence_window") or [])
    anomaly_ids = {a.get("component") for a in anomalies if a.get("component")}
    anomaly_rx = re.compile(
        r"(?<![\w.])(" + "|".join(re.escape(a) for a in sorted(anomaly_ids, key=len, reverse=True))
        + r")(?![\w])") if anomaly_ids else None
    content_list = content.get("blocks") or []
    blocks = {b.get("block_id"): b for b in content_list}
    block_class = {bid: str(b.get("class")) for bid, b in blocks.items()}

    errors += _asset_errors(model, manifest, root)
    model_assets = {k for k in (model.get("assets") or {}) if k != "manifest"}

    block_owner: dict[str, list[str]] = {}
    for comp in components:
        cid = comp.get("component_id") or "<sem id>"
        if not _ID.match(cid):
            errors.append(f"{cid}: component_id fora do padrão")
        cls = comp.get("automation_class")
        if cls not in CLASSES:
            errors.append(f"{cid}: automation_class inválida {cls!r}")
        conf = comp.get("confidence")
        if conf not in CONFIDENCES:
            errors.append(f"{cid}: confidence inválida {conf!r}")
        months_raw = [str(m) for m in comp.get("evidence_months") or []]
        if conf == "CONFIRMED":
            months = {m for m in months_raw if _MONTH.match(m)}
            if len(months) < 2:
                errors.append(f"{cid}: CONFIRMED exige evidence_months com ≥ 2 meses "
                              f"({sorted(months)})")
        outside = sorted(m for m in months_raw if window and m not in window)
        if outside:
            errors.append(f"{cid}: evidence_months fora de model.evidence_window "
                          f"{sorted(window)}: {outside}")
        provenance = comp.get("provenance") or []
        if not provenance:
            errors.append(f"{cid}: sem provenance")
        cited = set()
        for p in provenance:
            p = str(p)
            if p.removeprefix("anomaly:") in anomaly_ids:
                cited.add(p.removeprefix("anomaly:"))
            elif anomaly_rx:
                cited |= set(anomaly_rx.findall(p))
        if cited:
            errors.append(f"{cid}: anomalia histórica citada como regra: {sorted(cited)}")
        comp_assets = comp.get("assets") or ([comp["asset"]] if "asset" in comp else [])
        if cls == "STATIC_ASSET" and not comp_assets:
            errors.append(f"{cid}: STATIC_ASSET sem asset registrado (None)")
        for asset in comp_assets:
            if not asset or asset not in model_assets or asset not in manifest:
                errors.append(f"{cid}: STATIC_ASSET sem asset registrado ({asset!r})"
                              if cls == "STATIC_ASSET" else
                              f"{cid}: asset não registrado no modelo e no manifesto ({asset!r})")
        if cls == "STRUCTURED_DATA" and not comp.get("source"):
            errors.append(f"{cid}: STRUCTURED_DATA sem source")
        if comp.get("source") and comp["source"] not in sources:
            errors.append(f"{cid}: source {comp['source']!r} não declarada em sources "
                          "(não-fontes não contam)")
        render = comp.get("render")
        if cls == "RECONSTRUCTED_VISUAL" and not (comp.get("source") and render):
            errors.append(f"{cid}: RECONSTRUCTED_VISUAL precisa de source e render")
        elif cls == "RECONSTRUCTED_VISUAL" and not any(k for _, k in _refs_in(str(render))):
            errors.append(f"{cid}: RECONSTRUCTED_VISUAL com render sem referência arquivo#chave")
        has_content = comp.get("fields") or comp.get("blocks") or comp.get("source")
        if cls == "TEMPLATE" and not has_content:
            errors.append(f"{cid}: TEMPLATE sem fields, blocks ou source")
        if cls == "AI_SYNTHESIS" and not (comp.get("allowed_sources")
                                          and comp.get("human_review") is True):
            errors.append(f"{cid}: AI_SYNTHESIS precisa de allowed_sources e human_review: true")
        if comp.get("product") and comp["product"] not in products:
            errors.append(f"{cid}: produto {comp['product']!r} não declarado")
        for field in _REF_FIELDS:
            value = comp.get(field)
            if not isinstance(value, str):
                continue
            if _OLD_REF.search(value):
                errors.append(f"{cid}.{field}: referência fora do formato arquivo#chave: {value!r}")
            if _VAGUE.search(value):
                errors.append(f"{cid}.{field}: texto vago, sem regra: {value!r}")
            for path, key in _refs_in(value):
                if key is None:
                    errors.append(f"{cid}.{field}: referência a {path} sem #chave")
        for block_id in comp.get("blocks") or []:
            block_owner.setdefault(block_id, []).append(cid)
            bcls = block_class.get(block_id)
            if bcls in HUMAN_CLASSES and cls != bcls:
                errors.append(f"{cid}: bloco {bcls} {block_id} em componente {cls} "
                              f"(exige componente {bcls})")
            elif cls in HUMAN_CLASSES and bcls and bcls != cls:
                errors.append(f"{cid}: componente {cls} com bloco {bcls} {block_id}")
        errors += _confidence_errors(comp, blocks, files)

    for item in model.get("discontinued", []):
        for block_id in item.get("blocks") or []:
            block_owner.setdefault(block_id, []).append(f"discontinued:{item.get('component_id')}")

    # blocos do content_blocks × componentes
    content_ids = [b.get("block_id") for b in content_list]
    if content and not content_ids:
        errors.append(f"{CONTENT_BLOCKS} sem blocos")
    if content_ids:
        for block_id, count in Counter(content_ids).items():
            if count > 1:
                errors.append(f"bloco repetido em g2_content_blocks: {block_id}")
        known = set(content_ids)
        for block_id, owners in block_owner.items():
            if block_id not in known:
                errors.append(f"{owners[0]}: bloco inexistente em g2_content_blocks: {block_id}")
            if len(owners) > 1:
                errors.append(f"bloco {block_id} em mais de um componente: {owners}")
        for block_id in content_ids:
            if block_id not in block_owner:
                errors.append(f"bloco sem componente (nem FIXED_BODY_TEXT nem discontinued): "
                              f"{block_id}")
        for product in model.get("products", []):
            if product.get("title_source") == "content_blocks" and \
                    f"P{product.get('code')}_TITLE" not in known:
                errors.append(f"produto {product.get('code')}: sem bloco de título "
                              f"P{product.get('code')}_TITLE em g2_content_blocks")
        for block in content_list:
            for dev in block.get("deviations") or []:
                if dev.get("kind") != "ANOMALY":
                    continue
                ref = _ANOMALY_REF.search(str(dev.get("ref", "")))
                if not ref or ref.group(1) not in anomaly_ids:
                    errors.append(f"{block.get('block_id')}: desvio ANOMALY sem anomalia do "
                                  f"catálogo: {dev.get('ref')!r}")

    # referências arquivo#chave em todo o modelo e nos blocos de conteúdo
    for label, tree in (("modelo", model), ("content_blocks", content)):
        for text in _walk_strings(tree):
            if label == "modelo" and _OLD_REF.search(text):
                errors.append(f"{label}: referência fora do formato arquivo#chave: {text[:60]!r}")
            for path, key in _refs_in(text):
                errors += _check_ref(path, key, files, pending, label)
    errors += _highway_errors(model, files, pending)
    errors += _editorial_errors(model, files)
    errors += _annex_errors(model, content)
    errors += _human_input_errors(model, content, files, block_class)
    known_blocks = set(blocks) - {None}
    errors += _evidence_errors(model)
    errors += _positioning_errors(model, known_blocks, files)
    errors += _page_size_errors(model, files)
    errors += _duplicate_default_errors(model)
    errors += _field_errors(model, content, blocks)
    errors += _review_key_errors(model, known_blocks)
    errors += _environmental_process_errors(model, known_blocks)
    errors += _deviation_class_errors(content, anomalies)
    errors += _thematic_errors(files)
    errors += _presence_errors(content, root)
    errors += _external_status_errors(model)

    discontinued = {d.get("component_id") for d in model.get("discontinued", [])}
    covered = set(ids) | discontinued | set(model.get("merged_into", {}).keys())
    for row in matrix:
        if row.get("component_id") not in covered:
            errors.append(f"componente da matriz fora do modelo: {row.get('component_id')}")

    rules = {path: files.get(path) for path in DATA_RULE_TEXTS}
    texts = emitted_texts(content, rules, model, files.get(OOXML_BASE))
    errors += _anomaly_text_errors(texts, anomalies)
    allowed, literal_errors = _allowed_literals(model, content)
    errors += literal_errors + _hardcode_errors(texts, allowed)

    for text in [*_walk_strings(model), *_walk_strings(content),
                 *(t for data in rules.values() for t in _walk_strings(data))]:
        if _RM.search(text):
            errors.append(f"sigla RM usada como identificador: {text[:60]!r}")
    return list(dict.fromkeys(errors))
