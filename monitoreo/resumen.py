"""Resumen de una organización y checklist de activación (E06).

Cuento solo lo que existe en la base de esa organización. La checklist sigue el
recorrido de activación: cuenta observada, primer snapshot, política, canal
probado e incidente revisado por una persona.
"""

from typing import Any, Dict, Optional

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
    PositionSnapshotRecord,
)


def resumen(ctx: ContextoOrg, engine_: Optional[Engine] = None) -> Dict[str, Any]:
    Session = get_session_factory(engine_ or engine_por_defecto)
    org_id = ctx.organization_id
    with Session() as s:
        org = s.get(OrganizationRecord, org_id)
        cuentas = s.execute(select(MonitoredAccountRecord).where(MonitoredAccountRecord.organization_id == org_id)).scalars().all()
        por_calidad: Dict[str, int] = {}
        for c in cuentas:
            clave = c.last_data_quality or "NOT_EVALUATED"
            por_calidad[clave] = por_calidad.get(clave, 0) + 1
        activos = s.execute(select(IncidentRecord.severity, func.count()).where(
            IncidentRecord.organization_id == org_id, IncidentRecord.status.in_(("open", "acknowledged"))
        ).group_by(IncidentRecord.severity)).all()
        politicas = s.execute(select(func.count()).select_from(AlertPolicyRecord).where(
            AlertPolicyRecord.organization_id == org_id, AlertPolicyRecord.enabled.is_(True))).scalar_one()
        canales = s.execute(select(NotificationChannelRecord.verified_at).where(
            NotificationChannelRecord.organization_id == org_id)).scalars().all()
        direcciones = [c.address for c in cuentas]
        snapshots = 0
        if direcciones:
            from protocolos.abi import direccion

            snapshots = s.execute(select(func.count()).select_from(PositionSnapshotRecord).where(
                PositionSnapshotRecord.user_address.in_([direccion(d) for d in direcciones]),
                PositionSnapshotRecord.is_synthetic.is_(bool(org.is_demo)),
            )).scalar_one()
        revisados = s.execute(select(func.count()).select_from(IncidentRecord).where(
            IncidentRecord.organization_id == org_id,
            or_(IncidentRecord.acknowledged_at.is_not(None), IncidentRecord.resolution == "manual"),
        )).scalar_one()
        ultima = max((c.last_evaluation_at for c in cuentas if c.last_evaluation_at), default=None)
    severidades = {sev: n for sev, n in activos}
    return {
        "organization": {"id": org.id, "name": org.name, "is_demo": bool(org.is_demo), "expires_at": org.expires_at},
        "accounts": len(cuentas),
        "accounts_by_data_quality": por_calidad,
        "active_incidents": sum(severidades.values()),
        "active_incidents_by_severity": severidades,
        "enabled_policies": politicas,
        "channels": len(canales),
        "verified_channels": sum(1 for v in canales if v),
        "last_evaluation_at": ultima,
        "checklist": {
            "account_added": len(cuentas) > 0,
            "first_snapshot": snapshots > 0,
            "policy_created": politicas > 0,
            "channel_verified": any(canales),
            "incident_reviewed": revisados > 0,
        },
    }
