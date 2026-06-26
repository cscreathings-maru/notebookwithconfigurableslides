"""Map an uploaded filename to a SourceKind (best-effort; analysis confirms)."""

from __future__ import annotations

import os

from ..models import SourceKind

_EXT_MAP: dict[str, SourceKind] = {
    ".pdf": SourceKind.pdf,
    ".doc": SourceKind.office,
    ".docx": SourceKind.office,
    ".ppt": SourceKind.office,
    ".pptx": SourceKind.office,
    ".xls": SourceKind.office,
    ".xlsx": SourceKind.office,
    ".csv": SourceKind.csv,
    ".txt": SourceKind.text,
    ".md": SourceKind.text,
}


def kind_for_filename(filename: str) -> SourceKind:
    ext = os.path.splitext(filename.lower())[1]
    return _EXT_MAP.get(ext, SourceKind.text)
