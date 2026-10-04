"""Cola de jobs durable en la base, con leases y fencing.

- encolar: un índice único parcial sobre dedupe_key impide dos jobs activos
  (pending o running) para la misma cuenta; dos schedulers no duplican.
- tomar: elijo un job disponible (pending vencido, o running con lease vencido)
  con FOR UPDATE SKIP LOCKED y lo reclamo con un UPDATE condicional
  (compare-and-set sobre estado e intentos) que suma un intento y fija
  lease_owner y lease_expires_at. Dos workers nunca toman el mismo, tampoco en
  SQLite, donde SKIP LOCKED no existe.
- completar: verifico dentro de la transacción del llamador que el job sigue
  siendo mío (mismo lease_owner, mismo intento, running). Si otro worker lo
  retomó porque mi lease venció, la transacción falla y mis efectos no se
  confirman (fencing).
- reintentar: vuelvo a pending con available_at más backoff y jitter; al
  agotar max_attempts queda en dead.

No hay exactly-once: un job puede ejecutarse más de una vez si un worker muere
antes de confirmar. Por eso la evaluación es idempotente.
"""

import random
import time
from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from infra.db import engine as engine_por_defecto
from infra.db import get_session_factory, init_db
from infra.db_models import JobRecord, OrganizationRecord

# Veces que vuelvo a elegir candidato cuando otro proceso me ganó el reclamo.
INTENTOS_DE_RECLAMO = 5


class LeasePerdido(RuntimeError):
    """El job ya no es mío: otro worker lo retomó o terminó."""


@dataclass(frozen=True)
class TrabajoTomado:
    id: int
    kind: str
    organization_id: str
    account_id: Optional[str]
    intento: int
    max_intentos: int
    lease_owner: str


class ColaTrabajos:
    def __init__(self, engine_: Optional[Engine] = None, reloj: Callable[[], float] = time.time,
                 lease_segundos: float = 60.0, azar: Callable[[], float] = random.random):
        self._engine = engine_ or engine_por_defecto
        init_db(self._engine)
        self._Session = get_session_factory(self._engine)
        self.reloj = reloj
        self.lease_segundos = lease_segundos
        self.azar = azar

    @property
    def Session(self):
        return self._Session

    def encolar(self, kind: str, organization_id: str, account_id: Optional[str], dedupe_key: str,
                disponible_en: Optional[float] = None, max_intentos: int = 5) -> bool:
        ahora = self.reloj()
        with self._Session() as s:
            s.add(JobRecord(kind=kind, organization_id=organization_id, account_id=account_id, dedupe_key=dedupe_key,
                            status="pending", available_at=disponible_en if disponible_en is not None else ahora,
                            attempts=0, max_attempts=max_intentos, created_at=ahora, updated_at=ahora))
            try:
                s.commit()
                return True
            except IntegrityError:
                s.rollback()
                return False  # ya hay un job activo con esa clave

    def tomar(self, worker_id: str, dedupe_key: Optional[str] = None,
              solo_organizaciones_reales: bool = False) -> Optional[TrabajoTomado]:
        """Tomo un job disponible. solo_organizaciones_reales deja afuera las demos:
        el worker no las evalúa porque sus datos son sintéticos y se evalúan en línea."""
        conflictos = 0
        while conflictos < INTENTOS_DE_RECLAMO:
            ahora = self.reloj()
            disponible = (((JobRecord.status == "pending") & (JobRecord.available_at <= ahora))
                          | ((JobRecord.status == "running") & (JobRecord.lease_expires_at < ahora)))
            if dedupe_key is not None:
                disponible = disponible & (JobRecord.dedupe_key == dedupe_key)
            if solo_organizaciones_reales:
                demos = select(OrganizationRecord.id).where(OrganizationRecord.is_demo.is_(True))
                disponible = disponible & JobRecord.organization_id.not_in(demos)
            with self._Session() as s:
                candidato = s.execute(
                    select(JobRecord)
                    .where(disponible)
                    .order_by(JobRecord.available_at, JobRecord.id)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                ).scalars().first()
                if candidato is None:
                    return None
                # Reclamo con compare-and-set: la fila tiene que seguir disponible y con
                # el mismo número de intentos. En PostgreSQL ya la bloqueé con SKIP LOCKED;
                # en SQLite ese bloqueo no existe y esta condición es la que evita que dos
                # procesos tomen el mismo job.
                misma_fila = (JobRecord.id == candidato.id) & (JobRecord.attempts == candidato.attempts) & disponible
                if candidato.attempts >= candidato.max_attempts:
                    # Un lease vencido sin intentos restantes no se vuelve a tomar.
                    s.execute(update(JobRecord).where(misma_fila).values(
                        status="dead", finished_at=ahora, updated_at=ahora, lease_owner=None,
                        last_error=(candidato.last_error or "lease expired")[:300],
                    ).execution_options(synchronize_session=False))
                    s.commit()
                    continue
                reclamado = s.execute(update(JobRecord).where(misma_fila).values(
                    status="running", attempts=candidato.attempts + 1, lease_owner=worker_id,
                    lease_expires_at=ahora + self.lease_segundos, updated_at=ahora,
                ).execution_options(synchronize_session=False))
                if reclamado.rowcount != 1:
                    s.rollback()
                    conflictos += 1
                    continue  # otro proceso lo tomó entre la lectura y el reclamo
                tomado = TrabajoTomado(candidato.id, candidato.kind, candidato.organization_id, candidato.account_id,
                                       candidato.attempts + 1, candidato.max_attempts, worker_id)
                s.commit()
                return tomado
        return None

    def _mio(self, trabajo: TrabajoTomado):
        return (
            (JobRecord.id == trabajo.id) & (JobRecord.status == "running")
            & (JobRecord.lease_owner == trabajo.lease_owner) & (JobRecord.attempts == trabajo.intento)
        )

    def completar(self, sesion, trabajo: TrabajoTomado) -> None:
        """Marco el job como terminado dentro de la transacción del llamador (fencing)."""
        ahora = self.reloj()
        resultado = sesion.execute(
            update(JobRecord).where(self._mio(trabajo))
            .values(status="done", finished_at=ahora, updated_at=ahora, lease_owner=None, lease_expires_at=None)
        )
        if resultado.rowcount != 1:
            raise LeasePerdido(f"job {trabajo.id} is no longer leased by {trabajo.lease_owner}")

    def backoff(self, intento: int, base: float = 5.0, tope: float = 600.0) -> float:
        espera = min(tope, base * (2 ** max(0, intento - 1)))
        return espera * (0.5 + self.azar() / 2)

    def reintentar(self, trabajo: TrabajoTomado, error: str, espera: Optional[float] = None) -> str:
        """Devuelvo el estado final: pending (reintento) o dead (sin intentos)."""
        ahora = self.reloj()
        estado = "dead" if trabajo.intento >= trabajo.max_intentos else "pending"
        valores = dict(status=estado, last_error=error[:300], updated_at=ahora, lease_owner=None, lease_expires_at=None)
        if estado == "pending":
            valores["available_at"] = ahora + (espera if espera is not None else self.backoff(trabajo.intento))
        else:
            valores["finished_at"] = ahora
        with self._Session() as s:
            resultado = s.execute(update(JobRecord).where(self._mio(trabajo)).values(**valores))
            if resultado.rowcount != 1:
                s.rollback()
                raise LeasePerdido(f"job {trabajo.id} is no longer leased by {trabajo.lease_owner}")
            s.commit()
        return estado

    def estado(self, job_id: int) -> JobRecord:
        with self._Session() as s:
            return s.get(JobRecord, job_id)
