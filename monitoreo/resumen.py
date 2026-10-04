"""Resumen de una organización: qué necesita atención y si el monitoreo está preparado.

Cuento solo lo que existe en la base de esa organización y no invento
tendencias ni exposición.

- attention: incidentes activos ordenados por severidad (y antigüedad) y
  cuentas cuyo dato falta, está incompleto o atrasado. Cada ítem lleva su
  motivo, la frescura y lo necesario para enlazarlo.
- readiness ("monitoreo preparado"): lo derivo del estado vigente, no de
  hitos pasados. Hace falta una cuenta observada; una lectura válida ahora (la
  última lectura de esa cuenta en su cadena, protocolo y mercado es FRESH, la
  última evaluación no informó un problema y el dato no está atrasado); una
  política habilitada; y un webhook habilitado, con envíos externos encendidos
  en la instancia, cuyo destino aceptó la prueba y cuya última entrega no
  falló. Una posición sana puede quedar preparada sin esperar un incidente.
  Aparte informo `configured`: si alguna vez se completó cada paso. Así separo
  "la configuración está hecha" de "el circuito funciona ahora", y `issues`
  dice por qué una condición vigente no se cumple. En una demo o práctica todo
  es simulado y nunca cuenta como preparación.
- practice: si alguien ya revisó un incidente (lo practicado), aparte de la preparación.
"""

import time
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.engine import Engine

from identidad.servicio import ContextoOrg
from infra.db import engine as engine_por_defecto
from infra.db import get_session_factory
from infra.db_models import (
    AlertPolicyRecord,
    IncidentRecord,
    MonitoredAccountRecord,
    NotificationChannelRecord,
    OrganizationRecord,
    OutboxRecord,
    PositionSnapshotRecord,
)
from protocolos.aave_v3 import AdaptadorAaveV3

ORDEN_SEVERIDAD = {"critical": 0, "high": 1, "medium": 2, "low": 3}
CALIDADES_CON_PROBLEMA = ("UNAVAILABLE", "PARTIAL", "STALE")


def _ventana(intervalo: int) -> int:
    # Igual que la interfaz: más de dos intervalos (mínimo 15 min) es dato atrasado.
    return max(2 * intervalo, 900)


def _atrasada(ultima: Optional[float], intervalo: int, ahora: float) -> bool:
    return ultima is not None and ahora - ultima > _ventana(intervalo)


def _lectura_vigente(s, cuenta: MonitoredAccountRecord, sintetico: bool, ahora: float) -> Optional[str]:
    """None si la cuenta tiene una lectura válida ahora; si no, el motivo."""
    from protocolos.abi import direccion

    ultimo = s.execute(select(PositionSnapshotRecord.quality, PositionSnapshotRecord.read_at).where(
        PositionSnapshotRecord.chain_id == cuenta.chain_id,
        PositionSnapshotRecord.protocol == AdaptadorAaveV3.protocolo,
        PositionSnapshotRecord.market == AdaptadorAaveV3.mercado,
        PositionSnapshotRecord.user_address == direccion(cuenta.address),
        PositionSnapshotRecord.is_synthetic.is_(sintetico),
    ).order_by(PositionSnapshotRecord.read_at.desc(), PositionSnapshotRecord.id.desc()).limit(1)).first()
    # Una lectura que falló no se guarda como snapshot: la última evaluación la registra en la cuenta.
    if cuenta.last_data_quality in ("UNAVAILABLE", "PARTIAL", "STALE"):
        return cuenta.last_data_quality.lower()
    if ultimo is None:
        return "no_read"
    if ultimo.quality != "FRESH":
        return ultimo.quality.lower()
    # La evaluación del worker confirma frescura (last_fresh_at) aunque el bloque no haya cambiado y no se guarde otro snapshot.
    confirmado = max(ultimo.read_at, cuenta.last_fresh_at or 0)
    if ahora - confirmado > _ventana(cuenta.interval_seconds):
        return "outdated"
    return None


def _canal_vigente(s, canal: NotificationChannelRecord, envios_habilitados: bool) -> Optional[str]:
    """None si el webhook puede entregar ahora; si no, el motivo."""
    if not canal.verified_at:
        return "not_tested"
    if not envios_habilitados:
        return "webhooks_disabled"
    if not canal.enabled:
        return "channel_disabled"
    ultimo = s.execute(select(OutboxRecord.status).where(
        OutboxRecord.channel_id == canal.id, OutboxRecord.status.in_(("sent", "failed", "dead")),
    ).order_by(OutboxRecord.id.desc()).limit(1)).scalar_one_or_none()
    if ultimo in ("failed", "dead"):
        return "last_delivery_failed"
    return None


# Cuando hay varios motivos elijo el más accionable para mostrar.
_PRIORIDAD_DATO = ("unavailable", "partial", "stale", "outdated", "no_read")
_PRIORIDAD_CANAL = ("webhooks_disabled", "channel_disabled", "last_delivery_failed", "not_tested")


def _primero(motivos: List[str], prioridad) -> Optional[str]:
    return next((m for m in prioridad if m in motivos), None)


