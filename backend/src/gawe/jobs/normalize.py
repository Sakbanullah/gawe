"""Field normalisation shared by adapters and dedupe.

Rules from JOB-DISCOVERY.md §7 and §8: canonical URLs drop ``utm_*``,
``gh_src``, ``ref``, the fragment, and a trailing slash. The cross-source
fingerprint is
``sha256(company_norm + title_norm + location_norm + employment_type)``.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {"gh_src", "ref"}
TRACKING_PREFIXES = ("utm_",)
NON_WORD = re.compile(r"[^a-z0-9]+")
# Work-mode words carry no place, so they must never decide whether two postings
# are the same job.
GENERIC_PLACES = frozenset(
    {"remote", "anywhere", "worldwide", "global", "globally", "hybrid", "onsite", "on site"}
)


def canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
        and not key.lower().startswith(TRACKING_PREFIXES)
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/") or "/",
            urlencode(query),
            "",
        )
    )


def norm_text(value: str | None) -> str:
    return NON_WORD.sub(" ", (value or "").lower()).strip()


def city_of(location_raw: str | None) -> str:
    """First comma segment: "Jakarta, Indonesia" -> "jakarta"."""
    return norm_text((location_raw or "").split(",", 1)[0])


def location_key(location_raw: str | None) -> str:
    """First segment that names a place; work-mode words never decide identity.

    ``city_of`` reads the first comma segment, so "Remote, AMER" and
    "Remote, EMEA" both reduce to "remote" and two different regional postings
    collapse into one. A payload that names no place at all returns "anywhere",
    so its identity rests on company, title and type instead of a fake city.
    """
    for part in (location_raw or "").split(","):
        key = norm_text(part)
        if key and key not in GENERIC_PLACES:
            return key
    return "anywhere"


def fingerprint(record: dict) -> str:
    material = "|".join(
        (
            norm_text(record["company"]),
            norm_text(record["title"]),
            location_key((record.get("location") or {}).get("raw")),
            record["employment_type"],
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
