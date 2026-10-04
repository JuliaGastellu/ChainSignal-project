"""Adaptador de lectura de Aave V3 en Ethereum (mercado principal).

Fuentes que consulté el 4 de octubre de 2026, sin usar direcciones de memoria:
- Direcciones: bgd-labs/aave-address-book, src/AaveV3Ethereum.sol
  (biblioteca AaveV3Ethereum, autogenerada por el address book oficial).
- Firmas y salidas: aave-dao/aave-v3-origin (IPool, IPoolAddressesProvider,
  IPoolDataProvider/AaveProtocolDataProvider, AaveOracle).
- Escalas: GenericLogic.calculateUserAccountData calcula healthFactor con
  wadDiv (18 decimales) y devuelve type(uint256).max si la deuda es cero; LTV y
  umbral de liquidación son puntos básicos (10.000 = 100 %). La unidad de la
  moneda base no la supongo: leo AaveOracle.BASE_CURRENCY_UNIT() al mismo bloque.

Solo fijo el PoolAddressesProvider. Pool, oráculo y data provider los resuelvo
on-chain al bloque leído y los comparo con el address book; si difieren, lo
declaro como limitación. Todas las llamadas usan el mismo bloque explícito y
verifico que su hash no cambie durante la lectura.

Es de solo lectura: no hay ninguna función que firme ni envíe transacciones.
"""

import time
from typing import List, Optional

from infra.red import ETHEREUM, RedIncorrecta
from ingestion_onchain.resultados import Calidad, ErrorProveedor, Motivo
from protocolos.abi import Funcion, direccion, llamar, llamar_uno
from protocolos.modelos import ActivoPosicion, SnapshotPosicion

FUENTE_DIRECCIONES = "bgd-labs/aave-address-book src/AaveV3Ethereum.sol (consultado el 2026-10-04)"
ADDRESS_BOOK = {
    "POOL_ADDRESSES_PROVIDER": "0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e",
    "POOL": "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
    "ORACLE": "0x54586bE62E3c3580375aE3723C145253060Ca0C2",
    "AAVE_PROTOCOL_DATA_PROVIDER": "0x0a16f2FCC0D44FaE41cc54e079281D84A363bECD",
}

GET_POOL = Funcion("getPool", (), ("address",))
GET_PRICE_ORACLE = Funcion("getPriceOracle", (), ("address",))
GET_POOL_DATA_PROVIDER = Funcion("getPoolDataProvider", (), ("address",))
GET_USER_ACCOUNT_DATA = Funcion("getUserAccountData", ("address",), ("uint256",) * 6)
GET_USER_EMODE = Funcion("getUserEMode", ("address",), ("uint256",))
GET_ALL_RESERVES_TOKENS = Funcion("getAllReservesTokens", (), ("(string,address)[]",))
GET_USER_RESERVE_DATA = Funcion(
    "getUserReserveData", ("address", "address"),
    ("uint256", "uint256", "uint256", "uint256", "uint256", "uint256", "uint256", "uint40", "bool"),
)
GET_RESERVE_CONFIGURATION_DATA = Funcion(
    "getReserveConfigurationData", ("address",),
    ("uint256", "uint256", "uint256", "uint256", "uint256", "bool", "bool", "bool", "bool", "bool"),
)
GET_ASSETS_PRICES = Funcion("getAssetsPrices", ("address[]",), ("uint256[]",))
GET_SOURCE_OF_ASSET = Funcion("getSourceOfAsset", ("address",), ("address",))
BASE_CURRENCY_UNIT = Funcion("BASE_CURRENCY_UNIT", (), ("uint256",))
BASE_CURRENCY = Funcion("BASE_CURRENCY", (), ("address",))


