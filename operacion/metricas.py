"""Métricas operativas del piloto (E08), calculadas desde la base.

    python -m operacion.metricas          # JSON
    GET /metrics (con METRICS_TOKEN)      # formato de texto de Prometheus

Mido lo que puedo comprobar con datos propios:

- cobertura: cuentas reales con una evaluación FRESH dentro de dos intervalos;
- frescura: antigüedad de la última evaluación y calidad por cuenta;
- jobs: estados, el pendiente más viejo y los muertos;
- workers: latidos recientes;
- detección: desde que se leyó el snapshot hasta que se abrió el incidente;
- entrega: desde que se creó la fila de outbox hasta que se envió;
- errores del proveedor: snapshots no FRESH por motivo;
- costo: el de las explicaciones con modelo. El costo del RPC no lo mido: depende
  del plan del proveedor y queda pendiente.

Las metas internas (RPO 1 h, RTO 4 h, cobertura 99 %, detección p95 < 60 s)
se comparan con lo medido, pero no son un SLA comercial.
"""

import json
import math
import sys
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from infra.db import engine as engine_por_defecto
from infra.db import get_session_factory
from infra.db_models import (
    IncidentEvidenceRecord,
    IncidentExplanationRecord,
    IncidentRecord,
    JobRecord,
    MonitoredAccountRecord,
    OrganizationRecord,
    OutboxRecord,
    PositionSnapshotRecord,
    WorkerHeartbeatRecord,
)

VENTANA = 86400  # latencias y errores de las últimas 24 h
WORKER_VIVO_SEGUNDOS = 120
METAS = {"rpo_seconds": 3600, "rto_seconds": 4 * 3600, "coverage_ratio": 0.99, "detection_p95_seconds": 60}


def percentil(valores: List[float], p: float) -> Optional[float]:
    """Percentil por rango más cercano; None sin datos."""
    if not valores:
        return None
    ordenados = sorted(valores)
    return round(ordenados[max(0, math.ceil(p / 100 * len(ordenados)) - 1)], 3)


def _resumen(valores: List[float]) -> Dict[str, Any]:
    return {"count": len(valores), "p50": percentil(valores, 50), "p95": percentil(valores, 95),
            "max": round(max(valores), 3) if valores else None}


