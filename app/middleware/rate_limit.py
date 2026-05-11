from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_s: float) -> None:
        self._max = max(1, max_requests)
        self._window = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> bool:
        async with self._lock:
            now = time.monotonic()
            q = self._hits[key]
            while q and now - q[0] > self._window:
                q.popleft()
            if len(q) >= self._max:
                return False
            q.append(now)
            return True


def _skip_rate_limit(path: str) -> bool:
    if path in ("/health", "/ready", "/openapi.json", "/scalar"):
        return True
    if path.startswith("/docs") or path.startswith("/redoc"):
        return True
    return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, limiter: SlidingWindowLimiter) -> None:
        super().__init__(app)
        self._limiter = limiter

    async def dispatch(self, request: Request, call_next) -> Response:
        if _skip_rate_limit(request.url.path):
            return await call_next(request)

        client = request.client
        key = client.host if client else "unknown"
        if not await self._limiter.allow(key):
            return JSONResponse({"detail": "Too many requests"}, status_code=429)
        return await call_next(request)
