"""Loop Guardian del experimento testnet, fuera del runtime comercial.

Antes la API lo exponía con POST /agent/start y era una segunda vía de
escritura: en cada ciclo podía transferir o desplegar mediante AgentExecutor,
sin ExecutionGuard ni presupuesto individual (A02). Ahora la API no lo importa
y su constructor exige CHAINSIGNAL_MODE=TESTNET_EXPERIMENT.
"""

import asyncio
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

from agent_executor.executor import AgentExecutor
from agent_reasoning.reasoning_engine import ReasoningEngine
from agent_runtime.event_bus import AgentEventBus
from experiments.testnet_ejecucion import ExperimentoEjecucionTestnet
from generacion_features.extractor import ExtractorFeatures
from infra.modo import exigir_escritura_experimental
from experiments.testnet_ejecucion import ingesta_sepolia
from perfil_wallet.behavioral_scoring import BehavioralScorer
from watch_queue.queue_manager import QueueManager


class GuardianAgentLoop:
    def __init__(self, service: "ExperimentoEjecucionTestnet", event_bus: AgentEventBus):
        exigir_escritura_experimental("guardian_loop")
        self.service = service
        self.event_bus = event_bus
        self.queue = QueueManager()
        self.reasoning = ReasoningEngine()
        self.executor = AgentExecutor(event_bus=self.event_bus)
        self.extractor = ExtractorFeatures()
        self.client = ingesta_sepolia()
        self.scorer = BehavioralScorer()
        self.is_running = False
        self.stop_requested = False
        self.cycles_completed = 0
        self._task: Optional[asyncio.Task] = None
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = int(os.getenv("CACHE_TTL", "300"))
        self._interval = int(os.getenv("MONITOR_INTERVAL", "20"))

    async def start(self) -> Dict[str, Any]:
        if self.is_running:
            return {"status": "already_running", "cycles_completed": self.cycles_completed}
        
        # Clean up any stale locks from previous crashes
        logger.info("Cleaning up stale locks before starting agent loop...")
        await asyncio.to_thread(self.service.lock_manager.cleanup_stale_locks)
        
        self.is_running = True
        self.stop_requested = False
        self._task = asyncio.create_task(self._run())
        await self.event_bus.publish({"type": "loop_started", "timestamp": datetime.utcnow().isoformat()})
        return {"status": "started"}

    async def stop(self) -> Dict[str, Any]:
        self.stop_requested = True
        await self.event_bus.publish({"type": "loop_stop_requested", "timestamp": datetime.utcnow().isoformat()})
        return {"status": "stop_requested"}

    async def _run(self) -> None:
        while self.is_running:
            cycle = self.cycles_completed + 1
            await self.event_bus.publish({"type": "cycle_started", "cycle": cycle, "timestamp": datetime.utcnow().isoformat()})
            wallets = self.queue.list_wallets()
            if not wallets:
                await self.event_bus.publish({"type": "cycle_idle", "cycle": cycle, "description": "No wallets in watch queue"})
            for item in wallets:
                if self.stop_requested:
                    break
                wallet = str(item.get("address", "")).lower()
                try:
                    payload = await self._analyze_wallet(wallet)
                    agent_balance = self.service.budget.get_effective_balance_eth(wallet)
                    decision = await self.reasoning.decide(
                        {
                            "cycle": cycle,
                            "address": wallet,
                            "scores": payload["scores"],
                            "agent_balance_eth": f"{agent_balance:.8f}",
                        },
                        event_bus=self.event_bus
                    )
                    flagged = decision["decision"] in {"ALERT", "INTERVENE"}
                    self.queue.update_wallet_state(wallet, last_signal=decision["decision"], increment_flagged=flagged)
                    await self.event_bus.publish({"type": "reasoning", "cycle": cycle, "wallet": wallet, "decision": decision})
                    if decision["decision"] in {"ALERT", "INTERVENE"}:
                        result = await self.executor.execute(decision)
                        await self.event_bus.publish({"type": "execution", "cycle": cycle, "wallet": wallet, "result": result})
                    else:
                        await self.event_bus.publish({"type": "monitor", "cycle": cycle, "wallet": wallet, "decision": decision["decision"]})
                except Exception as exc:
                    await self.event_bus.publish({"type": "wallet_error", "cycle": cycle, "wallet": wallet, "error": str(exc)})
            self.cycles_completed += 1
            await self.event_bus.publish({"type": "cycle_completed", "cycle": cycle, "timestamp": datetime.utcnow().isoformat()})
            if self.stop_requested:
                self.is_running = False
                break
            await asyncio.sleep(self._interval)
        self.is_running = False
        self.stop_requested = False
        await self.event_bus.publish({"type": "loop_stopped", "timestamp": datetime.utcnow().isoformat()})

    async def _analyze_wallet(self, wallet: str) -> Dict[str, Any]:
        now_ts = time.time()
        cache_item = self._cache.get(wallet)
        if cache_item and (now_ts - float(cache_item.get("ts", 0.0))) < self._cache_ttl:
            await self.event_bus.publish({"type": "cache_hit", "wallet": wallet})
            return cache_item["payload"]

        await self.event_bus.publish({"type": "analysis_started", "wallet": wallet})
        raw = await asyncio.to_thread(self.client.obtener_datos_wallet, wallet)
        metrics = await asyncio.to_thread(self.extractor.extraer, raw)
        scores_obj = self.scorer.calcular_scores(metrics)
        payload = {
            "scores": {
                "activity": int(scores_obj.activity_score.value),
                "risk": int(scores_obj.risk_score.value),
                "defi_engagement": int(scores_obj.defi_engagement.value),
                "diversity": int(min(100, max(0, int(getattr(metrics, "porcentaje_interacciones_contratos", 0) or 0)))),
                "exploration": int(min(100, max(0, int(getattr(metrics, "variedad_contratos_unicos", 0) or 0)))),
            }
        }
        self._cache[wallet] = {"ts": now_ts, "payload": payload}
        await self.event_bus.publish({"type": "analysis_completed", "wallet": wallet, "scores": payload["scores"]})
        return payload
