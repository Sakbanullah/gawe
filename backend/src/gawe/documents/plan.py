"""Deterministic document adjustment plan.

The plan says what the writer may use before anything is written: which Master CV
items are kept, summarized, or dropped, which requirement keywords the profile
can actually support, which gaps stay open, and which language the document uses.

It is built from stored data only (`fit_assessment` components and gaps plus the
profile evidence index), so it needs no model call and no cloud consent. The plan
is bound to one posting version and one profile version; a newer version makes it
`outdated` instead of silently reusing stale reasoning.

The plan body is candidate data. It is never logged.
"""

from __future__ import annotations

import hashlib
import json
import re

from ..db.repo import Connection
from ..master_cv import new_id, now_iso
from ..profile.store import ProfileStore

KINDS = ("keep", "summarize", "drop")
STATUSES = ("draft", "approved", "rejected")
# A role or skill with no keyword overlap is dropped only when the profile has
# more material than a one-page CV can hold.
MAX_KEEP_ROLES = 3
MAX_KEEP_SKILLS = 12
MAX_KEYWORDS = 40
TOKEN = re.compile(r"[a-z0-9+#.]+")
STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is",
        "it", "of", "on", "or", "that", "the", "to", "with", "you", "your", "we",
        "will", "have", "has", "this", "our", "their", "they", "who", "what",
    }
)
# Indonesian postings dominate this product, so the detector covers both.
INDONESIAN = frozenset(
    {"dan", "yang", "untuk", "dengan", "dari", "kami", "anda", "kerja", "wajib",
     "persyaratan", "kualifikasi", "pengalaman", "bertanggung", "jawab"}
)


class PlanError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code


def content_hash(plan: dict) -> str:
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def detect_language(text: str, requested: str | None = None) -> str:
    """`id` when the posting reads as Indonesian, else `en`."""
    if requested in ("en", "id"):
        return requested
    tokens = set(TOKEN.findall((text or "").lower()))
    return "id" if len(tokens & INDONESIAN) >= 3 else "en"


def _tokens(text: str) -> set[str]:
    return {token for token in TOKEN.findall((text or "").lower()) if token not in STOPWORDS}


def build_plan(
    profile: dict,
    job: dict,
    fit: dict | None,
    requirements: list[dict],
    language: str | None = None,
) -> dict:
    """Compose the plan from stored assessment data and the profile evidence index.

    ``fit`` is the stored `fit_assessment` payload. A missing fit row is allowed
    for a job the rules marked eligible before scoring existed: the plan then
    keeps everything and reports no gaps rather than guessing.
    """
    content = profile.get("content") or {}
    evidence = _evidence_ids(profile.get("evidence_index") or {})
    wanted = _requirement_terms(requirements)
    gaps = list((fit or {}).get("gaps") or [])
    gap_terms = set()
    for gap in gaps:
        gap_terms |= _tokens(str(gap.get("description") or ""))

    keywords = []
    for term, requirement_ids in sorted(wanted.items()):
        supported = evidence.get(term) or []
        if not supported:
            continue
        keywords.append(
            {
                "term": term,
                "requirement_ids": requirement_ids,
                "evidence_ids": supported[:10],
            }
        )
    keyword_terms = {item["term"] for item in keywords}

    sections = []
    for role in content.get("experience") or []:
        text = " ".join(
            [str(role.get("title") or ""), str(role.get("company") or "")]
            + [str(bullet.get("text") or "") for bullet in role.get("bullets") or []]
        )
        hits = _tokens(text) & keyword_terms
        refs = _role_evidence(role)
        sections.append(
            _decision(
                "experience",
                role.get("id"),
                hits,
                refs,
                gap_terms,
                summarize_when=hits and len(role.get("bullets") or []) > 3,
            )
        )
    for skill in content.get("skills") or []:
        name = str(skill.get("name") or "")
        hits = _tokens(name) & keyword_terms
        sections.append(
            _decision(
                "skills",
                skill.get("id"),
                hits,
                list(skill.get("evidence") or []),
                gap_terms,
            )
        )
    for item in content.get("projects") or []:
        text = f"{item.get('name') or ''} {item.get('description') or ''}"
        sections.append(
            _decision(
                "projects",
                item.get("id"),
                _tokens(text) & keyword_terms,
                list(item.get("evidence") or []),
                gap_terms,
            )
        )

    sections = _limit(sections, "experience", MAX_KEEP_ROLES)
    sections = _limit(sections, "skills", MAX_KEEP_SKILLS)

    return {
        "sections": sections,
        "keywords": keywords[:MAX_KEYWORDS],
        "gaps": [
            {
                "requirement_id": gap.get("requirement_id"),
                "description": gap.get("description"),
                "evidence_ids": list(gap.get("evidence_ids") or []),
            }
            for gap in gaps
        ],
        "language": detect_language(
            f"{job.get('title') or ''} {job.get('description_text') or ''}", language
        ),
    }


