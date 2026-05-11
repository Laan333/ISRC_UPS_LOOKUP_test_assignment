import httpx
from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings

router = APIRouter(tags=["service"])


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
        "Если задан `READY_CHECK_URL`, выполняется пробный запрос, и при недоступности возвращается 503."
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
        r = await client.get(url, timeout=httpx.Timeout(3.0), follow_redirects=True)
        if r.status_code >= 500:
            raise HTTPException(
                status_code=503,
                detail=f"Ready check failed: {url} ({r.status_code})",
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail=f"Ready check failed: {url}") from None
    finally:
        if own_client:
            await client.aclose()

    return {"status": "ok"}
