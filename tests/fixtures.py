"""Fixtures de datos sintéticos para los tests unitarios."""

import hashlib
from decimal import Decimal
from typing import Optional

from ingestion_onchain.modelos import DatosWallet, Token, Transaccion, TransferenciaToken

TIMESTAMP_BASE = 1_700_000_000
TIMESTAMP_RECIENTE = 1_738_000_000

WALLET_MOCK = "0xabc123def456abc123def456abc123def456abc1"


def contrato_sintetico(semilla: str) -> str:
    """Dirección de contrato determinística y sintética para una semilla."""
    return "0x" + hashlib.sha256(semilla.encode()).hexdigest()[:40]


def crear_transaccion(
    hash_tx: str = "0xhash1",
    origen: str = WALLET_MOCK,
    destino: str = "0xotrawallet",
    valor_eth: float = 0.5,
    timestamp: int = TIMESTAMP_BASE,
    es_contrato: bool = False,
    es_error: bool = False,
    bloque: int = 18_000_000,
) -> Transaccion:
    return Transaccion(
        hash=hash_tx,
        bloque=bloque,
        timestamp=timestamp,
        origen=origen.lower(),
        destino=destino.lower(),
        valor_wei=int(Decimal(str(valor_eth)) * 10**18),
        gas_utilizado=21_000,
        es_error=es_error,
        es_contrato=es_contrato,
    )


def crear_transferencia_token(
    simbolo: str = "USDC",
    origen: str = WALLET_MOCK,
    destino: str = "0xotrawallet",
    timestamp: int = TIMESTAMP_BASE,
    contrato: Optional[str] = None,
    decimales: int = 6,
    cantidad_raw: int = 100_000_000,
) -> TransferenciaToken:
    # Por defecto, un contrato distinto por símbolo; puedo forzar dos contratos
    # con el mismo símbolo pasando `contrato`.
    return TransferenciaToken(
        hash="0xhashtoken",
        bloque=18_000_000,
        timestamp=timestamp,
        origen=origen.lower(),
        destino=destino.lower(),
        token=Token(1, contrato or contrato_sintetico(simbolo), decimales, simbolo),
        cantidad_raw=cantidad_raw,
    )


def datos_wallet_activo() -> DatosWallet:
    """Wallet con actividad moderada, varios tokens y algunas interacciones con contratos."""
    txs = [
        crear_transaccion(f"0xhash{i}", timestamp=TIMESTAMP_BASE + i * 86400, es_contrato=(i % 3 == 0))
        for i in range(20)
    ]
    txs += [
        crear_transaccion(f"0xrecv{i}", origen="0xotro", destino=WALLET_MOCK, timestamp=TIMESTAMP_RECIENTE)
        for i in range(5)
    ]
    tokens = [
        crear_transferencia_token("USDC"),
        crear_transferencia_token("USDC"),
        crear_transferencia_token("WETH"),
        crear_transferencia_token("DAI"),
        crear_transferencia_token("UNI"),
        crear_transferencia_token("AAVE"),
    ]
    return DatosWallet(
        direccion=WALLET_MOCK,
        chain_id=1,
        balance_wei=15 * 10**17,
        transacciones=txs,
        transferencias_token=tokens,
    )


def datos_wallet_inactivo() -> DatosWallet:
    """Wallet con muy poca actividad."""
    txs = [crear_transaccion(timestamp=TIMESTAMP_BASE)]
    return DatosWallet(
        direccion=WALLET_MOCK,
        chain_id=1,
        balance_wei=10**16,
        transacciones=txs,
        transferencias_token=[],
    )
