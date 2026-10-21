"""Safe API error envelope shared by routes and middleware."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        stage: str = "server",
        retryable: bool = False,
        details: list[dict[str, Any]] | None = None,
        active_task_id: str | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.stage = stage
        self.retryable = retryable
        self.details = details or []
        self.active_task_id = active_task_id


def error_payload(
    code: str,
    message: str,
    stage: str,
    retryable: bool = False,
    request_id: str | None = None,
    details: list[dict[str, Any]] | None = None,
    active_task_id: str | None = None,
) -> dict:
    return {
        "error": {
            "code": code,
            "message": message[:500],
            "stage": stage,
            "retryable": retryable,
            "run_id": None,
            "request_id": request_id,
            "active_task_id": active_task_id,
            "details": (details or [])[:50],
        }
    }


def payload_for(exc: ApiError, request_id: str | None = None) -> dict:
    return error_payload(
        exc.code,
        exc.message,
        exc.stage,
        retryable=exc.retryable,
        request_id=request_id,
        details=exc.details,
        active_task_id=exc.active_task_id,
    )
