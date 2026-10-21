"""Task status and retry."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ...master_cv.store import MasterCvError
from ..deps import discovery_service, profile_service, task_store
from ..errors import ApiError

router = APIRouter(prefix="/api")


class RetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["all", "failed_sources"] | None = None
    source_ids: list[str] = Field(default_factory=list, max_length=50)


@router.get("/tasks/{task_id}")
def get_task(request: Request, task_id: str) -> dict:
    task = task_store(request).get(task_id)
    if task is None:
        raise ApiError(404, "not_found", "Task tidak ditemukan.", stage="server")
    return task


@router.post("/tasks/{task_id}/retry", status_code=202)
def retry_task(
    request: Request, task_id: str, body: RetryRequest | None = None
) -> dict:
    task = task_store(request).get(task_id)
    if task is None:
        raise ApiError(404, "not_found", "Task tidak ditemukan.", stage="server")
    payload = body or RetryRequest()

    if task["type"] == "discovery":
        try:
            run = discovery_service(request).retry(
                task_id,
                scope=payload.scope,
                source_ids=payload.source_ids or None,
            )
        except MasterCvError as exc:
            raise ApiError(
                exc.status_code,
                exc.code,
                exc.message,
                stage="fetch",
                active_task_id=exc.active_task_id,
            ) from exc
        return {
            "task_id": run["task_id"],
            "type": "discovery",
            "status": run["status"],
            "application_id": None,
            "run_id": run["run_id"],
            "extraction_run_id": None,
        }

    if payload.scope == "failed_sources":
        raise ApiError(
            400,
            "validation_failed",
            "scope failed_sources hanya berlaku untuk task discovery.",
            stage="validation",
            details=[
                {
                    "field": "scope",
                    "code": "retry_scope_unsupported",
                    "message": "Gunakan scope all untuk tipe task ini.",
                }
            ],
        )
    if task["status"] not in {"failed", "completed", "needs_review", "partial"}:
        raise ApiError(409, "task_not_finished", "Task belum selesai.", stage="server")
    if not task["retry"]["retryable"] and task["status"] == "failed":
        raise ApiError(409, "task_not_retryable", "Task tidak dapat diulang.", stage="server")
    if task["type"] != "profile_extraction":
        raise ApiError(409, "task_not_retryable", "Tipe task belum mendukung retry.", stage="server")
    try:
        new_task = profile_service(request).start_extraction()
    except MasterCvError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message, stage="extract") from exc
    return {
        "task_id": new_task["task_id"],
        "type": new_task["type"],
        "status": new_task["status"],
        "application_id": None,
        "run_id": None,
        "extraction_run_id": new_task["task_id"],
    }
