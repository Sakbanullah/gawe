"""Deterministic job dedupe.

Order from JOB-DISCOVERY.md §8: exact canonical URL, cross-source fingerprint,
then fuzzy title match inside the same company/location block. A duplicate is
recorded in ``job.duplicate_of``; nothing is deleted.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher

from .normalize import location_key, norm_text

FUZZY_THRESHOLD = 0.92
# A title that names a different region names a different posting, whatever the
# string ratio says: "(AMER)" and "(EMEA)" are four characters apart.
REGION_TOKEN = re.compile(
    r"\b(amer|emea|apac|latam|dach|benelux|nordics|"
    r"north america|south america|europe|asia|africa|oceania|"
    r"united states|usa|us|uk|canada|australia|india|japan|singapore)\b",
    re.IGNORECASE,
)
# shortcut: candidate scan is capped per job; revisit when one employer block
# grows past this size (Phase 4 scale work).
MAX_CANDIDATES = 2000
MAX_CHAIN = 8


def _root(connection, job_id: str) -> str:
    """Follow ``duplicate_of`` links so a duplicate never points at a duplicate."""
    current = job_id
    for _ in range(MAX_CHAIN):
        row = connection.execute(
            "SELECT duplicate_of FROM job WHERE job_id = ?", (current,)
        ).fetchone()
        if row is None or not row["duplicate_of"]:
            return current
        current = row["duplicate_of"]
    return current


def find_duplicate(connection, job_id: str, record: dict) -> str | None:
    found = _exact_match(connection, job_id, record)
    # A duplicate pointing back at this job means this job is the canonical one.
    return None if found == job_id else found


def _exact_match(connection, job_id: str, record: dict) -> str | None:
    row = connection.execute(
        "SELECT job_id FROM job WHERE canonical_url = ? AND job_id <> ? "
        "AND duplicate_of IS NULL AND status = 'open' ORDER BY created_at, job_id LIMIT 1",
        (record["canonical_url"], job_id),
    ).fetchone()
    if row is not None:
        return _root(connection, row["job_id"])

    # The fingerprint is a cross-source identity; two postings on one board that
    # share company, title, city, and type may still be different roles.
    row = connection.execute(
        "SELECT job_id FROM job WHERE fingerprint = ? AND job_id <> ? AND source_id <> ? "
        "AND duplicate_of IS NULL AND status = 'open' ORDER BY created_at, job_id LIMIT 1",
        (record["fingerprint"], job_id, record["source_id"]),
    ).fetchone()
    if row is not None:
        return _root(connection, row["job_id"])

    place = location_key((record.get("location") or {}).get("raw"))
    title = norm_text(record["title"])
    rows = connection.execute(
        "SELECT job_id, title, location_json FROM job "
        "WHERE company = ? AND job_id <> ? AND duplicate_of IS NULL AND status = 'open' "
        "ORDER BY created_at, job_id LIMIT ?",
        (record["company"], job_id, MAX_CANDIDATES),
    ).fetchall()
    for candidate in rows:
        location = json.loads(candidate["location_json"] or "{}")
        if location_key(location.get("raw")) != place:
            continue
        other_title = norm_text(candidate["title"])
        if _region_conflict(title, other_title):
            continue
        ratio = SequenceMatcher(None, title, other_title).ratio()
        if ratio >= FUZZY_THRESHOLD:
            return candidate["job_id"]
    return None


def _region_conflict(left: str, right: str) -> bool:
    """True when both titles name a region and the regions differ."""
    left_regions = {match.group(0).lower() for match in REGION_TOKEN.finditer(left)}
    right_regions = {match.group(0).lower() for match in REGION_TOKEN.finditer(right)}
    return bool(left_regions and right_regions and left_regions != right_regions)


def link_duplicate(connection, job_id: str, record: dict) -> str | None:
    """Store the canonical job id for a duplicate; write only when it changes."""
    duplicate_of = find_duplicate(connection, job_id, record)
    current = connection.execute(
        "SELECT duplicate_of FROM job WHERE job_id = ?", (job_id,)
    ).fetchone()
    if (current["duplicate_of"] if current else None) != duplicate_of:
        with connection:
            connection.execute(
                "UPDATE job SET duplicate_of = ? WHERE job_id = ?", (duplicate_of, job_id)
            )
    return duplicate_of
