"""Source health and scheduling, derived only from recorded outcomes.

`health_status` is a function of the current failure streak, never a guess:

    unknown   no attempt recorded yet
    healthy   the last attempt succeeded
    degraded  one or two failures in a row
    broken    three or more failures in a row

A failing source is scheduled further away each time (exponential backoff), and a
`Retry-After` header from the server is honoured as a floor. Nothing here decides
whether a source may be fetched at all; that stays in the registry verification
gate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

UNKNOWN = "unknown"
HEALTHY = "healthy"
DEGRADED = "degraded"
BROKEN = "broken"

DEGRADED_AFTER = 1
BROKEN_AFTER = 3
MAX_BACKOFF_FACTOR = 8


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(stamp: datetime) -> str:
    return stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def status_from(failures: int, *, ever_succeeded: bool) -> str:
    if failures >= BROKEN_AFTER:
        return BROKEN
    if failures >= DEGRADED_AFTER:
        return DEGRADED
    return HEALTHY if ever_succeeded else UNKNOWN


def next_run_at(now: datetime, interval_minutes: int) -> str:
    return _iso(now + timedelta(minutes=max(1, interval_minutes)))


def retry_at(
    now: datetime,
    failures: int,
    interval_minutes: int,
    retry_after_s: int | None = None,
) -> str:
    """Back off after a failure, but never sooner than the server asked."""
    factor = 2 ** min(max(failures - 1, 0), MAX_BACKOFF_FACTOR)
    wait = max(1, interval_minutes) * 60 * factor
    if retry_after_s:
        wait = max(wait, retry_after_s)
    return _iso(now + timedelta(seconds=wait))


def is_due(next_run_at_value: str | None, now: datetime | None = None) -> bool:
    if not next_run_at_value:
        return True
    try:
        due = datetime.fromisoformat(next_run_at_value.replace("Z", "+00:00"))
    except ValueError:
        return True
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return due <= (now or _now())


def quota_exhausted(requests_last_24h: int, daily_request_quota: int) -> bool:
    return daily_request_quota > 0 and requests_last_24h >= daily_request_quota