def _decision(
    section: str,
    item_id: str | None,
    hits: set[str],
    evidence_ids: list[str],
    gap_terms: set[str],
    *,
    summarize_when: bool = False,
) -> dict:
    if not evidence_ids:
        decision = "drop"
        reason = "Tidak ada bukti profil untuk item ini."
    elif hits and gap_terms & hits:
        # The posting asks for this and the profile has no evidence for it, so the
        # item must not be stretched to cover the gap.
        decision = "summarize"
        reason = "Sebagian kata kunci lowongan adalah gap; ringkas tanpa klaim."
    elif summarize_when:
        decision = "summarize"
        reason = "Relevan, tetapi terlalu panjang untuk satu halaman."
    elif hits:
        decision = "keep"
        reason = "Relevan dan didukung bukti."
    else:
        decision = "drop"
        reason = "Tidak ada kata kunci lowongan yang cocok."
    return {
        "section": section,
        "item_id": item_id,
        "decision": decision,
        "reason": reason,
        "evidence_ids": evidence_ids[:10],
    }


def _limit(sections: list[dict], section: str, limit: int) -> list[dict]:
    """Keep the most supported items; the rest of that section is dropped."""
    kept = [item for item in sections if item["section"] == section and item["decision"] != "drop"]
    if len(kept) <= limit:
        return sections
    allowed = {item["item_id"] for item in kept[:limit]}
    return [
        (
            {**item, "decision": "drop", "reason": "Melebihi batas satu halaman."}
            if item["section"] == section
            and item["decision"] != "drop"
            and item["item_id"] not in allowed
            else item
        )
        for item in sections
    ]


def _requirement_terms(requirements: list[dict]) -> dict[str, list[str]]:
    """Requirement keyword -> the requirement ids that asked for it."""
    terms: dict[str, list[str]] = {}
    for requirement in requirements:
        text = " ".join(
            str(part or "")
            for part in (requirement.get("text"), requirement.get("quote"))
        )
        for token in _tokens(text):
            terms.setdefault(token, [])
            if requirement.get("requirement_id") not in terms[token]:
                terms[token].append(requirement.get("requirement_id"))
    return terms


def _role_evidence(role: dict) -> list[str]:
    refs: list[str] = []
    for bullet in role.get("bullets") or []:
        for ref in bullet.get("evidence") or bullet.get("evidence_ids") or []:
            if ref not in refs:
                refs.append(ref)
    return refs


def _evidence_ids(evidence_index: dict) -> dict[str, list[str]]:
    """Map each evidence term to the evidence ids that support it.

    The index is a mapping of evidence id to a record holding text, so the terms
    are derived from that text. Two shapes exist in stored data, so both are read.
    """
    mapping: dict[str, list[str]] = {}
    for evidence_id, record in evidence_index.items():
        if isinstance(record, dict):
            text = " ".join(
                str(record.get(key) or "") for key in ("text", "quote", "summary", "label")
            )
        else:
            text = str(record or "")
        for token in _tokens(text):
            mapping.setdefault(token, [])
            if evidence_id not in mapping[token]:
                mapping[token].append(evidence_id)
    return mapping


