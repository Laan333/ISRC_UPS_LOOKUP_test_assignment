import httpx
import pytest

from app.config import Settings
from app.providers.musicbrainz import MusicBrainzProvider

from tests.conftest import load_fixture


def _mb_transport(fixture_name: str, *, kind: str) -> httpx.MockTransport:
    data = load_fixture(fixture_name)

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "musicbrainz.org" not in u:
            return httpx.Response(404)
        if kind == "recording" and "/recording" in u and "isrc" in u:
            return httpx.Response(200, json=data)
        if kind == "release" and "/release" in u and "barcode" in u:
            return httpx.Response(200, json=data)
        return httpx.Response(404, text="unexpected mock path")

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_musicbrainz_isrc_parses_recording(no_musicbrainz_throttle: None) -> None:
    transport = _mb_transport("musicbrainz_recording.json", kind="recording")
    settings = Settings()
    async with httpx.AsyncClient(transport=transport) as client:
        p = MusicBrainzProvider(settings, client)
        r = await p.lookup_isrc("USRC17607839")
    assert r.provider == "musicbrainz"
    assert r.found is True
    assert r.title == "Example Track"
    assert r.artist == "Example Artist"


@pytest.mark.asyncio
async def test_musicbrainz_upc_parses_release(no_musicbrainz_throttle: None) -> None:
    transport = _mb_transport("musicbrainz_release.json", kind="release")
    settings = Settings()
    async with httpx.AsyncClient(transport=transport) as client:
        p = MusicBrainzProvider(settings, client)
        r = await p.lookup_upc("5901234123457")
    assert r.found is True
    assert r.title == "Example Album"
    assert r.artist == "Band Name"


@pytest.mark.asyncio
async def test_musicbrainz_empty_recordings(no_musicbrainz_throttle: None) -> None:
    payload = {"recordings": [], "recording-count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    settings = Settings()
    async with httpx.AsyncClient(transport=transport) as client:
        p = MusicBrainzProvider(settings, client)
        r = await p.lookup_isrc("USRC17607839")
    assert r.found is False
