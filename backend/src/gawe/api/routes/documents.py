"""`/api/applications/{id}/documents`: versions, revisions, review, approval, PDF.

D6 is decided: Tectonic renders the PDF. The `pdf` endpoint is a non-final
preview; only `/exports` creates a final file.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...documents import render
from ...documents.plan import DocumentPlanService, PlanError
from ...services.document_service import DocumentError, DocumentService
from ..deps import llm_client, profile_store
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
    # Checked findings for the next write call. Omitted keeps the old behaviour
    # (every open finding is passed as an instruction).
    finding_ids: list[str] | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected", "changes_requested"]
    content_hash: str = Field(min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def changes_need_note(self) -> "ApprovalRequest":
        # Approval idempotency is (version, hash, decision): an empty note would
        # replay the previous decision and silently drop what must change.
        if self.decision != "approved" and not (self.note or "").strip():
            raise ValueError("Catatan wajib diisi untuk keputusan rejected/changes_requested.")
        return self


def _service(request: Request) -> DocumentService:
    return DocumentService(
        request.state.db,
        profile_store(request),
        llm_client(request),
        request.app.state.config.root_dir,
    )


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


class PlanApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    content_hash: str = Field(min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def rejection_needs_note(self) -> "PlanApprovalRequest":
        if self.decision == "rejected" and not (self.note or "").strip():
            raise ValueError("Catatan wajib diisi saat rencana ditolak.")
        return self


class DocumentPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: Literal["en", "id"] | None = None


def _plan_service(request: Request) -> DocumentPlanService:
    return DocumentPlanService(request.state.db, profile_store(request))


def _raise_plan(exc: PlanError) -> None:
    raise ApiError(exc.status_code, exc.code, exc.message, stage="draft") from exc


@router.post("/{application_id}/document-plan", status_code=201)
def create_document_plan(
    request: Request, application_id: str, body: DocumentPlanRequest, response: Response
) -> dict:
    """Compose the adjustment plan. Deterministic: no task, no model, no consent."""
    service = _service(request)
    try:
        record = service.application_for_plan(application_id)
    except DocumentError as exc:
        _raise(exc, "eligibility")
    plan = _plan_service(request).create(
        application_id,
        record["job"],
        record["fit"],
        record["requirements"],
        body.language,
    )
    if plan.pop("replayed", False):
        # Same plan, same answer: a repeated request must not look like a new one.
        response.status_code = 200
        response.headers["Idempotency-Replayed"] = "true"
    return plan


@router.get("/{application_id}/document-plan")
def get_document_plan(request: Request, application_id: str) -> dict:
    plan = _plan_service(request).latest(application_id)
    if plan is None:
        raise ApiError(404, "not_found", "Belum ada rencana penyesuaian.", stage="draft")
    return plan


@router.post("/{application_id}/document-plan/{plan_id}/approval")
def approve_document_plan(
    request: Request,
    application_id: str,
    plan_id: str,
    body: PlanApprovalRequest,
    response: Response,
) -> dict:
    """Approve or reject a plan. This never approves a document version."""
    try:
        plan = _plan_service(request).approve(
            application_id,
            plan_id,
            body.decision,
            body.content_hash,
            body.note,
        )
    except PlanError as exc:
        _raise_plan(exc)
    if plan.pop("replayed", False):
        response.headers["Idempotency-Replayed"] = "true"
    return plan


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
            application_id,
            document_version_id,
            body.base_content_hash,
            body.reason,
            finding_ids=body.finding_ids,
        )
    except DocumentError as exc:
        _raise(exc, "draft")
    return _task_payload(task, "document_generation", application_id)


@router.post(
    "/{application_id}/documents/{document_version_id}/revision-request", status_code=202
)
def request_document_revision(
    request: Request, application_id: str, document_version_id: str, body: RegenerateRequest
) -> dict:
    """New version built only from the findings the user checked.

    Same loop as regenerate, but `finding_ids` is required: an unchecked finding
    is not passed to the writer. The approval gates still judge the whole version.
    """
    if not body.finding_ids:
        raise ApiError(
            400,
            "validation_failed",
            "Pilih minimal satu temuan.",
            stage="validation",
            details=[
                {"field": "finding_ids", "code": "empty", "message": "Minimal satu."}
            ],
        )
    try:
        task = _service(request).regenerate(
            application_id,
            document_version_id,
            body.base_content_hash,
            body.reason,
            finding_ids=body.finding_ids,
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


@router.get("/{application_id}/documents/{document_version_id}/pdf")
def preview_document_pdf(
    request: Request, application_id: str, document_version_id: str
):
    """Non-final PDF preview. Never marks the version approved or exported."""
    try:
        version = _service(request).get(application_id, document_version_id)
        pdf_bytes, _log = render.compile_pdf(render.build(version["content"]))
    except DocumentError as exc:
        _raise(exc, "draft")
    except render.RenderError as exc:
        raise ApiError(
            409,
            exc.code,
            exc.message,
            stage="export",
            retryable=exc.code in {"tectonic_unavailable", "compile_timeout"},
        ) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"},
    )


@router.get("/{application_id}/documents/{document_version_id}/pdf")
def preview_document_pdf(
    request: Request, application_id: str, document_version_id: str
):
    """Non-final PDF preview. Never marks the version approved or exported."""
    try:
        version = _service(request).get(application_id, document_version_id)
        pdf_bytes, _log = render.compile_pdf(render.build(version["content"]))
    except DocumentError as exc:
        _raise(exc, "draft")
    except render.RenderError as exc:
        raise ApiError(
            503 if exc.code == "tectonic_unavailable" else 409,
            exc.code,
            exc.message,
            stage="export",
            retryable=exc.code in {"tectonic_unavailable", "compile_timeout"},
        ) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"},
    )


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
