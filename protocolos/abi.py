"""Codificación mínima de llamadas eth_call y decodificación de resultados.

Uso eth_abi y eth_utils, que ya trae web3. Defino cada función por su firma
canónica de Solidity y los tipos de salida que publica el contrato oficial.
"""

from dataclasses import dataclass
from typing import Any, Tuple

from eth_abi import decode, encode
from eth_utils import keccak, to_checksum_address

from ingestion_onchain.resultados import ErrorProveedor, Motivo


@dataclass(frozen=True)
class Funcion:
    nombre: str
    entradas: Tuple[str, ...]
    salidas: Tuple[str, ...]

    @property
    def firma(self) -> str:
        return f"{self.nombre}({','.join(self.entradas)})"

    @property
    def selector(self) -> bytes:
        return keccak(text=self.firma)[:4]

    def codificar(self, *argumentos: Any) -> str:
        return "0x" + (self.selector + encode(list(self.entradas), list(argumentos))).hex()

    def decodificar(self, resultado_hex: str) -> Tuple[Any, ...]:
        datos = bytes.fromhex(resultado_hex[2:] if resultado_hex.startswith("0x") else resultado_hex)
        if not datos:
            # Un eth_call a una dirección sin código devuelve 0x: no es un cero válido.
            raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, f"{self.nombre} returned empty data")
        try:
            return decode(list(self.salidas), datos)
        except Exception:
            raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, f"{self.nombre} returned undecodable data")


def direccion(valor: str) -> str:
    return to_checksum_address(valor)


def llamar(lector, destino: str, funcion: Funcion, bloque: int, *argumentos: Any) -> Tuple[Any, ...]:
    return funcion.decodificar(lector.eth_call(destino, funcion.codificar(*argumentos), bloque))


def llamar_uno(lector, destino: str, funcion: Funcion, bloque: int, *argumentos: Any) -> Any:
    return llamar(lector, destino, funcion, bloque, *argumentos)[0]

