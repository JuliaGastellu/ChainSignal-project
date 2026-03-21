import os
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from .models import ExecutionPlan

STORAGE_BASE = Path("storage/plans")

class PersistenceManager:
    """Manages the lifecycle of execution plans on disk."""

    @staticmethod
    def _get_plan_dir(fingerprint: str) -> Path:
        return STORAGE_BASE / fingerprint

    @staticmethod
    def _get_plan_path(fingerprint: str) -> Path:
        return PersistenceManager._get_plan_dir(fingerprint) / "plan.json"

    @staticmethod
    def _get_lock_path(fingerprint: str) -> Path:
        return PersistenceManager._get_plan_dir(fingerprint) / "lock"

    @staticmethod
    def _get_journal_path(fingerprint: str) -> Path:
        return PersistenceManager._get_plan_dir(fingerprint) / "journal.log"

    def save_plan(self, plan: ExecutionPlan):
        """Atomically saves a plan to disk."""
        plan_dir = self._get_plan_dir(plan.fingerprint)
        plan_dir.mkdir(parents=True, exist_ok=True)
        
        plan_path = self._get_plan_path(plan.fingerprint)
        temp_path = plan_path.with_suffix(".tmp")
        
        with open(temp_path, "w") as f:
            json.dump(plan.to_dict(), f, indent=2)
        
        # Atomic rename (on Windows this might need os.replace)
        os.replace(temp_path, plan_path)

    def load_plan(self, fingerprint: str) -> Optional[ExecutionPlan]:
        """Loads a plan from disk."""
        plan_path = self._get_plan_path(fingerprint)
        if not plan_path.exists():
            return None
        
        with open(plan_path, "r") as f:
            data = json.load(f)
        return ExecutionPlan.from_dict(data)

    def log_event(self, fingerprint: str, event: str, data: Optional[Dict[str, Any]] = None):
        """Appends an event to the journal log."""
        journal_path = self._get_journal_path(fingerprint)
        entry = {
            "timestamp": time.time(),
            "event": event,
            "data": data or {}
        }
        with open(journal_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def acquire_lock(self, fingerprint: str, retries: int = 5, delay: float = 0.5) -> bool:
        """Attempts to acquire a file lock for the plan."""
        lock_path = self._get_lock_path(fingerprint)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        
        for i in range(retries):
            try:
                # Exclusive creation of lock file
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return True
            except FileExistsError:
                # Check if lock is stale (e.g., > 10 mins)
                try:
                    if time.time() - os.path.getmtime(lock_path) > 600:
                        os.remove(lock_path)
                        continue
                except FileNotFoundError:
                    pass
                time.sleep(delay)
        return False

    def release_lock(self, fingerprint: str):
        """Releases the file lock."""
        lock_path = self._get_lock_path(fingerprint)
        try:
            os.remove(lock_path)
        except FileNotFoundError:
            pass

    def get_all_plans(self) -> List[ExecutionPlan]:
        """Lists all plans stored on disk."""
        plans = []
        if not STORAGE_BASE.exists():
            return []
        for fingerprint_dir in STORAGE_BASE.iterdir():
            if fingerprint_dir.is_dir():
                plan = self.load_plan(fingerprint_dir.name)
                if plan:
                    plans.append(plan)
        return plans
