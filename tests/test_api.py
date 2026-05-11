from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready() -> None:
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


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
