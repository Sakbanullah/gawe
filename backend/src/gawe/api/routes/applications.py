"""`/api/applications`: workspace creation, reads, and explicit re-analysis.

A workspace is created from a matched `job_id`, or from a pasted URL through the
manual-URL fallback (API-CONTRACTS.md 3.4).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...master_cv.store import MasterCvError
from ...services.application_service import ApplicationError, ApplicationService
from ..deps import discovery_service, llm_client, profile_store
from ..errors import ApiError

router = APIRouter(prefix="/api/applications")

APPLICATION_STATUSES = {
    "not_started",
    "processing",
    "needs_review",
    "in_review",
    "approved",
    "exported",
    "failed",
    "outdated",
    "cancelled",
}


class CreateApplicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str | None = None
    url: str | None = None
    # Pasted description for a page that cannot be fetched (403/429 or a
    # JavaScript shell). The URL stays required: it is the job's identity.
    text: str | None = Field(default=None, max_length=200_000)
    language: str | None = None

    @model_validator(mode="after")
    def exactly_one_source(self) -> "CreateApplicationRequest":
        if bool(self.job_id) == bool(self.url):
            raise ValueError("Isi tepat satu dari job_id atau url.")
        if self.text is not None and not self.url:
            raise ValueError("text hanya boleh dikirim bersama url.")
        return self


class CancelApplicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1)
    profile_version_id: str | None = None
    note: str | None = Field(default=None, max_length=2000)


def _service(request: Request) -> ApplicationService:
    return ApplicationService(
        request.state.db,
        profile_store(request),
        llm_client=llm_client(request),
        root_dir=request.app.state.config.root_dir,
    )


def _bad_request(field: str, code: str, message: str) -> ApiError:
    return ApiError(
        400,
        "validation_failed",
        message,
        stage="validation",
        details=[{"field": field, "code": code, "message": message}],
    )


@router.get("")
def list_applications(
    request: Request,
    limit: int = 50,
    cursor: str | None = None,
    status: str | None = None,
    include_cancelled: bool = False,
) -> dict:
    if not 1 <= limit <= 200:
        raise _bad_request("limit", "out_of_range", "limit harus 1-200.")
    if status is not None and status not in APPLICATION_STATUSES:
        raise _bad_request("status", "invalid_enum", "Nilai status tidak dikenal.")
    try:
        items, next_cursor = _service(request).list(
            limit=limit,
            cursor=cursor,
            status=status,
            include_cancelled=include_cancelled,
        )
    except ApplicationError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message, stage="validation") from exc
    return {
        "items": items,
        "page": {"limit": limit, "next_cursor": next_cursor, "has_more": next_cursor is not None},
    }


@router.post("")
def create_application(request: Request, body: CreateApplicationRequest):
    service = _service(request)
    try:
        if body.url and not body.job_id:
            record, deduplicated = service.create_from_url(
                body.url, discovery_service(request), text=body.text
            )
        else:
            record, deduplicated = service.create(body.job_id or "")
    except MasterCvError as exc:
        raise ApiError(
            exc.status_code, exc.code, exc.message, stage="eligibility", active_task_id=exc.active_task_id
        ) from exc
    except ApplicationError as exc:
        raise ApiError(
            exc.status_code, exc.code, exc.message, stage="eligibility", active_task_id=exc.active_task_id
        ) from exc
    return JSONResponse(
        status_code=200 if deduplicated else 201,
        content={
            "application_id": record["application_id"],
            "job_id": record["job_id"],
            "task_id": None,
            "deduplicated": deduplicated,
        },
    )


@router.get("/{application_id}")
def get_application(request: Request, application_id: str) -> dict:
    try:
        return _service(request).workspace(application_id)
    except ApplicationError as exc:
        raise ApiError(
            exc.status_code, exc.code, exc.message, stage="eligibility", active_task_id=exc.active_task_id
        ) from exc


@router.post("/{application_id}/cancel")
def cancel_application(
    request: Request, application_id: str, body: CancelApplicationRequest
) -> dict:
    try:
        record = _service(request).cancel(application_id, body.reason)
    except ApplicationError as exc:
        raise ApiError(
            exc.status_code, exc.code, exc.message, stage="eligibility", active_task_id=exc.active_task_id
        ) from exc
    return {"application_id": record["application_id"], "cancelled_at": record["cancelled_at"]}


@router.get("/{application_id}/job")
def get_application_job(request: Request, application_id: str) -> dict:
    try:
        return _service(request).job_detail(application_id)
    except ApplicationError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message, stage="fetch") from exc


@router.get("/{application_id}/eligibility")
def get_eligibility(request: Request, application_id: str) -> dict:
    try:
        eligibility = _service(request).eligibility(application_id)
    except ApplicationError as exc:
        raise ApiError(
            exc.status_code, exc.code, exc.message, stage="eligibility", active_task_id=exc.active_task_id
        ) from exc
    if eligibility is None:
        raise ApiError(404, "not_found", "Eligibility belum dihitung.", stage="eligibility")
    return eligibility


@router.get("/{application_id}/fit")
def get_fit(request: Request, application_id: str) -> dict:
    try:
        fit = _service(request).fit(application_id)
    except ApplicationError as exc:
        raise ApiError(
            exc.status_code, exc.code, exc.message, stage="eligibility", active_task_id=exc.active_task_id
        ) from exc
    if fit is None:
        raise ApiError(
            409,
            "fit_not_available",
            "Fit hanya tersedia untuk eligibility eligible.",
            stage="eligibility",
        )
    return fit


@router.post("/{application_id}/analysis", status_code=202)
def rerun_analysis(request: Request, application_id: str, body: AnalysisRequest) -> dict:
    if body.reason not in {"profile_changed", "job_changed", "user_requested", "outdated"}:
        raise _bad_request("reason", "invalid_enum", "Nilai reason tidak dikenal.")
    try:
        result = _service(request).rerun_analysis(application_id)
    except MasterCvError as exc:
        raise ApiError(
            exc.status_code, exc.code, exc.message, stage="eligibility", active_task_id=exc.active_task_id
        ) from exc
    except ApplicationError as exc:
        raise ApiError(
            exc.status_code, exc.code, exc.message, stage="eligibility", active_task_id=exc.active_task_id
        ) from exc
    return {
        "task_id": result["task_id"],
        "type": "analysis",
        "status": result["status"],
        "application_id": application_id,
        "run_id": None,
        "extraction_run_id": None,
    }
