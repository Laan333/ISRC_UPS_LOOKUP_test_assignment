from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from tests.lookup_e2e_transport import build_lookup_e2e_transport


@pytest.fixture
def lookup_e2e_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stable settings for E2E: no in-process cache, no API rate limit noise."""
    monkeypatch.setenv("LOOKUP_CACHE_ENABLED", "false")
    monkeypatch.setenv("API_RATE_LIMIT_PER_MINUTE", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _close_client_sync(client: httpx.AsyncClient) -> None:
    asyncio.run(client.aclose())


def test_lookup_isrc_full_stack(lookup_e2e_env: None, no_musicbrainz_throttle: None) -> None:
    transport = build_lookup_e2e_transport()
    client = httpx.AsyncClient(transport=transport)
    app = create_app(http_client=client)
    try:
        with TestClient(app) as tc:
            r = tc.get("/lookup/isrc/USRC17607839")
    finally:
        _close_client_sync(client)

    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "USRC17607839"
    by_id = {p["provider"]: p for p in body["providers"]}
    assert by_id["musicbrainz"]["found"] is True
    assert by_id["musicbrainz"]["title"] == "Example Track"
    assert by_id["deezer"]["found"] is True
    assert by_id["wikidata"]["found"] is True
    assert by_id["discogs"]["found"] is True
    assert body["summary"]["found_in"] == 4


def test_lookup_upc_full_stack(lookup_e2e_env: None, no_musicbrainz_throttle: None) -> None:
    transport = build_lookup_e2e_transport()
    client = httpx.AsyncClient(transport=transport)
    app = create_app(http_client=client)
    try:
        with TestClient(app) as tc:
            r = tc.get("/lookup/upc/5901234123457")
    finally:
        _close_client_sync(client)

    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "5901234123457"
    by_id = {p["provider"]: p for p in body["providers"]}
    assert by_id["musicbrainz"]["found"] is True
    assert by_id["deezer"]["found"] is True
    assert by_id["discogs"]["found"] is True
    assert by_id["open_library"]["found"] is True
    assert "wikidata" not in by_id
    assert body["summary"]["found_in"] == 4
