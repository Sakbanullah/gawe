"""Deterministic fact and format checks against the confirmed profile.

This is the deterministic reviewer from DOCUMENT-GENERATION.md §7, not the
isolated LLM reviewer (D9 is still open). It compares what a document *says*
with what the profile proves:

- every date, scaled number, job title, certification, and citizenship claim
  must appear in the profile;
- exaggeration vocabulary must be grounded in the profile;
- ATS rules: no layout table, no multi-page CV.

`review_text` works on rendered plain text, so the same rules apply to drafts
produced by `gawe.documents.draft` and to the seeded-defect regression fixture.
"""

from __future__ import annotations

import re

SCALE = {
    "thousand": 1_000,
    "million": 1_000_000,
    "billion": 1_000_000_000,
    "juta": 1_000_000,
    "miliar": 1_000_000_000,
}
DATE_RE = re.compile(r"\b((?:19|20)\d{2})-(0[1-9]|1[0-2])\b")
NUMBER_RE = re.compile(
    r"\b(\d[\d.,]*)\s*(thousand|million|billion|juta|miliar)\b", re.IGNORECASE
)
PAGE_RE = re.compile(r"page\s+(\d+)\s+of\s+(\d+)", re.IGNORECASE)
TABLE_RE = re.compile(r"^\s*\|.*\|.*$")
CITIZEN_RE = re.compile(r"\b(citizen|kewarganegaraan|nationality)\b", re.IGNORECASE)
CERT_HEADING_RE = re.compile(r"\b(certification|certifications|sertifikasi)\b", re.IGNORECASE)
HEADING_RE = re.compile(r"^#{1,6}\s")
ROLE_WORDS = (
    "engineer",
    "manager",
    "director",
    "analyst",
    "developer",
    "scientist",
    "designer",
    "architect",
    "consultant",
    "specialist",
    "lead",
    "principal",
    "head of",
)
TITLE_RE = re.compile(
    r"\b(?:(?:senior|staff|principal|lead|junior|chief|head\s+of)\s+)?"
    r"(?:[A-Za-z]+\s+){0,3}"
    r"(?:engineer|manager|director|analyst|developer|scientist|designer|architect|"
    r"consultant|specialist)\b",
    re.IGNORECASE,
)
# Phrase -> (severity, category). A phrase found in the profile is grounded.
EXAGGERATION = {
    "expert": ("major", "exaggeration"),
    "world-class": ("major", "exaggeration"),
    "owned": ("major", "exaggeration"),
    "company-wide": ("major", "exaggeration"),
    "managed a team of": ("major", "factuality"),
    "led a team of": ("major", "factuality"),
    "principal": ("blocker", "factuality"),
}
STOPWORDS = {
    "citizen",
    "of",
    "and",
    "the",
    "a",
    "an",
    "in",
    "for",
    "at",
    "with",
    "kewarganegaraan",
    "nationality",
}


def review_text(
    text: str,
    profile_content: dict,
    *,
    kind: str = "cv",
    page_count: int | None = None,
) -> list[dict]:
    findings: list[dict] = []
    corpus = _corpus(profile_content)
    lower_corpus = corpus.lower()
    dates = _dates(corpus)
    numbers = _numbers(corpus)
    titles = _titles(profile_content)
    companies = _companies(profile_content)
    certifications = _certifications(profile_content)

    lines = (text or "").splitlines()
    in_certifications = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        page = PAGE_RE.search(stripped)
        if page and int(page.group(2)) > 2 and kind == "cv":
            findings.append(
                _finding(
                    "major",
                    "format",
                    stripped,
                    f"CV melebihi 2 halaman ({page.group(2)} halaman).",
                    "Pangkas CV sampai maksimal 2 halaman.",
                )
            )

        if HEADING_RE.match(stripped):
            in_certifications = bool(CERT_HEADING_RE.search(stripped))
            finding = _title_mismatch(stripped, titles, companies)
            if finding is not None:
                findings.append(finding)
            continue

        if TABLE_RE.match(stripped):
            findings.append(
                _finding(
                    "major",
                    "ats",
                    stripped,
                    "Tabel layout tidak dapat dibaca ATS.",
                    "Tulis keahlian sebagai daftar satu kolom.",
                )
            )

        for match in DATE_RE.finditer(stripped):
            value = f"{match.group(1)}-{match.group(2)}"
            if value not in dates:
                findings.append(
                    _finding(
                        "blocker",
                        "factuality",
                        stripped,
                        f"Tanggal {value} tidak ada di profil.",
                        "Pakai tanggal dari profil atau hapus klaim ini.",
                    )
                )

        for match in NUMBER_RE.finditer(stripped):
            raw, scale = match.group(1), SCALE[match.group(2).lower()]
            value = _to_number(raw) * scale
            if value not in numbers:
                findings.append(
                    _finding(
                        "blocker",
                        "factuality",
                        stripped,
                        f"Angka {match.group(0).strip()} tidak ada di profil.",
                        "Pakai angka dari evidence profil atau hapus klaim ini.",
                    )
                )

        lowered = stripped.lower()
        if any(word in lowered for word in ROLE_WORDS) and any(
            company.lower() in lowered for company in companies
        ):
            finding = _title_mismatch(stripped, titles, companies)
            if finding is not None:
                findings.append(finding)

        if in_certifications and stripped.startswith(("-", "*")):
            if not _matches_certification(stripped, certifications):
                findings.append(
                    _finding(
                        "blocker",
                        "factuality",
                        stripped,
                        "Sertifikasi tidak ada di profil.",
                        "Hapus sertifikasi ini atau tambahkan buktinya ke profil.",
                    )
                )

        if CITIZEN_RE.search(stripped):
            unknown = [
                word
                for word in re.findall(r"[A-Za-z]+", stripped)
                if word.lower() not in STOPWORDS and word.lower() not in lower_corpus
            ]
            if unknown:
                findings.append(
                    _finding(
                        "blocker",
                        "factuality",
                        stripped,
                        f"Kewarganegaraan tidak didukung profil: {', '.join(unknown[:3])}.",
                        "Hapus klaim kewarganegaraan yang tidak ada di profil.",
                    )
                )

        for phrase, (severity, category) in EXAGGERATION.items():
            if phrase in lowered and phrase not in lower_corpus:
                findings.append(
                    _finding(
                        severity,
                        category,
                        stripped,
                        f"Klaim '{phrase}' tidak didukung profil.",
                        "Turunkan klaim atau tambahkan evidence ke profil.",
                    )
                )

    if page_count is not None:
        limit = 2 if kind == "cv" else 1
        if page_count > limit:
            findings.append(
                _finding(
                    "major",
                    "format",
                    f"page_count={page_count}",
                    f"PDF {page_count} halaman; batas {limit}.",
                    "Pangkas dokumen sampai batas halaman.",
                )
            )
    return _dedupe(findings)


