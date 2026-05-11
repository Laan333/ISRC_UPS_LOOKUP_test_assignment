from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.providers.discogs import DiscogsProvider


@pytest.mark.asyncio
async def test_discogs_consumer_auth_uses_discogs_auth_header() -> None:
    auths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        auths.append(request.headers.get("authorization") or "")
        if "database/search" in str(request.url):
            return httpx.Response(200, json={"results": []})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    settings = Settings(
        discogs_consumer_key="mykey",
        discogs_consumer_secret="mysecret",
        discogs_personal_access_token=None,
    )
    async with httpx.AsyncClient(transport=transport) as client:
        p = DiscogsProvider(settings, client)
        await p.lookup_upc("5900000000000")

    assert any(a.startswith("Discogs key=mykey, secret=mysecret") for a in auths)


@pytest.mark.asyncio
async def test_discogs_upc_barcode_then_release_detail() -> None:
    detail = {
        "id": 9,
        "title": "Full Title",
        "year": 2020,
        "artists": [{"name": "Band"}],
        "labels": [{"name": "Nice Label", "catno": "NL-1"}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "database/search" in u and "barcode=" in u:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 9,
                            "title": "Full Title",
                            "artist": "Band",
                            "type": "release",
                            "barcode": "5901234123457",
                            "year": "2020",
                        }
                    ]
                },
            )
        if "/releases/9" in u:
            return httpx.Response(200, json=detail)
        return httpx.Response(404, text=u)

    transport = httpx.MockTransport(handler)
    settings = Settings()
    async with httpx.AsyncClient(transport=transport) as client:
        p = DiscogsProvider(settings, client)
        r = await p.lookup_upc("5901234123457")

    assert r.found is True
    assert r.title == "Full Title"
    assert r.artist == "Band"
    assert r.label == "Nice Label"
    assert r.raw and r.raw.get("release_detail", {}).get("labels")


@pytest.mark.asyncio
async def test_discogs_upc_fallback_when_barcode_empty() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        calls.append(u)
        if "database/search" in u and "barcode=" in u:
            return httpx.Response(200, json={"results": []})
        if "database/search" in u and "barcode=" not in u and "5901234123457" in u:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 88,
                            "title": "Fallback Hit",
                            "artist": "Someone",
                            "type": "release",
                        }
                    ]
                },
            )
        if "/releases/88" in u:
            return httpx.Response(200, json={"id": 88, "title": "Fallback Hit"})
        return httpx.Response(404, text=u)

    transport = httpx.MockTransport(handler)
    settings = Settings()
    async with httpx.AsyncClient(transport=transport) as client:
        p = DiscogsProvider(settings, client)
        r = await p.lookup_upc("5901234123457")

    assert r.found is True
    assert r.title == "Fallback Hit"
    assert any("barcode=" in c for c in calls)
    assert any("q=" in c and "5901234123457" in c for c in calls)
