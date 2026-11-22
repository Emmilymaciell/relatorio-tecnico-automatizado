"""Comparador do golden test: fatos do PDF de referência x fatos do PDF gerado.

Entrada: dois dicts de `prog_g2_report.qa.extract.extract_facts` e um `AllowanceSet` CONGELADO
(`config/golden_allowances.yaml`). Saída: `Report` com diferenças classificadas, métricas por
dimensão e veredito — nunca só um score (PHASES.md, Metas de QA).

Dimensões e severidades:

    STRUCTURAL       páginas (±tolerância), tamanho, orientação (sequência de blocos e
                     comprimento de cada bloco), sequência e página dos títulos, cabeçalho,
                     rodapé, numeração impressa
    CONTENT          códigos do Controle de Produtos por bloco e na ordem (100%), rótulos das
                     colunas, a LINHA inteira de cada código (manifestação, descrição, rodovia,
                     data, status), códigos citados no texto, número e mês (capa, Apresentação,
                     Encerramento), rodovias, contagens declaradas e coerência interna; por
                     seção da narrativa: presença, fatos citados (números, datas, horas, meses,
                     rodovias) como multiconjunto ordenado, cobertura do texto e maior trecho
                     da referência ausente no gerado; por figura raster: painel em branco,
                     semelhança com a referência, rodovia da legenda e selo do painel trocado
    VISUAL_GEOMETRY  figuras por âncora de título e tipo (raster/vetorial), bbox em cm,
                     fontes da capa

    CRITICAL  fato errado ou ordem estrutural quebrada (reprova)
    MAJOR     estrutura/apresentação divergente além da tolerância (reprova)
    MINOR     desvio pequeno; não reprova sozinho, mas baixa o score da sua dimensão
    ALLOWED   casou com uma allowance explícita, que cita anomalia catalogada ou DEC

Veredito PASS = nenhuma CRITICAL/MAJOR não permitida, acurácia de conteúdo 100% e score
estrutural >= `tolerances.structural_score_min`. Duas verificações nunca são permitidas:
`expected_report_number` (o gerado diz o número pedido) e `internal_consistency` (o gerado
concorda consigo mesmo: páginas e anexos declarados, mês da Apresentação x Encerramento).

A acurácia de conteúdo conta unidades: uma por linha do Controle de Produtos, uma por seção
para fatos/cobertura/semelhança, uma por figura raster para conteúdo e identidade, além das
verificações de identidade. Só `cover_date_text` (grafia) fica fora.

O que NÃO é verificável sem OCR: o texto dentro de figuras raster. A identidade de um painel
(rodovia) é conferida pelo casamento deslizante do selo da referência dentro do painel gerado;
só conclui "trocado" quando o selo de OUTRO painel da referência casa claramente melhor. Se
nenhum selo discrimina (painéis sem selo, fundo diferente), o painel fica "não verificável"
nas métricas — nunca aprovado nem reprovado por isso.

v3.0 (QA2-E: 19 mutações de conteúdo passavam no 2.0):
  - fatos da narrativa com status (vocabulário fechado, qualificado pelo campo), negação,
    ordinais, cardinais por extenso, dias da semana e executoras do contrato; cada diferença diz
    o bloco de rodovia em que está (`context.block`);
  - cobertura por PARÁGRAFO (`paragraph_coverage`: parágrafo da referência sem correspondente
    no gerado = MAJOR) e parágrafo duplicado no gerado (`paragraph_duplicate`, MAJOR);
  - signatário do Encerramento por hash (`signatory`, CRITICAL; o nome não entra no relatório);
  - figuras raster por REGIÃO (`raster_regions.yaml`): aba de rodovia destacada (seletor) e
    grade de tinta para painel trocado (CRITICAL); delta de tinta em regiões de texto/numerais
    calibradas (`figure_region`, MAJOR). Troca de 1 dígito fica no limiar ou abaixo do ruído
    legítimo na maioria das regiões e as tabelas dos quadros não são verificáveis: esses
    valores são cobertos pelo QA de fonte, não por este comparador;
  - allowance com `pending_decision: true` é recusada; a que cita a DEC que decidiu leva
    `reference: {anomaly: ..., dec: DEC-NNN}`; `max_vertical_delta_cm` prende o desvio vertical
    das allowances de geometria;
  - `narrative_facts` pode ser permitida por item exato (`match.items`: tipo, bloco, fato) ou
    por par (`match.pairs`: bloco, fato da referência, fato do gerado, emparelhados pelo
    comparador no mesmo bloco e campo). Cada item cobre uma diferença só, e a lista é tudo ou
    nada: usada em parte vira CRITICAL (`kind: incomplete`).
  - (allowances v1.8, extrator 3.1) fato `order` = o mesmo fato deslocado DENTRO do mesmo bloco
    de rodovia; o que sai de um bloco e aparece em outro é falta + sobra (e pode virar par).

v4.0 (QA3-E: 13 mutações de texto passavam no 3.0 — status fora do vocabulário,
quantificadores, verbos de estado, item curto apagado, sumário):
  - DIFF DE TEXTO ESTRITO (`prog_g2_report.qa.textdiff`): cada seção (inclusive CAPA e
    SUMARIO), os títulos e cada bloco do Controle de Produtos são comparados token a token,
    normalizados só no leiaute (espaços, hífen de fim de linha, aspas/travessões; caixa
    preservada). Cada trecho divergente é um hunk `text_diff` CRITICAL, salvo se estiver no
    conjunto CONGELADO de hunks aprovados (`docs/qa/approved_hunks/nNN.yaml`, registrado com
    sha256 nas allowances), cada um com a anomalia catalogada ou a DEC que o justifica. Nenhuma
    allowance cobre `text_diff`: só um hunk aprovado, exato (unidade, âncora do parágrafo,
    contexto de 6 tokens dos dois lados, textos de referência e gerado);
  - hunk aprovado que não ocorre = "aprovação órfã" (aviso); hunk aprovado com `pending`
    espera um texto que o builder ainda não emite: o hunk real no mesmo parágrafo sai
    CRITICAL marcado como pendente;
  - as verificações v3 de conteúdo derivadas do texto (fatos, cobertura, códigos, identidade,
    linhas do Controle de Produtos) continuam como diagnóstico redundante: uma diferença v3
    numa unidade de texto cujos hunks são TODOS aprovados é consequência deles e sai ALLOWED
    (`hunks:<unidade>`); com qualquer hunk não aprovado na unidade ela continua bloqueante;
  - `toc_consistency` (nunca permitível): cada linha do sumário do gerado tem o título e a
    página do título do próprio corpo, na ordem.

v4.1 (QA4-E: a ressalva da DUP movida da RD-103 para a RD-102A passava — a âncora era o hash
do parágrafo, idêntico nas 3 rodovias, e `_cover_by_hunks` rebaixava os `narrative_facts` que
acusavam a troca):
  - a âncora do hunk é POSICIONAL (`prog_g2_report.qa.textdiff`): bloco estrutural do parágrafo
    de referência (rodovia > grupo no 2.2, rodovia nas listas do 2.4, código da linha no
    Controle de Produtos), índice do parágrafo no bloco, intervalo de tokens na referência e
    bloco do parágrafo gerado, além do hash e do contexto. Um hunk aprovado só cobre a
    diferença no mesmo lugar; `occurrence` deixa de existir (a posição já distingue);
  - o hunk "revertido" (o gerado voltou ao texto publicado) é procurado só no bloco do hunk;
  - as diferenças v3 localizáveis numa seção (`narrative_facts`, `text_codes`, `roads`,
    `paragraph_coverage`, `paragraph_duplicate`) NÃO são mais cobertas pela seção inteira:
    cada uma é julgada pelo seu próprio hunk — sai ALLOWED só se um grupo de parágrafos ligado
    a hunks aprovados (sem hunk em aberto; `textdiff.paragraph_groups`) a explicar
    exatamente, e o fato de status por rodovia/grupo exige o MESMO bloco. Um hunk em aberto
    não derruba mais as outras diferenças da seção, e uma seção toda aprovada não cobre fato
    de outro bloco;
  - allowances do comparador 4.0 são aceitas com aviso, mas sem hunks aprovados (o formato
    antigo, sem posição, não é mais aceito);
  - `text_visibility` (extrator 3.2): palavra extraível sem tinta visível no gerado
    (branqueada ou coberta) é CRITICAL — o diff de texto lê o que o leitor não vê.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import yaml

from prog_g2_report.qa.extract import (
    COVER_KEY,
    NARRATIVE_EXCLUDED_SECTIONS,
    PRODUCT_CONTROL_FIELDS,
    fold,
    mask_facts,
    narrative_facts,
    section_masks,
    text_codes,
)
from prog_g2_report.qa.textdiff import (
    CONTEXT_TOKENS,
    Hunk,
    TextUnit,
    diff_unit,
    normalize_strict,
    paragraph_groups,
    text_units,
    toc_entries,
)
from prog_g2_report.report_id import strip_accents

COMPARATOR_VERSION = "4.1"
# Versões de allowances aceitas com aviso. As da v1/v2/v3 continuam válidas para as
# verificações que já existiam (mesmo nome e semântica), mas não cobrem as verificações novas —
# e (v4) não registram hunks aprovados: todo trecho de texto divergente sai CRITICAL. As da
# v4.0 registravam hunks sem posição (QA4-E): aceitas só sem `approved_hunks`.
LEGACY_ALLOWANCE_VERSIONS = frozenset({"1.0", "2.0", "3.0", "4.0"})

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ALLOWANCES = REPO_ROOT / "config" / "golden_allowances.yaml"
DEFAULT_HUNKS_DIR = REPO_ROOT / "docs" / "qa" / "approved_hunks"
DEFAULT_ANOMALIES = REPO_ROOT / "data" / "catalog" / "anomalies.jsonl"
DEFAULT_DECISIONS = REPO_ROOT / "docs" / "decisions"
DEFAULT_RASTER_REGIONS = Path(__file__).resolve().parent / "raster_regions.yaml"

STRUCTURAL = "STRUCTURAL"
CONTENT = "CONTENT"
VISUAL_GEOMETRY = "VISUAL_GEOMETRY"
DIMENSIONS = (STRUCTURAL, CONTENT, VISUAL_GEOMETRY)

CRITICAL = "CRITICAL"
MAJOR = "MAJOR"
MINOR = "MINOR"
ALLOWED = "ALLOWED"

# Conjunto fechado de verificações -> dimensão. Allowance com `check` fora daqui é inválida.
CHECKS: dict[str, str] = {
    "page_count": STRUCTURAL,
    "page_size": STRUCTURAL,
    "orientation_runs": STRUCTURAL,
    "orientation_run_length": STRUCTURAL,
    "heading_sequence": STRUCTURAL,
    "heading_text": STRUCTURAL,
    "heading_page": STRUCTURAL,
    "header_text": STRUCTURAL,
    "footer_text": STRUCTURAL,
    "page_number": STRUCTURAL,
    "product_control_blocks": CONTENT,
    "product_control_codes": CONTENT,
    "product_control_labels": CONTENT,
    "text_codes": CONTENT,
    "report_number": CONTENT,
    "expected_report_number": CONTENT,
    "reference_month": CONTENT,
    "roads": CONTENT,
    "declared_pages": CONTENT,
    "declared_annexes": CONTENT,
    "declared_words": CONTENT,
    "internal_consistency": CONTENT,
    "cover_date": CONTENT,
    "cover_date_text": CONTENT,
    "signature_date": CONTENT,
    "narrative_similarity": CONTENT,
    # v2.0
    "product_control_rows": CONTENT,
    "section_presence": CONTENT,
    "narrative_facts": CONTENT,
    "narrative_coverage": CONTENT,
    "figure_content": CONTENT,
    "figure_identity": CONTENT,
    "figure_count": VISUAL_GEOMETRY,
    "figure_bbox": VISUAL_GEOMETRY,
    "cover_fonts": VISUAL_GEOMETRY,
    # v3.0
    "paragraph_coverage": CONTENT,
    "paragraph_duplicate": CONTENT,
    "signatory": CONTENT,
    "figure_region": CONTENT,
    # v4.0
    "text_diff": CONTENT,
    "toc_consistency": CONTENT,
    # v4.1
    "text_visibility": CONTENT,
}
# `text_diff` só sai ALLOWED por hunk aprovado (nunca por allowance); `toc_consistency` é o
# gerado contra ele mesmo, como `internal_consistency`.
NON_ALLOWABLE = frozenset({"expected_report_number", "internal_consistency", "text_diff",
                           "toc_consistency"})
# v4.0 — verificações v3 de CONTEÚDO derivadas do texto: numa unidade de texto com todos os
# hunks aprovados, a diferença é consequência deles (diagnóstico redundante, ALLOWED). As de
# figura (conteúdo raster) e as não permitíveis ficam fora.
TEXT_DERIVED_CHECKS = frozenset({
    "product_control_blocks", "product_control_codes", "product_control_labels",
    "product_control_rows", "text_codes", "report_number", "reference_month", "roads",
    "declared_pages", "declared_annexes", "declared_words", "cover_date", "cover_date_text",
    "signature_date", "narrative_similarity", "section_presence", "narrative_facts",
    "narrative_coverage", "paragraph_coverage", "paragraph_duplicate", "signatory",
})
# v4.1 — as que se localizam em parágrafos de uma seção: julgadas pelo próprio hunk/fato
# (`_Comparator._explained_local`), nunca pela seção inteira.
LOCALIZED_CHECKS = frozenset({"narrative_facts", "text_codes", "roads", "paragraph_coverage",
                              "paragraph_duplicate"})
# Verificações só diagnósticas: entram nas métricas, não na acurácia de conteúdo.
UNSCORED = frozenset({"cover_date_text"})
# A capa é comparada pela identidade (número, data) e tem composição nova (DEC-011): suas
# figuras não entram na comparação de conteúdo.
FIGURE_CONTENT_EXCLUDED_ANCHORS = frozenset({COVER_KEY})

MATCH_KEYS = frozenset({
    "kind", "kinds", "value", "values", "value_regex", "reference", "generated",
    "generated_regex", "reference_sequence", "generated_sequence", "max_abs_delta",
    "figure_kind", "max_width_delta_cm", "field", "max_vertical_delta_cm", "items", "pairs",
})
# v3.0 — itens exatos de `narrative_facts`: cada item cobre UMA diferença (consumido no uso).
ITEM_KEYS = frozenset({"kind", "block", "value"})
PAIR_KEYS = frozenset({"block", "reference", "generated"})
ITEM_KINDS = frozenset({"missing", "extra", "order"})
DEFAULT_TOLERANCES = {
    "page_count_delta": 0,
    "heading_page_shift": 1,
    "bbox_cm": 0.5,
    "structural_score_min": 0.95,
    "narrative_similarity_min": 0.90,
    # v2.0 — calibradas no par real nº 14 (gerado do main x publicado), ver testes `golden`.
    # Cobertura: fração das palavras da referência achadas, em ordem, no gerado (controle:
    # mínimo 0,959). Maior lacuna: maior trecho contínuo da referência ausente no gerado
    # (controle: 14 palavras; a página de texto mais curta do nº 14 tem ~85).
    "narrative_coverage_min": 0.90,
    "narrative_gap_max_words": 40,
    # Figura raster: desvio-padrão da miniatura abaixo disto = painel em branco (controle: 15,6
    # o menor); correlação da miniatura com a referência abaixo disto = outro conteúdo
    # (controle: 0,63 o menor, quadro reconstruído da RD-102A).
    "figure_blank_std": 3.0,
    "figure_similarity_min": 0.40,
    # Selo: o painel é "trocado" quando o selo de outro painel da referência casa com pelo
    # menos `figure_identity_min` e supera o do próprio par por `figure_identity_margin`
    # (controle 2.2.2: próprio 0,94–0,97, outros <= 0,81).
    "figure_identity_min": 0.90,
    "figure_identity_margin": 0.08,
    # v3.0 — calibradas no par real nº 14 (14_v4 x publicado) e conferidas no nº 13 (13_main).
    # Parágrafo: fração das palavras de um parágrafo da referência achadas, em ordem, no
    # parágrafo correspondente do gerado (ou na região alinhada); parágrafos com menos de
    # `paragraph_min_words` palavras ficam só nos fatos (um rótulo "A) RD-103:" casa em qualquer
    # lugar). Duplicado: mesmo texto (com fatos) mais vezes no gerado que na referência.
    "paragraph_coverage_min": 0.60,
    "paragraph_min_words": 5,
    # Grade de tinta 12 colunas: o painel é "trocado" quando outro painel da referência fica
    # mais perto que o próprio par por esta margem (controle 2.1.2: próprio 0,000, outros
    # >= 0,062; 2.2.2/2.4.2: próprio e outros a <= 0,02 um do outro, não discrimina).
    "figure_grid_columns": 12,
    "figure_grid_margin": 0.03,
}
_WILDCARD = re.compile(r"[*?\[\]]")
_ANOMALY_REPORT = re.compile(r"n[ºo°]\s*(\d+)", re.IGNORECASE)


class AllowanceError(ValueError):
    """Arquivo de allowances inválido: genérico, sem referência ou não congelado."""


# --------------------------------------------------------------------------- allowances


@dataclass(frozen=True)
class Allowance:
    id: str
    report_number: int
    reference: dict
    dimension: str
    check: str
    scopes: tuple[str, ...]
    match: dict
    rationale: str = ""

    @property
    def reference_label(self) -> str:
        if "anomaly" in self.reference:
            dec = f" ({self.reference['dec']})" if "dec" in self.reference else ""
            return f"anomalia {self.reference['anomaly']}{dec}"
        return self.reference["dec"]

    def matches(self, diff: Difference, report_number: int | None) -> bool:
        if report_number != self.report_number:
            return False
        if diff.dimension != self.dimension or diff.check != self.check:
            return False
        if diff.scope not in self.scopes:
            return False
        m = self.match
        if "kind" in m and diff.kind != m["kind"]:
            return False
        if "kinds" in m and diff.kind not in m["kinds"]:
            return False
        if "value" in m and diff.value != m["value"]:
            return False
        if "values" in m and diff.value not in m["values"]:
            return False
        if "value_regex" in m and not re.fullmatch(m["value_regex"], str(diff.value)):
            return False
        if "reference" in m and diff.reference != m["reference"]:
            return False
        if "generated" in m and diff.generated != m["generated"]:
            return False
        if "generated_regex" in m and not re.fullmatch(m["generated_regex"], str(diff.generated)):
            return False
        for key in ("reference_sequence", "generated_sequence"):
            if key in m and diff.context.get(key) != m[key]:
                return False
        if "max_abs_delta" in m:
            ref, gen = diff.reference, diff.generated
            if not isinstance(ref, int | float) or not isinstance(gen, int | float):
                return False
            if abs(gen - ref) > m["max_abs_delta"]:
                return False
        if "figure_kind" in m and diff.context.get("figure_kind") != m["figure_kind"]:
            return False
        if "field" in m and diff.context.get("field") != m["field"]:
            return False
        if "max_width_delta_cm" in m:
            horizontal = diff.context.get("horizontal_delta_cm")
            if horizontal is None or horizontal > m["max_width_delta_cm"]:
                return False
        if "max_vertical_delta_cm" in m:
            vertical = diff.context.get("vertical_delta_cm")
            if vertical is None or vertical > m["max_vertical_delta_cm"]:
                return False
        return True

    def claim(self, diff: Difference, claimed: set) -> bool:
        """`items`/`pairs` (v3.0): a diferença tem de ser um item ainda livre da lista —
        (tipo, bloco de rodovia, fato) ou o lado de um par (bloco, fato da referência, fato do
        gerado) que o comparador emparelhou. Sem itens nem pares, nada a consumir."""
        m = self.match
        if "items" not in m and "pairs" not in m:
            return True
        block = diff.context.get("block", "")
        for n, item in enumerate(m.get("items") or []):
            if (("item", n) not in claimed and item["kind"] == diff.kind
                    and item["block"] == block and item["value"] == diff.value):
                claimed.add(("item", n))
                return True
        partner = diff.context.get("paired_with")
        for n, pair in enumerate(m.get("pairs") or []):
            if pair["block"] != block or partner is None:
                continue
            if diff.kind == "missing" and (pair["reference"], pair["generated"]) == (
                    diff.value, partner):
                side = "reference"
            elif diff.kind == "extra" and (pair["generated"], pair["reference"]) == (
                    diff.value, partner):
                side = "generated"
            else:
                continue
            if ("pair", n, side) not in claimed:
                claimed.add(("pair", n, side))
                return True
        return False


@dataclass(frozen=True)
class AllowanceSet:
    status: str
    version: str
    comparator_version: str
    frozen_on: str
    tolerances: dict
    allowances: tuple[Allowance, ...]
    pending: tuple[dict, ...] = ()
    sha256: str | None = None
    source: str | None = None
    warnings: tuple[str, ...] = ()
    # v4.0: conjuntos de hunks aprovados registrados: (nº do relatório, arquivo, sha256)
    hunk_files: tuple[tuple[int, str, str], ...] = ()

    def for_report(self, report_number: int | None) -> list[Allowance]:
        return [a for a in self.allowances if a.report_number == report_number]

    def approved_hunks(self, report_number: int | None, *,
                       anomalies_path: Path | None = DEFAULT_ANOMALIES,
                       decision_dirs: list[Path] | None = None) -> HunkSet:
        """Conjunto de hunks aprovados registrado para o relatório (sha256 conferido), ou o
        conjunto vazio (todo hunk sai CRITICAL)."""
        for number, file, sha256 in self.hunk_files:
            if number == report_number:
                path = Path(file)
                return load_approved_hunks(path if path.is_absolute() else REPO_ROOT / path,
                                           expected_sha256=sha256, anomalies_path=anomalies_path,
                                           decision_dirs=decision_dirs)
        return HunkSet.empty(report_number)

    def hunk_sha256(self, report_number: int | None) -> str | None:
        """sha256 registrado nestas allowances para o conjunto de hunks do relatório."""
        return next((sha for number, _, sha in self.hunk_files if number == report_number),
                    None)

    def load_hunks_file(self, path: Path | str, report_number: int | None, *,
                        anomalies_path: Path | None = DEFAULT_ANOMALIES,
                        decision_dirs: list[Path] | None = None) -> HunkSet:
        """Conjunto de hunks dado por caminho (CLI `--approved-hunks`), aceito SÓ se o sha256
        for o registrado nestas allowances para o relatório: outro arquivo, ou o mesmo
        editado, é recusado (QA4-E). Sem registro para o relatório também é recusado."""
        expected = self.hunk_sha256(report_number)
        if expected is None:
            raise AllowanceError(
                f"--approved-hunks: as allowances {self.version} não registram hunks aprovados "
                f"para o nº {report_number}; registre o sha256 em approved_hunks")
        return load_approved_hunks(path, expected_sha256=expected, anomalies_path=anomalies_path,
                                   decision_dirs=decision_dirs)

    @classmethod
    def empty(cls, tolerances: dict | None = None) -> AllowanceSet:
        return cls("FROZEN", "0", COMPARATOR_VERSION, "", {**DEFAULT_TOLERANCES,
                                                          **(tolerances or {})}, ())


def _known_anomalies(path: Path) -> set[tuple[int, str]]:
    known: set[tuple[int, str]] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        match = _ANOMALY_REPORT.search(record.get("report_id", ""))
        if match:
            known.add((int(match.group(1)), record["component"]))
    return known


def default_decision_dirs() -> list[Path]:
    """`docs/decisions` deste checkout; num worktree (`.claude/worktrees/<x>`), também o do
    checkout principal, onde DECs recém-registrados podem ainda não estar no commit base."""
    dirs = [DEFAULT_DECISIONS]
    parts = REPO_ROOT.parts
    for i in range(len(parts) - 1):
        if parts[i] == ".claude" and parts[i + 1] == "worktrees":
            dirs.append(Path(*parts[:i]) / "docs" / "decisions")
            break
    return dirs


def _decision_exists(dec: str, dirs: list[Path]) -> bool:
    return any(d.is_dir() and any(d.glob(f"{dec}-*.md")) for d in dirs)


def parse_allowances(
    data: dict,
    *,
    anomalies_path: Path | None = DEFAULT_ANOMALIES,
    decision_dirs: list[Path] | None = None,
    sha256: str | None = None,
    source: str | None = None,
) -> AllowanceSet:
    """Valida e congela o conteúdo de um arquivo de allowances.

    Recusa: status diferente de FROZEN, versão do comparador diferente, `check` desconhecido
    ou não permitível, dimensão incoerente, escopo vazio ou curinga, `match` vazio ou com
    chave desconhecida, referência sem anomalia catalogada (para o mesmo relatório) nem DEC
    existente, e (v3.0) `pending_decision: true`: decisão pendente não é desvio permitido. Se
    a decisão já foi tomada, a allowance cita a DEC (`reference: {anomaly: X, dec: DEC-NNN}`
    ou só `dec`) e a flag sai.
    """
    if data.get("status") != "FROZEN":
        raise AllowanceError("allowances precisam estar CONGELADAS (status: FROZEN)")
    version = str(data.get("comparator_version"))
    warnings: list[str] = []
    if version in LEGACY_ALLOWANCE_VERSIONS:
        warnings.append(
            f"allowances congeladas para o comparador {version}; este é {COMPARATOR_VERSION}: "
            "valem para as verificações antigas, mas não cobrem as novas (v2: linhas do "
            "Controle de Produtos, fatos e cobertura da narrativa, conteúdo e identidade de "
            "figuras; v3: status/negação/extenso nos fatos, parágrafos, signatário, regiões "
            "dos painéis; v4: diff de texto estrito, sem hunks aprovados registrados; v4.1: "
            "âncora posicional dos hunks)"
        )
    elif version != COMPARATOR_VERSION:
        raise AllowanceError(
            f"allowances congeladas para o comparador {data.get('comparator_version')!r}; "
            f"este é {COMPARATOR_VERSION!r}"
        )
    tolerances = {**DEFAULT_TOLERANCES, **(data.get("tolerances") or {})}
    unknown_tol = set(tolerances) - set(DEFAULT_TOLERANCES)
    if unknown_tol:
        raise AllowanceError(f"tolerâncias desconhecidas: {sorted(unknown_tol)}")
    known = _known_anomalies(anomalies_path) if anomalies_path else None
    dirs = decision_dirs if decision_dirs is not None else default_decision_dirs()

    seen: set[str] = set()
    parsed: list[Allowance] = []
    for raw in data.get("allowances") or []:
        aid = raw.get("id")
        if not aid or aid in seen:
            raise AllowanceError(f"allowance sem id ou com id repetido: {aid!r}")
        seen.add(aid)
        check = raw.get("check")
        if check not in CHECKS:
            raise AllowanceError(f"{aid}: check desconhecido {check!r}")
        if check in NON_ALLOWABLE:
            raise AllowanceError(f"{aid}: {check} nunca é permitível")
        if raw.get("dimension") != CHECKS[check]:
            raise AllowanceError(f"{aid}: {check} pertence a {CHECKS[check]}")
        scope = raw.get("scope")
        scopes = tuple(scope) if isinstance(scope, list) else (scope,)
        generic = any(not s or not isinstance(s, str) or _WILDCARD.search(s) for s in scopes)
        if not scopes or generic:
            raise AllowanceError(f"{aid}: escopo vazio ou genérico: {scope!r}")
        match = raw.get("match") or {}
        if not match:
            raise AllowanceError(f"{aid}: match vazio = allowance genérica")
        bad = set(match) - MATCH_KEYS
        if bad:
            raise AllowanceError(f"{aid}: chaves de match desconhecidas {sorted(bad)}")
        for key, fields in (("items", ITEM_KEYS), ("pairs", PAIR_KEYS)):
            if key not in match:
                continue
            entries = match[key]
            if (check != "narrative_facts" or not isinstance(entries, list) or not entries
                    or any(not isinstance(e, dict) or set(e) != fields for e in entries)):
                raise AllowanceError(
                    f"{aid}: {key} = lista não vazia de {sorted(fields)} (só narrative_facts)")
            if key == "items" and any(e["kind"] not in ITEM_KINDS for e in entries):
                raise AllowanceError(f"{aid}: items.kind fora de {sorted(ITEM_KINDS)}")
        reference = raw.get("reference") or {}
        if not reference or not ({"anomaly", "dec"} >= set(reference)):
            raise AllowanceError(
                f"{aid}: referência deve ser anomaly, dec ou anomaly + dec (a DEC que decidiu)")
        if raw.get("pending_decision"):
            if "dec" in reference:
                raise AllowanceError(
                    f"{aid}: cita {reference['dec']}, que decidiu: remova pending_decision")
            raise AllowanceError(
                f"{aid}: pending_decision — decisão pendente não é desvio permitido; registre "
                "a DEC e cite-a na referência")
        number = raw.get("report_number")
        if not isinstance(number, int):
            raise AllowanceError(f"{aid}: report_number inteiro obrigatório")
        anomaly = reference.get("anomaly")
        if anomaly and known is not None and (number, anomaly) not in known:
            raise AllowanceError(
                f"{aid}: anomalia {anomaly!r} não catalogada para o relatório nº {number}"
            )
        if "dec" in reference:
            if not re.fullmatch(r"DEC-\d{3}", str(reference["dec"])):
                raise AllowanceError(f"{aid}: DEC mal formado {reference['dec']!r}")
            if not _decision_exists(reference["dec"], dirs):
                raise AllowanceError(f"{aid}: {reference['dec']} não existe em docs/decisions")
        parsed.append(Allowance(
            id=aid, report_number=number, reference=dict(reference), dimension=raw["dimension"],
            check=check, scopes=scopes, match=dict(match), rationale=raw.get("rationale", ""),
        ))
    hunk_files: list[tuple[int, str, str]] = []
    for entry in data.get("approved_hunks") or []:
        if (not isinstance(entry, dict) or set(entry) != {"report_number", "file", "sha256"}
                or not isinstance(entry["report_number"], int)
                or not re.fullmatch(r"[0-9a-f]{64}", str(entry["sha256"]))):
            raise AllowanceError(
                "approved_hunks: cada registro é {report_number: int, file, sha256 (64 hex)}")
        if any(n == entry["report_number"] for n, _, _ in hunk_files):
            raise AllowanceError(f"approved_hunks: nº {entry['report_number']} registrado 2x")
        hunk_files.append((entry["report_number"], str(entry["file"]), str(entry["sha256"])))
    if hunk_files and version in LEGACY_ALLOWANCE_VERSIONS:
        raise AllowanceError(
            f"approved_hunks exige allowances do comparador {COMPARATOR_VERSION} (as da "
            f"{version} não têm âncora posicional)")
    return AllowanceSet(
        status=data["status"], version=str(data.get("version", "")),
        comparator_version=str(data["comparator_version"]),
        frozen_on=str(data.get("frozen_on", "")),
        tolerances=tolerances, allowances=tuple(parsed), pending=tuple(data.get("pending") or ()),
        sha256=sha256, source=source, warnings=tuple(warnings), hunk_files=tuple(hunk_files),
    )


def load_allowances(
    path: Path | str = DEFAULT_ALLOWANCES,
    *,
    anomalies_path: Path | None = DEFAULT_ANOMALIES,
    decision_dirs: list[Path] | None = None,
) -> AllowanceSet:
    path = Path(path)
    raw = path.read_bytes()
    data = yaml.safe_load(raw.decode("utf-8"))
    return parse_allowances(
        data, anomalies_path=anomalies_path, decision_dirs=decision_dirs,
        sha256=hashlib.sha256(raw).hexdigest(), source=str(path),
    )


# --------------------------------------------------------------------------- hunks aprovados (v4)

HUNK_REQUIRED = frozenset({"id", "section", "anchor", "position", "context_before",
                           "context_after", "reference_text", "generated_text", "reference"})
HUNK_KEYS = HUNK_REQUIRED | {"rationale", "pending"}
# v4.1: posição estrutural do hunk (textdiff.Hunk.position)
POSITION_KEYS = frozenset({"block", "paragraph", "tokens", "generated_block"})
HUNK_SET_KEYS = frozenset({"status", "version", "report_number", "comparator_version",
                           "frozen_on", "generated_from", "notes", "hunks"})


def _reference_label(reference: dict) -> str:
    if "anomaly" in reference:
        dec = f" ({reference['dec']})" if "dec" in reference else ""
        return f"anomalia {reference['anomaly']}{dec}"
    return reference["dec"]


@dataclass(frozen=True)
class ApprovedHunk:
    """Hunk de texto aprovado: exato (unidade, âncora, contexto, textos), POSICIONAL (bloco,
    parágrafo no bloco, tokens na referência, bloco gerado — v4.1) e justificado."""

    id: str
    report_number: int
    section: str
    anchor: str
    context_before: tuple[str, ...]
    context_after: tuple[str, ...]
    reference_text: str
    generated_text: str
    reference: dict
    rationale: str = ""
    # O gerado ainda não emite o texto esperado (ex.: "TT: DEC-015, ressalva por disciplina"):
    # o hunk real no mesmo parágrafo sai CRITICAL marcado como pendente (nunca ALLOWED).
    pending: str | None = None
    block: str = ""
    block_paragraph: int = 0
    reference_span: tuple[int, int] = (0, 0)
    generated_block: str = ""

    @property
    def key(self) -> tuple:
        """Mesma forma de `textdiff.Hunk.key`: o hunk real casa só no mesmo lugar."""
        return (self.section, self.anchor, self.block, self.block_paragraph,
                tuple(self.reference_span), self.generated_block, self.context_before,
                self.context_after, self.reference_text, self.generated_text)

    @property
    def reference_label(self) -> str:
        return _reference_label(self.reference)


@dataclass(frozen=True)
class HunkSet:
    status: str
    version: str
    report_number: int | None
    comparator_version: str
    frozen_on: str
    hunks: tuple[ApprovedHunk, ...]
    sha256: str | None = None
    source: str | None = None

    @classmethod
    def empty(cls, report_number: int | None = None) -> HunkSet:
        return cls("FROZEN", "0", report_number, COMPARATOR_VERSION, "", ())


def _parse_position(hid: str, position: Any, reference_text: str
                    ) -> tuple[str, int, tuple[int, int], str]:
    """`position: {block, paragraph, tokens: [início, fim], generated_block}` (v4.1)."""
    if not isinstance(position, dict) or set(position) != POSITION_KEYS:
        raise AllowanceError(
            f"{hid}: position = {{block, paragraph, tokens: [início, fim], generated_block}}")
    block, paragraph = position["block"], position["paragraph"]
    span, generated_block = position["tokens"], position["generated_block"]
    if not isinstance(block, str) or not isinstance(generated_block, str):
        raise AllowanceError(f"{hid}: position.block/generated_block = texto ('' fora de bloco)")
    if not isinstance(paragraph, int) or isinstance(paragraph, bool) or paragraph < 0:
        raise AllowanceError(f"{hid}: position.paragraph = inteiro >= 0 (índice no bloco)")
    if (not isinstance(span, list) or len(span) != 2
            or any(not isinstance(t, int) or isinstance(t, bool) for t in span)
            or not 0 <= span[0] <= span[1]):
        raise AllowanceError(f"{hid}: position.tokens = [início, fim] na referência")
    size = len(reference_text.split(" ")) if reference_text else 0
    if span[1] - span[0] != size:
        raise AllowanceError(
            f"{hid}: position.tokens {span} não tem os {size} tokens do texto de referência")
    return block, paragraph, (span[0], span[1]), generated_block


def parse_approved_hunks(
    data: dict,
    *,
    anomalies_path: Path | None = DEFAULT_ANOMALIES,
    decision_dirs: list[Path] | None = None,
    sha256: str | None = None,
    source: str | None = None,
) -> HunkSet:
    """Valida e congela um conjunto de hunks aprovados (docs/qa/approved_hunks/nNN.yaml).

    Recusa: status diferente de FROZEN, comparador diferente do atual, `report_number` ausente,
    chave desconhecida, hunk sem os campos obrigatórios (v4.1: `position`), posição mal
    formada (intervalo de tokens que não tem o tamanho do texto de referência), contexto com
    mais de 6 tokens, os dois textos vazios, id ou hunk repetido e — como as allowances —
    `reference` sem anomalia catalogada para o MESMO relatório nem DEC existente. Hunk sem
    justificativa não entra.
    """
    if not isinstance(data, dict) or data.get("status") != "FROZEN":
        raise AllowanceError("hunks aprovados precisam estar CONGELADOS (status: FROZEN)")
    if str(data.get("comparator_version")) != COMPARATOR_VERSION:
        raise AllowanceError(
            f"hunks aprovados para o comparador {data.get('comparator_version')!r}; "
            f"este é {COMPARATOR_VERSION!r}")
    unknown = set(data) - HUNK_SET_KEYS
    if unknown:
        raise AllowanceError(f"hunks aprovados: chaves desconhecidas {sorted(unknown)}")
    number = data.get("report_number")
    if not isinstance(number, int):
        raise AllowanceError("hunks aprovados: report_number inteiro obrigatório")
    known = _known_anomalies(anomalies_path) if anomalies_path else None
    dirs = decision_dirs if decision_dirs is not None else default_decision_dirs()
    ids: set[str] = set()
    keys: set[tuple] = set()
    parsed: list[ApprovedHunk] = []
    for raw in data.get("hunks") or []:
        hid = raw.get("id") if isinstance(raw, dict) else None
        if not hid or hid in ids:
            raise AllowanceError(f"hunk sem id ou com id repetido: {hid!r}")
        ids.add(hid)
        missing = HUNK_REQUIRED - set(raw)
        if missing:
            raise AllowanceError(f"{hid}: campos obrigatórios ausentes {sorted(missing)}")
        bad = set(raw) - HUNK_KEYS
        if bad:
            raise AllowanceError(f"{hid}: chaves desconhecidas {sorted(bad)}")
        reference = raw.get("reference")
        if (not isinstance(reference, dict) or not reference
                or not ({"anomaly", "dec"} >= set(reference))):
            raise AllowanceError(
                f"{hid}: reference deve ser anomaly, dec ou anomaly + dec (hunk sem "
                "justificativa não entra no conjunto aprovado)")
        anomaly = reference.get("anomaly")
        if anomaly and known is not None and (number, anomaly) not in known:
            raise AllowanceError(
                f"{hid}: anomalia {anomaly!r} não catalogada para o relatório nº {number}")
        if "dec" in reference:
            if not re.fullmatch(r"DEC-\d{3}", str(reference["dec"])):
                raise AllowanceError(f"{hid}: DEC mal formado {reference['dec']!r}")
            if not _decision_exists(reference["dec"], dirs):
                raise AllowanceError(f"{hid}: {reference['dec']} não existe em docs/decisions")
        contexts = []
        for name in ("context_before", "context_after"):
            value = raw[name]
            if (not isinstance(value, list) or len(value) > CONTEXT_TOKENS
                    or any(not isinstance(t, str) or not t for t in value)):
                raise AllowanceError(
                    f"{hid}: {name} = lista de até {CONTEXT_TOKENS} tokens (texto)")
            contexts.append(tuple(value))
        ref_text, gen_text = raw["reference_text"], raw["generated_text"]
        if not isinstance(ref_text, str) or not isinstance(gen_text, str) or not (
                ref_text or gen_text) or ref_text == gen_text:
            raise AllowanceError(f"{hid}: reference_text/generated_text: textos diferentes")
        if not isinstance(raw["section"], str) or not raw["section"]:
            raise AllowanceError(f"{hid}: section (unidade de texto) obrigatória")
        if not re.fullmatch(r"[0-9a-f]{12}|", str(raw["anchor"])):
            raise AllowanceError(f"{hid}: anchor = sha256[:12] do parágrafo de referência")
        pending = raw.get("pending")
        if pending is not None and (not isinstance(pending, str) or not pending.strip()):
            raise AllowanceError(f"{hid}: pending = texto que diz o que falta no builder")
        block, block_paragraph, span, generated_block = _parse_position(
            hid, raw["position"], ref_text)
        hunk = ApprovedHunk(
            id=hid, report_number=number, section=raw["section"], anchor=str(raw["anchor"]),
            context_before=contexts[0], context_after=contexts[1], reference_text=ref_text,
            generated_text=gen_text, reference=dict(reference),
            rationale=str(raw.get("rationale") or ""), pending=pending, block=block,
            block_paragraph=block_paragraph, reference_span=span,
            generated_block=generated_block)
        if hunk.key in keys:
            raise AllowanceError(
                f"{hid}: hunk repetido (mesma unidade, âncora, posição, contexto e textos)")
        keys.add(hunk.key)
        parsed.append(hunk)
    return HunkSet(status="FROZEN", version=str(data.get("version", "")), report_number=number,
                   comparator_version=str(data["comparator_version"]),
                   frozen_on=str(data.get("frozen_on", "")), hunks=tuple(parsed),
                   sha256=sha256, source=source)


def load_approved_hunks(
    path: Path | str,
    *,
    expected_sha256: str | None = None,
    anomalies_path: Path | None = DEFAULT_ANOMALIES,
    decision_dirs: list[Path] | None = None,
) -> HunkSet:
    """Carrega um conjunto de hunks aprovados; com `expected_sha256` (o registrado nas
    allowances), arquivo editado depois de congelado é recusado."""
    path = Path(path)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise AllowanceError(
            f"{path.name}: sha256 {digest[:12]} difere do registrado nas allowances "
            f"({expected_sha256[:12]}): conjunto de hunks alterado depois de congelado")
    return parse_approved_hunks(yaml.safe_load(raw.decode("utf-8")),
                                anomalies_path=anomalies_path, decision_dirs=decision_dirs,
                                sha256=digest, source=str(path))


def draft_hunks(report: Report, *, approved: HunkSet | None = None,
                id_prefix: str | None = None) -> dict:
    """Rascunho de conjunto de hunks a partir do diff atual (`text_diff` do relatório), na
    ordem do documento. Hunk que já casa com um aprovado traz a referência dele; os demais
    saem com `reference: null` — o parser recusa o rascunho até cada um ser classificado
    (anomalia ou DEC) ou retirado como defeito."""
    number = report.report_number
    prefix = id_prefix or f"HNK-{number}"
    by_id = {h.id: h for h in (approved.hunks if approved else ())}
    hunks = []
    real = (d for d in report.differences if d.check == "text_diff" and d.kind != "reverted")
    for n, d in enumerate(real, start=1):
        ctx = d.context
        known = by_id.get(d.allowance_id or "")
        entry = {
            "id": known.id if known else f"{prefix}-{n:03d}",
            "section": d.scope,
            "anchor": ctx.get("anchor", ""),
            "position": dict(ctx.get("position") or {}),
            "context_before": list(ctx.get("context_before", ())),
            "context_after": list(ctx.get("context_after", ())),
            "reference_text": d.reference or "",
            "generated_text": d.generated or "",
            "reference": dict(known.reference) if known else None,
            "rationale": known.rationale if known else "",
        }
        hunks.append(entry)
    return {"status": "DRAFT", "version": "draft", "report_number": number,
            "comparator_version": COMPARATOR_VERSION, "frozen_on": "",
            "generated_from": {"reference": report.reference_source,
                               "generated": report.generated_source},
            "hunks": hunks}


# --------------------------------------------------------------------------- relatório


@dataclass
class Difference:
    dimension: str
    check: str
    scope: str
    severity: str
    message: str
    kind: str = "mismatch"  # mismatch | missing | extra | order | delta
    value: Any = None
    reference: Any = None
    generated: Any = None
    original_severity: str | None = None
    allowance_id: str | None = None
    allowance_reference: str | None = None
    context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["context"] = {k: v for k, v in self.context.items()
                           if k not in ("reference_sequence", "generated_sequence")}
        return data


@dataclass
class _Unit:
    dimension: str
    check: str
    scope: str
    diffs: list[Difference]

    @property
    def failed(self) -> bool:
        return any(d.severity != ALLOWED for d in self.diffs)


@dataclass
class Report:
    report_number: int | None
    verdict: str
    reasons: list[str]
    metrics: dict
    differences: list[Difference]
    allowances_used: list[str]
    allowances_unused: list[str]
    comparator_version: str = COMPARATOR_VERSION
    allowances_sha256: str | None = None
    reference_source: dict | None = None
    generated_source: dict | None = None
    warnings: list[str] = field(default_factory=list)
    approved_hunks_sha256: str | None = None
    approved_hunks_orphans: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.verdict == "PASS"

    def by_severity(self, severity: str) -> list[Difference]:
        return [d for d in self.differences if d.severity == severity]

    def find(self, check: str, **attrs) -> list[Difference]:
        return [d for d in self.differences if d.check == check
                and all(getattr(d, k) == v for k, v in attrs.items())]

    def to_dict(self) -> dict:
        return {
            "report_number": self.report_number,
            "verdict": self.verdict,
            "reasons": self.reasons,
            "warnings": self.warnings,
            "comparator_version": self.comparator_version,
            "allowances_sha256": self.allowances_sha256,
            "approved_hunks_sha256": self.approved_hunks_sha256,
            "approved_hunks_orphans": self.approved_hunks_orphans,
            "reference_source": self.reference_source,
            "generated_source": self.generated_source,
            "metrics": self.metrics,
            "allowances_used": self.allowances_used,
            "allowances_unused": self.allowances_unused,
            "differences": [d.to_dict() for d in self.differences],
        }

    def to_markdown(self) -> str:
        m = self.metrics
        lines = [
            f"# Golden test — Relatório G2 nº {self.report_number}",
            "",
            f"**Veredito: {self.verdict}** · comparador {self.comparator_version} · "
            f"allowances sha256 `{(self.allowances_sha256 or '-')[:12]}` · "
            f"hunks aprovados sha256 `{(self.approved_hunks_sha256 or '-')[:12]}`",
            "",
        ]
        lines += [f"- {r}" for r in self.reasons] + [""]
        if self.warnings:
            lines += [f"> Aviso: {w}" for w in self.warnings] + [""]
        lines += ["| métrica | valor |", "|---|---|"]
        lines.append(f"| score estrutural | {m['structural_score']:.4f} |")
        lines.append(f"| acurácia de conteúdo | {m['content_accuracy']:.4f} |")
        for dim in DIMENSIONS:
            d = m["dimensions"][dim]
            lines.append(f"| {dim} | {d['passed']}/{d['units']} unidades |")
        for sev in (CRITICAL, MAJOR, MINOR, ALLOWED):
            lines.append(f"| diferenças {sev} | {m['severity_counts'].get(sev, 0)} |")
        lines.append(f"| páginas ref/ger | {m['pages']['reference']}/{m['pages']['generated']} |")
        td = m.get("text_diff") or {}
        if td:
            lines.append(
                f"| diff de texto estrito | {td['hunks']} hunks · aprovados {td['approved']} · "
                f"não aprovados {td['unapproved']} (pendentes {td['pending']}) · "
                f"órfãos {len(td['orphans'])} · v3 coberto por hunks {td['v3_covered']} |")
        for block, b in m["product_control"].items():
            lines.append(
                f"| Controle de Produtos {block} | ref {b['reference']} · ger {b['generated']} · "
                f"em ordem {b['in_order']} · linhas iguais {b.get('rows_equal', '-')} |"
            )
        fig = m.get("figures") or {}
        if fig:
            lines.append(
                f"| figuras raster | {fig.get('pairs', 0)} pares · "
                f"em branco {fig.get('blank', 0)} · "
                f"selo verificado {fig.get('identity_verified', 0)} · "
                f"não verificável {fig.get('identity_unverifiable', 0)} |"
            )
        low = {k: v for k, v in (m.get("narrative") or {}).items()
               if v["coverage"] < 1.0 or v["facts_reference"] != v["facts_generated"]}
        for key, v in sorted(low.items()):
            lines.append(
                f"| narrativa {key} | cobertura {v['coverage']:.3f} · maior lacuna "
                f"{v['longest_gap_words']} · fatos ref/ger {v['facts_reference']}/"
                f"{v['facts_generated']} |"
            )
        lines.append("")
        for sev in (CRITICAL, MAJOR, MINOR, ALLOWED):
            diffs = self.by_severity(sev)
            if not diffs:
                continue
            lines += [f"## {sev} ({len(diffs)})", ""]
            for d in diffs:
                extra = f" — {d.allowance_id} ({d.allowance_reference})" if d.allowance_id else ""
                lines.append(f"- `{d.dimension}/{d.check}` [{d.scope}] {d.message}{extra}")
            lines.append("")
        if self.allowances_unused:
            lines += ["## Allowances sem uso", ""]
            lines += [f"- {a}" for a in self.allowances_unused] + [""]
        return "\n".join(lines)


# --------------------------------------------------------------------------- utilidades


def _fold(text: str) -> str:
    """Forma de comparação: sem acento, maiúscula, espaços colapsados."""
    return re.sub(r"\s+", " ", strip_accents(text)).strip().upper()


def sequence_diff(ref: list, gen: list) -> tuple[list, list, list, int]:
    """(faltando, sobrando, fora de ordem, tamanho do casamento) entre duas sequências.

    Item que aparece em `faltando` e em `sobrando` foi deslocado: vira `fora de ordem`.
    """
    matcher = SequenceMatcher(None, ref, gen, autojunk=False)
    missing: list = []
    extra: list = []
    matched = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            matched += i2 - i1
            continue
        missing.extend(ref[i1:i2])
        extra.extend(gen[j1:j2])
    moved: list = []
    extra_pool = list(extra)
    remaining_missing = []
    for item in missing:
        if item in extra_pool:
            extra_pool.remove(item)
            moved.append(item)
        else:
            remaining_missing.append(item)
    return remaining_missing, extra_pool, moved, matched


_UNITS = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez",
          "onze", "doze", "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito",
          "dezenove"]
_TENS = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta",
         "noventa"]
_HUNDREDS = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos",
             "setecentos", "oitocentos", "novecentos"]


def number_to_words_pt(n: int, *, feminine: bool = False) -> str:
    """Numeral por extenso em pt-BR (0 a 999 999); `feminine` para 'páginas'."""
    if n < 0 or n > 999_999:
        raise ValueError(n)

    def fem(word: str) -> str:
        if not feminine:
            return word
        return {"um": "uma", "dois": "duas"}.get(word, word.replace("entos", "entas"))

    def below_thousand(k: int) -> str:
        if k == 100:
            return "cem"
        parts = []
        h, rest = divmod(k, 100)
        if h:
            parts.append(fem(_HUNDREDS[h]))
        if rest:
            if rest < 20:
                parts.append(fem(_UNITS[rest]))
            else:
                t, u = divmod(rest, 10)
                parts.append(_TENS[t] + (f" e {fem(_UNITS[u])}" if u else ""))
        return " e ".join(parts)

    if n == 0:
        return "zero"
    thousands, rest = divmod(n, 1000)
    words = []
    if thousands:
        words.append("mil" if thousands == 1 else f"{below_thousand(thousands)} mil")
    if rest:
        joiner = " e " if thousands and (rest < 100 or rest % 100 == 0) else " "
        text = below_thousand(rest)
        return (words[0] + joiner + text) if words else text
    return words[0]


def _words_equal(a: str, b: str) -> bool:
    def norm(s: str) -> str:
        return _fold(s).replace("CATORZE", "QUATORZE")

    return norm(a) == norm(b)


def _prose_words(text: str) -> list[str]:
    """Palavras do texto com cada fato (código, rodovia, data, hora, mês, número) trocado pelo
    seu tipo: cobertura e semelhança medem a prosa; cada fato é julgado só uma vez, por
    `narrative_facts`/`text_codes` (e suas allowances)."""
    return mask_facts(text).split()


def _paragraph_tokens(text: str) -> list[str]:
    """Palavras de um parágrafo para o alinhamento por parágrafo: fatos pelo tipo, sem
    pontuação (';' x '.' no fim de item não é diferença de prosa)."""
    return re.findall(r"<\w+>|\w+", _fold(mask_facts(text)))


def _paragraph_hash(text: str) -> str:
    return hashlib.sha256(_fold(text).encode("utf-8")).hexdigest()[:12]


def _contains_run(tokens: list[str], run: list[str]) -> bool:
    """`run` aparece contíguo em `tokens`."""
    n = len(run)
    first = run[0]
    return any(tokens[i] == first and tokens[i:i + n] == run
               for i in range(len(tokens) - n + 1))


def _containment(part: list[str], whole: list[str]) -> float:
    """Fração de `part` achada em ordem dentro de `whole`."""
    if not part:
        return 1.0
    matcher = SequenceMatcher(None, part, whole, autojunk=False)
    return sum(b.size for b in matcher.get_matching_blocks()) / len(part)


def _cell_key(text: str) -> str:
    """Célula do Controle de Produtos para comparação: sem acento, maiúscula, SEM espaços
    (a mesma descrição quebrada em pontos diferentes da coluna continua igual)."""
    return re.sub(r"\s+", "", strip_accents(text or "")).upper()


def _thumb(content: dict | None) -> tuple[int, int, list[int]] | None:
    thumb = (content or {}).get("thumb")
    if not thumb:
        return None
    return thumb["columns"], thumb["rows"], list(bytes.fromhex(thumb["hex"]))


def _pearson(a: list[float], b: list[float]) -> float | None:
    n = len(a)
    if n == 0 or n != len(b):
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va < 1e-9 or vb < 1e-9:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True)) / math.sqrt(va * vb)


def thumb_similarity(ref_content: dict | None, gen_content: dict | None) -> float | None:
    """Correlação das miniaturas na parte comum a partir do topo (a figura gerada pode mostrar
    a tabela inteira onde a histórica mostra a janela de rolagem — DEC-009)."""
    r, g = _thumb(ref_content), _thumb(gen_content)
    if r is None or g is None or r[0] != g[0]:
        return None
    cols, rows = r[0], min(r[1], g[1])
    return _pearson(r[2][:cols * rows], g[2][:cols * rows])


def _gray(patch: dict | None):
    import numpy as np

    if not patch:
        return None
    h, w = patch["shape"]
    data = np.frombuffer(base64.b64decode(patch["gray_b64"]), dtype=np.uint8)
    if data.size != h * w or h == 0 or w == 0:
        return None
    return data.reshape(h, w).astype(float)


def label_match(template_patch: dict | None, area_patch: dict | None) -> float | None:
    """Maior correlação normalizada do recorte justo (`template`) deslizando sobre a janela
    (`area`). None se algum dos dois for liso (sem conteúdo para casar)."""
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy vem com o extra `discovery` (pandas)
        return None
    tpl, area = _gray(template_patch), _gray(area_patch)
    if tpl is None or area is None:
        return None
    th, tw = min(tpl.shape[0], area.shape[0]), min(tpl.shape[1], area.shape[1])
    oy, ox = (tpl.shape[0] - th) // 2, (tpl.shape[1] - tw) // 2
    tpl = tpl[oy:oy + th, ox:ox + tw]
    t = tpl - tpl.mean()
    t_norm = float(np.sqrt((t * t).sum()))
    if t_norm < 1e-6:
        return None
    ah, aw = area.shape
    # Correlação cruzada "válida" por FFT; somas por janela por imagem integral.
    shape = (ah + th - 1, aw + tw - 1)
    spectrum = np.fft.rfft2(area, shape) * np.fft.rfft2(t[::-1, ::-1], shape)
    num = np.fft.irfft2(spectrum, shape)[th - 1:ah, tw - 1:aw]

    def window_sum(a):
        c = np.pad(a, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
        return c[th:, tw:] - c[:-th, tw:] - c[th:, :-tw] + c[:-th, :-tw]

    n = th * tw
    s1, s2 = window_sum(area), window_sum(area * area)
    var = np.clip(s2 - s1 * s1 / n, 0.0, None)
    den = np.sqrt(var) * t_norm
    valid = den > 1e-3 * t_norm * math.sqrt(n)
    if not valid.any():
        return None
    return float(np.clip(num[valid] / den[valid], -1.0, 1.0).max())


# --------------------------------------------------------------------------- regiões raster


def load_raster_regions(path: Path | str = DEFAULT_RASTER_REGIONS) -> dict:
    """Configuração das regiões de texto/numerais dos painéis (ver o arquivo)."""
    raw = Path(path).read_bytes()
    data = yaml.safe_load(raw.decode("utf-8")) or {}
    data["sha256"] = hashlib.sha256(raw).hexdigest()
    return data


def _ink_maps(content: dict | None):
    """(tinta 0..1, cinza 0..255) do mapa de tinta do extrator, ou (None, None)."""
    import numpy as np

    ink = (content or {}).get("ink")
    if not ink:
        return None, None
    shape = (ink["rows"], ink["columns"])
    a = np.frombuffer(base64.b64decode(ink["b64"]), dtype=np.uint8).reshape(shape) / 255.0
    g = (np.frombuffer(base64.b64decode(ink["gray_b64"]), dtype=np.uint8).reshape(shape)
         .astype(float) if ink.get("gray_b64") else None)
    return a, g


def ink_grid(content: dict | None, columns: int = 12):
    """Mapa de tinta agregado em `columns` colunas de células quadradas (painel inteiro)."""
    ink, _ = _ink_maps(content)
    if ink is None or ink.shape[1] < columns:
        return None
    f = ink.shape[1] // columns
    rows = ink.shape[0] // f
    if rows == 0:
        return None
    return ink[:rows * f, :columns * f].reshape(rows, f, columns, f).mean(axis=(1, 3))


def grid_distance(a, b) -> float | None:
    """Diferença média de tinta entre duas grades na parte comum a partir do topo."""
    if a is None or b is None or a.shape[1] != b.shape[1]:
        return None
    rows = min(a.shape[0], b.shape[0])
    return float(abs(a[:rows] - b[:rows]).mean())


def _box_cells(box: list[float], columns: int) -> tuple[int, int, int, int]:
    return tuple(round(v * columns) for v in box)


def region_delta(ref_content: dict | None, gen_content: dict | None, box: list[float], *,
                 subcell: int = 3, shift_rows: int = 0, shift_cols: int = 0) -> float | None:
    """Maior diferença de fração de tinta numa região (caixa em fração da largura), por
    faixas de subcélulas, depois do melhor deslocamento de cada faixa (até `shift_rows` x
    `shift_cols` células do mapa). None se a região não couber em algum dos painéis."""
    import numpy as np

    ra, _ = _ink_maps(ref_content)
    ga, _ = _ink_maps(gen_content)
    if ra is None or ga is None or ra.shape[1] != ga.shape[1]:
        return None
    x0, y0, x1, y1 = _box_cells(box, ra.shape[1])
    if y1 > min(ra.shape[0], ga.shape[0]) or x1 > ra.shape[1]:
        return None
    k = subcell
    width = (x1 - x0) // k * k
    if width == 0 or y1 - y0 < k:
        return None

    def pooled(m, top: int, left: int):
        band = m[top:top + k, left:left + width]
        return band.reshape(1, k, width // k, k).mean(axis=(1, 3))

    worst = 0.0
    for top in range(y0, y1 - k + 1, k):
        g = pooled(ga, top, x0)
        best = None
        for dy in range(-shift_rows, shift_rows + 1):
            for dx in range(-shift_cols, shift_cols + 1):
                t, left = top + dy, x0 + dx
                if t < 0 or t + k > ra.shape[0] or left < 0 or left + width > ra.shape[1]:
                    continue
                d = float(np.abs(g - pooled(ra, t, left)).max())
                best = d if best is None else min(best, d)
        if best is not None:
            worst = max(worst, best)
    return worst


def selected_tab(content: dict | None, selector: dict) -> int | None:
    """Aba destacada de um seletor (1..cells): a de menor cinza médio, se mais escura que a
    segunda por `min_contrast`; None se nenhuma se destaca ou se o mapa não existe."""
    _, gray = _ink_maps(content)
    if gray is None:
        return None
    x0, y0, x1, y1 = _box_cells(selector["box"], gray.shape[1])
    strip = gray[y0:y1, x0:x1]
    n = selector["cells"]
    if strip.size == 0 or strip.shape[1] < n:
        return None
    means = [float(strip[:, i * strip.shape[1] // n:(i + 1) * strip.shape[1] // n].mean())
             for i in range(n)]
    order = sorted(range(n), key=lambda i: means[i])
    if means[order[1]] - means[order[0]] < selector["min_contrast"]:
        return None
    return order[0] + 1


def panel_kind(regions: dict, anchor: str, position: int) -> str | None:
    kinds = (regions.get("anchors") or {}).get(anchor)
    if not kinds:
        return None
    return kinds[min(position, len(kinds)) - 1]


# --------------------------------------------------------------------------- comparador


def _run_at_block(unit: TextUnit, run: list[str], before: int, has_text: bool,
                  block: str) -> bool:
    """`run` (contexto antes + texto + contexto depois) aparece contíguo em `unit` com o PONTO
    do hunk dentro de `block`: o 1º token do texto, ou, sem texto, o último do contexto antes
    (como `TextUnit.paragraph_at`). O contexto pode cruzar o limite do bloco; o ponto não.
    `block` vazio = em qualquer lugar."""
    n, tokens = len(run), unit.tokens
    for i in range(len(tokens) - n + 1):
        if tokens[i] != run[0] or tokens[i:i + n] != run:
            continue
        point = i + before if has_text or not before else i + before - 1
        if not block or unit.paragraph_block[unit.token_paragraph[point]] == block:
            return True
    return False


class _Comparator:
    def __init__(self, ref: dict, gen: dict, allowances: AllowanceSet, report_number: int | None,
                 raster_regions: dict | None = None, hunks: HunkSet | None = None):
        self.ref = ref
        self.gen = gen
        self.allowances = allowances.for_report(report_number)
        self.allowance_set = allowances
        self.tol = allowances.tolerances
        self.report_number = report_number
        self.regions = raster_regions if raster_regions is not None else {}
        self.hunks = hunks if hunks is not None else HunkSet.empty(report_number)
        self.units: list[_Unit] = []
        self.used: set[str] = set()
        self.claimed: dict[str, set] = {}
        self.metrics: dict = {}
        # v4.0: estado de cada unidade de texto ("clean", "approved", "pending", "open") e as
        # referências dos hunks aprovados nela
        self.text_state: dict[str, str] = {}
        self.text_refs: dict[str, set[str]] = {}
        # v4.1: unidades de texto dos dois lados e, por unidade, os hunks reais aprovados
        # (com o id do aprovado) — base da explicação exata dos `narrative_facts`
        self.text_units: tuple[dict[str, TextUnit], dict[str, TextUnit]] = ({}, {})
        self.approved_by_unit: dict[str, list[tuple[Hunk, ApprovedHunk]]] = {}
        # todos os hunks reais por unidade, com o aprovado que casou (None = em aberto)
        self.hunks_by_unit: dict[str, list[tuple[Hunk, ApprovedHunk | None]]] = {}
        self._pools: dict[str, dict] = {}
        self.orphans: list[ApprovedHunk] = []

    # -- registro ---------------------------------------------------------------------------

    def unit(self, check: str, scope: str, diffs: list[Difference]) -> None:
        for diff in diffs:
            self._apply_allowance(diff)
        self.units.append(_Unit(CHECKS[check], check, scope, diffs))

    def diff(self, check: str, scope: str, severity: str, message: str, **kw) -> Difference:
        return Difference(CHECKS[check], check, scope, severity, message, **kw)

    def _apply_allowance(self, diff: Difference) -> None:
        if diff.check in NON_ALLOWABLE:
            return
        for allowance in self.allowances:
            if (allowance.matches(diff, self.report_number)
                    and allowance.claim(diff, self.claimed.setdefault(allowance.id, set()))):
                diff.original_severity = diff.severity
                diff.severity = ALLOWED
                diff.allowance_id = allowance.id
                diff.allowance_reference = allowance.reference_label
                self.used.add(allowance.id)
                return

    def seq_unit(self, check: str, scope: str, ref: list, gen: list, severity: str,
                 label: str) -> int:
        missing, extra, moved, matched = sequence_diff(ref, gen)
        ctx = {"reference_sequence": list(ref), "generated_sequence": list(gen)}
        diffs = []
        for item in missing:
            diffs.append(self.diff(check, scope, severity, f"{label}: {item} falta no gerado",
                                   kind="missing", value=item, context=ctx))
        for item in extra:
            diffs.append(self.diff(check, scope, severity, f"{label}: {item} sobra no gerado",
                                   kind="extra", value=item, context=ctx))
        for item in moved:
            diffs.append(self.diff(check, scope, severity, f"{label}: {item} fora de ordem",
                                   kind="order", value=item, context=ctx))
        self.unit(check, scope, diffs)
        return matched

    def facts_unit(self, scope: str, ref_s: dict, gen_s: dict, label: str) -> None:
        """`narrative_facts` como multiconjunto ORDENADO da seção (como `seq_unit`), com o
        bloco de rodovia de cada item no contexto e na mensagem ('[RD-103#2]')."""
        ref, gen = ref_s.get("facts") or [], gen_s.get("facts") or []
        rb = ref_s.get("fact_blocks") or [""] * len(ref)
        gb = gen_s.get("fact_blocks") or [""] * len(gen)
        matcher = SequenceMatcher(None, ref, gen, autojunk=False)
        missing: list[tuple[str, str]] = []
        extra: list[tuple[str, str]] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            missing += list(zip(ref[i1:i2], rb[i1:i2], strict=False))
            extra += list(zip(gen[j1:j2], gb[j1:j2], strict=False))
        moved: list[tuple[str, str]] = []
        remaining: list[tuple[str, str]] = []
        for item, block in missing:
            # Deslocado = o mesmo fato no MESMO bloco de rodovia (allowances v1.8): o fato que
            # sai de um bloco e aparece em outro mudou de rodovia/grupo, não de posição —
            # fica como falta + sobra (e pode virar par), não como `order`.
            hit = next((k for k, (v, b) in enumerate(extra) if v == item and b == block), None)
            if hit is None:
                remaining.append((item, block))
            else:
                moved.append((item, extra.pop(hit)[1] or block))
        ctx = {"reference_sequence": list(ref), "generated_sequence": list(gen)}

        # Par: o que falta e o que sobra no MESMO bloco, mesmo tipo e mesmo campo ("Análise
        # Programa: Não aprovado" -> "Em análise" na RD-104#3) — cada lado leva o outro no contexto.
        def shape(fact: str) -> tuple[str, str]:
            kind, _, rest = fact.partition(":")
            return kind, rest.partition("@")[2]

        partner: dict[tuple[str, int], str] = {}
        free = list(range(len(extra)))
        for i, (item, block) in enumerate(remaining):
            j = next((j for j in free if extra[j][1] == block
                      and shape(extra[j][0]) == shape(item)), None)
            if j is not None:
                free.remove(j)
                partner[("missing", i)] = extra[j][0]
                partner[("extra", j)] = item

        def where(block: str) -> str:
            return f" [{block}]" if block else ""

        diffs = []
        for kind, items, text in (("missing", remaining, "falta no gerado"),
                                  ("extra", extra, "sobra no gerado"),
                                  ("order", moved, "fora de ordem")):
            for n, (item, block) in enumerate(items):
                context = {**ctx, "block": block}
                pair = partner.get((kind, n))
                if pair is not None:
                    context["paired_with"] = pair
                diffs.append(self.diff("narrative_facts", scope, CRITICAL,
                                       f"{label}{where(block)}: {item} {text}"
                                       + (f" (par: {pair})" if pair else ""), kind=kind,
                                       value=item, context=context))
        self.unit("narrative_facts", scope, diffs)

    def scalar_unit(self, check: str, scope: str, ref: Any, gen: Any, severity: str,
                    label: str, **kw) -> None:
        diffs = []
        if ref != gen:
            diffs.append(self.diff(check, scope, severity,
                                   f"{label}: referência {ref!r}, gerado {gen!r}",
                                   reference=ref, generated=gen, **kw))
        self.unit(check, scope, diffs)

    # -- STRUCTURAL -------------------------------------------------------------------------

    def structural(self) -> None:
        ref, gen = self.ref, self.gen
        n_ref, n_gen = ref["page_count"], gen["page_count"]
        diffs = []
        if n_gen != n_ref:
            sev = MINOR if abs(n_gen - n_ref) <= self.tol["page_count_delta"] else MAJOR
            diffs.append(self.diff("page_count", "document", sev,
                                   f"páginas: referência {n_ref}, gerado {n_gen}",
                                   kind="delta", reference=n_ref, generated=n_gen))
        self.unit("page_count", "document", diffs)
        self.metrics["pages"] = {"reference": n_ref, "generated": n_gen}

        self.scalar_unit("page_size", "document",
                         sorted({p["size_name"] for p in ref["pages"]}),
                         sorted({p["size_name"] for p in gen["pages"]}),
                         MAJOR, "tamanhos de página")

        ref_runs = [r[0] for r in ref["orientation_runs"]]
        gen_runs = [r[0] for r in gen["orientation_runs"]]
        self.scalar_unit("orientation_runs", "document", ref_runs, gen_runs, CRITICAL,
                         "sequência de blocos retrato/paisagem")
        if ref_runs == gen_runs:
            for n, (r, g) in enumerate(zip(ref["orientation_runs"], gen["orientation_runs"],
                                           strict=True), start=1):
                diffs = []
                if r[1] != g[1]:
                    diffs.append(self.diff(
                        "orientation_run_length", f"run:{n}", MAJOR,
                        f"bloco {n} ({r[0]}): referência {r[1]} páginas, gerado {g[1]}",
                        kind="delta", reference=r[1], generated=g[1]))
                self.unit("orientation_run_length", f"run:{n}", diffs)

        self._headings()
        self._header_footer()

    def _headings(self) -> None:
        ref_h, gen_h = self.ref["headings"], self.gen["headings"]
        ref_labels = [_fold(h["label"]) for h in ref_h]
        gen_labels = [_fold(h["label"]) for h in gen_h]
        matcher = SequenceMatcher(None, ref_labels, gen_labels, autojunk=False)
        pairs: list[tuple[dict, dict]] = []
        missing: list[dict] = []
        extra: list[dict] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                pairs.extend(zip(ref_h[i1:i2], gen_h[j1:j2], strict=True))
            else:
                missing.extend(ref_h[i1:i2])
                extra.extend(gen_h[j1:j2])
        # Mesmo rótulo faltando e sobrando = título deslocado; mesmo número = texto mudou.
        for m in list(missing):
            same = next((e for e in extra if _fold(e["label"]) == _fold(m["label"])), None)
            if same:
                missing.remove(m)
                extra.remove(same)
                self.unit("heading_sequence", "document", [self.diff(
                    "heading_sequence", "document", CRITICAL,
                    f"título fora de ordem: {m['label']!r}", kind="order", value=m["label"],
                    reference=m["page"], generated=same["page"])])
                continue
            if m["number"]:
                renamed = next((e for e in extra if e["number"] == m["number"]), None)
                if renamed:
                    missing.remove(m)
                    extra.remove(renamed)
                    self.unit("heading_text", "document", [self.diff(
                        "heading_text", "document", MAJOR,
                        f"título {m['number']}: referência {m['text']!r}, "
                        f"gerado {renamed['text']!r}",
                        value=m["number"], reference=m["text"], generated=renamed["text"])])
                    pairs.append((m, renamed))
        for m in missing:
            self.unit("heading_sequence", "document", [self.diff(
                "heading_sequence", "document", CRITICAL, f"título falta no gerado: {m['label']!r}",
                kind="missing", value=m["label"], reference=m["page"])])
        for e in extra:
            self.unit("heading_sequence", "document", [self.diff(
                "heading_sequence", "document", CRITICAL, f"título sobra no gerado: {e['label']!r}",
                kind="extra", value=e["label"], generated=e["page"])])
        shift_tol = self.tol["heading_page_shift"]
        for r, g in pairs:
            self.unit("heading_sequence", "document", [])
            diffs = []
            if r["page"] != g["page"]:
                sev = None if abs(g["page"] - r["page"]) <= shift_tol else MINOR
                if sev:
                    diffs.append(self.diff(
                        "heading_page", "document", sev,
                        f"título {r['label']!r}: página {r['page']} na referência, "
                        f"{g['page']} no gerado",
                        kind="delta", value=r["label"], reference=r["page"], generated=g["page"]))
            self.unit("heading_page", "document", diffs)
        self.metrics["headings"] = {
            "reference": len(ref_h), "generated": len(gen_h), "matched_in_order": len(pairs),
        }

    def _header_footer(self) -> None:
        def profile(facts: dict, key: str, cover: bool) -> dict[str, list]:
            out: dict[str, set] = {}
            for p in facts["pages"]:
                if p.get("is_cover", False) != cover:
                    continue
                out.setdefault(p["orientation"], set()).add(" | ".join(p[key]))
            return {k: sorted(v) for k, v in out.items()}

        for key, check in (("header_text", "header_text"), ("footer_text", "footer_text")):
            for cover in (True, False):
                ref_p, gen_p = profile(self.ref, key, cover), profile(self.gen, key, cover)
                for orientation in sorted(set(ref_p) | set(gen_p)):
                    scope = f"{'cover' if cover else 'body'}:{orientation}"
                    self.scalar_unit(check, scope, ref_p.get(orientation), gen_p.get(orientation),
                                     MAJOR, f"{key} ({scope})")

        def numbering_ok(facts: dict) -> list[int]:
            return [p["index"] for p in facts["pages"]
                    if not p.get("is_cover") and p["printed_page_number"] != p["index"]]

        ref_bad, gen_bad = numbering_ok(self.ref), numbering_ok(self.gen)
        diffs = []
        if not ref_bad and gen_bad:
            diffs.append(self.diff("page_number", "document", MAJOR,
                                   "numeração impressa diverge da física nas páginas "
                                   f"{gen_bad[:10]}", generated=gen_bad))
        self.unit("page_number", "document", diffs)

    # -- CONTENT ----------------------------------------------------------------------------

    def content(self) -> None:
        ref_pc, gen_pc = self.ref["product_control"], self.gen["product_control"]
        self.seq_unit("product_control_blocks", "document", ref_pc["block_order"],
                      gen_pc["block_order"], CRITICAL, "blocos do Controle de Produtos")
        pc_metrics = {}
        blocks = list(dict.fromkeys(ref_pc["block_order"] + gen_pc["block_order"]))
        for block in blocks:
            ref_codes = ref_pc["blocks"].get(block, [])
            gen_codes = gen_pc["blocks"].get(block, [])
            matched = self.seq_unit("product_control_codes", f"block:{block}", ref_codes,
                                    gen_codes, CRITICAL, f"Controle de Produtos {block}")
            pc_metrics[block] = {"reference": len(ref_codes), "generated": len(gen_codes),
                                 "in_order": matched,
                                 "rows_equal": self._rows(block)}
            self._labels(block)
        self.metrics["product_control"] = pc_metrics

        sections = sorted({k for k, s in self.ref["sections"].items() if s["text_codes"]}
                          | {k for k, s in self.gen["sections"].items() if s["text_codes"]})
        for key in sections:
            self.seq_unit("text_codes", f"section:{key}",
                          self.ref["sections"].get(key, {}).get("text_codes", []),
                          self.gen["sections"].get(key, {}).get("text_codes", []),
                          CRITICAL, f"códigos citados em {key}")

        self._roads()
        self._identity()
        self._narrative()
        self._figures()
        self._visibility()

    def _visibility(self) -> None:
        """v4.1 (QA4-E, MAJOR → verificação): texto extraível tem de estar VISÍVEL no gerado.
        Palavra branqueada (cor ~ fundo) ou coberta (retângulo/figura por cima) — o extrator
        3.2 a lista em `pages[].invisible_words` — é CRITICAL: o diff de texto a lê, o leitor
        não. Fatos de extrator < 3.2 (sem a lista): nada a verificar. A mesma palavra invisível
        na MESMA página da referência não conta (artefato do publicado: a data da capa do nº 14
        não tem tinta visível no PDF publicado; o gerado tem 0)."""
        pages = self.gen.get("pages") or []
        if not any("invisible_words" in p for p in pages):
            return
        inherited = Counter((p["index"], w["text"]) for p in self.ref.get("pages") or []
                            for w in p.get("invisible_words") or [])
        total = 0
        for page in pages:
            words = []
            for w in page.get("invisible_words") or []:
                if inherited[(page["index"], w["text"])] > 0:
                    inherited[(page["index"], w["text"])] -= 1
                else:
                    words.append(w)
            total += len(words)
            diffs = [self.diff("text_visibility", f"page:{page['index']}", CRITICAL,
                               f"p. {page['index']}: texto sem tinta visível {w['text']!r} "
                               f"(tinta {w['ink']:.3f}, contraste {w['contrast']}) — branqueado "
                               "ou coberto", kind="invisible", value=w["text"],
                               context={"bbox": w["bbox"]})
                     for w in words]
            self.unit("text_visibility", f"page:{page['index']}", diffs)
        self.metrics["text_visibility"] = {"invisible_words": total}

    def _rows(self, block: str) -> int:
        """Linha inteira de cada código casado (mesma posição na sequência alinhada): cada
        célula diferente é CRITICAL. Uma unidade por linha. Devolve as linhas iguais."""
        ref_rows = self.ref["product_control"].get("rows", {}).get(block, [])
        gen_rows = self.gen["product_control"].get("rows", {}).get(block, [])
        if not any("cells" in r for r in ref_rows + gen_rows):
            return 0  # fatos de extrator sem células: nada a comparar
        matcher = SequenceMatcher(None, [r["code"] for r in ref_rows],
                                  [r["code"] for r in gen_rows], autojunk=False)
        scope = f"block:{block}"
        equal = 0
        seen: Counter[str] = Counter()
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "equal":
                continue  # código faltando/sobrando/fora de ordem: product_control_codes
            for r, g in zip(ref_rows[i1:i2], gen_rows[j1:j2], strict=True):
                seen[r["code"]] += 1
                occurrence = f"{r['code']}#{seen[r['code']]}"
                r_cells, g_cells = r.get("cells") or [], g.get("cells") or []
                diffs = []
                for n in range(max(len(r_cells), len(g_cells))):
                    rv = r_cells[n] if n < len(r_cells) else None
                    gv = g_cells[n] if n < len(g_cells) else None
                    if _cell_key(rv) == _cell_key(gv):
                        continue
                    name = (PRODUCT_CONTROL_FIELDS[n] if n < len(PRODUCT_CONTROL_FIELDS)
                            else f"col{n + 1}")
                    diffs.append(self.diff(
                        "product_control_rows", scope, CRITICAL,
                        f"Controle de Produtos {block}, {occurrence} ({name}): referência "
                        f"{rv!r}, gerado {gv!r} (pág. {g.get('page')})",
                        value=occurrence, reference=rv, generated=gv,
                        context={"field": name, "page": g.get("page")}))
                equal += not diffs
                self.unit("product_control_rows", scope, diffs)
        return equal

    def _labels(self, block: str) -> None:
        def labels(facts: dict) -> list[str] | None:
            """Rótulos das colunas do bloco; recortes com rótulos diferentes viram uma lista
            de variantes, o que já diverge de qualquer referência coerente."""
            crops = [c for c in facts["product_control"]["crops"] if c["block"] == block]
            variants = list(dict.fromkeys(tuple(c["labels"] or ()) for c in crops))
            if not variants:
                return None
            if len(variants) == 1:
                return list(variants[0])
            return [" / ".join(v) for v in variants]

        ref_l, gen_l = labels(self.ref), labels(self.gen)
        scope = f"block:{block}"
        diffs = []
        if ref_l is not None and gen_l is not None and ref_l != gen_l:
            if len(ref_l) == len(gen_l):
                for n, (r, g) in enumerate(zip(ref_l, gen_l, strict=True), start=1):
                    if _fold(r) != _fold(g):
                        diffs.append(self.diff("product_control_labels", scope, MAJOR,
                                               f"coluna {n} do Controle de Produtos {block}: "
                                               f"{r!r} na referência, {g!r} no gerado",
                                               value=n, reference=r, generated=g))
            else:
                diffs.append(self.diff("product_control_labels", scope, MAJOR,
                                       f"colunas do Controle de Produtos {block}: "
                                       f"{ref_l} x {gen_l}", reference=ref_l, generated=gen_l))
        self.unit("product_control_labels", scope, diffs)

    def _roads(self) -> None:
        keys = sorted({k for k, s in self.ref["sections"].items() if s["roads"]}
                      | {k for k, s in self.gen["sections"].items() if s["roads"]})
        for key in keys:
            ref_r = set(self.ref["sections"].get(key, {}).get("roads", []))
            gen_r = set(self.gen["sections"].get(key, {}).get("roads", []))
            self._set_unit("roads", f"section:{key}", ref_r, gen_r, CRITICAL, f"rodovias em {key}")
        self._set_unit("roads", "document", set(self.ref["roads"]), set(self.gen["roads"]),
                       CRITICAL, "rodovias do documento")

    def _set_unit(self, check: str, scope: str, ref: set, gen: set, severity: str,
                  label: str) -> None:
        diffs = [self.diff(check, scope, severity, f"{label}: {v} falta no gerado",
                           kind="missing", value=v) for v in sorted(ref - gen)]
        diffs += [self.diff(check, scope, severity, f"{label}: {v} sobra no gerado",
                            kind="extra", value=v) for v in sorted(gen - ref)]
        self.unit(check, scope, diffs)

    def _identity(self) -> None:
        ref_id, gen_id = self.ref["identity"], self.gen["identity"]
        expected = self.report_number

        for part in ("cover", "presentation", "closing"):
            ref_nums = ref_id[part]["report_numbers"]
            gen_nums = gen_id[part]["report_numbers"]
            self.scalar_unit("report_number", part, ref_nums[0] if ref_nums else None,
                             gen_nums[0] if gen_nums else None, CRITICAL, f"número em {part}")
            if expected is not None:
                diffs = []
                if not gen_nums or any(n != expected for n in gen_nums):
                    diffs.append(self.diff("expected_report_number", part, CRITICAL,
                                           f"{part} do gerado diz {gen_nums}, "
                                           f"esperado nº {expected}",
                                           reference=expected, generated=gen_nums))
                self.unit("expected_report_number", part, diffs)

        for part in ("presentation", "closing"):
            ref_m = ref_id[part]["reference_months"]
            gen_m = gen_id[part]["reference_months"]
            self.scalar_unit("reference_month", part, ref_m[0] if ref_m else None,
                             gen_m[0] if gen_m else None, CRITICAL, f"mês de referência em {part}")
        gen_pm = gen_id["presentation"]["reference_months"][:1]
        gen_cm = gen_id["closing"]["reference_months"][:1]
        diffs = []
        if gen_pm != gen_cm:
            diffs.append(self.diff("internal_consistency", "reference_month", CRITICAL,
                                   f"gerado: Apresentação {gen_pm} x Encerramento {gen_cm}",
                                   reference=gen_pm, generated=gen_cm))
        self.unit("internal_consistency", "reference_month", diffs)

        self.scalar_unit("cover_date", "cover", ref_id["cover"]["date_iso"],
                         gen_id["cover"]["date_iso"], CRITICAL, "data da capa")
        self.scalar_unit("cover_date_text", "cover", ref_id["cover"]["date_text"],
                         gen_id["cover"]["date_text"], MINOR, "grafia da data da capa")
        self.scalar_unit("signature_date", "closing", ref_id["closing"]["signature_date_iso"],
                         gen_id["closing"]["signature_date_iso"], MAJOR, "data da assinatura")
        r_sig = ref_id["closing"].get("signatory_sha256")
        g_sig = gen_id["closing"].get("signatory_sha256")
        if "signatory_sha256" in ref_id["closing"] or "signatory_sha256" in gen_id["closing"]:
            diffs = []
            if r_sig != g_sig:  # só hashes: o nome não entra no relatório
                diffs.append(self.diff(
                    "signatory", "closing", CRITICAL,
                    f"signatário do Encerramento difere (hash referência {(r_sig or '-')[:10]}, "
                    f"gerado {(g_sig or '-')[:10]})", reference=r_sig, generated=g_sig))
            self.unit("signatory", "closing", diffs)

        ref_c, gen_c = ref_id["closing"], gen_id["closing"]
        for key, check, feminine, label in (
            ("declared_pages", "declared_pages", True, "páginas declaradas"),
            ("declared_annexes", "declared_annexes", False, "anexos declarados"),
        ):
            r = (ref_c.get(key) or {}).get("value")
            g = (gen_c.get(key) or {}).get("value")
            self.scalar_unit(check, "closing", r, g, CRITICAL, label, kind="delta")
            words = (gen_c.get(key) or {}).get("words")
            diffs = []
            if g is not None and (words is None or not _words_equal(
                    words, number_to_words_pt(g, feminine=feminine))):
                diffs.append(self.diff("declared_words", f"closing:{key}", MAJOR,
                                       f"{label}: {g} ({words}), esperado "
                                       f"({number_to_words_pt(g, feminine=feminine)})",
                                       reference=number_to_words_pt(g, feminine=feminine),
                                       generated=words))
            self.unit("declared_words", f"closing:{key}", diffs)

        diffs = []
        g_pages = (gen_c.get("declared_pages") or {}).get("value")
        if g_pages != self.gen["page_count"]:
            diffs.append(self.diff("internal_consistency", "declared_pages", CRITICAL,
                                   f"gerado declara {g_pages} páginas e tem "
                                   f"{self.gen['page_count']}",
                                   reference=self.gen["page_count"], generated=g_pages))
        self.unit("internal_consistency", "declared_pages", diffs)
        diffs = []
        g_annex = (gen_c.get("declared_annexes") or {}).get("value")
        g_rows = len(self.gen["product_control"]["blocks"].get("ANEXOS", []))
        if g_annex != g_rows:
            diffs.append(self.diff("internal_consistency", "declared_annexes", CRITICAL,
                                   f"gerado declara {g_annex} anexos e lista {g_rows} no índice",
                                   reference=g_rows, generated=g_annex))
        self.unit("internal_consistency", "declared_annexes", diffs)

    def _narrative(self) -> None:
        """Por seção (âncora de título): presença, fatos citados, cobertura e semelhança."""
        sim_min = self.tol["narrative_similarity_min"]
        cov_min = self.tol["narrative_coverage_min"]
        gap_max = self.tol["narrative_gap_max_words"]
        sims: dict[str, float] = {}
        narrative: dict[str, dict] = {}
        ref_sections, gen_sections = self.ref["sections"], self.gen["sections"]
        for key in list(dict.fromkeys(list(ref_sections) + list(gen_sections))):
            if key in NARRATIVE_EXCLUDED_SECTIONS:
                continue
            ref_s, gen_s = ref_sections.get(key), gen_sections.get(key)
            scope = f"section:{key}"
            ref_text = (ref_s or {}).get("text", "")
            gen_text = (gen_s or {}).get("text", "")
            diffs = []
            if ref_text and gen_s is None:
                diffs.append(self.diff("section_presence", scope, CRITICAL,
                                       f"seção {key} ({ref_s['title']!r}) falta no gerado",
                                       kind="missing", value=key))
            elif gen_text and ref_s is None:
                diffs.append(self.diff("section_presence", scope, CRITICAL,
                                       f"seção {key} ({gen_s['title']!r}) sobra no gerado",
                                       kind="extra", value=key))
            self.unit("section_presence", scope, diffs)
            if ref_s is None or gen_s is None:
                continue
            if ref_s.get("facts") is not None or gen_s.get("facts") is not None:
                self.facts_unit(scope, ref_s, gen_s, f"fatos citados em {key}")
            paragraph_stats = self._paragraphs(key, scope, ref_s, gen_s)
            if not ref_text:
                continue
            ref_prose = _prose_words(ref_text)
            ref_words = [_fold(w) for w in ref_prose]
            gen_words = [_fold(w) for w in _prose_words(gen_text)]
            matcher = SequenceMatcher(None, ref_words, gen_words, autojunk=False)
            matched = sum(b.size for b in matcher.get_matching_blocks())
            coverage = matched / len(ref_words)
            gaps = [(i2 - i1, i1) for tag, i1, i2, _, _ in matcher.get_opcodes()
                    if tag in ("delete", "replace")]
            longest, at = max(gaps) if gaps else (0, 0)
            ratio = matcher.ratio()
            sims[key] = round(ratio, 4)
            narrative[key] = {
                "coverage": round(coverage, 4), "longest_gap_words": longest,
                "similarity": round(ratio, 4),
                "facts_reference": len(ref_s.get("facts") or []),
                "facts_generated": len(gen_s.get("facts") or []),
                "words_reference": len(ref_words), "words_generated": len(gen_words),
                **(paragraph_stats or {}),
            }
            diffs = []
            if coverage < cov_min or longest > gap_max:
                excerpt = " ".join(ref_prose[at:at + min(longest, 12)])
                diffs.append(self.diff(
                    "narrative_coverage", scope, MAJOR,
                    f"texto de {key}: cobertura {coverage:.3f} (mín. {cov_min}), maior trecho "
                    f"da referência ausente {longest} palavras (máx. {gap_max}): "
                    f"{excerpt!r}...",
                    kind="delta", reference=len(ref_words), generated=matched,
                    context={"coverage": round(coverage, 4), "longest_gap_words": longest}))
            self.unit("narrative_coverage", scope, diffs)
            diffs = []
            if ratio < sim_min:
                diffs.append(self.diff("narrative_similarity", scope, MINOR,
                                       f"texto de {key}: similaridade {ratio:.3f} < {sim_min}",
                                       reference=sim_min, generated=round(ratio, 4)))
            self.unit("narrative_similarity", scope, diffs)
        self.metrics["narrative_similarity"] = sims
        self.metrics["narrative"] = narrative

    def _paragraphs(self, key: str, scope: str, ref_s: dict, gen_s: dict) -> dict | None:
        """Cobertura por parágrafo e parágrafo duplicado (v3.0). Parágrafos iguais (prosa com
        fatos pelo tipo, sem pontuação) são alinhados em ordem; cada parágrafo da referência
        fora do alinhamento precisa ter >= `paragraph_coverage_min` das suas palavras, em ordem,
        na região alinhada do gerado ou em algum parágrafo do gerado que sobrou (parágrafo
        movido). Sem `segments` (fatos de extrator < 3.0), nada a comparar."""
        if "segments" not in ref_s or "segments" not in gen_s:
            return None
        min_words = self.tol["paragraph_min_words"]
        cov_min = self.tol["paragraph_coverage_min"]
        rp = [s["text"] for s in ref_s["segments"] if s.get("kind") == "body"]
        gp = [s["text"] for s in gen_s["segments"] if s.get("kind") == "body"]
        rt = [_paragraph_tokens(t) for t in rp]
        gt = [_paragraph_tokens(t) for t in gp]
        matcher = SequenceMatcher(None, [tuple(t) for t in rt], [tuple(t) for t in gt],
                                  autojunk=False)
        aligned: set[int] = set()
        regions = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                aligned.update(range(j1, j2))
            else:
                regions.append((i1, i2, j1, j2))
        leftovers = [j for j in range(len(gt)) if j not in aligned]
        private = key.split("#")[0] == "ENCERRAMENTO"  # assinatura: sem trecho no relatório

        def excerpt(text: str) -> str:
            return "" if private else " " + repr(" ".join(text.split()[:12]) + "...")

        diffs = []
        worst = 1.0
        uncovered = 0
        for i1, i2, j1, j2 in regions:
            window = [tok for j in range(j1, j2) for tok in gt[j]]
            for i in range(i1, i2):
                if len(rt[i]) < min_words:
                    continue
                best = _containment(rt[i], window) if window else 0.0
                for j in leftovers:
                    if best >= cov_min:
                        break
                    best = max(best, _containment(rt[i], gt[j]))
                worst = min(worst, best)
                if best < cov_min:
                    uncovered += 1
                    diffs.append(self.diff(
                        "paragraph_coverage", scope, MAJOR,
                        f"parágrafo {i + 1} de {key} sem correspondente no gerado (melhor "
                        f"cobertura {best:.2f} < {cov_min}):{excerpt(rp[i])}",
                        kind="missing", value=_paragraph_hash(rp[i]), reference=i + 1,
                        generated=round(best, 3), context={"words": len(rt[i])}))
        self.unit("paragraph_coverage", scope, diffs)

        # Duplicado: o mesmo parágrafo (texto com fatos) mais vezes no gerado que na referência
        # DENTRO do mesmo bloco de rodovia (o texto padronizado do 2.2 repete as mesmas frases
        # em cada rodovia, DEC-007: isso não é duplicação).
        def blocked(section: dict) -> Counter:
            return Counter((s.get("block", ""), _fold(s["text"])) for s in section["segments"]
                           if s.get("kind") == "body")

        ref_count = blocked(ref_s)
        diffs = []
        for (block, text), n in blocked(gen_s).items():
            if n > 1 and n > ref_count.get((block, text), 0) and len(text.split()) >= min_words:
                original = next(t for t in gp if _fold(t) == text)
                where = f" [{block}]" if block else ""
                diffs.append(self.diff(
                    "paragraph_duplicate", scope, MAJOR,
                    f"parágrafo repetido {n}x em {key}{where} no gerado "
                    f"({ref_count.get((block, text), 0)}x na referência):{excerpt(original)}",
                    kind="extra", value=_paragraph_hash(original),
                    reference=ref_count.get((block, text), 0), generated=n,
                    context={"block": block}))
        self.unit("paragraph_duplicate", scope, diffs)
        return {"paragraphs_reference": len(rp), "paragraphs_generated": len(gp),
                "paragraphs_uncovered": uncovered, "paragraph_coverage_worst": round(worst, 4)}

    # -- figuras (conteúdo) -----------------------------------------------------------------

    def _figures(self) -> None:
        """Figuras raster pareadas por âncora e ordem: em branco, semelhança, rodovia da legenda
        e selo trocado (ver docstring do módulo para o que não é verificável)."""
        def rasters(facts: dict) -> dict[str, list[dict]]:
            out: dict[str, list[dict]] = {}
            for p in facts["pages"]:
                for f in p["figures"]:
                    if f["kind"] == "raster" and f["anchor"] not in FIGURE_CONTENT_EXCLUDED_ANCHORS:
                        out.setdefault(f["anchor"], []).append({**f, "page": p["index"]})
            return out

        blank_std = self.tol["figure_blank_std"]
        sim_min = self.tol["figure_similarity_min"]
        id_min, id_margin = self.tol["figure_identity_min"], self.tol["figure_identity_margin"]
        grid_cols, grid_margin = self.tol["figure_grid_columns"], self.tol["figure_grid_margin"]
        ref_f, gen_f = rasters(self.ref), rasters(self.gen)
        stats = {"pairs": 0, "blank": 0, "identity_verified": 0, "identity_unverifiable": 0,
                 "identity_swapped": 0, "similarity": {}, "label_scores": {},
                 "grid_distance": {}, "selector": {}, "region_delta": {},
                 "regions_sha256": self.regions.get("sha256")}
        for anchor in sorted(set(ref_f) | set(gen_f)):
            r_list, g_list = ref_f.get(anchor, []), gen_f.get(anchor, [])
            scope = f"anchor:{anchor}"
            templates = [(r.get("content") or {}).get("label", {}).get("template")
                         for r in r_list]
            ref_grids = [ink_grid(r.get("content"), grid_cols) for r in r_list]
            for n, (r, g) in enumerate(zip(r_list, g_list, strict=False), start=1):
                stats["pairs"] += 1
                value = f"{anchor}#{n}"
                where = (f"figura raster #{n} após {anchor} (pág. {g['page']}, "
                         f"legenda {g.get('caption_road') or '-'})")
                rc, gc = r.get("content") or {}, g.get("content") or {}
                diffs = []
                r_std, g_std = rc.get("gray_std"), gc.get("gray_std")
                similarity = thumb_similarity(rc, gc)
                stats["similarity"][value] = (round(similarity, 3) if similarity is not None
                                              else None)
                if g_std is not None and g_std < blank_std <= (r_std or 0):
                    stats["blank"] += 1
                    diffs.append(self.diff(
                        "figure_content", scope, CRITICAL,
                        f"{where}: painel em branco (desvio {g_std} < {blank_std}; "
                        f"referência {r_std})", kind="blank", value=value,
                        reference=r_std, generated=g_std, context={"figure_kind": "raster"}))
                elif similarity is not None and similarity < sim_min:
                    diffs.append(self.diff(
                        "figure_content", scope, CRITICAL,
                        f"{where}: conteúdo não se parece com a referência (correlação "
                        f"{similarity:.2f} < {sim_min})", kind="mismatch", value=value,
                        reference=sim_min, generated=round(similarity, 3),
                        context={"figure_kind": "raster"}))
                self.unit("figure_content", scope, diffs)

                diffs = []
                if r.get("caption_road") != g.get("caption_road"):
                    diffs.append(self.diff(
                        "figure_identity", scope, CRITICAL,
                        f"figura raster #{n} após {anchor}: legenda cita "
                        f"{r.get('caption_road')} na referência e {g.get('caption_road')} no "
                        "gerado", kind="caption", value=value,
                        reference=r.get("caption_road"), generated=g.get("caption_road")))
                area = gc.get("label", {}).get("area")
                scores = [label_match(t, area) for t in templates]
                stats["label_scores"][value] = [None if s is None else round(s, 3)
                                                for s in scores]
                own = scores[n - 1] if n - 1 < len(scores) else None
                known = [(s, j) for j, s in enumerate(scores) if s is not None]
                best, best_j = max(known) if known else (None, None)
                if (best is not None and best_j != n - 1 and best >= id_min
                        and best - (own if own is not None else 0.0) >= id_margin):
                    stats["identity_swapped"] += 1
                    other = r_list[best_j]
                    diffs.append(self.diff(
                        "figure_identity", scope, CRITICAL,
                        f"{where}: o selo casa com o painel #{best_j + 1} da referência "
                        f"(legenda {other.get('caption_road') or '-'}, {best:.2f}) e não com o "
                        f"seu par ({'-' if own is None else f'{own:.2f}'}): painel trocado",
                        kind="swapped", value=value, reference=n, generated=best_j + 1,
                        context={"figure_kind": "raster", "score_own": own,
                                 "score_best": best}))
                elif best is not None and best_j == n - 1 and best >= id_min:
                    stats["identity_verified"] += 1
                else:
                    stats["identity_unverifiable"] += 1
                diffs += self._grid_identity(value, where, n, g, r_list, ref_grids, grid_cols,
                                             grid_margin, stats)
                kind_cfg = ((self.regions.get("kinds") or {})
                            .get(panel_kind(self.regions, anchor, n) or "", {}))
                diffs += self._selector_identity(value, where, rc, gc, kind_cfg, stats)
                self.unit("figure_identity", scope, diffs)
                self._regions_unit(scope, value, where, rc, gc, kind_cfg, stats)
        self.metrics["figures"] = stats

    def _grid_identity(self, value: str, where: str, n: int, g: dict, r_list: list[dict],
                       ref_grids: list, columns: int, margin: float, stats: dict) -> list:
        """Painel trocado pela grade de tinta: outro painel da referência mais perto que o
        próprio par por `margin` (só discrimina painéis de conteúdo distinto, ex. 2.1.2)."""
        grid = ink_grid(g.get("content"), columns)
        dists = [grid_distance(grid, rg) for rg in ref_grids]
        stats["grid_distance"][value] = [None if d is None else round(d, 4) for d in dists]
        own = dists[n - 1] if n - 1 < len(dists) else None
        known = [(d, j) for j, d in enumerate(dists) if d is not None and j != n - 1]
        if own is None or not known:
            return []
        best, best_j = min(known)
        if best + margin >= own:
            return []
        stats["identity_swapped"] += 1
        return [self.diff(
            "figure_identity", f"anchor:{value.rsplit('#', 1)[0]}", CRITICAL,
            f"{where}: a grade de tinta casa com o painel #{best_j + 1} da referência "
            f"({best:.3f}) e não com o seu par ({own:.3f}): painel trocado",
            kind="swapped_grid", value=value, reference=n, generated=best_j + 1,
            context={"figure_kind": "raster", "distance_own": round(own, 4),
                     "distance_best": round(best, 4),
                     "other_caption": r_list[best_j].get("caption_road")})]

    def _selector_identity(self, value: str, where: str, rc: dict, gc: dict, kind_cfg: dict,
                           stats: dict) -> list:
        """Aba de rodovia destacada no seletor do painel (Power BI): tem de ser a mesma."""
        selector = kind_cfg.get("selector")
        if not selector:
            return []
        r_tab, g_tab = selected_tab(rc, selector), selected_tab(gc, selector)
        stats["selector"][value] = [r_tab, g_tab]
        if r_tab == g_tab:
            return []
        stats["identity_swapped"] += 1
        return [self.diff(
            "figure_identity", f"anchor:{value.rsplit('#', 1)[0]}", CRITICAL,
            f"{where}: aba de rodovia destacada {g_tab or '-'} no gerado e {r_tab or '-'} na "
            "referência: painel de outra rodovia", kind="selector", value=value,
            reference=r_tab, generated=g_tab, context={"figure_kind": "raster"})]

    def _regions_unit(self, scope: str, value: str, where: str, rc: dict, gc: dict,
                      kind_cfg: dict, stats: dict) -> None:
        """Delta de tinta nas regiões de texto/numerais do tipo de painel (raster_regions)."""
        regions = kind_cfg.get("regions") or {}
        if not regions:
            return
        cfg = self.regions
        diffs = []
        deltas = {}
        for name, region in regions.items():
            delta = region_delta(rc, gc, region["box"], subcell=cfg.get("subcell", 3),
                                 shift_rows=cfg.get("shift_rows", 0),
                                 shift_cols=cfg.get("shift_cols", 0))
            deltas[name] = None if delta is None else round(delta, 3)
            if delta is not None and delta > region["max_delta"]:
                diffs.append(self.diff(
                    "figure_region", scope, MAJOR,
                    f"{where}: região {name} difere da referência (delta de tinta {delta:.3f} "
                    f"> {region['max_delta']})", kind="region", value=f"{value}:{name}",
                    reference=region["max_delta"], generated=round(delta, 3),
                    context={"figure_kind": "raster", "region": name}))
        stats["region_delta"][value] = deltas
        self.unit("figure_region", scope, diffs)

    # -- VISUAL_GEOMETRY --------------------------------------------------------------------

    @staticmethod
    def figure_pairs(r_list: list[dict], g_list: list[dict], kind: str
                     ) -> list[tuple[int, dict, dict]]:
        """Pares (nº da figura da referência na âncora, ref, gerado).

        Raster: pela ordem na âncora (um painel por posição). Vetorial: pela PÁGINA dentro da
        âncora — a k-ésima página com figura vetorial da âncora contra a k-ésima — comparando a
        união dos agrupamentos da página. Um recorte do Controle de Produtos (um EMF por
        página, DEC-010) chega ao PDF em 1 a 5 agrupamentos que dependem do conteúdo (faixa de
        título com as setas do filtro, 18,64 cm; trechos do corpo, 17,50 cm); parear
        agrupamento a agrupamento, pela ordem global ou mesmo dentro da página, cruza os dois
        tipos quando a paginação difere. O nº do par é o do 1º agrupamento da página na
        referência (compatível com allowances que citam "ANEXOS#1").
        """
        if kind != "vector":
            return [(n, r, g) for n, (r, g) in enumerate(zip(r_list, g_list, strict=False),
                                                          start=1)]

        def pages(items: list[dict]) -> list[tuple[int, dict]]:
            grouped: dict[int, list[tuple[int, dict]]] = {}
            for n, f in enumerate(items, start=1):
                grouped.setdefault(f["page"], []).append((n, f))
            out = []
            for page in sorted(grouped):
                first, boxes = grouped[page][0][0], [f["bbox_cm"] for _, f in grouped[page]]
                box = [min(b[0] for b in boxes), min(b[1] for b in boxes),
                       max(b[2] for b in boxes), max(b[3] for b in boxes)]
                out.append((first, {"bbox_cm": box, "width_cm": round(box[2] - box[0], 3),
                                    "height_cm": round(box[3] - box[1], 3), "page": page,
                                    "fragments": len(boxes)}))
            return out

        return [(n, r, g) for (n, r), (_, g) in zip(pages(r_list), pages(g_list), strict=False)]

    def visual(self) -> None:
        def by_anchor(facts: dict) -> dict[tuple[str, str], list[dict]]:
            out: dict[tuple[str, str], list[dict]] = {}
            for p in facts["pages"]:
                for f in p["figures"]:
                    out.setdefault((f["anchor"], f["kind"]), []).append(
                        {**f, "page": p["index"]})
            return out

        ref_f, gen_f = by_anchor(self.ref), by_anchor(self.gen)
        tol = self.tol["bbox_cm"]
        for anchor, kind in sorted(set(ref_f) | set(gen_f)):
            r_list, g_list = ref_f.get((anchor, kind), []), gen_f.get((anchor, kind), [])
            scope = f"anchor:{anchor}"
            diffs = []
            if len(r_list) != len(g_list):
                diffs.append(self.diff("figure_count", scope, MAJOR,
                                       f"figuras {kind} após {anchor}: referência {len(r_list)}, "
                                       f"gerado {len(g_list)}", kind="delta", value=kind,
                                       reference=len(r_list), generated=len(g_list),
                                       context={"figure_kind": kind}))
            self.unit("figure_count", scope, diffs)
            for n, r, g in self.figure_pairs(r_list, g_list, kind):
                rb, gb = r["bbox_cm"], g["bbox_cm"]
                dx0 = abs(gb[0] - rb[0])
                dy0 = abs(gb[1] - rb[1])
                dw = abs(g["width_cm"] - r["width_cm"])
                dh = abs(g["height_cm"] - r["height_cm"])
                worst = max(dx0, dy0, dw, dh)
                diffs = []
                if worst > tol:
                    diffs.append(self.diff(
                        "figure_bbox", scope, MINOR,
                        f"figura {kind} #{n} após {anchor}: desvio {worst:.2f} cm "
                        f"(tolerância {tol})",
                        kind="delta", value=f"{anchor}#{n}", reference=rb, generated=gb,
                        context={"figure_kind": kind, "max_delta_cm": round(worst, 3),
                                 "horizontal_delta_cm": round(max(dx0, dw), 3),
                                 "vertical_delta_cm": round(max(dy0, dh), 3)}))
                self.unit("figure_bbox", scope, diffs)

        ref_fonts = set(self.ref["identity"]["cover"]["fonts"])
        gen_fonts = set(self.gen["identity"]["cover"]["fonts"])
        diffs = [self.diff("cover_fonts", "cover", MINOR, f"fonte da capa {v} falta no gerado",
                           kind="missing", value=v) for v in sorted(ref_fonts - gen_fonts)]
        diffs += [self.diff("cover_fonts", "cover", MINOR, f"fonte da capa {v} sobra no gerado",
                            kind="extra", value=v) for v in sorted(gen_fonts - ref_fonts)]
        self.unit("cover_fonts", "cover", diffs)

    # -- texto estrito (v4.0) ---------------------------------------------------------------

    def text(self) -> None:
        """Diff de texto estrito por unidade: cada hunk é CRITICAL salvo se casar EXATAMENTE,
        no MESMO lugar (v4.1: bloco, parágrafo no bloco, tokens da referência, bloco gerado),
        com um hunk aprovado. Aprovado que não ocorre é órfão (aviso); se for `pending`, o
        hunk real no mesmo parágrafo do mesmo bloco sai marcado."""
        approved: dict[tuple, ApprovedHunk] = {ah.key: ah for ah in self.hunks.hunks}
        used: set[str] = set()
        ref_units, gen_units = text_units(self.ref), text_units(self.gen)
        self.text_units = (ref_units, gen_units)
        by_unit = {s: diff_unit(ref_units.get(s), gen_units.get(s), s)
                   for s in dict.fromkeys(list(ref_units) + list(gen_units))}
        unit_diffs: dict[str, list[Difference]] = {}
        for scope, hunks in by_unit.items():
            diffs = []
            for h in hunks:
                d = self._hunk_diff(h)
                match = approved.get(h.key)
                if match is not None and match.id not in used:
                    used.add(match.id)
                    d.original_severity, d.severity = d.severity, ALLOWED
                    d.allowance_id, d.allowance_reference = match.id, match.reference_label
                    self.text_refs.setdefault(scope, set()).add(match.reference_label)
                    self.approved_by_unit.setdefault(scope, []).append((h, match))
                else:
                    match = None
                self.hunks_by_unit.setdefault(scope, []).append((h, match))
                diffs.append(d)
            unit_diffs[scope] = diffs
        self.orphans = [ah for ah in self.hunks.hunks if ah.id not in used]
        # Órfão "revertido": o gerado voltou a ter, no lugar do hunk, o texto da REFERÊNCIA
        # (contexto + texto de referência contíguos). O hunk aprovado é uma correção
        # justificada (anomalia ou DEC); reproduzir o publicado ali é regressão, CRITICAL.
        # v4.1: procurado só nos parágrafos gerados do bloco do hunk (o mesmo texto em outra
        # rodovia é legítimo lá).
        for ah in self.orphans:
            if ah.pending:
                continue
            unit = gen_units.get(ah.section)
            needle = [*ah.context_before, *(ah.reference_text.split(" ") if ah.reference_text
                                            else []), *ah.context_after]
            if unit is None or not needle:
                continue
            if not _run_at_block(unit, needle, len(ah.context_before),
                                 bool(ah.reference_text), ah.generated_block or ah.block):
                continue
            d = self.diff(
                "text_diff", ah.section, CRITICAL,
                f"texto de {ah.section} revertido ao publicado: o gerado tem de novo "
                f"«{ah.reference_text or '∅'}» onde o hunk aprovado {ah.id} "
                f"({ah.reference_label}) exige «{ah.generated_text or '∅'}»",
                kind="reverted", value=ah.anchor, reference=ah.reference_text,
                generated=ah.reference_text,
                context={"anchor": ah.anchor, "approved_hunk": ah.id,
                         "expected": ah.generated_text, "block": ah.block,
                         "context_before": list(ah.context_before),
                         "context_after": list(ah.context_after)})
            unit_diffs.setdefault(ah.section, []).append(d)
        pending = {(ah.section, ah.anchor, ah.block): ah for ah in self.orphans if ah.pending}
        n_pending = 0
        for scope, diffs in unit_diffs.items():
            open_ = False
            for d in diffs:
                if d.severity == ALLOWED:
                    continue
                ah = pending.get((scope, d.context.get("anchor"),
                                  (d.context.get("position") or {}).get("block")))
                if ah is not None:
                    d.context["pending"] = ah.pending
                    d.context["pending_hunk"] = ah.id
                    d.message += f" — PENDENTE: {ah.id} espera outro texto ({ah.pending})"
                    n_pending += 1
                else:
                    open_ = True
            if not diffs:
                state = "clean"
            elif open_:
                state = "open"
            elif any(d.severity != ALLOWED for d in diffs):
                state = "pending"
            else:
                state = "approved"
            self.text_state[scope] = state
            self.units.append(_Unit(CONTENT, "text_diff", scope, diffs))
        total = sum(len(v) for v in unit_diffs.values())
        n_approved = sum(d.severity == ALLOWED for v in unit_diffs.values() for d in v)
        self.metrics["text_diff"] = {
            "units": len(unit_diffs), "hunks": total, "approved": n_approved,
            "unapproved": total - n_approved, "pending": n_pending,
            "orphans": [ah.id for ah in self.orphans],
            "approved_hunks_version": self.hunks.version,
            "approved_hunks_sha256": self.hunks.sha256,
            "by_unit": {s: {"hunks": len(v), "approved": sum(d.severity == ALLOWED for d in v),
                            "state": self.text_state[s]}
                        for s, v in unit_diffs.items() if v},
            "v3_covered": 0,
        }
        self._toc()

    def _hunk_diff(self, h: Hunk) -> Difference:
        label = {"replace": "trocado", "insert": "inserido no gerado",
                 "delete": "removido no gerado"}[h.kind]
        return self.diff(
            "text_diff", h.unit, CRITICAL, f"texto de {h.unit} {label}: {h.describe()}",
            kind=h.kind, value=h.anchor, reference=h.reference_text, generated=h.generated_text,
            context={"anchor": h.anchor, "paragraph": h.paragraph, "position": h.position,
                     "context_before": list(h.context_before),
                     "context_after": list(h.context_after),
                     "reference_span": list(h.reference_span),
                     "generated_span": list(h.generated_span)})

    def _toc(self) -> None:
        """Sumário do gerado x títulos do próprio corpo: cada linha com o título e a página
        do título correspondente, na ordem (o sumário x referência é o `text_diff` do
        SUMARIO)."""
        entries = toc_entries(self.gen)
        heads = [(normalize_strict(h["label"]), h["page"]) for h in self.gen["headings"]
                 if h["key"] != "SUMARIO"]
        diffs = []
        last = -1
        for title, page in entries:
            idx = next((i for i, (t, _) in enumerate(heads) if t == title and i > last), None)
            if idx is None:
                idx = next((i for i, (t, _) in enumerate(heads) if t == title), None)
                if idx is None:
                    diffs.append(self.diff("toc_consistency", "toc", CRITICAL,
                                           f"sumário: {title!r} não é título do corpo",
                                           kind="missing", value=title, generated=page))
                    continue
                diffs.append(self.diff("toc_consistency", "toc", CRITICAL,
                                       f"sumário: {title!r} fora da ordem do corpo",
                                       kind="order", value=title, generated=page))
            if heads[idx][1] != page:
                diffs.append(self.diff("toc_consistency", "toc", CRITICAL,
                                       f"sumário: {title!r} na página {page}, no corpo "
                                       f"{heads[idx][1]}", kind="delta", value=title,
                                       reference=heads[idx][1], generated=page))
            last = max(last, idx)
        self.units.append(_Unit(CONTENT, "toc_consistency", "toc", diffs))
        self.metrics["toc"] = {"entries": len(entries), "headings": len(heads)}

    def _text_scopes(self, diff: Difference) -> list[str] | None:
        """Unidades de texto de onde vem uma diferença v3 (None = não derivada de texto)."""
        if diff.check not in TEXT_DERIVED_CHECKS:
            return None
        scope = diff.scope
        if scope.startswith(("section:", "block:")):
            return [scope]
        named = {"presentation": "APRESENTACAO", "closing": "ENCERRAMENTO"}
        part = scope.split(":", 1)[0]
        if part in named:
            keys = [k for facts in (self.ref, self.gen) for k, s in facts["sections"].items()
                    if fold(re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", s["title"])) == named[part]]
            return [f"section:{k}" for k in dict.fromkeys(keys)] or None
        if scope == "cover":
            return [f"section:{COVER_KEY}"]
        if scope == "document" and diff.check == "roads":
            # rodovia do documento: as seções que a citam (num lado ou no outro)
            keys = [k for facts in (self.ref, self.gen) for k, s in facts["sections"].items()
                    if diff.value in s.get("roads", [])]
            return [f"section:{k}" for k in dict.fromkeys(keys)] or None
        if scope == "document":
            return [s for s in self.text_state if s.startswith("block:")] or None
        return None

    def _paragraph_texts(self, facts: dict, unit: TextUnit, key: str,
                         paragraphs: set[int]) -> list[tuple[str, str, int]]:
        """(texto do segmento, bloco, parágrafo) dos parágrafos dados — o texto ORIGINAL do
        segmento (o mesmo que o extrator usou para os fatos)."""
        section = (facts.get("sections") or {}).get(key) or {}
        segments = section.get("segments") or []
        out = []
        for p in sorted(paragraphs):
            src = unit.paragraph_source[p]
            text = segments[src]["text"] if 0 <= src < len(segments) else unit.paragraphs[p]
            out.append((text, unit.paragraph_block[p], p))
        return out

    def _paragraph_facts(self, facts: dict, unit: TextUnit, key: str,
                         paragraphs: set[int]) -> Counter:
        """Fatos (bloco, fato) dos parágrafos dados, com o mesmo `narrative_facts` e as
        mesmas máscaras do extrator (por segmento, como `finish_section`)."""
        section = (facts.get("sections") or {}).get(key) or {}
        masks = section_masks(key, section.get("title", ""))
        out: Counter = Counter()
        for text, block, _ in self._paragraph_texts(facts, unit, key, paragraphs):
            out.update((block, fact) for fact in narrative_facts(text, masks))
        return out

    def _paragraph_codes(self, facts: dict, unit: TextUnit, key: str,
                         paragraphs: set[int]) -> Counter:
        return Counter(code for text, _, _ in self._paragraph_texts(facts, unit, key, paragraphs)
                       for code in text_codes(text))

    def _fact_pools(self, scope: str) -> dict:
        """O que os hunks APROVADOS da unidade explicam, julgado hunk a hunk (v4.1).

        Grupos de parágrafos (`textdiff.paragraph_groups`) sobre TODOS os hunks da unidade;
        só o grupo cujos hunks são todos aprovados explica alguma coisa — um hunk em aberto não
        contamina os outros grupos (QA4-E: um só hunk não aprovado derrubava todas as
        allowances `hunks:` da seção). Por grupo aprovado: fatos (bloco, fato) e códigos que
        faltam (referência - gerado) ou sobram (gerado - referência); `order` = presente dos
        dois lados; os parágrafos de referência e gerados do grupo."""
        pools = self._pools.get(scope)
        if pools is not None:
            return pools
        ref_units, gen_units = self.text_units
        ref_u, gen_u = ref_units.get(scope), gen_units.get(scope)
        pairs = self.hunks_by_unit.get(scope, [])
        key = scope.split(":", 1)[1]
        pools = {"missing": Counter(), "extra": Counter(), "order": set(), "ids": {},
                 "any_missing": Counter(), "any_extra": Counter(), "any_order": set(),
                 "codes_missing": Counter(), "codes_extra": Counter(), "codes_order": set(),
                 "ref_paragraphs": {}, "gen_paragraphs": {}}
        if ref_u is not None and gen_u is not None and any(ah for _, ah in pairs):
            ids = {id(h): (ah.id if ah else None) for h, ah in pairs}
            for ref_pars, gen_pars, hunks in paragraph_groups(ref_u, gen_u,
                                                              [h for h, _ in pairs]):
                names = sorted({ids[id(h)] for h in hunks if ids[id(h)]})
                if any(ids[id(h)] is None for h in hunks):
                    continue  # grupo com hunk em aberto: nada nele é explicado
                for p in ref_pars:
                    pools["ref_paragraphs"].setdefault(p, set()).update(names)
                for p in gen_pars:
                    pools["gen_paragraphs"].setdefault(p, set()).update(names)
                rf = self._paragraph_facts(self.ref, ref_u, key, ref_pars)
                gf = self._paragraph_facts(self.gen, gen_u, key, gen_pars)
                for kind, counter in (("missing", rf - gf), ("extra", gf - rf)):
                    pools[kind].update(counter)
                    for item in counter:
                        pools["ids"].setdefault((kind, *item), set()).update(names)
                        pools[f"any_{kind}"][item[1]] += counter[item]
                        pools["ids"].setdefault((f"any_{kind}", item[1]), set()).update(names)
                for item in set(rf) & set(gf):
                    pools["order"].add(item)
                    pools["ids"].setdefault(("order", *item), set()).update(names)
                for item in set(rf) | set(gf):
                    pools["any_order"].add(item[1])
                    pools["ids"].setdefault(("any_order", item[1]), set()).update(names)
                rc = self._paragraph_codes(self.ref, ref_u, key, ref_pars)
                gc = self._paragraph_codes(self.gen, gen_u, key, gen_pars)
                for kind, counter in (("codes_missing", rc - gc), ("codes_extra", gc - rc)):
                    pools[kind].update(counter)
                    for code in counter:
                        pools["ids"].setdefault((kind, code), set()).update(names)
                for code in set(rc) | set(gc):
                    pools["codes_order"].add(code)
                    pools["ids"].setdefault(("codes_order", code), set()).update(names)
        self._pools[scope] = pools
        return pools

    def _explained_fact(self, d: Difference) -> list[str] | None:
        """v4.1 (QA4-E): uma diferença `narrative_facts` só é consequência dos hunks se um
        hunk APROVADO do MESMO bloco a explicar exatamente (o mesmo fato, no mesmo bloco, entra
        ou sai entre os parágrafos ligados a ele). Devolve os ids dos hunks, ou None."""
        pools = self._fact_pools(d.scope)
        block = d.context.get("block") or ""
        item = (block, d.value)
        if d.kind in ("missing", "extra"):
            if pools[d.kind][item] <= 0:
                return None
            pools[d.kind][item] -= 1
        elif d.kind != "order":
            return None
        elif item not in pools["order"]:
            # Fato deslocado num bloco com o MESMO multiconjunto de fatos nos dois lados: o
            # bloco mudou de lugar na seção (ex.: ordem das rodovias, anomalia
            # P2.4_BM_EM_ELABORACAO_ORDEM do nº 13), sem fato a mais nem a menos nele. Fato que
            # muda de bloco é falta + sobra (nunca `order`) e não passa por aqui.
            ref_u, gen_u = (units.get(d.scope) for units in self.text_units)
            if not block or ref_u is None or gen_u is None:
                return None
            key = d.scope.split(":", 1)[1]
            rf = self._paragraph_facts(self.ref, ref_u, key, {
                p for p, b in enumerate(ref_u.paragraph_block) if b == block})
            gf = self._paragraph_facts(self.gen, gen_u, key, {
                p for p, b in enumerate(gen_u.paragraph_block) if b == block})
            if rf != gf:
                return None
            return [f"bloco {block} com os mesmos fatos, deslocado"]
        return sorted(pools["ids"].get((d.kind, *item), ()))

    def _explained_local(self, d: Difference) -> list[str] | None:
        """Diferença v3 LOCALIZÁVEL de uma seção, julgada pelo seu próprio hunk (v4.1):
        códigos (`text_codes`) e rodovias (`roads`) que entram/saem num grupo aprovado;
        parágrafo sem correspondente (`paragraph_coverage`) ou repetido
        (`paragraph_duplicate`) que está num grupo aprovado. None = não explicada."""
        pools = self._fact_pools(d.scope)
        if d.check == "narrative_facts":
            return self._explained_fact(d)
        if d.check == "text_codes":
            kind = {"missing": "codes_missing", "extra": "codes_extra",
                    "order": "codes_order"}.get(d.kind or "")
            if kind is None:
                return None
            if kind == "codes_order":
                return (sorted(pools["ids"].get((kind, d.value), ()))
                        if d.value in pools[kind] else None)
            if pools[kind][d.value] <= 0:
                return None
            pools[kind][d.value] -= 1
            return sorted(pools["ids"].get((kind, d.value), ()))
        if d.check == "roads":
            kind = f"any_{d.kind}"
            item = f"road:{d.value}"
            if d.kind in ("missing", "extra") and pools[kind][item] > 0:
                return sorted(pools["ids"].get((kind, item), ()))
            return None
        if d.check in ("paragraph_coverage", "paragraph_duplicate"):
            side, facts = (("ref", self.ref) if d.check == "paragraph_coverage"
                           else ("gen", self.gen))
            unit = self.text_units[0 if side == "ref" else 1].get(d.scope)
            if unit is None:
                return None
            key = d.scope.split(":", 1)[1]
            hits = [p for text, _, p in self._paragraph_texts(
                        facts, unit, key, set(range(len(unit.paragraphs))))
                    if _paragraph_hash(text) == d.value]
            names = set()
            for p in hits:
                names |= pools[f"{side}_paragraphs"].get(p, set())
            if not hits or not all(p in pools[f"{side}_paragraphs"] for p in hits):
                return None
            return sorted(names)
        return None

    def _explained_document_road(self, d: Difference) -> list[str] | None:
        """Rodovia que falta/sobra no documento: explicada só se, em CADA seção onde ela
        falta/sobra, um hunk aprovado dali a explicar."""
        side_has, side_lacks = ((self.ref, self.gen) if d.kind == "missing"
                                else (self.gen, self.ref))
        keys = [k for k, s in side_has["sections"].items() if d.value in s.get("roads", [])
                and d.value not in (side_lacks["sections"].get(k) or {}).get("roads", [])]
        if d.kind not in ("missing", "extra") or not keys:
            return None
        names: set[str] = set()
        for k in keys:
            probe = Difference(d.dimension, "roads", f"section:{k}", d.severity, "",
                               kind=d.kind, value=d.value)
            ids = self._explained_local(probe)
            if ids is None:
                return None
            names |= set(ids)
        return sorted(names)

    def _cover_by_hunks(self) -> None:
        """Diferenças v3 de conteúdo derivadas do texto, como diagnóstico redundante dos hunks.

        v4.1 — cada diferença é julgada pelo SEU hunk ou fato, não pela seção inteira
        (QA4-E: um hunk não aprovado derrubava todas as `hunks:section:*` da seção; e uma
        seção toda aprovada rebaixava fato de outro bloco):
          - LOCALIZÁVEIS numa seção (`narrative_facts`, `text_codes`, `roads`,
            `paragraph_coverage`, `paragraph_duplicate`): ALLOWED só se um grupo de
            parágrafos ligado a hunks APROVADOS (sem hunk em aberto) a explicar exatamente
            (`_explained_local`); o fato de status por rodovia/grupo exige o MESMO bloco.
            Senão continua bloqueante, marcada `unexplained`;
          - não localizáveis (semelhança/cobertura da seção inteira, identidade, linhas e
            códigos do Controle de Produtos, escopo `document`): regra do 4.0 — ALLOWED se
            nenhuma unidade de onde vêm tem hunk em aberto e alguma tem hunk aprovado."""
        covered = 0
        unexplained = 0
        for unit in self.units:
            for d in unit.diffs:
                if d.severity == ALLOWED or d.kind == "incomplete":
                    continue
                scopes = self._text_scopes(d)
                if not scopes:
                    continue
                localized = d.check in LOCALIZED_CHECKS and d.scope.startswith("section:")
                if d.check == "roads" and d.scope == "document":
                    localized = True
                if localized:
                    hunk_ids = (self._explained_document_road(d) if d.scope == "document"
                                else self._explained_local(d))
                    if hunk_ids is None:
                        d.context["unexplained"] = True
                        if self.approved_by_unit.get(d.scope):
                            d.message += (" — nenhum hunk aprovado deste lugar explica a "
                                          "diferença (v4.1)")
                        unexplained += 1
                        continue
                    d.original_severity, d.severity = d.severity, ALLOWED
                    d.allowance_id = f"hunks:{d.scope}"
                    d.allowance_reference = "hunks aprovados: " + ", ".join(hunk_ids)
                    covered += 1
                    continue
                states = [self.text_state.get(s, "clean") for s in scopes]
                if "open" in states or not any(s in ("approved", "pending") for s in states):
                    continue
                refs = sorted({r for s in scopes for r in self.text_refs.get(s, ())})
                d.original_severity, d.severity = d.severity, ALLOWED
                d.allowance_id = "hunks:" + (scopes[0] if len(scopes) == 1 else "document")
                d.allowance_reference = "hunks aprovados: " + "; ".join(refs)
                covered += 1
        if "text_diff" in self.metrics:
            self.metrics["text_diff"]["v3_covered"] = covered
            self.metrics["text_diff"]["v3_unexplained"] = unexplained

    # -- resultado --------------------------------------------------------------------------

    def _incomplete_items(self) -> None:
        """`items`/`pairs` são o conjunto EXATO de diferenças que a anomalia/DEC explica: tudo
        ou nada. Usada em parte (o gerado mudou num ponto já permitido, ex. um dos fatos da
        frase completada sumiu) = CRITICAL, não permitível. Sem uso = o gerado reproduz a
        referência naquele ponto (allowance sem uso, como sempre)."""
        for allowance in self.allowances:
            m = allowance.match
            if "items" not in m and "pairs" not in m:
                continue
            claimed = self.claimed.get(allowance.id, set())
            expected = ([("item", n) for n in range(len(m.get("items") or []))]
                        + [("pair", n, side) for n in range(len(m.get("pairs") or []))
                           for side in ("reference", "generated")])
            missing = [k for k in expected if k not in claimed]
            if not claimed or not missing:
                continue
            labels = []
            for key in missing:
                if key[0] == "item":
                    item = m["items"][key[1]]
                    labels.append(f"{item['kind']} {item['value']} [{item['block'] or '-'}]")
                else:
                    pair = m["pairs"][key[1]]
                    labels.append(f"{key[2]} {pair[key[2]]} [{pair['block']}]")
            scope = allowance.scopes[0]
            self.units.append(_Unit(CHECKS[allowance.check], allowance.check, scope, [
                self.diff(allowance.check, scope, CRITICAL,
                          f"{allowance.id} ({allowance.reference_label}) usada em parte: "
                          f"{len(expected) - len(missing)} de {len(expected)} diferenças "
                          f"esperadas; não ocorreram: {'; '.join(labels)}",
                          kind="incomplete", value=allowance.id,
                          reference=len(expected), generated=len(expected) - len(missing))]))

    def report(self) -> Report:
        self.structural()
        self.content()
        self.text()
        self.visual()
        self._incomplete_items()
        self._cover_by_hunks()
        differences = [d for u in self.units for d in u.diffs]
        dims = {}
        for dim in DIMENSIONS:
            units = [u for u in self.units if u.dimension == dim]
            dims[dim] = {"units": len(units), "passed": sum(not u.failed for u in units)}
        geo_units = [u for u in self.units if u.dimension in (STRUCTURAL, VISUAL_GEOMETRY)]
        structural_score = (sum(not u.failed for u in geo_units) / len(geo_units)
                            if geo_units else 1.0)
        content_units = [u for u in self.units if u.dimension == CONTENT
                         and u.check not in UNSCORED]
        content_accuracy = (sum(not u.failed for u in content_units) / len(content_units)
                            if content_units else 1.0)
        self.metrics.update({
            "structural_score": round(structural_score, 4),
            "content_accuracy": round(content_accuracy, 4),
            "dimensions": dims,
            "severity_counts": dict(Counter(d.severity for d in differences)),
        })
        reasons = []
        blocking = [d for d in differences if d.severity in (CRITICAL, MAJOR)]
        if blocking:
            reasons.append(f"{len(blocking)} diferença(s) CRITICAL/MAJOR sem allowance")
        if content_accuracy < 1.0:
            reasons.append(f"acurácia de conteúdo {content_accuracy:.4f} < 1.0")
        minimum = self.tol["structural_score_min"]
        if structural_score < minimum:
            reasons.append(f"score estrutural {structural_score:.4f} < {minimum}")
        verdict = "FAIL" if reasons else "PASS"
        if not reasons:
            reasons.append("sem diferença bloqueante; conteúdo 100%; score estrutural ok")
        all_ids = [a.id for a in self.allowances]
        warnings = list(self.allowance_set.warnings)
        for ah in self.orphans:
            what = (f"pendente ({ah.pending})" if ah.pending
                    else "o gerado não tem mais esse trecho")
            warnings.append(f"aprovação órfã: {ah.id} [{ah.section}, {ah.anchor}] não ocorre "
                            f"no diff ({what})")
        return Report(
            report_number=self.report_number,
            verdict=verdict,
            reasons=reasons,
            metrics=self.metrics,
            differences=differences,
            allowances_used=sorted(self.used),
            allowances_unused=[a for a in all_ids if a not in self.used],
            allowances_sha256=self.allowance_set.sha256,
            reference_source=self.ref.get("source"),
            generated_source=self.gen.get("source"),
            warnings=warnings,
            approved_hunks_sha256=self.hunks.sha256,
            approved_hunks_orphans=[ah.id for ah in self.orphans],
        )


def compare(
    reference_facts: dict,
    generated_facts: dict,
    allowances: AllowanceSet | None = None,
    *,
    report_number: int | None = None,
    raster_regions: dict | None = None,
    approved_hunks: HunkSet | None = None,
) -> Report:
    """Compara fatos de referência e gerados sob um conjunto CONGELADO de allowances.

    `report_number`: o número pedido ao gerador. Habilita a verificação não permitível
    `expected_report_number` e seleciona as allowances daquele relatório.
    `raster_regions`: configuração das regiões dos painéis (padrão: `raster_regions.yaml`).
    `approved_hunks` (v4.0): hunks de texto aprovados; padrão = o conjunto registrado nas
    allowances para o relatório (sha256 conferido) ou nenhum (todo hunk sai CRITICAL).
    """
    if allowances is None:
        allowances = AllowanceSet.empty()
    if allowances.status != "FROZEN":
        raise AllowanceError("comparação exige allowances congeladas")
    if approved_hunks is None:
        approved_hunks = allowances.approved_hunks(report_number)
    if approved_hunks.status != "FROZEN":
        raise AllowanceError("comparação exige hunks aprovados congelados")
    if approved_hunks.hunks and approved_hunks.report_number != report_number:
        raise AllowanceError(
            f"hunks aprovados do nº {approved_hunks.report_number} usados no nº {report_number}")
    if raster_regions is None:
        raster_regions = load_raster_regions()
    return _Comparator(reference_facts, generated_facts, allowances, report_number,
                       raster_regions, approved_hunks).report()
