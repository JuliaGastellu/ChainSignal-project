"""Resultados tipados de la ingesta: de dónde viene cada dato y cuán actual es.

Ninguna falla del proveedor termina como cero o lista vacía. Cada lectura
devuelve una Calidad y, si algo faltó, un Motivo:

- FRESH: leí la ventana pedida completa, hace menos de INGESTION_CACHE_TTL_SECONDS.
- STALE: el proveedor falló o no lo consulté, y devuelvo lo último guardado, que
  es más viejo que el TTL.
- PARTIAL: leí parte de la ventana pedida (paginación incompleta o un
  componente faltante).
- UNAVAILABLE: no tengo datos utilizables. Nunca lo interpreto como cuenta sana.

Una cuenta sin actividad es FRESH con sin_actividad=True: es un dato, no una falla.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class Calidad(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


# Orden de gravedad para combinar componentes.
_GRAVEDAD = {Calidad.FRESH: 0, Calidad.STALE: 1, Calidad.PARTIAL: 2, Calidad.UNAVAILABLE: 3}


def peor(*calidades: Calidad) -> Calidad:
    return max(calidades, key=lambda c: _GRAVEDAD[c])


class Motivo(str, Enum):
    NINGUNO = "none"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    RESPUESTA_INVALIDA = "invalid_response"
    PAGINACION_INCOMPLETA = "pagination_incomplete"
    ERROR_PROVEEDOR = "provider_error"
    RED_INCORRECTA = "wrong_network"
    NO_CONFIGURADO = "not_configured"
    COMPONENTE_FALTANTE = "component_missing"
    SIN_ARCHIVO = "archive_unavailable"
    NO_CONCILIA = "reconciliation_mismatch"
    REORG_DURANTE_LECTURA = "reorg_during_read"


class ErrorProveedor(Exception):
    """Falla de un proveedor ya clasificada; nunca la convierto en dato vacío."""

    def __init__(self, motivo: Motivo, detalle: str = "", reintentable: bool = False):
        super().__init__(detalle or motivo.value)
        self.motivo = motivo
        self.detalle = detalle or motivo.value
        self.reintentable = reintentable


@dataclass(frozen=True)
class BloqueRef:
    numero: int
    hash: str
    timestamp: int


@dataclass
class Procedencia:
    """Origen y alcance de una lectura."""

    proveedor: str
    chain_id: int
    red: str
    referencia: Optional[BloqueRef] = None
    obtenido_en: Optional[float] = None
    desde_bloque: Optional[int] = None
    hasta_bloque: Optional[int] = None
    historial_completo: bool = False
    paginas: int = 0
    reorg_detectado: bool = False

    def a_dict(self) -> Dict[str, Any]:
        datos = asdict(self)
        datos["referencia"] = asdict(self.referencia) if self.referencia else None
        return datos


@dataclass
class ResultadoIngesta:
    """Resultado de un componente (transacciones, tokens, balance)."""

    calidad: Calidad
    procedencia: Procedencia
    motivo: Motivo = Motivo.NINGUNO
    detalle: str = ""
    sin_actividad: bool = False
    filas: int = 0

    def a_dict(self) -> Dict[str, Any]:
        return {
            "status": self.calidad.value,
            "reason": self.motivo.value,
            "detail": self.detalle,
            "no_activity": self.sin_actividad,
            "rows": self.filas,
            "provenance": self.procedencia.a_dict(),
        }


@dataclass
class CalidadDatos:
    """Calidad combinada de todos los componentes de una wallet."""

    calidad: Calidad
    motivo: Motivo
    componentes: Dict[str, ResultadoIngesta] = field(default_factory=dict)

    @property
    def utilizable(self) -> bool:
        return self.calidad is not Calidad.UNAVAILABLE

    @property
    def permite_recomendacion_accionable(self) -> bool:
        """Solo recomiendo acciones con datos frescos y completos para la ventana."""
        return self.calidad is Calidad.FRESH

    def a_dict(self) -> Dict[str, Any]:
        transacciones = self.componentes.get("transactions")
        # "Sin actividad" solo mira el historial; el balance no es actividad.
        historial = [c for n, c in self.componentes.items() if n in ("transactions", "tokens")]
        disponibles = [c for c in historial if c.calidad is not Calidad.UNAVAILABLE]
        return {
            "status": self.calidad.value,
            "reason": self.motivo.value,
            "actionable_allowed": self.permite_recomendacion_accionable,
            "no_activity": bool(disponibles) and len(disponibles) == len(historial) and all(c.sin_actividad for c in disponibles),
            "complete_history": bool(transacciones and transacciones.procedencia.historial_completo),
            "components": {nombre: c.a_dict() for nombre, c in self.componentes.items()},
        }


def combinar(componentes: Dict[str, ResultadoIngesta], obligatorio: str = "transactions") -> CalidadDatos:
    """Si falta el componente obligatorio todo es UNAVAILABLE; si falta otro, PARTIAL."""
    principal = componentes[obligatorio]
    if principal.calidad is Calidad.UNAVAILABLE:
        return CalidadDatos(Calidad.UNAVAILABLE, principal.motivo, componentes)
    calidad = principal.calidad
    motivo = principal.motivo
    for nombre, componente in componentes.items():
        if nombre == obligatorio:
            continue
        aporte = Calidad.PARTIAL if componente.calidad is Calidad.UNAVAILABLE else componente.calidad
        if _GRAVEDAD[aporte] > _GRAVEDAD[calidad]:
            calidad = aporte
            motivo = Motivo.COMPONENTE_FALTANTE if componente.calidad is Calidad.UNAVAILABLE else componente.motivo
    return CalidadDatos(calidad, motivo, componentes)
