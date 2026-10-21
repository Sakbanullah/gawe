"""`robots.txt` check for the manual-URL fallback (JOB-DISCOVERY.md §10).

Only the `User-agent: *` group is read, with longest-match Disallow/Allow
semantics. An unreachable robots.txt (404 or fetch error) is treated as no
restriction, which is the common convention; the URL guard still applies.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from .fetch import FetchError, FetchResponse, fetch_document


def is_allowed(robots_text: str, path: str, *, user_agent: str = "Gawe") -> bool:
    rules: list[tuple[str, bool]] = []
    applies = False
    for raw in (robots_text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            applies = value == "*" or value.lower() == user_agent.lower()
        elif key in {"allow", "disallow"} and applies:
            if not value:
                continue
            rules.append((value, key == "allow"))

    best: tuple[int, bool] | None = None
    for prefix, allowed in rules:
        if path.startswith(prefix) or prefix == "/":
            length = len(prefix)
            if best is None or length >= best[0]:
                # Allow wins on an exact tie, per the common implementation.
                best = (length, allowed)
    return True if best is None else best[1]


def check(url: str, *, fetcher=None) -> tuple[bool, str | None]:
    """Return `(allowed, reason)`. `reason` is safe to show to the user."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    path = parts.path or "/"
    robots_url = f"https://{host}/robots.txt"
    try:
        if fetcher is None:
            response: FetchResponse = fetch_document(
                robots_url, allowed_hosts=frozenset({host}), accept=("text/plain", "text/html")
            )
        else:
            response = fetcher(robots_url)
    except FetchError:
        return True, None
    allowed = is_allowed(response.body, path)
    return allowed, None if allowed else "robots.txt melarang pengambilan halaman ini."
