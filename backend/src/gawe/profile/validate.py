"""Deterministic validation of extracted profile facts.

Rules enforced here (Phase 2A):
- every fact carries at least one evidence_id that resolves in evidence_index;
- a `cv` quote must occur in the source text after normalisation;
- dates are `YYYY` or `YYYY-MM` and never reversed;
- enum values fall back to a safe default instead of being invented;
- `proficiency`/`level` only survive when the source quote states them.

Rejected facts are dropped, never guessed. The report is metadata only: paths
and counts, no CV text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..ingest.types import normalize_text, quote_matches

DATE_RE = re.compile(r"^(\d{4})(-(0[1-9]|1[0-2]))?$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
URL_RE = re.compile(r"^https?://\S+$")

WA_STATUS = {"citizen", "permit", "requires_sponsorship", "unknown"}
RELOCATION = {"yes", "no", "conditional", "unknown"}
WORK_MODES = {"onsite", "remote", "hybrid"}

FACT_COLLECTIONS = (
    "education",
    "experience",
    "skills",
    "projects",
    "certifications",
    "languages",
    "awards",
    "work_authorization",
)


@dataclass
class ValidationReport:
    dropped: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "dropped_count": len(self.dropped),
            "unverified_count": len(self.unverified),
            "dropped": self.dropped[:200],
            "unverified": self.unverified[:200],
        }


def _evidence_ids(item: dict) -> list[str]:
    # `evidence` is the contract field; `evidence_ids` is a common model alias.
    refs = item.get("evidence")
    if not refs:
        refs = item.get("evidence_ids")
    return [ref for ref in refs or [] if isinstance(ref, str)]


def _valid_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and DATE_RE.match(value):
        return value
    return None


def _range_ok(start: str | None, end: str | None) -> bool:
    if start is None or end is None:
        return True
    return start <= end


def _level_supported(level: str | None, refs: list[str], evidence: dict[str, dict]) -> bool:
    if not level:
        return True
    for ref in refs:
        quote = normalize_text(evidence.get(ref, {}).get("quote", ""))
        if normalize_text(level).lower() in quote.lower():
            return True
    return False


def validate_extraction(
    raw: dict, source_text: str, doc_id: str
) -> tuple[dict, dict, list[dict], ValidationReport]:
    """Return (content, evidence_index, conflicts, report)."""
    report = ValidationReport()
    evidence: dict[str, dict] = {}

    for evidence_id, item in (raw.get("evidence_index") or {}).items():
        if not isinstance(item, dict) or not item.get("quote"):
            report.dropped.append(f"evidence_index.{evidence_id}")
            continue
        source = item.get("source") or "cv"
        if source not in {"cv", "user_declaration"}:
            report.dropped.append(f"evidence_index.{evidence_id}")
            continue
        quote = str(item["quote"])[:2000]
        if source == "cv":
            if not quote_matches(quote, source_text):
                report.unverified.append(f"evidence_index.{evidence_id}")
                continue
            locator = item.get("locator")
            if not isinstance(locator, dict):
                # Models sometimes emit the locator as a bare string; keep the quote.
                locator = {}
            evidence[evidence_id] = {
                "evidence_id": evidence_id,
                "source": "cv",
                "doc_id": doc_id,
                "locator": {
                    "page": locator.get("page"),
                    "section": locator.get("section"),
                    "block_id": locator.get("block_id"),
                    "char_start": locator.get("char_start"),
                    "char_end": locator.get("char_end"),
                },
                "quote": quote,
                "declared_at": None,
            }
        else:
            evidence[evidence_id] = {
                "evidence_id": evidence_id,
                "source": "user_declaration",
                "doc_id": None,
                "locator": None,
                "quote": quote,
                "declared_at": item.get("declared_at"),
            }

    def keep(item: dict, path: str) -> bool:
        refs = _evidence_ids(item)
        if not refs or any(ref not in evidence for ref in refs):
            report.dropped.append(path)
            return False
        item["evidence"] = refs
        return True

    personal = raw.get("personal") or {}
    email = personal.get("email")
    if email is not None and (not isinstance(email, str) or not EMAIL_RE.match(email)):
        report.dropped.append("personal.email")
        email = None
    links = [
        link
        for link in (personal.get("links") or [])
        if isinstance(link, str) and URL_RE.match(link)
    ]
    if len(links) != len(personal.get("links") or []):
        report.dropped.append("personal.links")
    content: dict[str, Any] = {
        "personal": {
            "full_name": personal.get("full_name"),
            "email": email,
            "phone": personal.get("phone"),
            "location": personal.get("location"),
            "links": links,
        }
    }

    for collection in FACT_COLLECTIONS:
        items = []
        for index, item in enumerate(raw.get(collection) or []):
            if not isinstance(item, dict) or not item.get("id"):
                report.dropped.append(f"{collection}[{index}]")
                continue
            path = f"{collection}[{index}]"
            if not keep(item, path):
                continue
            if collection in {"education", "experience", "projects"}:
                item["start"] = _valid_date(item.get("start"))
                item["end"] = _valid_date(item.get("end"))
                if not _range_ok(item.get("start"), item.get("end")):
                    report.dropped.append(f"{path}.dates")
                    item["start"] = None
                    item["end"] = None
            if collection == "experience":
                bullets = []
                for bullet_index, bullet in enumerate(item.get("bullets") or []):
                    bullet_path = f"{path}.bullets[{bullet_index}]"
                    if not isinstance(bullet, dict) or not bullet.get("text"):
                        report.dropped.append(bullet_path)
                        continue
                    if not keep(bullet, bullet_path):
                        continue
                    bullets.append(bullet)
                item["bullets"] = bullets
            if collection == "skills":
                if not _level_supported(item.get("proficiency"), item["evidence"], evidence):
                    report.dropped.append(f"{path}.proficiency")
                    item["proficiency"] = None
            if collection == "languages":
                if not _level_supported(item.get("level"), item["evidence"], evidence):
                    report.dropped.append(f"{path}.level")
                    item["level"] = None
            if collection == "work_authorization":
                if item.get("status") not in WA_STATUS:
                    report.dropped.append(f"{path}.status")
                    item["status"] = "unknown"
                if item.get("source") not in {"document", "user_declaration"}:
                    item["source"] = "document"
            items.append(item)
        content[collection] = items

    preferences = raw.get("work_preferences") or {}
    relocation = preferences.get("relocation")
    if relocation not in RELOCATION:
        report.dropped.append("work_preferences.relocation")
        relocation = "unknown"
    modes = [mode for mode in (preferences.get("work_modes") or []) if mode in WORK_MODES]
    if len(modes) != len(preferences.get("work_modes") or []):
        report.dropped.append("work_preferences.work_modes")
    content["work_preferences"] = {
        "relocation": relocation,
        "relocation_notes": preferences.get("relocation_notes"),
        "preferred_locations": [
            location for location in (preferences.get("preferred_locations") or []) if isinstance(location, str)
        ],
        "work_modes": list(dict.fromkeys(modes)),
    }

    conflicts = _valid_conflicts(raw.get("conflicts") or [], evidence, report)
    return content, evidence, conflicts, report


def _valid_conflicts(raw: list, evidence: dict[str, dict], report: ValidationReport) -> list[dict]:
    conflicts = []
    for index, conflict in enumerate(raw):
        if not isinstance(conflict, dict) or not conflict.get("path"):
            report.dropped.append(f"conflicts[{index}]")
            continue
        candidates = []
        for candidate in conflict.get("candidates") or []:
            refs = _evidence_ids(candidate) if isinstance(candidate, dict) else []
            if refs and all(ref in evidence for ref in refs):
                candidates.append({"value": candidate.get("value"), "evidence": refs})
        if len(candidates) < 2:
            report.dropped.append(f"conflicts[{index}]")
            continue
        conflicts.append(
            {
                "conflict_id": str(conflict.get("conflict_id") or f"cfl_{index + 1}")[:64],
                "path": str(conflict["path"])[:300],
                "candidates": candidates[:50],
            }
        )
    return conflicts
