"""`/api/settings/sources`: user-managed source registry."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ...jobs.sources.registry import SourceError, SourceRegistry
from ..errors import ApiError

router = APIRouter(prefix="/api/settings/sources")

Market = Literal["indonesia", "global"]
# `html` and `manual_url` are gone from the request contract: no adapter can
# fetch them, and offering the option promised a run that always skipped.
AccessMethod = Literal["ats_api", "aggregator"]
Ats = Literal["greenhouse", "lever", "ashby", "himalayas", "unknown"]
Verification = Literal["unverified", "verified", "restricted", "broken"]
Health = Literal["unknown", "healthy", "degraded", "broken"]


class SourceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str = Field(min_length=1, max_length=200)
    market: Market
    careers_url: str = Field(min_length=1, max_length=2048)
    access_method: AccessMethod
    ats: Ats
    tos_notes: str | None = Field(default=None, max_length=2000)
    enabled: bool = False
    priority_order: int = Field(default=100, ge=1, le=1000)
    fetch_interval_minutes: int = Field(default=360, ge=5, le=43200)
    daily_request_quota: int = Field(default=24, ge=0, le=100_000)


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
    priority_order: int | None = Field(default=None, ge=1, le=1000)
    fetch_interval_minutes: int | None = Field(default=None, ge=5, le=43200)
    daily_request_quota: int | None = Field(default=None, ge=0, le=100_000)


def _api_error(exc: SourceError) -> ApiError:
    return ApiError(
        exc.status_code, exc.code, exc.message, stage="validation", details=exc.details
    )


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


@router.get("/health")
def source_health(request: Request) -> dict:
    """One row per source: health, failure streak, next slot, and quota use."""
    items, _ = SourceRegistry(request.state.db).list(limit=200)
    return {
        "items": [
            {
                "source_id": item["source_id"],
                "company": item["company"],
                "enabled": item["enabled"],
                "verification_status": item["verification_status"],
                "health_status": item["health_status"],
                "consecutive_failures": item["consecutive_failures"],
                "last_error_code": item["last_error_code"],
                "last_checked_at": item["last_checked_at"],
                "last_success_at": item["last_success_at"],
                "next_run_at": item["next_run_at"],
                "fetch_interval_minutes": item["fetch_interval_minutes"],
                "daily_request_quota": item["daily_request_quota"],
                "requests_last_24h": item["requests_last_24h"],
                "stale": item["stale"],
            }
            for item in items
        ]
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
