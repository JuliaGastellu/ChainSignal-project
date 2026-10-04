"""Worker de monitoreo: programa, evalúa y entrega, fuera del proceso HTTP.

Cada paso:
1. programar: encola un job de evaluación por cada cuenta vencida. El índice
   único parcial evita duplicados aunque varios workers programen a la vez.
2. evaluar: toma jobs con lease (SKIP LOCKED) y los ejecuta con Evaluador.
3. entregar: despacha filas del outbox con lease y reintentos.

Puedo correr varios workers a la vez: ninguno toma el job ni la fila de outbox
de otro mientras su lease esté vigente.
"""

import asyncio
import socket
import time
import uuid
from typing import Any, Callable, Dict, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.engine import Engine

from infra.db import engine as engine_por_defecto
from infra.db import get_session_factory, init_db
from infra.db_models import MonitoredAccountRecord, OrganizationRecord, WorkerHeartbeatRecord
from monitoreo.evaluador import Evaluador
from monitoreo.notificaciones import ServicioNotificaciones
from monitoreo.trabajos import ColaTrabajos, LeasePerdido

TIPO_EVALUACION = "evaluate_account"


def id_de_worker() -> str:
    return f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"[:64]


class WorkerMonitoreo:
    def __init__(self, construir_adaptador: Callable[[], Any], engine_: Optional[Engine] = None,
                 reloj: Callable[[], float] = time.time, worker_id: Optional[str] = None,
                 lease_segundos: float = 60.0, max_intentos: int = 5, transportes: Optional[Dict[str, Any]] = None):
        self._engine = engine_ or engine_por_defecto
        init_db(self._engine)
        self._Session = get_session_factory(self._engine)
        self.reloj = reloj
        self.worker_id = worker_id or id_de_worker()
        self.max_intentos = max_intentos
        self.cola = ColaTrabajos(self._engine, reloj, lease_segundos)
        self.evaluador = Evaluador(self.cola, construir_adaptador, self._engine, reloj)
        self.notificaciones = ServicioNotificaciones(self._engine, reloj, transportes, lease_segundos)
        self.is_running = False
        self.iniciado_en = reloj()

    def programar(self) -> int:
        """Encolo evaluaciones de cuentas vencidas; devuelvo cuántos jobs nuevos creé."""
        ahora = self.reloj()
        with self._Session() as s:
            # Las organizaciones demo no se programan: sus datos son sintéticos y se evalúan en línea.
            cuentas = s.execute(select(MonitoredAccountRecord.id, MonitoredAccountRecord.organization_id,
                                       MonitoredAccountRecord.last_evaluation_at, MonitoredAccountRecord.interval_seconds)
                                .join(OrganizationRecord, OrganizationRecord.id == MonitoredAccountRecord.organization_id)
                                .where(OrganizationRecord.is_demo.is_(False))).all()
        from comercial.suscripciones import ServicioSuscripciones

        # Solo programo organizaciones con servicio vigente (E09). Una prueba
        # vencida o una gracia terminada dejan de monitorearse solas.
        suscripciones = ServicioSuscripciones(self._engine, self.reloj)
        con_servicio = {org: suscripciones.derecho(org).con_servicio for org in {o for _, o, _, _ in cuentas}}
        creados = 0
        for account_id, org_id, ultima, intervalo in cuentas:
            if not con_servicio[org_id]:
                continue
            if ultima is None or ahora - ultima >= intervalo:
                if self.cola.encolar(TIPO_EVALUACION, org_id, account_id, f"evaluate:{account_id}", max_intentos=self.max_intentos):
                    creados += 1
        return creados

    def evaluar_disponibles(self, maximo: int = 50) -> Dict[str, int]:
        resultados: Dict[str, int] = {}
        for _ in range(maximo):
            trabajo = self.cola.tomar(self.worker_id, solo_organizaciones_reales=True)
            if trabajo is None:
                break
            try:
                estado = self.evaluador.ejecutar(trabajo)
            except LeasePerdido:
                estado = "lease_lost"
            except Exception as error:  # una falla inesperada no tumba el worker
                logger.warning("[WORKER] job {} failed: {}", trabajo.id, type(error).__name__)
                try:
                    estado = "error_" + self.cola.reintentar(trabajo, type(error).__name__)
                except LeasePerdido:
                    estado = "lease_lost"
            resultados[estado] = resultados.get(estado, 0) + 1
        return resultados

    def entregar_disponibles(self, maximo: int = 100) -> Dict[str, int]:
        resultados: Dict[str, int] = {}
        for _ in range(maximo):
            estado = self.notificaciones.entregar_uno(self.worker_id)
            if estado is None:
                break
            resultados[estado] = resultados.get(estado, 0) + 1
        return resultados

    def paso(self) -> Dict[str, Any]:
        resultado = {"scheduled": self.programar(), "jobs": self.evaluar_disponibles(), "deliveries": self.entregar_disponibles()}
        self.latir(resultado)
        return resultado

    def latir(self, ultimo_paso: Dict[str, Any], error: Optional[str] = None) -> None:
        """Registro que sigo vivo y qué hice en el último paso (E08)."""
        with self._Session() as s:
            latido = s.get(WorkerHeartbeatRecord, self.worker_id)
            if latido is None:
                latido = WorkerHeartbeatRecord(worker_id=self.worker_id, hostname=socket.gethostname()[:100],
                                               started_at=self.iniciado_en, last_seen_at=self.reloj(), last_step={})
                s.add(latido)
            latido.last_seen_at, latido.last_step, latido.last_error = self.reloj(), ultimo_paso, error
            s.commit()

    async def correr(self, intervalo: float = 5.0) -> None:
        self.is_running = True
        logger.info("Monitoring worker {} running.", self.worker_id)
        while self.is_running:
            try:
                await asyncio.to_thread(self.paso)
            except Exception as error:
                logger.error("Monitoring worker step failed: {}", type(error).__name__)
                try:
                    await asyncio.to_thread(self.latir, {}, type(error).__name__[:100])
                except Exception:
                    pass  # sin base no puedo latir; la liveness lo va a notar
            await asyncio.sleep(intervalo)

    def detener(self) -> None:
        self.is_running = False
