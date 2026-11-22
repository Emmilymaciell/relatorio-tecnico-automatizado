"""Apartamento COM com contagem de referência real (ole32), para Excel e Word na mesma thread.

Causa do `CO_E_OBJNOTCONNECTED` na 2ª passada do montador (provado em 2026-10-02): o pywin32
trata a thread que importou `pythoncom` como "inicializadora principal". Nela,
`pythoncom.CoInitialize()` repetido NÃO incrementa a contagem do sistema, mas
`pythoncom.CoUninitialize()` desfaz a inicialização inteira. Sequência medida:

    import pythoncom                 -> COM ok
    CoInitialize(); CoInitialize(); CoUninitialize()   -> CO_E_NOTINITIALIZED

Assim o par CoInitialize/CoUninitialize da exportação do Word (`builder.word_pdf`) derrubava o
apartamento da thread e desconectava o Excel aberto pelo Controle de Produtos; com
`first_slice_fill` os recortes da 2ª passada mudam, saem do cache e encontram o proxy morto.

Aqui as chamadas vão direto à ole32: toda entrada bem-sucedida (S_OK ou S_FALSE) tem exatamente
uma saída, e a contagem nunca desce abaixo da que o chamador encontrou.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

S_OK = 0
S_FALSE = 1
RPC_E_CHANGED_MODE = -2147417850       # 0x80010106: thread já em outro modelo (usável)
COINIT_APARTMENTTHREADED = 0x2


def _ole32() -> Any:
    import ctypes

    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    return ole32


class ComApartment:
    """`enter()` inicializa (STA) e `leave()` desfaz só o que `enter()` fez. Idempotente."""

    def __init__(self, ole32: Any = None) -> None:
        self._ole32 = ole32
        self._owned = False

    @property
    def owned(self) -> bool:
        return self._owned

    def enter(self) -> ComApartment:
        if self._owned:
            return self
        ole32 = self._ole32 = self._ole32 or _ole32()
        hr = int(ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED))
        if hr in (S_OK, S_FALSE):
            self._owned = True
        elif hr != RPC_E_CHANGED_MODE:
            raise OSError(f"CoInitializeEx falhou: HRESULT {hr & 0xFFFFFFFF:#010x}")
        return self

    def leave(self) -> None:
        if self._owned:
            self._owned = False
            self._ole32.CoUninitialize()


@contextlib.contextmanager
def com_apartment(ole32: Any = None) -> Iterator[ComApartment]:
    apartment = ComApartment(ole32).enter()
    try:
        yield apartment
    finally:
        apartment.leave()
