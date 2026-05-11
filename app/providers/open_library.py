from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings
from app.normalize import collapse_ws
from app.providers.base import safe_raw_fragment
from app.resilient_http import resilient_get
from app.schemas.lookup import ProviderEntry


class OpenLibraryProvider:
    """Open Library search by identifier (ISBN/barcode in catalog). Mostly books; optional signal for UPC."""

    id = "open_library"

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": self._settings.user_agent, "Accept": "application/json"}

    async def lookup_isrc(self, code: str) -> ProviderEntry:
        _ = code
        return ProviderEntry(
            provider=self.id,
            found=False,
            error="Open Library is not used for ISRC.",
            raw=None,
        )

    async def lookup_upc(self, code: str) -> ProviderEntry:
        params: dict[str, str | int] = {"q": code, "limit": 5}
        try:
            r = await resilient_get(
                self._client,
                self._settings,
                self._settings.open_library_search_url,
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

        num = int(data.get("numFound") or 0)
        docs = data.get("docs") or []
        if num == 0 or not docs:
            return ProviderEntry(
                provider=self.id,
                found=False,
                raw=safe_raw_fragment({"numFound": num}),
            )

        doc = docs[0]
        title = collapse_ws(str(doc.get("title", ""))) or None
        artist = None
        names = doc.get("author_name")
        if isinstance(names, list) and names:
            artist = collapse_ws(str(names[0]))
        elif isinstance(names, str):
            artist = collapse_ws(names)

        label = None
        pub = doc.get("publisher")
        if isinstance(pub, list) and pub:
            label = collapse_ws(str(pub[0]))
        elif isinstance(pub, str):
            label = collapse_ws(pub)

        return ProviderEntry(
            provider=self.id,
            found=bool(title),
            title=title,
            artist=artist,
            album=title,
            label=label,
            raw=safe_raw_fragment(self._compact_doc(doc)),
        )

    @staticmethod
    def _compact_doc(doc: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "title",
            "subtitle",
            "author_name",
            "first_publish_year",
            "publish_year",
            "isbn",
            "publisher",
            "key",
        )
        return {k: doc[k] for k in keys if k in doc}
