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
        if safe.host not in self._allowed_hosts:
            raise FetchError("source_unavailable", "Redirect ke host yang tidak diizinkan.", retryable=False)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def http_fetch(url: str, allowed_hosts: frozenset[str]) -> FetchResponse:
    try:
        safe = validate_url(url)
    except UnsafeUrl as exc:
        raise FetchError("url_rejected", f"URL fetch ditolak: {exc}.", retryable=False) from exc
    if safe.host not in allowed_hosts:
        raise FetchError("source_unavailable", "Host sumber tidak diizinkan.", retryable=False)

    opener = urllib.request.build_opener(_ValidatingRedirect(allowed_hosts))
    request = urllib.request.Request(url, headers={"User-Agent": "Gawe/0.1 (local)"})
    try:
        with opener.open(request, timeout=TIMEOUT_S) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise FetchError("response_too_large", "Respons sumber melebihi 5 MB.", retryable=False)
            return FetchResponse(
                status_code=response.status,
                body=body.decode("utf-8", errors="replace"),
                final_url=response.geturl(),
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
