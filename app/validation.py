import re

_ISRC_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}\d{2}\d{5}$")


def normalize_isrc(code: str) -> str:
    return code.strip().upper().replace("-", "").replace(" ", "")


def validate_isrc(code: str) -> str:
    normalized = normalize_isrc(code)
    if not _ISRC_RE.fullmatch(normalized):
        raise ValueError(
            "ISRC must be 12 characters: 2-letter country, 3-char registrant, "
            "2-digit year, 5-digit designation (hyphens optional)."
        )
    return normalized


def normalize_upc(code: str) -> str:
    return re.sub(r"\D", "", code.strip())


def _ean13_check_digit(first_12: str) -> int:
    total = 0
    for i, ch in enumerate(first_12):
        n = int(ch)
        total += n * (3 if i % 2 else 1)
    return (10 - (total % 10)) % 10


def validate_upc(code: str) -> str:
    digits = normalize_upc(code)
    # GTIN-14: leading packaging indicator + EAN-13 when the tail validates as EAN-13.
    if len(digits) == 14:
        tail = digits[1:]
        if int(tail[12]) == _ean13_check_digit(tail[:12]):
            digits = tail
    if len(digits) not in (8, 12, 13):
        raise ValueError(
            "UPC/EAN must be 8, 12, or 13 digits (or 14 digits that yield a valid EAN-13 after the first digit)."
        )
    if len(digits) == 13:
        expected = _ean13_check_digit(digits[:12])
        if int(digits[12]) != expected:
            raise ValueError("Invalid EAN-13 check digit.")
    elif len(digits) == 12:
        expected = _ean13_check_digit("0" + digits[:11])
        if int(digits[11]) != expected:
            raise ValueError("Invalid UPC-A check digit.")
    elif len(digits) == 8:
        # UPC-E check digit depends on implied expansion; accept 8 digits for lookup compatibility.
        pass
    return digits
