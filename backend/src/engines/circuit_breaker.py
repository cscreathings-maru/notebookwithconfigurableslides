"""A minimal circuit breaker for engine calls.

States: closed (normal) -> open (failing fast) -> half_open (one trial) -> closed.
After `fail_threshold` consecutive failures the circuit opens for `reset_seconds`;
the next call is a half-open trial that closes the circuit on success or re-opens it
on failure. Prevents hammering a sick engine and gives it room to recover.
"""

from __future__ import annotations

import time
from enum import Enum

from ..core.errors import EngineError


class CircuitState(str, Enum):
    closed = "closed"
    open = "open"
    half_open = "half_open"


class CircuitOpenError(EngineError):
    code = "circuit_open"


class CircuitBreaker:
    def __init__(self, *, name: str, fail_threshold: int, reset_seconds: float):
        self.name = name
        self.fail_threshold = fail_threshold
        self.reset_seconds = reset_seconds
        self._failures = 0
        self._state = CircuitState.closed
        self._opened_at = 0.0

    @property
    def state(self) -> CircuitState:
        return self._state

    def _now(self) -> float:
        return time.monotonic()

    def before_call(self) -> None:
        """Raise if the circuit is open and not yet ready for a half-open trial."""
        if self._state is CircuitState.open:
            if self._now() - self._opened_at >= self.reset_seconds:
                self._state = CircuitState.half_open
            else:
                raise CircuitOpenError(f"Engine '{self.name}' circuit is open.")

    def record_success(self) -> None:
        self._failures = 0
        self._state = CircuitState.closed

    def record_failure(self) -> None:
        self._failures += 1
        if self._state is CircuitState.half_open or self._failures >= self.fail_threshold:
            self._state = CircuitState.open
            self._opened_at = self._now()
