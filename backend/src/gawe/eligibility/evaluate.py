"""Eligibility gate: deterministic per-requirement checks with quotes.

Rules from ELIGIBILITY-AND-SCORING.md §3: an unmet mandatory requirement makes a
job ``ineligible``; anything that cannot be verified from the profile makes it
``needs_review``. Nothing here guesses, and nothing here uses the priority tier.

Skill requirements (``category: other``) are recorded as checks because they are
part of the fit score, but they never block eligibility: PLAN.md §4.2 defines
the gate over location, work authorization, experience, qualifications, and
language.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ..jobs.requirements import ELIGIBILITY_CATEGORIES

STATUSES = ("eligible", "ineligible", "needs_review")

INDONESIA = re.compile(r"\bindonesia\b", re.IGNORECASE)
EU = re.compile(r"\b(eu|european union|europe|eea|schengen)\b", re.IGNORECASE)
US = re.compile(r"\b(united states|u\.s\.|usa|us)\b", re.IGNORECASE)
SPONSORSHIP = re.compile(r"\b(sponsor\w*|visa support|relocation support)\b", re.IGNORECASE)
ONSITE = re.compile(r"\b(onsite|on-site|hybrid|in[- ]office)\b", re.IGNORECASE)
DEGREE = re.compile(r"\b(bachelor\w*|master\w*|degree|sarjana|s1|s2|diploma)\b", re.IGNORECASE)
CERT = re.compile(r"\b(certifi\w*|licensed|license)\b", re.IGNORECASE)
ENGLISH = re.compile(r"\benglish\b", re.IGNORECASE)
INDONESIAN = re.compile(r"\b(indonesian|bahasa)\b", re.IGNORECASE)


def evaluate(requirements: list[dict], profile: dict, job: dict) -> dict:
    """Return ``{status, checks, confidence, reason_summary}`` for one job."""
    facts = _facts(profile)
    checks = [_check(requirement, facts, job) for requirement in requirements]
    blocking = [
        check
        for check in checks
        if _is_blocking(check) and check["result"] != "met"
    ]
    if any(check["result"] == "not_met" for check in blocking):
        status = "ineligible"
    elif blocking:
        status = "needs_review"
    elif not any(requirement["kind"] == "must_have" for requirement in requirements):
        # ELIGIBILITY-AND-SCORING.md §8: no must-have means nothing was verified.
        status = "needs_review"
    else:
        status = "eligible"
    return {
        "status": status,
        "checks": checks,
        "confidence": _confidence(requirements, checks, job),
        "reason_summary": _summary(status, blocking),
    }


def _check(requirement: dict, facts: dict, job: dict) -> dict:
    category = requirement["category"]
    if category == "work_authorization":
        result, ref, evidence, reason = _work_authorization(requirement, facts, job)
    elif category == "location":
        result, ref, evidence, reason = _location(requirement, facts, job)
    elif category == "experience":
        result, ref, evidence, reason = _experience(requirement, facts)
    elif category == "education":
        result, ref, evidence, reason = _education(facts)
    elif category == "certification":
        result, ref, evidence, reason = _certification(requirement, facts)
    elif category == "language":
        result, ref, evidence, reason = _language(requirement, facts)
    else:
        result, ref, evidence, reason = _skill(requirement, facts)
    return {
        "requirement_id": requirement["requirement_id"],
        "category": category,
        "kind": requirement["kind"],
        "result": result,
        "job_quote": requirement["quote"],
        "profile_ref": ref,
        "evidence_refs": evidence,
        "reason": reason,
    }


def _is_blocking(check: dict) -> bool:
    """Only mandatory requirements can block eligibility."""
    return check["kind"] == "must_have" and check["category"] in ELIGIBILITY_CATEGORIES


def _work_authorization(requirement: dict, facts: dict, job: dict):
    quote = requirement["quote"]
    target = _authorization_target(quote, job)
    if target is None:
        return (
            "unknown",
            "work_authorization",
            [],
            "Lowongan menyebut izin kerja tanpa menyatakan negaranya.",
        )
    entry = facts["authorization"].get(target)
    if entry is not None and entry["status"] in {"citizen", "permit"}:
        return (
            "met",
            entry["id"],
            entry["evidence"],
            f"Profil menyatakan izin kerja/keanggotaan untuk {target}.",
        )
    if SPONSORSHIP.search(quote):
        return (
            "unknown",
            entry["id"] if entry else "work_authorization",
            entry["evidence"] if entry else [],
            "Lowongan menyebut sponsor/visa; status izin belum dipastikan.",
        )
    if entry is not None and entry["status"] == "requires_sponsorship":
        return (
            "not_met",
            entry["id"],
            entry["evidence"],
            f"Profil menyatakan butuh sponsor untuk {target}; lowongan tidak menawarkannya.",
        )
    if facts["authorization"]:
        return (
            "not_met",
            "work_authorization",
            facts["authorization_evidence"],
            f"Profil tidak menyatakan izin kerja untuk {target}.",
        )
    return (
        "unknown",
        "work_authorization",
        [],
        f"Profil belum menyatakan status izin kerja untuk {target}.",
    )


def _location(requirement: dict, facts: dict, job: dict):
    quote = requirement["quote"]
    if not ONSITE.search(quote) and not job.get("location_raw"):
        return ("unknown", "location", [], "Persyaratan lokasi tidak dapat dibaca.")
    job_city = _city(job.get("location_raw"))
    profile_city = _city(facts["location"])
    if job_city and profile_city and job_city == profile_city:
        return ("met", "personal.location", facts["location_evidence"], "Kota profil sama dengan lokasi lowongan.")
    relocation = facts["relocation"]
    if relocation == "no":
        return (
            "not_met",
            "work_preferences.relocation",
            [],
            "Profil menyatakan tidak bersedia relokasi dan lokasi berbeda.",
        )
    return (
        "unknown",
        "work_preferences.relocation",
        [],
        "Lokasi berbeda; kesediaan relokasi belum dapat dipastikan.",
    )


def _experience(requirement: dict, facts: dict):
    min_years = (requirement.get("constraint") or {}).get("min_years")
    if min_years is None:
        return ("unknown", "experience", [], "Jumlah tahun pengalaman tidak dinyatakan jelas.")
    if facts["years"] is None:
        return ("unknown", "experience", [], "Tanggal pengalaman profil tidak lengkap.")
    evidence = facts["experience_evidence"][:10]
    if facts["years"] >= min_years:
        return (
            "met",
            "experience",
            evidence,
            f"Profil mencatat sekitar {facts['years']:.1f} tahun pengalaman.",
        )
    return (
        "not_met",
        "experience",
        evidence,
        f"Profil mencatat sekitar {facts['years']:.1f} tahun; lowongan meminta {min_years}+.",
    )


def _education(facts: dict):
    if not facts["education"]:
        return ("unknown", "education", [], "Profil tidak mencantumkan pendidikan.")
    return ("met", facts["education"][0]["id"], facts["education"][0]["evidence"], "Profil mencantumkan gelar.")


def _certification(requirement: dict, facts: dict):
    for cert in facts["certifications"]:
        if _overlap(cert["name"], requirement["quote"]):
            return ("met", cert["id"], cert["evidence"], "Sertifikasi profil cocok dengan persyaratan.")
    if not facts["certifications"]:
        return ("unknown", "certifications", [], "Profil tidak mencantumkan sertifikasi.")
    return (
        "unknown",
        "certifications",
        facts["certification_evidence"][:10],
        "Sertifikasi yang diminta tidak ditemukan di profil.",
    )


def _language(requirement: dict, facts: dict):
    quote = requirement["quote"]
    wanted = "english" if ENGLISH.search(quote) else "indonesian" if INDONESIAN.search(quote) else None
    if wanted is None:
        return ("unknown", "languages", [], "Bahasa wajib tidak dapat ditentukan.")
    for language in facts["languages"]:
        if wanted in language["language"].lower():
            return ("met", language["id"], language["evidence"], f"Profil menyatakan kemampuan {wanted}.")
    if not facts["languages"]:
        return ("unknown", "languages", [], "Profil tidak mencantumkan bahasa.")
    return (
        "not_met",
        "languages",
        facts["language_evidence"][:10],
        f"Profil tidak mencantumkan kemampuan {wanted}.",
    )


def _skill(requirement: dict, facts: dict):
    matched = [skill for skill in facts["skills"] if _overlap(skill["name"], requirement["quote"])]
    if matched:
        evidence: list[str] = []
        for skill in matched:
            evidence.extend(skill["evidence"])
        return (
            "met",
            matched[0]["id"],
            evidence[:10],
            "Skill profil disebut pada persyaratan lowongan.",
        )
    return (
        "unknown",
        "skills",
        [],
        "Persyaratan ini tidak dapat dipastikan dari profil.",
    )


def _facts(profile: dict) -> dict:
    content = profile.get("content") or {}
    return {
        "location": ((content.get("personal") or {}).get("location") or ""),
        "location_evidence": _evidence_ids(content.get("personal")),
        "relocation": ((content.get("work_preferences") or {}).get("relocation") or "unknown"),
        "authorization": {
            str(entry.get("country", "")).strip().lower(): {
                "id": entry.get("id"),
                "status": entry.get("status"),
                "evidence": list(entry.get("evidence") or []),
            }
            for entry in content.get("work_authorization") or []
            if entry.get("country")
        },
        "authorization_evidence": _evidence_ids(content.get("work_authorization")),
        "years": _years(content.get("experience") or []),
        "experience_evidence": _evidence_ids(content.get("experience")),
        "education": content.get("education") or [],
        "certifications": content.get("certifications") or [],
        "certification_evidence": _evidence_ids(content.get("certifications")),
        "languages": content.get("languages") or [],
        "language_evidence": _evidence_ids(content.get("languages")),
        "skills": content.get("skills") or [],
    }


def _evidence_ids(value) -> list[str]:
    """Collect the evidence ids the profile itself cites for these facts.

    Experience entries carry evidence on their bullets, not on the entry root,
    so nested ``bullets`` are walked as well.
    """
    found: list[str] = []
    for item in value if isinstance(value, list) else [value]:
        if not isinstance(item, dict):
            continue
        for evidence_id in item.get("evidence") or []:
            if evidence_id not in found:
                found.append(evidence_id)
        for evidence_id in _evidence_ids(item.get("bullets")):
            if evidence_id not in found:
                found.append(evidence_id)
    return found


def _years(experience: list[dict]) -> float | None:
    """Summed months of experience; None when any period is unreadable."""
    total = 0
    counted = 0
    now = datetime.now(timezone.utc)
    for entry in experience:
        start = _month(entry.get("start"))
        if start is None:
            continue
        end = _month(entry.get("end")) or (now.year * 12 + now.month)
        if end < start:
            continue
        total += end - start
        counted += 1
    if not counted:
        return None
    return total / 12


def _month(value: str | None) -> int | None:
    if not value:
        return None
    match = re.match(r"^(\d{4})-(\d{2})$", str(value))
    if not match:
        return None
    return int(match.group(1)) * 12 + int(match.group(2)) - 1


def _city(value: str | None) -> str:
    return (value or "").split(",")[0].strip().lower()


def _authorization_target(quote: str, job: dict) -> str | None:
    if INDONESIA.search(quote) or (
        job.get("market") == "indonesia" and not (EU.search(quote) or US.search(quote))
    ):
        return "indonesia"
    if EU.search(quote):
        return "eu"
    if US.search(quote):
        return "united states"
    return None


def _overlap(name: str, text: str) -> bool:
    token = name.strip().lower()
    if len(token) < 2:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", text.lower()) is not None


def _confidence(requirements: list[dict], checks: list[dict], job: dict) -> str:
    must = [item for item in requirements if item["kind"] == "must_have"]
    if len(job.get("description_text") or "") >= 400 and len(must) >= 3:
        return "high"
    if must:
        return "medium"
    return "low"


def _summary(status: str, blocking: list[dict]) -> str | None:
    if status == "eligible":
        return None
    if not blocking:
        return "Tidak ada persyaratan wajib yang dapat dievaluasi dari deskripsi."
    first = blocking[0]
    if status == "ineligible":
        return f"{first['category']}: {first['reason']}"[:500]
    return f"{first['category']} belum dapat dipastikan: {first['reason']}"[:500]
