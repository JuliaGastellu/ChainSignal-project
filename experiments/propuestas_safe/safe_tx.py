"""SafeTx, su hash EIP-712 y las acciones permitidas (spike E10).

El hash es el que firman los owners del Safe (Safe >= 1.3.0): dominio
EIP712Domain(uint256 chainId,address verifyingContract) y tipo SafeTx. Lo
verifiqué contra getTransactionHash de los contratos oficiales con
scripts/verificar_safe_onchain.py (lectura, sin transacciones).

Solo armo acciones de una lista cerrada, siempre a nombre del propio Safe y
con approvals por el monto exacto (nunca infinitos). Varias llamadas van en una
sola SafeTx con MultiSendCallOnly: o se ejecutan todas o ninguna. No llamo
"atómico" a un lote de transacciones separadas.
"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple

from eth_abi import encode
from eth_utils import keccak, to_checksum_address

from protocolos.abi import Funcion

# Direcciones verificadas (ver __init__.py). Ethereum mainnet.
CHAIN_ID_MAINNET = 1
SAFE_SINGLETON_1_4_1 = "0x41675C099F32341bf84BFc5382aF534df5C7461a"
SAFE_SINGLETON_1_3_0 = "0xd9Db270c1B5E3Bd161E8c8503c55cEABeE709552"
MULTISEND_CALL_ONLY_1_4_1 = "0x9641d764fc13c8B624c04430C7356C1C7C8102e2"
AAVE_V3_POOL = "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
A_WETH = "0x4d5F47FA6A74757f35C14fD3a6Ef8E3C9BC514E8"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
USDC_DEUDA_VARIABLE = "0x72E95b8931767C79bA4EeE721354d6E99a61D004"

CERO = "0x0000000000000000000000000000000000000000"
CALL, DELEGATECALL = 0, 1

SAFE_TX_TYPEHASH = keccak(text="SafeTx(address to,uint256 value,bytes data,uint8 operation,uint256 safeTxGas,uint256 baseGas,"
                               "uint256 gasPrice,address gasToken,address refundReceiver,uint256 nonce)")
DOMINIO_TYPEHASH = keccak(text="EIP712Domain(uint256 chainId,address verifyingContract)")

APPROVE = Funcion("approve", ("address", "uint256"), ("bool",))
DEPOSIT = Funcion("deposit", (), ())
SUPPLY = Funcion("supply", ("address", "uint256", "address", "uint16"), ())
REPAY = Funcion("repay", ("address", "uint256", "uint256", "address"), ("uint256",))
MULTISEND = Funcion("multiSend", ("bytes",), ())
GET_TRANSACTION_HASH = Funcion("getTransactionHash", ("address", "uint256", "bytes", "uint8", "uint256", "uint256", "uint256",
                                                      "address", "address", "uint256"), ("bytes32",))
NONCE = Funcion("nonce", (), ("uint256",))
VERSION = Funcion("VERSION", (), ("string",))


@dataclass(frozen=True)
class Llamada:
    to: str
    value: int
    data: str  # hex con 0x
    descripcion: str


@dataclass(frozen=True)
class SafeTx:
    to: str
    value: int
    data: str
    operation: int
    safe_tx_gas: int
    base_gas: int
    gas_price: int
    gas_token: str
    refund_receiver: str
    nonce: int

    def como_dict(self) -> Dict[str, Any]:
        return asdict(self)


def safe_tx_hash(chain_id: int, safe: str, tx: SafeTx) -> str:
    separador = keccak(encode(["bytes32", "uint256", "address"], [DOMINIO_TYPEHASH, chain_id, to_checksum_address(safe)]))
    estructura = keccak(encode(
        ["bytes32", "address", "uint256", "bytes32", "uint8", "uint256", "uint256", "uint256", "address", "address", "uint256"],
        [SAFE_TX_TYPEHASH, to_checksum_address(tx.to), tx.value, keccak(bytes.fromhex(tx.data[2:])), tx.operation,
         tx.safe_tx_gas, tx.base_gas, tx.gas_price, to_checksum_address(tx.gas_token), to_checksum_address(tx.refund_receiver),
         tx.nonce]))
    return "0x" + keccak(b"\x19\x01" + separador + estructura).hex()


def multisend(llamadas: List[Llamada]) -> str:
    """Codifico multiSend(bytes): operación(1) | to(20) | value(32) | largo(32) | data, solo CALL."""
    empaquetado = b""
    for ll in llamadas:
        datos = bytes.fromhex(ll.data[2:])
        empaquetado += (bytes([CALL]) + bytes.fromhex(to_checksum_address(ll.to)[2:]) + ll.value.to_bytes(32, "big")
                        + len(datos).to_bytes(32, "big") + datos)
    return MULTISEND.codificar(empaquetado)


class AccionNoPermitida(ValueError):
    pass


def aportar_colateral_weth(safe: str, monto_wei: int) -> Tuple[List[Llamada], Dict[str, Any]]:
    """ETH del Safe → WETH → supply en Aave V3 a nombre del Safe. Approve por el monto exacto."""
    if monto_wei <= 0:
        raise AccionNoPermitida("amount must be positive")
    safe = to_checksum_address(safe)
    llamadas = [
        Llamada(WETH, monto_wei, DEPOSIT.codificar(), "Convertir ETH del Safe en WETH"),
        Llamada(WETH, 0, APPROVE.codificar(AAVE_V3_POOL, monto_wei), "Autorizar al Pool de Aave V3 por el monto exacto"),
        Llamada(AAVE_V3_POOL, 0, SUPPLY.codificar(WETH, monto_wei, safe, 0), "Aportar WETH como colateral a nombre del Safe"),
    ]
    efecto = {"token": A_WETH, "holder": safe, "direction": "increase", "min_delta": str(monto_wei * 999 // 1000)}
    return llamadas, efecto


def repagar_usdc(safe: str, monto: int) -> Tuple[List[Llamada], Dict[str, Any]]:
    """Repago de deuda variable en USDC a nombre del Safe. Approve por el monto exacto."""
    if monto <= 0:
        raise AccionNoPermitida("amount must be positive")
    safe = to_checksum_address(safe)
    llamadas = [
        Llamada(USDC, 0, APPROVE.codificar(AAVE_V3_POOL, monto), "Autorizar al Pool de Aave V3 por el monto exacto"),
        Llamada(AAVE_V3_POOL, 0, REPAY.codificar(USDC, monto, 2, safe), "Repagar deuda variable en USDC del Safe"),
    ]
    efecto = {"token": USDC_DEUDA_VARIABLE, "holder": safe, "direction": "decrease", "min_delta": str(monto * 999 // 1000)}
    return llamadas, efecto


ACCIONES = {"aportar_colateral_weth": aportar_colateral_weth, "repagar_usdc": repagar_usdc}
DESTINOS_PERMITIDOS = {to_checksum_address(d) for d in (WETH, USDC, AAVE_V3_POOL)}


def armar_safe_tx(llamadas: List[Llamada], nonce: int) -> SafeTx:
    for ll in llamadas:
        if to_checksum_address(ll.to) not in DESTINOS_PERMITIDOS:
            raise AccionNoPermitida(f"target {ll.to} is not allowed")
    if len(llamadas) == 1:
        ll = llamadas[0]
        return SafeTx(to_checksum_address(ll.to), ll.value, ll.data, CALL, 0, 0, 0, CERO, CERO, nonce)
    # Varias llamadas: una SafeTx que hace delegatecall solo a MultiSendCallOnly (no permite delegatecall internos).
    return SafeTx(MULTISEND_CALL_ONLY_1_4_1, 0, multisend(llamadas), DELEGATECALL, 0, 0, 0, CERO, CERO, nonce)
