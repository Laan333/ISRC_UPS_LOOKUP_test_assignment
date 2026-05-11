import re


def collapse_ws(s: str | None) -> str | None:
    if s is None:
        return None
    return re.sub(r"\s+", " ", s.strip())


def norm_compare(s: str | None) -> str:
    if not s:
        return ""
    return collapse_ws(s).casefold() or ""
