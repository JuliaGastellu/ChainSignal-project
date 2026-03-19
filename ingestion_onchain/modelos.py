"""Modelos de datos para la capa de ingestión on-chain."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Transaccion:
    """Representa una transacción normal de Ethereum."""

    hash: str
    bloque: int
    timestamp: int
    origen: str
    destino: str
    valor_eth: float
    gas_utilizado: int
    es_error: bool
    es_contrato: bool


@dataclass
class TransferenciaToken:
    """Representa una transferencia de token ERC-20."""

    hash: str
    timestamp: int
    origen: str
    destino: str
    simbolo_token: str
    contrato_token: str
    cantidad: float


@dataclass
class DatosWallet:
    """Agrupa todos los datos crudos de una wallet."""

    direccion: str
    balance_eth: float
    transacciones: List[Transaccion] = field(default_factory=list)
    transferencias_token: List[TransferenciaToken] = field(default_factory=list)
