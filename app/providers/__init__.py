from app.providers.base import MetadataProvider
from app.providers.deezer import DeezerProvider
from app.providers.discogs import DiscogsProvider
from app.providers.musicbrainz import MusicBrainzProvider
from app.providers.open_library import OpenLibraryProvider
from app.providers.spotify import SpotifyProvider
from app.providers.wikidata import WikidataIsrcProvider

__all__ = [
    "MetadataProvider",
    "MusicBrainzProvider",
    "DeezerProvider",
    "DiscogsProvider",
    "OpenLibraryProvider",
    "SpotifyProvider",
    "WikidataIsrcProvider",
]
