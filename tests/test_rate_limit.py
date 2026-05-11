import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.rate_limit import RateLimitMiddleware, SlidingWindowLimiter


@pytest.fixture
def limited_app() -> FastAPI:
    app = FastAPI()

    @app.get("/hit")
    def hit() -> dict[str, str]:
        return {"ok": "1"}

    app.add_middleware(
        RateLimitMiddleware,
        limiter=SlidingWindowLimiter(max_requests=3, window_s=60.0),
    )
    return app


def test_rate_limit_blocks_after_burst(limited_app: FastAPI) -> None:
    c = TestClient(limited_app)
    for _ in range(3):
        assert c.get("/hit").status_code == 200
    r = c.get("/hit")
    assert r.status_code == 429
    assert r.json().get("detail")


def test_rate_limit_skips_health_pattern() -> None:
    app = FastAPI()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.add_middleware(
        RateLimitMiddleware,
        limiter=SlidingWindowLimiter(max_requests=2, window_s=60.0),
    )
    c = TestClient(app)
    for _ in range(5):
        assert c.get("/health").status_code == 200
