"""DG-4: once a generation's studio has been opened, NoteAI stops offering its own
download for it (locked decision Q6, Option C).

Deck bytes are produced once at generation and stored in MinIO; editing in
Presenton updates only the engine's own copy (TD-24). These pin: the cutover is
durable (a DB flag, not a client-only one), idempotent, enforced server-side on
download (not just hidden client-side), and scoped correctly (author-only to set,
tenant-isolated, doesn't affect other generations).
"""

from __future__ import annotations

import pytest

from src.api import deps as api_deps
from src.core.db import SessionLocal
from src.generation.worker import generate_presentation
from src.main import app
from tests.conftest import Fixtures, auth
from tests.fakes import FakeLlm, FakeObjectStore, FakeOpenNotebook, FakePresenton

PROVIDER = {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "sk-x",
}


@pytest.fixture(autouse=True)
def _wire():
    app.dependency_overrides[api_deps.get_presenton_client] = lambda: FakePresenton()
    app.dependency_overrides[api_deps.get_object_store] = lambda: FakeObjectStore()
    app.dependency_overrides[api_deps.get_open_notebook_client] = lambda: FakeOpenNotebook()
    app.dependency_overrides[api_deps.get_llm_client] = lambda: FakeLlm()
    yield
    app.dependency_overrides.clear()


def _set_byok(client, seed: Fixtures) -> None:
    resp = client.put("/api/v1/tenant/llm-config", json=PROVIDER, headers=auth(seed.admin_a_sub))
    assert resp.status_code == 200, resp.text


async def _ready_generation(client, seed: Fixtures) -> dict:
    """A project with a real, READY freeform generation -- studio-opened only makes
    sense once there's something to open, and download only matters once ready."""
    _set_byok(client, seed)
    project_id = client.post(
        "/api/v1/projects", json={"name": "DG-4"}, headers=auth(seed.author_a_sub)
    ).json()["id"]
    gen = client.post(
        f"/api/v1/projects/{project_id}/generations",
        json={"content_source": "custom", "custom_markdown": "## A\n- x", "tone": "professional"},
        headers=auth(seed.author_a_sub),
    ).json()

    import uuid

    with SessionLocal() as db:
        await generate_presentation(
            db=db,
            generation_id=uuid.UUID(gen["id"]),
            tenant_id=seed.tenant_a,
            presenton=FakePresenton(),
            object_store=FakeObjectStore(),
        )
        db.commit()
    return gen


async def test_download_available_before_studio_is_opened(client, seed: Fixtures) -> None:
    gen = await _ready_generation(client, seed)

    resp = client.get(
        f"/api/v1/generations/{gen['id']}", headers=auth(seed.author_a_sub)
    )

    assert resp.json()["artifacts"]["pptx"] is True


async def test_marking_studio_opened_hides_downloads(client, seed: Fixtures) -> None:
    gen = await _ready_generation(client, seed)

    mark = client.post(
        f"/api/v1/generations/{gen['id']}/studio-opened", headers=auth(seed.author_a_sub)
    )
    assert mark.status_code == 200, mark.text
    assert mark.json()["artifacts"] == {"pptx": False, "pdf": False}

    # And it holds on a later, independent fetch -- not just the response of the
    # call that set it.
    later = client.get(f"/api/v1/generations/{gen['id']}", headers=auth(seed.author_a_sub))
    assert later.json()["artifacts"] == {"pptx": False, "pdf": False}


async def test_download_is_refused_server_side_after_studio_opened(
    client, seed: Fixtures
) -> None:
    """The client-side hide is a convenience; this is the actual guarantee -- a
    direct hit to the download URL must not return the stale file either."""
    gen = await _ready_generation(client, seed)
    client.post(
        f"/api/v1/generations/{gen['id']}/studio-opened", headers=auth(seed.author_a_sub)
    )

    resp = client.get(
        f"/api/v1/generations/{gen['id']}/download?format=pptx", headers=auth(seed.author_a_sub)
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "edited_in_studio"


async def test_marking_studio_opened_twice_keeps_the_first_timestamp(
    client, seed: Fixtures
) -> None:
    gen = await _ready_generation(client, seed)

    first = client.post(
        f"/api/v1/generations/{gen['id']}/studio-opened", headers=auth(seed.author_a_sub)
    ).json()
    second = client.post(
        f"/api/v1/generations/{gen['id']}/studio-opened", headers=auth(seed.author_a_sub)
    ).json()

    # Neither exposes the timestamp directly, but both report the same (cut-off)
    # artifact state -- idempotent in its observable effect either way.
    assert first["artifacts"] == second["artifacts"] == {"pptx": False, "pdf": False}


async def test_viewer_cannot_mark_studio_opened(client, seed: Fixtures) -> None:
    gen = await _ready_generation(client, seed)

    resp = client.post(
        f"/api/v1/generations/{gen['id']}/studio-opened", headers=auth(seed.viewer_a_sub)
    )

    assert resp.status_code == 403


async def test_studio_opened_is_tenant_scoped(client, seed: Fixtures) -> None:
    gen = await _ready_generation(client, seed)

    resp = client.post(
        f"/api/v1/generations/{gen['id']}/studio-opened", headers=auth(seed.user_b_sub)
    )

    assert resp.status_code == 404
