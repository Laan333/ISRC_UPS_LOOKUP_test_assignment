from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings
from app.normalize import collapse_ws
from app.providers.base import safe_raw_fragment
from app.resilient_http import resilient_get
from app.schemas.lookup import ProviderEntry


class DiscogsProvider:
    """
    Discogs Database API (read-only).

    - **ISRC:** ``GET /database/search?q=<isrc>&type=release`` (heuristic; catalog varies).
    - **UPC/EAN:** ``GET /database/search?barcode=<code>&type=release``; if empty, fallback
      ``q=<code>&type=release``. On a hit, optional ``GET /releases/{id}`` enriches label/year/country.
    """

    id = "discogs"

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    def _headers(self) -> dict[str, str]:
        """
        Discogs Auth (see https://www.discogs.com/developers/#page:authentication):

        - ``Authorization: Discogs token=<personal token>`` **or**
        - ``Authorization: Discogs key=<consumer key>, secret=<consumer secret>``

        The «логин/пароль потребителя» in Developer settings **are** the Consumer Key / Secret pair,
        not your discogs.com account password.
        """
        h = {"User-Agent": self._settings.user_agent}
        token = self._settings.discogs_personal_access_token
        if token:
            h["Authorization"] = f"Discogs token={token}"
            return h
        key = self._settings.discogs_consumer_key
        secret = self._settings.discogs_consumer_secret
        if key and secret:
            h["Authorization"] = f"Discogs key={key}, secret={secret}"
        return h

    async def lookup_isrc(self, code: str) -> ProviderEntry:
        url = f"{self._settings.discogs_api_base_url}/database/search"
        params = {"q": code, "type": "release", "per_page": 5}
        return await self._search(url, params, is_barcode_query=False)

    async def lookup_upc(self, code: str) -> ProviderEntry:
        url = f"{self._settings.discogs_api_base_url}/database/search"
        entry = await self._search(
            url,
            {"barcode": code, "type": "release", "per_page": 10},
            is_barcode_query=True,
        )
        if not entry.found:
            entry = await self._search(
                url,
                {"q": code, "type": "release", "per_page": 10},
                is_barcode_query=True,
            )
        if not entry.found:
            return entry
        return await self._attach_release_detail(entry)

    async def _attach_release_detail(self, entry: ProviderEntry) -> ProviderEntry:
        rid = entry.raw.get("id") if entry.raw else None
        if rid is None:
            return entry
        detail_url = f"{self._settings.discogs_api_base_url}/releases/{rid}"
        try:
            r = await resilient_get(
                self._client,
                self._settings,
                detail_url,
                headers=self._headers(),
            )
            r.raise_for_status()
            d = r.json()
        except httpx.HTTPError:
            return entry
        except Exception:  # noqa: BLE001
            return entry

        if not isinstance(d, dict):
            return entry

        title = entry.title or collapse_ws(str(d.get("title") or "")) or None
        artist = entry.artist
        if not artist:
            artists = d.get("artists") or []
            if isinstance(artists, list) and artists and isinstance(artists[0], dict):
                artist = collapse_ws(str(artists[0].get("name") or "")) or None

        label = entry.label
        if not label:
            labels = d.get("labels") or []
            if isinstance(labels, list) and labels and isinstance(labels[0], dict):
                label = collapse_ws(str(labels[0].get("name") or "")) or None

        album = entry.album or title
        found = bool(title or artist or label)

        raw = dict(entry.raw) if entry.raw else {}
        raw["release_detail"] = self._compact_release(d)

        return ProviderEntry(
            provider=self.id,
            found=found,
            title=title,
            artist=artist,
            album=album,
            label=label,
            raw=safe_raw_fragment(raw),
        )

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
            found = bool(title or artist or label)
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
        keys = (
            "id",
            "type",
            "resource_url",
            "title",
            "year",
            "barcode",
            "catno",
            "country",
            "genre",
            "style",
        )
        return {k: item[k] for k in keys if k in item}

    @staticmethod
    def _compact_release(d: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": d.get("id"),
            "title": d.get("title"),
            "released": d.get("released"),
            "year": d.get("year"),
            "country": d.get("country"),
        }
        labels = d.get("labels") or []
        if isinstance(labels, list) and labels and isinstance(labels[0], dict):
            out["labels"] = [
                {"name": x.get("name"), "catno": x.get("catno")} for x in labels[:3] if isinstance(x, dict)
            ]
        artists = d.get("artists") or []
        if isinstance(artists, list) and artists:
            out["artists"] = [
                {"name": x.get("name")} for x in artists[:5] if isinstance(x, dict) and x.get("name")
            ]
        fmts = d.get("formats") or []
        if isinstance(fmts, list) and fmts and isinstance(fmts[0], dict):
            out["formats"] = [
                {"name": x.get("name"), "qty": x.get("qty")} for x in fmts[:5] if isinstance(x, dict)
            ]
        return {k: v for k, v in out.items() if v is not None}
