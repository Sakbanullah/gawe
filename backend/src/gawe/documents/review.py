"""Deterministic integrity review for a document version.

This is not the isolated LLM reviewer from `DOCUMENT-GENERATION.md`; no model is
called (provider roles stay as decided in D1 but the pipeline does not depend on
a live provider). It checks what a deterministic pass can prove:

- required information exists;
- every factual claim carries at least one evidence id;
- every evidence id resolves in the profile evidence index.

Blockers and majors make the verdict `changes_required`. The user still decides
approval; findings stay attached to the version after approval.
"""

from __future__ import annotations

from .draft import required_missing


def review(content: dict, evidence_index: dict) -> dict:
    findings: list[dict] = []

    for problem in required_missing(content):
        findings.append(
            _finding(
                len(findings) + 1,
                "blocker",
                "consistency",
                quote=problem["field"],
                problem=problem["message"],
                fix="Lengkapi profil confirmed lalu buat versi dokumen baru.",
            )
        )

    for section, item_id, text, refs in _claims(content):
        if not text:
            continue
        if not refs:
            findings.append(
                _finding(
                    len(findings) + 1,
                    "major",
                    "factuality",
                    quote=text,
                    problem="Klaim tidak membawa evidence id.",
                    fix="Hapus klaim atau hubungkan ke bukti profil.",
                    section=section,
                    bullet_id=item_id,
                )
            )
            continue
        unknown = [ref for ref in refs if ref not in evidence_index]
        if unknown:
            findings.append(
                _finding(
                    len(findings) + 1,
                    "blocker",
                    "factuality",
                    quote=text,
                    problem=f"Evidence id tidak ditemukan di profil: {', '.join(str(ref) for ref in unknown[:5])}.",
                    fix="Perbaiki referensi bukti atau buat versi dari profil yang benar.",
                    section=section,
                    bullet_id=item_id,
                    evidence_refs=refs,
                )
            )

    for item in findings:
        item["location"]["doc"] = content.get("kind") or "cv"

    verdict = "pass"
    if any(item["severity"] in {"blocker", "major"} for item in findings):
        verdict = "changes_required"
    return {"verdict": verdict, "findings": findings}


def summary(findings: list[dict]) -> dict:
    counts = {"blocker": 0, "major": 0, "minor": 0, "nit": 0}
    for item in findings:
        severity = item.get("severity")
        if severity in counts:
            counts[severity] += 1
    return counts


def _claims(content: dict) -> list[tuple[str, str | None, str, list[str]]]:
    claims: list[tuple[str, str | None, str, list[str]]] = []
    if content.get("kind") == "cover_letter":
        for paragraph in content.get("paragraphs") or []:
            if paragraph.get("kind") == "claim":
                claims.append(
                    ("cover_letter", None, paragraph.get("text") or "", paragraph.get("evidence_ids") or [])
                )
        return claims
    summary = content.get("summary")
    if summary:
        claims.append(("summary", None, summary.get("text") or "", summary.get("evidence_ids") or []))
    for role in content.get("experience") or []:
        for bullet in role.get("bullets") or []:
            claims.append(
                (
                    "experience",
                    bullet.get("id"),
                    bullet.get("text") or "",
                    bullet.get("evidence_ids") or [],
                )
            )
    for project in content.get("projects") or []:
        if project.get("description"):
            claims.append(
                (
                    "projects",
                    project.get("id"),
                    project.get("description") or "",
                    project.get("evidence_ids") or [],
                )
            )
    for education in content.get("education") or []:
        label = " · ".join(
            part for part in (education.get("degree"), education.get("institution")) if part
        )
        claims.append(("education", education.get("id"), label, education.get("evidence_ids") or []))
    for certification in content.get("certifications") or []:
        claims.append(
            (
                "certifications",
                certification.get("id"),
                certification.get("name") or "",
                certification.get("evidence_ids") or [],
            )
        )
    for language in content.get("languages") or []:
        claims.append(
            (
                "languages",
                language.get("id"),
                language.get("name") or "",
                language.get("evidence_ids") or [],
            )
        )
    return claims


def _finding(
    number: int,
    severity: str,
    category: str,
    *,
    quote: str,
    problem: str,
    fix: str,
    section: str | None = None,
    bullet_id: str | None = None,
    evidence_refs: list[str] | None = None,
) -> dict:
    return {
        "finding_id": f"fnd_{number:03d}",
        "severity": severity,
        "category": category,
        "location": {"doc": "cv", "section": section, "bullet_id": bullet_id},
        "quote": (quote or "")[:2000],
        "problem": problem[:2000],
        "evidence_refs": evidence_refs or [],
        "suggested_fix": fix[:2000],
        "auto_fixable": False,
        "status": "open",
    }
