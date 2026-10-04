"""Evaluación de una cuenta observada: snapshot, reglas e incidentes.

1. Leo (o reutilizo, si el hash del bloque no cambió) el snapshot Aave V3 a la
   cabeza menos las confirmaciones. Esto pasa fuera de la transacción.
2. Si la lectura falló por una causa transitoria (429, timeout, error del
   proveedor) y me quedan intentos, reprogramo el job con backoff.
3. En una sola transacción: evalúo cada política vigente de la cuenta, aplico la
   máquina de estados de incidentes (con alertas, outbox y eventos), reviso si
   un reorg invalidó la evidencia de apertura, actualizo la cuenta y marco el
   job como terminado con fencing. Si perdí el lease, nada de esto se confirma.

Una nueva ejecución del mismo job es idempotente: el incidente abierto ya existe
y no se emite otra alerta de apertura.
"""

import time
from typing import Any, Callable, Optional

from sqlalchemy import or_, select
from sqlalchemy.engine import Engine

from identidad.servicio import registrar_evento
from infra.db import engine as engine_por_defecto
from infra.db import get_session_factory, init_db
from infra.db_models import AlertPolicyRecord, MonitoredAccountRecord, PolicyAccountStateRecord
from ingestion_onchain.resultados import Calidad, Motivo
from monitoreo.incidentes import ABIERTOS, ServicioIncidentes
from monitoreo.reglas import Observacion, ReglaInvalida, evaluar, normalizar_regla
from monitoreo.trabajos import ColaTrabajos, TrabajoTomado
from protocolos.servicio import ServicioPosiciones

MOTIVOS_TRANSITORIOS = {Motivo.RATE_LIMITED, Motivo.TIMEOUT, Motivo.ERROR_PROVEEDOR}


class Evaluador:
    def __init__(self, cola: ColaTrabajos, construir_adaptador: Callable[[], Any], engine_: Optional[Engine] = None,
                 reloj: Callable[[], float] = time.time):
        self._engine = engine_ or engine_por_defecto
        init_db(self._engine)
        self._Session = get_session_factory(self._engine)
        self.cola = cola
        self.construir_adaptador = construir_adaptador
        self.reloj = reloj
        self.posiciones = ServicioPosiciones(self._engine)
        self.incidentes = ServicioIncidentes(self._engine, reloj)

    def ejecutar(self, trabajo: TrabajoTomado) -> str:
        with self._Session() as s:
            cuenta = s.execute(select(MonitoredAccountRecord).where(
                MonitoredAccountRecord.id == trabajo.account_id,
                MonitoredAccountRecord.organization_id == trabajo.organization_id,
            )).scalar_one_or_none()
            direccion = cuenta.address if cuenta else None
        if direccion is None:
            with self._Session() as s:
                self.cola.completar(s, trabajo)  # la cuenta ya no existe
                s.commit()
            return "skipped"

        adaptador = self.construir_adaptador()
        snapshot = self.posiciones.leer_y_guardar(adaptador, direccion)
        if snapshot.id is not None:
            from comercial.analitica import registrar

            registrar(self._engine, trabajo.organization_id, "first_snapshot", {"source": "worker"})
        if snapshot.calidad is Calidad.UNAVAILABLE and snapshot.motivo in MOTIVOS_TRANSITORIOS and trabajo.intento < trabajo.max_intentos:
            self.cola.reintentar(trabajo, f"{snapshot.motivo.value}: {snapshot.detalle}")
            return "retry"

        referencia = {
            "id": snapshot.id,
            "block_number": snapshot.bloque.numero if snapshot.bloque else None,
            "block_hash": snapshot.bloque.hash if snapshot.bloque else None,
            "data_quality": snapshot.calidad.value,
            "debt_base": snapshot.deuda_base,
        }
        ahora = self.reloj()
        with self._Session() as s:
            cuenta = s.execute(select(MonitoredAccountRecord).where(
                MonitoredAccountRecord.id == trabajo.account_id,
                MonitoredAccountRecord.organization_id == trabajo.organization_id,
            ).with_for_update()).scalar_one()
            if snapshot.calidad is Calidad.FRESH:
                cuenta.last_fresh_at = ahora
            observacion = Observacion(
                calidad=snapshot.calidad.value,
                health_factor=snapshot.health_factor(),
                sin_deuda=None if snapshot.deuda_base is None else snapshot.deuda_base == 0,
                deuda_base=snapshot.deuda_base,
                ultima_fresca_en=cuenta.last_fresh_at or cuenta.created_at,
                ahora=ahora,
                bloque=referencia["block_number"],
            )
            politicas = s.execute(select(AlertPolicyRecord).where(
                AlertPolicyRecord.organization_id == cuenta.organization_id,
                AlertPolicyRecord.enabled.is_(True),
                or_(AlertPolicyRecord.account_id == cuenta.id, AlertPolicyRecord.account_id.is_(None)),
            ).order_by(AlertPolicyRecord.id)).scalars().all()
            for politica in politicas:
                try:
                    regla = normalizar_regla(politica.rule)
                except ReglaInvalida:
                    continue  # regla heredada que no sé evaluar: no la invento
                estado = s.execute(select(PolicyAccountStateRecord).where(
                    PolicyAccountStateRecord.policy_id == politica.id, PolicyAccountStateRecord.account_id == cuenta.id,
                )).scalar_one_or_none()
                linea_base = int(estado.baseline_debt_base) if estado and estado.baseline_debt_base is not None else None
                veredicto = evaluar(regla, observacion, linea_base)
                self.incidentes.aplicar(s, cuenta, politica, politica.current_version, regla, veredicto, referencia)
            self._corregir_reorgs_previos(s, cuenta, adaptador)
            cuenta.last_evaluation_at = ahora
            cuenta.last_data_quality = snapshot.calidad.value
            registrar_evento(s, cuenta.organization_id, "account.evaluated",
                             {"account_id": cuenta.id, "data_quality": snapshot.calidad.value,
                              "block_number": referencia["block_number"], "status": snapshot.estado}, None)
            self.cola.completar(s, trabajo)  # fencing: si perdí el lease, lanza y no confirmo nada
            s.commit()
        return "done"

    def _corregir_reorgs_previos(self, s, cuenta: MonitoredAccountRecord, adaptador) -> None:
        """Reviso que la evidencia de apertura de cada incidente abierto siga en la cadena canónica."""
        from infra.db_models import IncidentEvidenceRecord, IncidentRecord

        abiertos = s.execute(select(IncidentRecord).where(
            IncidentRecord.account_id == cuenta.id, IncidentRecord.status.in_(ABIERTOS))).scalars().all()
        for incidente in abiertos:
            apertura = s.execute(select(IncidentEvidenceRecord).where(
                IncidentEvidenceRecord.incident_id == incidente.id, IncidentEvidenceRecord.kind == "opening")).scalar_one_or_none()
            if apertura is None or apertura.block_number is None:
                continue
            try:
                canonico = adaptador.lector.bloque(apertura.block_number).hash
            except Exception:
                continue  # sin datos no afirmo un reorg
            self.incidentes.corregir_por_reorg(s, incidente, apertura.block_number, canonico)
