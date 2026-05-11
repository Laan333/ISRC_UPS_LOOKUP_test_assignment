from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

_sem: asyncio.Semaphore | None = None


def set_outbound_concurrency_limit(max_concurrent: int) -> None:
    """max_concurrent <= 0 disables limiting."""
    global _sem
    _sem = asyncio.Semaphore(max_concurrent) if max_concurrent > 0 else None


def clear_outbound_concurrency_limit() -> None:
    global _sem
    _sem = None


@asynccontextmanager
async def outbound_slot():
    if _sem is None:
        yield
        return
    await _sem.acquire()
    try:
        yield
    finally:
        _sem.release()
