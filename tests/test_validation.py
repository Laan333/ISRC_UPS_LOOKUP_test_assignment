import pytest

from app.validation import (
    _ean13_check_digit,
    normalize_isrc,
    validate_isrc,
    validate_upc,
)


def test_isrc_normalize_and_validate() -> None:
    assert validate_isrc("us-rc17607839") == "USRC17607839"


def test_isrc_invalid() -> None:
    with pytest.raises(ValueError):
        validate_isrc("short")
    with pytest.raises(ValueError):
        validate_isrc("USRC1761234")


def test_upc_ean13_valid() -> None:
    base12 = "590123412345"
    check = _ean13_check_digit(base12)
    full = base12 + str(check)
    assert validate_upc(full) == full


def test_upc_invalid_check() -> None:
    with pytest.raises(ValueError):
        validate_upc("5901234123450")


def test_normalize_isrc() -> None:
    assert normalize_isrc(" gb-xyz-12-34567 ") == "GBXYZ1234567"
