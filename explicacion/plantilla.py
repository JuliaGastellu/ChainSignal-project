"""Explicación determinista por plantilla (E07).

Es el camino por defecto y el fallback de cualquier falla del modelo. Solo
redacta hechos de la entrada, cada uno con su referencia. No usa los
metadatos no confiables y no recomienda operar.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional

ESQUEMA_SALIDA = "chainsignal.explicacion.salida/1"

ESTADOS = {"open": "abierto", "acknowledged": "en seguimiento", "resolved": "resuelto"}

PROBLEMAS = {
    "reconciliation_mismatch": "los saldos no coincidieron con la verificación independiente",
    "no_debt_with_debt": "el snapshot dice que no hay deuda pero informa un monto de deuda",
    "health_factor_vs_collateral": "el health factor informado no coincide con el que resulta de colateral, deuda y umbral de liquidación",
    "observed_vs_snapshot": "el valor que evaluó la regla no coincide con el del snapshot",
}


def numero(valor: Any, decimales: int = 4) -> str:
    """Formato es-AR (coma decimal, punto de miles), redondeado y sin pasar por float."""
    paso = Decimal(1).scaleb(-decimales) if decimales > 0 else Decimal(1)
    texto = format(Decimal(str(valor)).quantize(paso, rounding=ROUND_HALF_UP), "f")
    entero, _, fraccion = texto.partition(".")
    signo = "-" if entero.startswith("-") else ""
    entero = f"{int(entero.lstrip('-')):,}".replace(",", ".")
    fraccion = fraccion.rstrip("0")
    return f"{signo}{entero},{fraccion}" if fraccion else f"{signo}{entero}"


def _bloque(snap: Dict[str, Any]) -> str:
    return numero(snap["block_number"], 0)


def _enunciado(texto: str, refs: List[str]) -> Dict[str, Any]:
    return {"text": texto, "refs": refs}


def explicar_con_plantilla(entrada: Dict[str, Any]) -> Dict[str, Any]:
    regla, obs = entrada["rule"], entrada.get("observed") or {}
    snap: Optional[Dict[str, Any]] = entrada.get("snapshot")
    incidente = entrada["incident"]
    ref_regla = regla["ref"]
    ref_snap = snap["ref"] if snap else None
    refs_dato = [ref_snap] if ref_snap else [ref_regla]
    apertura = next((e["ref"] for e in entrada.get("evidence") or [] if e.get("kind") == "opening"), None)
    consistente = entrada["checks"]["figures_consistent"]
    calidad = (snap or {}).get("data_quality") or incidente.get("data_quality")
    enunciados: List[Dict[str, Any]] = []
    advertencias: List[str] = []

    # 1. Estado del dato.
    if not snap:
        enunciados.append(_enunciado("No hay un snapshot de la posición asociado a este incidente.", [ref_regla]))
    elif calidad == "FRESH":
        enunciados.append(_enunciado(f"El snapshot del bloque {_bloque(snap)} tiene datos actualizados.", [ref_snap]))
    elif calidad == "STALE":
        enunciados.append(_enunciado(f"El snapshot del bloque {_bloque(snap)} está atrasado: describe la cuenta en ese bloque, no ahora.", [ref_snap]))
    elif calidad == "PARTIAL":
        enunciados.append(_enunciado(f"El snapshot del bloque {_bloque(snap)} está incompleto: faltan datos de la lectura.", [ref_snap]))
    else:
        enunciados.append(_enunciado("No hay datos disponibles de la cuenta. Esto no indica que la posición esté bien.", refs_dato))
    if calidad != "FRESH":
        advertencias.append("Con datos que no están actualizados no saco conclusiones sobre el estado actual de la posición.")

    # 2. La regla.
    tipo = regla.get("type")
    v = numero(regla["version"], 0)
    if not consistente:
        detalle = "; ".join(PROBLEMAS.get(p, p) for p in entrada["checks"]["problems"])
        enunciados.append(_enunciado(f"Las cifras no son consistentes entre sí: {detalle}.", refs_dato))
        advertencias.append("Hasta una nueva lectura consistente no comparo estas cifras con el umbral.")
        resumen = "Las cifras de este incidente no son consistentes entre sí; hace falta una nueva lectura antes de sacar conclusiones."
    elif tipo == "health_factor_below":
        umbral = numero(regla["threshold"])
        hf = (snap or {}).get("health_factor") or obs.get("health_factor")
        sin_deuda = (snap or {}).get("no_debt") if snap else obs.get("no_debt")
        refs = [r for r in (ref_snap, ref_regla) if r]
        if sin_deuda is True and calidad == "FRESH":
            enunciados.append(_enunciado(f"La cuenta no tiene deuda en ese bloque, así que no hay riesgo de liquidación y la regla de la versión {v} no se cumple.", refs))
            resumen = "La cuenta no tiene deuda: la condición de health factor no se cumple."
        elif hf is None or calidad != "FRESH":
            enunciados.append(_enunciado(f"No hay un health factor actualizado para comparar con el umbral {umbral} de la versión {v} de la política.", refs))
            resumen = "No hay datos actualizados para evaluar el health factor contra el umbral."
        elif Decimal(str(hf)) < Decimal(str(regla["threshold"])):
            enunciados.append(_enunciado(f"El health factor fue {numero(hf)}, por debajo del umbral {umbral} de la versión {v} de la política.", refs))
            resumen = f"El health factor ({numero(hf)}) está por debajo del umbral {umbral}."
        else:
            enunciados.append(_enunciado(f"El health factor fue {numero(hf)}, por encima del umbral {umbral} de la versión {v} de la política.", refs))
            resumen = f"El health factor ({numero(hf)}) está por encima del umbral {umbral}."
        if regla.get("clear_above") is not None:
            enunciados.append(_enunciado(
                f"El incidente se cierra solo cuando el health factor supera {numero(regla['clear_above'])} en {numero(regla.get('clear_after', 1), 0)} evaluaciones seguidas.",
                [ref_regla]))
    elif tipo == "debt_change":
        if obs.get("change_pct") is not None:
            enunciados.append(_enunciado(
                f"La deuda cambió {numero(obs['change_pct'], 2)} % respecto de la línea base; la versión {v} de la política abre un incidente desde {numero(regla['change_pct'], 2)} %.",
                [r for r in (ref_snap, ref_regla) if r]))
            resumen = f"La deuda cambió {numero(obs['change_pct'], 2)} % respecto de la línea base."
        elif obs.get("baseline") is not None:
            enunciados.append(_enunciado("La cuenta pasó de no tener deuda a tener deuda.", [r for r in (ref_snap, ref_regla) if r]))
            resumen = "La cuenta pasó de no tener deuda a tener deuda."
        else:
            enunciados.append(_enunciado(f"Todavía no hay una línea base de deuda para la versión {v} de la política.", [ref_regla]))
            resumen = "Todavía no hay una línea base de deuda para comparar."
    else:
        maximo = numero(Decimal(str(regla["max_age_seconds"])) / 60, 0)
        if obs.get("age_seconds") is None:
            enunciados.append(_enunciado(f"No hay ninguna lectura actualizada de la cuenta; la versión {v} de la política admite hasta {maximo} min.", [ref_regla]))
            resumen = "No hay ninguna lectura actualizada de la cuenta."
        else:
            edad = numero(Decimal(str(obs["age_seconds"])) / 60, 0)
            enunciados.append(_enunciado(f"El dato está atrasado: la última lectura actualizada tiene {edad} min y la versión {v} de la política admite hasta {maximo} min.", [ref_regla]))
            resumen = f"La última lectura actualizada tiene {edad} min."

    # 3. Estado del incidente.
    estado = ESTADOS.get(incidente.get("status"), "en estado desconocido")
    texto = f"El incidente está {estado}"
    if incidente.get("escalation_level"):
        texto += " y fue escalado porque nadie lo tomó a tiempo"
    enunciados.append(_enunciado(texto + ".", [apertura or ref_regla]))

    advertencias.append("Esta explicación describe datos; no es una recomendación de operar.")
    return {"schema": ESQUEMA_SALIDA, "summary": resumen, "statements": enunciados, "caveats": advertencias}
