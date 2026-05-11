from __future__ import annotations

import asyncio
import time
from typing import Generic, TypeVar

T = TypeVar("T")


class TtlCache(Generic[T]):
    """Process-local TTL cache (single instance). Not shared across replicas."""

    def __init__(self, ttl_s: float, max_entries: int = 512) -> None:
        self._ttl = ttl_s
        self._max = max(1, max_entries)
        self._lock = asyncio.Lock()
        self._store: dict[str, tuple[float, T]] = {}

    def _purge_expired_unlocked(self) -> None:
        now = time.monotonic()
        dead = [k for k, (exp, _) in self._store.items() if exp <= now]
        for k in dead:
            del self._store[k]

    async def get(self, key: str) -> T | None:
        async with self._lock:
            self._purge_expired_unlocked()
            item = self._store.get(key)
            if not item:
                return None
            exp, val = item
            if exp <= time.monotonic():
                del self._store[key]
                return None
            return val

    async def set(self, key: str, value: T) -> None:
        async with self._lock:
            self._purge_expired_unlocked()
            while len(self._store) >= self._max:
                self._store.pop(next(iter(self._store)))
            self._store[key] = (time.monotonic() + self._ttl, value)
