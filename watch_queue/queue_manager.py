import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class QueueManager:
    def __init__(self, file_path: str = "watched_wallets.json"):
        self.path = Path(file_path)
        self._thread_lock = threading.Lock()
        if not self.path.exists():
            self.path.write_text(json.dumps({"wallets": []}, indent=2), encoding="utf-8")

    @contextmanager
    def _file_lock(self, mode: str):
        with open(self.path, mode, encoding="utf-8") as handle:
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

    def _load(self) -> Dict[str, Any]:
        with self._thread_lock:
            with self._file_lock("r+") as handle:
                handle.seek(0)
                raw = handle.read().strip()
                if not raw:
                    return {"wallets": []}
                data = json.loads(raw)
                if not isinstance(data, dict):
                    return {"wallets": []}
                wallets = data.get("wallets")
                if not isinstance(wallets, list):
                    data["wallets"] = []
                return data

    def _save(self, payload: Dict[str, Any]) -> None:
        with self._thread_lock:
            temp = self.path.with_suffix(".tmp")
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            os.replace(temp, self.path)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def list_wallets(self) -> List[Dict[str, Any]]:
        return self._load().get("wallets", [])

    def add_wallet(self, address: str, label: Optional[str] = None) -> Dict[str, Any]:
        normalized = address.lower()
        payload = self._load()
        wallets = payload.get("wallets", [])
        existing = next((w for w in wallets if str(w.get("address", "")).lower() == normalized), None)
        if existing:
            if label is not None:
                existing["label"] = label
            self._save(payload)
            return existing

        item = {
            "address": normalized,
            "label": label or "",
            "added_at": self._now_iso(),
            "last_analyzed": None,
            "last_signal": None,
            "times_flagged": 0,
        }
        wallets.append(item)
        payload["wallets"] = wallets
        self._save(payload)
        return item

    def remove_wallet(self, address: str) -> bool:
        normalized = address.lower()
        payload = self._load()
        wallets = payload.get("wallets", [])
        next_wallets = [w for w in wallets if str(w.get("address", "")).lower() != normalized]
        changed = len(next_wallets) != len(wallets)
        if changed:
            payload["wallets"] = next_wallets
            self._save(payload)
        return changed

    def update_wallet_state(
        self,
        address: str,
        last_signal: Optional[str] = None,
        increment_flagged: bool = False,
    ) -> Optional[Dict[str, Any]]:
        normalized = address.lower()
        payload = self._load()
        wallets = payload.get("wallets", [])
        target = next((w for w in wallets if str(w.get("address", "")).lower() == normalized), None)
        if not target:
            return None
        target["last_analyzed"] = self._now_iso()
        if last_signal is not None:
            target["last_signal"] = last_signal
        if increment_flagged:
            target["times_flagged"] = int(target.get("times_flagged", 0) or 0) + 1
        self._save(payload)
        return target
