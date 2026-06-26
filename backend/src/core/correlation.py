"""Per-request correlation id propagated via a contextvar.

Set by CorrelationIdMiddleware at the edge of every request so structured logs,
error responses, and (later) engine calls can be traced end-to-end.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

CORRELATION_HEADER = "X-Correlation-ID"

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> str | None:
    return _correlation_id.get()
