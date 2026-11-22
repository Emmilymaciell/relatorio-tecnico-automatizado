"""Extração factual de um PDF do Relatório G2 — histórico ou gerado, pelo mesmo código.

Lê só o PDF (PyMuPDF). Não importa o builder nem o render: a régua do golden test não pode
depender do que ela mede (WAVE1_FINDINGS §H). Saída é um dict JSON-serializável:

    page_count, pages[]           orientação, tamanho, cabeçalho/rodapé, nº impresso, figuras
    orientation_runs              [["portrait", 6], ["landscape", 8], ...]
    headings[]                    títulos por fonte/tamanho/negrito, na ordem do documento
    sections{}                    texto normalizado, rodovias e códigos citados, por título;
                                  `facts` = números, datas, horas, meses e rodovias citados, na
                                  ordem do texto (v2.0); v3.0: também ordinais, cardinais por
                                  extenso, status (vocabulário fechado, qualificado pelo campo
                                  "Rótulo: valor"), negação, dias da semana e executoras do
                                  contrato; `segments` = parágrafos do corpo e linhas de quadro,
                                  na ordem; `fact_blocks` = bloco de rodovia de cada fato
    product_control               linhas do Controle de Produtos por bloco (2.1, 2.2, 2.4, ANEXOS):
                                  código e as seis células (v2.0: linha inteira, não só o código)
    identity                      número/mês na capa, Apresentação e Encerramento; contagens
                                  declaradas ("N (extenso) páginas", "N (extenso) anexos")
    pages[].figures[]             figuras por âncora; raster com miniatura em cinza, desvio-padrão,
                                  nº de cores, rodovia da legenda e recorte do selo (v2.0); v3.0:
                                  mapa de tinta a 300 dpi (`content.ink`)
    identity.closing              v3.0: `signatory_sha256` (o nome do signatário só por hash)

Heurísticas são constantes nomeadas deste módulo, calibradas nos PDFs nº 13 e nº 14 e válidas
para PDF exportado pelo Word. Mudá-las é mudar a régua: exige nova `EXTRACTOR_VERSION`.
"""

from __future__ import annotations

import base64
import hashlib
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

import pymupdf
import yaml

from prog_g2_report.report_id import MONTHS_PT, reference_month, strip_accents

# 1.1: código de documento quebrado no hífen de fim de linha ("NC-" + "025.1") é lido inteiro
#      (TEXT_CODE_RE); o nº 13 imprime "NC-525.1" no DOCX e o Word quebra a linha no hífen.
# 2.0: linhas inteiras do Controle de Produtos, fatos da narrativa por seção, descritores e
#      legenda das figuras raster (comparador 2.0).
# 3.0: fatos de narrativa ampliados (status, negação, ordinais — "1º" não é mais engolido pelo
#      `\w` —, cardinais por extenso, dias da semana, executoras), parágrafos e blocos de rodovia
#      por seção, hash do signatário e mapa de tinta das figuras raster (comparador 3.0).
# 3.1: status "aprovado com ressalva(s)" (APROVADO_COM_RESSALVA) no vocabulário fechado; o
#      resto da régua do 3.0 não muda (comparador 3.0).
# 3.2: `pages[].invisible_words` — palavras extraíveis sem tinta visível (branqueadas ou
#      cobertas; QA4-E MAJOR). O resto da régua do 3.1 não muda (comparador 4.1).
EXTRACTOR_VERSION = "3.2"

REPO_ROOT = Path(__file__).resolve().parents[3]
# Domínio fechado das executoras: o contrato (rodovias e empresas) e a agenda de reuniões que o
# modelo declara como fonte de `meetings_agenda`. Só leitura de configuração; nada do builder.
MODEL_CONFIG = REPO_ROOT / "config" / "g2_report_model.yaml"
AGENDA_CONFIG = REPO_ROOT / "config" / "data_rules" / "p21_executive_summary.yaml"

PT_PER_CM = 72 / 2.54
# Faixas de cabeçalho e rodapé: linha cujo y1 fica a até 1,75 cm do topo é cabeçalho; linha cujo
# y0 fica a até 1,2 cm da base é rodapé. No nº 14 o cabeçalho vai de 1,11 a 1,58 cm e o rodapé
# começa a 0,6 cm da base; a última linha de tabela (recorte encolhido à mão) começa a 1,8 cm.
HEADER_BAND_CM = 1.75
FOOTER_BAND_CM = 1.2
# Título = linha toda em negrito com corpo >= corpo do texto + 1,5 pt (13 pt contra 11 pt).
HEADING_DELTA_PT = 1.5
# Linhas cujo topo difere até 2 pt formam uma linha visual ("1" + tab + "APRESENTAÇÃO").
ROW_TOLERANCE_PT = 2.0
SPAN_GAP_FACTOR = 0.2
# Continuação de título quebrado em duas linhas: distância vertical < 0,6 x corpo do título.
HEADING_CONTINUATION_FACTOR = 0.6
# Figuras: raster com os dois lados >= 0,5 cm; abaixo disso (setas de autofiltro) só conta.
MIN_RASTER_CM = 0.5
# Vetorial: agrupamento de desenhos (tolerância 12 pt) com os dois lados >= 1 cm.
MIN_VECTOR_CM = 1.0
VECTOR_CLUSTER_TOLERANCE_PT = 12.0

COVER_KEY = "CAPA"
FRONT_KEY = "INICIO"

# Controle de Produtos: nomes das seis colunas, pela posição (o rótulo impresso da 2ª coluna
# varia entre "Parecer", "Manifestação" e "Tipo"; a posição não).
PRODUCT_CONTROL_FIELDS = ("code", "kind", "description", "road", "date", "status")
# Texto do recorte a mais de N pt (vertical) do centro da linha de código mais próxima não é
# célula (linha a 18,5 pt; descrição quebrada em 2 linhas fica a ±4,6 pt do código).
PC_ROW_ATTACH_PT = 12.0
COLUMN_START_SLACK_PT = 2.0

# Legenda de figura: até N linhas de corpo imediatamente antes da figura (sem passar por outra
# figura) são lidas, da mais próxima para a mais distante, até achar uma rodovia. nº 14: os
# quadros do 2.2.2 vêm depois de "...da Rodovia RD-103:" e os painéis de condicionantes do 2.4.2
# depois de "RD-101: Não apresenta condicionantes..." (2 linhas).
CAPTION_MAX_ROWS = 4
# Miniatura de figura raster: 32 colunas em cinza, linhas pela proporção (máx. 64).
THUMB_COLUMNS = 32
THUMB_MAX_ROWS = 64
# Cores distintas (RGB quantizado em 4 níveis por canal) com pelo menos 0,5% da área.
COLOR_LEVELS = 4
COLOR_MIN_SHARE = 0.005
# Selo do painel: recorte em cinza (zoom 2) do canto inferior esquerdo, onde os painéis Power BI
# do 2.2.2 (nº 13/14) trazem a rodovia ("RD-103"). `template` é o recorte justo (usado da
# referência) e `area` a janela de busca, mais larga (usada do gerado). Em figuras sem selo o
# recorte existe, mas não discrimina: o comparador detecta isso e não conclui nada.
LABEL_TEMPLATE_FRAC = (0.02, 0.925, 0.13, 0.985)
LABEL_AREA_FRAC = (0.0, 0.89, 0.16, 1.0)
LABEL_ZOOM = 2.0

# Fatos da narrativa: rodovias, datas, horas, meses e números, na ordem do texto. Códigos de
# documento ficam fora (comparados em `text_codes`); nas seções de identidade (Apresentação e
# Encerramento) o número do relatório, o mês/ano de referência, as contagens declaradas e a
# data da assinatura também ficam fora (verificações próprias, com suas allowances).
_MONTH_NAMES = ("janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|setembro|outubro"
                "|novembro|dezembro")


def _acc(word: str) -> str:
    """Padrão tolerante a acento para uma palavra em ASCII: 'analise' casa 'análise'."""
    classes = {"a": "[aáàâã]", "e": "[eéê]", "i": "[ií]", "o": "[oóôõ]", "u": "[uúü]",
               "c": "[cç]"}
    return "".join(classes.get(ch, re.escape(ch) if ch not in " " else r"\s+")
                   for ch in word)


