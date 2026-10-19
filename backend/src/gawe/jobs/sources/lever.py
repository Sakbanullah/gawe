"""Lever Postings API adapter.

Docs: https://github.com/lever/postings-api
One request per site. ``api.eu.lever.co`` serves EU sites.
"""

from __future__ import annotations

from urllib.parse import quote, urlsplit

from .base import AdapterError, RawJob, parse_json

ATS = "lever"
HOSTS = ("api.lever.co", "api.eu.lever.co")
CAREER_HOSTS = ("jobs.lever.co", "jobs.eu.lever.co")


def _site(source: dict) -> tuple[str, str]:
    parts = urlsplit(source["careers_url"])
    host = (parts.hostname or "").lower()
    if host not in CAREER_HOSTS:
        raise AdapterError("lever careers_url must be a jobs.lever.co URL")
    site = parts.path.strip("/").split("/", 1)[0]
    if not site:
        raise AdapterError("lever careers_url is missing the site name")
    api_host = "api.eu.lever.co" if host == "jobs.eu.lever.co" else "api.lever.co"
    return api_host, site


def build_url(source: dict) -> str:
    api_host, site = _site(source)
    return f"https://{api_host}/v0/postings/{quote(site)}?mode=json"


def parse(body: str, source: dict) -> list[RawJob]:
    payload = parse_json(body)
    if not isinstance(payload, list):
        raise AdapterError("lever payload is not a postings list")
    jobs: list[RawJob] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            categories = item.get("categories") or {}
            jobs.append(
                RawJob(
                    source_job_id=str(item["id"]),
                    title=str(item.get("text") or ""),
                    canonical_url=str(item.get("hostedUrl") or ""),
                    description_html=str(
                        item.get("description") or item.get("descriptionPlain") or ""
                    ),
                    apply_url=item.get("applyUrl"),
                    location_raw=categories.get("location"),
                    employment_type_hint=categories.get("commitment"),
                    posted_at=item.get("createdAt"),
                )
            )
        except (KeyError, TypeError, AttributeError):
            continue
    return jobs
