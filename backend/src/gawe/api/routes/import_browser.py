"""`/api/import/browser`: job data sent by the browser extension.

Separate from `/api/sources` on purpose: this endpoint cannot fetch, schedule, or
change a source. It only accepts data the user already has on screen, and it is
authenticated with a pairing token instead of the session CSRF pair, because the
caller is an extension page rather than the SPA.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...master_cv.store import MasterCvError
from ...security import browser_token
from ...services.browser_import_service import (
    MAX_JOBS_PER_REQUEST,
    BrowserImportError,
    BrowserImportService,
)
from ..deps import browser_import_service
from ..errors import ApiError

router = APIRouter(prefix="/api/import/browser")


class JobCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=2048)
    company: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=200)
    salary: str | None = Field(default=None, max_length=200)
    snippet: str | None = Field(default=None, max_length=4000)
    posted_at: str | None = Field(default=None, max_length=32)


class JobDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=2048)
    company: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=200)
    posted_at: str | None = Field(default=None, max_length=32)
    description: str = Field(min_length=1, max_length=200_000)


class BrowserImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["jobstreet"]
    page_url: str = Field(min_length=1, max_length=2048)
    mode: Literal["cards", "detail"] = "cards"
    jobs: list[JobCard] = Field(default_factory=list, max_length=MAX_JOBS_PER_REQUEST)
    detail: JobDetail | None = None

    @model_validator(mode="after")
    def exactly_the_mode_payload(self) -> "BrowserImportRequest":
        if self.mode == "detail" and self.detail is None:
            raise ValueError("mode detail memerlukan detail.")
        if self.mode == "cards" and not self.jobs:
            raise ValueError("mode cards memerlukan jobs.")
        return self


@router.post("")
def import_from_browser(request: Request, body: BrowserImportRequest) -> dict:
    if not browser_token.verify(
        request.app.state.config, request.headers.get(browser_token.TOKEN_HEADER)
    ):
        raise ApiError(
            401,
            "import_token_invalid",
            "Token impor browser tidak valid. Salin ulang token dari Settings.",
            stage="security",
        )
    origin = request.headers.get("origin")
    if origin is not None and not origin.startswith("chrome-extension://"):
        raise ApiError(
            403,
            "origin_not_allowed",
            "Endpoint ini hanya menerima request dari ekstensi.",
            stage="security",
        )
    service: BrowserImportService = browser_import_service(request)
    try:
        if body.mode == "detail":
            result = service.import_detail(
                body.source, body.page_url, body.detail.model_dump()
            )
            return {**result, "mode": "detail"}
        result = service.import_cards(
            body.source, body.page_url, [card.model_dump() for card in body.jobs]
        )
        return {**result, "mode": "cards"}
    except BrowserImportError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message, stage="validation") from exc
    except MasterCvError as exc:
        raise ApiError(
            exc.status_code,
            exc.code,
            exc.message,
            stage="validation",
            active_task_id=exc.active_task_id,
        ) from exc
