"""Tenant BYOK config schemas. The secret api_key is write-only — never returned."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LlmConfigUpdate(BaseModel):
    provider: str = Field(..., examples=["deepseek"])
    base_url: str = Field(..., examples=["https://api.deepseek.com/v1"])
    model: str = Field(..., examples=["deepseek-chat"])
    api_key: str = Field(..., min_length=1, description="Write-only; stored encrypted.")


class LlmConfigPublic(BaseModel):
    """Non-secret view safe to render to an admin."""

    provider: str | None = None
    base_url: str | None = None
    model: str | None = None
