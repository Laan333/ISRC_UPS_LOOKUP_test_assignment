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

        detail, picked, label_name, release_extra = await self._enrich_recording_isrc(mbid, artist)
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
            if "video" in detail:
                raw_payload["video"] = detail.get("video")
            rels = detail.get("releases")
            if isinstance(rels, list):
                raw_payload["releases_linked_count"] = len(rels)
            tags = self._compact_tag_names(detail.get("tags"))
            if tags:
                raw_payload["tags"] = tags
            aliases = self._compact_alias_names(detail.get("aliases"))
            if aliases:
                raw_payload["aliases"] = aliases
            if isinstance(rels, list) and primary_summary:
                pid = primary_summary.get("id")
                sample = self._compact_releases_sample(
                    rels, exclude_id=pid if isinstance(pid, str) else None
                )
                if sample:
                    raw_payload["other_releases_sample"] = sample
        if primary_summary:
            raw_payload["primary_release"] = primary_summary
        if release_extra:
            raw_payload["primary_release_detail"] = release_extra
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
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None, dict[str, Any]]:
        """Fetch recording detail, pick a representative release, labels + tracklist enrichment."""
        await self._respect_rate_limit()
        detail_url = f"{self._settings.musicbrainz_base_url}/recording/{mbid}"
        detail_params: dict[str, str] = {
            "fmt": "json",
            "inc": "artist-credits+releases+release-groups+isrcs+tags+aliases",
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
            return None, None, None, {}

        if not isinstance(detail, dict):
            return None, None, None, {}

        releases = detail.get("releases") or []
        picked = self._pick_display_release(releases, artist_hint)
        label_name: str | None = None
        picked_id = picked.get("id") if isinstance(picked, dict) else None
        release_extra: dict[str, Any] = {}
        if isinstance(picked_id, str) and picked_id:
            label_name, release_extra = await self._fetch_release_enrichment(picked_id)
        return detail, picked, label_name, release_extra

    async def _fetch_release_enrichment(
        self, release_mbid: str
    ) -> tuple[str | None, dict[str, Any]]:
        """Full release with labels + recordings (tracklist). Used for ISRC and UPC."""
        await self._respect_rate_limit()
        url = f"{self._settings.musicbrainz_base_url}/release/{release_mbid}"
        params: dict[str, str] = {
            "fmt": "json",
            "inc": "labels+recordings+artist-credits+release-groups",
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
        except (httpx.HTTPError, Exception):  # noqa: BLE001
            return None, {}

        if not isinstance(data, dict):
            return None, {}

        label_name = self._first_label_name_from_release(data)
        rg = data.get("release-group") if isinstance(data.get("release-group"), dict) else {}
        enrichment: dict[str, Any] = {
            "labels": self._compact_mb_label_infos(data),
            "tracklist": self._tracklist_from_mb_release(data),
            "packaging": data.get("packaging"),
            "disambiguation": data.get("disambiguation"),
            "quality": data.get("quality"),
            "status": data.get("status"),
            "country": data.get("country"),
            "release_group": self._compact_mb_release_group(rg) if rg else None,
        }
        enrichment = {k: v for k, v in enrichment.items() if v not in (None, [], {})}
        return label_name, enrichment

    @staticmethod
    def _first_label_name_from_release(data: dict[str, Any]) -> str | None:
        infos = data.get("label-info") or []
        if not infos or not isinstance(infos[0], dict):
            return None
        label = infos[0].get("label")
        if isinstance(label, dict) and label.get("name"):
            return str(label["name"])
        return None

    @staticmethod
    def _compact_mb_label_infos(data: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for info in (data.get("label-info") or [])[:8]:
            if not isinstance(info, dict):
                continue
            lab = info.get("label")
            name = None
            if isinstance(lab, dict):
                name = lab.get("name")
            cat = info.get("catalog-number")
            if name:
                out.append({"name": str(name), "catalog_number": str(cat) if cat else None})
        return out

    @staticmethod
    def _compact_mb_release_group(rg: dict[str, Any]) -> dict[str, Any]:
        return {
            k: rg[k]
            for k in ("id", "title", "primary-type", "secondary-types", "first-release-date")
            if k in rg and rg[k] not in (None, [])
        }

    @staticmethod
    def _tracklist_from_mb_release(data: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for medium in data.get("media") or []:
            if not isinstance(medium, dict):
                continue
            for tr in medium.get("tracks") or []:
                if not isinstance(tr, dict):
                    continue
                rec = tr.get("recording") if isinstance(tr.get("recording"), dict) else {}
                row: dict[str, Any] = {
                    "position": tr.get("position"),
                    "title": tr.get("title"),
                    "length_ms": tr.get("length"),
                    "recording_id": rec.get("id"),
                }
                out.append({k: v for k, v in row.items() if v is not None})
                if len(out) >= 80:
                    return out
        return out

    @staticmethod
    def _compact_tag_names(tags: Any, *, limit: int = 20) -> list[str]:
        if not isinstance(tags, list):
            return []
        names: list[str] = []
        for t in tags:
            if isinstance(t, dict) and t.get("name"):
                names.append(str(t["name"]))
            if len(names) >= limit:
                break
        return names

    @staticmethod
    def _compact_alias_names(aliases: Any, *, limit: int = 15) -> list[str]:
        if not isinstance(aliases, list):
            return []
        names: list[str] = []
        for a in aliases:
            if isinstance(a, dict) and a.get("name"):
                names.append(str(a["name"]))
            if len(names) >= limit:
                break
        return names

    def _compact_releases_sample(
        self, releases: list[Any], *, exclude_id: str | None, limit: int = 12
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for rel in releases:
            if not isinstance(rel, dict):
                continue
            rid = rel.get("id")
            if exclude_id and rid == exclude_id:
                continue
            rg = rel.get("release-group") if isinstance(rel.get("release-group"), dict) else {}
            row = {
                "id": rid,
                "title": rel.get("title"),
                "date": rel.get("date"),
                "barcode": rel.get("barcode"),
                "country": rel.get("country"),
                "status": rel.get("status"),
                "release_group_title": rg.get("title"),
                "primary_type": rg.get("primary-type"),
            }
            out.append({k: v for k, v in row.items() if v is not None})
            if len(out) >= limit:
                break
        return out

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
        mb_release_extra: dict[str, Any] = {}
        if isinstance(rel_id, str) and rel_id:
            label_name, mb_release_extra = await self._fetch_release_enrichment(rel_id)

        rg = rel.get("release-group") if isinstance(rel.get("release-group"), dict) else {}
        raw_extra: dict[str, Any] = {
            "title": title,
            "date": date,
            "barcode": barcode,
            "status": rel.get("status"),
            "country": rel.get("country"),
            "id": rel_id,
        }
        if rg:
            if rg.get("title"):
                raw_extra["release_group_title"] = rg.get("title")
            if rg.get("primary-type"):
                raw_extra["primary_type"] = rg.get("primary-type")
        rc = data.get("release-count")
        if isinstance(rc, int):
            raw_extra["release_search_total"] = rc
        if mb_release_extra:
            raw_extra["musicbrainz_release"] = mb_release_extra

        return ProviderEntry(
            provider=self.id,
            found=True,
            title=title,
            artist=artist,
            album=collapse_ws(str(rg.get("title") or "")) or None,
            label=collapse_ws(label_name) if label_name else None,
            raw=safe_raw_fragment(raw_extra),
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
