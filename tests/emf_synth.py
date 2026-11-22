"""EMF sintético mínimo para testes offline: EMR_HEADER (88 bytes) + EMR_EOF (20 bytes)."""

from __future__ import annotations

import struct

EMR_HEADER, EMR_EOF = 1, 14
SIGNATURE = 0x464D4520  # " EMF"


def make_emf(bounds: tuple[int, int, int, int] = (0, 1, 1232, 280),
             frame_01mm: tuple[int, int, int, int] = (0, 0, 22091, 5048),
             device_px: tuple[int, int] = (1920, 1080),
             device_mm: tuple[int, int] = (344, 194)) -> bytes:
    eof = struct.pack("<IIIII", EMR_EOF, 20, 0, 16, 20)
    total = 88 + len(eof)
    header = struct.pack(
        "<II4i4iIIIIHHIII2i2i",
        EMR_HEADER, 88, *bounds, *frame_01mm, SIGNATURE, 0x10000, total, 2, 1, 0, 0, 0, 0,
        *device_px, *device_mm)
    assert len(header) == 88
    return header + eof


def font_record(handle: int, weight: int, face: str = "Arial Nova Cond") -> bytes:
    """EMR_EXTCREATEFONTINDIRECTW (82) com LOGFONTW de 92 bytes."""
    name = face.encode("utf-16-le")[:62].ljust(64, b"\x00")
    logfont = struct.pack("<5i8B", -10, 0, 0, 0, weight, 0, 0, 0, 0, 0, 0, 0, 0) + name
    return struct.pack("<III", 82, 12 + len(logfont), handle) + logfont


def select_record(handle: int) -> bytes:
    return struct.pack("<III", 37, 12, handle)


def text_record(text: str, x: int = 0, y: int = 0) -> bytes:
    """EMR_EXTTEXTOUTW (84): cabeçalho de 76 bytes, texto UTF-16 alinhado a 4, dx."""
    raw = text.encode("utf-16-le")
    raw += b"\x00" * (-len(raw) % 4)
    dx = struct.pack(f"<{len(text)}i", *([5] * len(text)))
    head = struct.pack("<II4iIff2iIII4iI", 84, 76 + len(raw) + len(dx), 0, 0, 0, 0, 1, 1.0, 1.0,
                       x, y, len(text), 76, 0, 0, 0, 0, 0, 76 + len(raw))
    assert len(head) == 76
    return head + raw + dx


def make_text_emf(records: list[bytes]) -> bytes:
    """EMF sintético com os registros dados entre o cabeçalho e o EOF."""
    base = make_emf()
    return base[:88] + b"".join(records) + base[88:]
