"""The Outline contract — a validated structure that drives deterministic generation.

Outline = { schema_version, sections[], talking_points[], data_bindings[] }. Sections
are the fixed structure (order matters); talking_points and data_bindings reference
sections by id. This schema is the consistency contract: the LLM fills wording, never
the structure.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

OUTLINE_SCHEMA_VERSION = "1.0"


class OutlineSection(BaseModel):
    id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    order: int = Field(..., ge=0)


class TalkingPoint(BaseModel):
    section_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)


class DataBinding(BaseModel):
    section_id: str = Field(..., min_length=1)
    key: str = Field(..., min_length=1)
    source_ref: str | None = None


class OutlineContent(BaseModel):
    schema_version: str = OUTLINE_SCHEMA_VERSION
    sections: list[OutlineSection] = Field(default_factory=list)
    talking_points: list[TalkingPoint] = Field(default_factory=list)
    data_bindings: list[DataBinding] = Field(default_factory=list)
