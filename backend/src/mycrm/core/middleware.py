import asyncio
from collections import defaultdict, deque
from time import perf_counter, time
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from mycrm.core.config import Settings
from mycrm.core.errors import error_response


class FixedWindowRateLimiter:
    """Small single-instance limiter for the initial public deployment.

    A shared Redis-backed implementation must replace this class before the API
    is scaled to multiple backend instances.
    """

    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> bool:
        now = time()
        cutoff = now - self.window_seconds
        async with self._lock:
            requests = self._requests[key]
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= self.limit:
                return False
            requests.append(now)
            return True


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def install_request_middleware(app: FastAPI, settings: Settings) -> None:
    limiter = FixedWindowRateLimiter(settings.public_rate_limit_per_minute)

    @app.middleware("http")
    async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        started_at = perf_counter()

        content_length = request.headers.get("content-length")
        if (
            content_length is not None
            and content_length.isdecimal()
            and int(content_length) > settings.max_request_body_bytes
        ):
            return error_response(
                request=request,
                status_code=413,
                code="payload_too_large",
                message="Request body is too large",
            )

        if request.url.path.startswith("/api/") and not await limiter.allow(_client_key(request)):
            rate_limit_response = error_response(
                request=request,
                status_code=429,
                code="rate_limit_exceeded",
                message="Too many requests",
            )
            rate_limit_response.headers["Retry-After"] = "60"
            return rate_limit_response

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        request.app.state.logger.info(
            "HTTP request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        return response
