"""Requirement extraction from a job description.

Two paths share one output shape, so `evaluate.py`, `match/score.py`, and the
`job_requirement` table accept either:

* `extract_with_llm` asks the `extract` role for a classified list, validates
  the reply against `job.schema.json#/properties/requirements`, and drops any
  item whose quote is not in the description. It returns ``None`` when the
  model is unavailable, refuses consent, or answers unusable JSON.
* `extract` is the deterministic fallback: cue words and section headings only.

The description reaches this module as one collapsed line: ``html_to_text``
drops the markup, so headings, list items, and paragraphs arrive separated by
single spaces. The regex path can therefore only use inline headings and cue
words, which is why an Indonesian bullet list without a standard heading reads
as nothing there.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from ..ingest.types import quote_matches
from ..llm.prompts import PromptNotFound, load_prompt_with_schema, load_schema, render
from .normalize import norm_text

logger = logging.getLogger(__name__)

LLM_PROMPT_ID = "parse_requirements"
# A reply for one description; 200 requirements of ~15 tokens still fit.
LLM_MAX_TOKENS = 4000
# Below this length the text is a card teaser, not a description worth a call.
LLM_MIN_DESCRIPTION_CHARS = 200
LLM_KINDS = {"must_have", "nice_to_have", "responsibility", "constraint"}

MUST_CUE = re.compile(
    r"\b(required?|requires?(?!\s*[.,;!?])|requiring|must|minimum|at least|proficien\w*|"
    r"strong|solid|hands[- ]on|expert\w*)\b",
    re.IGNORECASE,
)
# Bare "plus", "bonus", and "advantage" matched ordinary benefit prose
# ("... plus local statutory holidays"), so only phrase forms count.
NICE_CUE = re.compile(
    r"\b(nice[- ]to[- ]have|preferred|a plus|is a plus|bonus points?|"
    r"desirable|advantageous|ideally)\b",
    re.IGNORECASE,
)
RESPONSIBILITY_CUE = re.compile(
    r"\b(you will|you'll|you’ll|you would|you’d|day[- ]to[- ]day|in this role)\b",
    re.IGNORECASE,
)
# A sentence that starts with the candidate as the actor describes the job, not
# a gate: "You'll work across pre-sales ... in English and Portuguese".
RESPONSIBILITY_START = re.compile(
    r"^(?:you(?:'|’)?ll|you will|you would|you(?:'|’)?d|"
    r"as an? [^.]{0,60}?, you(?:'|’)?ll)\b",
    re.IGNORECASE,
)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|[\r\n]+|(?<=[;])\s+")
YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?|tahun)\b", re.IGNORECASE)

CATEGORIES = (
    ("work_authorization", r"\b(authori[sz]ed to work|right to work|work permit|"
                           r"visa|sponsorship|work authori[sz]ation|eligible to work)\b"),
    ("location", r"\b(onsite|on-site|hybrid|relocat\w*|based in|must reside|"
                 r"located in|office in)\b"),
    ("language", r"\b(english|indonesian|bahasa|fluent|language)\b"),
    # "a high degree of ownership" is not an education gate; require a real
    # degree phrase. Same for "experience": only an explicit year count is a
    # years gate, everything else is a skill and belongs to the fit score.
    ("education", r"\b(bachelor\w*|master(?:'s|’s)?\b|degree (?:in|from)|"
                  r"university degree|sarjana|s1|s2|diploma)\b"),
    ("certification", r"\b(certifi\w*|licensed|license|accredited)\b"),
    ("timezone", r"\b(time ?zone|utc|gmt|overlap)\b"),
    ("travel", r"\b(travel|travelling|traveling)\b"),
)

# Only a missing skill can block eligibility (D25). Experience is recorded as a
# check but never blocks: the user may judge seniority themselves. Credentials
# (education, certification, work authorization, language) and logistics
# (location, timezone, travel) are checks too; they feed the fit score.
ELIGIBILITY_CATEGORIES = {"other"}

# (section, pattern, anchored). Anchored patterns are ordinary words that also
# occur inside sentences, so they must start the text or follow punctuation.
HEADINGS = (
    ("responsibilities", re.compile(r"\bwhat you(?:'|’)?ll do\b", re.I), False),
    ("responsibilities", re.compile(r"\bwhat you(?:'|’)?ll be working on\b", re.I), False),
    ("responsibilities", re.compile(r"\byour responsibilities\b", re.I), False),
    ("responsibilities", re.compile(r"\bresponsibilities\b", re.I), True),
    ("requirements", re.compile(r"\bwhat you(?:'|’)?ll bring\b", re.I), False),
    ("requirements", re.compile(r"\bwhat we(?:'|’)?re looking for\b", re.I), False),
    ("requirements", re.compile(r"\bwhat you(?:'|’)?ll need\b", re.I), False),
    ("requirements", re.compile(r"\bwho you are\b", re.I), False),
    ("requirements", re.compile(r"\babout you\b", re.I), False),
    ("requirements", re.compile(r"\brequirements\b", re.I), True),
    ("requirements", re.compile(r"\bqualifications\b", re.I), True),
    ("requirements", re.compile(r"\bmust[- ]haves?\b", re.I), True),
    ("nice_to_have", re.compile(r"\bnice[- ]to[- ]have\b", re.I), False),
    ("nice_to_have", re.compile(r"\bpreferred qualifications?\b", re.I), False),
    ("nice_to_have", re.compile(r"\bbonus points?\b", re.I), False),
    ("benefits", re.compile(r"\bhere(?:'|’)?s what you can expect\b", re.I), False),
    ("benefits", re.compile(r"\bwhat we offer\b", re.I), False),
    ("benefits", re.compile(r"\bbenefits include\b", re.I), False),
    ("benefits", re.compile(r"\bperks and benefits\b", re.I), False),
    ("benefits", re.compile(r"\bbenefits\b", re.I), True),
    ("benefits", re.compile(r"\bperks\b", re.I), True),
    ("benefits", re.compile(r"\bcompensation\b", re.I), True),
    ("eeo", re.compile(r"\bequal (?:employment )?opportunit\w*\b", re.I), False),
    ("eeo", re.compile(r"\beeo\b", re.I), False),
    ("eeo", re.compile(r"\baffirmative action\b", re.I), False),
    ("about", re.compile(r"\babout (?:us|the team|the company)\b", re.I), False),
    ("about", re.compile(r"\bour mission\b", re.I), False),
    ("how_to_apply", re.compile(r"\bhow to apply\b", re.I), False),
)

EXCLUDED_SECTIONS = {"benefits", "eeo", "about", "how_to_apply"}
REQUIREMENT_SECTIONS = {"requirements", "nice_to_have"}
RESPONSIBILITY_SECTIONS = {"responsibilities"}

# A heading is followed by a colon, a list item, or a capitalised word. Prose
# such as "we care about you joining" must not switch the section.
_AFTER_HEADING = re.compile(r"\s*([A-Za-z])")

BOILERPLATE = re.compile(
    r"\b(equal (?:employment )?opportunit\w*|eeo\b|affirmative action|"
    r"(?:we|does not) do not discriminate|does not discriminate|"
    r"regardless of (?:race|religion|gender|age|disability|national origin)|"
    r"all qualified applicants|reasonable accommodation|"
    r"not expected to (?:have|know))\b",
    re.IGNORECASE,
)
# Only used outside a requirement section, and only when the sentence carries
# no requirement cue, so a finance role asking for equity experience survives.
BENEFIT = re.compile(
    r"\b(competitive salary|salary and equity|equity|401\(k\)|health insurance|"
    r"dental|vision|paid time off|unlimited pto|parental leave|stipend|"
    r"stock options|wellness|commuter)\b",
    re.IGNORECASE,
)

MAX_REQUIREMENTS = 200


def extract(description_text: str) -> list[dict]:
    """Return requirement dicts with a stable id derived from category and text."""
    requirements: list[dict] = []
    seen: set[str] = set()
    for section, body in _segments(description_text or ""):
        if section in EXCLUDED_SECTIONS or section in RESPONSIBILITY_SECTIONS:
            continue
        for raw in SENTENCE_SPLIT.split(body):
            sentence = " ".join(raw.split()).strip(" -•\t")
            if len(sentence) < 8:
                continue
            if BOILERPLATE.search(sentence):
                continue
            if BENEFIT.search(sentence) and not (
                MUST_CUE.search(sentence) or YEARS.search(sentence)
            ):
                # An offer is not a gate: "We also offer competitive salary and
                # equity" must not become a nice-to-have. A requirement cue in
                # the same sentence still wins, so "strong equity research
                # background" survives.
                continue
            kind = _kind(sentence, section)
            if kind is None:
                continue
            category = _category(sentence) or "other"
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
                return requirements
    return requirements


def extract_with_llm(
    description_text: str, *, client, root_dir: Path | None
) -> list[dict] | None:
    """Classify requirements with the `extract` role.

    Returns ``None`` on any condition the caller must survive by falling back:
    no client, no prompt or schema file, a refusal (consent), a provider error,
    or a reply whose every item lost its quote. Only content that survives
    validation is returned, so a stored requirement always quotes the posting.
    """
    text = (description_text or "").strip()
    if client is None or root_dir is None or len(text) < LLM_MIN_DESCRIPTION_CHARS:
        return None
    try:
        prompt_id, prompt_version, body, schema_name = load_prompt_with_schema(
            root_dir, LLM_PROMPT_ID
        )
        if not schema_name:
            return None
        item_schema = load_schema(root_dir, schema_name)
    except (PromptNotFound, ValueError):
        logger.info("requirement_llm skipped: prompt_or_schema_missing")
        return None

    # The declared contract is the requirement array; the prompt answers with an
    # object that also reports `no_must_have_found`.
    reply_schema = {
        "type": "object",
        "required": ["requirements"],
        "properties": {
            "requirements": item_schema,
            "no_must_have_found": {"type": "boolean"},
        },
    }
    messages = [
        {
            "role": "system",
            "content": render(
                body, {"job_description_text": "(deskripsi lowongan ada di pesan pengguna)"}
            ),
        },
        {"role": "user", "content": "<untrusted>\n" + text + "\n</untrusted>"},
    ]
    try:
        result = client.generate(
            role="extract",
            messages=messages,
            response_schema=reply_schema,
            temperature=0.0,
            max_tokens=LLM_MAX_TOKENS,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
        )
    except Exception as exc:  # provider, consent, validation: all mean "fall back"
        # Metadata only: the description never reaches the log.
        logger.info("requirement_llm fell back: %s", type(exc).__name__)
        return None

    return _from_llm(result.object, text)


def extract_requirements(
    description_text: str, *, client=None, root_dir: Path | None = None
) -> tuple[list[dict], str]:
    """Return ``(requirements, source)``: the model when it can answer, else regex.

    ``source`` is ``"llm"``, ``"regex"``, or ``"none"`` when the description
    yielded no requirement at all. ``"none"`` is not an error: the caller keeps
    the job out of scoring instead of inventing a gate.
    """
    from_llm = extract_with_llm(description_text, client=client, root_dir=root_dir)
    if from_llm is not None:
        return from_llm, "llm"
    from_regex = extract(description_text)
    return from_regex, "regex" if from_regex else "none"


def _from_llm(reply: dict, description_text: str) -> list[dict] | None:
    """Map the reply onto the stored requirement shape; drop unsupported items.

    ``quote`` must occur in the description, because every stored requirement is
    challenged later with its own quote. An item without one is a paraphrase or
    an invention, so it is dropped rather than trimmed into something checkable.
    """
    items = reply.get("requirements")
    if not isinstance(items, list):
        return None

    requirements: list[dict] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        text = " ".join(str(item.get("text") or "").split())
        quote = " ".join(str(item.get("quote") or text).split())
        if kind not in LLM_KINDS or not text or not quote:
            continue
        if not quote_matches(quote, description_text):
            continue
        category = _category(text) or "other"
        key = norm_text(text)
        if key in seen:
            continue
        seen.add(key)
        requirements.append(
            {
                "requirement_id": _requirement_id(category, key),
                "kind": kind,
                "category": category,
                "text": text[:2000],
                "quote": quote[:2000],
                "weight": 1.0 if kind == "must_have" else 0.5,
                "constraint": _constraint(text, category),
            }
        )
        if len(requirements) >= MAX_REQUIREMENTS:
            break
    if items and not requirements:
        # Every item was unsupported. That is a failed reading, not an empty job,
        # so the caller still gets its chance at the deterministic path.
        return None
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


def _kind(sentence: str, section: str | None) -> str | None:
    """Cue words win; a requirement section supplies the default."""
    if NICE_CUE.search(sentence):
        return "nice_to_have"
    if MUST_CUE.search(sentence) or YEARS.search(sentence):
        # "You'll bring strong leadership" describes the work, not a gate; an
        # explicit year count still makes it a requirement.
        if RESPONSIBILITY_START.search(sentence) and not YEARS.search(sentence):
            return None
        return "must_have"
    if section in REQUIREMENT_SECTIONS and not RESPONSIBILITY_CUE.search(sentence):
        # Inside "Requirements" a plain list item ("Kubernetes") is still a gate;
        # inside "Nice to have" it stays optional.
        return "must_have" if section == "requirements" else "nice_to_have"
    return None


def _segments(text: str) -> list[tuple[str | None, str]]:
    """Split the collapsed description into (section, body) pairs."""
    matches: list[tuple[int, int, str]] = []
    for section, pattern, anchored in HEADINGS:
        for match in pattern.finditer(text):
            if anchored and not _starts_block(text, match.start()):
                continue
            if not _ends_heading(text, match.end()):
                continue
            matches.append((match.start(), match.end(), section))
    matches.sort()

    segments: list[tuple[str | None, str]] = []
    cursor = 0
    current: str | None = None
    for start, end, section in matches:
        if start < cursor:
            continue
        if start > cursor:
            segments.append((current, _body(text[cursor:start])))
        current = section
        cursor = end
    if cursor < len(text):
        segments.append((current, _body(text[cursor:])))
    return segments


def _body(text: str) -> str:
    """Drop the separator that follows a heading: `Requirements: ...`."""
    return text.lstrip(" \t\n:-–—")


def _starts_block(text: str, index: int) -> bool:
    if index == 0:
        return True
    return re.search(r"[.!?:;]\s+$", text[:index]) is not None


def _ends_heading(text: str, index: int) -> bool:
    rest = text[index:]
    if not rest:
        return True
    if rest[0] not in " \t:-–—\n":
        return False
    letter = _AFTER_HEADING.match(rest)
    return letter is None or letter.group(1).isupper()


def _category(sentence: str) -> str | None:
    for category, pattern in CATEGORIES:
        if re.search(pattern, sentence, re.IGNORECASE):
            return category
    return "experience" if YEARS.search(sentence) else None


def _constraint(sentence: str, category: str) -> dict | None:
    if category == "experience":
        match = YEARS.search(sentence)
        if match:
            return {"min_years": int(match.group(1))}
    return None


def _requirement_id(category: str, normalised: str) -> str:
    digest = hashlib.sha256(f"{category}|{normalised}".encode("utf-8")).hexdigest()
    return f"req_{digest[:16]}"
