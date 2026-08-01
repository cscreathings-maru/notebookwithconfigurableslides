"""Integration: multi-session chat over the HTTP stack (Phase C).

A project used to hold one implicit, unbounded thread — every question it had ever
been asked lived in one stream, so unrelated topics collided and the payload only
grew. Sessions split that, and these tests pin the behaviour that makes them safe:
requests without a session still work, a session id cannot reach across projects or
tenants, an explicit rename survives the next message, and delete is reversible.
"""

from __future__ import annotations

import uuid

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


@pytest.fixture
def llm() -> FakeLlm:
    return FakeLlm()


@pytest.fixture(autouse=True)
def _wire(on_client, llm):
    app.dependency_overrides[api_deps.get_open_notebook_client] = lambda: on_client
    app.dependency_overrides[api_deps.get_llm_client] = lambda: llm
    app.dependency_overrides[api_deps.get_object_store] = lambda: FakeObjectStore()
    yield
    app.dependency_overrides.clear()


def _set_byok(client, seed: Fixtures) -> None:
    resp = client.put("/api/v1/tenant/llm-config", json=PROVIDER, headers=auth(seed.admin_a_sub))
    assert resp.status_code == 200, resp.text


def _project(client, sub: str, name: str = "Onboarding") -> str:
    resp = client.post("/api/v1/projects", json={"name": name}, headers=auth(sub))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _ask(client, sub: str, project_id: str, question: str, session_id: str | None = None):
    body: dict = {"question": question}
    if session_id is not None:
        body["session_id"] = session_id
    return client.post(f"/api/v1/projects/{project_id}/chat", json=body, headers=auth(sub))


def test_asking_without_a_session_creates_and_reuses_one(client, seed: Fixtures) -> None:
    """The pre-Phase-C caller shape still works: no session_id, no error."""
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)

    # Act
    assert _ask(client, seed.author_a_sub, project_id, "Pertanyaan pertama").status_code == 200
    assert _ask(client, seed.author_a_sub, project_id, "Pertanyaan kedua").status_code == 200

    # Assert -- both turns landed in ONE session, not two
    sessions = client.get(
        f"/api/v1/projects/{project_id}/chat/sessions", headers=auth(seed.author_a_sub)
    ).json()
    assert len(sessions) == 1
    messages = client.get(
        f"/api/v1/projects/{project_id}/chat", headers=auth(seed.author_a_sub)
    ).json()
    assert len(messages) == 4  # two user turns + two assistant turns


def test_a_session_is_titled_from_its_opening_question(client, seed: Fixtures) -> None:
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)

    # Act
    _ask(client, seed.author_a_sub, project_id, "Apa syarat pendaftaran merchant?")

    # Assert
    sessions = client.get(
        f"/api/v1/projects/{project_id}/chat/sessions", headers=auth(seed.author_a_sub)
    ).json()
    assert sessions[0]["title"] == "Apa syarat pendaftaran merchant?"


def test_a_rename_survives_the_next_message(client, seed: Fixtures) -> None:
    """Auto-titling must never overwrite a title the user chose."""
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    created = client.post(
        f"/api/v1/projects/{project_id}/chat/sessions",
        json={"title": None},
        headers=auth(seed.author_a_sub),
    ).json()
    renamed = client.patch(
        f"/api/v1/chat/sessions/{created['id']}",
        json={"title": "Riset kompetitor"},
        headers=auth(seed.author_a_sub),
    )
    assert renamed.status_code == 200

    # Act
    _ask(client, seed.author_a_sub, project_id, "Pertanyaan yang sama sekali berbeda", created["id"])

    # Assert
    sessions = client.get(
        f"/api/v1/projects/{project_id}/chat/sessions", headers=auth(seed.author_a_sub)
    ).json()
    assert sessions[0]["title"] == "Riset kompetitor"


def test_sessions_keep_separate_threads(client, seed: Fixtures) -> None:
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    a = client.post(
        f"/api/v1/projects/{project_id}/chat/sessions", json={}, headers=auth(seed.author_a_sub)
    ).json()
    b = client.post(
        f"/api/v1/projects/{project_id}/chat/sessions", json={}, headers=auth(seed.author_a_sub)
    ).json()

    # Act
    _ask(client, seed.author_a_sub, project_id, "Topik A", a["id"])
    _ask(client, seed.author_a_sub, project_id, "Topik B", b["id"])

    # Assert -- each thread sees only its own turns
    in_a = client.get(
        f"/api/v1/projects/{project_id}/chat?session_id={a['id']}", headers=auth(seed.author_a_sub)
    ).json()
    in_b = client.get(
        f"/api/v1/projects/{project_id}/chat?session_id={b['id']}", headers=auth(seed.author_a_sub)
    ).json()
    assert [m["content"] for m in in_a if m["role"] == "user"] == ["Topik A"]
    assert [m["content"] for m in in_b if m["role"] == "user"] == ["Topik B"]


