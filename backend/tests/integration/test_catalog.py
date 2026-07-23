"""Integration: the Studio dropdown catalogs — /models and /languages.

Both are viewer-visible and driven by config; the active default is listed first.
"""

from __future__ import annotations

from tests.conftest import Fixtures, auth


def test_languages_lists_default_first(client, seed: Fixtures) -> None:
    resp = client.get("/api/v1/languages", headers=auth(seed.author_a_sub))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body[0]["id"] == "Bahasa Indonesia"
    assert body[0]["default"] is True
    ids = [row["id"] for row in body]
    assert "English" in ids
    assert sum(1 for row in body if row["default"]) == 1


def test_models_lists_default_first(client, seed: Fixtures) -> None:
    resp = client.get("/api/v1/models", headers=auth(seed.author_a_sub))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body[0]["default"] is True
    assert sum(1 for row in body if row["default"]) == 1
