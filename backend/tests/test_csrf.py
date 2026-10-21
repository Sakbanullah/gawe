from __future__ import annotations

import pytest

from gawe.security.csrf import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    CsrfError,
    allowed_origins,
    new_session,
    validate_csrf,
)

ALLOWED = allowed_origins("127.0.0.1", 8000)


def _cookies(session) -> dict:
    return {SESSION_COOKIE: session.session_id, CSRF_COOKIE: session.csrf_token}


def test_safe_method_needs_no_token() -> None:
    validate_csrf("GET", {}, {}, None, ALLOWED)


def test_missing_token_is_rejected() -> None:
    session = new_session()
    with pytest.raises(CsrfError):
        validate_csrf("POST", {}, _cookies(session), session, ALLOWED)


def test_wrong_token_is_rejected() -> None:
    session = new_session()
    with pytest.raises(CsrfError):
        validate_csrf(
            "POST", {CSRF_HEADER: "wrong"}, _cookies(session), session, ALLOWED
        )


def test_valid_token_is_accepted() -> None:
    session = new_session()
    validate_csrf(
        "POST", {CSRF_HEADER: session.csrf_token}, _cookies(session), session, ALLOWED
    )


def test_foreign_origin_is_rejected() -> None:
    session = new_session()
    with pytest.raises(CsrfError):
        validate_csrf(
            "POST",
            {CSRF_HEADER: session.csrf_token, "origin": "https://evil.example"},
            _cookies(session),
            session,
            ALLOWED,
        )


def test_cross_site_fetch_is_rejected() -> None:
    session = new_session()
    with pytest.raises(CsrfError):
        validate_csrf(
            "POST",
            {CSRF_HEADER: session.csrf_token, "sec-fetch-site": "cross-site"},
            _cookies(session),
            session,
            ALLOWED,
        )


def test_dev_proxy_origin_is_accepted() -> None:
    session = new_session()
    validate_csrf(
        "POST",
        {CSRF_HEADER: session.csrf_token, "origin": "http://127.0.0.1:5173"},
        _cookies(session),
        session,
        ALLOWED,
    )
