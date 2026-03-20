"""Modelos de dominio para transacciones y estado on-chain."""

from dataclasses import dataclass
from typing import Any


@dataclass
class ResultadoTransaccion:
    """Result of executing a write function on a contract."""

    transaction_hash: str
    contract_address: str
    function: str
    success: bool
    detail: str = ""


@dataclass
class EstadoContrato:
    """Result of reading the state of a contract variable or function."""

    contract_address: str
    field: str
    value: Any
    success: bool
    detail: str = ""
