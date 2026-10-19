"""`/api/setup` routes: Master CV upload, profile review, confirmation."""

from __future__ import annotations

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ...ingest.validate import IngestError, validate_upload
from ...master_cv.store import MasterCvError
from ...profile.corrections import CorrectionError
from ...profile.store import ProfileStore
from ..deps import master_cv_store, profile_service, profile_store
from ..errors import ApiError
from ..schemas.setup import ConfirmRequest, CorrectionRequest, ExtractionRequest, RollbackRequest

router = APIRouter(prefix="/api/setup")


def _raise(exc: Exception) -> None:
    if isinstance(exc, (MasterCvError, IngestError)):
        raise ApiError(exc.status_code, exc.code, exc.message, stage="upload") from exc
    if isinstance(exc, CorrectionError):
        raise ApiError(400, "validation_failed", exc.message, stage="validation") from exc
    raise exc


@router.get("/master-cv")
def get_master_cv(request: Request) -> dict:
    record = master_cv_store(request).active()
    if record is None:
        raise ApiError(404, "not_found", "Belum ada Master CV.", stage="upload")
    return record


@router.post("/master-cv")
async def upload_master_cv(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    data = await file.read()
    try:
        upload = validate_upload(file.filename or "", file.content_type, data)
    except IngestError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message, stage="upload") from exc
    record, deduplicated = master_cv_store(request).upload(upload)
    payload = {**record, "deduplicated": deduplicated}
    return JSONResponse(status_code=200 if deduplicated else 201, content=payload)


@router.get("/master-cv/file")
def download_master_cv(request: Request) -> FileResponse:
    store = master_cv_store(request)
    record = store.active()
    if record is None:
        raise ApiError(404, "not_found", "Belum ada Master CV.", stage="upload")
    try:
        path = store.file_path(record)
    except MasterCvError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message, stage="upload") from exc
    return FileResponse(
        path,
        media_type=record["original_file"]["mime"],
        filename=record["original_file"]["filename"],
    )


@router.post("/master-cv/extractions", status_code=202)
def start_profile_extraction(request: Request, body: ExtractionRequest | None = None) -> dict:
    service = profile_service(request)
    try:
        task = service.start_extraction()
    except MasterCvError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message, stage="extract") from exc
    return {
        "task_id": task["task_id"],
        "type": task["type"],
        "status": task["status"],
        "application_id": None,
        "run_id": None,
        "extraction_run_id": task["task_id"],
    }


@router.get("/profiles")
def list_profile_versions(
    request: Request, limit: int = 50, cursor: str | None = None
) -> dict:
    if limit < 1 or limit > 200:
        raise ApiError(
            400,
            "validation_failed",
            "limit harus 1-200.",
            stage="validation",
            details=[{"field": "limit", "code": "out_of_range", "message": "1-200"}],
        )
    store = profile_store(request)
    items, next_cursor = store.list(limit=limit, cursor=cursor)
    service = profile_service(request)
    return {
        "items": [service.summary(item) for item in items],
        "page": {"limit": limit, "next_cursor": next_cursor, "has_more": next_cursor is not None},
    }


@router.get("/profiles/{profile_version_id}")
def get_profile_version(request: Request, profile_version_id: str) -> dict:
    version = profile_store(request).get(profile_version_id)
    if version is None:
        raise ApiError(404, "not_found", "Versi profil tidak ditemukan.", stage="validation")
    return profile_service(request).version_payload(version)


@router.patch("/profiles/{profile_version_id}")
def correct_profile_version(
    request: Request, profile_version_id: str, body: CorrectionRequest
) -> JSONResponse:
    service = profile_service(request)
    try:
        version, created = service.correct(
            profile_version_id,
            body.expected_version,
            [item.model_dump() for item in body.corrections],
        )
    except MasterCvError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message, stage="validation") from exc
    return JSONResponse(
        status_code=201 if created else 200,
        content=service.version_payload(version),
    )


@router.post("/profiles/{profile_version_id}/confirm")
def confirm_profile_version(
    request: Request, profile_version_id: str, body: ConfirmRequest | None = None
) -> dict:
    try:
        return profile_service(request).confirm(
            profile_version_id, body.note if body else None
        )
    except MasterCvError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message, stage="validation") from exc


@router.post("/profile/rollback")
def rollback_profile(request: Request, body: RollbackRequest) -> dict:
    try:
        return profile_service(request).rollback(body.target_profile_version_id, body.reason)
    except MasterCvError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message, stage="validation") from exc
