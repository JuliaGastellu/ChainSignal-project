import asyncio
from typing import Any, Dict, List


class AgentEventBus:
    def __init__(self):
        self._subscribers: List[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    async def publish(self, event: Dict[str, Any]) -> None:
        async with self._lock:
            dead: List[asyncio.Queue] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except Exception:
                    dead.append(q)
            if dead:
                self._subscribers = [q for q in self._subscribers if q not in dead]

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        async with self._lock:
            self._subscribers.append(q)
        return q

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        async with self._lock:
            self._subscribers = [q for q in self._subscribers if q is not queue]
