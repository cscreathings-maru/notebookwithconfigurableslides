"""Shared response envelopes."""

from __future__ import annotations

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """The single error shape for the whole API: { "error": { code, message } }."""

    error: ErrorBody