def medir(engine_: Optional[Engine] = None, ahora: Optional[float] = None) -> Dict[str, Any]:
    ahora = ahora if ahora is not None else time.time()
    desde = ahora - VENTANA
    Session = get_session_factory(engine_ or engine_por_defecto)
    with Session() as s:
        cuentas = s.execute(select(MonitoredAccountRecord.last_evaluation_at, MonitoredAccountRecord.interval_seconds,
                                   MonitoredAccountRecord.last_data_quality)
                            .join(OrganizationRecord, OrganizationRecord.id == MonitoredAccountRecord.organization_id)
                            .where(OrganizationRecord.is_demo.is_(False))).all()
        jobs = dict(s.execute(select(JobRecord.status, func.count()).group_by(JobRecord.status)).all())
        pendiente_mas_viejo = s.execute(select(func.min(JobRecord.available_at)).where(
            JobRecord.status == "pending", JobRecord.available_at <= ahora)).scalar_one()
        errores_jobs = s.execute(select(JobRecord.last_error, func.count()).where(
            JobRecord.updated_at >= desde, JobRecord.last_error.is_not(None)).group_by(JobRecord.last_error)).all()
        latidos = s.execute(select(WorkerHeartbeatRecord.last_seen_at)).scalars().all()
        detecciones = s.execute(
            select(IncidentRecord.opened_at, PositionSnapshotRecord.read_at)
            .join(IncidentEvidenceRecord, (IncidentEvidenceRecord.incident_id == IncidentRecord.id)
                  & (IncidentEvidenceRecord.kind == "opening"))
            .join(PositionSnapshotRecord, PositionSnapshotRecord.id == IncidentEvidenceRecord.snapshot_id)
            .where(IncidentRecord.opened_at >= desde, PositionSnapshotRecord.is_synthetic.is_(False))).all()
        entregas = s.execute(select(OutboxRecord.created_at, OutboxRecord.sent_at).where(
            OutboxRecord.status == "sent", OutboxRecord.sent_at >= desde)).all()
        outbox = dict(s.execute(select(OutboxRecord.status, func.count()).group_by(OutboxRecord.status)).all())
        outbox_viejo = s.execute(select(func.min(OutboxRecord.created_at)).where(OutboxRecord.status == "pending")).scalar_one()
        no_frescos = s.execute(select(PositionSnapshotRecord.quality, PositionSnapshotRecord.quality_reason, func.count()).where(
            PositionSnapshotRecord.read_at >= desde, PositionSnapshotRecord.is_synthetic.is_(False),
            PositionSnapshotRecord.quality != "FRESH").group_by(PositionSnapshotRecord.quality, PositionSnapshotRecord.quality_reason)).all()
        snapshots = s.execute(select(func.count()).select_from(PositionSnapshotRecord).where(
            PositionSnapshotRecord.read_at >= desde, PositionSnapshotRecord.is_synthetic.is_(False))).scalar_one()
        costos = s.execute(select(IncidentExplanationRecord.cost_usd, IncidentExplanationRecord.created_at,
                                  IncidentExplanationRecord.source, IncidentExplanationRecord.fallback_reason)).all()

    cubiertas = sum(1 for ultima, intervalo, calidad in cuentas
                    if calidad == "FRESH" and ultima is not None and ahora - ultima <= 2 * intervalo)
    edades = [ahora - ultima for ultima, _, _ in cuentas if ultima is not None]
    calidades: Dict[str, int] = {}
    for _, _, calidad in cuentas:
        calidades[calidad or "NOT_EVALUATED"] = calidades.get(calidad or "NOT_EVALUATED", 0) + 1
    cobertura = (cubiertas / len(cuentas)) if cuentas else None
    deteccion = _resumen([max(0.0, abierto - leido) for abierto, leido in detecciones])
    costo_24h = sum((Decimal(c) for c, creado, _, _ in costos if creado >= desde), Decimal(0))
    return {
        "measured_at": ahora,
        "coverage": {"accounts": len(cuentas), "covered": cubiertas, "ratio": None if cobertura is None else round(cobertura, 4)},
        "freshness": {"evaluation_age_seconds": _resumen(edades), "never_evaluated": sum(1 for u, _, _ in cuentas if u is None),
                      "data_quality": calidades},
        "jobs": {"by_status": jobs, "oldest_pending_age_seconds": None if pendiente_mas_viejo is None else round(ahora - pendiente_mas_viejo, 3),
                 "errors_24h": {e[:60]: n for e, n in errores_jobs}},
        "workers": {"alive": sum(1 for v in latidos if ahora - v <= WORKER_VIVO_SEGUNDOS), "known": len(latidos),
                    "last_seen_age_seconds": None if not latidos else round(ahora - max(latidos), 3)},
        "detection_latency_seconds": deteccion,
        "delivery": {"latency_seconds": _resumen([enviado - creado for creado, enviado in entregas]), "by_status": outbox,
                     "oldest_pending_age_seconds": None if outbox_viejo is None else round(ahora - outbox_viejo, 3)},
        "provider": {"snapshots_24h": snapshots, "not_fresh_24h": {f"{q}:{r}": n for q, r, n in no_frescos}},
        "cost": {"explanations_usd_24h": str(costo_24h),
                 "explanations_usd_total": str(sum((Decimal(c) for c, _, _, _ in costos), Decimal(0))),
                 "model_calls_total": sum(1 for _, _, fuente, motivo in costos if fuente == "model" or motivo in
                                          ("validation_failed", "invalid_json")),
                 "rpc_usd": "pending: depends on the provider plan; not measured"},
        "targets": {**METAS, "internal_only": True,
                    "coverage_met": None if cobertura is None else cobertura >= METAS["coverage_ratio"],
                    "detection_p95_met": None if deteccion["p95"] is None else deteccion["p95"] < METAS["detection_p95_seconds"]},
    }


def a_prometheus(m: Dict[str, Any]) -> str:
    """Formato de texto de Prometheus, sin dependencias. Omito los valores sin dato."""
    lineas: List[str] = []

    def gauge(nombre: str, valor: Any, etiquetas: Optional[Dict[str, str]] = None) -> None:
        if valor is None:
            return
        texto = "" if not etiquetas else "{" + ",".join(f'{k}="{str(v).replace(chr(34), "")}"' for k, v in etiquetas.items()) + "}"
        lineas.append(f"chainsignal_{nombre}{texto} {float(valor)}")

    gauge("coverage_ratio", m["coverage"]["ratio"])
    gauge("accounts", m["coverage"]["accounts"])
    for p in ("p50", "p95", "max"):
        gauge("evaluation_age_seconds", m["freshness"]["evaluation_age_seconds"][p], {"quantile": p})
        gauge("detection_latency_seconds", m["detection_latency_seconds"][p], {"quantile": p})
        gauge("delivery_latency_seconds", m["delivery"]["latency_seconds"][p], {"quantile": p})
    for calidad, n in m["freshness"]["data_quality"].items():
        gauge("accounts_by_quality", n, {"quality": calidad})
    for estado, n in m["jobs"]["by_status"].items():
        gauge("jobs", n, {"status": estado})
    gauge("jobs_oldest_pending_age_seconds", m["jobs"]["oldest_pending_age_seconds"])
    for estado, n in m["delivery"]["by_status"].items():
        gauge("outbox", n, {"status": estado})
    gauge("workers_alive", m["workers"]["alive"])
    gauge("snapshots_24h", m["provider"]["snapshots_24h"])
    for motivo, n in m["provider"]["not_fresh_24h"].items():
        gauge("provider_not_fresh_24h", n, {"reason": motivo})
    gauge("explanations_cost_usd_24h", Decimal(m["cost"]["explanations_usd_24h"]))
    return "\n".join(lineas) + "\n"


def main() -> int:
    print(json.dumps(medir(), indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
