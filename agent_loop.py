"""Monitor de solo lectura de las cuentas observadas por cada organización.

Recorro monitored_accounts por prioridad, analizo cada cuenta con
AgentService.run_pipeline_core (análisis sin efectos on-chain) y guardo la
última evaluación, el riesgo y la decisión recomendada con
ServicioRecursos.registrar_evaluacion, que solo escribe si la cuenta sigue en
la misma organización y emite el evento en esa organización.

La API no arranca este loop en su lifespan (A22). Lo corro como proceso aparte
con `python -m worker_lectura`. El loop Guardian, que podía ejecutar, vive en
experiments/guardian_loop.py. Desde E02 ya no leo tracking.json: lo migro con
`python -m identidad.cli importar-legado`.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from loguru import logger

from identidad.recursos import ServicioRecursos
from services.agent_service import AgentService

_ORDEN_PRIORIDAD = {"high": 0, "medium": 1, "low": 2}


class AutonomousAgentLoop:
    """Loop de monitoreo de lectura: evalúa cuentas observadas y nunca ejecuta."""

    def __init__(self, service: AgentService, recursos: Optional[ServicioRecursos] = None):
        self.service = service
        self.recursos = recursos or ServicioRecursos()
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Arranco el loop en segundo plano."""
        if self.is_running:
            return
        self.is_running = True
        logger.info("Read-only monitor loop starting...")
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        """Detengo el loop de forma ordenada."""
        self.is_running = False
        if self._task:
            logger.info("Stopping read-only monitor loop...")
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Read-only monitor loop stopped.")

    @staticmethod
    def _corresponde_evaluar(cuenta: Dict[str, Any], ahora: float) -> bool:
        ultima = cuenta.get("last_evaluation_at")
        return ultima is None or (ahora - float(ultima)) >= int(cuenta.get("interval_seconds") or 300)

    def _cola(self, cuentas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(cuentas, key=lambda c: (_ORDEN_PRIORIDAD.get(c.get("priority"), 2), c.get("last_evaluation_at") or 0))

    async def run_once(self) -> Dict[str, Dict[str, Any]]:
        """Evalúo una vez cada cuenta que corresponde y devuelvo los resultados por account_id."""
        cuentas = await asyncio.to_thread(self.recursos.cuentas_para_monitorear)
        ahora = time.time()
        resultados: Dict[str, Dict[str, Any]] = {}
        for cuenta in self._cola(cuentas):
            if not self.is_running and self._task is not None:
                break
            if not self._corresponde_evaluar(cuenta, ahora):
                continue
            resultado = await self.evaluate_wallet(cuenta["address"])
            resultados[cuenta["id"]] = resultado
            await asyncio.to_thread(
                self.recursos.registrar_evaluacion,
                cuenta["organization_id"], cuenta["id"],
                resultado.get("decision"), resultado.get("risk_score"), resultado["status"],
                resultado.get("data_quality"),
            )
        return resultados

    async def evaluate_wallet(self, wallet_addr: str) -> Dict[str, Any]:
        """Analizo una dirección sin efectos on-chain."""
        try:
            reporte = await self.service.run_pipeline_core(wallet_addr)
        except Exception as e:
            logger.warning("[MONITOR] Could not analyze {}: {}", wallet_addr, e)
            return {"status": "error"}
        decision = (reporte.get("agent_decision") or {}).get("decision")
        calidad = (reporte.get("data_quality") or {}).get("status")
        if decision == "DATA_UNAVAILABLE":
            # Sin datos no actualizo decisión ni riesgo: no invento una cuenta sana.
            return {"status": "unavailable", "decision": None, "risk_score": None, "data_quality": calidad}
        riesgo = ((reporte.get("scores") or {}).get("risk") or {}).get("value")
        return {"status": "analyzed", "decision": decision, "risk_score": riesgo, "data_quality": calidad}

    async def _loop(self):
        """Ciclo principal."""
        while self.is_running:
            try:
                resultados = await self.run_once()
                if not resultados:
                    logger.debug("No accounts due for evaluation. Sleeping...")
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in read-only monitor cycle: {e}")
                await asyncio.sleep(30)
