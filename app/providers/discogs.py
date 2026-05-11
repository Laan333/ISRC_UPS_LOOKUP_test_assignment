from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings
from app.normalize import collapse_ws
from app.providers.base import safe_raw_fragment
from app.resilient_http import resilient_get
from app.schemas.lookup import ProviderEntry


class DiscogsProvider:
    id = "discogs"

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    def _headers(self) -> dict[str, str]:
        h = {"User-Agent": self._settings.user_agent}
        token = self._settings.discogs_personal_access_token
        if token:
            h["Authorization"] = f"Discogs token={token}"
        return h

    async def lookup_isrc(self, code: str) -> ProviderEntry:
        url = f"{self._settings.discogs_api_base_url}/database/search"
        params = {"q": code, "type": "release", "per_page": 5}
        return await self._search(url, params, is_barcode_query=False)

    async def lookup_upc(self, code: str) -> ProviderEntry:
        url = f"{self._settings.discogs_api_base_url}/database/search"
        params = {"barcode": code, "type": "release", "per_page": 5}
        return await self._search(url, params, is_barcode_query=True)

    async def _search(
        self,
        url: str,
        params: dict[str, str | int],
        *,
        is_barcode_query: bool,
    ) -> ProviderEntry:
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

        results = data.get("results") or []
        if not results:
            return ProviderEntry(
                provider=self.id,
                found=False,
                raw=safe_raw_fragment({"result_count": 0}),
            )

        best = results[0]
        title = collapse_ws(str(best.get("title", ""))) or None
        label = None
        labels = best.get("label")
        if isinstance(labels, list) and labels:
            label = collapse_ws(str(labels[0]))
        elif isinstance(labels, str):
            label = collapse_ws(labels)

        artist = None
        for key in ("artist", "anv"):
            v = best.get(key)
            if v:
                artist = collapse_ws(str(v))
                break

        if is_barcode_query:
            found = True
        else:
            found = bool(title)

        return ProviderEntry(
            provider=self.id,
            found=found,
            title=title,
            artist=artist,
            album=title,
            label=label,
            raw=safe_raw_fragment(self._compact_result(best)),
        )

    @staticmethod
    def _compact_result(item: dict[str, Any]) -> dict[str, Any]:
        return {
            k: item.get(k)
            for k in ("title", "year", "type", "barcode", "catno", "country", "genre", "style")
            if k in item
        }
