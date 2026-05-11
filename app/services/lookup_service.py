from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Iterable

import httpx

from app.cache import TtlCache
from app.config import Settings
from app.normalize import collapse_ws
from app.providers.base import MetadataProvider
from app.schemas.lookup import LookupResponse, ProviderEntry
from app.summary import build_summary

logger = logging.getLogger(__name__)


class LookupService:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient,
        *,
        providers: Iterable[MetadataProvider] | None = None,
        cache: TtlCache[LookupResponse] | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._cache = cache
        self._providers: dict[str, MetadataProvider] = {p.id: p for p in (providers or [])}

    async def lookup_isrc(self, code: str, request_id: str | None) -> LookupResponse:
        cache_key = f"isrc:{code}"
        if self._cache is not None:
            hit = await self._cache.get(cache_key)
            if hit is not None:
                logger.info("cache hit request_id=%s key=%s", request_id, cache_key)
                return hit

        tasks: list[asyncio.Task[ProviderEntry]] = []
        if self._settings.provider_musicbrainz_enabled and "musicbrainz" in self._providers:
            tasks.append(
                asyncio.create_task(
                    self._safe_call("musicbrainz", self._providers["musicbrainz"].lookup_isrc(code))
                )
            )
        if self._settings.provider_deezer_enabled and "deezer" in self._providers:
            tasks.append(
                asyncio.create_task(
                    self._safe_call("deezer", self._providers["deezer"].lookup_isrc(code))
                )
            )
        if self._settings.provider_discogs_enabled and "discogs" in self._providers:
            tasks.append(
                asyncio.create_task(
                    self._safe_call("discogs", self._providers["discogs"].lookup_isrc(code))
                )
            )
        if self._settings.provider_wikidata_enabled and "wikidata" in self._providers:
            tasks.append(
                asyncio.create_task(
                    self._safe_call("wikidata", self._providers["wikidata"].lookup_isrc(code))
                )
            )

        providers = await self._gather(tasks, request_id, code)
        providers = await self._refine_by_title_hint(providers, request_id=request_id, code=code)
        providers = self._omit_providers_with_only_error(providers)
        summary = build_summary(providers)
        out = LookupResponse(query=code, providers=providers, summary=summary)
        if self._cache is not None:
            await self._cache.set(cache_key, out)
        return out

    async def lookup_upc(self, code: str, request_id: str | None) -> LookupResponse:
        cache_key = f"upc:{code}"
        if self._cache is not None:
            hit = await self._cache.get(cache_key)
            if hit is not None:
                logger.info("cache hit request_id=%s key=%s", request_id, cache_key)
                return hit

        tasks: list[asyncio.Task[ProviderEntry]] = []
        if self._settings.provider_musicbrainz_enabled and "musicbrainz" in self._providers:
            tasks.append(
                asyncio.create_task(
                    self._safe_call("musicbrainz", self._providers["musicbrainz"].lookup_upc(code))
                )
            )
        if self._settings.provider_deezer_enabled and "deezer" in self._providers:
            tasks.append(
                asyncio.create_task(
                    self._safe_call("deezer", self._providers["deezer"].lookup_upc(code))
                )
            )
        if self._settings.provider_discogs_enabled and "discogs" in self._providers:
            tasks.append(
                asyncio.create_task(
                    self._safe_call("discogs", self._providers["discogs"].lookup_upc(code))
                )
            )
        if self._settings.provider_open_library_enabled and "open_library" in self._providers:
            tasks.append(
                asyncio.create_task(
                    self._safe_call(
                        "open_library", self._providers["open_library"].lookup_upc(code)
                    )
                )
            )

        providers = await self._gather(tasks, request_id, code)
        providers = await self._refine_by_title_hint(providers, request_id=request_id, code=code)
        providers = self._omit_providers_with_only_error(providers)
        summary = build_summary(providers)
        out = LookupResponse(query=code, providers=providers, summary=summary)
        if self._cache is not None:
            await self._cache.set(cache_key, out)
        return out

    @staticmethod
    def _omit_providers_with_only_error(providers: list[ProviderEntry]) -> list[ProviderEntry]:
        """Drop providers that failed with an exception/HTTP message (``found`` + ``error``)."""
        out: list[ProviderEntry] = []
        for p in providers:
            if p.found is False and p.error:
                continue
            out.append(p)
        return out

    @staticmethod
    def _hint_title_artist(providers: list[ProviderEntry]) -> tuple[str | None, str | None]:
        priority = (
            "musicbrainz",
            "deezer",
            "discogs",
            "open_library",
            "wikidata",
        )
        by_id = {p.provider: p for p in providers}
        for pid in priority:
            p = by_id.get(pid)
            if p and p.found and (p.title or p.album):
                title = collapse_ws(str(p.title or p.album or "")) or None
                artist = collapse_ws(p.artist) if p.artist else None
                if title:
                    return title, artist
        for p in providers:
            if p.found and (p.title or p.album):
                title = collapse_ws(str(p.title or p.album or "")) or None
                if title:
                    return title, collapse_ws(p.artist) if p.artist else None
        return None, None

    @staticmethod
    def _deezer_discogs_hint_query(title: str, artist: str | None) -> str:
        if artist:
            return f"{artist} {title}"
        return title

    async def _refine_by_title_hint(
        self,
        providers: list[ProviderEntry],
        *,
        request_id: str | None,
        code: str,
    ) -> list[ProviderEntry]:
        title, artist = self._hint_title_artist(providers)
        if not title:
            return providers

        q = self._deezer_discogs_hint_query(title, artist)
        by_idx = {p.provider: i for i, p in enumerate(providers)}
        refinements: list[tuple[str, Awaitable[ProviderEntry]]] = []

        if self._settings.provider_deezer_enabled and "deezer" in self._providers:
            i = by_idx.get("deezer")
            if i is not None and not providers[i].found:
                fn = getattr(self._providers["deezer"], "lookup_free_text", None)
                if callable(fn):
                    refinements.append(("deezer", fn(q)))

        if self._settings.provider_discogs_enabled and "discogs" in self._providers:
            i = by_idx.get("discogs")
            if i is not None and not providers[i].found:
                fn = getattr(self._providers["discogs"], "lookup_release_free_text", None)
                if callable(fn):
                    refinements.append(("discogs", fn(q)))

        if not refinements:
            return providers

        merged = list(providers)
        for pid, coro in refinements:
            entry = await self._safe_call(pid, coro)
            idx = by_idx[pid]
            if entry.found and not merged[idx].found:
                merged[idx] = entry
                logger.info(
                    "refined provider=%s from title hint request_id=%s code=%s",
                    pid,
                    request_id,
                    code,
                )
        return merged

    async def _safe_call(self, provider_id: str, coro: Awaitable[ProviderEntry]) -> ProviderEntry:
        try:
            entry = await coro
        except Exception as e:  # noqa: BLE001
            return ProviderEntry(provider=provider_id, found=False, error=str(e), raw=None)

        if not entry.provider:
            return ProviderEntry(
                provider=provider_id,
                found=entry.found,
                title=entry.title,
                artist=entry.artist,
                album=entry.album,
                label=entry.label,
                error=entry.error,
                raw=entry.raw,
            )
        return entry

    async def _gather(
        self,
        tasks: list[asyncio.Task[ProviderEntry]],
        request_id: str | None,
        code: str,
    ) -> list[ProviderEntry]:
        if not tasks:
            logger.warning("No providers enabled request_id=%s code=%s", request_id, code)
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        out: list[ProviderEntry] = []
        for r in results:
            if isinstance(r, ProviderEntry):
                out.append(r)
            elif isinstance(r, BaseException):
                logger.error(
                    "Provider task failed request_id=%s code=%s",
                    request_id,
                    code,
                    exc_info=r,
                )
                out.append(ProviderEntry(provider="unknown", found=False, error=str(r), raw=None))
            else:
                out.append(
                    ProviderEntry(
                        provider="unknown",
                        found=False,
                        error="unexpected task result",
                        raw=None,
                    )
                )
        return out