class DocumentPlanService:
    """Store, approve, and read the plan. No model call, no document write."""

    def __init__(self, connection: Connection, profile_store: ProfileStore) -> None:
        self._connection = connection
        self._profiles = profile_store

    def latest(self, application_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM document_plan WHERE application_id = ? "
            "ORDER BY version DESC LIMIT 1",
            (application_id,),
        ).fetchone()
        return self._payload(row) if row else None

    def create(
        self,
        application_id: str,
        job: dict,
        fit: dict | None,
        requirements: list[dict],
        language: str | None = None,
    ) -> dict:
        profile = self._profiles.require_confirmed()
        plan = build_plan(profile, job, fit, requirements, language)
        digest = content_hash(plan)
        existing = self._connection.execute(
            "SELECT * FROM document_plan WHERE application_id = ? AND content_hash = ?",
            (application_id, digest),
        ).fetchone()
        if existing is not None:
            # Same plan, same answer: re-creating it must not burn a version.
            return {**self._payload(existing), "replayed": True}
        row = self._connection.execute(
            "SELECT COALESCE(MAX(version), 0) AS version FROM document_plan "
            "WHERE application_id = ?",
            (application_id,),
        ).fetchone()
        version = int(row["version"]) + 1
        plan_id = new_id("dpl")
        timestamp = now_iso()
        with self._connection:
            self._connection.execute(
                "INSERT INTO document_plan (plan_id, application_id, job_id, "
                "job_posting_version_id, profile_version_id, version, status, plan_json, "
                "content_hash, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?)",
                (
                    plan_id,
                    application_id,
                    job["job_id"],
                    job["job_posting_version_id"],
                    profile["profile_version_id"],
                    version,
                    json.dumps(plan, ensure_ascii=False),
                    digest,
                    timestamp,
                    timestamp,
                ),
            )
        record = self._connection.execute(
            "SELECT * FROM document_plan WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        return {**self._payload(record), "replayed": False}

    def approve(
        self,
        application_id: str,
        plan_id: str,
        decision: str,
        digest: str,
        note: str | None,
    ) -> dict:
        row = self._connection.execute(
            "SELECT * FROM document_plan WHERE plan_id = ? AND application_id = ?",
            (plan_id, application_id),
        ).fetchone()
        if row is None:
            raise PlanError("not_found", "Rencana tidak ditemukan.", 404)
        if row["content_hash"] != digest:
            raise PlanError(
                "approval_hash_mismatch",
                "Isi rencana sudah berubah. Muat ulang sebelum menyetujui.",
                409,
            )
        if self._outdated(row):
            raise PlanError(
                "plan_outdated",
                "Rencana dibuat dari profil atau versi lowongan lama. Susun ulang rencana.",
                409,
            )
        previous = self._connection.execute(
            "SELECT decision FROM document_plan_approval WHERE plan_id = ? AND plan_hash = ?",
            (plan_id, digest),
        ).fetchone()
        if previous is not None and previous["decision"] == decision:
            return {**self._payload(row), "replayed": True}
        timestamp = now_iso()
        with self._connection:
            self._connection.execute(
                "INSERT INTO document_plan_approval (approval_id, plan_id, application_id, "
                "plan_hash, decision, note, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON DUPLICATE KEY UPDATE decision = VALUES(decision), note = VALUES(note), "
                "decided_at = VALUES(decided_at)",
                (
                    new_id("dpa"),
                    plan_id,
                    application_id,
                    digest,
                    decision,
                    (note or "").strip() or None,
                    timestamp,
                ),
            )
            self._connection.execute(
                "UPDATE document_plan SET status = ?, updated_at = ? WHERE plan_id = ?",
                (decision, timestamp, plan_id),
            )
        fresh = self._connection.execute(
            "SELECT * FROM document_plan WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        return {**self._payload(fresh), "replayed": False}

    def approved_for(self, application_id: str, job_posting_version_id: str) -> dict | None:
        """The approved plan a document version may be written from, if any."""
        row = self._connection.execute(
            "SELECT p.* FROM document_plan p "
            "JOIN profile_version v ON v.profile_version_id = p.profile_version_id "
            "WHERE p.application_id = ? AND p.job_posting_version_id = ? "
            "  AND p.status = 'approved' AND v.active = 1 "
            "ORDER BY p.version DESC LIMIT 1",
            (application_id, job_posting_version_id),
        ).fetchone()
        return self._payload(row) if row else None

    def _outdated(self, row: dict) -> bool:
        active = self._profiles.active()
        if active is None or active["profile_version_id"] != row["profile_version_id"]:
            return True
        job = self._connection.execute(
            "SELECT latest_version_id FROM job WHERE job_id = ?", (row["job_id"],)
        ).fetchone()
        return job is None or job["latest_version_id"] != row["job_posting_version_id"]

    def _payload(self, row: dict) -> dict:
        approval = self._connection.execute(
            "SELECT decision, note, decided_at FROM document_plan_approval "
            "WHERE plan_id = ? ORDER BY decided_at DESC LIMIT 1",
            (row["plan_id"],),
        ).fetchone()
        return {
            "plan_id": row["plan_id"],
            "application_id": row["application_id"],
            "job_id": row["job_id"],
            "job_posting_version_id": row["job_posting_version_id"],
            "profile_version_id": row["profile_version_id"],
            "version": int(row["version"]),
            "status": row["status"],
            "content_hash": row["content_hash"],
            "plan": json.loads(row["plan_json"]),
            "outdated": self._outdated(row),
            "approval": dict(approval) if approval else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
