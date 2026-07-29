"""T-1.2 (second surface): the template preview link needs the ENGINE's template id.

The templates page built `/editor/template-preview?id=${tpl.id}` from `Template.logical_id`
— a Postgres UUID Presenton has never seen — so the preview rendered
"Error loading template / Template not found". That is the same defect T-1.2 fixed for
the generation deep link, on a surface the fix did not cover.

Composed server-side for the same reason: the engine ref stays an implementation detail
and the client receives a URL it cannot forge meaning from.
"""

from __future__ import annotations

import uuid

import pytest

from src.api.templates import _preview_url
from src.models import RegistrationStatus, RegistryStatus, Template


def _template(ref: str | None) -> Template:
    return Template(
        logical_id=uuid.uuid4(),
        version=1,
        name="Acme Brand",
        presenton_template_ref=ref,
        brand_tokens={},
        status=RegistryStatus.draft,
        registration_status=(
            RegistrationStatus.registered if ref and ref != "default"
            else RegistrationStatus.fallback
        ),
    )


def test_url_uses_the_engine_ref_not_the_logical_id() -> None:
    # Arrange
    template = _template("template_abc123")

    # Act
    url = _preview_url(template)

    # Assert -- the whole defect was sending the wrong one of these
    assert url is not None
    assert "template_abc123" in url
    assert str(template.logical_id) not in url


def test_url_is_same_origin_under_the_editor_prefix() -> None:
    # Act
    url = _preview_url(_template("template_abc123"))

    # Assert
    assert url == "/editor/template-preview?id=template_abc123"
    assert "://" not in url


def test_no_url_when_registration_fell_back() -> None:
    """"default" is not a real engine template; previewing it shows layouts the user
    never uploaded, which is worse than hiding the button."""
    # Act / Assert
    assert _preview_url(_template("default")) is None


def test_no_url_when_the_engine_issued_no_ref() -> None:
    # Act / Assert
    assert _preview_url(_template(None)) is None


@pytest.mark.parametrize("raw", ["ref/with/slashes", "ref with spaces", "ref?x=1"])
def test_engine_refs_are_url_encoded(raw: str) -> None:
    # Act
    url = _preview_url(_template(raw))

    # Assert
    assert url is not None
    assert " " not in url
    assert url.count("?") == 1, url
