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
        entry = await self._search(f'isrc:"{code}"')
        return await self._attach_track_detail(entry)

    async def lookup_upc(self, code: str) -> ProviderEntry:
        queries = [f'upc:"{code}"']
        if len(code) == 13 and code.startswith("0"):
            queries.append(f'upc:"{code[1:]}"')
        last: ProviderEntry | None = None
        for q in queries:
            last = await self._search(q)
            if last.found:
                return await self._attach_album_detail(last)
        fallback = last or await self._search(queries[0])
        return await self._attach_album_detail(fallback)

    async def _get_entity(self, path: str) -> dict[str, Any] | None:
        base = self._settings.deezer_api_base_url.rstrip("/")
        url = f"{base}/{path.lstrip('/')}"
        try:
            r = await resilient_get(self._client, self._settings, url, headers=self._headers())
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError:
            return None
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(data, dict):
            return None
        if data.get("error"):
            return None
        return data

    async def _attach_track_detail(self, entry: ProviderEntry) -> ProviderEntry:
        if not entry.found or not entry.raw:
            return entry
        tid = entry.raw.get("id")
        if not isinstance(tid, int):
            return entry
        detail = await self._get_entity(f"track/{tid}")
        if not detail:
            return entry
        merged = dict(entry.raw)
        merged["track_detail"] = self._compact_track_detail(detail)
        return ProviderEntry(
            provider=self.id,
            found=entry.found,
            title=entry.title,
            artist=entry.artist,
            album=entry.album,
            label=entry.label,
            error=entry.error,
            raw=safe_raw_fragment(merged),
        )

    async def _attach_album_detail(self, entry: ProviderEntry) -> ProviderEntry:
        if not entry.found or not entry.raw:
            return entry
        alb = entry.raw.get("album")
        aid = None
        if isinstance(alb, dict):
            aid = alb.get("id")
        if not isinstance(aid, int):
            return entry
        detail = await self._get_entity(f"album/{aid}")
        if not detail:
            return entry
        merged = dict(entry.raw)
        merged["album_detail"] = self._compact_album_detail(detail)
        return ProviderEntry(
            provider=self.id,
            found=entry.found,
            title=entry.title,
            artist=entry.artist,
            album=entry.album,
            label=collapse_ws(str(detail.get("label") or "")) or entry.label,
            error=entry.error,
            raw=safe_raw_fragment(merged),
        )

    @staticmethod
    def _compact_track_detail(d: dict[str, Any]) -> dict[str, Any]:
        alb = d.get("album") if isinstance(d.get("album"), dict) else {}
        row: dict[str, Any] = {
            "isrc": d.get("isrc"),
            "bpm": d.get("bpm"),
            "gain": d.get("gain"),
            "track_position": d.get("track_position"),
            "disk_number": d.get("disk_number"),
            "release_date": d.get("release_date") or alb.get("release_date"),
            "explicit_content_lyrics": d.get("explicit_content_lyrics"),
            "readable": d.get("readable"),
        }
        contribs = d.get("contributors")
        if isinstance(contribs, list) and contribs:
            names: list[str] = []
            for c in contribs[:12]:
                if isinstance(c, dict) and c.get("name"):
                    names.append(str(c["name"]))
            if names:
                row["contributors"] = names
        return {k: v for k, v in row.items() if v not in (None, [])}

    @staticmethod
    def _compact_album_detail(d: dict[str, Any]) -> dict[str, Any]:
        genres_block = d.get("genres") or {}
        glist = genres_block.get("data") if isinstance(genres_block, dict) else []
        genre_names: list[str] = []
        if isinstance(glist, list):
            for g in glist[:8]:
                if isinstance(g, dict) and g.get("name"):
                    genre_names.append(str(g["name"]))
        row: dict[str, Any] = {
            "title": d.get("title"),
            "upc": d.get("upc"),
            "label": d.get("label"),
            "nb_tracks": d.get("nb_tracks"),
            "duration": d.get("duration"),
            "release_date": d.get("release_date"),
            "record_type": d.get("record_type"),
            "explicit_lyrics": d.get("explicit_lyrics"),
            "genres": genre_names or None,
        }
        return {k: v for k, v in row.items() if v not in (None, [])}

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

