"""Local session and CSRF tokens.

Token must match the cookie, be tied to the session, and pass the closed
Origin allowlist. Origin checking is defence in depth, not a replacement.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping

CSRF_HEADER = "X-CSRF-Token"
SESSION_COOKIE = "gawe_session"
CSRF_COOKIE = "gawe_csrf"
SESSION_TTL = timedelta(hours=12)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class CsrfError(Exception):
    code = "csrf_invalid"


@dataclass(frozen=True)
class Session:
    session_id: str
    csrf_token: str
    expires_at: datetime

    @property
    def csrf_header(self) -> str:
        return CSRF_HEADER

    def is_expired(self, now: datetime | None = None) -> bool:
        return (now or datetime.now(timezone.utc)) >= self.expires_at

    def as_response(self) -> dict:
        return {
            "session_id": self.session_id,
            "csrf_token": self.csrf_token,
            "csrf_header": CSRF_HEADER,
            "expires_at": self.expires_at.isoformat().replace("+00:00", "Z"),
        }


def new_session(now: datetime | None = None) -> Session:
    start = now or datetime.now(timezone.utc)
    return Session(
        session_id=secrets.token_urlsafe(24),
        csrf_token=secrets.token_urlsafe(32),
        expires_at=start + SESSION_TTL,
    )


def allowed_origins(host: str, port: int) -> set[str]:
    return {
        f"http://{host}:{port}",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    }


def validate_csrf(
    method: str,
    headers: Mapping[str, str],
    cookies: Mapping[str, str],
    session: Session | None,
    allowed: set[str],
    now: datetime | None = None,
) -> None:
    if method.upper() in SAFE_METHODS:
        return
    if session is None or session.is_expired(now):
        raise CsrfError("no active session")

    origin = headers.get("origin")
    if origin is not None and origin not in allowed:
        raise CsrfError("origin not allowed")
    if headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise CsrfError("cross-site request")

    header_token = headers.get(CSRF_HEADER)
    cookie_token = cookies.get(CSRF_COOKIE)
    if not header_token or not cookie_token:
        raise CsrfError("missing csrf token")
    if not secrets.compare_digest(header_token, cookie_token):
        raise CsrfError("csrf token mismatch")
    if not secrets.compare_digest(header_token, session.csrf_token):
        raise CsrfError("csrf token does not belong to session")
    if cookies.get(SESSION_COOKIE) != session.session_id:
        raise CsrfError("session cookie mismatch")
