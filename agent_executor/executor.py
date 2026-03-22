import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from domain.modelos_contrato import InsightContrato
from infra.config import settings
from tools.herramienta_compilar_contrato import compilar_contrato_tool
from tools.herramienta_generar_contrato import generar_contrato
from wallet_controller.wallet_agent import WalletAgent

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class AgentExecutor:
    def __init__(self, history_path: str = "executions.json"):
        self.history_path = Path(history_path)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.history_path.exists():
            self.history_path.write_text("[]", encoding="utf-8")
        self.wallet_agent = WalletAgent()

    @contextmanager
    def _file_lock(self, mode: str):
        with open(self.history_path, mode, encoding="utf-8") as handle:
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield handle
            finally:
                if os.name == "nt":
                    handle.flush()
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _load_history(self) -> List[Dict[str, Any]]:
        with self._file_lock("r+") as handle:
            handle.seek(0)
            raw = handle.read().strip()
            if not raw:
                return []
            data = json.loads(raw)
            return data if isinstance(data, list) else []

    def _save_history(self, entries: List[Dict[str, Any]]) -> None:
        temp = self.history_path.with_suffix(".tmp")
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, indent=2)
        os.replace(temp, self.history_path)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _is_duplicate(self, history: List[Dict[str, Any]], wallet: str, cycle: int) -> bool:
        return any(str(h.get("wallet", "")).lower() == wallet.lower() and int(h.get("cycle", -1)) == int(cycle) for h in history)

    def _cooldown_ok(self, history: List[Dict[str, Any]]) -> bool:
        last = next((h for h in reversed(history) if h.get("status") in {"confirmed", "simulated", "failed"}), None)
        if not last:
            return True
        try:
            last_ts = datetime.fromisoformat(str(last["timestamp"]))
        except Exception:
            return True
        return (datetime.now(timezone.utc) - last_ts).total_seconds() >= int(os.getenv("COOLDOWN_SECONDS", str(settings.COOLDOWN_SECONDS)))

    def _append(self, record: Dict[str, Any]) -> Dict[str, Any]:
        history = self._load_history()
        history.append(record)
        self._save_history(history)
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

    def execute(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        wallet = str(decision.get("wallet", "")).lower()
        cycle = int(decision.get("cycle", 0) or 0)
        action = decision.get("action", {}) or {}
        action_type = action.get("type")
        threat_score = float(decision.get("threat_score", 0.0) or 0.0)

        history = self._load_history()
        if self._is_duplicate(history, wallet, cycle):
            return {"status": "skipped", "reason": "duplicate_cycle_wallet"}
        if not self._cooldown_ok(history):
            return {"status": "skipped", "reason": "cooldown_active"}

        if action_type not in {"transfer", "deploy_contract"}:
            return {"status": "no_action"}

        base = {
            "id": str(uuid.uuid4()),
            "timestamp": self._now_iso(),
            "cycle": cycle,
            "wallet": wallet,
            "decision": str(decision.get("decision", "")),
            "threat_score": threat_score,
            "action_type": action_type,
            "tx_hash": None,
            "contract_address": None,
            "status": "failed",
            "error": None,
        }

        try:
            if action_type == "transfer":
                amount_eth = float(action.get("amount_eth", 0.001) or 0.001)
                if not self._post_balance_ok(amount_eth):
                    base["status"] = "failed"
                    base["error"] = "insufficient_post_action_balance"
                    return self._append(base)
                tx_hash = self.wallet_agent.ejecutar_transaccion(wallet, int(amount_eth * (10**18)))
                if tx_hash:
                    base["tx_hash"] = tx_hash
                    base["status"] = "confirmed"
                else:
                    base["status"] = "simulated"
            else:
                if not self._post_balance_ok(0.001):
                    base["status"] = "failed"
                    base["error"] = "insufficient_post_action_balance"
                    return self._append(base)
                insight = InsightContrato(type="risk_guard", analyzed_wallet=wallet, risk_score=max(1, int(threat_score * 100)))
                source = generar_contrato(insight)
                compiled = compilar_contrato_tool(source)
                deploy_result = self.wallet_agent.deploy_contract(compiled.abi, compiled.bytecode, args=None)
                if deploy_result and isinstance(deploy_result, dict):
                    base["tx_hash"] = deploy_result.get("transaction_hash")
                    base["contract_address"] = deploy_result.get("address")
                    method_name = "poke"
                    if compiled.abi:
                        method_candidates = [x.get("name") for x in compiled.abi if x.get("type") == "function" and x.get("stateMutability") != "view"]
                        if method_candidates:
                            method_name = str(method_candidates[0])
                    call_hash = self.wallet_agent.call_contract(base["contract_address"], compiled.abi, method_name, args=[])
                    if call_hash and not base["tx_hash"]:
                        base["tx_hash"] = call_hash
                    base["status"] = "confirmed"
                else:
                    base["status"] = "simulated"
            return self._append(base)
        except Exception as exc:
            base["status"] = "failed"
            base["error"] = str(exc)
            return self._append(base)
