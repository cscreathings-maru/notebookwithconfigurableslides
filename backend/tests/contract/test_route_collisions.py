"""T-1.1: Presenton's Traefik allowlist must not steal orchestrator routes.

Presenton is served same-origin under `/editor`, but `basePath` only rewrites
`Link`/`Image`/router navigation — not client-side `fetch()`. Its Python API is called
at root paths, so the Traefik router carries an explicit allowlist of those prefixes at
**priority 20**, above the orchestrator's `/api` router at priority 10.

That allowlist therefore *takes* paths from the orchestrator. Nothing collides today,
which is exactly why it would regress silently: someone adds `/api/v1/admin/...` to the
orchestrator and it starts resolving to the slide engine, with no error anywhere.

The allowlist is parsed from the compose file rather than duplicated here — a copy would
drift, and a drifted guard is worse than none.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.main import app

COMPOSE = Path(__file__).parents[3] / "deploy" / "docker-compose.lite.yml"

# Presenton legitimately owns these; the orchestrator must never route under them.
# `/editor` is excluded from the collision check itself — it is the whole point of the
# rule, and the orchestrator has no reason to serve anything there.
_ALWAYS_PRESENTON = {"/editor"}


def _presenton_allowlist() -> list[str]:
    """Every PathPrefix the presenton router claims, read from the compose file."""
    text = COMPOSE.read_text(encoding="utf-8")
    rule_lines = [
        line for line in text.splitlines() if "routers.presenton.rule" in line
    ]
    assert rule_lines, "presenton router rule not found — has the compose file moved?"
    return re.findall(r"PathPrefix\(`([^`]+)`\)", rule_lines[0])


def _orchestrator_paths() -> list[str]:
    """Canonical paths the orchestrator serves, from its own OpenAPI schema."""
    return sorted(app.openapi()["paths"])


def test_the_allowlist_is_not_empty() -> None:
    """Guards the parser: a regex that silently matches nothing would pass everything."""
    allowlist = _presenton_allowlist()

    assert len(allowlist) > 5, allowlist
    assert "/editor" in allowlist


def test_the_orchestrator_serves_routes_worth_protecting() -> None:
    """Second parser guard, on the other side of the comparison."""
    paths = _orchestrator_paths()

    assert len(paths) > 20, paths
    assert "/api/v1/projects" in paths


@pytest.mark.parametrize("prefix", sorted(set(_presenton_allowlist()) - _ALWAYS_PRESENTON))
def test_no_orchestrator_route_sits_under_a_presenton_prefix(prefix: str) -> None:
    # Act -- Traefik matches on prefix, so any route starting with it is captured
    stolen = [p for p in _orchestrator_paths() if p.startswith(prefix)]

    # Assert
    assert not stolen, (
        f"Presenton's allowlist claims {prefix!r} at priority 20, which would capture "
        f"these orchestrator routes before they reach the API: {stolen}. "
        f"Either rename the orchestrator route or narrow the allowlist entry."
    )


def test_health_endpoints_are_not_captured() -> None:
    """`/api/healthz` and `/api/readyz` sit under /api, where the allowlist also lives."""
    # Arrange
    allowlist = set(_presenton_allowlist()) - _ALWAYS_PRESENTON

    # Act / Assert
    for probe in ("/api/healthz", "/api/readyz"):
        captured = [p for p in allowlist if probe.startswith(p)]
        assert not captured, f"{probe} would be routed to Presenton by {captured}"
