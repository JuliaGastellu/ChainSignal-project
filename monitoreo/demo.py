"""Demo aislada con datos sintéticos (E06).

Cada demo es una organización propia marcada is_demo, con vencimiento
(DEMO_TTL_HOURS), un usuario owner generado y una cuenta con dirección
sintética. Sus posiciones salen de un escenario sintético codificado con el ABI
real: nunca consulto la red y los snapshots quedan marcados is_synthetic, así
no se mezclan con lecturas reales. El worker no programa organizaciones demo;
evalúo en el momento con evaluar_en_linea.
"""

import time
from typing import Any, Callable, Dict, Optional

from sqlalchemy import select
from sqlalchemy.engine import Engine

from identidad import seguridad
from identidad.recursos import ServicioRecursos
from identidad.servicio import ServicioIdentidad
from infra.config import settings
from infra.db import engine as engine_por_defecto
from infra.db_models import OutboxRecord
from monitoreo.evaluador import Evaluador
from monitoreo.notificaciones import ServicioNotificaciones
from monitoreo.trabajos import ColaTrabajos
from protocolos.abi import direccion
from protocolos.aave_v3 import AdaptadorAaveV3
from protocolos.replay import LectorReproduccion
from protocolos.sintetico import escenario_con_health_factor

# Dirección sintética, elegida para que no se confunda con una cuenta real.
DIRECCION_DEMO = direccion("0xde40000000000000000000000000000000000001")
HF_DEMO = "1.375"


def adaptador_demo(direccion_cuenta: str) -> AdaptadorAaveV3:
    escenario = escenario_con_health_factor(HF_DEMO, [direccion_cuenta])
    return AdaptadorAaveV3(LectorReproduccion(escenario.fixture()))


def evaluar_en_linea(engine_: Engine, organization_id: str, account_id: str, direccion_cuenta: str,
                     construir: Callable[[], Any], reloj: Callable[[], float] = time.time) -> str:
    """Evalúo una cuenta ahora mismo (demo) usando el mismo camino que el worker:
    job con lease, transacción con fencing y entrega del outbox sandbox."""
    cola = ColaTrabajos(engine_, reloj)
    cola.encolar("evaluate_account", organization_id, account_id, f"evaluate:{account_id}")
    trabajo = cola.tomar(f"inline:{account_id}"[:64], dedupe_key=f"evaluate:{account_id}")
    if trabajo is None:
        return "busy"
    estado = Evaluador(cola, construir, engine_, reloj).ejecutar(trabajo)
    notificaciones = ServicioNotificaciones(engine_, reloj)
    with notificaciones._Session() as s:
        pendientes = s.execute(select(OutboxRecord.id).where(
            OutboxRecord.organization_id == organization_id, OutboxRecord.status == "pending")).scalars().all()
    for outbox_id in pendientes:
        notificaciones.entregar_uno(f"inline:{organization_id}"[:64], outbox_id)
    return estado


def _poblar(engine_: Engine, ctx) -> None:
    """Cuenta sintética, dos políticas, un canal sandbox probado y un incidente abierto."""
    recursos, notificaciones = ServicioRecursos(engine_), ServicioNotificaciones(engine_)
    cuenta = recursos.crear_cuenta(ctx, DIRECCION_DEMO, 1, "Cuenta de demostración", "high", 300)
    recursos.crear_politica(ctx, "Health factor bajo 1,5", {"type": "health_factor_below", "threshold": "1.5",
                                                            "clear_above": "1.6", "severity": "high"})
    recursos.crear_politica(ctx, "Datos atrasados", {"type": "stale_data", "max_age_seconds": 1800, "severity": "medium"})
    canal = notificaciones.crear_canal(ctx, "sandbox", "Canal de demostración", {})
    notificaciones.probar_canal(ctx, canal["id"])
    evaluar_en_linea(engine_, ctx.organization_id, cuenta["id"], DIRECCION_DEMO, lambda: adaptador_demo(DIRECCION_DEMO))


def crear_demo(engine_: Optional[Engine] = None) -> Dict[str, Any]:
    """Creo una organización demo completa y devuelvo sus credenciales de sesión."""
    engine_ = engine_ or engine_por_defecto
    identidad = ServicioIdentidad(engine_)
    email = f"demo-{seguridad.nuevo_id()[:12]}@demo.invalid"
    contrasena = seguridad.nuevo_token()  # nadie la conoce: la demo entra solo por la sesión emitida aquí
    vence = time.time() + settings.DEMO_TTL_HOURS * 3600
    org_id, user_id = identidad.crear_organizacion_con_owner("Organización de demostración", email, contrasena,
                                                             es_demo=True, vence_en=vence)
    token, csrf, sesion = identidad.crear_sesion(user_id)
    _poblar(engine_, identidad.contexto(sesion, org_id, "owner"))
    return {"organization_id": org_id, "token": token, "csrf": csrf, "expires_at": vence}


NOMBRE_PRACTICA = "Práctica con datos sintéticos"


def crear_practica(sesion, engine_: Optional[Engine] = None) -> Dict[str, Any]:
    """Organización de práctica para una persona que ya tiene cuenta.

    Es una demo (is_demo, vence sola, datos sintéticos, fuera del worker y de la
    analítica comercial) donde esa persona es owner: puede practicar un
    incidente sin tocar su organización real ni cambiar de sesión. Si ya tiene
    una práctica vigente, devuelvo esa en lugar de crear otra.
    """
    from infra.db import get_session_factory
    from infra.db_models import MembershipRecord, OrganizationRecord

    engine_ = engine_ or engine_por_defecto
    identidad = ServicioIdentidad(engine_)
    ahora = time.time()
    with get_session_factory(engine_)() as s:
        vigente = s.execute(select(OrganizationRecord.id, OrganizationRecord.expires_at)
                            .join(MembershipRecord, MembershipRecord.organization_id == OrganizationRecord.id)
                            .where(MembershipRecord.user_id == sesion.user_id, OrganizationRecord.is_demo.is_(True),
                                   OrganizationRecord.name == NOMBRE_PRACTICA, OrganizationRecord.expires_at > ahora)).first()
    if vigente:
        return {"organization_id": vigente[0], "expires_at": vigente[1], "created": False}
    vence = ahora + settings.DEMO_TTL_HOURS * 3600
    # La persona ya existe: crear_organizacion_con_owner la reutiliza y no toca su contraseña.
    org_id, _ = identidad.crear_organizacion_con_owner(NOMBRE_PRACTICA, sesion.email, seguridad.nuevo_token(),
                                                       es_demo=True, vence_en=vence)
    _poblar(engine_, identidad.contexto(sesion, org_id, "owner"))
    return {"organization_id": org_id, "expires_at": vence, "created": True}
