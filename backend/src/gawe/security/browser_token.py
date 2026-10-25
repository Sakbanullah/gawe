"""Pairing token for the browser-import extension.

The extension lives outside the API session: it runs on `chrome-extension://`
origins and has no CSRF cookie. A bearer token in a file is the smallest thing
that stops any page the browser opens from posting jobs into localhost.

Only the hash is stored. The plaintext is returned once, when issued, and
again only through the authenticated settings route so the user can copy it into
the extension.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path

TOKEN_HEADER = "X-Gawe-Token"
TOKEN_FILE = "browser_token"


def _path(config) -> Path:
    return Path(config.data_dir) / TOKEN_FILE


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _write(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(_digest(token), encoding="utf-8")
    os.replace(tmp, path)


def issue(config) -> str:
    """Create a new token, replacing any previous one. Returns the plaintext."""
    token = secrets.token_urlsafe(32)
    _write(_path(config), token)
    return token


def ensure(config) -> str:
    """Issue a token when none exists; otherwise mint a fresh readable one."""
    return issue(config)


def verify(config, header_value: str | None) -> bool:
    """Constant-time check of a presented token against the stored hash."""
    if not header_value:
        return False
    path = _path(config)
    try:
        stored = path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if not stored:
        return False
    return hmac.compare_digest(stored, _digest(header_value))


def exists(config) -> bool:
    return _path(config).is_file()
