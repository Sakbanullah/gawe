"""`/api/applications/{id}/exports`: list, create, download (API-CONTRACTS §2.7).

Export only accepts an approved version whose hash still matches the approval.
A failed compile yields `tex_only` or `failed`, never `exported`.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from ...services.export_service import ExportError, ExportService
from ..errors import ApiError

router = APIRouter(prefix="/api/applications")


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["cv", "cover_letter"]
    document_version_id: str = Field(min_length=1, max_length=64)
    content_hash: str = Field(min_length=1, max_length=128)
    filename: str | None = Field(default=None, max_length=255)


def _service(request: Request) -> ExportService:
    return ExportService(request.state.db, request.app.state.config.data_dir)


def _raise(exc: ExportError, stage: str) -> None:
    raise ApiError(
        exc.status_code,
        exc.code,
        exc.message,
        stage=stage,
        details=exc.details,
        active_task_id=exc.active_task_id,
    ) from exc


@router.get("/{application_id}/exports")
def list_exports(
    request: Request, application_id: str, limit: int = 50, cursor: str | None = None
) -> dict:
    if not 1 <= limit <= 200:
        raise ApiError(
            400,
            "validation_failed",
            "limit harus 1-200.",
            stage="validation",
            details=[{"field": "limit", "code": "out_of_range", "message": "limit harus 1-200."}],
        )
    try:
        items, next_cursor = _service(request).list(application_id, limit=limit, cursor=cursor)
    except ExportError as exc:
        _raise(exc, "validation")
    return {
        "application_id": application_id,
        "items": items,
        "page": {"limit": limit, "next_cursor": next_cursor, "has_more": next_cursor is not None},
    }


@router.post("/{application_id}/exports", status_code=202)
def create_export(request: Request, application_id: str, body: ExportRequest) -> dict:
    try:
        task = _service(request).create(
            application_id,
            body.document_version_id,
            kind=body.kind,
            content_hash=body.content_hash,
            filename=body.filename,
        )
    except ExportError as exc:
        _raise(exc, "export")
    return {
        "task_id": task["task_id"],
        "type": task["type"],
        "status": task["status"],
        "application_id": application_id,
        "run_id": None,
        "extraction_run_id": None,
    }


@router.get("/{application_id}/exports/{export_id}/download")
def download_export(request: Request, application_id: str, export_id: str):
    service = _service(request)
    try:
        record = service.get(application_id, export_id)
        path = service.path_for(application_id, export_id)
    except ExportError as exc:
        _raise(exc, "export")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=record["filename"],
        headers={"X-Content-Type-Options": "nosniff"},
    )
