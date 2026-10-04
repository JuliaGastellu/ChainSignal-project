"""Lectores de reproducción y grabación, y verificación independiente a bloque fijo.

- LectorGrabador envuelve un RPC real y registra cada eth_call y bloque leído.
- LectorReproduccion responde solo con lo grabado: una llamada no grabada es un
  error, nunca un cero. Así replico una lectura pública sin red.
- verificar_independiente compara los saldos del data provider con balanceOf de
  los aToken y debt tokens de cada reserva, al mismo bloque. Son contratos
  distintos que deberían coincidir.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from infra.red import REDES
from ingestion_onchain.resultados import BloqueRef, ErrorProveedor, Motivo
from protocolos.abi import Funcion, direccion, llamar, llamar_uno
from protocolos.modelos import SnapshotPosicion

GET_RESERVE_TOKENS_ADDRESSES = Funcion("getReserveTokensAddresses", ("address",), ("address", "address", "address"))
BALANCE_OF = Funcion("balanceOf", ("address",), ("uint256",))


def _clave(destino: str, datos: str, numero: int) -> str:
    return f"{destino.lower()}|{datos.lower()}|{numero}"


class LectorReproduccion:
    def __init__(self, fixture: Dict[str, Any]):
        self.fixture = fixture
        self.red = REDES[int(fixture["chain_id"])]
        self.llamadas: List[str] = []
        # Una fixture construida (no grabada de la red) produce snapshots sintéticos.
        self.sintetico = bool(fixture.get("synthetic", False))

    @classmethod
    def desde_archivo(cls, ruta: Path) -> "LectorReproduccion":
        return cls(json.loads(Path(ruta).read_text(encoding="utf-8")))

    def bloque_actual(self) -> int:
        return int(self.fixture["head"])

    def bloque(self, numero: int) -> BloqueRef:
        datos = self.fixture["blocks"].get(str(numero))
        if datos is None:
            raise ErrorProveedor(Motivo.SIN_ARCHIVO, f"block {numero} not recorded")
        return BloqueRef(numero, datos["hash"], int(datos["timestamp"]))

    def eth_call(self, destino: str, datos: str, numero: int) -> str:
        clave = _clave(destino, datos, numero)
        self.llamadas.append(clave)
        if clave not in self.fixture["calls"]:
            raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, f"eth_call not recorded: {clave[:80]}")
        return self.fixture["calls"][clave]


class LectorGrabador:
    def __init__(self, lector):
        self.lector = lector
        self.red = lector.red
        self.fixture: Dict[str, Any] = {"chain_id": lector.red.chain_id, "head": None, "blocks": {}, "calls": {}}

    def bloque_actual(self) -> int:
        cabeza = self.lector.bloque_actual()
        self.fixture["head"] = cabeza
        return cabeza

    def bloque(self, numero: int) -> BloqueRef:
        ref = self.lector.bloque(numero)
        self.fixture["blocks"][str(numero)] = {"hash": ref.hash, "timestamp": ref.timestamp}
        return ref

    def eth_call(self, destino: str, datos: str, numero: int) -> str:
        resultado = self.lector.eth_call(destino, datos, numero)
        self.fixture["calls"][_clave(destino, datos, numero)] = resultado
        return resultado

    def guardar(self, ruta: Path, metadatos: Dict[str, Any]) -> None:
        if self.fixture["head"] is None:
            self.fixture["head"] = max(int(b) for b in self.fixture["blocks"])
        Path(ruta).write_text(json.dumps({**self.fixture, "meta": metadatos}, indent=1, sort_keys=True), encoding="utf-8")


def verificar_independiente(lector, snapshot: SnapshotPosicion) -> Dict[str, Any]:
    """Comparo cada saldo del snapshot con balanceOf del token correspondiente al mismo bloque."""
    numero = snapshot.bloque.numero
    data_provider = snapshot.contratos["pool_data_provider"]
    diferencias = []
    for activo in snapshot.activos:
        a_token, deuda_estable_token, deuda_variable_token = (direccion(x) for x in llamar(lector, data_provider, GET_RESERVE_TOKENS_ADDRESSES, numero, activo.activo))
        comparaciones = [("a_token_balance", a_token, activo.saldo_atoken), ("variable_debt", deuda_variable_token, activo.deuda_variable)]
        if int(deuda_estable_token, 16) != 0:
            comparaciones.append(("stable_debt", deuda_estable_token, activo.deuda_estable))
        for campo, token, esperado in comparaciones:
            leido = int(llamar_uno(lector, token, BALANCE_OF, numero, snapshot.usuario))
            if leido != esperado:
                diferencias.append({"asset": activo.activo, "field": campo, "snapshot": str(esperado), "balance_of": str(leido)})
    return {"block": numero, "assets_checked": len(snapshot.activos), "differences": diferencias, "matches": not diferencias}
