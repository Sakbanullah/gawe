"""Bounded HTTP fetch with per-host rate limiting.

Rules from SECURITY.md: HTTPS only, public host only, redirects re-validated,
20 s timeout, at most 5 redirects, at most 5 MB.
"""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

from ..security.url_guard import MAX_RESPONSE_BYTES, TIMEOUT_S, UnsafeUrl, validate_url

MAX_WORKERS = 3
MIN_INTERVAL_S = 1.0

# Registrable-domain approximation for redirect checks. Two hosts on the same
# registrable domain (boards.greenhouse.io -> job-boards.greenhouse.io) are the
# same site; anything else is rejected. Multi-label suffixes need the list below
# so `evil.co.id` is not treated as the same site as `bank.co.id`.
_PUBLIC_SUFFIXES = {
    "co.uk", "co.id", "or.id", "ac.id", "web.id", "my.id", "biz.id", "sch.id",
    "com.au", "co.jp", "com.br", "co.in", "com.sg", "co.nz", "co.za", "com.mx",
}


def _registrable_domain(host: str) -> str:
    labels = host.split(".")
    if len(labels) < 2:
        return host
    if ".".join(labels[-2:]) in _PUBLIC_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _redirect_allowed(host: str, allowed_hosts: frozenset[str]) -> bool:
    if host in allowed_hosts:
        return True
    domain = _registrable_domain(host)
    return any(_registrable_domain(allowed) == domain for allowed in allowed_hosts)


class FetchError(Exception):
    def __init__(
        self, code: str, message: str, *, retryable: bool, http_status: int | None = None
    ) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.http_status = http_status


@dataclass(frozen=True)
class FetchResponse:
    status_code: int
    body: str
    final_url: str
    truncated: bool = False
    content_type: str | None = None


def _is_json_content_type(value: str | None) -> bool:
    if not value:
        return True
    media_type = value.split(";", 1)[0].strip().lower()
    return media_type == "application/json" or media_type.endswith("+json") or media_type == "text/json"


class HostRateLimiter:
    """Reserve one request slot per host per interval; hosts run in parallel."""

    def __init__(
        self,
        min_interval: float = MIN_INTERVAL_S,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_slot: dict[str, float] = {}

    def wait(self, host: str) -> None:
        with self._lock:
            now = self._clock()
            slot = max(now, self._next_slot.get(host, now))
            self._next_slot[host] = slot + self._min_interval
        delay = slot - now
        if delay > 0:
            self._sleep(delay)


class _ValidatingRedirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 5

    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        self._allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        try:
            safe = validate_url(newurl)
        except UnsafeUrl as exc:
            raise FetchError("source_unavailable", f"Redirect ditolak: {exc}.", retryable=False)
        if not _redirect_allowed(safe.host, self._allowed_hosts):
            raise FetchError("source_unavailable", "Redirect ke host yang tidak diizinkan.", retryable=False)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def http_fetch(url: str, allowed_hosts: frozenset[str]) -> FetchResponse:
    try:
        safe = validate_url(url)
    except UnsafeUrl as exc:
        raise FetchError("url_rejected", f"URL fetch ditolak: {exc}.", retryable=False) from exc
    if not _redirect_allowed(safe.host, allowed_hosts):
        raise FetchError("source_unavailable", "Host sumber tidak diizinkan.", retryable=False)

    opener = urllib.request.build_opener(_ValidatingRedirect(allowed_hosts))
    request = urllib.request.Request(url, headers={"User-Agent": "Gawe/0.1 (local)"})
    try:
        with opener.open(request, timeout=TIMEOUT_S) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise FetchError("response_too_large", "Respons sumber melebihi 5 MB.", retryable=False)
            content_type = response.headers.get("Content-Type")
            if not _is_json_content_type(content_type):
                raise FetchError(
                    "source_unavailable",
                    f"Sumber mengembalikan content type tidak didukung: {content_type}.",
                    retryable=False,
                )
            return FetchResponse(
                status_code=response.status,
                body=body.decode("utf-8", errors="replace"),
                final_url=response.geturl(),
                content_type=content_type,
            )
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise FetchError(
                "source_unavailable",
                "Sumber menolak akses otomatis.",
                retryable=False,
                http_status=exc.code,
            ) from exc
        raise FetchError(
            "source_error",
            "Sumber mengembalikan status HTTP yang tidak diharapkan.",
            retryable=exc.code >= 500,
            http_status=exc.code,
        ) from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        raise FetchError("source_unavailable", "Sumber tidak dapat dihubungi.", retryable=True) from exc


def fetch_source(
    source: dict,
    adapter,
    *,
    fetcher: Callable[[str], FetchResponse] | None = None,
    limiter: HostRateLimiter | None = None,
) -> FetchResponse:
    url = adapter.build_url(source)
    host = (urlsplit(url).hostname or "").lower()
    (limiter or HostRateLimiter()).wait(host)
    if fetcher is None:
        return http_fetch(url, frozenset(adapter.HOSTS))
    return fetcher(url)


def fetch_document(
    url: str,
    *,
    allowed_hosts: frozenset[str],
    accept: tuple[str, ...] = ("text/html", "application/xhtml+xml"),
) -> FetchResponse:
    """Fetch one HTML page for the manual-URL fallback.

    Same guard, timeout, redirect and size rules as `http_fetch`; only the
    accepted content types differ, because an ATS JSON body is not a job page.
    """
    try:
        safe = validate_url(url)
    except UnsafeUrl as exc:
        raise FetchError("url_rejected", f"URL ditolak: {exc}.", retryable=False) from exc
    if not _redirect_allowed(safe.host, allowed_hosts):
        raise FetchError("source_unavailable", "Host tidak diizinkan.", retryable=False)

    opener = urllib.request.build_opener(_ValidatingRedirect(allowed_hosts))
    request = urllib.request.Request(
        url, headers={"User-Agent": "Gawe/0.1 (local)", "Accept": ", ".join(accept)}
    )
    try:
        with opener.open(request, timeout=TIMEOUT_S) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise FetchError("response_too_large", "Halaman melebihi 5 MB.", retryable=False)
            content_type = response.headers.get("Content-Type")
            media_type = (content_type or "").split(";", 1)[0].strip().lower()
            if media_type and media_type not in accept:
                raise FetchError(
                    "source_unavailable",
                    f"Halaman bukan HTML: {content_type}.",
                    retryable=False,
                )
            return FetchResponse(
                status_code=response.status,
                body=body.decode("utf-8", errors="replace"),
                final_url=response.geturl(),
                content_type=content_type,
            )
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 429):
            raise FetchError(
                "source_unavailable",
                "Halaman menolak akses otomatis. Tempelkan teks lowongan secara manual.",
                retryable=False,
                http_status=exc.code,
            ) from exc
        if exc.code == 404:
            raise FetchError("source_not_found", "Halaman tidak ditemukan.", retryable=False) from exc
        raise FetchError(
            "source_error",
            "Halaman mengembalikan status HTTP yang tidak diharapkan.",
            retryable=exc.code >= 500,
            http_status=exc.code,
        ) from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        raise FetchError("source_unavailable", "Halaman tidak dapat dihubungi.", retryable=True) from exc
