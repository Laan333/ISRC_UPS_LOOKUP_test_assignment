"""Consistent JSON error responses and logging for unexpected failures."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _or_new_rid(request: Request) -> str:
    rid = _request_id(request)
    if rid is None:
        rid = str(uuid.uuid4())
        request.state.request_id = rid
    return rid


def register_exception_handlers(app: Any) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        rid = _or_new_rid(request)
        return JSONResponse(
            status_code=422,
            content={
                "detail": exc.errors(),
                "type": "validation_error",
                "request_id": rid,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        rid = _or_new_rid(request)
        detail: Any = exc.detail
        if isinstance(detail, str):
            body: dict[str, Any] = {
                "detail": detail,
                "type": "http_error",
                "request_id": rid,
            }
        else:
            body = {"detail": detail, "type": "http_error", "request_id": rid}
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        rid = _or_new_rid(request)
        logger.exception("Unhandled error request_id=%s", rid)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "type": "internal_error",
                "request_id": rid,
            },
        )
