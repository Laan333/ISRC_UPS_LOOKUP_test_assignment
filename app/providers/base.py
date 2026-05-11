from typing import Any, Protocol

from app.schemas.lookup import ProviderEntry


class MetadataProvider(Protocol):
    id: str

    async def lookup_isrc(self, code: str) -> ProviderEntry: ...

    async def lookup_upc(self, code: str) -> ProviderEntry: ...


def safe_raw_fragment(data: Any, max_chars: int = 12000) -> dict[str, Any]:
    if isinstance(data, dict):
        out: dict[str, Any] = dict(data)
    else:
        out = {"value": data}
    text = str(out)
    if len(text) > max_chars:
        return {"_truncated": True, "preview": text[:max_chars]}
    return out
