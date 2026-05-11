from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.config import Settings
from app.normalize import collapse_ws
from app.providers.base import safe_raw_fragment
from app.resilient_http import resilient_get
from app.schemas.lookup import ProviderEntry


class MusicBrainzProvider:
    id = "musicbrainz"

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client
        self._lock = asyncio.Lock()
        self._last_request_at = 0.0

    async def _respect_rate_limit(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = 1.05 - (now - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at = time.monotonic()

    def _mb_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._settings.user_agent,
            "Accept": "application/json",
        }

    async def lookup_isrc(self, code: str) -> ProviderEntry:
        await self._respect_rate_limit()
        url = f"{self._settings.musicbrainz_base_url}/recording"
        params: dict[str, str | int] = {"query": f"isrc:{code}", "fmt": "json", "limit": 5}
        try:
            r = await resilient_get(
                self._client,
                self._settings,
                url,
                params=params,
                headers=self._mb_headers(),
            )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            return ProviderEntry(
                provider=self.id,
                found=False,
                error=f"HTTP error: {e!s}",
                raw=None,
            )
        except Exception as e:  # noqa: BLE001
            return ProviderEntry(
                provider=self.id,
                found=False,
                error=str(e),
                raw=None,
            )

        recordings = data.get("recordings") or []
        if not recordings:
            return ProviderEntry(
                provider=self.id,
                found=False,
                raw=safe_raw_fragment({"count": data.get("recording-count", 0)}),
            )

        rec = recordings[0]
        title = collapse_ws(rec.get("title"))
        artist = self._artist_credit(rec.get("artist-credit"))
        return ProviderEntry(
            provider=self.id,
            found=True,
            title=title,
            artist=artist,
            album=None,
            label=None,
            raw=safe_raw_fragment(self._compact_recording(rec)),
        )

    async def lookup_upc(self, code: str) -> ProviderEntry:
        await self._respect_rate_limit()
        url = f"{self._settings.musicbrainz_base_url}/release"
        params: dict[str, str | int] = {
            "query": f"barcode:{code}",
            "fmt": "json",
            "limit": 5,
        }
        try:
            r = await resilient_get(
                self._client,
                self._settings,
                url,
                params=params,
                headers=self._mb_headers(),
            )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            return ProviderEntry(
                provider=self.id,
                found=False,
                error=f"HTTP error: {e!s}",
                raw=None,
            )
        except Exception as e:  # noqa: BLE001
            return ProviderEntry(
                provider=self.id,
                found=False,
                error=str(e),
                raw=None,
            )

        releases = data.get("releases") or []
        if not releases:
            return ProviderEntry(
                provider=self.id,
                found=False,
                raw=safe_raw_fragment({"count": data.get("release-count", 0)}),
            )

        rel = releases[0]
        title = collapse_ws(rel.get("title"))
        artist = self._artist_credit(rel.get("artist-credit"))
        date = rel.get("date")
        barcode = rel.get("barcode")
        return ProviderEntry(
            provider=self.id,
            found=True,
            title=title,
            artist=artist,
            album=None,
            label=None,
            raw=safe_raw_fragment(
                {
                    "title": title,
                    "date": date,
                    "barcode": barcode,
                    "status": rel.get("status"),
                }
            ),
        )

    @staticmethod
    def _artist_credit(credits: Any) -> str | None:
        if not credits:
            return None
        parts: list[str] = []
        for c in credits:
            if isinstance(c, dict) and "artist" in c:
                name = c["artist"].get("name")
                if name:
                    parts.append(name)
            elif isinstance(c, dict) and c.get("name"):
                parts.append(str(c["name"]))
        joined = collapse_ws(" / ".join(parts))
        return joined

    @staticmethod
    def _compact_recording(rec: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": rec.get("id"),
            "title": rec.get("title"),
            "length": rec.get("length"),
            "disambiguation": rec.get("disambiguation"),
        }
