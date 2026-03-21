import asyncio
import json
from datetime import datetime
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from loguru import logger
from services.agent_service import AgentService

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
