from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from scalar_fastapi import AgentScalarConfig, get_scalar_api_reference
from starlette.middleware.cors import CORSMiddleware

from app.api.routes import health, lookup
from app.cache import TtlCache
from app.config import get_settings
from app.exception_handlers import register_exception_handlers
from app.logging_setup import configure_logging
from app.middleware.rate_limit import RateLimitMiddleware, SlidingWindowLimiter
from app.middleware.request_id import RequestIdMiddleware
from app.openapi_meta import APP_OPENAPI_DESCRIPTION, OPENAPI_TAGS_METADATA
from app.outbound import clear_outbound_concurrency_limit, set_outbound_concurrency_limit
from app.providers.deezer import DeezerProvider
from app.providers.discogs import DiscogsProvider
from app.providers.musicbrainz import MusicBrainzProvider
from app.providers.open_library import OpenLibraryProvider
from app.providers.spotify import SpotifyProvider
from app.providers.wikidata import WikidataIsrcProvider
from app.schemas.lookup import LookupResponse
from app.services.lookup_service import LookupService


def make_lifespan(http_client: httpx.AsyncClient | None = None):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = get_settings()
        set_outbound_concurrency_limit(settings.outbound_max_concurrent)
        own_client = http_client is None
        client = http_client or httpx.AsyncClient(
            headers={"User-Agent": settings.user_agent},
            timeout=httpx.Timeout(settings.http_timeout_s),
            follow_redirects=True,
            max_redirects=5,
        )
        try:
            app.state.settings = settings
            app.state.http_client = client
            cache: TtlCache[LookupResponse] | None = None
            if settings.lookup_cache_enabled and settings.lookup_cache_ttl_s > 0:
                cache = TtlCache(
                    settings.lookup_cache_ttl_s,
                    max_entries=settings.lookup_cache_max_entries,
                )
            providers = [
                MusicBrainzProvider(settings, client),
                DeezerProvider(settings, client),
                DiscogsProvider(settings, client),
                WikidataIsrcProvider(settings, client),
                OpenLibraryProvider(settings, client),
            ]
            if settings.provider_spotify_enabled:
                providers.append(SpotifyProvider(settings, client))
            app.state.lookup_service = LookupService(settings, client, providers=providers, cache=cache)
            yield
        finally:
            if own_client:
                await client.aclose()
            clear_outbound_concurrency_limit()

    return lifespan


def create_app(*, http_client: httpx.AsyncClient | None = None) -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    server_url = (settings.openapi_server_url or "").strip()
    servers = (
        [{"url": server_url.rstrip("/"), "description": "Configured host (e.g. docker compose)"}]
        if server_url
        else None
    )
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=APP_OPENAPI_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS_METADATA,
        servers=servers,
        lifespan=make_lifespan(http_client),
        swagger_ui_parameters={
            "tryItOutEnabled": True,
            "persistAuthorization": True,
            "displayRequestDuration": True,
        },
    )

    @app.get("/scalar", include_in_schema=False)
    def scalar_api_reference():
        return get_scalar_api_reference(
            openapi_url=app.openapi_url,
            title=settings.app_name,
            agent=AgentScalarConfig(disabled=True),
        )

    app.add_middleware(RequestIdMiddleware)
    if settings.api_rate_limit_per_minute > 0:
        app.add_middleware(
            RateLimitMiddleware,
            limiter=SlidingWindowLimiter(
                max_requests=settings.api_rate_limit_per_minute,
                window_s=60.0,
            ),
        )
    cors_origins = settings.cors_origins_for_middleware()
    if cors_origins is not None:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(health.router)
    app.include_router(lookup.router)
    register_exception_handlers(app)
    return app


app = create_app()
