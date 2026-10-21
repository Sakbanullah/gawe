"""Deterministic CV and cover letter drafts built from confirmed profile facts.

No model call happens here. Every sentence is copied from the profile or
assembled from labels plus profile values, so the draft cannot invent a fact.
Anything the profile does not provide is listed in `missing` and never guessed.

Content schema (documented in `docs/domains/DOCUMENT-GENERATION.md`):
- header: personal fields, no evidence (personal facts carry no evidence refs);
- every other factual item keeps the `evidence` ids it came from;
- `missing` lists absent information as field paths.

Approval gate: `required_missing` defines the minimum a document must carry.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SCHEMA_VERSION = 1
KINDS = ("cv", "cover_letter")
LANGUAGES = ("en", "id")
DIFF_LIMIT = 500
MAX_BULLETS = 4
MIN_BULLETS = 2

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#]{1,}")
_STOPWORDS = {
    "and",
    "the",
    "with",
    "for",
    "from",
    "that",
    "this",
    "you",
    "your",
    "our",
    "are",
    "will",
    "have",
    "has",
    "who",
    "all",
    "any",
    "can",
    "not",
    "but",
    "per",
    "kerja",
    "yang",
    "dan",
    "untuk",
    "dengan",
    "dari",
    "pada",
    "atau",
    "adalah",
    "akan",
    "tidak",
}

_LABELS = {
    "en": {
        "summary": "{title} at {company}. Core skills: {skills}.",
        "greeting": "Dear {company} hiring team,",
        "greeting_generic": "Dear hiring team,",
        "applying": "I am applying for the {title} role at {company}.",
        "experience": "At {company} I worked as {title}. {bullet}",
        "skills": "My core skills are {skills}.",
        "closing": "I would welcome the chance to discuss how this experience fits the role.",
        "signoff": "Sincerely,",
    },
    "id": {
        "summary": "{title} di {company}. Keahlian utama: {skills}.",
        "greeting": "Kepada tim rekrutmen {company},",
        "greeting_generic": "Kepada tim rekrutmen,",
        "applying": "Saya melamar posisi {title} di {company}.",
        "experience": "Di {company} saya bekerja sebagai {title}. {bullet}",
        "skills": "Keahlian utama saya adalah {skills}.",
        "closing": "Saya ingin berdiskusi tentang bagaimana pengalaman ini sesuai dengan posisi tersebut.",
        "signoff": "Hormat saya,",
    },
}


def content_hash(content: dict) -> str:
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build(
    kind: str,
    profile_content: dict,
    job: dict,
    language: str | None = None,
) -> dict:
    if kind not in KINDS:
        raise ValueError(f"unknown document kind: {kind}")
    if language is None:
        lang = "en"
    elif language in LANGUAGES:
        lang = language
    else:
        raise ValueError(f"unknown document language: {language}")
    target = {
        "job_id": job.get("job_id"),
        "job_posting_version_id": job.get("job_posting_version_id"),
        "title": job.get("title"),
        "company": job.get("company"),
    }
    header = _header(profile_content)
    experience = _experience(profile_content, job)
    skills = _skills(profile_content, job)
    if kind == "cv":
        content = _cv(lang, target, header, profile_content, experience, skills)
    else:
        content = _cover_letter(lang, target, header, experience, skills)
    content["missing"] = missing_information(content)
    return content


def missing_information(content: dict) -> list[str]:
    missing: list[str] = []
    header = content.get("header") or {}
    for field in ("full_name", "email", "phone", "location"):
        if not header.get(field):
            missing.append(f"personal.{field}")
    target = content.get("target") or {}
    for field in ("title", "company"):
        if not target.get(field):
            missing.append(f"target.{field}")
    if content.get("kind") == "cover_letter":
        if not any(
            paragraph.get("kind") == "claim"
            for paragraph in content.get("paragraphs") or []
        ):
            missing.append("paragraphs.claim")
        return missing
    for section in ("skills", "experience", "projects", "education"):
        if not content.get(section):
            missing.append(section)
    if content.get("summary") is None:
        missing.append("summary")
    return missing


def required_missing(content: dict) -> list[dict]:
    """Fields that must exist before a version can be approved or exported."""
    problems: list[dict] = []
    name = (content.get("header") or {}).get("full_name")
    if not name:
        problems.append(
            {
                "field": "header.full_name",
                "code": "missing_required_field",
                "message": "Nama lengkap wajib ada sebelum dokumen disetujui.",
            }
        )
    if content.get("kind") == "cover_letter":
        if not any(
            paragraph.get("kind") == "claim"
            for paragraph in content.get("paragraphs") or []
        ):
            problems.append(
                {
                    "field": "paragraphs.claim",
                    "code": "missing_required_section",
                    "message": "Cover letter wajib memuat minimal satu klaim berbukti.",
                }
            )
        return problems
    if not (
        content.get("experience") or content.get("projects") or content.get("education")
    ):
        problems.append(
            {
                "field": "experience|projects|education",
                "code": "missing_required_section",
                "message": "Minimal satu pengalaman, proyek, atau pendidikan wajib ada.",
            }
        )
    return problems


def diff_against_profile(content: dict, profile_content: dict) -> dict:
    """Diff of a first version against the Master CV facts it was tailored from."""
    if content.get("kind") == "cover_letter":
        return _diff_cover_letter(content, profile_content)
    items: list[dict] = []
    selected = 0
    omitted = 0
    summarized = 0

    document_experience = {item["id"]: item for item in content.get("experience", [])}
    for role in profile_content.get("experience", []):
        role_id = role.get("id")
        if role_id in document_experience:
            selected += 1
            items.append(
                {
                    "path": f"experience.{role_id}",
                    "change": "selected",
                    "label": f"{role.get('title')} · {role.get('company')}",
                }
            )
            kept = {bullet["id"] for bullet in document_experience[role_id].get("bullets", [])}
            for bullet in role.get("bullets", []):
                if bullet.get("id") in kept:
                    continue
                summarized += 1
                items.append(
                    {
                        "path": f"experience.{role_id}.bullets.{bullet.get('id')}",
                        "change": "summarized",
                        "before": bullet.get("text"),
                        "after": None,
                    }
                )
        else:
            omitted += 1
            items.append(
                {
                    "path": f"experience.{role_id}",
                    "change": "omitted",
                    "before": f"{role.get('title')} · {role.get('company')}",
                }
            )

    document_skills = {item["id"] for item in content.get("skills", [])}
    for skill in profile_content.get("skills", []):
        if skill.get("id") in document_skills:
            selected += 1
            items.append(
                {"path": f"skills.{skill.get('id')}", "change": "selected", "label": skill.get("name")}
            )
        else:
            omitted += 1
            items.append(
                {
                    "path": f"skills.{skill.get('id')}",
                    "change": "omitted",
                    "before": skill.get("name"),
                }
            )

    for section in ("projects", "education", "certifications", "languages"):
        included = {item.get("id") for item in content.get(section, [])}
        for item in profile_content.get(section, []):
            if item.get("id") in included:
                selected += 1
            else:
                omitted += 1
                items.append(
                    {
                        "path": f"{section}.{item.get('id')}",
                        "change": "omitted",
                        "before": _item_label(section, item),
                    }
                )

    return {
        "base": "master_cv",
        "base_document_version_id": None,
        "counts": {"selected": selected, "omitted": omitted, "summarized": summarized},
        "items": items[:DIFF_LIMIT],
    }


def _diff_cover_letter(content: dict, profile_content: dict) -> dict:
    used: set[str] = set()
    for paragraph in content.get("paragraphs") or []:
        used.update(paragraph.get("evidence_ids") or [])

    items: list[dict] = []
    selected = 0
    omitted = 0
    for role in profile_content.get("experience") or []:
        refs = {ref for bullet in role.get("bullets") or [] for ref in bullet.get("evidence") or []}
        if refs & used:
            selected += 1
            items.append(
                {
                    "path": f"experience.{role.get('id')}",
                    "change": "selected",
                    "label": f"{role.get('title')} · {role.get('company')}",
                }
            )
        else:
            omitted += 1
            items.append(
                {
                    "path": f"experience.{role.get('id')}",
                    "change": "omitted",
                    "before": f"{role.get('title')} · {role.get('company')}",
                }
            )
    for skill in profile_content.get("skills") or []:
        if set(skill.get("evidence") or []) & used:
            selected += 1
            items.append(
                {"path": f"skills.{skill.get('id')}", "change": "selected", "label": skill.get("name")}
            )
        else:
            omitted += 1
            items.append(
                {
                    "path": f"skills.{skill.get('id')}",
                    "change": "omitted",
                    "before": skill.get("name"),
                }
            )
    return {
        "base": "master_cv",
        "base_document_version_id": None,
        "counts": {"selected": selected, "omitted": omitted, "summarized": 0},
        "items": items[:DIFF_LIMIT],
    }


def diff_between(parent: dict, content: dict, parent_id: str) -> dict:
    items: list[dict] = []
    _walk(parent, content, "", items)
    counts: dict[str, int] = {}
    for item in items:
        counts[item["change"]] = counts.get(item["change"], 0) + 1
    return {
        "base": "document_version",
        "base_document_version_id": parent_id,
        "counts": counts,
        "items": items[:DIFF_LIMIT],
    }


# -- content builders --------------------------------------------------------
def _header(profile_content: dict) -> dict:
    personal = profile_content.get("personal") or {}
    return {
        "full_name": personal.get("full_name"),
        "email": personal.get("email"),
        "phone": personal.get("phone"),
        "location": personal.get("location"),
        "links": list(personal.get("links") or []),
    }


def _experience(profile_content: dict, job: dict) -> list[dict]:
    keywords = _job_keywords(job)
    roles = []
    for role in profile_content.get("experience") or []:
        bullets = []
        for bullet in role.get("bullets") or []:
            bullets.append(
                {
                    "id": bullet.get("id"),
                    "text": bullet.get("text"),
                    "evidence_ids": list(bullet.get("evidence") or []),
                    "skills": list(bullet.get("skills") or []),
                }
            )
        roles.append(
            {
                "id": role.get("id"),
                "company": role.get("company"),
                "title": role.get("title"),
                "location": role.get("location"),
                "start": role.get("start"),
                "end": role.get("end"),
                "bullets": _select_bullets(bullets, keywords),
            }
        )
    roles.sort(key=lambda role: -_relevance(_role_text(role), keywords))
    return roles


def _skills(profile_content: dict, job: dict) -> list[dict]:
    keywords = _job_keywords(job)
    skills = [
        {
            "id": skill.get("id"),
            "name": skill.get("name"),
            "proficiency": skill.get("proficiency"),
            "evidence_ids": list(skill.get("evidence") or []),
        }
        for skill in profile_content.get("skills") or []
    ]
    skills.sort(key=lambda skill: -_relevance(skill.get("name") or "", keywords))
    return skills


def _cv(
    language: str,
    target: dict,
    header: dict,
    profile_content: dict,
    experience: list[dict],
    skills: list[dict],
) -> dict:
    summary = None
    if experience:
        top = experience[0]
        if top.get("title") and top.get("company"):
            skill_names = [skill["name"] for skill in skills if skill.get("name")][:6]
            text = _LABELS[language]["summary"].format(
                title=top.get("title"),
                company=top.get("company"),
                skills=", ".join(skill_names),
            )
            evidence_ids = []
            for bullet in top.get("bullets", []):
                evidence_ids.extend(bullet.get("evidence_ids") or [])
            for skill in skills[:6]:
                evidence_ids.extend(skill.get("evidence_ids") or [])
            summary = {"text": text, "evidence_ids": _unique(evidence_ids)}
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "cv",
        "language": language,
        "target": target,
        "header": header,
        "summary": summary,
        "skills": skills,
        "experience": experience,
        "projects": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "role": item.get("role"),
                "technologies": list(item.get("technologies") or []),
                "description": item.get("description"),
                "start": item.get("start"),
                "end": item.get("end"),
                "evidence_ids": list(item.get("evidence") or []),
            }
            for item in profile_content.get("projects") or []
        ],
        "education": [
            {
                "id": item.get("id"),
                "institution": item.get("institution"),
                "degree": item.get("degree"),
                "field": item.get("field"),
                "start": item.get("start"),
                "end": item.get("end"),
                "evidence_ids": list(item.get("evidence") or []),
            }
            for item in profile_content.get("education") or []
        ],
        "certifications": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "issuer": item.get("issuer"),
                "date": item.get("date"),
                "evidence_ids": list(item.get("evidence") or []),
            }
            for item in profile_content.get("certifications") or []
        ],
        "languages": [
            {
                "id": item.get("id"),
                "name": item.get("language"),
                "level": item.get("level"),
                "evidence_ids": list(item.get("evidence") or []),
            }
            for item in profile_content.get("languages") or []
        ],
    }


def _cover_letter(
    language: str,
    target: dict,
    header: dict,
    experience: list[dict],
    skills: list[dict],
) -> dict:
    labels = _LABELS[language]
    company = target.get("company")
    title = target.get("title")
    greeting = (
        labels["greeting"].format(company=company)
        if company
        else labels["greeting_generic"]
    )
    paragraphs: list[dict] = []
    if title and company:
        paragraphs.append(
            {
                "kind": "intent",
                "text": labels["applying"].format(title=title, company=company),
                "evidence_ids": [],
            }
        )
    if experience:
        top = experience[0]
        bullet = next((item for item in top.get("bullets") or [] if item.get("text")), None)
        if bullet:
            paragraphs.append(
                {
                    "kind": "claim",
                    "text": labels["experience"].format(
                        company=top.get("company"),
                        title=top.get("title"),
                        bullet=bullet["text"],
                    ),
                    "evidence_ids": _unique(
                        list(bullet.get("evidence_ids") or [])
                        + _role_evidence(top)
                    ),
                }
            )
    skill_names = [skill["name"] for skill in skills if skill.get("name")][:8]
    if skill_names:
        paragraphs.append(
            {
                "kind": "claim",
                "text": labels["skills"].format(skills=", ".join(skill_names)),
                "evidence_ids": _unique(
                    [ref for skill in skills[:8] for ref in skill.get("evidence_ids") or []]
                ),
            }
        )
    paragraphs.append(
        {"kind": "intent", "text": labels["closing"], "evidence_ids": []}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "cover_letter",
        "language": language,
        "target": target,
        "header": header,
        "greeting": greeting,
        "paragraphs": paragraphs,
        "signoff": labels["signoff"],
        "signature": header.get("full_name"),
    }


# -- helpers -----------------------------------------------------------------
def _select_bullets(bullets: list[dict], keywords: set[str]) -> list[dict]:
    scored = [
        (
            _relevance(f"{bullet.get('text')} {' '.join(bullet.get('skills') or [])}", keywords),
            index,
        )
        for index, bullet in enumerate(bullets)
    ]
    ranked = [index for score, index in sorted(scored, key=lambda pair: (-pair[0], pair[1])) if score > 0]
    keep = set(ranked[:MAX_BULLETS])
    if len(keep) < MIN_BULLETS:
        for _, index in sorted(scored, key=lambda pair: pair[1]):
            keep.add(index)
            if len(keep) >= MIN_BULLETS:
                break
    return [bullet for index, bullet in enumerate(bullets) if index in keep]


def _role_text(role: dict) -> str:
    bullets = " ".join(bullet.get("text") or "" for bullet in role.get("bullets") or [])
    return f"{role.get('title')} {role.get('company')} {bullets}"


def _role_evidence(role: dict) -> list[str]:
    refs: list[str] = []
    for bullet in role.get("bullets") or []:
        refs.extend(bullet.get("evidence_ids") or [])
    return refs


def _job_keywords(job: dict) -> set[str]:
    text = " ".join(
        str(part or "")
        for part in (
            job.get("title"),
            job.get("description_text"),
            *[item.get("text") for item in job.get("requirements") or []],
        )
    )
    return {
        token
        for token in _TOKEN_RE.findall(text.lower())
        if token not in _STOPWORDS
    }


def _relevance(text: str, keywords: set[str]) -> int:
    tokens = set(_TOKEN_RE.findall(text.lower()))
    return len(tokens & keywords)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _item_label(section: str, item: dict) -> str:
    if section == "education":
        return " · ".join(part for part in (item.get("degree"), item.get("institution")) if part)
    if section == "languages":
        return item.get("language") or ""
    return item.get("name") or item.get("id") or ""


def _walk(before: Any, after: Any, path: str, items: list[dict]) -> None:
    if len(items) >= DIFF_LIMIT:
        return
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            child = f"{path}.{key}" if path else key
            if key not in before:
                items.append({"path": child, "change": "added", "after": after[key]})
            elif key not in after:
                items.append({"path": child, "change": "removed", "before": before[key]})
            else:
                _walk(before[key], after[key], child, items)
        return
    if isinstance(before, list) and isinstance(after, list):
        for index in range(max(len(before), len(after))):
            child = f"{path}.{index}"
            if index >= len(before):
                items.append({"path": child, "change": "added", "after": after[index]})
            elif index >= len(after):
                items.append({"path": child, "change": "removed", "before": before[index]})
            else:
                _walk(before[index], after[index], child, items)
        return
    if before != after:
        items.append(
            {"path": path, "change": "changed", "before": before, "after": after}
        )
