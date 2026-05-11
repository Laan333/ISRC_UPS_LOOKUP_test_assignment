from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ISRC/UPC Lookup"
    app_version: str = Field(
        default="0.1.0",
        description="SemVer for OpenAPI info.version (env: APP_VERSION).",
    )
    openapi_server_url: str = Field(
        default="http://127.0.0.1:8000",
        description="OpenAPI servers[0].url for Swagger Try it out; empty string omits servers.",
    )
    ready_check_url: str | None = Field(
        default=None,
        description=(
            "Optional URL to probe from /ready (env: READY_CHECK_URL). "
            "If set, /ready returns 503 when the URL is unreachable."
        ),
    )
    user_agent: str = "ISRC_UPS_Lookup/1.0 (educational)"
    http_timeout_s: float = 15.0
    http_get_max_retries: int = 2
    http_get_retry_backoff_s: float = 0.15
    outbound_max_concurrent: int = 16
    max_response_body_bytes: int = 2_000_000

    musicbrainz_base_url: str = "https://musicbrainz.org/ws/2"
    deezer_api_base_url: str = "https://api.deezer.com"
    discogs_api_base_url: str = "https://api.discogs.com"
    wikidata_sparql_url: str = "https://query.wikidata.org/sparql"
    open_library_search_url: str = "https://openlibrary.org/search.json"

    discogs_personal_access_token: str | None = None

    provider_musicbrainz_enabled: bool = True
    provider_deezer_enabled: bool = True
    provider_discogs_enabled: bool = True
    provider_wikidata_enabled: bool = True
    provider_open_library_enabled: bool = True

    lookup_cache_enabled: bool = True
    lookup_cache_ttl_s: float = 300.0
    lookup_cache_max_entries: int = 512

    api_rate_limit_per_minute: int = 120

    log_level: str = Field(
        default="INFO",
        description="Root log level (env: LOG_LEVEL), e.g. DEBUG, INFO, WARNING.",
    )
    log_file_path: str | None = Field(
        default="logs/app.log",
        description=(
            "Rotating application log file (env: LOG_FILE_PATH). "
            "Empty string disables file logging (stdout only)."
        ),
    )
    log_max_bytes: int = Field(
        default=5_000_000,
        ge=10_000,
        description="Max size of one log file before rotation (env: LOG_MAX_BYTES).",
    )
    log_backup_count: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Number of rotated log files to keep (env: LOG_BACKUP_COUNT).",
    )

    @field_validator("log_file_path", mode="before")
    @classmethod
    def empty_log_path_means_none(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
