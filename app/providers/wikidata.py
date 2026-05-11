from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.normalize import collapse_ws
from app.providers.base import safe_raw_fragment
from app.resilient_http import resilient_get
from app.schemas.lookup import ProviderEntry


class WikidataIsrcProvider:
    """SPARQL lookup for entities with ISRC (P1243). ISRC-only; UPC returns not implemented."""

    id = "wikidata"

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def lookup_isrc(self, code: str) -> ProviderEntry:
        if not code.isalnum():
            return ProviderEntry(
                provider=self.id,
                found=False,
                error="Invalid characters for Wikidata query.",
                raw=None,
            )

        query = f"""
SELECT ?work ?workLabel ?performerLabel WHERE {{
  ?work wdt:P1243 "{code}" .
  OPTIONAL {{ ?work wdt:P175 ?performer . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT 5
""".strip()

        url = f"{self._settings.wikidata_sparql_url}?{urlencode({'query': query, 'format': 'json'})}"
        headers = {
            "User-Agent": self._settings.user_agent,
            "Accept": "application/sparql-results+json",
        }
        try:
            r = await resilient_get(self._client, self._settings, url, headers=headers)
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

        bindings = (data.get("results") or {}).get("bindings") or []
        if not bindings:
            return ProviderEntry(
                provider=self.id,
                found=False,
                raw=safe_raw_fragment({"bindings": 0}),
            )

        b0 = bindings[0]
        title = self._binding_value(b0.get("workLabel")) or self._binding_value(b0.get("work"))
        artist = self._binding_value(b0.get("performerLabel"))
        title = collapse_ws(title) if title else None
        artist = collapse_ws(artist) if artist else None

        return ProviderEntry(
            provider=self.id,
            found=True,
            title=title,
            artist=artist,
            raw=safe_raw_fragment({"entity": self._binding_value(b0.get("work"))}),
        )

    async def lookup_upc(self, code: str) -> ProviderEntry:
        _ = code
        return ProviderEntry(
            provider=self.id,
            found=False,
            error="Wikidata provider is not used for UPC in this build.",
            raw=None,
        )

    @staticmethod
    def _binding_value(cell: dict[str, Any] | None) -> str | None:
        if not cell:
            return None
        return cell.get("value")