def resumen(ctx: ContextoOrg, engine_: Optional[Engine] = None, ahora: Optional[float] = None) -> Dict[str, Any]:
    from infra.config import settings

    ahora = ahora if ahora is not None else time.time()
    Session = get_session_factory(engine_ or engine_por_defecto)
    org_id = ctx.organization_id
    with Session() as s:
        org = s.get(OrganizationRecord, org_id)
        cuentas = s.execute(select(MonitoredAccountRecord).where(MonitoredAccountRecord.organization_id == org_id)
                            .order_by(MonitoredAccountRecord.created_at)).scalars().all()
        por_calidad: Dict[str, int] = {}
        for c in cuentas:
            clave = c.last_data_quality or "NOT_EVALUATED"
            por_calidad[clave] = por_calidad.get(clave, 0) + 1
        activos = s.execute(select(IncidentRecord).where(
            IncidentRecord.organization_id == org_id, IncidentRecord.status.in_(("open", "acknowledged")))).scalars().all()
        politicas = s.execute(select(func.count()).select_from(AlertPolicyRecord).where(
            AlertPolicyRecord.organization_id == org_id, AlertPolicyRecord.enabled.is_(True))).scalar_one()
        politicas_total = s.execute(select(func.count()).select_from(AlertPolicyRecord).where(
            AlertPolicyRecord.organization_id == org_id)).scalar_one()
        registros_canal = s.execute(select(NotificationChannelRecord).where(
            NotificationChannelRecord.organization_id == org_id)).scalars().all()
        canales = [(c.kind, c.verified_at) for c in registros_canal]
        sintetico = bool(org.is_demo)
        motivos_dato = [_lectura_vigente(s, c, sintetico, ahora) for c in cuentas]
        lectura_valida = any(m is None for m in motivos_dato)
        lectura_alguna_vez = False
        if cuentas:
            from protocolos.abi import direccion

            lectura_alguna_vez = s.execute(select(func.count()).select_from(PositionSnapshotRecord).where(
                PositionSnapshotRecord.user_address.in_([direccion(c.address) for c in cuentas]),
                PositionSnapshotRecord.is_synthetic.is_(sintetico),
                PositionSnapshotRecord.quality == "FRESH",
            )).scalar_one() > 0
        webhooks = [c for c in registros_canal if c.kind == "webhook"]
        motivos_canal = [_canal_vigente(s, c, settings.NOTIFICATIONS_WEBHOOKS_ENABLED) for c in webhooks]
        webhook_vigente = any(m is None for m in motivos_canal)
        revisados = s.execute(select(func.count()).select_from(IncidentRecord).where(
            IncidentRecord.organization_id == org_id,
            or_(IncidentRecord.acknowledged_at.is_not(None), IncidentRecord.resolution == "manual"),
        )).scalar_one()
    etiquetas = {c.id: (c.label, c.address) for c in cuentas}

    atencion: List[Dict[str, Any]] = []
    for i in sorted(activos, key=lambda x: (ORDEN_SEVERIDAD.get(x.severity, 9), x.opened_at)):
        etiqueta, direccion_cuenta = etiquetas.get(i.account_id, (None, None))
        atencion.append({"kind": "incident", "incident_id": i.id, "account_id": i.account_id, "account_label": etiqueta,
                         "account_address": direccion_cuenta, "rule_type": i.rule_type, "severity": i.severity,
                         "status": i.status, "observed": i.last_observed, "data_quality": i.data_quality,
                         "opened_at": i.opened_at, "last_evaluated_at": i.last_evaluated_at})
    con_incidente = {i.account_id for i in activos}
    for c in cuentas:
        problema = c.last_data_quality in CALIDADES_CON_PROBLEMA or _atrasada(c.last_evaluation_at, c.interval_seconds, ahora)
        if problema and c.id not in con_incidente:
            atencion.append({"kind": "data", "account_id": c.id, "account_label": c.label, "account_address": c.address,
                             "data_quality": c.last_data_quality, "stale": _atrasada(c.last_evaluation_at, c.interval_seconds, ahora),
                             "last_evaluated_at": c.last_evaluation_at})

    severidades: Dict[str, int] = {}
    for i in activos:
        severidades[i.severity] = severidades.get(i.severity, 0) + 1
    webhook_verificado = any(kind == "webhook" and verificado for kind, verificado in canales)
    preparacion = {
        "account_observed": len(cuentas) > 0,
        "valid_read": lectura_valida,
        "policy_enabled": politicas > 0,
        "external_channel_verified": webhook_vigente and not org.is_demo,
    }
    configurado = bool(cuentas) and lectura_alguna_vez and politicas_total > 0 and webhook_verificado and not org.is_demo
    motivos = {
        "valid_read": None if lectura_valida or not cuentas else _primero([m for m in motivos_dato if m], _PRIORIDAD_DATO),
        "policy_enabled": None if politicas > 0 else ("paused" if politicas_total > 0 else "none"),
        "external_channel_verified": None if preparacion["external_channel_verified"] else (
            "simulated_only" if org.is_demo else _primero([m for m in motivos_canal if m], _PRIORIDAD_CANAL) or "none"),
    }
    return {
        "organization": {"id": org.id, "name": org.name, "is_demo": bool(org.is_demo), "expires_at": org.expires_at},
        "attention": atencion,
        "readiness": {**preparacion, "ready": all(preparacion.values()) and not org.is_demo, "simulated": bool(org.is_demo),
                      "configured": configurado, "issues": motivos},
        "practice": {"incident_reviewed": revisados > 0},
        "accounts": len(cuentas),
        "accounts_by_data_quality": por_calidad,
        "active_incidents": len(activos),
        "active_incidents_by_severity": severidades,
        "enabled_policies": politicas,
        "channels": {"total": len(canales), "simulated": sum(1 for k, _ in canales if k == "sandbox"),
                     "external": sum(1 for k, _ in canales if k == "webhook"), "external_verified": sum(
                         1 for k, v in canales if k == "webhook" and v), "webhooks_enabled": settings.NOTIFICATIONS_WEBHOOKS_ENABLED},
        "last_evaluation_at": max((c.last_evaluation_at for c in cuentas if c.last_evaluation_at), default=None),
    }
