import httpx
import pytest

from app.config import Settings
from app.resilient_http import ResponseBodyTooLarge, resilient_get


@pytest.mark.asyncio
async def test_resilient_get_retries_503() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="bad")
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    settings = Settings(http_get_max_retries=2, http_get_retry_backoff_s=0.01)
    async with httpx.AsyncClient(transport=transport) as client:
        r = await resilient_get(client, settings, "https://example.test/x")
    assert r.status_code == 200
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_resilient_get_no_retry_on_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    settings = Settings(http_get_max_retries=2)
    async with httpx.AsyncClient(transport=transport) as client:
        r = await resilient_get(client, settings, "https://example.test/x")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_resilient_get_timeout_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(200, json={"v": 1})

    transport = httpx.MockTransport(handler)
    settings = Settings(http_get_max_retries=2, http_get_retry_backoff_s=0.01)
    async with httpx.AsyncClient(transport=transport) as client:
        r = await resilient_get(client, settings, "https://example.test/x")
    assert r.status_code == 200
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_resilient_get_rejects_content_length_over_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-length": "999999999"},
            content=b"ignored",
        )

    transport = httpx.MockTransport(handler)
    settings = Settings(max_response_body_bytes=1000)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ResponseBodyTooLarge):
            await resilient_get(client, settings, "https://example.test/x")


@pytest.mark.asyncio
async def test_resilient_get_rejects_stream_over_limit() -> None:
    body = b"x" * 5000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    transport = httpx.MockTransport(handler)
    settings = Settings(max_response_body_bytes=1000)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ResponseBodyTooLarge):
            await resilient_get(client, settings, "https://example.test/x")
