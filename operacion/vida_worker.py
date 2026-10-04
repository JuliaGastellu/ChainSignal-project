"""Liveness del worker para el healthcheck del contenedor (E08).

    python -m operacion.vida_worker

Salgo con 0 si algún worker de este host latió en los últimos
WORKER_VIVO_SEGUNDOS; con 1 si no, o si no puedo leer la base.
"""

import socket
import sys
import time

from sqlalchemy import func, select


def main() -> int:
    from infra.db import get_session_factory
    from infra.db_models import WorkerHeartbeatRecord
    from operacion.metricas import WORKER_VIVO_SEGUNDOS

    try:
        with get_session_factory()() as s:
            ultimo = s.execute(select(func.max(WorkerHeartbeatRecord.last_seen_at)).where(
                WorkerHeartbeatRecord.hostname == socket.gethostname()[:100])).scalar_one()
    except Exception as error:
        print(f"worker liveness: database unavailable ({type(error).__name__})", file=sys.stderr)
        return 1
    if ultimo is None or time.time() - ultimo > WORKER_VIVO_SEGUNDOS:
        print("worker liveness: no recent heartbeat", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
