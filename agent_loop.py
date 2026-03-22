import asyncio
import json
from datetime import datetime
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from loguru import logger
from services.agent_service import AgentService
from generacion_features.extractor import ExtractorFeatures
from ingestion_onchain.cliente_etherscan import ClienteEtherscan
from perfil_wallet.behavioral_scoring import BehavioralScorer
from watch_queue.queue_manager import QueueManager
from agent_reasoning.reasoning_engine import ReasoningEngine
from agent_executor.executor import AgentExecutor
from agent_runtime.event_bus import AgentEventBus

TRACKING_FILE = Path("tracking.json")
TRACKING_LOCK = Path("tracking.json.lock")

class AutonomousAgentLoop:
    """
    Continuous background loop that evaluates tracked wallets.
    Uses AgentService for execution logic and respects WalletLockManager.
    """

    def __init__(self, service: AgentService):
        self.service = service
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Starts the autonomous loop."""
        if self.is_running:
            return
        self.is_running = True
        logger.info("Autonomous Agent Loop starting...")
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        """Gracefully stops the loop."""
        self.is_running = False
        if self._task:
            logger.info("Stopping Autonomous Agent Loop...")
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Autonomous Agent Loop stopped.")

    async def _loop(self):
        """Main execution cycle."""
        while self.is_running:
            try:
                wallets = await asyncio.to_thread(self._load_tracking_data)
                if not wallets:
                    logger.debug("No wallets in tracking.json. Sleeping...")
                    await asyncio.sleep(30)
                    continue

                # Priority-based scheduling
                sorted_wallets = self._get_priority_queue(wallets)

                for wallet_addr in sorted_wallets:
                    if not self.is_running:
                        break

                    config = wallets[wallet_addr]
                    if self._should_evaluate(config):
                        locked = await asyncio.to_thread(self.service.lock_manager.is_locked, wallet_addr)
                        if locked:
                            logger.info(f"[LOOP] Skipping wallet {wallet_addr}: locked by another process.")
                            await asyncio.sleep(1)
                            continue

                        logger.info(f"[LOOP] Evaluating wallet {wallet_addr} (Priority: {config['priority']})")
                        
                        # Use AgentService for execution
                        result = await self.service.run_pipeline_loop(wallet_addr)
                        
                        # Update tracking metadata
                        await asyncio.to_thread(self._update_wallet_state, wallet_addr, result)
                        
                        # Adaptive backoff or interval sleep
                        if result.get("status") in {"skipped", "error"}:
                            await asyncio.sleep(5)
                        else:
                            await asyncio.sleep(2)

                # Main cycle sleep
                await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"Error in Autonomous Agent Loop cycle: {e}")
                await asyncio.sleep(30)

    def _load_tracking_data(self) -> Dict[str, Any]:
        """Loads and locks tracking.json safely."""
        if not TRACKING_FILE.exists():
            return {}
        try:
            with self._acquire_tracking_lock():
                with TRACKING_FILE.open("r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading tracking.json: {e}")
            return {}

    def _save_tracking_data(self, data: Dict[str, Any]):
        """Saves updated tracking state."""
        try:
            with self._acquire_tracking_lock():
                tmp_path = TRACKING_FILE.with_suffix(".json.tmp")
                with tmp_path.open("w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
                os.replace(tmp_path, TRACKING_FILE)
        except Exception as e:
            logger.error(f"Error saving tracking.json: {e}")

    def _acquire_tracking_lock(self, retries: int = 10, delay_s: float = 0.1):
        class _LockCtx:
            def __init__(self, outer: "AutonomousAgentLoop"):
                self.outer = outer
                self.acquired = False

            def __enter__(self):
                for _ in range(retries):
                    try:
                        fd = os.open(TRACKING_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                        with os.fdopen(fd, "w", encoding="utf-8") as f:
                            f.write(str(os.getpid()))
                        self.acquired = True
                        return self
                    except FileExistsError:
                        try:
                            if time.time() - TRACKING_LOCK.stat().st_mtime > 30:
                                TRACKING_LOCK.unlink(missing_ok=True)
                        except Exception:
                            pass
                        time.sleep(delay_s)
                raise RuntimeError("Could not acquire tracking.json lock")

            def __exit__(self, exc_type, exc, tb):
                if self.acquired:
                    try:
                        TRACKING_LOCK.unlink(missing_ok=True)
                    except Exception:
                        pass

        return _LockCtx(self)

    def _get_priority_queue(self, wallets: Dict[str, Any]) -> List[str]:
        """Orders wallets by priority: high > medium > low."""
        priority_map = {"high": 0, "medium": 1, "low": 2}
        return sorted(
            wallets.keys(),
            key=lambda w: priority_map.get(wallets[w].get("priority", "low"), 2)
        )

    def _should_evaluate(self, config: Dict[str, Any]) -> bool:
        """Checks if enough time has passed since last evaluation."""
        last_eval = config.get("last_evaluation")
        if not last_eval:
            return True
        
        try:
            last_dt = datetime.fromisoformat(last_eval)
            elapsed = (datetime.now() - last_dt).total_seconds()
            interval = config.get("interval_seconds", 300)
            return elapsed >= interval
        except:
            return True

    def _update_wallet_state(self, wallet_addr: str, result: Dict[str, Any]):
        """Updates last evaluation metrics in tracking.json."""
        wallets = self._load_tracking_data()
        if wallet_addr not in wallets:
            return

        wallets[wallet_addr]["last_evaluation"] = datetime.now().isoformat()
        
        if result.get("status") == "success":
            logger.success(f"[LOOP] Action EXECUTED for {wallet_addr}. Fingerprint: {result.get('fingerprint')}")
        elif result.get("status") == "skipped":
            logger.warning(f"[LOOP] Skipped {wallet_addr}: Wallet locked by API.")
        elif result.get("status") == "no_action":
            logger.info(f"[LOOP] No action needed for {wallet_addr}. Reasoning: {result.get('decision')}")
        elif result.get("status") == "aborted":
            logger.warning(f"[LOOP] ESL Aborted execution for {wallet_addr}: {result.get('reason')}")
        
        # We could also update last_risk_score if the result contained it
        # For now, we just update the timestamp
        self._save_tracking_data(wallets)

if __name__ == "__main__":
    # Test script for the loop
    async def test():
        service = AgentService()
        loop = AutonomousAgentLoop(service)
        await loop.start()
        await asyncio.sleep(60)
        await loop.stop()

    asyncio.run(test())


class GuardianAgentLoop:
    def __init__(self, service: AgentService, event_bus: AgentEventBus):
        self.service = service
        self.event_bus = event_bus
        self.queue = QueueManager()
        self.reasoning = ReasoningEngine()
        self.executor = AgentExecutor(event_bus=self.event_bus)
        self.extractor = ExtractorFeatures()
        self.client = ClienteEtherscan()
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
