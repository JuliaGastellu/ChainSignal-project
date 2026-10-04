"""Modelos de datos de la capa de ingesta on-chain.

Guardo montos como enteros (wei o unidades base del token) y convierto con
Decimal solo al presentar. Identifico tokens por red y contrato, nunca por
símbolo: dos contratos pueden usar el mismo símbolo.
"""

from dataclasses import dataclass, field
from decimal import Context, Decimal
from typing import List, Optional

from ingestion_onchain.resultados import CalidadDatos

WEI_POR_ETH = 10**18

# Un uint256 tiene 78 dígitos: el contexto por defecto de Decimal (28) redondea.
CONTEXTO_MONTOS = Context(prec=120)


def escalar(entero: int, decimales: int) -> Decimal:
    """Convierto unidades base a unidades del activo sin perder precisión."""
    return CONTEXTO_MONTOS.divide(Decimal(entero), Decimal(10) ** decimales)


@dataclass(frozen=True)
class Token:
    chain_id: int
    contrato: str
    decimales: int
    simbolo: str = ""

    @property
    def clave(self) -> str:
        return f"{self.chain_id}:{self.contrato}"

    @property
    def etiqueta(self) -> str:
        simbolo = self.simbolo or "?"
        return f"{simbolo} ({self.contrato[:6]}…{self.contrato[-4:]})"


@dataclass
class Transaccion:
    """Transacción normal de Ethereum."""

    hash: str
    bloque: int
    timestamp: int
    origen: str
    destino: str
    valor_wei: int
    gas_utilizado: int
    es_error: bool
    es_contrato: bool
    hash_bloque: str = ""

    @property
    def valor_eth(self) -> Decimal:
        return escalar(self.valor_wei, 18)


@dataclass
class TransferenciaToken:
    """Transferencia ERC-20 identificada por red y contrato."""

    hash: str
    bloque: int
    timestamp: int
    origen: str
    destino: str
    token: Token
    cantidad_raw: int
    hash_bloque: str = ""

    @property
    def cantidad(self) -> Decimal:
        return escalar(self.cantidad_raw, self.token.decimales)


@dataclass
class DatosWallet:
    """Datos de una wallet con su calidad y procedencia.

    balance_wei es None si no pude leerlo: nunca lo reemplazo por cero.
    """

    direccion: str
    chain_id: int
    balance_wei: Optional[int]
    transacciones: List[Transaccion] = field(default_factory=list)
    transferencias_token: List[TransferenciaToken] = field(default_factory=list)
    calidad: Optional[CalidadDatos] = None

    @property
    def balance_eth(self) -> Optional[Decimal]:
        return None if self.balance_wei is None else escalar(self.balance_wei, 18)
