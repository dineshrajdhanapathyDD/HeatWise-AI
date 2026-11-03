"""One JSON error envelope for every API error (D-M3-7):
`{"error": {"code", "message", "fields": [{"field", "message"}]}}`. No stack traces."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.jobs import TooManyJobs
from backend.api.schemas import ErrorBody, ErrorDetail, FieldError

logger = logging.getLogger("heatwise.api")

_VALUE_ERROR_PREFIX = "Value error, "


def error_response(status: int, code: str, message: str, fields: list[FieldError] | None = None,
                   headers: dict[str, str] | None = None) -> JSONResponse:
    body = ErrorBody(error=ErrorDetail(code=code, message=message, fields=fields or []))
    return JSONResponse(status_code=status, content=body.model_dump(), headers=headers)


def _field_errors(exc: RequestValidationError) -> list[FieldError]:
    out: list[FieldError] = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p != "body"]
        msg = str(err.get("msg", "Invalid value."))
        if msg.startswith(_VALUE_ERROR_PREFIX):
            msg = msg[len(_VALUE_ERROR_PREFIX):]
        out.append(FieldError(field=".".join(loc), message=msg))
    return out


async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(422, "validation_error", "The request is not valid.", _field_errors(exc))


async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "not_found" if exc.status_code == 404 else f"http_{exc.status_code}"
    message = exc.detail if isinstance(exc.detail, str) else "The request could not be handled."
    return error_response(exc.status_code, code, message, headers=getattr(exc, "headers", None))


async def _too_many(_: Request, exc: TooManyJobs) -> JSONResponse:
    return error_response(429, "too_many_jobs", "Too many assessments are queued or running. Try again shortly.")


async def _internal(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled API error", exc_info=exc)
    return error_response(500, "internal_error", "Something went wrong on the server.")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http)  # type: ignore[arg-type]
    app.add_exception_handler(TooManyJobs, _too_many)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _internal)
