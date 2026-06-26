"""Integration: a viewer cannot perform a mutating action (RBAC enforced).

The BYOK config update (PUT /api/v1/tenant/llm-config) requires the admin role.
A viewer is authenticated but unauthorized, so the contract demands 403 (not 404).
"""

from __future__ import annotations

from tests.conftest import Fixtures, auth


def test_viewer_cannot_mutate_returns_403(client, seed: Fixtures) -> None:
    payload = {
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key": "sk-should-be-rejected",
    }
    resp = client.put(
        "/api/v1/tenant/llm-config", json=payload, headers=auth(seed.viewer_a_sub)
    )

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "insufficient_role"


def test_admin_can_mutate_and_secret_is_not_echoed(client, seed: Fixtures) -> None:
    payload = {
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key": "sk-secret-value",
    }
    resp = client.put(
        "/api/v1/tenant/llm-config", json=payload, headers=auth(seed.admin_a_sub)
    )

    assert resp.status_code == 200
    body = resp.json()
    # The encrypted secret must never round-trip back to the client.
    assert "api_key" not in body
    assert body["model"] == "deepseek-chat"


def test_me_returns_user_tenant_and_role(client, seed: Fixtures) -> None:
    resp = client.get("/api/v1/auth/me", headers=auth(seed.admin_a_sub))

    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "admin"
    assert body["tenant"]["slug"] == "acme"
    assert body["user"]["email"] == "admin@acme.id"
