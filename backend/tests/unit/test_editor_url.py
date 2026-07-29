"""T-1.2: the editor link must carry an identifier the slide engine can resolve.

`StudioPanel` built the URL from `Generation.id` — a Postgres UUID Presenton has never
seen — so "🎨 Editor" opened a 404 even once routing worked. The engine needs
`presenton_presentation_id`, which `_PUBLIC_PARAM_KEYS` deliberately strips from the
response and which no schema field exposes.

Resolved by composing the URL server-side: the client receives a capability it cannot
forge meaning from, the engine id stays an implementation detail, and changing the
engine's URL shape stays a backend-only edit.

The route shape is verified, not guessed: `app-path-routes-manifest.json` in the
published engine image maps `/(presentation-generator)/presentation/page` to a static
`/presentation`. There is no dynamic segment, so the id must be a query parameter.
"""

from __future__ import annotations

import uuid

import pytest

from src.api.generations import _editor_url
from src.models import Generation, GenerationStatus


def _generation(presenton_id: str | None) -> Generation:
    return Generation(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        status=GenerationStatus.ready,
        presenton_presentation_id=presenton_id,
        params={},
        source_ids=[],
    )


def test_url_uses_the_engine_id_not_the_generation_id() -> None:
    # Arrange
    generation = _generation("pres_abc123")

    # Act
    url = _editor_url(generation)

    # Assert -- the whole defect was sending the wrong one of these
    assert "pres_abc123" in url
    assert str(generation.id) not in url


def test_url_is_same_origin_under_the_editor_prefix() -> None:
    # Act
    url = _editor_url(_generation("pres_abc123"))

    # Assert
    assert url.startswith("/editor/")
    assert "://" not in url, "must stay same-origin; no scheme or host"


def test_the_id_is_a_query_parameter_not_a_path_segment() -> None:
    """`/presentation` is a static route in the engine — `/presentation/{id}` is a 404."""
    # Act
    url = _editor_url(_generation("pres_abc123"))

    # Assert
    assert url == "/editor/presentation?id=pres_abc123"


def test_no_url_when_the_engine_has_produced_nothing() -> None:
    """A queued or failed generation has no presentation to open; the button hides."""
    # Act / Assert
    assert _editor_url(_generation(None)) is None


@pytest.mark.parametrize("raw", ["pres/with/slashes", "pres?with=query", "pres with spaces"])
def test_engine_ids_are_url_encoded(raw: str) -> None:
    """A raw id with reserved characters would otherwise corrupt the query string."""
    # Act
    url = _editor_url(_generation(raw))

    # Assert
    assert url is not None
    assert " " not in url
    assert url.count("?") == 1, url


# The complementary invariant -- `presenton_presentation_id` never appearing in an
# API response -- is asserted end to end in
# tests/integration/test_generation.py::test_full_pipeline_to_ready_and_download,
# which already has the engine fakes wired. Not duplicated here.
