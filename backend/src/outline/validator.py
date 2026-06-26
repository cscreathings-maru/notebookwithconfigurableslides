"""Outline validation + repair.

validate_outline parses the schema and enforces semantic invariants (unique section
ids, sequential order, cross-refs resolve). repair_outline best-effort coerces a raw
outline back onto a required section structure (the profile's contract) so minor LLM
drift becomes a valid, deterministic outline instead of a hard failure.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError as PydValidationError

from .schema import OUTLINE_SCHEMA_VERSION, OutlineContent


def validate_outline(raw: dict[str, Any]) -> tuple[OutlineContent | None, list[str]]:
    """Return (model, []) if valid, else (None, [errors])."""
    try:
        content = OutlineContent.model_validate(raw)
    except PydValidationError as exc:
        return None, [f"{e['loc']}: {e['msg']}" for e in exc.errors()]

    errors: list[str] = []
    ids = [s.id for s in content.sections]
    if len(ids) != len(set(ids)):
        errors.append("section ids must be unique")
    if [s.order for s in content.sections] != sorted(s.order for s in content.sections):
        errors.append("sections must be ordered by `order`")
    id_set = set(ids)
    for tp in content.talking_points:
        if tp.section_id not in id_set:
            errors.append(f"talking_point references unknown section '{tp.section_id}'")
    for db in content.data_bindings:
        if db.section_id not in id_set:
            errors.append(f"data_binding references unknown section '{db.section_id}'")
    if not content.sections:
        errors.append("outline must have at least one section")

    if errors:
        return None, errors
    return content, []


def repair_outline(raw: dict[str, Any], required_titles: list[str]) -> dict[str, Any]:
    """Coerce a raw outline onto the required section structure (in order).

    Sections are rebuilt from `required_titles` (the profile's pinned contract);
    talking points/data bindings are kept only if they map to a surviving section
    (matched by id or by section title). This is what makes structure deterministic.
    """
    from .builder import slugify  # local import to avoid a cycle

    sections = [
        {"id": slugify(title), "title": title, "order": index}
        for index, title in enumerate(required_titles)
    ]
    valid_ids = {s["id"] for s in sections}
    title_to_id = {s["title"]: s["id"] for s in sections}

    def _remap(section_ref: str) -> str | None:
        if section_ref in valid_ids:
            return section_ref
        return title_to_id.get(section_ref)

    kept_points = []
    for tp in raw.get("talking_points", []) or []:
        sid = _remap(str(tp.get("section_id", "")))
        if sid and tp.get("text"):
            kept_points.append({"section_id": sid, "text": tp["text"]})

    kept_bindings = []
    for db in raw.get("data_bindings", []) or []:
        sid = _remap(str(db.get("section_id", "")))
        if sid and db.get("key"):
            kept_bindings.append(
                {"section_id": sid, "key": db["key"], "source_ref": db.get("source_ref")}
            )

    return {
        "schema_version": raw.get("schema_version") or OUTLINE_SCHEMA_VERSION,
        "sections": sections,
        "talking_points": kept_points,
        "data_bindings": kept_bindings,
    }
