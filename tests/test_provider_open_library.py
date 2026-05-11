import httpx
import pytest

from app.config import Settings
from app.providers.open_library import OpenLibraryProvider

from tests.conftest import load_fixture


@pytest.mark.asyncio
async def test_open_library_upc_found() -> None:
    data = load_fixture("open_library_search.json")

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "openlibrary.org" in u and "search.json" in u:
            return httpx.Response(200, json=data)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    settings = Settings()
    async with httpx.AsyncClient(transport=transport) as client:
        p = OpenLibraryProvider(settings, client)
        r = await p.lookup_upc("9780000000002")
    assert r.provider == "open_library"
    assert r.found is True
    assert r.title == "Sample Book Title"
    assert r.artist == "Jane Author"


@pytest.mark.asyncio
async def test_open_library_isrc_disabled() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(500))
    settings = Settings()
    async with httpx.AsyncClient(transport=transport) as client:
        p = OpenLibraryProvider(settings, client)
        r = await p.lookup_isrc("USRC17607839")
    assert r.found is False
    assert r.error and "not used" in r.error.lower()
