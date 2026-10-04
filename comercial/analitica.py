"""Eventos de producto para medir activación y uso (E09).

Registro solo nombres de una lista cerrada y propiedades enumeradas. No guardo
correos, direcciones, balances, montos de posiciones, nombres ni textos libres:
una propiedad fuera de la lista se rechaza. La organización figura por su id
interno, que ya existe en la base y no identifica a una persona.

Registrar un evento nunca rompe el producto: si falla, lo anoto en el log y sigo.
Algunos eventos cuentan una vez por organización (`once_key`); la unicidad la
garantiza la base.
"""

import time
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

EVENTOS = {
    "org_created", "account_added", "first_snapshot", "policy_created", "channel_tested",
    "incident_reviewed", "incident_acknowledged", "data_reviewed",
    "subscription_canceled", "subscription_resumed", "payment_confirmed",
}
# Eventos que cuentan una sola vez por organización (o por organización y día).
UNA_VEZ = {"org_created", "first_snapshot"}
UNA_VEZ_POR_DIA = {"data_reviewed"}
UNA_VEZ_POR_RECURSO = {"incident_reviewed"}

PROPIEDADES = {
    "role": {"owner", "operator", "viewer"},
    "rule_type": {"health_factor_below", "debt_change", "stale_data"},
    "channel_kind": {"sandbox", "webhook"},
    "source": {"api", "worker", "manual", "webhook", "signup", "cli"},
    "severity": {"low", "medium", "high", "critical"},
}


class EventoInvalido(ValueError):
    pass


def validar(nombre: str, propiedades: Dict[str, Any]) -> Dict[str, str]:
    if nombre not in EVENTOS:
        raise EventoInvalido(f"unknown event {nombre!r}")
    limpias = {}
    for clave, valor in (propiedades or {}).items():
        if clave not in PROPIEDADES or valor not in PROPIEDADES[clave]:
            raise EventoInvalido(f"property {clave!r} is not allowed")
        limpias[clave] = valor
    return limpias


def registrar(engine_: Optional[Engine], organization_id: str, nombre: str, propiedades: Optional[Dict[str, Any]] = None,
              recurso: Optional[str] = None, ahora: Optional[float] = None) -> bool:
    """Devuelvo True si guardé el evento; False si ya existía o si falló (sin propagar el error)."""
    from infra.db import engine as engine_por_defecto
    from infra.db import get_session_factory
    from infra.db_models import OrganizationRecord, ProductEventRecord

    try:
        limpias = validar(nombre, propiedades or {})
    except EventoInvalido as error:
        logger.warning("Analytics event rejected: {}", error)
        return False
    momento = ahora if ahora is not None else time.time()
    once_key = None
    if nombre in UNA_VEZ:
        once_key = f"{organization_id}:{nombre}"
    elif nombre in UNA_VEZ_POR_DIA:
        once_key = f"{organization_id}:{nombre}:{int(momento // 86400)}"
    elif nombre in UNA_VEZ_POR_RECURSO and recurso:
        once_key = f"{organization_id}:{nombre}:{recurso}"[:80]
    try:
        with get_session_factory(engine_ or engine_por_defecto)() as s:
            org = s.get(OrganizationRecord, organization_id)
            if org is None:
                return False
            s.add(ProductEventRecord(organization_id=organization_id, name=nombre, properties=limpias,
                                     is_demo=bool(org.is_demo), occurred_at=momento, once_key=once_key))
            s.commit()
            return True
    except IntegrityError:
        return False  # ya contado
    except Exception as error:  # la analítica no puede romper el producto
        logger.warning("Analytics event not stored: {}", type(error).__name__)
        return False
