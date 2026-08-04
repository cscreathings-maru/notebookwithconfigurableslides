"""Integration: truncated chat answers and continuing them (Phase F1).

Chat completions were capped at `max_tokens=1000` — hard-coded, and the lowest cap
in the codebase on the only surface producing long prose — and the provider's own
`finish_reason` was discarded, so a cut-off answer rendered identically to a
complete one. These tests pin: the configured cap actually reaches the provider,
a truncated answer is marked as such, `continue` requires that mark, and continuing
appends to the SAME message rather than creating a new one.
"""

from __future__ import annotations

import pytest

from src.api import deps as api_deps
from src.main import app
from tests.conftest import Fixtures, auth
from tests.fakes import FakeLlm, FakeObjectStore, FakeOpenNotebook

PROVIDER = {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "sk-x",
}


@pytest.fixture
def on_client() -> FakeOpenNotebook:
    return FakeOpenNotebook()


@pytest.fixture(autouse=True)
def _wire(on_client):
    app.dependency_overrides[api_deps.get_open_notebook_client] = lambda: on_client
    app.dependency_overrides[api_deps.get_object_store] = lambda: FakeObjectStore()
    yield
    app.dependency_overrides.clear()


def _set_byok(client, seed: Fixtures) -> None:
    resp = client.put("/api/v1/tenant/llm-config", json=PROVIDER, headers=auth(seed.admin_a_sub))
    assert resp.status_code == 200, resp.text


def _project(client, sub: str) -> str:
    resp = client.post("/api/v1/projects", json={"name": "Onboarding"}, headers=auth(sub))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _ask(client, sub: str, project_id: str, question: str):
    return client.post(
        f"/api/v1/projects/{project_id}/chat", json={"question": question}, headers=auth(sub)
    )


def test_the_configured_cap_reaches_the_provider_not_a_hardcoded_one(
    client, seed: Fixtures
) -> None:
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    llm = FakeLlm()
    app.dependency_overrides[api_deps.get_llm_client] = lambda: llm

    # Act
    resp = _ask(client, seed.author_a_sub, project_id, "Apa syarat pendaftaran?")

    # Assert -- default is 8000, not the old hard-coded 1000
    assert resp.status_code == 200, resp.text
    assert 8000 in llm.max_tokens_seen


def test_a_truncated_answer_is_marked_and_a_complete_one_is_not(
    client, seed: Fixtures
) -> None:
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    llm = FakeLlm(truncate_first_answer=True)
    app.dependency_overrides[api_deps.get_llm_client] = lambda: llm

    # Act
    truncated = _ask(client, seed.author_a_sub, project_id, "Ceritakan tentang revenue").json()
    complete = _ask(client, seed.author_a_sub, project_id, "Pertanyaan kedua").json()

    # Assert
    assert truncated["truncated"] is True
    assert complete["truncated"] is False


def test_continuing_appends_to_the_same_message_and_clears_the_flag(
    client, seed: Fixtures
) -> None:
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    llm = FakeLlm(truncate_first_answer=True)
    app.dependency_overrides[api_deps.get_llm_client] = lambda: llm
    truncated = _ask(client, seed.author_a_sub, project_id, "Ceritakan tentang revenue").json()
    assert truncated["truncated"] is True
    original_text = truncated["content"]

    # Act
    resp = client.post(
        f"/api/v1/chat/messages/{truncated['id']}/continue", headers=auth(seed.author_a_sub)
    )

    # Assert -- SAME message id, content grew, flag cleared
    assert resp.status_code == 200, resp.text
    continued = resp.json()
    assert continued["id"] == truncated["id"]
    assert continued["content"].startswith(original_text)
    assert len(continued["content"]) > len(original_text)
    assert continued["truncated"] is False

    # And the thread has exactly 2 messages, not 3 -- nothing new was created
    messages = client.get(
        f"/api/v1/projects/{project_id}/chat", headers=auth(seed.author_a_sub)
    ).json()
    assert len(messages) == 2


def test_continuing_a_complete_answer_is_rejected(client, seed: Fixtures) -> None:
    # Arrange -- an ordinary, non-truncated answer
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    app.dependency_overrides[api_deps.get_llm_client] = lambda: FakeLlm()
    answered = _ask(client, seed.author_a_sub, project_id, "Halo").json()
    assert answered["truncated"] is False

    # Act
    resp = client.post(
        f"/api/v1/chat/messages/{answered['id']}/continue", headers=auth(seed.author_a_sub)
    )

    # Assert
    assert resp.status_code == 422, resp.text


def test_continuing_a_user_message_is_rejected(client, seed: Fixtures) -> None:
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    app.dependency_overrides[api_deps.get_llm_client] = lambda: FakeLlm()
    _ask(client, seed.author_a_sub, project_id, "Halo")
    messages = client.get(
        f"/api/v1/projects/{project_id}/chat", headers=auth(seed.author_a_sub)
    ).json()
    user_message = next(m for m in messages if m["role"] == "user")

    # Act
    resp = client.post(
        f"/api/v1/chat/messages/{user_message['id']}/continue", headers=auth(seed.author_a_sub)
    )

    # Assert
    assert resp.status_code == 422, resp.text


def test_continue_is_tenant_isolated(client, seed: Fixtures) -> None:
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    llm = FakeLlm(truncate_first_answer=True)
    app.dependency_overrides[api_deps.get_llm_client] = lambda: llm
    truncated = _ask(client, seed.author_a_sub, project_id, "Ceritakan").json()

    # Act -- another tenant's author reaches for it
    resp = client.post(
        f"/api/v1/chat/messages/{truncated['id']}/continue", headers=auth(seed.user_b_sub)
    )

    # Assert -- 404, never 403: existence must not leak across tenants
    assert resp.status_code == 404, resp.text
