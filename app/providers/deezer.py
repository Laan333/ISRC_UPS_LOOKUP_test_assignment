from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings
from app.normalize import collapse_ws
from app.providers.base import safe_raw_fragment
from app.resilient_http import resilient_get
from app.schemas.lookup import ProviderEntry


class DeezerProvider:
    """
    Deezer public search API (no token required for basic queries).

    Supports:
    - ISRC: q=isrc:"<code>"
    - UPC/EAN: ``q=upc:"<code>"``; for 13-digit EAN with a leading ``0``, also tries the 12-digit UPC-A form.
    """

    id = "deezer"

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": self._settings.user_agent, "Accept": "application/json"}

    async def lookup_isrc(self, code: str) -> ProviderEntry:
        return await self._search(f'isrc:"{code}"')

    async def lookup_upc(self, code: str) -> ProviderEntry:
        queries = [f'upc:"{code}"']
        if len(code) == 13 and code.startswith("0"):
            queries.append(f'upc:"{code[1:]}"')
        last: ProviderEntry | None = None
        for q in queries:
            last = await self._search(q)
            if last.found:
                return last
        return last or await self._search(queries[0])

    async def lookup_free_text(self, query: str) -> ProviderEntry:
        """Plain Deezer search ``q=…`` (track-oriented results; used as a fallback when ISRC/UPC miss)."""
        q = collapse_ws(query) or ""
        if not q:
            return ProviderEntry(provider=self.id, found=False, raw=None)
        return await self._search(q)

    async def _search(self, query: str) -> ProviderEntry:
        url = f"{self._settings.deezer_api_base_url}/search"
        params = {"q": query, "limit": 5}
        try:
            r = await resilient_get(
                self._client,
                self._settings,
                url,
                params=params,
                headers=self._headers(),
            )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            return ProviderEntry(provider=self.id, found=False, error=f"HTTP error: {e!s}", raw=None)
        except Exception as e:  # noqa: BLE001
            return ProviderEntry(provider=self.id, found=False, error=str(e), raw=None)

        items = data.get("data") or []
        if not items:
            total = data.get("total")
            return ProviderEntry(provider=self.id, found=False, raw=safe_raw_fragment({"total": total}))

        first = items[0]
        title = collapse_ws(self._get_str(first, "title"))
        artist = collapse_ws(self._get_str((first.get("artist") or {}), "name"))
        album = collapse_ws(self._get_str((first.get("album") or {}), "title"))

        raw = safe_raw_fragment(
            {
                "id": first.get("id"),
                "link": first.get("link"),
                "duration": first.get("duration"),
                "rank": first.get("rank"),
                "explicit_lyrics": first.get("explicit_lyrics"),
                "artist": {"id": (first.get("artist") or {}).get("id"), "name": artist},
                "album": {"id": (first.get("album") or {}).get("id"), "title": album},
            }
        )

        return ProviderEntry(
            provider=self.id,
            found=bool(title),
            title=title,
            artist=artist,
            album=album,
            label=None,
            raw=raw,
        )

    @staticmethod
    def _get_str(obj: Any, key: str) -> str | None:
        if not isinstance(obj, dict):
            return None
        v = obj.get(key)
        if v is None:
            return None
        return str(v)

