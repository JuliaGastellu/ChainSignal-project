"""Snapshots de posiciones y la interfaz de protocolo, sin dependencia del proveedor.

Un adaptador de protocolo recibe un lector de contratos (cualquier objeto con
red, eth_call(destino, datos, bloque), bloque(numero) y bloque_actual()) y lee
todo a un bloque explícito. Guardo dinero y escalas como enteros tal como los
devuelve el contrato; convierto a Decimal solo al presentar.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Protocol

from ingestion_onchain.modelos import CONTEXTO_MONTOS, escalar
from ingestion_onchain.resultados import BloqueRef, Calidad, Motivo

ESQUEMA_SNAPSHOT = "position-snapshot/1"
MAX_UINT256 = 2**256 - 1
WAD = 10**18
BPS = 10_000


class LectorContratos(Protocol):
    red: Any

    def eth_call(self, destino: str, datos: str, numero: int) -> str: ...

    def bloque(self, numero: int) -> BloqueRef: ...

    def bloque_actual(self) -> int: ...


@dataclass
class ActivoPosicion:
    """Una reserva en la que la cuenta tiene saldo o deuda, con su configuración al bloque."""

    activo: str
    simbolo: str
    decimales: int
    saldo_atoken: int
    deuda_estable: int
    deuda_variable: int
    usado_como_colateral: bool
    precio_base: int
    fuente_oraculo: str
    ltv_bps: int
    umbral_liquidacion_bps: int

    @property
    def deuda_total(self) -> int:
        return self.deuda_estable + self.deuda_variable

    def valor_base(self, unidades: int) -> int:
        # Misma aritmética entera que el Pool: unidades * precio / 10^decimales.
        return unidades * self.precio_base // (10**self.decimales)

    def presentar(self, unidad_base: int) -> Dict[str, Any]:
        return {
            "asset": self.activo,
            "symbol": self.simbolo,
            "decimals": self.decimales,
            "supplied": str(escalar(self.saldo_atoken, self.decimales)),
            "stable_debt": str(escalar(self.deuda_estable, self.decimales)),
            "variable_debt": str(escalar(self.deuda_variable, self.decimales)),
            "used_as_collateral": self.usado_como_colateral,
            "price_base": str(CONTEXTO_MONTOS.divide(Decimal(self.precio_base), Decimal(unidad_base))),
            "oracle_source": self.fuente_oraculo,
            "ltv_pct": str(Decimal(self.ltv_bps) / 100),
            "liquidation_threshold_pct": str(Decimal(self.umbral_liquidacion_bps) / 100),
            "raw": {
                "a_token_balance": str(self.saldo_atoken), "stable_debt": str(self.deuda_estable),
                "variable_debt": str(self.deuda_variable), "price_base": str(self.precio_base),
            },
        }


@dataclass
class SnapshotPosicion:
    protocolo: str
    mercado: str
    chain_id: int
    usuario: str
    bloque: Optional[BloqueRef]
    calidad: Calidad
    motivo: Motivo = Motivo.NINGUNO
    detalle: str = ""
    estado: str = "UNKNOWN"  # ACTIVE, COLLATERAL_ONLY, NO_POSITION, UNKNOWN
    colateral_base: Optional[int] = None
    deuda_base: Optional[int] = None
    disponible_base: Optional[int] = None
    umbral_liquidacion_bps: Optional[int] = None
    ltv_bps: Optional[int] = None
    health_factor_wad: Optional[int] = None
    unidad_base: Optional[int] = None
    moneda_base: Optional[str] = None
    categoria_emode: Optional[int] = None
    activos: List[ActivoPosicion] = field(default_factory=list)
    reservas_sin_leer: List[str] = field(default_factory=list)
    contratos: Dict[str, str] = field(default_factory=dict)
    conciliacion: Dict[str, Any] = field(default_factory=dict)
    limitaciones: List[str] = field(default_factory=list)
    leido_en: Optional[float] = None
    esquema: str = ESQUEMA_SNAPSHOT
    id: Optional[int] = None  # id en position_snapshots cuando está persistido
    sintetico: bool = False  # True solo para la demo y las pruebas; nunca se mezcla con lecturas reales

    @property
    def sin_deuda(self) -> bool:
        return self.deuda_base == 0

    def health_factor(self) -> Optional[Decimal]:
        """None cuando no hay deuda: el contrato devuelve uint256 máximo y no es un número útil."""
        if self.health_factor_wad is None or self.health_factor_wad == MAX_UINT256 or self.sin_deuda:
            return None
        return escalar(self.health_factor_wad, 18)

    def presentar(self) -> Dict[str, Any]:
        unidad = self.unidad_base or 1
        def base(valor):
            return None if valor is None or self.unidad_base is None else str(CONTEXTO_MONTOS.divide(Decimal(valor), Decimal(unidad)))
        hf = self.health_factor()
        return {
            "schema": self.esquema,
            "protocol": self.protocolo,
            "market": self.mercado,
            "chain_id": self.chain_id,
            "user": self.usuario,
            "block": {"number": self.bloque.numero, "hash": self.bloque.hash, "timestamp": self.bloque.timestamp} if self.bloque else None,
            "data_quality": {"status": self.calidad.value, "reason": self.motivo.value, "detail": self.detalle},
            "status": self.estado,
            "collateral_base": base(self.colateral_base),
            "debt_base": base(self.deuda_base),
            "available_borrows_base": base(self.disponible_base),
            "base_currency": self.moneda_base,
            "base_currency_unit": str(self.unidad_base) if self.unidad_base is not None else None,
            "health_factor": None if hf is None else str(hf),
            "no_debt": self.sin_deuda if self.deuda_base is not None else None,
            "liquidation_threshold_pct": None if self.umbral_liquidacion_bps is None else str(Decimal(self.umbral_liquidacion_bps) / 100),
            "ltv_pct": None if self.ltv_bps is None else str(Decimal(self.ltv_bps) / 100),
            "emode_category": self.categoria_emode,
            "assets": [a.presentar(unidad) for a in self.activos],
            "unread_reserves": list(self.reservas_sin_leer),
            "contracts": dict(self.contratos),
            "reconciliation": dict(self.conciliacion),
            "limitations": list(self.limitaciones),
            "read_at": self.leido_en,
            "synthetic": self.sintetico,
            "raw": {
                "total_collateral_base": None if self.colateral_base is None else str(self.colateral_base),
                "total_debt_base": None if self.deuda_base is None else str(self.deuda_base),
                "available_borrows_base": None if self.disponible_base is None else str(self.disponible_base),
                "health_factor_wad": None if self.health_factor_wad is None else str(self.health_factor_wad),
            },
        }



class ProtocoloLectura(Protocol):
    """Interfaz que cumple cada adaptador de protocolo."""

    protocolo: str
    mercado: str

    def leer_posicion(self, usuario: str, bloque: Optional[int] = None) -> SnapshotPosicion: ...
