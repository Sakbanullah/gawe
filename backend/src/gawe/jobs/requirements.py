"""Deterministic requirement extraction from a job description.

PLAN.md §4.2 step 8 asks for a deterministic pre-pass before any model call.
Sentences are classified by explicit cue words only; a sentence without a
requirement cue is a responsibility and is not stored as a gate.

shortcut: no LLM classification pass yet. Add one for ambiguous requirements
when a calibrated prompt and consent path exist (D1); every check must keep its
quote.
"""

from __future__ import annotations

import hashlib
import re

from .normalize import norm_text

MUST_CUE = re.compile(
    r"\b(required?|requires?|requiring|must|minimum|at least|proficien\w*|"
    r"strong|solid|hands[- ]on|expert\w*)\b",
    re.IGNORECASE,
)
NICE_CUE = re.compile(
    r"\b(nice[- ]to[- ]have|preferred|plus|bonus|desirable|advantage\w*)\b",
    re.IGNORECASE,
)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|[\r\n]+|(?<=[;])\s+")
YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)

CATEGORIES = (
    ("work_authorization", r"\b(authori[sz]ed to work|right to work|work permit|"
                           r"visa|sponsorship|work authori[sz]ation|eligible to work)\b"),
    ("location", r"\b(onsite|on-site|hybrid|relocat\w*|based in|must reside|"
                 r"located in|office in)\b"),
    ("language", r"\b(english|indonesian|bahasa|fluent|language)\b"),
    ("education", r"\b(bachelor\w*|master\w*|degree|sarjana|s1|s2|diploma)\b"),
    ("certification", r"\b(certifi\w*|licensed|license|accredited)\b"),
    ("timezone", r"\b(time ?zone|utc|gmt|overlap)\b"),
    ("travel", r"\b(travel|travelling|traveling)\b"),
    ("experience", r"\b(experience|years?|yrs?)\b"),
)

# Only these categories can block eligibility. Skills and responsibilities feed
# the fit score instead, so a missing "nice" skill never makes a job ineligible.
ELIGIBILITY_CATEGORIES = {
    "work_authorization",
    "location",
    "experience",
    "education",
    "certification",
    "language",
    "timezone",
    "travel",
}

MAX_REQUIREMENTS = 200


def extract(description_text: str) -> list[dict]:
    """Return requirement dicts with a stable id derived from category and text."""
    requirements: list[dict] = []
    seen: set[str] = set()
    for raw in SENTENCE_SPLIT.split(description_text or ""):
        sentence = " ".join(raw.split()).strip(" -•\t")
        if len(sentence) < 8:
            continue
        kind = "nice_to_have" if NICE_CUE.search(sentence) else None
        if kind is None and (MUST_CUE.search(sentence) or YEARS.search(sentence)):
            # An explicit "5+ years" is a mandatory experience requirement
            # (PLAN.md §4.2), even without the word "required".
            kind = "must_have"
        category = _category(sentence)
        if kind is None:
            continue
        if category is None:
            category = "other"
        key = norm_text(sentence)
        if key in seen:
            continue
        seen.add(key)
        requirements.append(
            {
                "requirement_id": _requirement_id(category, key),
                "kind": kind,
                "category": category,
                "text": sentence[:2000],
                "quote": sentence[:2000],
                "weight": 1.0 if kind == "must_have" else 0.5,
                "constraint": _constraint(sentence, category),
            }
        )
        if len(requirements) >= MAX_REQUIREMENTS:
            break
    return requirements


def fallback_requirement(description_text: str) -> dict:
    """One traceable requirement so every assessment has at least one check."""
    quote = " ".join((description_text or "").split())[:2000]
    text = quote or "Lowongan tidak memuat deskripsi."
    return {
        "requirement_id": _requirement_id("other", norm_text(text)),
        "kind": "responsibility",
        "category": "other",
        "text": text,
        "quote": text,
        "weight": 0.0,
        "constraint": None,
    }


def _category(sentence: str) -> str | None:
    for category, pattern in CATEGORIES:
        if re.search(pattern, sentence, re.IGNORECASE):
            return category
    return None


def _constraint(sentence: str, category: str) -> dict | None:
    if category == "experience":
        match = YEARS.search(sentence)
        if match:
            return {"min_years": int(match.group(1))}
    return None


def _requirement_id(category: str, normalised: str) -> str:
    digest = hashlib.sha256(f"{category}|{normalised}".encode("utf-8")).hexdigest()
    return f"req_{digest[:16]}"
