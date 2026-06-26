"""Edge middleware: assign a correlation id and emit a structured access log.

Runs first on every request so the id is available to logs, error responses, and
downstream engine calls. An inbound X-Correlation-ID is honored (trace propagation);
otherwise a fresh one is generated and echoed back on the response.
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .correlation import (
    CORRELATION_HEADER,
    new_correlation_id,
    set_correlation_id,
)
from .logging import get_logger

logger = get_logger("orchestrator.access")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = request.headers.get(CORRELATION_HEADER) or new_correlation_id()
        set_correlation_id(correlation_id)

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        response.headers[CORRELATION_HEADER] = correlation_id
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": elapsed_ms,
            },
        )
        return response
