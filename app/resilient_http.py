from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import httpx

from app.config import Settings
from app.outbound import outbound_slot

_RETRY_STATUS = {502, 503, 504}


class ResponseBodyTooLarge(httpx.HTTPError):
    """Raised when the response body exceeds ``Settings.max_response_body_bytes``."""

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        super().__init__(f"response body exceeds {max_bytes} bytes")


def _content_length_int(response: httpx.Response) -> int | None:
    raw = response.headers.get("content-length")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def read_response_body_limited(response: httpx.Response, max_bytes: int) -> bytes:
    """Read the full body or raise :class:`ResponseBodyTooLarge`; closes the stream on oversize."""
    cl = _content_length_int(response)
    if cl is not None and cl > max_bytes:
        await response.aclose()
        raise ResponseBodyTooLarge(max_bytes)

    buf = bytearray()
    async for chunk in response.aiter_bytes():
        buf.extend(chunk)
        if len(buf) > max_bytes:
            await response.aclose()
            raise ResponseBodyTooLarge(max_bytes)
    return bytes(buf)


def _materialized_response(original: httpx.Response, body: bytes) -> httpx.Response:
    # `aiter_bytes()` yields decoded (decompressed) content, but original headers may still
    # advertise Content-Encoding: gzip. A new Response with that header would try to
    # decompress again on .json() → zlib "incorrect header check".
    headers = httpx.Headers(original.headers)
    for name in ("content-encoding", "content-length", "transfer-encoding"):
        while name in headers:
            del headers[name]
    return httpx.Response(
        status_code=original.status_code,
        headers=headers,
        content=body,
        request=original.request,
    )


async def resilient_get(
    client: httpx.AsyncClient,
    settings: Settings,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> httpx.Response:
    """GET with optional concurrency slot, retries on timeouts / connect errors / 502–504.

    The returned response has an in-memory body capped by ``max_response_body_bytes``
    (enforced while reading, including before retries on 5xx).
    """
    attempts = max(1, settings.http_get_max_retries + 1)
    backoff = settings.http_get_retry_backoff_s
    max_body = settings.max_response_body_bytes

    for attempt in range(attempts):
        async with outbound_slot():
            try:
                response = await client.get(url, params=params, headers=headers)
            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.RemoteProtocolError,
            ) as e:
                if attempt + 1 >= attempts:
                    raise
                await asyncio.sleep(backoff * (2**attempt))
                continue

        body = await read_response_body_limited(response, max_body)

        if response.status_code in _RETRY_STATUS and attempt + 1 < attempts:
            await asyncio.sleep(backoff * (2**attempt))
            continue

        return _materialized_response(response, body)
