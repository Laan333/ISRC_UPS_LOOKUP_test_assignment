import httpx
import pytest

from app.config import Settings
from app.providers.musicbrainz import MusicBrainzProvider

from tests.conftest import load_fixture


def _mb_transport_isrc_with_detail(*, detail_fixture: str) -> httpx.MockTransport:
    search = load_fixture("musicbrainz_recording.json")
    detail = load_fixture(detail_fixture)
    labels = load_fixture("musicbrainz_release_labels.json")
    labels_enriched = load_fixture("musicbrainz_release_labels_enriched.json")

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "musicbrainz.org" not in u:
            return httpx.Response(404)
        if "/ws/2/recording/" in u and "query=" not in u:
            return httpx.Response(200, json=detail)
        if "/ws/2/recording" in u and "query=" in u and "isrc" in u.lower():
            return httpx.Response(200, json=search)
        if "/ws/2/release/" in u and "query=" not in u and "inc=labels" in u:
            if "rel-pick-1" in u:
                return httpx.Response(200, json=labels_enriched)
            if "test-rel-id" in u:
                return httpx.Response(200, json=labels)
        if "/ws/2/release" in u and "barcode" in u:
            return httpx.Response(200, json=load_fixture("musicbrainz_release.json"))
        return httpx.Response(404, text=f"unexpected mock path: {u}")

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_musicbrainz_isrc_parses_recording(no_musicbrainz_throttle: None) -> None:
    transport = _mb_transport_isrc_with_detail(detail_fixture="musicbrainz_recording_detail.json")
    settings = Settings()
    async with httpx.AsyncClient(transport=transport) as client:
        p = MusicBrainzProvider(settings, client)
        r = await p.lookup_isrc("USRC17607839")
    assert r.provider == "musicbrainz"
    assert r.found is True
    assert r.title == "Example Track"
    assert r.artist == "Example Artist"
    assert r.album is None
    assert r.label is None
    assert r.raw and r.raw.get("isrcs") == ["USRC17607839"]


@pytest.mark.asyncio
async def test_musicbrainz_isrc_enriched_album_and_label(no_musicbrainz_throttle: None) -> None:
    transport = _mb_transport_isrc_with_detail(detail_fixture="musicbrainz_recording_detail_enriched.json")
    settings = Settings()
    async with httpx.AsyncClient(transport=transport) as client:
        p = MusicBrainzProvider(settings, client)
        r = await p.lookup_isrc("USRC17607839")
    assert r.found is True
    assert r.album == "Example Album RG"
    assert r.label == "Indie Label Co"
    assert r.raw and r.raw.get("primary_release", {}).get("id") == "rel-pick-1"


@pytest.mark.asyncio
async def test_musicbrainz_upc_parses_release(no_musicbrainz_throttle: None) -> None:
    transport = _mb_transport_isrc_with_detail(detail_fixture="musicbrainz_recording_detail.json")
    settings = Settings()
    async with httpx.AsyncClient(transport=transport) as client:
        p = MusicBrainzProvider(settings, client)
        r = await p.lookup_upc("5901234123457")
    assert r.found is True
    assert r.title == "Example Album"
    assert r.artist == "Band Name"
    assert r.label == "Fixture Records"
    assert r.raw and r.raw.get("barcode") == "5901234123457"


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
