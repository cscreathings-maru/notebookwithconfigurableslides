"""Map an uploaded filename to a SourceKind and a MIME type.

The MIME type matters as much as the kind. Sources reach Open Notebook as a presigned
object-store URL, so the engine's only clue about the format is the `Content-Type` header
the store serves. Uploading everything as `application/octet-stream` left the engine's
extractor nothing to route on: a text file could still be sniffed from its bytes, but a
binary OFFICE file was rejected with "Could not extract content ... unsupported format"
and `started_at: null` — processing never began.
"""

from __future__ import annotations

import os

from ..models import SourceKind

_OCTET_STREAM = "application/octet-stream"

# extension -> (kind, mime). One table, so the two can never disagree.
_EXT_MAP: dict[str, tuple[SourceKind, str]] = {
    ".pdf": (SourceKind.pdf, "application/pdf"),
    ".doc": (SourceKind.office, "application/msword"),
    ".docx": (
        SourceKind.office,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    ".ppt": (SourceKind.office, "application/vnd.ms-powerpoint"),
    ".pptx": (
        SourceKind.office,
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
    ".xls": (SourceKind.office, "application/vnd.ms-excel"),
    ".xlsx": (
        SourceKind.office,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    ".csv": (SourceKind.csv, "text/csv"),
    ".txt": (SourceKind.text, "text/plain"),
    ".md": (SourceKind.text, "text/markdown"),
}


def _extension(filename: str) -> str:
    return os.path.splitext(filename.lower())[1]


def kind_for_filename(filename: str) -> SourceKind:
    """Best-effort kind from the extension; analysis confirms the real content."""
    entry = _EXT_MAP.get(_extension(filename))
    return entry[0] if entry else SourceKind.text


def content_type_for_filename(filename: str) -> str:
    """MIME type to store the object under, so the engine can route on it.

    Falls back to `application/octet-stream` for unknown extensions — honest about not
    knowing, rather than guessing a type the bytes may not match.
    """
    entry = _EXT_MAP.get(_extension(filename))
    return entry[1] if entry else _OCTET_STREAM


def is_supported_upload(filename: str) -> bool:
    """Whether the analysis engine can be expected to extract this file.

    The engine rejects unextractable *uploads* with 415 up front — a guard it added
    specifically to avoid a background job that fails and then burns the retry budget
    behind a generic error. We hand it a URL instead, so that guard never runs for us
    and the equivalent check has to live here.
    """
    return _extension(filename) in _EXT_MAP


def supported_extensions() -> list[str]:
    """Sorted, for error messages that tell the user what would work."""
    return sorted(_EXT_MAP)
