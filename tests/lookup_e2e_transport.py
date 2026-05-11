"""Single MockTransport that satisfies all outbound providers for lookup E2E tests."""

from __future__ import annotations

import json
from pathlib import Path

import httpx


def _load_fixture(name: str) -> dict:
    path = Path(__file__).parent / "fixtures" / name
    return json.loads(path.read_text(encoding="utf-8"))


def build_lookup_e2e_transport() -> httpx.MockTransport:
    mb_recording = _load_fixture("musicbrainz_recording.json")
    mb_recording_detail = _load_fixture("musicbrainz_recording_detail.json")
    mb_release = _load_fixture("musicbrainz_release.json")
    mb_release_labels = _load_fixture("musicbrainz_release_labels.json")
    open_library = _load_fixture("open_library_search.json")
    deezer_search = _load_fixture("deezer_search.json")

    discogs_barcode = {
        "results": [
            {
                "id": 12345,
                "title": "Discogs Album",
                "artist": "Discogs Artist",
                "type": "release",
                "barcode": "5901234123457",
                "year": "2019",
            }
        ]
    }
    discogs_release_detail = {
        "id": 12345,
        "title": "Discogs Album",
        "year": 2019,
        "country": "Poland",
        "artists": [{"name": "Discogs Artist"}],
        "labels": [{"name": "Discogs Label", "catno": "X-1"}],
        "formats": [{"name": "CD", "qty": "1"}],
    }
    discogs_isrc = {
        "results": [
            {"title": "Discogs ISRC Match", "artist": "Side Artist", "type": "release", "year": "2018"}
        ]
    }
    wikidata = {
        "results": {
            "bindings": [
                {
                    "work": {"value": "http://www.wikidata.org/entity/Q123"},
                    "workLabel": {"value": "Wikidata Work"},
                    "performerLabel": {"value": "Wikidata Performer"},
                }
            ]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "musicbrainz.org" in u and "/ws/2/recording/" in u and "query=" not in u:
            return httpx.Response(200, json=mb_recording_detail)
        if "musicbrainz.org" in u and "/recording" in u and "query=" in u and "isrc" in u.lower():
            return httpx.Response(200, json=mb_recording)
        if "musicbrainz.org" in u and "/ws/2/release/" in u and "inc=labels" in u:
            return httpx.Response(200, json=mb_release_labels)
        if "musicbrainz.org" in u and "/release" in u and "barcode" in u.lower():
            return httpx.Response(200, json=mb_release)
        if "api.discogs.com" in u and "/releases/" in u:
            return httpx.Response(200, json=discogs_release_detail)
        if "api.discogs.com" in u and "database/search" in u:
            if "5901234123457" in u:
                return httpx.Response(200, json=discogs_barcode)
            return httpx.Response(200, json=discogs_isrc)
        if "query.wikidata.org" in u:
            return httpx.Response(200, json=wikidata)
        if "openlibrary.org" in u and "search.json" in u:
            return httpx.Response(200, json=open_library)
        if "api.deezer.com" in u and "/search" in u:
            return httpx.Response(200, json=deezer_search)
        return httpx.Response(404, text=f"unmocked: {u}")

    return httpx.MockTransport(handler)
