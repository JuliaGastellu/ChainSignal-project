import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from web3 import Web3

from infra.config import settings


class AgentBudgetService:
    def __init__(self):
        self._path = Path("storage/agent_budget.json")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.w3 = Web3(Web3.HTTPProvider(settings.SEPOLIA_RPC_URL)) if settings.SEPOLIA_RPC_URL else None

    def _load(self) -> Dict[str, Any]:
        if not self._path.exists():
            return {"budgets": {}, "processed_txs": {}}
        try:
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "budgets" in data:
                    data.setdefault("processed_txs", {})
                    return data
        except Exception:
            pass
        return {"budgets": {}, "processed_txs": {}}

    def _save(self, data: Dict[str, Any]) -> None:
        tmp = self._path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self._path)

    def get_budget(self, wallet: str) -> Dict[str, Any]:
        key = wallet.lower()
        data = self._load()
        item = data["budgets"].get(
            key,
            {
                "wallet": key,
                "agent_wallet": settings.X402_PAYMENT_RECIPIENT,
                "balance_eth": 0.0,
                "spent_eth": 0.0,
                "created_at": None,
                "updated_at": None,
                "last_funding_tx": None,
                "last_funding_amount_eth": 0.0,
            },
        )
        return item

    def get_effective_balance_eth(self, wallet: str) -> float:
        stored_balance = float(self.get_budget(wallet).get("balance_eth", 0.0))
        if not self.w3 or not self.w3.is_connected():
            return stored_balance
        try:
            onchain_wei = self.w3.eth.get_balance(settings.X402_PAYMENT_RECIPIENT)
            onchain_eth = float(self.w3.from_wei(onchain_wei, "ether"))
            return max(stored_balance, onchain_eth)
        except Exception:
            return stored_balance

    def consume(self, wallet: str, amount_eth: float) -> None:
        if amount_eth <= 0:
            return
        key = wallet.lower()
        data = self._load()
        item = self.get_budget(key)
        item["balance_eth"] = max(0.0, float(item.get("balance_eth", 0.0)) - float(amount_eth))
        item["spent_eth"] = float(item.get("spent_eth", 0.0)) + float(amount_eth)
        item["updated_at"] = time.time()
        data["budgets"][key] = item
        self._save(data)

    def verify_and_fund(self, wallet: str, tx_hash: str) -> Dict[str, Any]:
        if not tx_hash or not tx_hash.startswith("0x"):
            return {"ok": False, "message": "Invalid tx hash format."}
        if not self.w3 or not self.w3.is_connected():
            return {"ok": False, "message": "RPC unavailable for on-chain verification."}

        try:
            data = self._load()
            processed = data.get("processed_txs", {}) or {}
            if tx_hash in processed:
                key = wallet.lower()
                item = self.get_budget(key)
                funded_eth = float(processed[tx_hash].get("funded_eth", 0.0) or 0.0)
                return {"ok": True, "message": "Funding tx already registered.", "budget": item, "funded_eth": funded_eth}

            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            tx = self.w3.eth.get_transaction(tx_hash)
            if not receipt or receipt.get("status") != 1:
                return {"ok": False, "message": "Transaction failed or not found."}
            to_addr = (tx.get("to") or "").lower()
            expected = settings.X402_PAYMENT_RECIPIENT.lower()
            if to_addr != expected:
                return {"ok": False, "message": "Transaction recipient does not match agent wallet."}
            value_wei = int(tx.get("value") or 0)
            if value_wei <= 0:
                return {"ok": False, "message": "Transaction has zero ETH value."}

            funded_eth = float(self.w3.from_wei(value_wei, "ether"))
            key = wallet.lower()
            item = self.get_budget(key)
            item["balance_eth"] = float(item.get("balance_eth", 0.0)) + funded_eth
            item["created_at"] = item.get("created_at") or time.time()
            item["updated_at"] = time.time()
            item["last_funding_tx"] = tx_hash
            item["last_funding_amount_eth"] = funded_eth
            data["budgets"][key] = item
            data["processed_txs"][tx_hash] = {"wallet": key, "funded_eth": funded_eth, "timestamp": time.time()}
            self._save(data)
            return {"ok": True, "message": "Agent budget funded.", "budget": item, "funded_eth": funded_eth}
        except Exception as e:
            return {"ok": False, "message": f"Funding verification error: {e}"}

    def get_recent_funding_events(self, limit: int = 20) -> list[Dict[str, Any]]:
        data = self._load()
        events: list[Dict[str, Any]] = []
        for wallet, item in (data.get("budgets", {}) or {}).items():
            tx_hash = item.get("last_funding_tx")
            updated_at = item.get("updated_at")
            amount = float(item.get("last_funding_amount_eth", 0.0) or 0.0)
            if not tx_hash or not updated_at:
                continue
            events.append(
                {
                    "wallet": wallet,
                    "timestamp": updated_at,
                    "type": "FUNDING",
                    "status": "SUCCESS",
                    "tx_hash": tx_hash,
                    "value_moved_eth": amount,
                    "reason": f"Funding received: +{amount} ETH",
                    "strategy": "FUNDING",
                    "simulated": False,
                    "explorer": f"https://sepolia.etherscan.io/tx/{tx_hash}",
                }
            )
        events_sorted = sorted(events, key=lambda e: float(e.get("timestamp") or 0.0), reverse=True)
        return events_sorted[:limit]

    def get_global_state(self) -> Dict[str, Any]:
        data = self._load()
        budgets = data.get("budgets", {})
        total_balance = 0.0
        total_spent = 0.0
        funded_wallets = 0
        for _, item in budgets.items():
            bal = float(item.get("balance_eth", 0.0))
            spent = float(item.get("spent_eth", 0.0))
            total_balance += bal
            total_spent += spent
            if bal > 0:
                funded_wallets += 1
        return {
            "agent_wallet": settings.X402_PAYMENT_RECIPIENT,
            "funded_wallets": funded_wallets,
            "total_balance_eth": round(total_balance, 8),
            "total_spent_eth": round(total_spent, 8),
        }
