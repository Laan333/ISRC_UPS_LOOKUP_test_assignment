from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any

import httpx

from app.config import Settings
from app.normalize import collapse_ws
from app.outbound import outbound_slot
from app.providers.base import safe_raw_fragment
from app.resilient_http import read_response_body_limited, resilient_get
from app.schemas.lookup import ProviderEntry

logger = logging.getLogger(__name__)


class SpotifyProvider:
    """
    Spotify Web API (Client Credentials).

    - ISRC: ``GET /v1/search?q=isrc:<code>&type=track``
    - UPC/EAN: ``GET /v1/search?q=upc:<code>&type=album``

    Requires ``SPOTIFY_CLIENT_ID`` and ``SPOTIFY_CLIENT_SECRET`` (server-side only).
    """

    id = "spotify"

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client
        self._token_lock = asyncio.Lock()
        self._access_token: str | None = None
        self._token_expires_monotonic: float = 0.0

    def _configured(self) -> bool:
        return bool(self._settings.spotify_client_id and self._settings.spotify_client_secret)

    async def _get_bearer_token(self) -> str | None:
        if not self._configured():
            return None

        async with self._token_lock:
            margin = 60.0
            if self._access_token and time.monotonic() < self._token_expires_monotonic - margin:
                return self._access_token

            cid = self._settings.spotify_client_id or ""
            sec = self._settings.spotify_client_secret or ""
            basic = base64.b64encode(f"{cid}:{sec}".encode()).decode("ascii")
            url = f"{self._settings.spotify_accounts_url.rstrip('/')}/api/token"
            headers = {
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            try:
                async with outbound_slot():
                    resp = await self._client.post(
                        url,
                        headers=headers,
                        data={"grant_type": "client_credentials"},
                    )
                body = await read_response_body_limited(
                    resp, min(64_000, self._settings.max_response_body_bytes)
                )
                resp = httpx.Response(status_code=resp.status_code, content=body, request=resp.request)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as e:
                logger.warning("Spotify token request failed: %s", e)
                return None
            except Exception as e:  # noqa: BLE001
                logger.warning("Spotify token request error: %s", e)
                return None

            token = data.get("access_token")
            if not isinstance(token, str) or not token:
                return None
            expires_in = data.get("expires_in")
            ttl = float(expires_in) if isinstance(expires_in, (int, float)) else 3600.0

            self._access_token = token
            self._token_expires_monotonic = time.monotonic() + ttl
            return self._access_token

    def _api_headers(self, bearer: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {bearer}",
            "Accept": "application/json",
        }

    async def lookup_isrc(self, code: str) -> ProviderEntry:
        if not self._configured():
            return ProviderEntry(
                provider=self.id,
                found=False,
                error="Spotify is enabled but credentials are missing (SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET).",
                raw=None,
            )

        token = await self._get_bearer_token()
        if not token:
            return ProviderEntry(
                provider=self.id,
                found=False,
                error="Could not obtain Spotify access token.",
                raw=None,
            )

        url = f"{self._settings.spotify_api_base_url.rstrip('/')}/v1/search"
        params = {"q": f"isrc:{code}", "type": "track", "limit": 5}
        try:
            r = await resilient_get(
                self._client,
                self._settings,
                url,
                params=params,
                headers=self._api_headers(token),
            )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            return ProviderEntry(provider=self.id, found=False, error=f"HTTP error: {e!s}", raw=None)
        except Exception as e:  # noqa: BLE001
            return ProviderEntry(provider=self.id, found=False, error=str(e), raw=None)

        items = (data.get("tracks") or {}).get("items") or []
        if not items:
            return ProviderEntry(
                provider=self.id,
                found=False,
                raw=safe_raw_fragment({"tracks": {"total": (data.get("tracks") or {}).get("total")}}),
            )

        return self._entry_from_track(items[0])

    async def lookup_upc(self, code: str) -> ProviderEntry:
        if not self._configured():
            return ProviderEntry(
                provider=self.id,
                found=False,
                error="Spotify is enabled but credentials are missing (SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET).",
                raw=None,
            )

        token = await self._get_bearer_token()
        if not token:
            return ProviderEntry(
                provider=self.id,
                found=False,
                error="Could not obtain Spotify access token.",
                raw=None,
            )

        url = f"{self._settings.spotify_api_base_url.rstrip('/')}/v1/search"
        params = {"q": f"upc:{code}", "type": "album", "limit": 5}
        try:
            r = await resilient_get(
                self._client,
                self._settings,
                url,
                params=params,
                headers=self._api_headers(token),
            )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            return ProviderEntry(provider=self.id, found=False, error=f"HTTP error: {e!s}", raw=None)
        except Exception as e:  # noqa: BLE001
            return ProviderEntry(provider=self.id, found=False, error=str(e), raw=None)

        items = (data.get("albums") or {}).get("items") or []
        if not items:
            return ProviderEntry(
                provider=self.id,
                found=False,
                raw=safe_raw_fragment({"albums": {"total": (data.get("albums") or {}).get("total")}}),
            )

        return self._entry_from_album(items[0])

    def _entry_from_track(self, track: dict[str, Any]) -> ProviderEntry:
        title = collapse_ws(str(track.get("name") or "")) or None
        artist = self._artists_join(track.get("artists"))
        album_obj = track.get("album") if isinstance(track.get("album"), dict) else {}
        album = collapse_ws(str(album_obj.get("name") or "")) or None
        label = collapse_ws(str(album_obj.get("label") or "")) or None

        raw = safe_raw_fragment(
            {
                "id": track.get("id"),
                "uri": track.get("uri"),
                "external_ids": track.get("external_ids"),
                "external_urls": track.get("external_urls"),
                "album": {"id": album_obj.get("id"), "release_date": album_obj.get("release_date")},
            }
        )

        return ProviderEntry(
            provider=self.id,
            found=bool(title),
            title=title,
            artist=artist,
            album=album,
            label=label,
            raw=raw,
        )

    def _entry_from_album(self, album: dict[str, Any]) -> ProviderEntry:
        title = collapse_ws(str(album.get("name") or "")) or None
        artist = self._artists_join(album.get("artists"))
        label = collapse_ws(str(album.get("label") or "")) or None

        raw = safe_raw_fragment(
            {
                "id": album.get("id"),
                "uri": album.get("uri"),
                "external_ids": album.get("external_ids"),
                "external_urls": album.get("external_urls"),
                "release_date": album.get("release_date"),
            }
        )

        return ProviderEntry(
            provider=self.id,
            found=bool(title),
            title=title,
            artist=artist,
            album=None,
            label=label,
            raw=raw,
        )

    @staticmethod
    def _artists_join(artists: Any) -> str | None:
        if not isinstance(artists, list):
            return None
        names: list[str] = []
        for a in artists:
            if isinstance(a, dict) and a.get("name"):
                names.append(str(a["name"]))
        if not names:
            return None
        return collapse_ws(", ".join(names))
