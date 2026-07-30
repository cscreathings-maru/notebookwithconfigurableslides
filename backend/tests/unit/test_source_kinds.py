"""The engine routes on Content-Type, so uploads must be stored under the real one.

Sources reach Open Notebook as a presigned object-store URL. Every upload was stored as
`application/octet-stream`, so the engine's extractor had nothing to route on. A text file
could still be sniffed from its bytes; a binary OFFICE file was rejected with:

    "Could not extract content from this source. The URL or file may be unreachable,
     invalid, or in an unsupported format."   ...   started_at: null

`started_at: null` is the tell — processing never began, so this was never a corrupt file
or a crashed extractor. The router simply had no usable format signal.
"""

from __future__ import annotations

import pytest

from src.ingestion.kinds import (
    content_type_for_filename,
    is_supported_upload,
    kind_for_filename,
    supported_extensions,
)
from src.models import SourceKind


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("report.pdf", "application/pdf"),
        ("notes.txt", "text/plain"),
        ("00-overview.md", "text/markdown"),
        ("data.csv", "text/csv"),
    ],
)
def test_text_and_pdf_types_are_named(filename: str, expected: str) -> None:
    assert content_type_for_filename(filename) == expected


@pytest.mark.parametrize(
    ("filename", "fragment"),
    [
        ("Panduan Onboarding.docx", "wordprocessingml.document"),
        ("Template Presentasi BRI.pptx", "presentationml.presentation"),
        ("budget.xlsx", "spreadsheetml.sheet"),
        ("legacy.doc", "msword"),
        ("legacy.ppt", "ms-powerpoint"),
        ("legacy.xls", "ms-excel"),
    ],
)
def test_office_types_are_never_octet_stream(filename: str, fragment: str) -> None:
    """This is the case that failed in production."""
    content_type = content_type_for_filename(filename)

    assert fragment in content_type
    assert content_type != "application/octet-stream"


def test_an_unknown_extension_admits_it_rather_than_guessing() -> None:
    # Arrange / Act
    content_type = content_type_for_filename("mystery.qqq")

    # Assert -- claiming a type the bytes may not match would be worse than not knowing
    assert content_type == "application/octet-stream"


def test_extension_matching_is_case_insensitive() -> None:
    assert content_type_for_filename("REPORT.PDF") == "application/pdf"
    assert kind_for_filename("DECK.PPTX") is SourceKind.office


def test_a_filename_with_dots_uses_the_final_extension() -> None:
    assert content_type_for_filename("v1.2.final.pptx").endswith("presentationml.presentation")


@pytest.mark.parametrize("filename", ["a.pdf", "a.docx", "a.pptx", "a.md", "a.csv"])
def test_known_types_are_supported(filename: str) -> None:
    assert is_supported_upload(filename)


@pytest.mark.parametrize("filename", ["a.zip", "a.png", "a.mp4", "noextension"])
def test_unknown_types_are_rejected_before_a_job_is_enqueued(filename: str) -> None:
    """The engine cannot extract these, so failing at upload beats failing in a worker."""
    assert not is_supported_upload(filename)


def test_kind_and_content_type_come_from_one_table() -> None:
    """They cannot disagree: every supported extension yields both."""
    for ext in supported_extensions():
        name = f"file{ext}"
        assert is_supported_upload(name)
        assert content_type_for_filename(name) != "application/octet-stream"
        assert isinstance(kind_for_filename(name), SourceKind)


def test_the_supported_list_is_usable_in_an_error_message() -> None:
    extensions = supported_extensions()

    assert ".pptx" in extensions
    assert extensions == sorted(extensions), "sorted, so the message reads predictably"
