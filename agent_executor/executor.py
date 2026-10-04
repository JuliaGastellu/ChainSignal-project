import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.engine import Engine

from domain.modelos_contrato import InsightContrato
from infra.config import settings
from infra.db import engine as default_engine
from infra.db import get_session_factory, init_db
from infra.db_models import ExecutionRecord
from agent_executor.historial import load_execution_history  # noqa: F401  (compatibilidad)
from infra.modo import exigir_escritura_experimental
from tools.herramienta_compilar_contrato import compilar_contrato_tool
from tools.herramienta_generar_contrato import generar_contrato
from wallet_controller.wallet_agent import WalletAgent


class AgentExecutor:
    """Persisto el historial de ejecución en la base (infra/db.py) en lugar de
    executions.json, para que un reinicio o una caída no lo corrompan. Los
    controles de ciclo duplicado y cooldown consultan la base en vez de cargar
    todo el historial en memoria.

    Todavía no resuelvo locking distribuido, centralización de nonce ni
    reconciliación completa tras una caída. El control de ciclo duplicado
    conserva la lógica anterior, ahora respaldada por una consulta.
    """

    def __init__(self, event_bus: Optional[Any] = None, engine_: Optional[Engine] = None):
        exigir_escritura_experimental("crear_ejecutor")
        self._engine = engine_ or default_engine
        init_db(self._engine)
        self._Session = get_session_factory(self._engine)
        self.wallet_agent = WalletAgent()
        self.event_bus = event_bus

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _is_duplicate(self, wallet: str, cycle: int) -> bool:
        with self._Session() as session:
            exists = (
                session.query(ExecutionRecord.id)
                .filter(ExecutionRecord.wallet == wallet.lower(), ExecutionRecord.cycle == int(cycle))
                .first()
            )
            return exists is not None

    def _cooldown_ok(self) -> bool:
        with self._Session() as session:
            last = (
                session.query(ExecutionRecord)
                .filter(ExecutionRecord.status.in_(["confirmed", "submitted", "simulated", "failed"]))
                .order_by(ExecutionRecord.timestamp.desc())
                .first()
            )
            last_timestamp = last.timestamp if last else None
        if not last_timestamp:
            return True
        try:
            last_ts = datetime.fromisoformat(str(last_timestamp))
        except Exception:
            return True
        return (datetime.now(timezone.utc) - last_ts).total_seconds() >= int(
            settings.COOLDOWN_SECONDS
        )

    def _append(self, record: Dict[str, Any]) -> Dict[str, Any]:
        with self._Session() as session:
            session.add(
                ExecutionRecord(
                    id=record["id"],
                    timestamp=record["timestamp"],
                    cycle=record["cycle"],
                    wallet=record["wallet"],
                    decision=record.get("decision"),
                    threat_score=record.get("threat_score"),
                    action_type=record.get("action_type"),
                    tx_hash=record.get("tx_hash"),
                    contract_address=record.get("contract_address"),
                    status=record["status"],
                    error=record.get("error"),
                )
            )
            session.commit()
        return record

    def _get_agent_balance(self) -> float:
        address = self.wallet_agent.get_address()
        if not address:
            return 0.0
        try:
            return float(self.wallet_agent.get_balance(address))
        except Exception:
            return 0.0

    def _post_balance_ok(self, cost_eth: float) -> bool:
        return (self._get_agent_balance() - cost_eth) >= 0.001

    async def execute(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecuto la acción del experimento testnet y registro su estado.

        Un hash devuelto por el WDK solo significa envío: lo registro como
        `submitted`, nunca como `confirmed`, porque todavía no espero receipt
        (A04). Si el WDK no devuelve hash, el estado es `failed`; nunca convierto
        una falla en éxito simulado.
        """
        exigir_escritura_experimental("ejecutar_decision")
        wallet = str(decision.get("wallet", "")).lower()
        cycle = int(decision.get("cycle", 0) or 0)
        action = decision.get("action", {}) or {}
        action_type = action.get("type")
        threat_score = float(decision.get("threat_score", 0.0) or 0.0)
        decision_str = str(decision.get("decision", ""))

        if self._is_duplicate(wallet, cycle):
            return {"status": "skipped", "reason": "duplicate_cycle_wallet"}
        if not self._cooldown_ok():
            return {"status": "skipped", "reason": "cooldown_active"}

        if action_type not in {"transfer", "deploy_contract"}:
            return {"status": "no_action"}

        # Emit execution_start
        amount_eth = float(action.get("amount_eth", 0.0) or 0.0)
        if action_type == "transfer" and amount_eth == 0:
            amount_eth = 0.001

        if self.event_bus:
            await self.event_bus.publish({
                "type": "execution_start",
                "wallet": wallet,
                "action_type": action_type,
                "amount_eth": amount_eth,
                "decision": decision_str
            })

        base = {
            "id": str(uuid.uuid4()),
            "timestamp": self._now_iso(),
            "cycle": cycle,
            "wallet": wallet,
            "decision": decision_str,
            "threat_score": threat_score,
            "action_type": action_type,
            "tx_hash": None,
            "contract_address": None,
            "status": "failed",
            "error": None,
        }

        try:
            logger.info(f"STARTING execution attempt for {wallet} (Action: {action_type}, Cycle: {cycle})")

            if action_type == "transfer":
                if not self._post_balance_ok(amount_eth):
                    base["status"] = "failed"
                    base["error"] = "insufficient_post_action_balance"
                else:
                    tx_hash = await asyncio.to_thread(self.wallet_agent.ejecutar_transaccion, wallet, int(amount_eth * (10**18)))
                    if tx_hash:
                        base["tx_hash"] = tx_hash
                        base["status"] = "submitted"
                    else:
                        base["status"] = "failed"
                        base["error"] = "wdk_no_tx_hash"
            else:
                # deploy_contract
                cost_estimate = 0.001
                if not self._post_balance_ok(cost_estimate):
                    base["status"] = "failed"
                    base["error"] = "insufficient_post_action_balance"
                else:
                    insight = InsightContrato(type="risk_guard", analyzed_wallet=wallet, risk_score=max(1, int(threat_score * 100)))
                    source = await asyncio.to_thread(generar_contrato, insight)
                    compiled = await asyncio.to_thread(compilar_contrato_tool, source)
                    deploy_result = await asyncio.to_thread(self.wallet_agent.deploy_contract, compiled.abi, compiled.bytecode, args=None)
                    if deploy_result and isinstance(deploy_result, dict):
                        base["tx_hash"] = deploy_result.get("transaction_hash")
                        base["contract_address"] = deploy_result.get("address")
                        method_name = "poke"
                        if compiled.abi:
                            method_candidates = [x.get("name") for x in compiled.abi if x.get("type") == "function" and x.get("stateMutability") != "view"]
                            if method_candidates:
                                method_name = str(method_candidates[0])
                        call_hash = await asyncio.to_thread(self.wallet_agent.call_contract, base["contract_address"], compiled.abi, method_name, args=[])
                        if call_hash and not base["tx_hash"]:
                            base["tx_hash"] = call_hash
                        base["status"] = "submitted"
                    else:
                        base["status"] = "failed"
                        base["error"] = "wdk_deploy_failed"

            logger.info(f"FINISHED execution attempt for {wallet}. Status: {base['status']}")

            # Emit execution events
            if self.event_bus:
                if base["status"] == "submitted":
                    await self.event_bus.publish({
                        "type": "execution_submitted",
                        "wallet": wallet,
                        "tx_hash": base["tx_hash"],
                        "amount_eth": amount_eth,
                        "contract_address": base["contract_address"]
                    })
                else:
                    await self.event_bus.publish({
                        "type": "execution_failed",
                        "wallet": wallet,
                        "error": base["error"] or "Unknown error"
                    })

                # Emit balance update
                new_balance = self._get_agent_balance()
                await self.event_bus.publish({
                    "type": "balance_update",
                    "balance_eth": new_balance
                })

            return self._append(base)
        except Exception as exc:
            logger.error(f"EXCEPTION in execution for {wallet}: {exc}")
            base["status"] = "failed"
            base["error"] = str(exc)

            if self.event_bus:
                await self.event_bus.publish({
                    "type": "execution_failed",
                    "wallet": wallet,
                    "error": str(exc)
                })

            return self._append(base)
