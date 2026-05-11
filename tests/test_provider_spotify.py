from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.providers.spotify import SpotifyProvider


def _load(name: str) -> dict:
    p = Path(__file__).parent / "fixtures" / name
    return json.loads(p.read_text(encoding="utf-8"))


def _transport() -> httpx.MockTransport:
    token_json = _load("spotify_token.json")
    track_search = _load("spotify_track_search.json")
    album_search = _load("spotify_album_search.json")

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "accounts.spotify.com" in u and "/api/token" in u:
            return httpx.Response(200, json=token_json)
        if "api.spotify.com" in u and "/v1/search" in u:
            if "type=track" in u or "type%3Dtrack" in u:
                return httpx.Response(200, json=track_search)
            if "type=album" in u or "type%3Dalbum" in u:
                return httpx.Response(200, json=album_search)
        return httpx.Response(404, text=f"unmocked: {u}")

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_spotify_lookup_isrc_happy_path() -> None:
    settings = Settings(
        provider_spotify_enabled=True,
        spotify_client_id="id",
        spotify_client_secret="secret",
        spotify_accounts_url="https://accounts.spotify.com",
        spotify_api_base_url="https://api.spotify.com",
    )
    async with httpx.AsyncClient(transport=_transport()) as client:
        p = SpotifyProvider(settings, client)
        entry = await p.lookup_isrc("USRC17607839")

    assert entry.provider == "spotify"
    assert entry.found is True
    assert entry.title == "Spotify Track Title"
    assert entry.artist == "Spotify Artist"
    assert entry.album == "Spotify Album"
    assert entry.label == "Test Label"
    assert entry.raw and entry.raw.get("id") == "trackid1"


@pytest.mark.asyncio
async def test_spotify_lookup_upc_happy_path() -> None:
    settings = Settings(
        provider_spotify_enabled=True,
        spotify_client_id="id",
        spotify_client_secret="secret",
    )
    async with httpx.AsyncClient(transport=_transport()) as client:
        p = SpotifyProvider(settings, client)
        entry = await p.lookup_upc("5901234123457")

    assert entry.found is True
    assert entry.title == "Spotify Release Name"
    assert entry.artist == "Album Artist"
    assert entry.label == "Album Label Co"
    assert entry.album is None


@pytest.mark.asyncio
async def test_spotify_missing_credentials() -> None:
    settings = Settings(provider_spotify_enabled=True, spotify_client_id=None, spotify_client_secret=None)
    async with httpx.AsyncClient(transport=_transport()) as client:
        p = SpotifyProvider(settings, client)
        isrc_entry = await p.lookup_isrc("USRC17607839")
        upc_entry = await p.lookup_upc("5901234123457")

    assert isrc_entry.found is False
    assert isrc_entry.error and "credentials" in isrc_entry.error.lower()
    assert upc_entry.found is False
