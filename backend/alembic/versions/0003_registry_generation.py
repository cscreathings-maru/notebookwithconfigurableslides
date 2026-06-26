"""registry (template, stakeholder_profile) + generation provenance

Revision ID: 0003_registry_generation
Revises: 0002_project_source
Create Date: 2026-06-20
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_registry_generation"
down_revision: Union[str, None] = "0002_project_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_REG_STATUS = ("draft", "approved", "archived")
_TONE = ("default", "casual", "professional", "funny", "educational", "sales_pitch")
_VERBOSITY = ("concise", "standard", "text-heavy")
_GEN_STATUS = (
    "queued",
    "analyzing",
    "building_outline",
    "generating",
    "validating",
    "ready",
    "failed",
)


def upgrade() -> None:
    op.create_table(
        "template",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("logical_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("presenton_template_ref", sa.String(length=255), nullable=True),
        sa.Column("source_pptx_uri", sa.String(length=1024), nullable=True),
        sa.Column("brand_tokens", sa.JSON(), nullable=False),
        sa.Column("status", sa.Enum(*_REG_STATUS, name="template_status"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "logical_id", "version", name="uq_template_version"),
    )
    op.create_index("ix_template_tenant_id", "template", ["tenant_id"])
    op.create_index("ix_template_logical_id", "template", ["logical_id"])

    op.create_table(
        "stakeholder_profile",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("logical_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("audience", sa.String(length=1000), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("tone", sa.Enum(*_TONE, name="profile_tone"), nullable=False),
        sa.Column("verbosity", sa.Enum(*_VERBOSITY, name="profile_verbosity"), nullable=False),
        sa.Column("slide_min", sa.Integer(), nullable=False),
        sa.Column("slide_max", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("section_structure", sa.JSON(), nullable=False),
        sa.Column("prompt_config", sa.JSON(), nullable=False),
        sa.Column("status", sa.Enum(*_REG_STATUS, name="profile_status"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "logical_id", "version", name="uq_profile_version"),
    )
    op.create_index("ix_profile_tenant_id", "stakeholder_profile", ["tenant_id"])
    op.create_index("ix_profile_logical_id", "stakeholder_profile", ["logical_id"])

    op.create_table(
        "generation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("project.id"), nullable=True),
        sa.Column("outline_id", sa.Uuid(), nullable=True),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("provider", sa.String(length=128), nullable=True),
        sa.Column("status", sa.Enum(*_GEN_STATUS, name="generation_status"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_generation_tenant_id", "generation", ["tenant_id"])
    op.create_index("ix_generation_profile_id", "generation", ["profile_id"])
    op.create_index("ix_generation_template_id", "generation", ["template_id"])


def downgrade() -> None:
    op.drop_table("generation")
    op.drop_table("stakeholder_profile")
    op.drop_table("template")
    for enum_name in (
        "generation_status",
        "profile_status",
        "profile_verbosity",
        "profile_tone",
        "template_status",
    ):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
