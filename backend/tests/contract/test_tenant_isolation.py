"""Contract: cross-tenant access returns 404 (never 403), to avoid enumeration.

Per orchestrator-api.md: "cross-tenant access returns 404 to avoid resource
enumeration." Tenant A asks for a job that belongs to Tenant B; the tenant-scoped
repository filters it out, so it is simply not found.
"""

from __future__ import annotations

from tests.conftest import Fixtures, auth


def test_cross_tenant_job_access_returns_404(client, seed: Fixtures) -> None:
    # Tenant A's viewer requests Tenant B's job.
    resp = client.get(f"/api/v1/jobs/{seed.job_b_id}", headers=auth(seed.viewer_a_sub))

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "not_found"


def test_same_tenant_job_access_succeeds(client, seed: Fixtures) -> None:
    # Tenant B's own user can read the job — proves 404 above is isolation, not a 404 bug.
    resp = client.get(f"/api/v1/jobs/{seed.job_b_id}", headers=auth(seed.user_b_sub))

    assert resp.status_code == 200
    assert resp.json()["id"] == str(seed.job_b_id)


def test_unauthenticated_request_is_401(client, seed: Fixtures) -> None:
    resp = client.get(f"/api/v1/jobs/{seed.job_b_id}")

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"
