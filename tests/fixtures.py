"""Fixtures de datos mock para los tests unitarios."""

from ingestion_onchain.modelos import DatosWallet, Transaccion, TransferenciaToken

TIMESTAMP_BASE = 1_700_000_000
TIMESTAMP_RECIENTE = 1_738_000_000

WALLET_MOCK = "0xabc123def456abc123def456abc123def456abc1"


def crear_transaccion(
    hash_tx: str = "0xhash1",
    origen: str = WALLET_MOCK,
    destino: str = "0xotrawallet",
    valor_eth: float = 0.5,
    timestamp: int = TIMESTAMP_BASE,
    es_contrato: bool = False,
    es_error: bool = False,
) -> Transaccion:
    return Transaccion(
        hash=hash_tx,
        bloque=18_000_000,
        timestamp=timestamp,
        origen=origen.lower(),
        destino=destino.lower(),
        valor_eth=valor_eth,
        gas_utilizado=21_000,
        es_error=es_error,
        es_contrato=es_contrato,
    )


def crear_transferencia_token(
    simbolo: str = "USDC",
    origen: str = WALLET_MOCK,
    destino: str = "0xotrawallet",
    timestamp: int = TIMESTAMP_BASE,
) -> TransferenciaToken:
    return TransferenciaToken(
        hash="0xhashtoken",
        timestamp=timestamp,
        origen=origen.lower(),
        destino=destino.lower(),
        simbolo_token=simbolo,
        contrato_token="0xcontrato",
        cantidad=100.0,
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
        balance_eth=1.5,
        transacciones=txs,
        transferencias_token=tokens,
    )


def datos_wallet_inactivo() -> DatosWallet:
    """Wallet con muy poca actividad."""
    txs = [crear_transaccion(timestamp=TIMESTAMP_BASE)]
    return DatosWallet(
        direccion=WALLET_MOCK,
        balance_eth=0.01,
        transacciones=txs,
        transferencias_token=[],
    )
