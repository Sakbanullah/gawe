"""Himalayas aggregator adapter.

Docs: https://himalayas.app/api — Terms: https://himalayas.app/terms#api

One feed covers many companies, so the company comes from the record and never
from the source label. `companyName` is used when present; when it is empty the
slug is read from `guid` and used as the display name, and a record with neither
is dropped. `applicationLink` is the apply target, unchanged (terms §api: "Use
the `applicationLink` for every Apply button, unchanged").

`pubDate` is "when the job was last updated", not when it was posted, so
`posted_at` stays unknown instead of storing a date that means something else.
`locationRestrictions` is the only location the feed publishes: an empty list
stays unknown, because "no restriction published" is not "open worldwide".

Pagination is cursor-based with at most 20 records per page. A run reads at most
`MAX_REQUESTS` pages of a feed with six figures of jobs, so the snapshot is
always partial: it never closes absent jobs (`complete=False`).
"""

from __future__ import annotations

import os
import re
from urllib.parse import quote

from .base import AdapterError, ParsedJobs, RawJob, parse_json

ATS = "himalayas"
HOSTS = ("himalayas.app",)
CAREER_HOSTS = ("himalayas.app",)

FEED_URL = "https://himalayas.app/jobs/api"
PAGE_LIMIT = 20
# Five pages is the approved ceiling for one run (5 x 20 = 100 records). Raising
# it needs a new decision, not a bigger number here.
MAX_REQUESTS = 5

# The feed is free without a key; a key only raises the rate limit. The key is
# read from the environment by the caller and never logged.
API_KEY_ENV = "GAWE_HIMALAYAS_API_KEY"

_GUID_COMPANY = re.compile(r"^https://himalayas\.app/companies/([^/?#]+)/")


def build_url(source: dict, cursor: str | None = None) -> str:
    url = f"{FEED_URL}?limit={PAGE_LIMIT}"
    if cursor:
        url += f"&cursor={quote(cursor, safe='')}"
    return url


def headers() -> dict[str, str] | None:
    """Optional API key for a higher rate limit.

    The feed works without one. The key is read from the environment here and
    never stored on the source, logged, or returned by any endpoint.
    """
    key = (os.environ.get(API_KEY_ENV) or "").strip()
    return {"Authorization": f"Bearer {key}"} if key else None


def next_cursor(body: str) -> str | None:
    """Opaque cursor for the next page, or ``None`` at the end of the feed."""
    payload = parse_json(body)
    if not isinstance(payload, dict):
        raise AdapterError("himalayas payload is not an object")
    cursor = payload.get("nextCursor")
    return cursor if isinstance(cursor, str) and cursor else None


def _slug_from_guid(guid: str) -> str | None:
    match = _GUID_COMPANY.match(guid)
    return match.group(1) if match else None


def _company(item: dict, guid: str) -> tuple[str, bool] | None:
    """Company name and whether it came from the slug; ``None`` means drop."""
    name = str(item.get("companyName") or "").strip()
    if name:
        return name, False
    slug = _slug_from_guid(guid) or str(item.get("companySlug") or "").strip()
    if not slug:
        return None
    return slug, True


def _location(item: dict) -> str | None:
    countries = [str(value).strip() for value in item.get("locationRestrictions") or []]
    countries = [value for value in countries if value]
    # An empty list means the feed published no restriction, not that the job is
    # open worldwide. Keep the location unknown so it cannot lift the geo scope.
    return ", ".join(countries) if countries else None


def _record(item: dict) -> RawJob:
    guid = str(item.get("guid") or "").strip()
    if not guid:
        raise AdapterError("himalayas record has no guid")
    company = _company(item, guid)
    if company is None:
        raise AdapterError("missing_company")
    name, from_slug = company
    link = str(item.get("applicationLink") or "").strip()
    return RawJob(
        source_job_id=guid,
        title=str(item.get("title") or ""),
        canonical_url=guid,
        description_html=str(item.get("description") or ""),
        # Terms: the apply button uses this link unchanged. A record without one
        # keeps no apply URL rather than inventing the posting page.
        apply_url=link or None,
        location_raw=_location(item),
        work_mode_hint="remote",
        employment_type_hint=str(item.get("employmentType") or "") or None,
        # `pubDate` is "when the job was last updated"; storing it as the posting
        # date would report a different fact. O6 keeps it unknown.
        posted_at=None,
        extra={
            "company": name,
            "company_from_slug": from_slug,
            "posted_at_unknown": True,
        },
    )


def parse(body: str, source: dict) -> ParsedJobs:
    return parse_pages([body], source)


def parse_pages(bodies: list[str], source: dict) -> ParsedJobs:
    """Parse every page of one walk; duplicate guids are read once."""
    jobs: list[RawJob] = []
    skipped = 0
    reasons: dict[str, int] = {}
    seen: set[str] = set()
    for body in bodies:
        payload = parse_json(body)
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise AdapterError("himalayas payload has no jobs list")
        for item in payload["jobs"]:
            if not isinstance(item, dict):
                skipped += 1
                reasons["invalid_record"] = reasons.get("invalid_record", 0) + 1
                continue
            try:
                record = _record(item)
            except AdapterError as exc:
                reason = str(exc) or "invalid_record"
                skipped += 1
                reasons[reason] = reasons.get(reason, 0) + 1
                continue
            if record.source_job_id in seen:
                skipped += 1
                reasons["duplicate_guid"] = reasons.get("duplicate_guid", 0) + 1
                continue
            seen.add(record.source_job_id)
            jobs.append(record)
    # A page set is never the whole feed, so a run must not close absent jobs.
    return ParsedJobs(jobs, skipped=skipped, complete=False, skip_reasons=reasons)
