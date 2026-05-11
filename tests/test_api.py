import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app, create_app

client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready() -> None:
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_fallback_when_primary_transport_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("READY_CHECK_URL", "http://primary.invalid/health")
    monkeypatch.setenv("READY_CHECK_FALLBACK_URL", "http://fallback.ok/health")
    get_settings.cache_clear()
    try:

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "primary.invalid":
                raise httpx.ConnectError("simulated")
            if request.url.host == "fallback.ok":
                return httpx.Response(200, json={"status": "ok"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        app_fb = create_app(http_client=httpx.AsyncClient(transport=transport))
        with TestClient(app_fb) as tc:
            r = tc.get("/ready")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
    finally:
        monkeypatch.delenv("READY_CHECK_URL", raising=False)
        monkeypatch.delenv("READY_CHECK_FALLBACK_URL", raising=False)
        get_settings.cache_clear()


def test_ready_fallback_when_primary_returns_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("READY_CHECK_URL", "http://primary.bad/health")
    monkeypatch.setenv("READY_CHECK_FALLBACK_URL", "http://fallback.ok/health")
    get_settings.cache_clear()
    try:

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "primary.bad":
                return httpx.Response(502)
            if request.url.host == "fallback.ok":
                return httpx.Response(200, json={"status": "ok"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        app_fb = create_app(http_client=httpx.AsyncClient(transport=transport))
        with TestClient(app_fb) as tc:
            r = tc.get("/ready")
        assert r.status_code == 200
    finally:
        monkeypatch.delenv("READY_CHECK_URL", raising=False)
        monkeypatch.delenv("READY_CHECK_FALLBACK_URL", raising=False)
        get_settings.cache_clear()


def test_isrc_422() -> None:
    r = client.get("/lookup/isrc/bad")
    assert r.status_code == 422


def test_upc_422_bad_check_digit() -> None:
    r = client.get("/lookup/upc/5901234123450")
    assert r.status_code == 422


def test_request_id_header() -> None:
    r = client.get("/health")
    assert "x-request-id" in {k.lower(): v for k, v in r.headers.items()}


def test_scalar_reference_page() -> None:
    r = client.get("/scalar")
    assert r.status_code == 200
    text = r.text.lower()
    assert "openapi.json" in text or "scalar" in text


def test_cors_reflects_wildcard() -> None:
    r = client.get("/health", headers={"Origin": "http://example.com"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "*"
