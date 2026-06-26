"""Unit: circuit breaker opens after the failure threshold and recovers half-open."""

from __future__ import annotations

import pytest

from src.engines.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


def _breaker(**kwargs) -> CircuitBreaker:
    defaults = dict(name="test", fail_threshold=3, reset_seconds=10.0)
    defaults.update(kwargs)
    return CircuitBreaker(**defaults)


def test_opens_after_threshold_failures() -> None:
    cb = _breaker()
    for _ in range(3):
        cb.before_call()
        cb.record_failure()

    assert cb.state is CircuitState.open
    with pytest.raises(CircuitOpenError):
        cb.before_call()


def test_success_resets_failure_count() -> None:
    cb = _breaker()
    cb.before_call()
    cb.record_failure()
    cb.record_success()

    assert cb.state is CircuitState.closed
    cb.before_call()  # does not raise


def test_half_open_trial_after_reset_window() -> None:
    cb = _breaker(reset_seconds=0.0)  # immediately eligible for a trial
    for _ in range(3):
        cb.before_call()
        cb.record_failure()
    assert cb.state is CircuitState.open

    # Reset window elapsed -> next call is allowed as a half-open trial.
    cb.before_call()
    assert cb.state is CircuitState.half_open
    cb.record_success()
    assert cb.state is CircuitState.closed
