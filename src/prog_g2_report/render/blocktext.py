"""Estrutura textual comum dos renderizadores puros do Relatório G2.

CONTEÚDO (o que dizer) sai dos renderizadores (`p22_text`, `p24_text`, …) nesta forma; a
REPRESENTAÇÃO (estilo, lista, negrito, imagem) é aplicada pelo builder (`builder.emit`); o
POSICIONAMENTO é a ordem de `config/g2_content_blocks.yaml` (`builder.assemble`).

    Segment    um run: texto + negrito/itálico
    Paragraph  um parágrafo: segmentos, styleId, lista, alinhamento e `kind`
    BlockText  o que um renderizador devolve para um bloco: parágrafos, fatos, status, avisos

`Paragraph.kind` (vocabulário fechado, `KINDS`):

    text        parágrafo comum (padrão)
    spacer      parágrafo vazio de espaçamento
    heading     título interno do bloco (não é título de nível; o estilo diz qual)
    image_slot  lugar de uma imagem gerada; `ref` = "<prefixo>[:<chave>]", resolvido pelo
                builder em `builder.emit.IMAGE_PROVIDERS[<prefixo>]`
    group       item de 1º nível de uma lista (ex.: grupo de disciplinas no 2.2)
    status      item de 2º nível (ex.: linha de status no 2.2)

Listas: `numbering` é a definição da lista (ex.: 'numId_29' de `p24_blocks.yaml
common.numbering`; o builder usa a chave numérica de `builder.blocks.LIST_DEFINITIONS`),
`level` é o ilvl e `list_key` identifica a instância: o builder cria um `<w:num>` novo por
`list_key` dentro do bloco, para que cada lista recomece (`common.numbering.restart`).
`list_level`/`list_id` são os nomes usados pelo 2.2 (aliases de leitura de `level`/`list_key`).

Superconjunto dos formatos do builder U (2.4) e do builder X (2.2); nenhum campo novo é
obrigatório, então os dois continuam a construir os mesmos objetos.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

KINDS = frozenset({"text", "spacer", "heading", "image_slot", "group", "status"})
STATUSES = frozenset({"OK", "SKIPPED", "PENDING_HUMAN", "PENDING", "FAILED"})


@dataclass(frozen=True)
class Segment:
    text: str
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True)
class Paragraph:
    segments: tuple[Segment, ...]
    style: str = "Normal"
    numbering: str | None = None      # definição da lista (ex.: 'numId_29')
    level: int | None = None          # ilvl; None = fora de lista
    list_key: str | None = None       # instância da lista (um <w:num> novo por chave)
    align: str | None = None          # left | center | right | both
    kind: str = "text"
    ref: str | None = None            # image_slot: '<prefixo>[:<chave>]'

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"Paragraph.kind desconhecido: {self.kind!r} (use {sorted(KINDS)})")
        if self.kind == "image_slot" and not self.ref:
            raise ValueError("image_slot exige ref")

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.segments)

    @property
    def list_level(self) -> int | None:     # nome do 2.2
        return self.level

    @property
    def list_id(self) -> str | None:        # nome do 2.2
        return self.list_key

    @property
    def in_list(self) -> bool:
        return self.level is not None


@dataclass
class BlockText:
    block_id: str
    paragraphs: Sequence[Paragraph] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    status: str = "OK"                # OK | SKIPPED | PENDING_HUMAN | PENDING | FAILED
    warnings: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def present(self) -> bool:
        return bool(self.paragraphs)

    @property
    def lines(self) -> list[str]:
        return [p.text for p in self.paragraphs]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def image_refs(self) -> list[str]:
        return [p.ref for p in self.paragraphs if p.kind == "image_slot" and p.ref]


def markup(text: str) -> tuple[Segment, ...]:
    """'a **b** c' -> (Segment('a '), Segment('b', bold), Segment(' c')); funde vizinhos iguais."""
    out: list[Segment] = []
    for i, piece in enumerate(text.split("**")):
        if not piece:
            continue
        bold = i % 2 == 1
        if out and out[-1].bold == bold:
            out[-1] = Segment(out[-1].text + piece, bold)
        else:
            out.append(Segment(piece, bold))
    return tuple(out)


def numbering_key(numbering: str | None) -> str | None:
    """'numId_29' -> '29'; 'PargrafodaLista, numId 37 lvl 0' -> '37'; None -> None."""
    if not numbering:
        return None
    match = re.search(r"numId[_\s]*(\d+)", str(numbering))
    if match:
        return match.group(1)
    return str(numbering)
