"""`/api/discovery`: manual discovery runs and per-source status."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ...jobs.sources.registry import SourceError
from ...master_cv.store import MasterCvError
from ..deps import discovery_service
from ..errors import ApiError

router = APIRouter(prefix="/api/discovery")


class DiscoveryRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ids: list[str] = Field(default_factory=list, max_length=200)
    profile_version_id: str | None = None


@router.get("/runs")
def list_discovery_runs(
    request: Request, limit: int = 50, cursor: str | None = None
) -> dict:
    if not 1 <= limit <= 200:
        raise ApiError(
            400,
            "validation_failed",
            "limit harus 1-200.",
            stage="validation",
            details=[{"field": "limit", "code": "out_of_range", "message": "1-200"}],
        )
    items, next_cursor = discovery_service(request).list_runs(limit=limit, cursor=cursor)
    return {
        "items": items,
        "page": {"limit": limit, "next_cursor": next_cursor, "has_more": next_cursor is not None},
    }


@router.post("/runs", status_code=202)
def start_discovery_run(request: Request, body: DiscoveryRunCreateRequest | None = None) -> dict:
    payload = body or DiscoveryRunCreateRequest()
    try:
        run = discovery_service(request).start_run(
            source_ids=payload.source_ids or None,
            profile_version_id=payload.profile_version_id,
        )
    except (MasterCvError, SourceError) as exc:
        raise ApiError(exc.status_code, exc.code, exc.message, stage="fetch") from exc
    return {
        "task_id": run["task_id"],
        "type": "discovery",
        "status": run["status"],
        "application_id": None,
        "run_id": run["run_id"],
        "extraction_run_id": None,
    }


@router.get("/runs/{run_id}")
def get_discovery_run(request: Request, run_id: str) -> dict:
    try:
        return discovery_service(request).get_run(run_id)
    except MasterCvError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message, stage="fetch") from exc
