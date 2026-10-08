import logging
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("api.access")


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """
    Structured logging middleware that logs request metadata, status, and duration.
    Never logs request bodies containing secrets, passwords, or audio contents.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        request_id = getattr(request.state, "request_id", "-")

        # Extract client IP safely
        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or (request.client.host if request.client else "-")
        )

        path = request.url.path
        method = request.method

        response: Response = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000, 2)

        # Do not log spammy health check routes at INFO level
        if path.startswith("/health"):
            return response

        logger.info(
            "HTTP %s %s status=%d duration=%.2fms ip=%s req_id=%s",
            method,
            path,
            response.status_code,
            duration_ms,
            client_ip,
            request_id,
        )

        return response
