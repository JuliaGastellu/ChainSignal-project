import os
import time
from pathlib import Path
from loguru import logger

LOCK_BASE = Path("storage/locks")

class WalletLockManager:
    """Manages file-based locks for individual wallets to prevent concurrent execution."""

    def __init__(self):
        LOCK_BASE.mkdir(parents=True, exist_ok=True)

    def _get_lock_path(self, wallet: str) -> Path:
        return LOCK_BASE / f"{wallet.lower()}.lock"

    def acquire(self, wallet: str, timeout: int = 10) -> bool:
        """
        Attempts to acquire a lock for a wallet.
        Returns True if successful, False otherwise.
        """
        lock_path = self._get_lock_path(wallet)
        
        # Check for stale lock (e.g., > 5 minutes)
        if lock_path.exists():
            if time.time() - lock_path.stat().st_mtime > 300:
                logger.warning(f"Removing stale lock for wallet {wallet}")
                self.release(wallet)

        try:
            # Atomic creation of lock file
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, 'w') as f:
                f.write(str(os.getpid()))
            return True
        except FileExistsError:
            return False
        except Exception as e:
            logger.error(f"Error acquiring lock for {wallet}: {e}")
            return False

    def release(self, wallet: str):
        """Releases the lock for a wallet."""
        lock_path = self._get_lock_path(wallet)
        try:
            if lock_path.exists():
                os.remove(lock_path)
        except Exception as e:
            logger.error(f"Error releasing lock for {wallet}: {e}")

    def is_locked(self, wallet: str) -> bool:
        """Checks if a wallet is currently locked."""
        lock_path = self._get_lock_path(wallet)
        
        # Check for stale lock (e.g., > 60 seconds for is_locked checks)
        if lock_path.exists():
            if time.time() - lock_path.stat().st_mtime > 60:
                logger.warning(f"Removing stale lock for wallet {wallet} (is_locked check)")
                self.release(wallet)
                return False
        
        return lock_path.exists()

    def cleanup_stale_locks(self, stale_age_seconds: int = 60):
        """Clean up all stale locks older than the specified age."""
        if not LOCK_BASE.exists():
            return
            
        stale_count = 0
        for lock_file in LOCK_BASE.glob("*.lock"):
            if time.time() - lock_file.stat().st_mtime > stale_age_seconds:
                try:
                    wallet = lock_file.stem
                    logger.warning(f"Cleaning up stale lock for wallet {wallet}")
                    lock_file.unlink()
                    stale_count += 1
                except Exception as e:
                    logger.error(f"Error cleaning up stale lock {lock_file}: {e}")
        
        if stale_count > 0:
            logger.info(f"Cleaned up {stale_count} stale lock files")
