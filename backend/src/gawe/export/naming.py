"""File naming for exported documents (DOCUMENT-GENERATION.md §9).

The backend owns the final name. A user-supplied name only renames the output;
it never changes content or approval.
"""

from __future__ import annotations

import re

KIND_PREFIX = {"cv": "CV", "cover_letter": "Cover_Letter"}
MAX_FILENAME_LENGTH = 150
_PART_MAX = 60
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SEPARATORS = re.compile(r"[\s._-]+")


def _part(value: str | None, fallback: str) -> str:
    """One name segment: no illegal characters, underscore-separated."""
    text = _ILLEGAL.sub(" ", value or "")
    text = _SEPARATORS.sub("_", text.strip()).strip("_")
    return text[:_PART_MAX] or fallback


def suggested_filename(
    kind: str,
    candidate: str | None,
    company: str | None,
    position: str | None,
) -> str:
    prefix = KIND_PREFIX.get(kind, KIND_PREFIX["cv"])
    stem = "_".join(
        [
            prefix,
            _part(candidate, "Candidate"),
            _part(company, "Company"),
            _part(position, "Position"),
        ]
    )
    return _clamp(f"{stem}.pdf")


def with_collision_suffix(filename: str, job_id: str) -> str:
    """Stable differentiator for identical company + position pairs."""
    tail = _part(job_id.replace("job_", "")[-8:], "job")
    stem, _, extension = filename.rpartition(".")
    return _clamp(f"{stem}_{tail}.{extension}")


def _clamp(filename: str) -> str:
    if len(filename) <= MAX_FILENAME_LENGTH:
        return filename
    stem, _, extension = filename.rpartition(".")
    keep = MAX_FILENAME_LENGTH - len(extension) - 1
    return f"{stem[:keep]}.{extension}"