# v3.0 — status com vocabulário FECHADO (contrato do relatório: Aprovado/Aprovado com ressalva
# (3.1)/Não aprovado/Reprovado/
# Em análise/Aceito/Aceitação/Aprovação/Pendente/Atrasado/Entregue/Em elaboração/No prazo/
# Próximo do vencimento), flexões de gênero e número normalizadas para o termo canônico. A forma
# negada vem antes da afirmativa (alternação da esquerda para a direita).
STATUS_TERMS: tuple[tuple[str, str], ...] = (
    ("NAO_APROVADO", _acc("nao aprovad") + "[oa]s?"),
    ("NAO_ACEITO", _acc("nao aceit") + "[oa]s?"),
    ("NAO_ENTREGUE", _acc("nao entregue") + "s?"),
    ("REPROVADO", _acc("reprovad") + "[oa]s?"),
    # 3.1: o qualificador da avaliação (Projetos!S 'Aprovado com ressalva(s)') é fato: trocar
    # "aprovado" por "aprovado com ressalva" (ou o contrário) muda o fato.
    ("APROVADO_COM_RESSALVA", _acc("aprovad") + "[oa]s?" + r"\s+com\s+ressalvas?"),
    ("APROVADO", _acc("aprovad") + "[oa]s?"),
    ("ACEITO", _acc("aceit") + "[oa]s?"),
    ("ACEITACAO", _acc("aceitacao")),
    ("APROVACAO", _acc("aprovacao")),
    ("EM_ANALISE", _acc("em analise")),
    ("PENDENTE", _acc("pendente") + "s?"),
    ("ATRASADO", _acc("atrasad") + "[oa]s?|" + _acc("em atraso")),
    ("ENTREGUE", _acc("entregue") + "s?"),
    ("EM_ELABORACAO", _acc("em elaboracao")),
    ("NO_PRAZO", _acc("no prazo")),
    ("PROXIMO_VENCIMENTO", _acc("proxim") + r"[oa]s?\s+(?:ao|do|[àa])\s+" + _acc("venc")
     + "(?:er|" + _acc("imento") + ")"),
)
# Negação como fato: "não há", "não houve", "nenhum(a)", "sem" e qualquer outro "não".
NEGATION_TERMS: tuple[tuple[str, str], ...] = (
    ("NAO_HA", _acc("nao ha")),
    ("NAO_HOUVE", _acc("nao houve")),
    ("NENHUM", _acc("nenhum") + "a?s?"),
    ("SEM", "sem"),
    ("NAO", _acc("nao")),
)
WEEKDAY_TERMS: tuple[tuple[str, str], ...] = (
    ("SEGUNDA", "segundas?(?:-feiras?)?"),
    ("TERCA", _acc("terca") + "s?(?:-feiras?)?"),
    ("QUARTA", "quartas?(?:-feiras?)?"),
    ("QUINTA", "quintas?(?:-feiras?)?"),
    ("SEXTA", "sextas?(?:-feiras?)?"),
    ("SABADO", _acc("sabado") + "s?"),
    ("DOMINGO", "domingos?"),
)
# Cardinais por extenso (pt-BR) -> número. "um"/"uma" sozinhos são artigo, não fato; dentro de
# um composto ("vinte e um") contam.
NUMBER_WORDS: dict[str, int] = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
    "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13,
    "quatorze": 14, "catorze": 14, "quinze": 15, "dezesseis": 16, "dezasseis": 16,
    "dezessete": 17, "dezassete": 17, "dezoito": 18, "dezenove": 19, "dezanove": 19,
    "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70,
    "oitenta": 80, "noventa": 90, "cem": 100, "cento": 100, "duzentos": 200, "duzentas": 200,
    "trezentos": 300, "trezentas": 300, "quatrocentos": 400, "quatrocentas": 400,
    "quinhentos": 500, "quinhentas": 500, "seiscentos": 600, "seiscentas": 600,
    "setecentos": 700, "setecentas": 700, "oitocentos": 800, "oitocentas": 800,
    "novecentos": 900, "novecentas": 900, "mil": 1000,
}
_NUMBER_WORD_ALT = "|".join(_acc(w) for w in sorted(NUMBER_WORDS, key=len, reverse=True))
_ARTICLES = frozenset({"um", "uma"})


def _alternation(terms: tuple[tuple[str, str], ...]) -> str:
    return "|".join(f"(?:{pattern})" for _, pattern in terms)


def _canonical(terms: tuple[tuple[str, str], ...], value: str) -> str:
    for name, pattern in terms:
        if re.fullmatch(pattern, value, re.IGNORECASE):
            return name
    return fold(value).replace(" ", "_")  # pragma: no cover - a alternação garante o casamento


def _load_companies(model: Path = MODEL_CONFIG, agenda: Path = AGENDA_CONFIG) -> tuple[str, ...]:
    """Nomes das executoras: `contract.highways[].environmental_company` do modelo e as
    executoras da agenda de reuniões (`config.meetings[].executora`). Arquivo ausente = vazio."""
    names: list[str] = []
    try:
        data = yaml.safe_load(model.read_text(encoding="utf-8")) or {}
        names += [h.get("environmental_company") for h in
                  (data.get("contract") or {}).get("highways") or []]
    except (OSError, yaml.YAMLError):
        pass
    try:
        data = yaml.safe_load(agenda.read_text(encoding="utf-8")) or {}
        names += [m.get("executora") for m in (data.get("config") or {}).get("meetings") or []]
    except (OSError, yaml.YAMLError):
        pass
    def key(name: str) -> str:
        return " ".join(strip_accents(name).upper().split())

    unique = {key(n): n for n in names if isinstance(n, str) and n.strip()}
    return tuple(sorted(unique.values(), key=lambda n: (-len(n), key(n))))


COMPANIES = _load_companies()


def _company_pattern(names: tuple[str, ...]) -> str:
    alts = [r"\s+".join(_acc(strip_accents(part).lower()) for part in name.split())
            for name in names]
    return "|".join(alts) if alts else r"(?!x)x"


def build_fact_re(companies: tuple[str, ...] = COMPANIES) -> re.Pattern:
    """Regex dos fatos da narrativa, na ordem de prioridade da alternação."""
    return re.compile(
        r"(?P<code>\b[A-Z]{2,4}-\s?\d{3}\.\d\b)"  # com o hífen de fim de linha (TEXT_CODE_RE)
        r"|(?P<road>\bRD\s?[-–]?\s?\d{3}[A-Za-z]?\b)"
        r"|(?P<date>(?<![\w/])\d{1,2}/\d{1,2}(?:/\d{2,4})?(?![\w/]))"
        r"|(?P<time>(?<!\w)\d{1,2}h(?:\d{2})?(?!\w))"
        rf"|(?P<month>\b(?:{_MONTH_NAMES})\b(?:\s*/\s*\d{{4}})?)"
        # v3.0: "1º", "2ª", "1°" (o "º" é \w e fazia o número sumir)
        r"|(?P<ordinal>(?<![\w.,/])\d{1,3}\s?[ºª°](?![^\W\d_]))"
        r"|(?P<number>(?<![\w.,/])\d+(?:[.,/]\d+)*(?!\w))"
        rf"|(?P<status>(?<!\w)(?:{_alternation(STATUS_TERMS)})(?!\w))"
        rf"|(?P<neg>(?<!\w)(?:{_alternation(NEGATION_TERMS)})(?!\w))"
        rf"|(?P<weekday>(?<!\w)(?:{_alternation(WEEKDAY_TERMS)})(?!\w))"
        rf"|(?P<company>(?<!\w)(?:{_company_pattern(companies)})(?!\w))"
        rf"|(?P<numword>(?<!\w)(?:{_NUMBER_WORD_ALT})"
        rf"(?:\s+e\s+(?:{_NUMBER_WORD_ALT})|\s+mil)*(?!\w))",
        re.IGNORECASE,
    )


