"""`/api/applications/{id}/documents`: versions, revisions, review, approval.

Phase 3D slice. LaTeX/PDF and export endpoints stay unimplemented while D6 is
OPEN; nothing here claims a PDF exists.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...services.document_service import DocumentError, DocumentService
from ..deps import profile_store
from ..errors import ApiError

router = APIRouter(prefix="/api/applications")


class GenerateDocumentsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kinds: list[Literal["cv", "cover_letter"]] = Field(min_length=1, max_length=2)
    language: Literal["en", "id"]
    template_version: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def unique_kinds(self) -> "GenerateDocumentsRequest":
        if len(set(self.kinds)) != len(self.kinds):
            raise ValueError("kinds tidak boleh berisi duplikat.")
        return self


class DocumentEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=300)
    value: Any
    note: str | None = Field(default=None, max_length=2000)


class DocumentRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_content_hash: str = Field(min_length=1, max_length=128)
    edits: list[DocumentEdit] = Field(min_length=1, max_length=500)
    note: str | None = Field(default=None, max_length=2000)


class RegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_content_hash: str = Field(min_length=1, max_length=128)
    reason: Literal["user_requested", "review_changes", "outdated_source"]


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected", "changes_requested"]
    content_hash: str = Field(min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=2000)


def _service(request: Request) -> DocumentService:
    return DocumentService(request.state.db, profile_store(request))


def _raise(exc: DocumentError, stage: str) -> None:
    raise ApiError(
        exc.status_code,
        exc.code,
        exc.message,
        stage=stage,
        retryable=exc.code == "review_unavailable",
        details=exc.details,
        active_task_id=exc.active_task_id,
    ) from exc


def _task_payload(task: dict, task_type: str, application_id: str) -> dict:
    return {
        "task_id": task["task_id"],
        "type": task_type,
        "status": task["status"],
        "application_id": application_id,
        "run_id": None,
        "extraction_run_id": None,
    }


@router.get("/{application_id}/documents")
def list_documents(
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
    except DocumentError as exc:
        _raise(exc, "validation")
    return {
        "application_id": application_id,
        "items": items,
        "page": {"limit": limit, "next_cursor": next_cursor, "has_more": next_cursor is not None},
    }


@router.post("/{application_id}/documents", status_code=202)
def generate_documents(
    request: Request, application_id: str, body: GenerateDocumentsRequest
) -> dict:
    try:
        task = _service(request).generate(
            application_id, list(body.kinds), body.language, body.template_version
        )
    except DocumentError as exc:
        _raise(exc, "draft")
    return _task_payload(task, "document_generation", application_id)


@router.get("/{application_id}/documents/{document_version_id}")
def get_document_version(
    request: Request, application_id: str, document_version_id: str
) -> dict:
    try:
        return _service(request).get(application_id, document_version_id)
    except DocumentError as exc:
        _raise(exc, "draft")


@router.post("/{application_id}/documents/{document_version_id}/revisions", status_code=201)
def create_document_revision(
    request: Request,
    application_id: str,
    document_version_id: str,
    body: DocumentRevisionRequest,
) -> dict:
    try:
        return _service(request).revise(
            application_id,
            document_version_id,
            body.base_content_hash,
            [edit.model_dump() for edit in body.edits],
            body.note,
        )
    except DocumentError as exc:
        _raise(exc, "draft")


@router.post("/{application_id}/documents/{document_version_id}/regenerate", status_code=202)
def regenerate_document(
    request: Request, application_id: str, document_version_id: str, body: RegenerateRequest
) -> dict:
    try:
        task = _service(request).regenerate(
            application_id, document_version_id, body.base_content_hash, body.reason
        )
    except DocumentError as exc:
        _raise(exc, "draft")
    return _task_payload(task, "document_generation", application_id)


@router.post("/{application_id}/documents/{document_version_id}/review", status_code=202)
def run_document_review(
    request: Request, application_id: str, document_version_id: str
) -> dict:
    try:
        task = _service(request).run_review(application_id, document_version_id)
    except DocumentError as exc:
        _raise(exc, "review")
    return _task_payload(task, "review", application_id)


@router.get("/{application_id}/documents/{document_version_id}/findings")
def get_document_findings(
    request: Request, application_id: str, document_version_id: str
) -> dict:
    try:
        return _service(request).findings(application_id, document_version_id)
    except DocumentError as exc:
        _raise(exc, "review")


@router.post("/{application_id}/documents/{document_version_id}/approval")
def approve_document_version(
    request: Request, application_id: str, document_version_id: str, body: ApprovalRequest
) -> JSONResponse:
    try:
        record, replayed = _service(request).approve(
            application_id,
            document_version_id,
            body.decision,
            body.content_hash,
            body.note,
        )
    except DocumentError as exc:
        _raise(exc, "approval")
    return JSONResponse(
        status_code=200 if replayed else 201,
        content=record,
        headers={"Idempotency-Replayed": "true"} if replayed else None,
    )
