"""Deterministic synthetic extraction provider for Phase 2A.

No network. It reads the locator-prefixed CV text from the prompt and returns a
synthetic profile JSON. Quotes are copied verbatim from the source lines, so
the quote validator runs for real. This is a test double, not evidence of
extraction quality (see `llm-client.md` §8).
"""

from __future__ import annotations

import json
import re

from .base import Call, Completion, ProviderError

LINE_RE = re.compile(r"^(?P<locator>[A-Za-z0-9:._-]+) \| (?P<text>.*)$")
PHONE_RE = re.compile(r"\+?\d[\d\s()-]{6,}\d")
SECTION_ALIASES = {
    "experience": "experience",
    "work experience": "experience",
    "education": "education",
    "projects": "projects",
    "skills": "skills",
    "certifications": "certifications",
    "languages": "languages",
    "work authorization": "work authorization",
    "work preferences": "work preferences",
}
DATE_RANGE_RE = re.compile(
    r"^(?P<start>\d{4}(?:-\d{2})?)\s*[–-]\s*(?P<end>\d{4}(?:-\d{2})?|present|now)\s*(?:,\s*(?P<place>.+))?$",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL_RE = re.compile(r"https?://\S+")


class SyntheticExtractProvider:
    """Extraction test double. Other roles are refused, not faked.

    A document call answered with profile JSON would look like a writer bug in
    the logs. Refusing keeps the failure where it belongs: this double only
    covers `extract`.
    """

    provider_id = "fake"
    SUPPORTED_ROLES = {"extract"}

    def __init__(self) -> None:
        self.calls: list[Call] = []

    def complete(self, call: Call) -> Completion:
        self.calls.append(call)
        if call.role not in self.SUPPORTED_ROLES:
            raise ProviderError("provider_not_configured", retryable=False)
        text = "\n".join(message.get("content", "") for message in call.messages)
        inside = re.findall(r"<untrusted>(.*?)</untrusted>", text, flags=re.DOTALL)
        body = inside[-1] if inside else text
        payload = _extract(body)
        raw = json.dumps(payload)
        return Completion(text=raw, input_tokens=len(text) // 4, output_tokens=len(raw) // 4)


def _extract(body: str) -> dict:
    lines: list[tuple[str, str]] = []
    for raw in body.splitlines():
        match = LINE_RE.match(raw.strip())
        if match:
            lines.append((match.group("locator"), match.group("text").strip()))

    evidence: dict[str, dict] = {}
    counter = {"n": 0}

    def cite(locator: str, quote: str) -> str:
        counter["n"] += 1
        evidence_id = f"ev_syn_{counter['n']:03d}"
        locator_parts = locator.split(":")
        page = None
        if locator_parts[0].startswith("p") and locator_parts[0][1:].isdigit():
            page = int(locator_parts[0][1:])
        evidence[evidence_id] = {
            "evidence_id": evidence_id,
            "source": "cv",
            "doc_id": "pending",
            "locator": {"page": page, "section": None, "block_id": locator},
            "quote": quote[:2000],
            "declared_at": None,
        }
        return evidence_id

    profile: dict = {
        "schema_version": 1,
        "personal": {"full_name": None, "email": None, "phone": None, "location": None, "links": []},
        "education": [],
        "experience": [],
        "skills": [],
        "projects": [],
        "certifications": [],
        "languages": [],
        "awards": [],
        "work_authorization": [],
        "work_preferences": {
            "relocation": "unknown",
            "relocation_notes": None,
            "preferred_locations": [],
            "work_modes": [],
        },
        "evidence_index": evidence,
        "conflicts": [],
    }

    section: str | None = None
    current: dict | None = None

    for locator, text in lines:
        if text.startswith("#"):
            heading = text.lstrip("#").strip()
            level = len(text) - len(text.lstrip("#"))
            if level <= 2:
                section = SECTION_ALIASES.get(heading.lower())
                current = None
                if level == 1 and profile["personal"]["full_name"] is None:
                    profile["personal"]["full_name"] = heading
            elif section == "experience":
                company, _, title = heading.partition("—")
                current = {
                    "id": f"exp_{len(profile['experience']) + 1}",
                    "company": company.strip() or heading,
                    "title": title.strip() or heading,
                    "location": None,
                    "start": None,
                    "end": None,
                    "bullets": [],
                    "_evidence": [cite(locator, heading)],
                }
                profile["experience"].append(current)
            elif section == "education":
                current = {
                    "id": f"edu_{len(profile['education']) + 1}",
                    "institution": heading,
                    "degree": None,
                    "field": None,
                    "start": None,
                    "end": None,
                    "_evidence": [cite(locator, heading)],
                }
                profile["education"].append(current)
            elif section == "projects":
                current = {
                    "id": f"prj_{len(profile['projects']) + 1}",
                    "name": heading,
                    "role": None,
                    "technologies": [],
                    "description": None,
                    "start": None,
                    "end": None,
                    "_evidence": [cite(locator, heading)],
                }
                profile["projects"].append(current)
            else:
                current = None
            continue

        if section is None:
            _personal(profile, locator, text, cite)
            continue

        if section in {"experience", "education", "projects"} and current is not None:
            date_range = DATE_RANGE_RE.match(text)
            if date_range:
                current["start"] = date_range.group("start")
                end = date_range.group("end")
                current["end"] = None if end.lower() in {"present", "now"} else end
                if date_range.group("place"):
                    current["location"] = date_range.group("place").strip()
                continue
            if section == "education" and text.lower().startswith("bachelor"):
                degree, _, dates = text.partition(",")
                current["degree"] = degree.strip()
                current["field"] = degree.strip().removeprefix("Bachelor of ").strip() or None
                date_range = DATE_RANGE_RE.match(dates.strip())
                if date_range:
                    current["start"] = date_range.group("start")
                    end = date_range.group("end")
                    current["end"] = None if end.lower() in {"present", "now"} else end
                continue
            bullet_text = text.lstrip("-* ").strip()
            if section == "projects":
                current["description"] = bullet_text
                current["_evidence"].append(cite(locator, bullet_text))
                continue
            if bullet_text:
                current["bullets"].append(
                    {
                        "id": f"{current['id']}_b{len(current['bullets']) + 1}",
                        "text": bullet_text,
                        "evidence": [cite(locator, bullet_text)],
                        "skills": [],
                    }
                )
            continue

        if section == "skills":
            for name in (part.strip() for part in text.lstrip("-* ").split(",")):
                if name:
                    profile["skills"].append(
                        {
                            "id": f"skill_{len(profile['skills']) + 1}",
                            "name": name,
                            "proficiency": None,
                            "evidence": [cite(locator, text.lstrip("-* "))],
                        }
                    )
            continue

        if section == "certifications":
            name, _, date = text.lstrip("-* ").partition(",")
            profile["certifications"].append(
                {
                    "id": f"cert_{len(profile['certifications']) + 1}",
                    "name": name.strip(),
                    "issuer": None,
                    "date": date.strip() or None,
                    "evidence": [cite(locator, text.lstrip("-* "))],
                }
            )
            continue

        if section == "languages":
            language, _, level = text.lstrip("-* ").partition(",")
            profile["languages"].append(
                {
                    "id": f"lang_{len(profile['languages']) + 1}",
                    "language": language.strip(),
                    "level": level.strip() or None,
                    "evidence": [cite(locator, text.lstrip("-* "))],
                }
            )
            continue

        if section == "work authorization":
            country, _, status = text.lstrip("-* ").partition(",")
            if status.strip() in {"citizen", "permit", "requires_sponsorship", "unknown"}:
                profile["work_authorization"].append(
                    {
                        "id": f"wa_{len(profile['work_authorization']) + 1}",
                        "country": country.strip(),
                        "status": status.strip(),
                        "notes": None,
                        "source": "document",
                        "evidence": [cite(locator, text.lstrip("-* "))],
                    }
                )
            continue

        if section == "work preferences":
            lowered = text.lower()
            if "relocation" in lowered:
                value = "unknown"
                for candidate in ("conditional", "yes", "no"):
                    if candidate in lowered:
                        value = candidate
                        break
                profile["work_preferences"]["relocation"] = value
                profile["work_preferences"]["relocation_notes"] = text.split(":", 1)[-1].strip()
            if "mode" in lowered:
                modes = [
                    mode
                    for mode in ("onsite", "remote", "hybrid")
                    if mode in lowered.split(":", 1)[-1].lower()
                ]
                profile["work_preferences"]["work_modes"] = modes
            continue

    for item in profile["experience"] + profile["education"] + profile["projects"]:
        item["evidence"] = item.pop("_evidence", [])
    return profile


def _personal(profile: dict, locator: str, text: str, cite) -> None:
    personal = profile["personal"]
    email = EMAIL_RE.search(text)
    if email and personal["email"] is None:
        personal["email"] = email.group(0)
    phone = PHONE_RE.search(text)
    if phone and personal["phone"] is None:
        personal["phone"] = phone.group(0).strip()
    for url in URL_RE.findall(text):
        if url not in personal["links"]:
            personal["links"].append(url)
    if "|" in text and personal["location"] is None:
        parts = [part.strip() for part in text.split("|")]
        if len(parts) >= 2 and "@" not in parts[0] and not parts[0].startswith("http"):
            personal["location"] = parts[0]
