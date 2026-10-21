"""Ashby Job Postings API adapter.

Docs: https://developers.ashbyhq.com
One request per job board. ``isListed: false`` records are not published jobs.
"""

from __future__ import annotations

from urllib.parse import quote, urlsplit

from .base import AdapterError, ParsedJobs, RawJob, parse_json

ATS = "ashby"
HOSTS = ("api.ashbyhq.com",)
CAREER_HOSTS = ("jobs.ashbyhq.com",)


def _board(source: dict) -> str:
    parts = urlsplit(source["careers_url"])
    if (parts.hostname or "").lower() not in CAREER_HOSTS:
        raise AdapterError("ashby careers_url must be a jobs.ashbyhq.com URL")
    board = parts.path.strip("/").split("/", 1)[0]
    if not board:
        raise AdapterError("ashby careers_url is missing the job board name")
    return board


def build_url(source: dict) -> str:
    return (
        f"https://api.ashbyhq.com/posting-api/job-board/{quote(_board(source))}"
        "?includeCompensation=true"
    )


def parse(body: str, source: dict) -> ParsedJobs:
    payload = parse_json(body)
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise AdapterError("ashby payload has no jobs list")
    jobs: list[RawJob] = []
    skipped = 0
    for item in payload["jobs"]:
        if not isinstance(item, dict) or item.get("isListed") is False:
            skipped += 1
            continue
        try:
            jobs.append(
                RawJob(
                    source_job_id=str(item["id"]),
                    title=str(item.get("title") or ""),
                    canonical_url=str(item.get("jobUrl") or ""),
                    description_html=str(item.get("descriptionHtml") or ""),
                    apply_url=item.get("applyUrl"),
                    location_raw=item.get("location"),
                    work_mode_hint=item.get("workplaceType"),
                    employment_type_hint=item.get("employmentType"),
                    posted_at=item.get("publishedAt"),
                )
            )
        except (KeyError, TypeError, AttributeError):
            skipped += 1
            continue
    return ParsedJobs(jobs, skipped)