def tolerancia_por_activo(activo: ActivoPosicion) -> int:
    """Máxima diferencia de redondeo esperable en moneda base para un activo.

    El Pool y el data provider pueden redondear distinto en una unidad del
    activo (piso vs techo al aplicar índices); una unidad vale
    ceil(precio / 10^decimales) en moneda base, más una por la división entera.
    """
    unidad = 10**activo.decimales
    return -(-activo.precio_base // unidad) + 1


def construir_desde_settings():
    """Adaptador sobre el RPC de mainnet configurado. Sin ETHEREUM_RPC_URL, las
    lecturas devuelven UNAVAILABLE (not_configured): no fabrico posiciones."""
    from infra.config import settings
    from ingestion_onchain.proveedores import PoliticaReintentos, RpcLectura

    if settings.AAVE_REPLAY_FIXTURE and not settings.is_production:
        from protocolos.replay import LectorReproduccion

        return AdaptadorAaveV3(LectorReproduccion.desde_archivo(settings.AAVE_REPLAY_FIXTURE), confirmaciones=12)
    rpc = RpcLectura(ETHEREUM, settings.ETHEREUM_RPC_URL, reintentos=PoliticaReintentos(intentos=settings.INGESTION_MAX_RETRIES),
                     timeout=settings.PROVIDER_TIMEOUT_SECONDS)
    return AdaptadorAaveV3(rpc, confirmaciones=settings.INGESTION_CONFIRMATIONS)


class AdaptadorAaveV3:
    protocolo = "aave-v3"
    mercado = "AaveV3Ethereum"

    def __init__(self, lector, confirmaciones: int = 12, reloj=time.time):
        self.lector = lector
        self.confirmaciones = confirmaciones
        self.reloj = reloj

    def _snapshot_vacio(self, usuario: str, calidad: Calidad, motivo: Motivo, detalle: str, bloque=None) -> SnapshotPosicion:
        return SnapshotPosicion(self.protocolo, self.mercado, ETHEREUM.chain_id, usuario, bloque, calidad, motivo, detalle,
                                leido_en=self.reloj(), limitaciones=[f"Addresses from {FUENTE_DIRECCIONES}."])

    def leer_posicion(self, usuario: str, bloque: Optional[int] = None) -> SnapshotPosicion:
        snapshot = self._leer_posicion(usuario, bloque)
        snapshot.sintetico = bool(getattr(self.lector, "sintetico", False))
        return snapshot

    def _leer_posicion(self, usuario: str, bloque: Optional[int] = None) -> SnapshotPosicion:
        usuario = direccion(usuario)
        if getattr(self.lector, "red", None) is None or self.lector.red.chain_id != ETHEREUM.chain_id:
            return self._snapshot_vacio(usuario, Calidad.UNAVAILABLE, Motivo.RED_INCORRECTA, "reader is not configured for Ethereum mainnet")
        try:
            return self._leer(usuario, bloque)
        except RedIncorrecta as error:
            return self._snapshot_vacio(usuario, Calidad.UNAVAILABLE, Motivo.RED_INCORRECTA, str(error))
        except ErrorProveedor as error:
            return self._snapshot_vacio(usuario, Calidad.UNAVAILABLE, error.motivo, error.detalle)

    def _leer(self, usuario: str, bloque: Optional[int]) -> SnapshotPosicion:
        numero = bloque if bloque is not None else self.lector.bloque_actual() - self.confirmaciones
        referencia = self.lector.bloque(numero)
        lector = self.lector
        limitaciones: List[str] = [f"Addresses resolved on-chain from PoolAddressesProvider; reference: {FUENTE_DIRECCIONES}."]

        proveedor = ADDRESS_BOOK["POOL_ADDRESSES_PROVIDER"]
        pool = direccion(llamar_uno(lector, proveedor, GET_POOL, numero))
        oraculo = direccion(llamar_uno(lector, proveedor, GET_PRICE_ORACLE, numero))
        data_provider = direccion(llamar_uno(lector, proveedor, GET_POOL_DATA_PROVIDER, numero))
        contratos = {"pool_addresses_provider": proveedor, "pool": pool, "oracle": oraculo, "pool_data_provider": data_provider}
        for clave, valor in (("POOL", pool), ("ORACLE", oraculo), ("AAVE_PROTOCOL_DATA_PROVIDER", data_provider)):
            if valor != direccion(ADDRESS_BOOK[clave]):
                limitaciones.append(f"{clave} at block {numero} is {valor}, differs from the address book ({ADDRESS_BOOK[clave]}).")

        colateral, deuda, disponible, umbral, ltv, hf = llamar(lector, pool, GET_USER_ACCOUNT_DATA, numero, usuario)
        emode = int(llamar_uno(lector, pool, GET_USER_EMODE, numero, usuario))
        unidad_base = int(llamar_uno(lector, oraculo, BASE_CURRENCY_UNIT, numero))
        moneda_base = direccion(llamar_uno(lector, oraculo, BASE_CURRENCY, numero))
        if unidad_base <= 0:
            raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, "BASE_CURRENCY_UNIT must be positive")

        reservas = llamar_uno(lector, data_provider, GET_ALL_RESERVES_TOKENS, numero)
        con_saldo, sin_leer = [], []
        for simbolo, activo in reservas:
            activo = direccion(activo)
            try:
                datos = llamar(lector, data_provider, GET_USER_RESERVE_DATA, numero, activo, usuario)
            except ErrorProveedor as error:
                if error.motivo in (Motivo.SIN_ARCHIVO, Motivo.NO_CONFIGURADO):
                    raise
                sin_leer.append(activo)
                continue
            saldo, deuda_estable, deuda_variable = int(datos[0]), int(datos[1]), int(datos[2])
            if saldo or deuda_estable or deuda_variable:
                con_saldo.append((str(simbolo), activo, saldo, deuda_estable, deuda_variable, bool(datos[8])))

        activos: List[ActivoPosicion] = []
        if con_saldo:
            precios = llamar_uno(lector, oraculo, GET_ASSETS_PRICES, numero, [c[1] for c in con_saldo])
            if len(precios) != len(con_saldo):
                raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, "getAssetsPrices returned a different number of prices")
            for (simbolo, activo, saldo, deuda_estable, deuda_variable, colateral_usuario), precio in zip(con_saldo, precios):
                config = llamar(lector, data_provider, GET_RESERVE_CONFIGURATION_DATA, numero, activo)
                fuente = direccion(llamar_uno(lector, oraculo, GET_SOURCE_OF_ASSET, numero, activo))
                activos.append(ActivoPosicion(
                    activo=activo, simbolo=simbolo, decimales=int(config[0]), saldo_atoken=saldo,
                    deuda_estable=deuda_estable, deuda_variable=deuda_variable, usado_como_colateral=colateral_usuario,
                    precio_base=int(precio), fuente_oraculo=fuente, ltv_bps=int(config[1]), umbral_liquidacion_bps=int(config[2]),
                ))

        final = lector.bloque(numero)
        snapshot = SnapshotPosicion(
            protocolo=self.protocolo, mercado=self.mercado, chain_id=ETHEREUM.chain_id, usuario=usuario, bloque=referencia,
            calidad=Calidad.FRESH, colateral_base=int(colateral), deuda_base=int(deuda), disponible_base=int(disponible),
            umbral_liquidacion_bps=int(umbral), ltv_bps=int(ltv), health_factor_wad=int(hf), unidad_base=unidad_base,
            moneda_base=moneda_base, categoria_emode=emode, activos=activos, reservas_sin_leer=sin_leer,
            contratos=contratos, limitaciones=limitaciones, leido_en=self.reloj(),
        )
        self._clasificar(snapshot)
        self._conciliar(snapshot)

        if final.hash != referencia.hash:
            snapshot.calidad, snapshot.motivo = Calidad.PARTIAL, Motivo.REORG_DURANTE_LECTURA
            snapshot.detalle = "block hash changed during the read (reorg); values may mix two chains"
        elif sin_leer:
            snapshot.calidad, snapshot.motivo = Calidad.PARTIAL, Motivo.COMPONENTE_FALTANTE
            snapshot.detalle = f"{len(sin_leer)} reserve(s) could not be read"
        elif not snapshot.conciliacion["reconciled"]:
            snapshot.calidad, snapshot.motivo = Calidad.PARTIAL, Motivo.NO_CONCILIA
            snapshot.detalle = "per-asset totals do not reconcile with getUserAccountData"
        return snapshot

    @staticmethod
    def _clasificar(s: SnapshotPosicion) -> None:
        if s.colateral_base == 0 and s.deuda_base == 0 and not s.activos:
            s.estado = "NO_POSITION"
        elif s.deuda_base == 0:
            s.estado = "COLLATERAL_ONLY"
        else:
            s.estado = "ACTIVE"
        if s.deuda_base == 0:
            s.limitaciones.append("No debt: health factor is not applicable (the Pool returns uint256 max).")
        if s.categoria_emode:
            s.limitaciones.append(
                f"E-mode category {s.categoria_emode} is active: account-level LTV and liquidation threshold include E-mode; "
                "per-asset LTV and threshold shown are the reserve defaults."
            )

    @staticmethod
    def _conciliar(s: SnapshotPosicion) -> None:
        """Comparo los totales del Pool con la suma independiente por activo al mismo bloque."""
        colateral_calc = sum(a.valor_base(a.saldo_atoken) for a in s.activos if a.usado_como_colateral and a.umbral_liquidacion_bps != 0)
        deuda_calc = sum(a.valor_base(a.deuda_total) for a in s.activos)
        tolerancia = sum(tolerancia_por_activo(a) for a in s.activos)
        colateral_ok = abs(colateral_calc - s.colateral_base) <= tolerancia
        deuda_ok = abs(deuda_calc - s.deuda_base) <= tolerancia
        s.conciliacion = {
            "collateral_reported": str(s.colateral_base), "collateral_computed": str(colateral_calc),
            "debt_reported": str(s.deuda_base), "debt_computed": str(deuda_calc),
            "tolerance_base_units": str(tolerancia), "collateral_ok": colateral_ok, "debt_ok": deuda_ok,
            "complete": not s.reservas_sin_leer, "reconciled": colateral_ok and deuda_ok and not s.reservas_sin_leer,
        }
