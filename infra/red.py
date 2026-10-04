"""Red única del runtime: chain_id, proveedor y explorador en un solo lugar.

El producto lee Ethereum mainnet. No mezclo redes: Etherscan, el RPC, las
cuentas observadas y los enlaces al explorador salen de la misma Red, y cada
proveedor verifica eth_chainId en la primera llamada. Sepolia queda registrada
solo para los experimentos de experiments/, nunca para el producto.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Red:
    chain_id: int
    nombre: str
    es_testnet: bool
    explorador: str

    def url_tx(self, tx_hash: str) -> str:
        return f"{self.explorador}/tx/{tx_hash}"

    def url_direccion(self, direccion: str) -> str:
        return f"{self.explorador}/address/{direccion}"


ETHEREUM = Red(chain_id=1, nombre="ethereum", es_testnet=False, explorador="https://etherscan.io")
SEPOLIA = Red(chain_id=11155111, nombre="sepolia", es_testnet=True, explorador="https://sepolia.etherscan.io")

REDES = {r.chain_id: r for r in (ETHEREUM, SEPOLIA)}


class RedIncorrecta(RuntimeError):
    """El proveedor responde un chain_id distinto del configurado."""

    def __init__(self, esperado: int, recibido: object, proveedor: str):
        super().__init__(f"{proveedor} reports chain_id {recibido}; expected {esperado}.")
        self.esperado = esperado
        self.recibido = recibido
        self.proveedor = proveedor


def red_del_producto() -> Red:
    from infra.config import settings

    return REDES[settings.CHAIN_ID]


def verificar_chain_id(esperado: int, recibido: object, proveedor: str) -> None:
    """Acepto el chain_id como entero o como hexadecimal (eth_chainId)."""
    try:
        valor = int(recibido, 16) if isinstance(recibido, str) and recibido.startswith("0x") else int(recibido)
    except (TypeError, ValueError):
        raise RedIncorrecta(esperado, recibido, proveedor)
    if valor != esperado:
        raise RedIncorrecta(esperado, valor, proveedor)
