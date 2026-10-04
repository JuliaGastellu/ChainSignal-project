import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from infra.db import engine as default_engine
from infra.db import get_session_factory, init_db
from infra.db_models import ExecutionPlanEventRecord, ExecutionPlanRecord
from .models import ExecutionLifecycle, ExecutionPlan

# Los archivos de lock por plan (ExecutionRunner.run() los usa para serializar
# un mismo fingerprint) siguen en disco. Solo save_plan/load_plan/log_event/
# get_all_plans pasaron a la base; el lock distribuido queda pendiente.
STORAGE_BASE = Path("storage/plans")


class PersistenceManager:
    """Manages the lifecycle of execution plans.

    Persisto el estado del plan y su journal en la base (infra/db.py) en lugar
    de storage/plans/<fingerprint>/plan.json y journal.log, para que el ciclo
    de vida sobreviva un reinicio. El lock por plan sigue en disco.
    """

    def __init__(self, engine_: Optional[Engine] = None):
        self._engine = engine_ or default_engine
        init_db(self._engine)
        self._Session = get_session_factory(self._engine)

    # -- lock file paths (unchanged, file-based) --------------------------
    @staticmethod
    def _get_plan_dir(fingerprint: str) -> Path:
        return STORAGE_BASE / fingerprint

    @staticmethod
    def _get_lock_path(fingerprint: str) -> Path:
        return PersistenceManager._get_plan_dir(fingerprint) / "lock"

    # -- durable plan state -------------------------------------------------
    def save_plan(self, plan: ExecutionPlan) -> None:
        """Upserts a plan's current state into the database."""
        data = plan.to_dict()
        with self._Session() as session:
            record = session.get(ExecutionPlanRecord, plan.fingerprint)
            if record is None:
                record = ExecutionPlanRecord(fingerprint=plan.fingerprint)
                session.add(record)
            record.wallet = data["wallet"]
            record.risk_score = data["risk_score"]
            record.block_number = data["block_number"]
            record.lifecycle = data["lifecycle"]
            record.actions = data["actions"]
            record.context = data["context"]
            record.recovery = data["recovery"]
            record.created_at = data["created_at"]
            record.expires_at = data["expires_at"]
            record.updated_at = time.time()
            session.commit()

    def try_claim_plan(self, plan: ExecutionPlan) -> Tuple[bool, str]:
        """Decido si quien llama puede empezar a ejecutar `plan`.

        Cierra la carrera entre la lectura de idempotencia de
        ExecutionGuard.validate_plan() y el inicio real de la ejecución: el
        primer reclamo depende de la clave única en la base.

        Devuelvo (True, "") si puedo avanzar: no existía fila para el
        fingerprint o la existente estaba en FAILED/ABORTED. Devuelvo
        (False, motivo) si el plan está activo (CREATED/VALIDATED/EXECUTING)
        o COMPLETED. Advertencia: el re-reclamo de FAILED/ABORTED se hace con
        lectura y actualización, sin comparación atómica (hallazgo A06).
        """
        data = plan.to_dict()
        with self._Session() as session:
            record = session.get(ExecutionPlanRecord, plan.fingerprint)

            if record is None:
                record = ExecutionPlanRecord(
                    fingerprint=plan.fingerprint,
                    wallet=data["wallet"],
                    risk_score=data["risk_score"],
                    block_number=data["block_number"],
                    lifecycle=ExecutionLifecycle.EXECUTING.value,
                    actions=data["actions"],
                    context=data["context"],
                    recovery=data["recovery"],
                    created_at=data["created_at"],
                    expires_at=data["expires_at"],
                    updated_at=time.time(),
                )
                session.add(record)
                try:
                    session.commit()
                    return True, ""
                except IntegrityError:
                    # Otra llamada concurrente (por ejemplo, otro host sin el
                    # lock en archivo compartido) ganó la carrera entre mi
                    # SELECT y mi INSERT.
                    session.rollback()
                    return False, (
                        f"Execution plan {plan.fingerprint[:10]} was claimed by a "
                        "concurrent execution attempt."
                    )

            active_states = {
                ExecutionLifecycle.CREATED.value,
                ExecutionLifecycle.VALIDATED.value,
                ExecutionLifecycle.EXECUTING.value,
            }
            if record.lifecycle in active_states:
                return False, (
                    f"Execution plan {plan.fingerprint[:10]} is already active "
                    f"(lifecycle={record.lifecycle})."
                )
            if record.lifecycle == ExecutionLifecycle.COMPLETED.value:
                return False, f"Execution plan {plan.fingerprint[:10]} already completed."

            # FAILED or ABORTED: a legitimate retry, per the same policy
            # ExecutionGuard.validate_plan already applies. Re-claim it.
            record.lifecycle = ExecutionLifecycle.EXECUTING.value
            record.updated_at = time.time()
            session.commit()
            return True, ""

    def load_plan(self, fingerprint: str) -> Optional[ExecutionPlan]:
        """Cargo un plan desde la base."""
        with self._Session() as session:
            record = session.get(ExecutionPlanRecord, fingerprint)
            if record is None:
                return None
            data = {
                "wallet": record.wallet,
                "actions": record.actions,
                "risk_score": record.risk_score,
                "block_number": record.block_number,
                "context": record.context,
                "lifecycle": record.lifecycle,
                "recovery": record.recovery,
                "created_at": record.created_at,
                "expires_at": record.expires_at,
                "fingerprint": record.fingerprint,
            }
        return ExecutionPlan.from_dict(data)

    def log_event(self, fingerprint: str, event: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Appends an event to the durable, append-only plan journal."""
        with self._Session() as session:
            session.add(
                ExecutionPlanEventRecord(
                    fingerprint=fingerprint,
                    timestamp=time.time(),
                    event=event,
                    data=data or {},
                )
            )
            session.commit()

    def get_all_plans(self) -> List[ExecutionPlan]:
        """Lists all plans stored in the database."""
        with self._Session() as session:
            records = session.query(ExecutionPlanRecord).all()
            plans_data = [
                {
                    "wallet": r.wallet,
                    "actions": r.actions,
                    "risk_score": r.risk_score,
                    "block_number": r.block_number,
                    "context": r.context,
                    "lifecycle": r.lifecycle,
                    "recovery": r.recovery,
                    "created_at": r.created_at,
                    "expires_at": r.expires_at,
                    "fingerprint": r.fingerprint,
                }
                for r in records
            ]
        return [ExecutionPlan.from_dict(d) for d in plans_data]

    # -- manejo del lock en archivo (sin cambios) ---------------------------
    def acquire_lock(self, fingerprint: str, retries: int = 5, delay: float = 0.5) -> bool:
        """Intento tomar el lock en archivo del plan."""
        lock_path = self._get_lock_path(fingerprint)
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        for i in range(retries):
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return True
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(lock_path) > 600:
                        os.remove(lock_path)
                        continue
                except FileNotFoundError:
                    pass
                time.sleep(delay)
        return False

    def release_lock(self, fingerprint: str) -> None:
        """Releases the file lock."""
        lock_path = self._get_lock_path(fingerprint)
        try:
            os.remove(lock_path)
        except FileNotFoundError:
            pass
