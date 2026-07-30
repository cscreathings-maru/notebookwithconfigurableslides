"""T-2.4: health endpoints must be reachable and report per dependency.

Two defects, both invisible from inside the app: the endpoints were mounted only at
the root, where Traefik routes `/` to the frontend, so nothing in the deployed stack
could reach them; and `/readyz` checked Postgres alone, so a Redis, MinIO or engine
outage looked identical to a healthy service.

Readiness is deliberately graded. Only Postgres — the system of record — can make the
service `unready`; a Presenton outage degrades it, because the API still serves
everything that is not deck rendering.
"""

from __future__ import annotations

import pytest

# Both mounts must work: /api for Traefik, root for container probes.
HEALTH_PATHS = ["/healthz", "/api/healthz"]
READY_PATHS = ["/readyz", "/api/readyz"]

EXPECTED_DEPENDENCIES = {"postgres", "redis", "minio", "open_notebook", "presenton"}


@pytest.mark.parametrize("path", HEALTH_PATHS)
def test_liveness_is_reachable(client, path) -> None:
    # Act
    resp = client.get(path)

    # Assert
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.parametrize("path", READY_PATHS)
def test_readiness_is_reachable(client, path) -> None:
    # Act
    resp = client.get(path)

    # Assert -- 200 healthy/degraded, 503 only when Postgres is gone
    assert resp.status_code in (200, 503)


@pytest.mark.parametrize("path", READY_PATHS)
def test_readiness_reports_every_dependency_separately(client, path) -> None:
    # Act
    body = client.get(path).json()

    # Assert
    assert set(body["dependencies"]) == EXPECTED_DEPENDENCIES
    for name, check in body["dependencies"].items():
        assert check["status"] in {"ok", "degraded", "down", "misconfigured"}, name


def test_reachable_database_keeps_the_service_ready(client) -> None:
    """The test DB is reachable, so Postgres is ok however the engines fare."""
    # Act
    body = client.get("/api/readyz").json()

    # Assert
    assert body["dependencies"]["postgres"]["status"] == "ok"
    assert body["status"] in {"ok", "degraded"}
    assert body["status"] != "unready"


def test_an_engine_outage_degrades_but_does_not_unready(client) -> None:
    """A dead Presenton must not take the orchestrator out of the load balancer."""
    # Act -- no engines run in the test environment, so they are already down
    body = client.get("/api/readyz").json()

    # Assert
    unhealthy = [n for n, c in body["dependencies"].items() if c["status"] != "ok"]
    assert unhealthy, "engines should be unreachable in tests; probe may be a no-op"
    assert body["status"] == "degraded"


def test_liveness_does_not_depend_on_dependencies(client) -> None:
    """Liveness answers 'is the process up', so it must stay ok while deps are down."""
    # Act
    ready = client.get("/api/readyz").json()
    live = client.get("/api/healthz").json()

    # Assert
    assert ready["status"] == "degraded"
    assert live["status"] == "ok"
