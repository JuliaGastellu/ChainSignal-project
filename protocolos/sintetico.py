"""Escenarios sintéticos de Aave V3 codificados con el ABI real.

Los uso en dos lugares: en las pruebas, para armar casos que no puedo grabar a
voluntad (deuda cero, E-mode, reorg, totales que no concilian), y en la demo,
que nunca consulta la red. Cada fixture lleva "synthetic": True; el lector de
reproducción lo propaga y los snapshots resultantes quedan marcados como
sintéticos, así nunca se mezclan con lecturas reales de la misma dirección.
Las direcciones de los activos son sintéticas.
"""

import hashlib
from dataclasses import dataclass, field
from typing import List

from eth_abi import encode

from protocolos import aave_v3
from protocolos.abi import direccion
from protocolos.replay import BALANCE_OF, GET_RESERVE_TOKENS_ADDRESSES, _clave

USUARIO = direccion("0x" + "c0" * 20)
MONEDA_BASE = "0x" + "0" * 40


def _dir(semilla: str) -> str:
    return direccion("0x" + hashlib.sha256(semilla.encode()).hexdigest()[:40])


@dataclass
class ReservaSintetica:
    simbolo: str
    decimales: int
    precio: int  # en unidades de la moneda base
    saldo: int = 0
    deuda_variable: int = 0
    deuda_estable: int = 0
    colateral: bool = True
    ltv_bps: int = 8000
    umbral_bps: int = 8250

    @property
    def activo(self) -> str:
        return _dir(f"activo-{self.simbolo}")

    def valor(self, unidades: int) -> int:
        return unidades * self.precio // 10**self.decimales


@dataclass
class EscenarioAave:
    bloque: int = 20_000_000
    reservas: List[ReservaSintetica] = field(default_factory=list)
    emode: int = 0
    unidad_base: int = 10**8
    pool: str = aave_v3.ADDRESS_BOOK["POOL"]
    ajuste_colateral: int = 0  # para forzar que los totales no concilien
    usuarios: List[str] = field(default_factory=lambda: [USUARIO])  # todos con la misma posición

    def totales(self):
        colateral = sum(r.valor(r.saldo) for r in self.reservas if r.colateral and r.umbral_bps) + self.ajuste_colateral
        deuda = sum(r.valor(r.deuda_variable + r.deuda_estable) for r in self.reservas)
        umbral = 8250 if colateral else 0
        ltv = 8000 if colateral else 0
        hf = 2**256 - 1 if deuda == 0 else colateral * umbral * 10**18 // (deuda * 10_000)
        disponible = max(0, colateral * ltv // 10_000 - deuda)
        return colateral, deuda, disponible, umbral, ltv, hf

    def fixture(self) -> dict:
        b = self.bloque
        llamadas = {}

        def responder(destino, funcion, argumentos, valores):
            llamadas[_clave(direccion(destino), funcion.codificar(*argumentos), b)] = "0x" + encode(list(funcion.salidas), list(valores)).hex()

        proveedor = aave_v3.ADDRESS_BOOK["POOL_ADDRESSES_PROVIDER"]
        oraculo = aave_v3.ADDRESS_BOOK["ORACLE"]
        dp = aave_v3.ADDRESS_BOOK["AAVE_PROTOCOL_DATA_PROVIDER"]
        responder(proveedor, aave_v3.GET_POOL, (), (self.pool,))
        responder(proveedor, aave_v3.GET_PRICE_ORACLE, (), (oraculo,))
        responder(proveedor, aave_v3.GET_POOL_DATA_PROVIDER, (), (dp,))
        responder(oraculo, aave_v3.BASE_CURRENCY_UNIT, (), (self.unidad_base,))
        responder(oraculo, aave_v3.BASE_CURRENCY, (), (MONEDA_BASE,))
        responder(dp, aave_v3.GET_ALL_RESERVES_TOKENS, (), ([(r.simbolo, r.activo) for r in self.reservas],))
        con_saldo = []
        for usuario in self.usuarios:
            usuario = direccion(usuario)
            responder(self.pool, aave_v3.GET_USER_ACCOUNT_DATA, (usuario,), self.totales())
            responder(self.pool, aave_v3.GET_USER_EMODE, (usuario,), (self.emode,))
            for r in self.reservas:
                responder(dp, aave_v3.GET_USER_RESERVE_DATA, (r.activo, usuario),
                          (r.saldo, r.deuda_estable, r.deuda_variable, 0, 0, 0, 0, 0, r.colateral))
        for r in self.reservas:
            if r.saldo or r.deuda_variable or r.deuda_estable:
                con_saldo.append(r)
                responder(dp, aave_v3.GET_RESERVE_CONFIGURATION_DATA, (r.activo,),
                          (r.decimales, r.ltv_bps, r.umbral_bps, 10500, 1000, True, True, False, True, False))
                responder(oraculo, aave_v3.GET_SOURCE_OF_ASSET, (r.activo,), (_dir(f"feed-{r.simbolo}"),))
                a_token, v_token = _dir(f"a-{r.simbolo}"), _dir(f"v-{r.simbolo}")
                responder(dp, GET_RESERVE_TOKENS_ADDRESSES, (r.activo,), (a_token, "0x" + "0" * 40, v_token))
                for usuario in self.usuarios:
                    responder(a_token, BALANCE_OF, (direccion(usuario),), (r.saldo,))
                    responder(v_token, BALANCE_OF, (direccion(usuario),), (r.deuda_variable,))
        if con_saldo:
            responder(oraculo, aave_v3.GET_ASSETS_PRICES, ([r.activo for r in con_saldo],), ([r.precio for r in con_saldo],))
        return {
            "chain_id": 1, "head": b + 12, "synthetic": True,
            "blocks": {str(b): {"hash": "0x" + hashlib.sha256(f"b{b}".encode()).hexdigest(), "timestamp": 1_750_000_000}},
            "calls": llamadas,
        }


def escenario_con_health_factor(hf_objetivo: str, usuarios: List[str], bloque: int = 20_000_000) -> EscenarioAave:
    """Colateral de 25.000 en WETH y deuda en USDC que da aproximadamente el HF pedido."""
    from decimal import Decimal

    deuda = int(Decimal("20625") / Decimal(hf_objetivo))  # umbral 82,5 % sobre 25.000
    return EscenarioAave(bloque=bloque, usuarios=list(usuarios), reservas=[
        ReservaSintetica("WETH", 18, 2_500 * 10**8, saldo=10 * 10**18),
        ReservaSintetica("USDC", 6, 10**8, deuda_variable=deuda * 10**6, colateral=False),
    ])


def escenario_activo() -> EscenarioAave:
    return EscenarioAave(reservas=[
        ReservaSintetica("WETH", 18, 2_500 * 10**8, saldo=10 * 10**18),
        ReservaSintetica("USDC", 6, 10**8, deuda_variable=15_000 * 10**6, colateral=False),
        ReservaSintetica("DAI", 18, 10**8),  # reserva sin saldo
    ])
