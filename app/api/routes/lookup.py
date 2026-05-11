from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request

from app.schemas.lookup import LookupResponse
from app.services.lookup_service import LookupService
from app.validation import validate_isrc, validate_upc

router = APIRouter(prefix="/lookup", tags=["lookup"])

_ISRC_422 = {
    "description": "Код не соответствует формату ISRC после нормализации.",
    "content": {
        "application/json": {
            "examples": {
                "invalid_isrc": {
                    "summary": "Неверный ISRC",
                    "value": {"detail": "Invalid ISRC format"},
                },
            }
        }
    },
}

_UPC_422 = {
    "description": "Код не соответствует UPC-A / EAN-8 / EAN-13 или контрольной цифре.",
    "content": {
        "application/json": {
            "examples": {
                "invalid_upc": {
                    "summary": "Неверный UPC/EAN",
                    "value": {"detail": "Invalid UPC/EAN check digit"},
                },
            }
        }
    },
}


def _service(request: Request) -> LookupService:
    return request.app.state.lookup_service


def _rid(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.get(
    "/isrc/{code}",
    response_model=LookupResponse,
    summary="Поиск по ISRC",
    description=(
        "Параллельный опрос провайдеров по нормализованному ISRC (регистр и дефисы не важны). "
        "Частичные ошибки отражаются в `providers[].error`."
    ),
    response_description="Сводный JSON: провайдеры и блок `summary`.",
    responses={422: _ISRC_422},
)
async def lookup_isrc(
    code: Annotated[
        str,
        Path(
            max_length=64,
            description="Строка ISRC (допускаются пробелы и дефисы; нормализуется перед запросами).",
            examples=["USRC17607839"],
        ),
    ],
    request: Request,
) -> LookupResponse:
    try:
        normalized = validate_isrc(code)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return await _service(request).lookup_isrc(normalized, _rid(request))


@router.get(
    "/upc/{code}",
    response_model=LookupResponse,
    summary="Поиск по UPC / EAN",
    description=(
        "Параллельный опрос провайдеров по штрихкоду (8 / 12 / 13 цифр; для 12 и 13 проверяется контрольная цифра; "
        "14-значный GTIN-14 нормализуется в EAN-13, если хвост из 13 цифр валиден). "
        "Частичные ошибки отражаются в `providers[].error`."
    ),
    response_description="Сводный JSON: провайдеры и блок `summary`.",
    responses={422: _UPC_422},
)
async def lookup_upc(
    code: Annotated[
        str,
        Path(
            max_length=32,
            description="Цифры: 8, 12, 13 (EAN/UPC) или 14 (GTIN-14 → EAN-13 при валидном хвосте).",
            examples=["5901234123457"],
        ),
    ],
    request: Request,
) -> LookupResponse:
    try:
        normalized = validate_upc(code)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return await _service(request).lookup_upc(normalized, _rid(request))
