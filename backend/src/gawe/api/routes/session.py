"""Session and CSRF token issuance."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ...security import csrf

router = APIRouter(prefix="/api")


@router.get("/session")
def get_session(request: Request) -> JSONResponse:
    session = csrf.new_session()
    request.app.state.sessions[session.session_id] = session
    response = JSONResponse(session.as_response())
    response.set_cookie(
        csrf.SESSION_COOKIE,
        session.session_id,
        httponly=True,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        csrf.CSRF_COOKIE,
        session.csrf_token,
        httponly=False,
        samesite="strict",
        path="/",
    )
    return response
