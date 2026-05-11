import asyncio

import pytest

from app.cache import TtlCache


@pytest.mark.asyncio
async def test_ttl_cache_hit_and_miss() -> None:
    c = TtlCache[str](ttl_s=60.0, max_entries=10)
    assert await c.get("x") is None
    await c.set("x", "hello")
    assert await c.get("x") == "hello"


@pytest.mark.asyncio
async def test_ttl_cache_expires() -> None:
    c = TtlCache[str](ttl_s=0.05, max_entries=10)
    await c.set("k", "v")
    assert await c.get("k") == "v"
    await asyncio.sleep(0.08)
    assert await c.get("k") is None


@pytest.mark.asyncio
async def test_ttl_cache_max_entries_eviction() -> None:
    c = TtlCache[int](ttl_s=60.0, max_entries=2)
    await c.set("a", 1)
    await c.set("b", 2)
    await c.set("c", 3)
    assert await c.get("a") is None
