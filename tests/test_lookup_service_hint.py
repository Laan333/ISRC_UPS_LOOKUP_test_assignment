"""LookupService: omit error-only providers and Deezer/Discogs title-hint refinement."""

from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.schemas.lookup import ProviderEntry, SummaryBlock
from app.services.lookup_service import LookupService


class _Mb:
    id = "musicbrainz"

    async def lookup_isrc(self, code: str) -> ProviderEntry:
        return ProviderEntry(
            provider=self.id,
            found=True,
            title="Hint Title",
            artist="Hint Artist",
        )

    async def lookup_upc(self, code: str) -> ProviderEntry:
        return ProviderEntry(provider=self.id, found=True, title="Album T", artist="Band")


class _Deezer:
    id = "deezer"

    def __init__(self) -> None:
        self.hint_query: str | None = None

    async def lookup_isrc(self, code: str) -> ProviderEntry:
        return ProviderEntry(provider=self.id, found=False, raw={"total": 0})

    async def lookup_upc(self, code: str) -> ProviderEntry:
        return ProviderEntry(provider=self.id, found=False, raw={"total": 0})

    async def lookup_free_text(self, query: str) -> ProviderEntry:
        self.hint_query = query
        return ProviderEntry(
            provider=self.id,
            found=True,
            title="Hint Title",
            artist="Hint Artist",
        )


class _Discogs:
    id = "discogs"

    def __init__(self) -> None:
        self.hint_query: str | None = None

    async def lookup_isrc(self, code: str) -> ProviderEntry:
        return ProviderEntry(provider=self.id, found=False, raw={"result_count": 0})

    async def lookup_upc(self, code: str) -> ProviderEntry:
        return ProviderEntry(provider=self.id, found=False, raw={"result_count": 0})

    async def lookup_release_free_text(self, query: str) -> ProviderEntry:
        self.hint_query = query
        return ProviderEntry(provider=self.id, found=True, title="Discogs T", artist="Hint Artist")


class _Wikidata429:
    id = "wikidata"

    async def lookup_isrc(self, code: str) -> ProviderEntry:
        return ProviderEntry(
            provider=self.id,
            found=False,
            error="HTTP error: Client error '429 Too Many Requests'",
            raw=None,
        )

    async def lookup_upc(self, code: str) -> ProviderEntry:
        return ProviderEntry(provider=self.id, found=False, error=None, raw=None)


@pytest.mark.asyncio
async def test_isrc_omits_wikidata_on_error_and_refines_deezer_discogs() -> None:
    settings = Settings()
    deezer = _Deezer()
    discogs = _Discogs()
    providers = [_Mb(), deezer, discogs, _Wikidata429()]
    async with httpx.AsyncClient() as client:
        svc = LookupService(settings, client, providers=providers)
        out = await svc.lookup_isrc("USUM72201759", None)

    by = {p.provider: p for p in out.providers}
    assert "wikidata" not in by
    assert by["deezer"].found is True
    assert deezer.hint_query == "Hint Artist Hint Title"
    assert discogs.hint_query == "Hint Artist Hint Title"
    assert by["discogs"].found is True


def test_summary_note_when_upstream_errors_omitted() -> None:
    before = [
        ProviderEntry(
            provider="musicbrainz",
            found=False,
            error="HTTP error: Server error '502 Bad Gateway'",
            raw=None,
        ),
        ProviderEntry(provider="deezer", found=False, raw={"total": 0}),
    ]
    summary = LookupService._summary_with_dropped_errors(
        before,
        SummaryBlock(found_in=0, confidence="low", note=None),
    )
    assert summary.note
    assert "musicbrainz" in summary.note.lower()
    assert "502" in summary.note


@pytest.mark.asyncio
async def test_omit_does_not_drop_found_false_without_error() -> None:
    settings = Settings()
    providers = [
        ProviderEntry(provider="deezer", found=False, raw={"total": 0}),
        ProviderEntry(provider="x", found=False, error="boom", raw=None),
    ]
    out = LookupService._omit_providers_with_only_error(providers)
    assert [p.provider for p in out] == ["deezer"]