FACT_RE = build_fact_re()
# 3.1 — disciplina citada no VALOR de um campo ("o Disciplinas pendentes de aprovação: Projeto
# de Terraplenagem e Projeto de Pavimentação;" -> discipline:TERRAPLENAGEM@DISCIPLINAS
# PENDENTES DE APROVACAO, discipline:PAVIMENTACAO@...). Vocabulário FECHADO pelo termo que
# distingue a disciplina nas formas longa (planilha) e curta (texto histórico): "Projeto de
# Drenagem" e "Projeto de Drenagem e Obra de Arte Corrente (OAC)" são DRENAGEM. Mudar uma
# disciplina de lista (pendente -> em análise) muda o fato. Fora de campo não é fato (a prosa
# do 2.1 cita disciplinas por tema, sem conjunto). Não entra no FACT_RE: a máscara da
# similaridade (`mask_facts`) não muda.
DISCIPLINE_TERMS: tuple[tuple[str, str], ...] = (
    ("ATIVIDADES_PRELIMINARES", _acc("atividades preliminares")),
    ("TRAFEGO", _acc("trafego")),
    ("TOPOGRAFICOS", _acc("topografic") + "[oa]s?"),
    ("GEOLOGICOS", _acc("geologic") + "[oa]s?"),
    ("DAP", _acc("diagnostico ambiental previo")),
    ("DUP", _acc("utilidade publica")),
    ("HIDROLOGICOS", _acc("hidrologic") + "[oa]s?"),
    ("GEOTECNICOS", _acc("geotecnic") + "[oa]s?"),
    ("GEOMETRICO", _acc("geometric") + "[oa]s?"),
    ("TERRAPLENAGEM", _acc("terraplenagem")),
    ("DRENAGEM", _acc("drenagem")),
    ("PAVIMENTACAO", _acc("pavimentacao")),
    ("SINALIZACAO", _acc("sinalizacao")),
    ("DESAPROPRIACAO", _acc("desapropriacao")),
    ("COMPONENTE_AMBIENTAL", _acc("componente ambiental")),
    ("PAISAGISMO", _acc("paisagismo")),
    ("INTERFERENCIA", _acc("interferencia") + "s?"),
    ("ORCAMENTO", _acc("orcamento") + "s?"),
    ("CRONOGRAMA", _acc("cronograma") + "s?"),
    ("OAE", _acc("obra") + r"s?\s+de\s+arte\s+" + _acc("especia") + "(?:l|is)"),
    ("MEMORIAIS_ESTRUTURAL", _acc("memoriais de calculo estrutural")),
)
DISCIPLINE_RE = re.compile(rf"(?<!\w)(?:{_alternation(DISCIPLINE_TERMS)})(?!\w)", re.IGNORECASE)
NARRATIVE_EXCLUDED_SECTIONS = frozenset({COVER_KEY, "SUMARIO"})
# Tipos de fato qualificados pelo campo ("• Análise Programa: Aprovado;" -> status:APROVADO@ANALISE
# PROGRAMA): trocar o rótulo de dois campos com o mesmo status muda o fato.
QUALIFIED_KINDS = frozenset({"status", "neg"})
# Item de lista: marcador próprio (span do "•"/"o" do Word) ou "A)", "a)", "I.", "II.".
LIST_GLYPHS = frozenset({"•", "o", "▪", "◦", "‣", "-", "–", "", "", "§"})
TEXT_MARKER_RE = re.compile(r"^(?:[A-Za-z]\)|[IVXivx]{1,4}\.)\s")
# Campo "Rótulo: valor" num parágrafo (rótulo curto, sem ponto/ponto e vírgula).
FIELD_RE = re.compile(r"^(?P<label>[^:;.]{2,80}?)\s*:\s+(?P<value>\S.*)$")
FIELD_LABEL_MAX_WORDS = 6
# Âncora de bloco de rodovia: parágrafo que começa pela rodovia ("A) RD-103:", "• RD-101: ...")
# ou parágrafo curto terminado em ":" com uma única rodovia ("...da Rodovia RD-103:").
ROAD_LEAD_RE = re.compile(
    r"^(?:[A-Za-z]\)\s*|[•▪◦o]\s+){0,2}RD\s?[-–]?\s?(\d{3})([A-Za-z]?)\s*:")
ROAD_ANCHOR_MAX_WORDS = 14
# Parágrafos: linhas do corpo a mais de N pt (vertical) da anterior abrem parágrafo (linha a
# 2,8 pt; espaço entre parágrafos 8,8 pt no nº 13/14). Na troca de página, a última linha curta
# (acaba antes da margem direita menos N pt) fecha o parágrafo.
PARAGRAPH_GAP_PT = 5.0
PARAGRAPH_SHORT_LINE_PT = 40.0

