"""Reglas de monitoreo: validación y evaluación pura, sin base de datos.

Tres tipos de regla, cada una con su severidad declarada:
- health_factor_below: abre si el health factor cae bajo `threshold` y solo
  cierra tras `clear_after` evaluaciones seguidas por encima de `clear_above`
  (histéresis), para no abrir y cerrar en cada poll.
- debt_change: abre si la deuda cambió al menos `change_pct` % respecto de una
  línea base que fijo cuando no hay incidente abierto.
- stale_data: abre si la última lectura FRESH es más vieja que `max_age_seconds`.

Separo tres cosas que antes se mezclaban:
- severidad: la declara la política (low, medium, high, critical);
- calidad del dato: viene del snapshot (FRESH, STALE, PARTIAL, UNAVAILABLE);
- probabilidad: no la calculo. Ninguna regla devuelve una "confianza" que
  pueda leerse como probabilidad calibrada.

Si la regla no puede evaluarse con los datos disponibles (por ejemplo, health
factor con datos UNAVAILABLE), el resultado es "desconocido": no abre ni cuenta
como condición despejada.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

SEVERIDADES = ("low", "medium", "high", "critical")
TIPOS = ("health_factor_below", "debt_change", "stale_data")


class ReglaInvalida(ValueError):
    pass


def _decimal(valor: Any, campo: str, minimo: Optional[Decimal] = None) -> Decimal:
    if isinstance(valor, bool):
        raise ReglaInvalida(f"{campo} must be a number.")
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        raise ReglaInvalida(f"{campo} must be a number.")
    if not numero.is_finite() or (minimo is not None and numero < minimo):
        raise ReglaInvalida(f"{campo} is out of range.")
    return numero


def _entero(valor: Any, campo: str, minimo: int, maximo: int) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or not minimo <= valor <= maximo:
        raise ReglaInvalida(f"{campo} must be an integer between {minimo} and {maximo}.")
    return valor


def normalizar_regla(regla: Dict[str, Any]) -> Dict[str, Any]:
    """Valido y normalizo una regla. Guardo los decimales como texto para no perder precisión.

    Acepto también el formato heredado de E02 {metric: health_factor, operator: lt|lte, threshold}.
    """
    if not isinstance(regla, dict):
        raise ReglaInvalida("rule must be an object.")
    if "type" not in regla and regla.get("metric") == "health_factor" and regla.get("operator") in ("lt", "lte"):
        umbral = _decimal(regla.get("threshold"), "threshold", Decimal(0))
        regla = {"type": "health_factor_below", "threshold": str(umbral), "clear_above": str(umbral * Decimal("1.05"))}
    tipo = regla.get("type")
    if tipo not in TIPOS:
        raise ReglaInvalida(f"rule.type must be one of {', '.join(TIPOS)}.")
    severidad = regla.get("severity", "high" if tipo == "health_factor_below" else "medium")
    if severidad not in SEVERIDADES:
        raise ReglaInvalida(f"rule.severity must be one of {', '.join(SEVERIDADES)}.")
    escalar = _entero(regla.get("escalate_after_seconds", 3600), "escalate_after_seconds", 60, 7 * 86400)
    base = {"type": tipo, "severity": severidad, "escalate_after_seconds": escalar}
    permitidas = {"type", "severity", "escalate_after_seconds"}

    if tipo == "health_factor_below":
        umbral = _decimal(regla.get("threshold"), "threshold", Decimal(0))
        despeje = _decimal(regla.get("clear_above", str(umbral * Decimal("1.05"))), "clear_above", Decimal(0))
        if despeje < umbral:
            raise ReglaInvalida("clear_above must be greater than or equal to threshold.")
        base.update(threshold=str(umbral), clear_above=str(despeje),
                    clear_after=_entero(regla.get("clear_after", 2), "clear_after", 1, 20))
        permitidas |= {"threshold", "clear_above", "clear_after"}
    elif tipo == "debt_change":
        base.update(change_pct=str(_decimal(regla.get("change_pct"), "change_pct", Decimal("0.01"))))
        permitidas |= {"change_pct"}
    else:
        base.update(max_age_seconds=_entero(regla.get("max_age_seconds"), "max_age_seconds", 60, 7 * 86400))
        permitidas |= {"max_age_seconds"}

    sobrantes = set(regla) - permitidas - ({"metric", "operator"} if "metric" in regla else set())
    if sobrantes:
        raise ReglaInvalida(f"unknown rule fields: {', '.join(sorted(sobrantes))}.")
    return base


@dataclass
class Observacion:
    """Lo que el evaluador sabe de una cuenta en esta pasada."""

    calidad: str  # FRESH, STALE, PARTIAL, UNAVAILABLE
    health_factor: Optional[Decimal] = None  # None sin deuda o sin datos
    sin_deuda: Optional[bool] = None
    deuda_base: Optional[int] = None
    ultima_fresca_en: Optional[float] = None
    ahora: float = 0.0
    bloque: Optional[int] = None


@dataclass
class Veredicto:
    condicion: Optional[bool]  # True: se cumple; False: despejada; None: no evaluable
    valores: Dict[str, Any] = field(default_factory=dict)
    despejada: bool = False  # cumple el criterio de cierre (con histéresis)


def evaluar(regla: Dict[str, Any], obs: Observacion, linea_base: Optional[int]) -> Veredicto:
    tipo = regla["type"]
    if tipo == "health_factor_below":
        if obs.calidad not in ("FRESH",) or obs.sin_deuda is None:
            return Veredicto(None, {"data_quality": obs.calidad})
        if obs.sin_deuda:
            # Sin deuda no hay riesgo de liquidación: la condición está despejada.
            return Veredicto(False, {"health_factor": None, "no_debt": True}, despejada=True)
        hf = obs.health_factor
        valores = {"health_factor": str(hf), "threshold": regla["threshold"], "clear_above": regla["clear_above"]}
        if hf < Decimal(regla["threshold"]):
            return Veredicto(True, valores)
        return Veredicto(False, valores, despejada=hf >= Decimal(regla["clear_above"]))

    if tipo == "debt_change":
        if obs.calidad != "FRESH" or obs.deuda_base is None:
            return Veredicto(None, {"data_quality": obs.calidad})
        if linea_base is None:
            return Veredicto(False, {"debt_base": str(obs.deuda_base), "baseline": None})
        valores = {"debt_base": str(obs.deuda_base), "baseline": str(linea_base), "change_pct_threshold": regla["change_pct"]}
        if linea_base == 0:
            cambio = obs.deuda_base > 0
            valores["change_pct"] = None
        else:
            pct = abs(Decimal(obs.deuda_base - linea_base)) * 100 / Decimal(linea_base)
            valores["change_pct"] = str(pct.quantize(Decimal("0.01")))
            cambio = pct >= Decimal(regla["change_pct"])
        return Veredicto(cambio, valores)

    # stale_data: se evalúa siempre, justamente cuando los datos faltan.
    edad = None if obs.ultima_fresca_en is None else obs.ahora - obs.ultima_fresca_en
    valores = {"last_fresh_at": obs.ultima_fresca_en, "age_seconds": edad, "max_age_seconds": regla["max_age_seconds"],
               "data_quality": obs.calidad}
    atrasado = edad is None or edad > regla["max_age_seconds"]
    return Veredicto(atrasado, valores, despejada=not atrasado and obs.calidad == "FRESH")


def subir_severidad(severidad: str) -> str:
    indice = SEVERIDADES.index(severidad)
    return SEVERIDADES[min(indice + 1, len(SEVERIDADES) - 1)]


def describir_regla(regla: Dict[str, Any]) -> Dict[str, Any]:
    """Cuándo abre, cuándo se despeja y cuándo escala una regla ya normalizada.

    Lo uso para mostrarle a una persona el efecto de una política antes de
    guardarla, con los mismos valores que va a usar el evaluador.
    """
    tipo = regla["type"]
    base = {"type": tipo, "severity": regla["severity"], "escalate_after_seconds": regla["escalate_after_seconds"]}
    if tipo == "health_factor_below":
        return {**base,
                "opens": {"when": "health_factor_below", "threshold": regla["threshold"], "requires_fresh_data": True},
                "clears": {"when": "health_factor_at_or_above", "value": regla["clear_above"],
                           "consecutive_evaluations": regla["clear_after"], "also_when": "no_debt"}}
    if tipo == "debt_change":
        return {**base,
                "opens": {"when": "debt_change_at_least_pct", "change_pct": regla["change_pct"], "requires_fresh_data": True},
                "clears": {"when": "resolved_by_a_person"}}
    return {**base,
            "opens": {"when": "no_fresh_read_for_seconds", "max_age_seconds": regla["max_age_seconds"]},
            "clears": {"when": "first_fresh_read"}}
