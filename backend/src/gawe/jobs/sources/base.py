"""Adapter contract: fetch URL construction and payload parsing.

Adapters are pure. Network access lives in ``gawe.jobs.fetch``; persistence
lives in ``gawe.services.discovery_service``. Parsed content is untrusted data.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlsplit

from ..normalize import canonical_url as canonicalize
from ..normalize import city_of, fingerprint, norm_text
from ..priority import market_from_scope

EMPLOYMENT_TYPES = {
    "fulltime": "full_time",
    "full-time": "full_time",
    "full time": "full_time",
    "parttime": "part_time",
    "part-time": "part_time",
    "part time": "part_time",
    "contract": "contract",
    "contractor": "contract",
    "internship": "internship",
    "intern": "internship",
    "temporary": "temporary",
}


class AdapterError(ValueError):
    """Source payload or registry entry cannot be used. Message is safe."""


# HTTP requests one run spends on this source, at most. Adapters that page
# override it, and the quota reserves this many before the first request: a
# half-fetched page set is a partial snapshot, never the whole board.
MAX_REQUESTS = 1


class InvalidJob(ValueError):
    """A single record is unusable and must be skipped."""


@dataclass(frozen=True)
class RawJob:
    source_job_id: str
    title: str
    canonical_url: str
    description_html: str
    apply_url: str | None = None
    location_raw: str | None = None
    work_mode_hint: str | None = None
    employment_type_hint: str | None = None
    posted_at: str | None = None
    extra: dict = field(default_factory=dict)


class ParsedJobs(list):
    """Parsed records plus what a run needs to know about the snapshot.

    ``skipped`` counts payload entries the adapter dropped. ``complete`` says the
    payload covered the whole board: only then may a run close jobs that are
    absent from it. An adapter that pages must return ``complete=False`` for a
    partial page, otherwise a missing job looks like a closed job.
    """

    def __init__(
        self,
        jobs: list[RawJob],
        skipped: int = 0,
        complete: bool = True,
        skip_reasons: dict[str, int] | None = None,
    ) -> None:
        super().__init__(jobs)
        self.skipped = skipped
        self.complete = complete
        # Why records were dropped, so a run can report a real cause instead of
        # one anonymous count.
        self.skip_reasons = skip_reasons or {}


def company_of(raw: RawJob, fallback: str | None = None) -> str | None:
    """Per-record company name, or ``fallback`` when the payload names none.

    Adapters that publish many companies per payload read the name from the
    record. Returning ``None`` lets the adapter drop the record instead of
    inventing a company; a source label would collapse every unnamed employer
    into one dedupe block.
    """
    value = (raw.extra or {}).get("company")
    if value and str(value).strip():
        return str(value).strip()
    return fallback


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value or "")
    parser.close()
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def http_url(value: str | None, *, required: bool = True) -> str | None:
    """Accept only absolute https URLs from source data; never invent one."""
    if not value:
        if required:
            raise InvalidJob("missing url")
        return None
    parts = urlsplit(value.strip())
    if parts.scheme.lower() != "https" or not parts.hostname:
        if required:
            raise InvalidJob("url must be absolute https")
        return None
    if parts.username or parts.password:
        if required:
            raise InvalidJob("url must not contain credentials")
        return None
    return value.strip()


def work_mode_from_text(text: str | None) -> str:
    lowered = (text or "").lower()
    if "hybrid" in lowered:
        return "hybrid"
    if "remote" in lowered or "anywhere" in lowered or "worldwide" in lowered:
        return "remote"
    if lowered.strip():
        return "onsite"
    return "unknown"


def employment_type(value: str | None) -> str:
    return EMPLOYMENT_TYPES.get((value or "").strip().lower(), "unknown")


def parse_timestamp(value: str | int | float | None) -> str | None:
    """Normalise adapter timestamps to ISO 8601 UTC; unknown shapes become None."""
    from datetime import datetime, timezone

    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10**11 else value
        try:
            stamp = datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    else:
        text = str(value).strip()
        if not text:
            return None
        candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            stamp = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# Strongest signal first: "Senior Engineering Manager" is senior, not manager.
SENIORITY_WORDS = (
    ("intern", ("intern", "internship")),
    ("principal", ("principal",)),
    ("lead", ("lead",)),
    ("senior", ("senior", "sr.")),
    ("junior", ("junior", "jr.", "entry level")),
    ("mid", ("mid-level", "mid level")),
)


def seniority_from_title(title: str) -> str:
    lowered = title.lower()
    for level, words in SENIORITY_WORDS:
        if any(
            re.search(rf"\b{re.escape(word)}(?![a-z])", lowered) for word in words
        ):
            return level
    return "unknown"


def content_hash(record: dict) -> str:
    material = json.dumps(
        [
            record["title"],
            record["company"],
            record["description_text"],
            record["canonical_url"],
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def normalize(raw: RawJob, source: dict, fetched_at: str) -> dict:
    title = (raw.title or "").strip()
    if not title:
        raise InvalidJob("missing title")
    source_job_id = str(raw.source_job_id or "").strip()
    if not source_job_id:
        raise InvalidJob("missing source_job_id")
    canonical_url = canonicalize(http_url(raw.canonical_url))
    apply_url = http_url(raw.apply_url, required=False)
    description_text = html_to_text(raw.description_html)
    company = (company_of(raw, source.get("company")) or "").strip()
    if not company:
        raise InvalidJob("missing company")
    location_raw = (raw.location_raw or "").strip() or None
    mode = work_mode_from_text(raw.work_mode_hint or location_raw)
    missing = [
        name
        for name, value in (
            ("title", title),
            ("company", company),
            ("description_text", description_text),
            ("location", location_raw),
        )
        if not value
    ]
    # A record can carry a value that is not the real field: the company shown is
    # a slug, or the posting date is unknown. Both stay visible as gaps instead
    # of passing for data the source published.
    if raw.extra.get("company_from_slug"):
        missing.append("company_name")
    if raw.extra.get("posted_at_unknown"):
        missing.append("posted_at")
    if raw.extra.get("snippet_only"):
        # A card teaser has no readable requirements, so the UI must say why the
        # job cannot be judged instead of showing an empty fit.
        missing.append("snippet_only")
    record = {
        "source_id": source["source_id"],
        "source_job_id": source_job_id[:255],
        "title": title[:300],
        "company": company[:300],
        "description_text": description_text[:87381],
        "description_truncated": len(description_text) > 87381,
        "canonical_url": canonical_url,
        "apply_url": apply_url,
        "apply_url_status": "available" if apply_url else "unavailable",
        "location": {"raw": location_raw, "is_remote": mode == "remote"},
        "work_mode": mode,
        "employment_type": employment_type(raw.employment_type_hint),
        "seniority": seniority_from_title(title),
        "market": market_from_scope(location_raw, description_text, title),
        "posted_at": parse_timestamp(raw.posted_at),
        "fetched_at": fetched_at,
        "priority_tier": "unclassified",
        "priority_reason": None,
        "priority_confidence": "unknown",
        "requirements": [],
        "duplicate_of": None,
        "completeness": {
            "missing_fields": missing,
            "fetched_at": fetched_at,
            "stale": False,
        },
    }
    record["content_hash"] = content_hash(record)
    record["fingerprint"] = fingerprint(record)
    return record


def parse_json(body: str) -> dict | list:
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise AdapterError("source returned invalid JSON") from exc
