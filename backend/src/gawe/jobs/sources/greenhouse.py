"""Greenhouse Job Board API adapter.

Docs: https://developers.greenhouse.io/job-board.html
One request per board token. ``content`` is HTML escaped twice (verified quirk).
"""

from __future__ import annotations

import html
from urllib.parse import quote, urlsplit

from .base import AdapterError, ParsedJobs, RawJob, parse_json

ATS = "greenhouse"
HOSTS = ("boards-api.greenhouse.io",)
CAREER_HOSTS = ("boards.greenhouse.io", "job-boards.greenhouse.io")


def _token(source: dict) -> str:
    parts = urlsplit(source["careers_url"])
    if (parts.hostname or "").lower() not in CAREER_HOSTS:
        raise AdapterError("greenhouse careers_url must be a boards.greenhouse.io URL")
    token = parts.path.strip("/").split("/", 1)[0]
    if not token:
        raise AdapterError("greenhouse careers_url is missing the board token")
    return token


def build_url(source: dict) -> str:
    return (
        f"https://boards-api.greenhouse.io/v1/boards/{quote(_token(source))}/jobs"
        "?content=true"
    )


def parse(body: str, source: dict) -> ParsedJobs:
    payload = parse_json(body)
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise AdapterError("greenhouse payload has no jobs list")
    jobs: list[RawJob] = []
    skipped = 0
    for item in payload["jobs"]:
        if not isinstance(item, dict):
            skipped += 1
            continue
        try:
            jobs.append(
                RawJob(
                    source_job_id=str(item["id"]),
                    title=str(item.get("title") or ""),
                    canonical_url=str(item.get("absolute_url") or ""),
                    description_html=html.unescape(html.unescape(item.get("content") or "")),
                    location_raw=(item.get("location") or {}).get("name"),
                )
            )
        except (KeyError, TypeError, AttributeError):
            skipped += 1
            continue
    return ParsedJobs(jobs, skipped)
