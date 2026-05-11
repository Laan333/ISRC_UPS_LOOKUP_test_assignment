import httpx
from fastapi import APIRouter, HTTPException, Request

from app.config import Settings, get_settings

router = APIRouter(tags=["service"])

_READY_TIMEOUT = httpx.Timeout(3.0)


def _ready_check_failed_http_exc(url: str, suffix: str = "") -> HTTPException:
    detail = f"Ready check failed: {url}{suffix}"
    return HTTPException(status_code=503, detail=detail)


async def _ready_probe_one(
    client: httpx.AsyncClient,
    url: str,
) -> httpx.Response:
    return await client.get(url, timeout=_READY_TIMEOUT, follow_redirects=True)


async def _ready_probe_chain(
    client: httpx.AsyncClient,
    settings: Settings,
    primary: str,
) -> None:
    """Raise HTTPException(503) if neither primary nor optional fallback succeeds."""
    fallback = (settings.ready_check_fallback_url or "").strip()

    try:
        r = await _ready_probe_one(client, primary)
    except httpx.RequestError:
        if not fallback:
            raise _ready_check_failed_http_exc(primary) from None
        try:
            r = await _ready_probe_one(client, fallback)
        except httpx.RequestError:
            raise _ready_check_failed_http_exc(
                primary, f" (fallback also failed: {fallback})"
            ) from None
        if r.status_code >= 500:
            raise _ready_check_failed_http_exc(fallback, f" ({r.status_code})") from None
        return

    if r.status_code < 500:
        return
    if not fallback:
        raise _ready_check_failed_http_exc(primary, f" ({r.status_code})") from None
    try:
        r2 = await _ready_probe_one(client, fallback)
    except httpx.RequestError:
        raise _ready_check_failed_http_exc(
            primary, f" ({r.status_code}; fallback transport failed: {fallback})"
        ) from None
    if r2.status_code >= 500:
        raise _ready_check_failed_http_exc(fallback, f" ({r2.status_code})") from None


@router.get(
    "/health",
    summary="Liveness",
    description="Минимальная проверка процесса; используется Docker healthcheck.",
    response_description="Сервис отвечает.",
)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/ready",
    summary="Readiness",
    description=(
        "Готовность процесса. "
        "Если задан `READY_CHECK_URL`, выполняется пробный GET; при ошибке транспорта или ответе ≥500 "
        "опционально пробуется `READY_CHECK_FALLBACK_URL` (например `http://nginx/health` из контейнера `api`)."
    ),
    response_description="Процесс готов принимать трафик.",
)
async def ready(request: Request) -> dict[str, str]:
    settings = getattr(request.app.state, "settings", None) or get_settings()
    url = (settings.ready_check_url or "").strip()
    if not url:
        return {"status": "ok"}

    client = getattr(request.app.state, "http_client", None)
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(headers={"User-Agent": settings.user_agent})
    try:
        await _ready_probe_chain(client, settings, url)
    finally:
        if own_client:
            await client.aclose()

    return {"status": "ok"}
