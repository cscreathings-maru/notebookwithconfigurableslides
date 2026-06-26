"""Resilient base for engine HTTP clients.

Wraps httpx with: a per-call timeout, bounded retry with exponential backoff (only
on transport errors and 5xx/429), and a circuit breaker. Engine-specific clients
subclass this and add typed methods — they never re-implement resilience. Engine
errors are normalized to EngineError so no upstream detail leaks to the client.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from ..core.config import get_settings
from ..core.errors import EngineError
from ..core.logging import get_logger
from .circuit_breaker import CircuitBreaker

logger = get_logger("orchestrator.engines")

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class EngineClient:
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        auth: tuple[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        settings = get_settings()
        self.name = name
        self.base_url = base_url.rstrip("/")
        self._timeout = settings.engine_timeout_seconds
        self._max_retries = settings.engine_max_retries
        self._backoff_base = settings.engine_backoff_base_seconds
        self._auth = auth
        self._client = client  # injectable for tests
        self._breaker = CircuitBreaker(
            name=name,
            fail_threshold=settings.engine_circuit_fail_threshold,
            reset_seconds=settings.engine_circuit_reset_seconds,
        )

    @property
    def breaker(self) -> CircuitBreaker:
        return self._breaker

    def _http(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self._timeout,
            auth=httpx.BasicAuth(*self._auth) if self._auth else None,
        )

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Issue a request through the breaker with bounded backoff retries."""
        self._breaker.before_call()
        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                client = self._http()
                owns_client = self._client is None
                try:
                    response = await client.request(method, path, **kwargs)
                finally:
                    if owns_client:
                        await client.aclose()

                if response.status_code in _RETRYABLE_STATUS:
                    raise httpx.HTTPStatusError(
                        f"retryable status {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                self._breaker.record_success()
                return response

            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                self._breaker.record_failure()
                if attempt >= self._max_retries:
                    break
                await asyncio.sleep(self._backoff_base * (2 ** (attempt - 1)))

        logger.error(
            "engine_request_failed",
            extra={"engine": self.name, "method": method, "path": path},
        )
        raise EngineError(f"Engine '{self.name}' request failed.") from last_exc