def _normalise(text: str) -> str:
    for dash in ("\u2013", "\u2014", "\u2212"):
        text = text.replace(dash, "-")
    return " ".join(text.split())


SENIORITY = {"principal", "staff", "chief", "head", "lead", "senior", "junior", "executive"}


_SEPARATORS = (" - ", " | ", " at ", ",", ":")


def _title_mismatch(line: str, titles: set[str], companies: set[str]) -> dict | None:
    """A line naming a known employer must use the profile's exact job title."""
    text = _normalise(line).strip("#").strip()
    lowered = text.lower()
    company = next((name for name in companies if name.lower() in lowered), None)
    if company is None:
        return None
    known = {_normalise(title).lower() for title in titles}

    segments = [text]
    for separator in _SEPARATORS:
        segments = [part for segment in segments for part in segment.split(separator)]
    for segment in segments:
        candidate = segment.strip(" -|").lower()
        if not any(word in candidate.split() for word in ROLE_WORDS):
            continue
        if candidate in known:
            return None
        return _finding(
            "blocker",
            "factuality",
            line,
            "Jabatan tidak cocok dengan profil.",
            "Pakai jabatan persis seperti di profil.",
        )
    return None


# -- profile facts -----------------------------------------------------------


def to_text(content: dict) -> str:
    """Flatten draft content into the line shape `review_text` expects."""
    lines: list[str] = []
    header = content.get("header") or {}
    if header.get("full_name"):
        lines.append(f"# {header['full_name']}")
    if content.get("summary", {}).get("text"):
        lines += ["## Summary", content["summary"]["text"]]
    if content.get("skills"):
        lines += ["## Skills", ", ".join(item.get("name") or "" for item in content["skills"])]
    if content.get("experience"):
        lines.append("## Experience")
        for role in content["experience"]:
            lines.append(f"### {role.get('title')} - {role.get('company')}")
            lines.append(f"{role.get('start') or ''} - {role.get('end') or 'present'}")
            lines += [f"- {item.get('text')}" for item in role.get("bullets") or []]
    if content.get("projects"):
        lines.append("## Projects")
        for project in content["projects"]:
            lines.append(f"### {project.get('name')}")
            if project.get("description"):
                lines.append(project["description"])
    if content.get("education"):
        lines.append("## Education")
        for item in content["education"]:
            lines.append(f"### {item.get('degree')} - {item.get('institution')}")
            lines.append(f"{item.get('start') or ''} - {item.get('end') or 'present'}")
    if content.get("certifications"):
        lines.append("## Certifications")
        lines += [f"- {item.get('name')}" for item in content["certifications"]]
    if content.get("languages"):
        lines.append("## Languages")
        lines += [
            f"- {item.get('name')} ({item.get('level')})" for item in content["languages"]
        ]
    if content.get("paragraphs"):
        lines += [item.get("text") or "" for item in content["paragraphs"]]
    return "\n".join(line for line in lines if line)


def _corpus(content: dict) -> str:
    parts: list[str] = []

    def walk(value) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(content)
    return "\n".join(parts)


def _dates(corpus: str) -> set[str]:
    return {f"{match.group(1)}-{match.group(2)}" for match in DATE_RE.finditer(corpus)}


def _numbers(corpus: str) -> set[float]:
    values = {_to_number(match.group(0)) for match in re.finditer(r"\b\d[\d.,]*\b", corpus)}
    for match in NUMBER_RE.finditer(corpus):
        values.add(_to_number(match.group(1)) * SCALE[match.group(2).lower()])
    return values


def _to_number(raw: str) -> float:
    text = raw.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return -1.0


def _titles(profile: dict) -> set[str]:
    return {
        role["title"].strip()
        for role in profile.get("experience") or []
        if role.get("title")
    }


def _companies(profile: dict) -> set[str]:
    return {
        role["company"].strip()
        for role in profile.get("experience") or []
        if role.get("company")
    }


def _certifications(profile: dict) -> set[str]:
    return {
        item["name"].strip()
        for item in profile.get("certifications") or []
        if item.get("name")
    }


def _matches_certification(line: str, certifications: set[str]) -> bool:
    text = line.lstrip("-* ").strip().lower()
    return any(cert.lower()[:24] in text for cert in certifications)


def _finding(severity: str, category: str, quote: str, problem: str, fix: str) -> dict:
    return {
        "severity": severity,
        "category": category,
        "quote": quote[:300],
        "problem": problem,
        "fix": fix,
    }


def _dedupe(findings: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict] = []
    for finding in findings:
        key = (finding["category"], finding["quote"], finding["problem"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique
