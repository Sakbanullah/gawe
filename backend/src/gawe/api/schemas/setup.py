"""Request models for the setup routes. Shapes mirror the approved OpenAPI."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str | None = Field(default=None, pattern="^(en|id)$")


class CorrectionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=200)
    value: Any = None
    reason: str | None = Field(default=None, max_length=2000)


class CorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    corrections: list[CorrectionItem] = Field(min_length=1, max_length=100)


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=2000)


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_profile_version_id: str = Field(min_length=1)
    reason: str = Field(min_length=3, max_length=2000)
