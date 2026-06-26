"""Alert sink for operational events (e.g. quota exceeded).

A minimal seam: the default logs a structured alert; production can swap in a sink
that posts to a webhook / pager. Secrets must never be placed in alert payloads.
"""

from __future__ import annotations

from typing import Any, Protocol

from ..core.logging import get_logger

logger = get_logger("orchestrator.alerts")


class AlertSink(Protocol):
    def emit(self, event: dict[str, Any]) -> None: ...


class LoggingAlertSink:
    def emit(self, event: dict[str, Any]) -> None:
        logger.warning("alert", extra={"alert": event})


def get_alert_sink() -> AlertSink:
    return LoggingAlertSink()
