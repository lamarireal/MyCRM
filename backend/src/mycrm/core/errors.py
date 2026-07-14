from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def error_response(
    *, request: Request, status_code: int, code: str, message: str, details: Any = None
) -> JSONResponse:
    content: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": _request_id(request),
        }
    }
    if details is not None:
        content["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=content)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return error_response(
            request=request,
            status_code=exc.status_code,
            code=f"http_{exc.status_code}",
            message=message,
            details=None if isinstance(exc.detail, str) else exc.detail,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            request=request,
            status_code=422,
            code="validation_error",
            message="Request validation failed",
            details=exc.errors(),
        )

    @app.exception_handler(Exception)
    async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request.app.state.logger.exception(
            "Unhandled application error",
            extra={"request_id": _request_id(request)},
        )
        return error_response(
            request=request,
            status_code=500,
            code="internal_error",
            message="An unexpected error occurred",
        )
