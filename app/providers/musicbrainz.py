from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.config import Settings
from app.normalize import collapse_ws, norm_compare
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
        mbid = rec.get("id")
        if not isinstance(mbid, str) or not mbid:
            return ProviderEntry(
                provider=self.id,
                found=True,
                title=title,
                artist=artist,
                album=None,
                label=None,
                raw=safe_raw_fragment(self._compact_recording(rec)),
            )

        detail, picked, label_name = await self._enrich_recording_isrc(mbid, artist)
        album = None
        primary_summary: dict[str, Any] | None = None
        if picked:
            rg = picked.get("release-group") if isinstance(picked.get("release-group"), dict) else {}
            album = collapse_ws(str(rg.get("title") or picked.get("title") or "")) or None
            primary_summary = {
                "id": picked.get("id"),
                "title": picked.get("title"),
                "date": picked.get("date"),
                "barcode": picked.get("barcode"),
                "country": picked.get("country"),
                "status": picked.get("status"),
                "release_group_title": rg.get("title"),
                "primary_type": rg.get("primary-type"),
            }

        raw_payload = self._compact_recording(rec)
        if isinstance(detail, dict):
            raw_payload["isrcs"] = detail.get("isrcs")
            raw_payload["first_release_date"] = detail.get("first-release-date")
        if primary_summary:
            raw_payload["primary_release"] = primary_summary
        if label_name:
            raw_payload["label_name"] = label_name

        return ProviderEntry(
            provider=self.id,
            found=True,
            title=title,
            artist=artist,
            album=album,
            label=collapse_ws(label_name) if label_name else None,
            raw=safe_raw_fragment(raw_payload),
        )

    async def _enrich_recording_isrc(
        self, mbid: str, artist_hint: str | None
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
        """Fetch recording detail, pick a representative release, optional label lookup."""
        await self._respect_rate_limit()
        detail_url = f"{self._settings.musicbrainz_base_url}/recording/{mbid}"
        detail_params: dict[str, str] = {
            "fmt": "json",
            "inc": "artist-credits+releases+release-groups+isrcs",
        }
        try:
            r = await resilient_get(
                self._client,
                self._settings,
                detail_url,
                params=detail_params,
                headers=self._mb_headers(),
            )
            r.raise_for_status()
            detail = r.json()
        except (httpx.HTTPError, Exception):  # noqa: BLE001
            return None, None, None

        if not isinstance(detail, dict):
            return None, None, None

        releases = detail.get("releases") or []
        picked = self._pick_display_release(releases, artist_hint)
        label_name: str | None = None
        if picked and isinstance(picked.get("id"), str):
            label_name = await self._fetch_release_label_name(picked["id"])
        return detail, picked, label_name

    async def _fetch_release_label_name(self, release_mbid: str) -> str | None:
        await self._respect_rate_limit()
        url = f"{self._settings.musicbrainz_base_url}/release/{release_mbid}"
        params: dict[str, str] = {"fmt": "json", "inc": "labels"}
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
        except (httpx.HTTPError, Exception):  # noqa: BLE001
            return None

        infos = data.get("label-info") or []
        if not infos or not isinstance(infos[0], dict):
            return None
        label = infos[0].get("label")
        if isinstance(label, dict) and label.get("name"):
            return str(label["name"])
        return None

    @staticmethod
    def _release_credit_line(release: dict[str, Any]) -> str:
        parts: list[str] = []
        for c in release.get("artist-credit") or []:
            if isinstance(c, dict) and c.get("name"):
                parts.append(str(c["name"]))
        return " / ".join(parts)

    def _pick_display_release(
        self, releases: list[Any], artist_hint: str | None
    ) -> dict[str, Any] | None:
        if not releases:
            return None

        hint = norm_compare(artist_hint)
        primary_order = {"Single": 0, "EP": 1, "Album": 2, "Broadcast": 3}

        def rank(rel: dict[str, Any]) -> tuple[int, str]:
            rg = rel.get("release-group") if isinstance(rel.get("release-group"), dict) else {}
            pt = str(rg.get("primary-type") or "")
            return (primary_order.get(pt, 9), str(rel.get("date") or "9999-99-99"))

        candidates: list[dict[str, Any]] = []
        for rel in releases:
            if not isinstance(rel, dict):
                continue
            if rel.get("status") != "Official":
                continue
            credit = self._release_credit_line(rel)
            if "Various Artists" in credit:
                continue
            if hint:
                if hint not in norm_compare(credit):
                    continue
            candidates.append(rel)

        if not candidates:
            for rel in releases:
                if not isinstance(rel, dict):
                    continue
                if rel.get("status") != "Official":
                    continue
                credit = self._release_credit_line(rel)
                if "Various Artists" in credit:
                    continue
                candidates.append(rel)

        if not candidates:
            return None

        candidates.sort(key=rank)
        return candidates[0]

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
        label_name: str | None = None
        rel_id = rel.get("id")
        if isinstance(rel_id, str) and rel_id:
            label_name = await self._fetch_release_label_name(rel_id)

        return ProviderEntry(
            provider=self.id,
            found=True,
            title=title,
            artist=artist,
            album=None,
            label=collapse_ws(label_name) if label_name else None,
            raw=safe_raw_fragment(
                {
                    "title": title,
                    "date": date,
                    "barcode": barcode,
                    "status": rel.get("status"),
                    "id": rel_id,
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
