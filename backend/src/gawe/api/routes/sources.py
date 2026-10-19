"""`/api/settings/sources`: user-managed source registry."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ...jobs.sources.registry import SourceError, SourceRegistry
from ..errors import ApiError

router = APIRouter(prefix="/api/settings/sources")

Market = Literal["indonesia", "global"]
AccessMethod = Literal["ats_api", "html"]
Ats = Literal["greenhouse", "lever", "ashby", "unknown"]
Verification = Literal["unverified", "verified", "restricted", "broken"]


class SourceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str = Field(min_length=1, max_length=200)
    market: Market
    careers_url: str = Field(min_length=1, max_length=2048)
    access_method: AccessMethod
    ats: Ats
    tos_notes: str | None = Field(default=None, max_length=2000)
    enabled: bool = False


class SourceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str | None = Field(default=None, min_length=1, max_length=200)
    market: Market | None = None
    careers_url: str | None = Field(default=None, min_length=1, max_length=2048)
    access_method: AccessMethod | None = None
    ats: Ats | None = None
    verification_status: Verification | None = None
    tos_notes: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None


def _api_error(exc: SourceError) -> ApiError:
    return ApiError(exc.status_code, exc.code, exc.message, stage="validation")


@router.get("")
def list_sources(
    request: Request,
    limit: int = 50,
    cursor: str | None = None,
    enabled: bool | None = None,
    verification_status: Verification | None = None,
) -> dict:
    if not 1 <= limit <= 200:
        raise ApiError(
            400,
            "validation_failed",
            "limit harus 1-200.",
            stage="validation",
            details=[{"field": "limit", "code": "out_of_range", "message": "1-200"}],
        )
    items, next_cursor = SourceRegistry(request.state.db).list(
        limit=limit,
        cursor=cursor,
        enabled=enabled,
        verification_status=verification_status,
    )
    return {
        "items": items,
        "page": {"limit": limit, "next_cursor": next_cursor, "has_more": next_cursor is not None},
    }


@router.post("", status_code=201)
def create_source(request: Request, body: SourceCreateRequest) -> dict:
    try:
        return SourceRegistry(request.state.db).create(body.model_dump())
    except SourceError as exc:
        raise _api_error(exc) from exc


@router.get("/{source_id}")
def get_source(request: Request, source_id: str) -> dict:
    record = SourceRegistry(request.state.db).get(source_id)
    if record is None:
        raise ApiError(404, "not_found", "Sumber tidak ditemukan.", stage="validation")
    return record


@router.patch("/{source_id}")
def update_source(request: Request, source_id: str, body: SourceUpdateRequest) -> dict:
    try:
        return SourceRegistry(request.state.db).update(
            source_id, body.model_dump(exclude_unset=True)
        )
    except SourceError as exc:
        raise _api_error(exc) from exc
