"""Incidentes: apertura, escalamiento, acknowledgement, resolución y evidencia.

Reglas que sigo:
- Un solo episodio abierto (open o acknowledged) por política y cuenta. Lo
  garantiza un índice único parcial; si la condición sigue cumpliéndose en cada
  poll, actualizo el estado observado pero no emito alertas nuevas.
- Histéresis: health_factor_below solo cierra tras `clear_after` evaluaciones
  seguidas por encima de `clear_above`; stale_data cierra con la primera lectura
  fresca; debt_change no cierra solo, lo resuelve una persona.
- Escalamiento: si un incidente abierto no se reconoce en
  `escalate_after_seconds`, subo el nivel y la severidad y emito una alerta.
- La evidencia es de solo agregado. Una corrección es otra evidencia que apunta
  a la corregida (por ejemplo, cuando un reorg cambia el bloque de apertura).
- Alerta, filas de outbox (una por canal habilitado) y evento de la
  organización se escriben en la misma transacción que el cambio de incidente.
"""

import time
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.engine import Engine

from identidad import seguridad
from identidad.servicio import Conflicto, ContextoOrg, NoEncontrado, SolicitudInvalida, registrar_evento
from infra.db import engine as engine_por_defecto
from infra.db import get_session_factory, init_db
from infra.db_models import (
    AlertRecord,
    IncidentEvidenceRecord,
    IncidentRecord,
    MonitoredAccountRecord,
    NotificationChannelRecord,
    OutboxRecord,
    PolicyAccountStateRecord,
)
from monitoreo.reglas import Veredicto, subir_severidad

ABIERTOS = ("open", "acknowledged")


def _evidencia_a_dict(e: IncidentEvidenceRecord) -> Dict[str, Any]:
    return {"id": e.id, "kind": e.kind, "snapshot_id": e.snapshot_id, "block_number": e.block_number,
            "block_hash": e.block_hash, "observed": e.observed, "data_quality": e.data_quality, "note": e.note,
            "corrects_evidence_id": e.corrects_evidence_id, "created_at": e.created_at, "created_by_user_id": e.created_by_user_id}


def incidente_a_dict(i: IncidentRecord) -> Dict[str, Any]:
    return {
        "id": i.id, "account_id": i.account_id, "policy_id": i.policy_id, "policy_version": i.policy_version,
        "rule_type": i.rule_type, "status": i.status, "severity": i.severity, "escalation_level": i.escalation_level,
        "data_quality": i.data_quality, "opened_at": i.opened_at, "escalated_at": i.escalated_at,
        "acknowledged_at": i.acknowledged_at, "acknowledged_by_user_id": i.acknowledged_by_user_id,
        "resolved_at": i.resolved_at, "resolved_by_user_id": i.resolved_by_user_id, "resolution": i.resolution,
        "resolution_note": i.resolution_note, "last_evaluated_at": i.last_evaluated_at, "last_observed": i.last_observed,
    }


