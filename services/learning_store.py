import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List


class LearningStore:
    def __init__(self):
        self.path = Path("storage/learning_store.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"signals": [], "outcomes": []}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("signals", [])
                    data.setdefault("outcomes", [])
                    return data
        except Exception:
            pass
        return {"signals": [], "outcomes": []}

    def _save(self, data: Dict[str, Any]) -> None:
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)

    def record_signal(self, wallet: str, signals: List[Dict[str, Any]], strategy: str) -> None:
        data = self._load()
        data["signals"].append({"timestamp": time.time(), "wallet": wallet, "signals": signals, "strategy": strategy})
        data["signals"] = data["signals"][-500:]
        self._save(data)

    def record_outcome(self, wallet: str, status: str, strategy: str, moved_eth: float, tx_hash: str | None = None) -> None:
        data = self._load()
        data["outcomes"].append(
            {
                "timestamp": time.time(),
                "wallet": wallet,
                "status": status,
                "strategy": strategy,
                "moved_eth": moved_eth,
                "tx_hash": tx_hash,
            }
        )
        data["outcomes"] = data["outcomes"][-500:]
        self._save(data)

    def summary(self) -> Dict[str, Any]:
        data = self._load()
        signals = data.get("signals", [])
        outcomes = data.get("outcomes", [])
        success = [o for o in outcomes if o.get("status") == "success"]
        signal_frequency: Dict[str, int] = {}
        for item in signals[-200:]:
            for signal in item.get("signals", []) or []:
                key = str(signal.get("type", "UNKNOWN"))
                signal_frequency[key] = signal_frequency.get(key, 0) + 1
        strategy_success: Dict[str, int] = {}
        for item in success[-200:]:
            key = str(item.get("strategy", "EXPLORE"))
            strategy_success[key] = strategy_success.get(key, 0) + 1
        return {
            "signals_count": len(signals),
            "outcomes_count": len(outcomes),
            "success_count": len(success),
            "total_moved_eth": round(sum(float(o.get("moved_eth", 0.0) or 0.0) for o in success), 8),
            "latest_signal": signals[-1] if signals else None,
            "latest_outcome": outcomes[-1] if outcomes else None,
            "signal_frequency": signal_frequency,
            "strategy_success": strategy_success,
        }
