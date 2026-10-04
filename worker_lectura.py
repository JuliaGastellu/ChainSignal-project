"""Worker de monitoreo de solo lectura (E05).

Lo corro como uno o más procesos aparte de la API:
    python -m worker_lectura

Cada paso programa evaluaciones vencidas, ejecuta jobs con lease (lectura de
posiciones Aave V3, reglas e incidentes) y entrega el outbox. Me niego a
arrancar fuera de CHAINSIGNAL_MODE=READ_ONLY: este worker es parte del
producto comercial y no debe convivir con la capa de firma.
"""

import asyncio
import signal

from loguru import logger

from infra.config import settings
from monitoreo.worker import WorkerMonitoreo
from protocolos.aave_v3 import construir_desde_settings


async def main() -> None:
    if not settings.is_read_only:
        raise SystemExit("worker_lectura solo corre con CHAINSIGNAL_MODE=READ_ONLY.")

    worker = WorkerMonitoreo(construir_desde_settings, lease_segundos=settings.WORKER_LEASE_SECONDS,
                             max_intentos=settings.WORKER_MAX_ATTEMPTS)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.detener)
        except NotImplementedError:
            pass  # Windows no soporta add_signal_handler; Ctrl+C corta el proceso.
    logger.info("Read-only monitoring worker starting. Mode: {}", settings.CHAINSIGNAL_MODE)
    await worker.correr(settings.WORKER_POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
