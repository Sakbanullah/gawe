"""`/api/settings` routes: versioned cloud consent."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ...security.consent import (
    CONSENT_TYPE,
    REQUIRED_DATA_CLASSES,
    ConsentAlreadyRevoked,
    ConsentNotFound,
)
from ..deps import consent_store
from ..errors import ApiError

router = APIRouter(prefix="/api/settings")


class ConsentScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_classes: list[Literal["cv_text", "job_description", "profile_slice"]] = Field(
        max_length=3
    )
    provider_id: str = Field(min_length=1, max_length=100)
    model_roles: dict[str, str] | None = None


class ConsentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consent_type: Literal[CONSENT_TYPE]
    scope: ConsentScopeRequest
    accepted: Literal[True]


@router.get("/consent")
def get_consent(request: Request, history_limit: int = 20) -> dict:
    if not 1 <= history_limit <= 100:
        raise ApiError(
            400,
            "validation_failed",
            "history_limit harus 1-100.",
            stage="validation",
            details=[{"field": "history_limit", "code": "out_of_range", "message": "1-100"}],
        )
    return consent_store(request).status(history_limit=history_limit)


@router.post("/consent", status_code=201)
def grant_consent(request: Request, body: ConsentCreateRequest) -> dict:
    store = consent_store(request)
    required = store.required_scope()
    if body.scope.provider_id != required["provider_id"]:
        raise ApiError(
            400,
            "validation_failed",
            "provider_id tidak cocok dengan provider aktif.",
            stage="validation",
            details=[{"field": "scope.provider_id", "code": "provider_mismatch",
                      "message": "Harus sama dengan provider aktif."}],
        )
    if sorted(body.scope.data_classes) != sorted(required["data_classes"]):
        raise ApiError(
            400,
            "validation_failed",
            "Cakupan data harus mencakup semua kelas data yang dikirim.",
            stage="validation",
            details=[{"field": "scope.data_classes", "code": "scope_mismatch",
                      "message": ", ".join(REQUIRED_DATA_CLASSES)}],
        )
    return store.grant()


@router.delete("/consent/{consent_id}")
def revoke_consent(request: Request, consent_id: str) -> dict:
    store = consent_store(request)
    try:
        return store.revoke(consent_id)
    except ConsentNotFound as exc:
        raise ApiError(404, "not_found", "Consent tidak ditemukan.", stage="validation") from exc
    except ConsentAlreadyRevoked as exc:
        raise ApiError(
            409, "conflict", "Consent sudah dicabut.", stage="validation"
        ) from exc