def test_a_session_from_another_project_is_rejected(client, seed: Fixtures) -> None:
    """Scoping is per project, not just per tenant — same-tenant leakage counts too."""
    # Arrange
    _set_byok(client, seed)
    first = _project(client, seed.author_a_sub, "First")
    second = _project(client, seed.author_a_sub, "Second")
    session = client.post(
        f"/api/v1/projects/{first}/chat/sessions", json={}, headers=auth(seed.author_a_sub)
    ).json()

    # Act -- try to write into `first`'s session through `second`
    resp = _ask(client, seed.author_a_sub, second, "Pertanyaan", session["id"])

    # Assert -- 422 is this codebase's ValidationError mapping (core/errors.py)
    assert resp.status_code == 422, resp.text
    assert "another project" in resp.text


def test_sessions_are_tenant_isolated(client, seed: Fixtures) -> None:
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    session = client.post(
        f"/api/v1/projects/{project_id}/chat/sessions", json={}, headers=auth(seed.author_a_sub)
    ).json()

    # Act -- another tenant's author reaches for it
    resp = client.patch(
        f"/api/v1/chat/sessions/{session['id']}",
        json={"title": "stolen"},
        headers=auth(seed.user_b_sub),
    )

    # Assert -- 404, never 403: existence must not leak across tenants
    assert resp.status_code == 404, resp.text


def test_delete_is_reversible_and_keeps_the_messages(client, seed: Fixtures) -> None:
    """Undo has to restore the thread, not just the row — otherwise it is a lie."""
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    _ask(client, seed.author_a_sub, project_id, "Pertanyaan penting")
    session = client.get(
        f"/api/v1/projects/{project_id}/chat/sessions", headers=auth(seed.author_a_sub)
    ).json()[0]

    # Act -- delete, then undo
    assert client.delete(
        f"/api/v1/chat/sessions/{session['id']}", headers=auth(seed.author_a_sub)
    ).status_code == 200
    hidden = client.get(
        f"/api/v1/projects/{project_id}/chat/sessions", headers=auth(seed.author_a_sub)
    ).json()
    assert hidden == []

    restored = client.post(
        f"/api/v1/chat/sessions/{session['id']}/restore", headers=auth(seed.author_a_sub)
    )

    # Assert -- back in the list WITH its turns intact
    assert restored.status_code == 200
    listed = client.get(
        f"/api/v1/projects/{project_id}/chat/sessions", headers=auth(seed.author_a_sub)
    ).json()
    assert [s["id"] for s in listed] == [session["id"]]
    messages = client.get(
        f"/api/v1/projects/{project_id}/chat?session_id={session['id']}",
        headers=auth(seed.author_a_sub),
    ).json()
    assert any(m["content"] == "Pertanyaan penting" for m in messages)


def test_message_list_is_windowed(client, seed: Fixtures) -> None:
    """The old endpoint returned every message ever; the new one pages."""
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    for i in range(4):
        _ask(client, seed.author_a_sub, project_id, f"Pertanyaan {i}")

    # Act -- ask for the newest 3 of 8 turns
    page = client.get(
        f"/api/v1/projects/{project_id}/chat?limit=3", headers=auth(seed.author_a_sub)
    ).json()

    # Assert -- newest window, still oldest-first for display
    assert len(page) == 3
    timestamps = [m["created_at"] for m in page]
    assert timestamps == sorted(timestamps)
    assert page[-1]["role"] == "assistant"


def test_older_turns_load_through_the_before_cursor(client, seed: Fixtures) -> None:
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    for i in range(3):
        _ask(client, seed.author_a_sub, project_id, f"Pertanyaan {i}")
    newest = client.get(
        f"/api/v1/projects/{project_id}/chat?limit=2", headers=auth(seed.author_a_sub)
    ).json()

    # Act
    older = client.get(
        f"/api/v1/projects/{project_id}/chat?limit=10&before={newest[0]['created_at']}",
        headers=auth(seed.author_a_sub),
    ).json()

    # Assert -- strictly older, no overlap with the page we already have
    assert older, "the cursor must reach earlier turns"
    assert {m["id"] for m in older}.isdisjoint({m["id"] for m in newest})
    assert all(m["created_at"] < newest[0]["created_at"] for m in older)


def test_a_viewer_can_read_sessions_but_not_change_them(client, seed: Fixtures) -> None:
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)

    # Act / Assert -- read allowed
    assert client.get(
        f"/api/v1/projects/{project_id}/chat/sessions", headers=auth(seed.viewer_a_sub)
    ).status_code == 200
    # Write refused
    assert client.post(
        f"/api/v1/projects/{project_id}/chat/sessions", json={}, headers=auth(seed.viewer_a_sub)
    ).status_code == 403


def test_renaming_to_blank_is_rejected(client, seed: Fixtures) -> None:
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)
    session = client.post(
        f"/api/v1/projects/{project_id}/chat/sessions", json={}, headers=auth(seed.author_a_sub)
    ).json()

    # Act
    resp = client.patch(
        f"/api/v1/chat/sessions/{session['id']}",
        json={"title": "   "},
        headers=auth(seed.author_a_sub),
    )

    # Assert
    assert resp.status_code in (400, 422), resp.text


def test_an_unknown_session_id_is_not_found(client, seed: Fixtures) -> None:
    # Arrange
    _set_byok(client, seed)
    project_id = _project(client, seed.author_a_sub)

    # Act
    resp = _ask(client, seed.author_a_sub, project_id, "Halo", str(uuid.uuid4()))

    # Assert
    assert resp.status_code == 404, resp.text