CODE_RE = re.compile(r"\b[A-Z]{2,4}-\d{3}\.\d\b")
CODE_FULL_RE = re.compile(r"[A-Z]{2,4}-\d{3}\.\d")
# Códigos citados no texto corrido: o hífen pode fechar a linha do PDF e a junção das linhas põe
# um espaço ("NC- 525.1"), como já acontece com as rodovias ("RD- 101", ROAD_RE).
TEXT_CODE_RE = re.compile(r"\b([A-Z]{2,4})-\s?(\d{3}\.\d)\b")
ROAD_RE = re.compile(r"\bRD\s?[-–]?\s?(\d{3})([A-Za-z]?)\b")
HEADING_NUMBER_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s*([^\d\s.].*)$")
PRODUCT_CONTROL_TITLE_RE = re.compile(r"^Programa\s*\|\s*Controle de Produtos$", re.IGNORECASE)
REPORT_NUMBER_RE = re.compile(r"Relat[óo]rio\s+Mensal\s+N\s*[°º.]?\s*(\d{1,3})\b", re.IGNORECASE)
MONTH_REF_RE = re.compile(
    r"\b(janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro"
    r"|dezembro)\s*/\s*(\d{4})\b",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b(\d{1,2})\s*de\s+([A-Za-zÀ-ÿ]+)\s+de\s+(\d{4})\b")
SIGNATURE_RE = re.compile(r"Capital\s*,\s*(\d{1,2}\s*de\s+[A-Za-zÀ-ÿ]+\s+de\s+\d{4})")
DECLARED_PAGES_RE = re.compile(r"\b(\d+)\s*\(([^)]*)\)\s*p[áa]ginas", re.IGNORECASE)
DECLARED_ANNEXES_RE = re.compile(r"\b(\d+)\s*\(([^)]*)\)\s*anexos", re.IGNORECASE)
# Signatário: o nome entre a data da assinatura e "Programa" (título "Eng°"/"Eng." fora). Só o hash
# sai dos fatos de identidade (o nome não vai para o relatório de comparação).
SIGNATORY_RE = re.compile(
    r"Capital\s*,\s*\d{1,2}\s*de\s+[A-Za-zÀ-ÿ]+\s+de\s+\d{4}\s+"
    r"(?:(?:Eng|Enga|Arq|Dr|Dra)\s?[º°ª.]?\s+)?(?P<name>[^\d–\-|]+?)\s+(?:Programa|Cons[óo]rcio)\b"
)
PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")
# Mapa de tinta das figuras raster (v3.0): renderização a INK_DPI em cinza; fundo local = mediana
# de blocos de 1/INK_BG_BLOCKS da largura; pixel com |cinza - fundo| > INK_DELTA é tinta; mapa
# com INK_COLUMNS colunas e células quadradas (linhas pela altura), fração de tinta x 255.
INK_DPI = 300
INK_BG_BLOCKS = 24
INK_DELTA = 60
INK_COLUMNS = 96
# Visibilidade do texto (v3.2, `invisible_words`): página renderizada a VISIBILITY_DPI; na bbox
# de cada palavra, pixel de tinta = destoa do fundo (mediana da bbox) mais que
# VISIBILITY_INK_DELTA e está a menos de max(VISIBILITY_COLOR_TOL, 60% do contraste) da cor do
# texto. Invisível: fração de tinta < VISIBILITY_MIN_INK ou contraste < VISIBILITY_MIN_CONTRAST.
# Calibrado nos 14_v6/13_v6 e nos publicados nº 13/14 (0 palavra invisível nos gerados).
VISIBILITY_DPI = 110
VISIBILITY_INK_DELTA = 40
VISIBILITY_COLOR_TOL = 60
VISIBILITY_MIN_INK = 0.03
VISIBILITY_MIN_CONTRAST = 50


# --------------------------------------------------------------------------- normalização


def normalize_text(text: str) -> str:
    """NFC, espaços especiais viram espaço comum, espaços colapsados, bordas aparadas."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace(" ", " ").replace(" ", " ").replace("​", "")
    return re.sub(r"\s+", " ", text).strip()


def fold(text: str) -> str:
    """Forma de comparação: sem acento, maiúscula, espaços normalizados."""
    return strip_accents(normalize_text(text)).upper()


def normalize_road(number: str, suffix: str) -> str:
    """'RD 102a' -> 'RD-102A'. Não completa sufixo: 'RD-102' continua 'RD-102'."""
    return f"RD-{number}{suffix.upper()}"


def parse_date_pt(text: str) -> str | None:
    """'08 de Setembro de 2026' (ou '11de Agosto de 2026') -> '2026-09-08'."""
    match = DATE_RE.search(text)
    if not match:
        return None
    day, month_name, year = match.groups()
    month = MONTHS_PT.get(strip_accents(month_name).lower())
    if month is None:
        return None
    return f"{int(year):04d}-{month:02d}-{int(day):02d}"


def _cm(value: float) -> float:
    return round(value / PT_PER_CM, 3)


def _bbox_cm(rect) -> list[float]:
    return [_cm(rect[0]), _cm(rect[1]), _cm(rect[2]), _cm(rect[3])]


# --------------------------------------------------------------------------- estruturas


@dataclass
class _Span:
    text: str
    font: str
    size: float
    bold: bool
    x0: float
    x1: float


@dataclass
class _Line:
    x0: float
    y0: float
    x1: float
    y1: float
    spans: list[_Span]

    @property
    def text(self) -> str:
        # Tab do Word vira lacuna horizontal entre spans ("2.1" + tab + "Produto"): lacuna
        # maior que SPAN_GAP_FACTOR x corpo conta como espaço.
        parts: list[str] = []
        prev: _Span | None = None
        for span in self.spans:
            if (prev is not None and span.x0 - prev.x1 > SPAN_GAP_FACTOR * span.size
                    and not prev.text.endswith(" ") and not span.text.startswith(" ")):
                parts.append(" ")
            parts.append(span.text)
            prev = span
        return normalize_text("".join(parts))


@dataclass
class _Row:
    lines: list[_Line] = field(default_factory=list)

    @property
    def y0(self) -> float:
        return min(line.y0 for line in self.lines)

    @property
    def y1(self) -> float:
        return max(line.y1 for line in self.lines)

    @property
    def x0(self) -> float:
        return min(line.x0 for line in self.lines)

    @property
    def x1(self) -> float:
        return max(line.x1 for line in self.lines)

    @property
    def spans(self) -> list[_Span]:
        return [s for line in sorted(self.lines, key=lambda ln: ln.x0) for s in line.spans
                if s.text.strip()]

    @property
    def text(self) -> str:
        ordered = sorted(self.lines, key=lambda ln: ln.x0)
        return normalize_text(" ".join(line.text for line in ordered))

    @property
    def all_bold(self) -> bool:
        spans = self.spans
        return bool(spans) and all(s.bold for s in spans)

    @property
    def min_size(self) -> float:
        return min((s.size for s in self.spans), default=0.0)


def _is_bold(span: dict) -> bool:
    return bool(span["flags"] & 16) or "bold" in span["font"].lower()


def _page_lines(page) -> list[_Line]:
    lines: list[_Line] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for raw in block["lines"]:
            spans = [
                _Span(s["text"], s["font"], round(s["size"], 2), _is_bold(s), s["bbox"][0],
                      s["bbox"][2])
                for s in raw["spans"]
                if s["text"].strip()
            ]
            if spans:
                x0, y0, x1, y1 = raw["bbox"]
                lines.append(_Line(x0, y0, x1, y1, spans))
    return lines


def _rows(lines: list[_Line]) -> list[_Row]:
    rows: list[_Row] = []
    for line in sorted(lines, key=lambda ln: (ln.y0, ln.x0)):
        if rows and abs(line.y0 - rows[-1].lines[0].y0) <= ROW_TOLERANCE_PT:
            rows[-1].lines.append(line)
        else:
            rows.append(_Row([line]))
    return rows


def _heading_parts(text: str) -> tuple[str | None, str]:
    match = HEADING_NUMBER_RE.match(text)
    if match:
        return match.group(1), normalize_text(match.group(2))
    return None, normalize_text(text)


def _heading_key(number: str | None, text: str) -> str:
    return number if number else fold(text)


def _block_key(heading: dict | None) -> str:
    """Bloco de primeiro/segundo nível: '2.4.2' -> '2.4'; 'ANEXOS' -> 'ANEXOS'."""
    if heading is None:
        return FRONT_KEY
    if heading["number"]:
        return ".".join(heading["number"].split(".")[:2])
    return heading["key"]


def _ordered_unique(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return list(seen)


def _row_road(text: str) -> str | None:
    """Célula 'Empreendimento' de uma linha do Controle de Produtos: rodovia ou 'Geral'."""
    value = normalize_text(text)
    match = ROAD_RE.fullmatch(value)
    if match:
        return normalize_road(*match.groups())
    return "Geral" if value == "Geral" else None


def text_codes(text: str) -> list[str]:
    """Códigos de documento citados no texto, na ordem, normalizados para 'XX-NNN.N'."""
    return [f"{prefix}-{number}" for prefix, number in TEXT_CODE_RE.findall(text)]


def _roads(text: str) -> list[str]:
    return [normalize_road(n, s) for n, s in ROAD_RE.findall(text)]


def _continues(previous: int, value: int) -> bool:
    """'quarenta' + 'e três' compõe; 'cinco' + 'e quatro' não (são dois números)."""
    if value == 1000:
        return previous < 1000
    if previous == 1000:
        return value < 1000
    if previous >= 100:
        return value < 100
    if 20 <= previous <= 90:
        return value < 10
    return False


def number_word_groups(text: str, offset: int = 0) -> list[tuple[int, int, int]]:
    """Números por extenso de um trecho: (valor, início, fim). 'quarenta e três' -> 43;
    'cento e quarenta e nove' -> 149; 'dois mil' -> 2000; 'cinco e quatro' -> 5 e 4; 'uma'
    sozinho é artigo e fica de fora."""
    groups: list[list] = []
    previous = None
    for match in re.finditer(r"[^\W\d_]+", text):
        word = strip_accents(match.group(0)).lower()
        if word == "e":
            continue
        value = NUMBER_WORDS[word]
        start, end = offset + match.start(), offset + match.end()
        if groups and previous is not None and _continues(previous, value):
            group = groups[-1]
            if value == 1000:
                group[0] = (group[0] or 1) * 1000
            else:
                group[0] += value
            group[2], group[3] = end, False
        else:
            groups.append([value, start, end, word in _ARTICLES])
        previous = value
    return [(v, s, e) for v, s, e, article in groups if not article]


def iter_facts(text: str, fact_re: re.Pattern | None = None):
    """(tipo, valor normalizado, início, fim) de cada fato do texto, na ordem. Códigos de
    documento vêm com tipo 'code' (o chamador decide); 'um'/'uma' soltos não são fato."""
    for match in (fact_re or FACT_RE).finditer(text):
        kind, value = match.lastgroup, match.group(0)
        if kind == "road":
            road = ROAD_RE.search(value)
            value = normalize_road(*road.groups()) if road else value
        elif kind == "month":  # 'abril/2026' -> '2026-04'; 'abril' -> '04'
            name, _, year = value.partition("/")
            month = MONTHS_PT[strip_accents(name.strip()).lower()]
            value = f"{year.strip()}-{month:02d}" if year else f"{month:02d}"
        elif kind == "ordinal":
            value = str(int(re.match(r"\d+", value).group(0)))
        elif kind == "numword":
            for number, start, end in number_word_groups(value, match.start()):
                yield "number", str(number), start, end
            continue
        elif kind == "status":
            value = _canonical(STATUS_TERMS, normalize_text(value))
        elif kind == "neg":
            value = _canonical(NEGATION_TERMS, normalize_text(value))
        elif kind == "weekday":
            value = _canonical(WEEKDAY_TERMS, value)
        elif kind == "company":
            value = fold(value)
        else:
            value = value.upper().replace(" ", "")
        yield kind, value, match.start(), match.end()


def mask_facts(text: str) -> str:
    """Texto com cada fato trocado pelo seu tipo ('<status>'): a prosa sem os fatos, que são
    julgados uma vez só por `narrative_facts`/`text_codes`."""
    out, last = [], 0
    for kind, _, start, end in iter_facts(text):
        out.append(text[last:start])
        out.append(f" <{kind}> ")
        last = end
    out.append(text[last:])
    return "".join(out)


def _field_label(text: str) -> tuple[str | None, int]:
    """Rótulo de um parágrafo "Rótulo: valor" (sem o marcador de lista) e a posição onde o
    valor começa; (None, 0) se o parágrafo não for um campo."""
    body = text
    offset = 0
    marker = re.match(r"^(?:[•▪◦‣\-–§o]\s+|[A-Za-z]\)\s*|[IVXivx]{1,4}\.\s+)", body)
    if marker:
        offset = marker.end()
        body = body[offset:]
    match = FIELD_RE.match(body)
    if not match:
        return None, 0
    label = match.group("label").strip()
    if len(label.split()) > FIELD_LABEL_MAX_WORDS:
        return None, 0
    road = ROAD_RE.fullmatch(label)
    name = normalize_road(*road.groups()) if road else fold(label)
    return name, offset + match.start("value")


def narrative_facts(text: str, masks: tuple[re.Pattern, ...] = ()) -> list[str]:
    """Fatos citados no texto, na ordem: 'road:RD-103', 'date:10/08/2026', 'time:10H',
    'month:2026-04' (ou 'month:04' sem ano), 'number:09', 'number:01/2025' e, desde a v3.0,
    'ordinal:1', 'number:8' (por extenso), 'status:APROVADO', 'neg:NAO_HOUVE', 'weekday:QUINTA',
    'company:DELTA'. Num parágrafo "Rótulo: valor", status e negação do valor levam o campo
    ('status:APROVADO@ANALISE PROGRAMA'). Códigos de documento ficam fora (`text_codes`).

    `masks`: padrões cujos trechos são apagados antes (fatos comparados por outra verificação).
    """
    for pattern in masks:
        text = pattern.sub(" ", text)
    label, value_at = _field_label(text)
    out: list[str] = []
    for kind, value, start, _ in iter_facts(text):
        if kind == "code":
            continue
        if label and kind in QUALIFIED_KINDS and start >= value_at:
            value = f"{value}@{label}"
        out.append(f"{kind}:{value}")
    if label:
        # 3.1: disciplinas do valor do campo como CONJUNTO (depois dos outros fatos do campo,
        # em ordem canônica): a ordem da enumeração e a posição do verbo são redação (DEC-007;
        # P2.2_ORDEM_HERDADA_SECUNDARIO); estar ou não na lista é fato.
        out += sorted({f"discipline:{_canonical(DISCIPLINE_TERMS, normalize_text(m.group(0)))}"
                       f"@{label}" for m in DISCIPLINE_RE.finditer(text, value_at)})
    return out


def road_anchor(text: str) -> str | None:
    """Rodovia que abre um bloco: parágrafo começado pela rodovia ("A) RD-103:") ou parágrafo
    curto, terminado em ':', com uma única rodovia ("...projeto executivo da Rodovia RD-103:")."""
    match = ROAD_LEAD_RE.match(text)
    if match:
        return normalize_road(*match.groups())
    roads = _ordered_unique(_roads(text))
    if (len(roads) == 1 and text.rstrip().endswith(":")
            and len(text.split()) <= ROAD_ANCHOR_MAX_WORDS):
        return roads[0]
    return None


def _is_list_item(text: str) -> bool:
    first = text.split(" ", 1)[0] if text else ""
    return first in LIST_GLYPHS or bool(TEXT_MARKER_RE.match(text))


def _row_is_list_start(row) -> bool:
    """Linha que abre item de lista: glifo de marcador ("•", "o" do Word em span próprio) ou
    marcador textual ("A)", "a)", "I.")."""
    spans = row.spans
    if not spans:
        return False
    text = row.text
    first = text.split(" ", 1)[0]
    if first in LIST_GLYPHS - {"o", "-"}:
        return True
    if first in {"o", "-"}:
        return spans[0].text.strip() == first and len(spans) > 1
    return bool(TEXT_MARKER_RE.match(text))


def section_masks(key: str, title: str) -> tuple[re.Pattern, ...]:
    """Padrões apagados antes dos fatos da seção: na Apresentação e no Encerramento, o número
    do relatório, o mês, as contagens declaradas e a data/nome da assinatura têm verificação
    própria (com suas allowances)."""
    _, name = _heading_parts(title)
    return {
        "APRESENTACAO": (REPORT_NUMBER_RE, MONTH_REF_RE),
        "ENCERRAMENTO": (REPORT_NUMBER_RE, MONTH_REF_RE, DECLARED_PAGES_RE, DECLARED_ANNEXES_RE,
                         SIGNATURE_RE),
    }.get(fold(name), ())


def finish_section(section: dict, masks: tuple[re.Pattern, ...] = ()) -> dict:
    """(Re)calcula os campos derivados de uma seção a partir de `segments` (parágrafos do corpo
    e linhas de quadro, na ordem): texto, rodovias, códigos, fatos e o bloco de rodovia de cada
    fato (`fact_blocks`, 'RD-103#2' = 2º bloco da RD-103 na seção, 'RD-103#1 > DISCIPLINAS DA
    FASE DE ESTUDOS' = grupo dentro do bloco; '' fora de bloco). Cada segmento recebe o seu
    `block`."""
    segments = section.get("segments") or []
    text = normalize_text(" ".join(s["text"] for s in segments))
    section["text"] = text
    section["roads"] = _ordered_unique(_roads(text))
    section["text_codes"] = text_codes(text)
    section["word_count"] = len(text.split())
    facts: list[str] = []
    blocks: list[str] = []
    block = group = ""
    seen: Counter[str] = Counter()
    for seg in segments:
        if seg.get("kind") == "body":
            text = seg["text"]
            road = road_anchor(text)
            if road:
                seen[road] += 1
                block, group = f"{road}#{seen[road]}", ""
            elif not _is_list_item(text):
                block = group = ""
            elif text.rstrip().endswith(":") and _field_label(text)[0] is None:
                # cabeçalho de grupo dentro do bloco ("• Disciplinas da Fase de Estudos:")
                group = fold(re.sub(r"^\S+\s+", "", text.rstrip()[:-1]))
        label = " > ".join(part for part in (block, group) if part)
        seg["block"] = label
        block_label = label
        seg_facts = narrative_facts(seg["text"], masks)
        facts += seg_facts
        blocks += [block_label] * len(seg_facts)
    section["facts"] = facts
    section["fact_blocks"] = blocks
    return section


def _size_name(width_cm: float, height_cm: float) -> str:
    short, long_ = sorted((width_cm, height_cm))
    if abs(short - 21.0) <= 0.1 and abs(long_ - 29.7) <= 0.1:
        return "A4"
    return f"{short:.1f}x{long_:.1f}cm"


# --------------------------------------------------------------------------- figuras


def _gray_grid(pix, columns: int, rows: int) -> list[int]:
    """Média por célula de um pixmap em cinza (1 canal), `columns` x `rows` células."""
    w, h, samples = pix.width, pix.height, pix.samples
    out: list[int] = []
    for gy in range(rows):
        y0 = gy * h // rows
        y1 = max(y0 + 1, (gy + 1) * h // rows)
        for gx in range(columns):
            x0 = gx * w // columns
            x1 = max(x0 + 1, (gx + 1) * w // columns)
            total = 0
            for yy in range(y0, y1):
                base = yy * w
                total += sum(samples[base + x0:base + x1])
            out.append(round(total / ((y1 - y0) * (x1 - x0))))
    return out


def _patch(page, rect, frac: tuple[float, float, float, float]) -> dict:
    """Recorte em cinza (zoom `LABEL_ZOOM`) de uma fração da figura, em base64."""
    w, h = rect[2] - rect[0], rect[3] - rect[1]
    clip = pymupdf.Rect(rect[0] + frac[0] * w, rect[1] + frac[1] * h,
                        rect[0] + frac[2] * w, rect[1] + frac[3] * h)
    pix = page.get_pixmap(clip=clip, matrix=pymupdf.Matrix(LABEL_ZOOM, LABEL_ZOOM),
                          colorspace=pymupdf.csGRAY, alpha=False)
    return {"shape": [pix.height, pix.width],
            "gray_b64": base64.b64encode(bytes(pix.samples)).decode("ascii")}


def _page_words(page):
    """(palavra, bbox, cor) de cada palavra de texto da página (>= 2 caracteres, com letra ou
    dígito), pelos caracteres do `rawdict` (a bbox é a dos glifos, não a do span)."""
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                word: list[str] = []
                box: list[float] | None = None
                for ch in [*span["chars"], None]:
                    if ch is None or ch["c"].isspace():
                        if box and len(word) >= 2 and any(c.isalnum() for c in word):
                            yield "".join(word), box, span["color"]
                        word, box = [], None
                        continue
                    word.append(ch["c"])
                    x0, y0, x1, y1 = ch["bbox"]
                    box = [x0, y0, x1, y1] if box is None else [
                        min(box[0], x0), min(box[1], y0), max(box[2], x1), max(box[3], y1)]


def invisible_words(page) -> list[dict] | None:
    """v3.2 (QA4-E, MAJOR): palavras extraíveis SEM tinta visível — texto branqueado (cor do
    texto ~ cor do fundo) ou coberto (retângulo/figura por cima). Renderiza a página a
    VISIBILITY_DPI e, na bbox de cada palavra, conta os pixels que destoam do fundo (mediana da
    bbox) E têm a cor do texto; abaixo de VISIBILITY_MIN_INK, ou contraste texto x fundo abaixo
    de VISIBILITY_MIN_CONTRAST, a palavra é invisível. None sem numpy."""
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy vem com o extra `discovery`
        return None
    zoom = VISIBILITY_DPI / 72
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    img = img[:, :, :3].astype(np.int16)
    out = []
    for text, box, c in _page_words(page):
        x0, y0, x1, y1 = (round(v * zoom) for v in box)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(pix.width, max(x0 + 1, x1)), min(pix.height, max(y0 + 1, y1))
        region = img[y0:y1, x0:x1].reshape(-1, 3)
        if not len(region):
            continue
        color = np.array([(c >> 16) & 255, (c >> 8) & 255, c & 255], dtype=np.int16)
        background = np.median(region, axis=0)
        contrast = int(np.abs(color - background).max())
        off_background = np.abs(region - background).max(axis=1) > VISIBILITY_INK_DELTA
        like_text = np.abs(region - color).max(axis=1) < max(VISIBILITY_COLOR_TOL,
                                                             contrast * 0.6)
        ink = float((off_background & like_text).mean())
        if contrast < VISIBILITY_MIN_CONTRAST or ink < VISIBILITY_MIN_INK:
            out.append({"text": text, "bbox": [round(v, 1) for v in box],
                        "ink": round(ink, 4), "contrast": contrast})
    return out


def ink_map(page, rect, *, dpi: int = INK_DPI, columns: int = INK_COLUMNS) -> dict | None:
    """Mapa de tinta da figura: fração de pixels que destoam do fundo local, em células
    quadradas de 1/`columns` da largura (linhas pela altura). O fundo local é a mediana de
    blocos de 1/INK_BG_BLOCKS da largura, o que tira o efeito de fundo liso x foto: o mapa mede
    onde há TEXTO/traço, não a cor do fundo. `gray_b64` = cinza médio das mesmas células (para
    seletores: aba destacada). None sem numpy."""
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy vem com o extra `discovery`
        return None
    pix = page.get_pixmap(clip=pymupdf.Rect(rect), dpi=dpi, colorspace=pymupdf.csGRAY,
                          alpha=False)
    h, w = pix.height, pix.width
    if h < 2 or w < 2:
        return None
    gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(h, w).astype(np.int16)
    block = max(2, round(w / INK_BG_BLOCKS))
    bh, bw = -(-h // block), -(-w // block)
    padded = np.pad(gray, ((0, bh * block - h), (0, bw * block - w)), mode="edge")
    tiles = padded.reshape(bh, block, bw, block).transpose(0, 2, 1, 3).reshape(bh, bw, -1)
    background = np.median(tiles, axis=2)
    bg = np.repeat(np.repeat(background, block, axis=0), block, axis=1)[:h, :w]
    ink = (np.abs(gray - bg) > INK_DELTA).astype(np.float32)
    cell = w / columns
    rows = max(1, round(h / cell))
    ys = np.linspace(0, h, rows + 1).round().astype(int)
    xs = np.linspace(0, w, columns + 1).round().astype(int)
    areas = np.outer(np.diff(ys), np.diff(xs)).clip(min=1)

    def cells(values):
        sums = np.add.reduceat(np.add.reduceat(values, ys[:-1], axis=0), xs[:-1], axis=1)
        return sums / areas

    ink_cells = np.clip(np.round(cells(ink) * 255), 0, 255).astype(np.uint8)
    gray_cells = np.clip(np.round(cells(gray.astype(np.float32))), 0, 255).astype(np.uint8)
    return {"columns": columns, "rows": rows, "dpi": dpi,
            "b64": base64.b64encode(ink_cells.tobytes()).decode("ascii"),
            "gray_b64": base64.b64encode(gray_cells.tobytes()).decode("ascii")}


def _raster_content(page, rect) -> dict:
    """Descritores do que a figura MOSTRA (renderizada como na página, não o fluxo da imagem):
    miniatura em cinza, desvio-padrão, cores distintas, o recorte do selo e o mapa de tinta."""
    clip = pymupdf.Rect(rect)
    rows = max(1, min(THUMB_MAX_ROWS, round(THUMB_COLUMNS * clip.height / clip.width)))
    zoom = THUMB_COLUMNS * 4 / clip.width
    gray = page.get_pixmap(clip=clip, matrix=pymupdf.Matrix(zoom, zoom),
                           colorspace=pymupdf.csGRAY, alpha=False)
    thumb = _gray_grid(gray, THUMB_COLUMNS, rows)
    mean = sum(thumb) / len(thumb)
    std = (sum((v - mean) ** 2 for v in thumb) / len(thumb)) ** 0.5
    rgb = page.get_pixmap(clip=clip, matrix=pymupdf.Matrix(zoom, zoom),
                          colorspace=pymupdf.csRGB, alpha=False)
    q = 256 // COLOR_LEVELS
    data = rgb.samples
    colors: Counter[tuple[int, int, int]] = Counter(
        (data[i] // q, data[i + 1] // q, data[i + 2] // q) for i in range(0, len(data), 3)
    )
    n_pixels = rgb.width * rgb.height
    return {
        "thumb": {"columns": THUMB_COLUMNS, "rows": rows, "hex": bytes(thumb).hex()},
        "gray_std": round(std, 2),
        "colors": sum(1 for c in colors.values() if c / n_pixels >= COLOR_MIN_SHARE),
        "label": {"template": _patch(page, rect, LABEL_TEMPLATE_FRAC),
                  "area": _patch(page, rect, LABEL_AREA_FRAC)},
        "ink": ink_map(page, rect),
    }


def _contains(outer, inner, slack: float = 1.0) -> bool:
    return (inner[0] >= outer[0] - slack and inner[1] >= outer[1] - slack
            and inner[2] <= outer[2] + slack and inner[3] <= outer[3] + slack)


def _page_figures(
    page, header_limit: float, footer_limit: float
) -> tuple[list[dict], int, list[tuple]]:
    """Figuras da página: (figuras serializáveis, nº de rasters minúsculos, caixas vetoriais pt).

    Texto com centro dentro de uma caixa vetorial é texto de quadro/tabela (EMF), não corpo.
    """
    rect = page.rect
    figures: list[dict] = []
    tiny = 0
    rasters: list[tuple] = []
    vectors: list[tuple] = []
    for info in page.get_image_info():
        x0, y0, x1, y1 = info["bbox"]
        clipped = (max(x0, rect.x0), max(y0, rect.y0), min(x1, rect.x1), min(y1, rect.y1))
        cy = (clipped[1] + clipped[3]) / 2
        if cy <= header_limit or cy >= footer_limit:
            continue
        w, h = clipped[2] - clipped[0], clipped[3] - clipped[1]
        if w < MIN_RASTER_CM * PT_PER_CM or h < MIN_RASTER_CM * PT_PER_CM:
            tiny += 1
            continue
        rasters.append(clipped)
        figures.append({
            "kind": "raster",
            "bbox_cm": _bbox_cm(clipped),
            "width_cm": _cm(w),
            "height_cm": _cm(h),
            "pixels": [info.get("width"), info.get("height")],
            "content": _raster_content(page, clipped),
        })
    try:
        clusters = page.cluster_drawings(
            x_tolerance=VECTOR_CLUSTER_TOLERANCE_PT, y_tolerance=VECTOR_CLUSTER_TOLERANCE_PT
        )
    except (ValueError, RuntimeError):  # página sem desenhos
        clusters = []
    for cluster in clusters:
        box = (cluster.x0, cluster.y0, cluster.x1, cluster.y1)
        cy = (box[1] + box[3]) / 2
        if cy <= header_limit or cy >= footer_limit:
            continue
        w, h = box[2] - box[0], box[3] - box[1]
        if w < MIN_VECTOR_CM * PT_PER_CM or h < MIN_VECTOR_CM * PT_PER_CM:
            continue
        if any(_contains(r, box) for r in rasters):
            continue  # sobreposição a uma imagem (ex.: logotipo sobre o fundo da capa)
        vectors.append(box)
        figures.append({
            "kind": "vector",
            "bbox_cm": _bbox_cm(box),
            "width_cm": _cm(w),
            "height_cm": _cm(h),
            "pixels": None,
        })
    figures.sort(key=lambda f: (f["bbox_cm"][1], f["bbox_cm"][0]))
    return figures, tiny, vectors


# --------------------------------------------------------------------------- extração


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_facts(pdf_path: str | Path, *, cover_pages: int = 1) -> dict:
    """Extrai os fatos comparáveis de um PDF do Relatório G2.

    `cover_pages`: quantas páginas iniciais são capa (sem títulos, cabeçalho nem rodapé
    esperados). O padrão vigente tem uma.
    """
    path = Path(pdf_path)
    doc = pymupdf.open(path)
    try:
        return _extract(doc, path, cover_pages)
    finally:
        doc.close()


def _extract(doc, path: Path, cover_pages: int) -> dict:
    page_lines = [_page_lines(page) for page in doc]
    bands = []
    for page in doc:
        h = page.rect.height
        bands.append((HEADER_BAND_CM * PT_PER_CM, h - FOOTER_BAND_CM * PT_PER_CM))

    def in_header(line: _Line, i: int) -> bool:
        return line.y1 <= bands[i][0]

    def in_footer(line: _Line, i: int) -> bool:
        return line.y0 >= bands[i][1]

    page_figures = [_page_figures(page, *bands[i]) for i, page in enumerate(doc)]

    def in_figure(x0: float, y0: float, x1: float, y1: float, i: int) -> bool:
        """Centro dentro de uma figura: texto de tabela/quadro, não corpo nem título."""
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        return any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in page_figures[i][2])

    # Corpo do texto: tamanho mais frequente (por caractere) fora da capa, das faixas e das
    # figuras (sem isso o Controle de Produtos, a 7 pt, vira o "corpo" do nº 13).
    sizes: Counter[float] = Counter()
    for i, lines in enumerate(page_lines):
        if i < cover_pages:
            continue
        for line in lines:
            if in_header(line, i) or in_footer(line, i):
                continue
            if in_figure(line.x0, line.y0, line.x1, line.y1, i):
                continue
            for s in line.spans:
                sizes[round(s.size * 2) / 2] += len(s.text.strip())
    body_size = sizes.most_common(1)[0][0] if sizes else 11.0
    heading_min = body_size + HEADING_DELTA_PT
    # Margem direita do corpo por orientação (fim de linha justificada): fecha parágrafo na
    # troca de página quando a última linha acaba antes dela.
    right_edge: dict[str, float] = {}
    for i, lines in enumerate(page_lines):
        if i < cover_pages:
            continue
        orientation = "landscape" if doc[i].rect.width > doc[i].rect.height else "portrait"
        for line in lines:
            if (in_header(line, i) or in_footer(line, i)
                    or in_figure(line.x0, line.y0, line.x1, line.y1, i)):
                continue
            right_edge[orientation] = max(right_edge.get(orientation, 0.0), line.x1)

    pages: list[dict] = []
    headings: list[dict] = []
    sections: dict[str, dict] = {}
    section_parts: dict[str, list[dict]] = {}
    open_paragraph: dict = {}  # parágrafo do corpo em curso: seção, segmento, última linha
    blocks: dict[str, list[str]] = {}
    block_rows: dict[str, list[dict]] = {}
    crops: list[dict] = []
    body_rows: list[tuple[int, float, float, str]] = []
    current: dict | None = None
    key_counts: Counter[str] = Counter()

    def open_section(heading: dict | None, page_index: int) -> str:
        if heading is None:
            key = COVER_KEY if page_index < cover_pages else FRONT_KEY
            title = key
        else:
            key, title = heading["key"], heading["label"]
        if key not in sections:
            sections[key] = {"title": title, "page": page_index + 1}
            section_parts[key] = []
        return key

    def add_body_row(key: str, row: _Row, page_index: int, orientation: str) -> None:
        """Junta a linha ao parágrafo em curso ou abre outro (ver PARAGRAPH_GAP_PT)."""
        prev = open_paragraph.get("row")
        new = (prev is None or open_paragraph.get("key") != key or _row_is_list_start(row))
        if not new and open_paragraph["page"] == page_index:
            new = row.y0 - prev.y1 > PARAGRAPH_GAP_PT
        elif not new:
            edge = right_edge.get(open_paragraph["orientation"], prev.x1)
            ended = prev.text.rstrip().endswith((".", ":", ";", "!", "?"))
            new = (prev.x1 < edge - PARAGRAPH_SHORT_LINE_PT
                   or (ended and row.text[:1].isupper()))
        if new:
            segment = {"kind": "body", "text": row.text, "page": page_index + 1}
            section_parts[key].append(segment)
            open_paragraph.update(key=key, segment=segment)
        else:
            segment = open_paragraph["segment"]
            segment["text"] = normalize_text(f"{segment['text']} {row.text}")
        open_paragraph.update(row=row, page=page_index, orientation=orientation)

    for i, page in enumerate(doc):
        rect = page.rect
        width_cm, height_cm = _cm(rect.width), _cm(rect.height)
        lines = page_lines[i]
        header = [ln for ln in lines if in_header(ln, i)]
        footer = [ln for ln in lines if in_footer(ln, i)]
        body = [ln for ln in lines if not in_header(ln, i) and not in_footer(ln, i)]

        header_text = [r.text for r in _rows(header)]
        footer_tokens: list[str] = []
        printed_number = None
        for ln in sorted(footer, key=lambda ln: (ln.y0, ln.x0)):
            if PAGE_NUMBER_RE.match(ln.text) and printed_number is None:
                printed_number = int(ln.text)
            else:
                footer_tokens.append(ln.text)

        rows = _rows(body)
        is_cover = i < cover_pages
        page_heading_keys: list[str] = []

        # Regiões do Controle de Produtos: do título "Programa | Controle de Produtos" até o
        # próximo título do documento na página ou o início do rodapé.
        heading_rows = set()
        if not is_cover:
            for idx, row in enumerate(rows):
                if (row.all_bold and row.min_size >= heading_min
                        and not in_figure(row.x0, row.y0, row.x1, row.y1, i)):
                    heading_rows.add(idx)
        title_rows = [idx for idx, row in enumerate(rows)
                      if row.all_bold and PRODUCT_CONTROL_TITLE_RE.match(row.text)]
        regions: list[tuple[float, float]] = []
        for idx in title_rows:
            end = bands[i][1]
            for later in range(idx + 1, len(rows)):
                if later in heading_rows or later in title_rows:
                    end = rows[later].y0
                    break
            regions.append((rows[idx].y0, end))

        crop_state: dict[int, dict] = {}
        state_boxes: dict[int, list[tuple[float, float]]] = {}
        state_spans: dict[int, list[tuple[_Span, float, float]]] = {}
        prev_heading_row: _Row | None = None
        orientation = "landscape" if rect.width > rect.height else "portrait"
        for idx, row in enumerate(rows):
            if idx in heading_rows:
                open_paragraph.clear()
                number, text = _heading_parts(row.text)
                continuation = (
                    prev_heading_row is not None
                    and number is None
                    and headings
                    and row.y0 - prev_heading_row.y1
                    < HEADING_CONTINUATION_FACTOR * row.min_size
                )
                if continuation:
                    last = headings[-1]
                    last["text"] = normalize_text(f"{last['text']} {text}")
                    last["label"] = normalize_text(f"{last['label']} {text}")
                    sections[last["key"]]["title"] = last["label"]
                    prev_heading_row = row
                    continue
                base_key = _heading_key(number, text)
                key_counts[base_key] += 1
                count = key_counts[base_key]
                key = base_key if count == 1 else f"{base_key}#{count}"
                current = {
                    "key": key,
                    "number": number,
                    "text": text,
                    "label": normalize_text(f"{number} {text}") if number else text,
                    "level": number.count(".") + 1 if number else 1,
                    "page": i + 1,
                    "y_cm": _cm(row.y0),
                }
                headings.append(current)
                page_heading_keys.append(key)
                open_section(current, i)
                prev_heading_row = row
                continue
            prev_heading_row = None
            section_key = open_section(current, i)
            region = next((n for n, (start, end) in enumerate(regions) if start <= row.y0 < end),
                          None)
            if region is not None:
                open_paragraph.clear()
                state = crop_state.setdefault(region, {
                    "page": i + 1,
                    "block": _block_key(current),
                    "anchor": current["key"] if current else section_key,
                    "labels": None,
                    "rows": 0,
                })
                if PRODUCT_CONTROL_TITLE_RE.match(row.text):
                    continue
                ordered = sorted(row.lines, key=lambda ln: ln.x0)
                if state["labels"] is None and row.all_bold:
                    state["labels"] = [ln.text for ln in ordered]
                    state_boxes[region] = [(ln.x0, ln.x1) for ln in ordered]
                    continue
                state_spans.setdefault(region, []).extend(
                    (span, line.y0, line.y1) for line in ordered for span in line.spans
                    if span.text.strip()
                )
                continue
            if in_figure(row.x0, row.y0, row.x1, row.y1, i):
                section_parts[section_key].append(
                    {"kind": "figure", "text": row.text, "page": i + 1})
                open_paragraph.clear()
            else:
                add_body_row(section_key, row, i, orientation)
                body_rows.append((i + 1, row.y0, row.y1, row.text))

        for n in sorted(crop_state):
            state = crop_state[n]
            for record in _crop_rows(state_spans.get(n, []), state_boxes.get(n)):
                record["page"] = i + 1
                blocks.setdefault(state["block"], []).append(record["code"])
                block_rows.setdefault(state["block"], []).append(record)
                state["rows"] += 1
            crops.append(state)
        figures, tiny, _ = page_figures[i]
        pages.append({
            "index": i + 1,
            "width_cm": width_cm,
            "height_cm": height_cm,
            "orientation": "landscape" if rect.width > rect.height else "portrait",
            "size_name": _size_name(width_cm, height_cm),
            "is_cover": is_cover,
            "header_text": header_text,
            "footer_text": footer_tokens,
            "printed_page_number": printed_number,
            "heading_keys": page_heading_keys,
            "figures": figures,
            "tiny_raster_count": tiny,
            "invisible_words": invisible_words(page),
        })

    _anchor_figures(pages, headings, cover_pages)
    _caption_figures(pages, body_rows)

    for key, section in sections.items():
        section["segments"] = section_parts.get(key, [])
        finish_section(section, section_masks(key, section["title"]))
        if key in NARRATIVE_EXCLUDED_SECTIONS:
            section["facts"], section["fact_blocks"] = [], []

    runs: list[list] = []
    for page in pages:
        if runs and runs[-1][0] == page["orientation"]:
            runs[-1][1] += 1
        else:
            runs.append([page["orientation"], 1])

    all_body_roads = [r for key in sections for r in sections[key]["roads"]]
    return {
        "extractor_version": EXTRACTOR_VERSION,
        "source": {"file_name": path.name, "sha256": _sha256(path), "bytes": path.stat().st_size},
        "page_count": len(pages),
        "cover_pages": cover_pages,
        "body_font_size": body_size,
        "pages": pages,
        "orientation_runs": runs,
        "headings": headings,
        "sections": sections,
        "product_control": {
            "block_order": list(blocks),
            "blocks": blocks,
            "rows": block_rows,
            "counts": {k: len(v) for k, v in blocks.items()},
            "crops": crops,
        },
        "roads": _ordered_unique(all_body_roads),
        "identity": _identity(page_lines, sections, cover_pages),
    }


def _anchor_figures(pages: list[dict], headings: list[dict], cover_pages: int) -> None:
    """Âncora de uma figura = último título antes dela na ordem do documento."""
    ordered = sorted(headings, key=lambda h: (h["page"], h["y_cm"]))
    for page in pages:
        for fig in page["figures"]:
            if page["index"] <= cover_pages:
                fig["anchor"] = COVER_KEY
                continue
            anchor = FRONT_KEY
            for h in ordered:
                if (h["page"], h["y_cm"]) <= (page["index"], fig["bbox_cm"][1]):
                    anchor = h["key"]
                else:
                    break
            fig["anchor"] = anchor


def _caption_figures(pages: list[dict], body_rows: list[tuple[int, float, float, str]]) -> None:
    """Legenda de cada figura = linhas de corpo entre a figura anterior e ela; `caption_road` é
    a primeira rodovia achada da linha mais próxima para trás (até CAPTION_MAX_ROWS linhas)."""
    figures = sorted(
        ((page["index"], f["bbox_cm"][1] * PT_PER_CM, f["bbox_cm"][3] * PT_PER_CM, f)
         for page in pages for f in page["figures"]),
        key=lambda item: (item[0], item[1]),
    )
    previous_end = (0, 0.0)
    for page_no, top, bottom, fig in figures:
        before = [r for r in body_rows
                  if previous_end <= (r[0], r[1]) and (r[0], r[2]) <= (page_no, top + 2.0)]
        nearest = before[-CAPTION_MAX_ROWS:][::-1]
        fig["caption"] = nearest[0][3] if nearest else None
        fig["caption_road"] = next((_roads(r[3])[0] for r in nearest if _roads(r[3])), None)
        previous_end = max(previous_end, (page_no, bottom - 2.0))


def _crop_rows(spans: list[tuple[_Span, float, float]],
               label_boxes: list[tuple[float, float]] | None) -> list[dict]:
    """Linhas de um recorte do Controle de Produtos: uma por código na 1ª coluna, com as
    células montadas pela posição dos rótulos (célula quebrada em várias linhas é juntada)."""
    if not spans:
        return []
    if label_boxes and len(label_boxes) > 1:
        # Célula pertence à coluna cujo rótulo começa antes do seu centro: as colunas são
        # alinhadas à esquerda do rótulo, e o status (centralizado) tem centro além do início
        # do rótulo. Fragmento no fim de uma descrição longa continua na descrição.
        bounds = [b[0] - COLUMN_START_SLACK_PT for b in label_boxes[1:]]
        n_cols = len(label_boxes)
    else:  # sem rótulos: colunas pelos spans da primeira linha com código
        first = next((s for s in spans if CODE_FULL_RE.fullmatch(normalize_text(s[0].text))),
                     spans[0])
        row = sorted((s[0] for s in spans if abs(s[1] - first[1]) <= ROW_TOLERANCE_PT),
                     key=lambda sp: sp.x0)
        bounds = [(a.x1 + b.x0) / 2 for a, b in pairwise(row)]
        n_cols = len(row)

    def column(span: _Span) -> int:
        center = (span.x0 + span.x1) / 2
        return sum(1 for b in bounds if center > b)

    anchors = [s for s in spans if column(s[0]) == 0
               and CODE_FULL_RE.fullmatch(normalize_text(s[0].text))]
    anchors.sort(key=lambda s: s[1])
    cells: list[list[list[tuple[float, float, str]]]] = [
        [[] for _ in range(n_cols)] for _ in anchors]
    for span, y0, y1 in spans:
        if not anchors:
            break
        center = (y0 + y1) / 2
        idx = min(range(len(anchors)),
                  key=lambda k: abs((anchors[k][1] + anchors[k][2]) / 2 - center))
        anchor_center = (anchors[idx][1] + anchors[idx][2]) / 2
        if abs(anchor_center - center) > PC_ROW_ATTACH_PT:
            continue
        cells[idx][min(column(span), n_cols - 1)].append((y0, span.x0, span.text))
    rows = []
    for anchor, row_cells in zip(anchors, cells, strict=True):
        texts = [normalize_text(" ".join(t for _, _, t in sorted(c))) for c in row_cells]
        code = normalize_text(anchor[0].text)
        road = next((_row_road(t) for t in texts[1:] if _row_road(t)), None)
        rows.append({"code": code, "road": road, "cells": texts})
    return rows


def _find_section(sections: dict[str, dict], name: str) -> dict | None:
    target = fold(name)
    for section in sections.values():
        _, text = _heading_parts(section["title"])
        if fold(text) == target:
            return section
    return None


def _months(text: str) -> list[str]:
    out = []
    for name, year in MONTH_REF_RE.findall(text):
        month = MONTHS_PT.get(strip_accents(name).lower())
        if month:
            out.append(reference_month(int(year), month))
    return out


def _declared(regex: re.Pattern, text: str) -> dict | None:
    match = regex.search(text)
    if not match:
        return None
    return {"value": int(match.group(1)), "words": normalize_text(match.group(2))}


def signatory_hash(closing_text: str) -> str | None:
    """sha256 do nome do signatário (forma de comparação, sem título) ou None se não houver
    assinatura reconhecível. O nome em si não sai daqui."""
    match = SIGNATORY_RE.search(closing_text)
    if not match:
        return None
    return hashlib.sha256(fold(match.group("name")).encode("utf-8")).hexdigest()


def _identity(page_lines: list[list[_Line]], sections: dict[str, dict], cover_pages: int) -> dict:
    cover_lines = [ln for lines in page_lines[:cover_pages] for ln in lines]
    ordered = sorted(cover_lines, key=lambda ln: (ln.y0, ln.x0))
    cover_text = normalize_text(" ".join(ln.text for ln in ordered))
    date_match = DATE_RE.search(cover_text)
    cover = {
        "text": cover_text,
        "report_numbers": [int(n) for n in REPORT_NUMBER_RE.findall(cover_text)],
        "date_text": normalize_text(date_match.group(0)) if date_match else None,
        "date_iso": parse_date_pt(cover_text),
        "fonts": sorted({s.font for ln in cover_lines for s in ln.spans}),
    }

    presentation_section = _find_section(sections, "APRESENTAÇÃO")
    p_text = presentation_section["text"] if presentation_section else ""
    presentation = {
        "found": presentation_section is not None,
        "report_numbers": [int(n) for n in REPORT_NUMBER_RE.findall(p_text)],
        "reference_months": _months(p_text),
    }

    closing_section = _find_section(sections, "ENCERRAMENTO")
    c_text = closing_section["text"] if closing_section else ""
    signature = SIGNATURE_RE.search(c_text)
    closing = {
        "found": closing_section is not None,
        "report_numbers": [int(n) for n in REPORT_NUMBER_RE.findall(c_text)],
        "reference_months": _months(c_text),
        "declared_pages": _declared(DECLARED_PAGES_RE, c_text),
        "declared_annexes": _declared(DECLARED_ANNEXES_RE, c_text),
        "signature_date_text": normalize_text(signature.group(1)) if signature else None,
        "signature_date_iso": parse_date_pt(signature.group(1)) if signature else None,
        "signatory_sha256": signatory_hash(c_text),
    }
    return {"cover": cover, "presentation": presentation, "closing": closing}