class ServicioIncidentes:
    def __init__(self, engine_: Optional[Engine] = None, reloj=time.time):
        self._engine = engine_ or engine_por_defecto
        init_db(self._engine)
        self._Session = get_session_factory(self._engine)
        self.reloj = reloj

    # --- escritura transaccional compartida ---------------------------------------

    def _alertar(self, s, incidente: IncidentRecord, tipo: str, cuenta_direccion: str, extra: Dict[str, Any]) -> str:
        ahora = self.reloj()
        alerta = AlertRecord(id=seguridad.nuevo_id(), organization_id=incidente.organization_id, incident_id=incidente.id,
                             kind=tipo, severity=incidente.severity, created_at=ahora)
        s.add(alerta)
        s.flush()
        canales = s.execute(select(NotificationChannelRecord).where(
            NotificationChannelRecord.organization_id == incidente.organization_id,
            NotificationChannelRecord.enabled.is_(True),
        )).scalars().all()
        mensaje = {
            "type": f"incident.{tipo}", "incident_id": incidente.id, "account_id": incidente.account_id,
            "account_address": cuenta_direccion, "rule_type": incidente.rule_type, "severity": incidente.severity,
            "escalation_level": incidente.escalation_level, "data_quality": incidente.data_quality,
            "observed": incidente.last_observed, **extra,
        }
        for canal in canales:
            s.add(OutboxRecord(organization_id=incidente.organization_id, channel_id=canal.id, alert_id=alerta.id,
                               idempotency_key=f"alert:{alerta.id}:{canal.id}", payload=mensaje, status="pending",
                               attempts=0, max_attempts=6, available_at=ahora, created_at=ahora))
        registrar_evento(s, incidente.organization_id, f"incident.{tipo}",
                         {"incident_id": incidente.id, "account_id": incidente.account_id, "severity": incidente.severity,
                          "rule_type": incidente.rule_type}, None)
        return alerta.id

    def _evidencia(self, s, incidente: IncidentRecord, tipo: str, snapshot: Dict[str, Any], observado: Dict[str, Any],
                   nota: Optional[str] = None, corrige: Optional[int] = None, autor: Optional[str] = None) -> IncidentEvidenceRecord:
        evidencia = IncidentEvidenceRecord(
            organization_id=incidente.organization_id, incident_id=incidente.id, kind=tipo,
            snapshot_id=snapshot.get("id"), block_number=snapshot.get("block_number"), block_hash=snapshot.get("block_hash"),
            observed=observado, data_quality=snapshot.get("data_quality", "UNKNOWN"), note=nota,
            corrects_evidence_id=corrige, created_at=self.reloj(), created_by_user_id=autor,
        )
        s.add(evidencia)
        s.flush()
        return evidencia

    def _estado(self, s, organization_id: str, policy_id: str, account_id: str) -> PolicyAccountStateRecord:
        estado = s.execute(select(PolicyAccountStateRecord).where(
            PolicyAccountStateRecord.policy_id == policy_id, PolicyAccountStateRecord.account_id == account_id,
        )).scalar_one_or_none()
        if estado is None:
            estado = PolicyAccountStateRecord(organization_id=organization_id, policy_id=policy_id, account_id=account_id,
                                              consecutive_clear=0, updated_at=self.reloj())
            s.add(estado)
            s.flush()
        return estado

    def abierto(self, s, policy_id: str, account_id: str) -> Optional[IncidentRecord]:
        return s.execute(select(IncidentRecord).where(
            IncidentRecord.policy_id == policy_id, IncidentRecord.account_id == account_id,
            IncidentRecord.status.in_(ABIERTOS),
        ).with_for_update()).scalar_one_or_none()

    def aplicar(self, s, cuenta: MonitoredAccountRecord, politica, version: int, regla: Dict[str, Any],
                veredicto: Veredicto, snapshot: Dict[str, Any]) -> List[str]:
        """Aplico un veredicto a la máquina de estados; devuelvo las alertas emitidas."""
        ahora = self.reloj()
        emitidas: List[str] = []
        estado = self._estado(s, cuenta.organization_id, politica.id, cuenta.id)
        incidente = self.abierto(s, politica.id, cuenta.id)
        if incidente is not None:
            incidente.last_evaluated_at = ahora

        if veredicto.condicion is None:
            return emitidas  # no evaluable: ni abre ni cuenta como despeje

        if veredicto.condicion:
            estado.consecutive_clear = 0
            if incidente is None:
                incidente = IncidentRecord(
                    id=seguridad.nuevo_id(), organization_id=cuenta.organization_id, account_id=cuenta.id,
                    policy_id=politica.id, policy_version=version, rule_type=regla["type"], status="open",
                    severity=regla["severity"], escalation_level=0, data_quality=snapshot.get("data_quality", "UNKNOWN"),
                    opened_at=ahora, last_evaluated_at=ahora, last_observed=veredicto.valores,
                )
                s.add(incidente)
                s.flush()
                self._evidencia(s, incidente, "opening", snapshot, veredicto.valores)
                emitidas.append(self._alertar(s, incidente, "opened", cuenta.address, {}))
            else:
                incidente.last_observed = veredicto.valores
                incidente.data_quality = snapshot.get("data_quality", incidente.data_quality)
                desde = incidente.escalated_at or incidente.opened_at
                if incidente.status == "open" and ahora - desde >= regla["escalate_after_seconds"]:
                    incidente.escalation_level += 1
                    incidente.severity = subir_severidad(incidente.severity)
                    incidente.escalated_at = ahora
                    self._evidencia(s, incidente, "escalation", snapshot, veredicto.valores,
                                    nota=f"Not acknowledged after {regla['escalate_after_seconds']} seconds.")
                    emitidas.append(self._alertar(s, incidente, "escalated", cuenta.address, {}))
        else:
            if incidente is None:
                estado.consecutive_clear = 0
                if regla["type"] == "debt_change" and estado.baseline_debt_base is None and snapshot.get("debt_base") is not None:
                    estado.baseline_debt_base = str(snapshot["debt_base"])
                    estado.baseline_block = snapshot.get("block_number")
            elif veredicto.despejada:
                estado.consecutive_clear += 1
                necesarias = regla.get("clear_after", 1) if regla["type"] == "health_factor_below" else 1
                if regla["type"] != "debt_change" and estado.consecutive_clear >= necesarias:
                    incidente.status, incidente.resolved_at, incidente.resolution = "resolved", ahora, "auto_cleared"
                    incidente.last_observed = veredicto.valores
                    self._evidencia(s, incidente, "resolution", snapshot, veredicto.valores,
                                    nota=f"Condition cleared for {estado.consecutive_clear} consecutive evaluation(s).")
                    emitidas.append(self._alertar(s, incidente, "resolved", cuenta.address, {}))
                    estado.consecutive_clear = 0
            else:
                estado.consecutive_clear = 0  # dentro de la banda de histéresis
        estado.updated_at = ahora
        return emitidas

    def corregir_por_reorg(self, s, incidente: IncidentRecord, bloque: int, hash_nuevo: str) -> bool:
        """Si la evidencia de apertura quedó en un bloque reorganizado, agrego una corrección (una sola vez)."""
        apertura = s.execute(select(IncidentEvidenceRecord).where(
            IncidentEvidenceRecord.incident_id == incidente.id, IncidentEvidenceRecord.kind == "opening",
        )).scalar_one_or_none()
        if apertura is None or apertura.block_number != bloque or apertura.block_hash in (None, hash_nuevo):
            return False
        ya = s.execute(select(IncidentEvidenceRecord.id).where(IncidentEvidenceRecord.corrects_evidence_id == apertura.id)).first()
        if ya is not None:
            return False
        self._evidencia(s, incidente, "correction", {"block_number": bloque, "block_hash": hash_nuevo, "data_quality": incidente.data_quality},
                        {"original_block_hash": apertura.block_hash, "canonical_block_hash": hash_nuevo},
                        nota="The opening block was reorganized; the original evidence is kept and the incident is re-evaluated.",
                        corrige=apertura.id)
        registrar_evento(s, incidente.organization_id, "incident.evidence_corrected",
                         {"incident_id": incidente.id, "corrects_evidence_id": apertura.id}, None)
        return True

    # --- acciones de personas (API) ---------------------------------------------------

    def _incidente(self, s, ctx: ContextoOrg, incident_id: str, bloquear: bool = False) -> IncidentRecord:
        consulta = select(IncidentRecord).where(IncidentRecord.id == incident_id, IncidentRecord.organization_id == ctx.organization_id)
        if bloquear:
            consulta = consulta.with_for_update()
        incidente = s.execute(consulta).scalar_one_or_none()
        if incidente is None:
            raise NoEncontrado("Incident not found.")
        return incidente

    def listar(self, ctx: ContextoOrg, estado: Optional[str] = None, limite: int = 50, desplazamiento: int = 0) -> List[Dict[str, Any]]:
        if not (1 <= limite <= 200) or desplazamiento < 0:
            raise SolicitudInvalida("limit must be 1..200 and offset >= 0.")
        with self._Session() as s:
            consulta = select(IncidentRecord).where(IncidentRecord.organization_id == ctx.organization_id)
            if estado is not None:
                if estado not in ("open", "acknowledged", "resolved", "active"):
                    raise SolicitudInvalida("status must be open, acknowledged, resolved or active.")
                consulta = consulta.where(IncidentRecord.status.in_(ABIERTOS) if estado == "active" else IncidentRecord.status == estado)
            filas = s.execute(consulta.order_by(IncidentRecord.opened_at.desc(), IncidentRecord.id).limit(limite).offset(desplazamiento)).scalars().all()
            return [incidente_a_dict(i) for i in filas]

    def obtener(self, ctx: ContextoOrg, incident_id: str) -> Dict[str, Any]:
        with self._Session() as s:
            incidente = self._incidente(s, ctx, incident_id)
            evidencias = s.execute(select(IncidentEvidenceRecord).where(
                IncidentEvidenceRecord.incident_id == incidente.id,
                IncidentEvidenceRecord.organization_id == ctx.organization_id,
            ).order_by(IncidentEvidenceRecord.id)).scalars().all()
            alertas = s.execute(select(AlertRecord).where(AlertRecord.incident_id == incidente.id)
                                .order_by(AlertRecord.created_at)).scalars().all()
            entregas = s.execute(select(OutboxRecord).where(OutboxRecord.alert_id.in_([a.id for a in alertas] or [""]))).scalars().all()
            return {
                **incidente_a_dict(incidente),
                "evidence": [_evidencia_a_dict(e) for e in evidencias],
                "alerts": [{"id": a.id, "kind": a.kind, "severity": a.severity, "created_at": a.created_at} for a in alertas],
                "deliveries": [{"alert_id": o.alert_id, "channel_id": o.channel_id, "status": o.status, "attempts": o.attempts,
                                "sent_at": o.sent_at, "last_error": o.last_error} for o in entregas],
            }

    def reconocer(self, ctx: ContextoOrg, incident_id: str) -> Dict[str, Any]:
        ctx.exigir_rol("operator")
        with self._Session() as s:
            incidente = self._incidente(s, ctx, incident_id, bloquear=True)
            if incidente.status != "open":
                raise Conflicto(f"Incident is {incidente.status}; only open incidents can be acknowledged.")
            incidente.status, incidente.acknowledged_at, incidente.acknowledged_by_user_id = "acknowledged", self.reloj(), ctx.user_id
            registrar_evento(s, ctx.organization_id, "incident.acknowledged", {"incident_id": incidente.id}, ctx.user_id)
            s.commit()
            resultado = incidente_a_dict(incidente)
        from comercial.analitica import registrar

        registrar(self._engine, ctx.organization_id, "incident_acknowledged", {"severity": resultado["severity"], "role": ctx.role})
        return resultado

    def resolver(self, ctx: ContextoOrg, incident_id: str, nota: str) -> Dict[str, Any]:
        ctx.exigir_rol("operator")
        nota = (nota or "").strip()
        if not nota or len(nota) > 500:
            raise SolicitudInvalida("A resolution note is required (max 500 characters).")
        with self._Session() as s:
            incidente = self._incidente(s, ctx, incident_id, bloquear=True)
            if incidente.status not in ABIERTOS:
                raise Conflicto("Incident is already resolved.")
            ahora = self.reloj()
            incidente.status, incidente.resolved_at, incidente.resolved_by_user_id = "resolved", ahora, ctx.user_id
            incidente.resolution, incidente.resolution_note = "manual", nota
            self._evidencia(s, incidente, "resolution", {"data_quality": incidente.data_quality}, incidente.last_observed,
                            nota=nota, autor=ctx.user_id)
            estado = self._estado(s, ctx.organization_id, incidente.policy_id, incidente.account_id)
            estado.baseline_debt_base, estado.baseline_block, estado.consecutive_clear = None, None, 0
            cuenta = s.get(MonitoredAccountRecord, incidente.account_id)
            self._alertar(s, incidente, "resolved", cuenta.address if cuenta else "", {"resolution_note": nota})
            s.commit()
            return incidente_a_dict(incidente)

    def corregir(self, ctx: ContextoOrg, incident_id: str, evidence_id: int, nota: str) -> Dict[str, Any]:
        """Corrección manual trazable: nunca edito la evidencia original."""
        ctx.exigir_rol("operator")
        nota = (nota or "").strip()
        if not nota or len(nota) > 500:
            raise SolicitudInvalida("A correction note is required (max 500 characters).")
        with self._Session() as s:
            incidente = self._incidente(s, ctx, incident_id)
            original = s.execute(select(IncidentEvidenceRecord).where(
                IncidentEvidenceRecord.id == evidence_id, IncidentEvidenceRecord.incident_id == incidente.id,
            )).scalar_one_or_none()
            if original is None:
                raise NoEncontrado("Evidence not found.")
            correccion = self._evidencia(s, incidente, "correction", {"block_number": original.block_number,
                                         "block_hash": original.block_hash, "data_quality": original.data_quality},
                                         {}, nota=nota, corrige=original.id, autor=ctx.user_id)
            registrar_evento(s, ctx.organization_id, "incident.evidence_corrected",
                             {"incident_id": incidente.id, "corrects_evidence_id": original.id}, ctx.user_id)
            s.commit()
            return _evidencia_a_dict(correccion)
