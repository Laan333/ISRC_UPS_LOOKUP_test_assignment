from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProviderEntry(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "provider": "musicbrainz",
                    "found": True,
                    "title": "Example Song",
                    "artist": "Example Artist",
                    "album": None,
                    "label": None,
                    "error": None,
                    "raw": {"id": "recording-id"},
                },
                {
                    "provider": "discogs",
                    "found": False,
                    "title": None,
                    "artist": None,
                    "album": None,
                    "label": None,
                    "error": "HTTP error: Client error '404 Not Found'",
                    "raw": None,
                },
            ]
        }
    )

    provider: str
    found: bool
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    label: str | None = None
    error: str | None = None
    raw: dict[str, Any] | None = None


class SummaryBlock(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"found_in": 2, "confidence": "high", "note": None},
                {"found_in": 0, "confidence": "low", "note": "No provider returned a match."},
            ]
        }
    )

    found_in: int = Field(ge=0)
    confidence: Literal["high", "medium", "low"]
    note: str | None = None


_LOOKUP_RESPONSE_EXAMPLE: dict[str, Any] = {
    "query": "USRC17607839",
    "providers": [
        {
            "provider": "musicbrainz",
            "found": True,
            "title": "Example Song",
            "artist": "Example Artist",
            "album": None,
            "label": None,
            "error": None,
            "raw": {"id": "abc", "title": "Example Song"},
        },
        {
            "provider": "wikidata",
            "found": True,
            "title": "Example Song",
            "artist": "Example Artist",
            "album": None,
            "label": None,
            "error": None,
            "raw": {"entity": "http://www.wikidata.org/entity/Q1"},
        },
    ],
    "summary": {"found_in": 2, "confidence": "high", "note": None},
}


class LookupResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [_LOOKUP_RESPONSE_EXAMPLE]})

    query: str
    providers: list[ProviderEntry]
    summary: SummaryBlock
