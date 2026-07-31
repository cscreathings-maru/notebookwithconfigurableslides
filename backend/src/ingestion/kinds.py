"""Map an uploaded filename to a SourceKind and a MIME type.

The MIME type matters as much as the kind: it is stored on the object AND sent as the
multipart part's content type when the file is uploaded to Open Notebook, so the engine
can route to a document handler.

Sources used to reach the engine as a presigned object-store URL typed as "link". That
was the real cause of "Could not extract content ... unsupported format" with
`started_at: null` — the link path is a web-page extractor and never routes binaries,
whatever Content-Type the store serves. Files are uploaded directly now
(`OpenNotebookClient.add_source_file`).
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

    The engine rejects unextractable *uploads* with 415 up front. Now that files are
    uploaded rather than linked, that guard does run for us — but this check stays: it
    fails at request time, before an object is stored and a job enqueued, so the user
    learns immediately instead of watching a source sit in "queued".
    """
    return _extension(filename) in _EXT_MAP


def supported_extensions() -> list[str]:
    """Sorted, for error messages that tell the user what would work."""
    return sorted(_EXT_MAP)
