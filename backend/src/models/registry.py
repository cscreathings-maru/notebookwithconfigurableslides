"""Versioned registry models: StakeholderProfile and Template.

Versioning model: each row is one immutable version. A stable logical `id` is shared
across versions of the same profile/template; `version` increments on each edit.
A surrogate `row_id` is the physical PK so foreign keys and lookups stay simple.
Clients reference the logical `id`; "latest" is the max `version` for that id.

The stored PPTX key (source_pptx_uri) is never exposed to clients.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UuidPkMixin, utcnow


class RegistryStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    archived = "archived"


class TemplateCatalogStatus(str, enum.Enum):
    """Lifecycle of the LLM-produced `DesignCatalog` (LD-2/LD-3,
    `PLAN-LLM-DECK-PLANNING.md`) -- the ONLY read of a template's `.pptx` as
    of the Phase C cutover (LD-9/LD-11). Replaces `TemplateStatus`
    (`deck/inspect.py`'s geometric layout read), which classified a
    template's LAYOUTS; this classifies a template's SLIDES, which is where
    the assessment found the design actually lives
    (`ASSESSMENT-LLM-DECK-PLANNING.md` §1).

    - `no_source`: no PPTX uploaded, nothing to catalogue.
    - `cataloguing`: an LLM job is in flight (LD-3: an LLM call belongs in a
      job, not a request/response cycle -- there is no synchronous
      "inspect on upload" anymore).
    - `ready`: at least one usable design was catalogued. Rendering still
      additionally requires `catalog_reviewed_at is not None` (L3) --
      `ready` alone means the LLM produced something, not that a human has
      seen it.
    - `failed`: the job errored, or produced no usable design.
      `catalog_error` carries the reason.
    """

    no_source = "no_source"
    cataloguing = "cataloguing"
    ready = "ready"
    failed = "failed"


class Tone(str, enum.Enum):
    default = "default"
    casual = "casual"
    professional = "professional"
    funny = "funny"
    educational = "educational"
    sales_pitch = "sales_pitch"


class Verbosity(str, enum.Enum):
    concise = "concise"
    standard = "standard"
    text_heavy = "text-heavy"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class Template(UuidPkMixin, Base):
    """A company template version, catalogued by an LLM (LD-2/LD-3) -- no
    engine round trip, no geometric layout read."""

    __tablename__ = "template"
    __table_args__ = (
        UniqueConstraint("tenant_id", "logical_id", "version", name="uq_template_version"),
    )

    # row_id is `id` from UuidPkMixin (physical PK); logical_id is the stable id.
    logical_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenant.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_pptx_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    brand_tokens: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[RegistryStatus] = mapped_column(
        Enum(RegistryStatus, name="template_status"),
        default=RegistryStatus.draft,
        nullable=False,
    )

    # LD-3: `deck.catalog.DesignCatalog.model_dump(mode="json")` -- the LLM's
    # reading of this template's slides as a reusable design vocabulary.
    # Null until a cataloguing job has completed at least once.
    slide_catalog: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    catalog_status: Mapped[TemplateCatalogStatus] = mapped_column(
        Enum(TemplateCatalogStatus, name="template_catalog_status"),
        default=TemplateCatalogStatus.no_source,
        nullable=False,
    )
    catalog_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # LD-4/L3: set once an admin has reviewed (and optionally corrected) the
    # catalog. `review_catalog()` also approves `status` at the same time --
    # this IS the approval gate now (replaces the old "usable inspection
    # auto-approves"), since a catalog an admin has not seen is not yet
    # something a deck should be planned against.
    catalog_reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    catalog_reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)


class StakeholderProfile(UuidPkMixin, Base):
    """An audience profile version that drives consistent generation."""

    __tablename__ = "stakeholder_profile"
    __table_args__ = (
        UniqueConstraint("tenant_id", "logical_id", "version", name="uq_profile_version"),
    )

    logical_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenant.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    audience: Mapped[str] = mapped_column(String(1000), nullable=False)
    # Pinned template (logical id + version) for full provenance.
    template_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    tone: Mapped[Tone] = mapped_column(
        Enum(Tone, name="profile_tone", values_callable=_enum_values), nullable=False
    )
    verbosity: Mapped[Verbosity] = mapped_column(
        Enum(Verbosity, name="profile_verbosity", values_callable=_enum_values), nullable=False
    )
    slide_min: Mapped[int] = mapped_column(Integer, nullable=False)
    slide_max: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    section_structure: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    prompt_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[RegistryStatus] = mapped_column(
        Enum(RegistryStatus, name="profile_status"),
        default=RegistryStatus.draft,
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
