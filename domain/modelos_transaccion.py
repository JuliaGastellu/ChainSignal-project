"""Modelos de dominio para transacciones y estado on-chain."""

from dataclasses import dataclass
from typing import Any


@dataclass
class ResultadoTransaccion:
    """Resultado de ejecutar una función de escritura en un contrato."""

    transaction_hash: str
    contrato_direccion: str
    funcion: str
    exitoso: bool
    detalle: str = ""


@dataclass
class EstadoContrato:
    """Resultado de leer el estado de una variable o función de un contrato."""

    contrato_direccion: str
    campo: str
    valor: Any
    exitoso: bool
    detalle: str = ""
