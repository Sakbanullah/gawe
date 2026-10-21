"""Document versions: deterministic generation, revisions, review, and approval.

Phase 3D slice: no LaTeX, no PDF, no export. Approval is bound to a version id
plus its content hash; a new version never inherits an approval. Review is a
deterministic integrity pass (see `gawe.documents.review`), not an LLM reviewer.
"""

from __future__ import annotations

import base64
import binascii
import copy
import json

from ..db.repo import Connection
from ..documents import draft, review as review_rules
from ..master_cv import new_id, now_iso
from ..profile.store import ProfileStore
from .assessment_service import AssessmentService
from .tasks import TaskStore

GENERATION_STAGES = ["select_evidence", "draft", "diff"]
REVIEW_STAGES = ["review"]
MAX_REVIEW_CYCLES = 3


class DocumentError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        active_task_id: str | None = None,
        details: list[dict] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.active_task_id = active_task_id
        self.details = details or []


class DocumentService:
    def __init__(self, connection: Connection, profile_store: ProfileStore) -> None:
        self._connection = connection
        self._profiles = profile_store
        self._assessments = AssessmentService(connection, profile_store)
        self._tasks = TaskStore(connection)

    # -- generation ------------------------------------------------------
    def generate(
        self,
        application_id: str,
        kinds: list[str],
        language: str,
        template_version: str | None = None,
    ) -> dict:
        record = self._application(application_id)
        self._require_eligible(record)
        self._require_no_active_task(application_id)
        profile = self._profile(record)
        job = self._job_context(record)

        task = self._tasks.create("document_generation", GENERATION_STAGES, application_id)
        task_id = task["task_id"]
        try:
            self._tasks.start_stage(task_id, "select_evidence")
            self._tasks.finish_stage(task_id, "select_evidence")
            self._tasks.start_stage(task_id, "draft")
            drafts = {
                kind: draft.build(kind, profile["content"], job, language) for kind in kinds
            }
            self._tasks.finish_stage(task_id, "draft")
            self._tasks.start_stage(task_id, "diff")
            created: list[str] = []
            for kind, content in drafts.items():
                diff = draft.diff_against_profile(content, profile["content"])
                created.append(
                    self._insert(
                        record,
                        kind=kind,
                        content=content,
                        diff=diff,
                        parent_document_version_id=None,
                        template_version=template_version,
                        job_posting_version_id=self._job_posting_version_id(record),
                    )["document_version_id"]
                )
            self._tasks.finish_stage(task_id, "diff")
        except DocumentError as exc:
            self._tasks.fail(task_id, exc.code, exc.message, "draft")
            raise
        except Exception as exc:  # noqa: BLE001 - task must not stay processing
            self._tasks.fail(task_id, "internal_error", "Pembuatan dokumen gagal.", "draft")
            raise DocumentError(
                "internal_error", "Pembuatan dokumen gagal.", 500
            ) from exc

        self._touch_application(application_id)
        self._tasks.finish(
            task_id, "completed", result={"document_version_ids": created, "kinds": kinds}
        )
        return {"task_id": task_id, "status": "completed"}

    def regenerate(
        self,
        application_id: str,
        document_version_id: str,
        base_content_hash: str,
        reason: str,
    ) -> dict:
        record = self._application(application_id)
        parent = self._version(application_id, document_version_id)
        if parent["content_hash"] != base_content_hash:
            raise DocumentError(
                "version_conflict", "Hash versi berubah; muat ulang sebelum regenerate.", 409
            )
        self._require_eligible(record)
        self._require_no_active_task(application_id)
        profile = self._profile(record)
        job = self._job_context(record)

        task = self._tasks.create("document_generation", GENERATION_STAGES, application_id)
        task_id = task["task_id"]
        try:
            self._tasks.start_stage(task_id, "select_evidence")
            self._tasks.finish_stage(task_id, "select_evidence")
            self._tasks.start_stage(task_id, "draft")
            content = draft.build(parent["kind"], profile["content"], job, parent["content"].get("language"))
            self._tasks.finish_stage(task_id, "draft")
            self._tasks.start_stage(task_id, "diff")
            created = self._insert(
                record,
                kind=parent["kind"],
                content=content,
                diff=draft.diff_between(parent["content"], content, document_version_id),
                parent_document_version_id=document_version_id,
                template_version=parent["template_version"],
                job_posting_version_id=self._job_posting_version_id(record),
            )
            self._tasks.finish_stage(task_id, "diff")
        except DocumentError as exc:
            self._tasks.fail(task_id, exc.code, exc.message, "draft")
            raise
        except Exception as exc:  # noqa: BLE001
            self._tasks.fail(task_id, "internal_error", "Regenerate dokumen gagal.", "draft")
            raise DocumentError("internal_error", "Regenerate dokumen gagal.", 500) from exc

        self._touch_application(application_id)
        self._tasks.finish(
            task_id,
            "completed",
            result={
                "document_version_ids": [created["document_version_id"]],
                "kinds": [parent["kind"]],
                "reason": reason,
            },
        )
        return {"task_id": task_id, "status": "completed"}

    # -- revisions -------------------------------------------------------
    def revise(
        self,
        application_id: str,
        document_version_id: str,
        base_content_hash: str,
        edits: list[dict],
        note: str | None = None,
    ) -> dict:
        record = self._application(application_id)
        parent = self._version(application_id, document_version_id)
        if parent["content_hash"] != base_content_hash:
            raise DocumentError(
                "version_conflict", "Hash versi berubah; muat ulang sebelum mengedit.", 409
            )
        content = copy.deepcopy(parent["content"])
        for edit in edits:
            _apply_edit(content, edit["path"], edit["value"])
        _validate_content(content, kind=parent["kind"])
        content["missing"] = draft.missing_information(content)
        diff = draft.diff_between(parent["content"], content, document_version_id)
        if note:
            diff["note"] = note
        edit_notes = [edit.get("note") for edit in edits if edit.get("note")]
        if edit_notes:
            diff["edit_notes"] = edit_notes
        created = self._insert(
            record,
            kind=parent["kind"],
            content=content,
            diff=diff,
            parent_document_version_id=document_version_id,
            template_version=parent["template_version"],
            job_posting_version_id=parent["job_posting_version_id"],
        )
        self._touch_application(application_id)
        return created

    # -- review ----------------------------------------------------------
    def run_review(self, application_id: str, document_version_id: str) -> dict:
        record = self._application(application_id)
        version = self._version(application_id, document_version_id)
        latest = self._latest_approval(document_version_id)
        if latest is not None and latest["decision"] == "approved":
            raise DocumentError(
                "conflict",
                "Versi sudah disetujui; buat versi baru untuk review ulang.",
                409,
                details=[
                    {
                        "field": "document_version_id",
                        "code": "version_already_approved",
                        "message": "Approval yang berlaku tidak boleh ditimpa review baru.",
                    }
                ],
            )
        cycle = int(version.get("review_cycle") or 0) + 1
        if cycle > MAX_REVIEW_CYCLES:
            raise DocumentError(
                "conflict",
                "Batas 3 siklus review tercapai; buat versi baru.",
                409,
                details=[
                    {
                        "field": "document_version_id",
                        "code": "review_cycle_limit",
                        "message": "Maksimum 3 siklus review per versi.",
                    }
                ],
            )
        self._require_no_active_task(application_id)
        profile = self._profile(record)
        task = self._tasks.create("review", REVIEW_STAGES, application_id)
        task_id = task["task_id"]
        try:
            self._tasks.start_stage(task_id, "review")
            result = review_rules.review(
                version["content"], profile.get("evidence_index") or {}
            )
            self._tasks.finish_stage(task_id, "review")
        except Exception as exc:  # noqa: BLE001
            self._tasks.fail(task_id, "internal_error", "Review dokumen gagal.", "review")
            raise DocumentError("internal_error", "Review dokumen gagal.", 500) from exc

        timestamp = now_iso()
        report = {
            "document_version_id": document_version_id,
            "profile_version_id": version["profile_version_id"],
            "review_run_id": task_id,
            "cycle": cycle,
            "verdict": result["verdict"],
            "findings": result["findings"],
            "reviewed_at": timestamp,
        }
        with self._connection:
            self._connection.execute(
                "UPDATE document_version SET status = 'in_review', review_status = 'completed', "
                "review_verdict = ?, review_cycle = ?, findings_json = ?, reviewed_at = ?, "
                "updated_at = ? WHERE document_version_id = ?",
                (
                    result["verdict"],
                    cycle,
                    json.dumps(report, ensure_ascii=False),
                    timestamp,
                    timestamp,
                    document_version_id,
                ),
            )
        self._touch_application(application_id)
        self._tasks.finish(task_id, "completed", result={"verdict": result["verdict"]})
        return {"task_id": task_id, "status": "completed"}

    def findings(self, application_id: str, document_version_id: str) -> dict:
        version = self._version(application_id, document_version_id)
        if not version.get("findings"):
            raise DocumentError("not_found", "Review belum dijalankan untuk versi ini.", 404)
        return version["findings"]

    # -- approval --------------------------------------------------------
    def approve(
        self,
        application_id: str,
        document_version_id: str,
        decision: str,
        content_hash: str,
        note: str | None = None,
    ) -> tuple[dict, bool]:
        record = self._application(application_id)
        version = self._version(application_id, document_version_id)
        if (
            content_hash != version["content_hash"]
            or draft.content_hash(version["content"]) != version["content_hash"]
        ):
            raise DocumentError(
                "approval_hash_mismatch",
                "Hash konten tidak cocok dengan versi. Muat ulang versi terbaru.",
                409,
            )
        self._require_eligible(record)

        problems = draft.required_missing(version["content"])
        if problems:
            raise DocumentError(
                "conflict",
                "Data wajib belum lengkap; approval dan ekspor diblokir.",
                409,
                details=problems,
            )
        if version["review_status"] != "completed":
            raise DocumentError(
                "review_not_completed", "Review belum selesai untuk versi ini.", 409
            )
        if version.get("review_verdict") == "changes_required":
            raise DocumentError(
                "review_not_completed",
                "Review meminta perubahan; buat versi baru lalu review ulang.",
                409,
            )

        latest = self._latest_approval(document_version_id)
        if latest is not None and latest["decision"] == "approved":
            if decision == "approved" and latest["document_hash"] == content_hash:
                return self._approval_payload(latest), True
            raise DocumentError(
                "conflict",
                "Versi sudah disetujui; buat versi baru untuk keputusan lain.",
                409,
                details=[
                    {
                        "field": "document_version_id",
                        "code": "version_already_approved",
                        "message": "Approval yang berlaku tidak boleh diganti.",
                    }
                ],
            )
        if (
            latest is not None
            and latest["decision"] == decision
            and latest["document_hash"] == content_hash
        ):
            return self._approval_payload(latest), True

        approval_id = new_id("apr")
        timestamp = now_iso()
        with self._connection:
            self._connection.execute(
                "INSERT INTO document_approval (approval_id, document_version_id, "
                "application_id, profile_version_id, document_hash, kind, decision, note, "
                "decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    approval_id,
                    document_version_id,
                    application_id,
                    version["profile_version_id"],
                    content_hash,
                    version["kind"],
                    decision,
                    note,
                    timestamp,
                ),
            )
            status = "approved" if decision == "approved" else "in_review"
            self._connection.execute(
                "UPDATE document_version SET status = ?, updated_at = ? "
                "WHERE document_version_id = ?",
                (status, timestamp, document_version_id),
            )
        self._touch_application(application_id)
        row = self._connection.execute(
            "SELECT * FROM document_approval WHERE approval_id = ?", (approval_id,)
        ).fetchone()
        assert row is not None
        return self._approval_payload(dict(row)), False

    # -- reads -----------------------------------------------------------
    def list(self, application_id: str, limit: int = 50, cursor: str | None = None) -> tuple[list[dict], str | None]:
        self._application(application_id)
        rows = self._connection.execute(
            "SELECT * FROM document_version WHERE application_id = ? "
            "ORDER BY created_at DESC, document_version_id DESC",
            (application_id,),
        ).fetchall()
        records = [dict(row) for row in rows]
        if cursor:
            key = _decode_cursor(cursor)
            records = [
                record
                for record in records
                if (record["created_at"], record["document_version_id"])
                < (key["created_at"], key["document_version_id"])
            ]
        items = [self._summary(record) for record in records[:limit]]
        next_cursor = (
            _encode_cursor(records[limit - 1])
            if len(records) > limit and limit > 0
            else None
        )
        return items, next_cursor

    def get(self, application_id: str, document_version_id: str) -> dict:
        version = self._version(application_id, document_version_id)
        approval = self._latest_approval(document_version_id)
        return {
            **self._summary_row(version, approval),
            "parent_document_version_id": version.get("parent_document_version_id"),
            "content": version["content"],
            "diff": version.get("diff") or {"base": "master_cv", "items": []},
            "evidence_ids": version.get("evidence_ids") or [],
            "prompt_version": version.get("prompt_version"),
            "template_version": version.get("template_version"),
            "provider": version.get("provider"),
            "model": version.get("model"),
            "review_verdict": version.get("review_verdict"),
        }

    def summaries(self, application_id: str) -> dict:
        rows = self._connection.execute(
            "SELECT * FROM document_version WHERE application_id = ? "
            "ORDER BY created_at DESC, document_version_id DESC LIMIT 200",
            (application_id,),
        ).fetchall()
        grouped: dict[str, list[dict]] = {"cv": [], "cover_letter": []}
        for row in rows:
            record = dict(row)
            grouped.setdefault(record["kind"], []).append(self._summary(record))
        return grouped

    def counts(self, application_id: str) -> dict:
        rows = self._connection.execute(
            "SELECT kind, COUNT(*) AS total, "
            "SUM(CASE WHEN review_status != 'completed' THEN 1 ELSE 0 END) AS pending "
            "FROM document_version WHERE application_id = ? GROUP BY kind",
            (application_id,),
        ).fetchall()
        counts = {"cv_versions": 0, "cover_letter_versions": 0, "pending_review": 0}
        for row in rows:
            if row["kind"] == "cv":
                counts["cv_versions"] = int(row["total"])
            elif row["kind"] == "cover_letter":
                counts["cover_letter_versions"] = int(row["total"])
            counts["pending_review"] += int(row["pending"] or 0)
        return counts

    # -- internals -------------------------------------------------------
    def _application(self, application_id: str) -> dict:
        row = self._connection.execute(
            "SELECT * FROM application WHERE application_id = ?", (application_id,)
        ).fetchone()
        if row is None:
            raise DocumentError("not_found", "Workspace tidak ditemukan.", 404)
        return dict(row)

    def _profile(self, record: dict) -> dict:
        profile = self._profiles.get(record["profile_version_id"])
        if profile is None:
            raise DocumentError("not_found", "Versi profil workspace tidak ditemukan.", 404)
        return profile

    def _job_context(self, record: dict) -> dict:
        detail = self._assessments.detail(record["job_id"], record["profile_version_id"])
        if detail is None:
            raise DocumentError("not_found", "Job workspace belum dianalisis.", 404)
        job = dict(detail["job_detail"]["job"])
        job["description_text"] = detail["job_detail"]["description_text"]
        job["requirements"] = detail["job_detail"]["requirements"]
        return job

    def _require_eligible(self, record: dict) -> dict:
        eligibility = self._assessments.eligibility_for(
            record["job_id"], record["profile_version_id"]
        )
        if eligibility is None:
            raise DocumentError("not_found", "Eligibility belum dihitung.", 404)
        if eligibility.get("status_outdated"):
            raise DocumentError(
                "conflict",
                "Eligibility sudah outdated; analisis ulang sebelum membuat atau menyetujui dokumen.",
                409,
                details=[
                    {
                        "field": "eligibility",
                        "code": "assessment_outdated",
                        "message": "Eligibility berasal dari profil atau lowongan lama.",
                    }
                ],
            )
        if eligibility["status"] == "needs_review":
            raise DocumentError(
                "eligibility_needs_review",
                "Eligibility needs_review memblokir pembuatan dokumen.",
                409,
            )
        if eligibility["status"] != "eligible":
            raise DocumentError(
                "eligibility_not_eligible",
                "Eligibility ineligible tidak masuk alur dokumen normal.",
                409,
            )
        return eligibility

    def _require_no_active_task(self, application_id: str) -> None:
        row = self._connection.execute(
            "SELECT task_id FROM task WHERE application_id = ? "
            "AND status IN ('queued','processing') ORDER BY created_at DESC LIMIT 1",
            (application_id,),
        ).fetchone()
        if row is not None:
            raise DocumentError(
                "task_already_running",
                "Sudah ada task aktif untuk workspace ini.",
                409,
                active_task_id=row["task_id"],
            )

    def _version(self, application_id: str, document_version_id: str) -> dict:
        self._application(application_id)
        row = self._connection.execute(
            "SELECT * FROM document_version WHERE document_version_id = ? "
            "AND application_id = ?",
            (document_version_id, application_id),
        ).fetchone()
        if row is None:
            raise DocumentError("not_found", "Versi dokumen tidak ditemukan.", 404)
        return _version_row(dict(row))

    def _insert(
        self,
        record: dict,
        *,
        kind: str,
        content: dict,
        diff: dict,
        parent_document_version_id: str | None,
        template_version: str | None,
        job_posting_version_id: str,
    ) -> dict:
        version = self._next_version(record["application_id"], kind)
        document_version_id = new_id("docv")
        timestamp = now_iso()
        content_hash = draft.content_hash(content)
        evidence_ids = _evidence_ids(content)
        with self._connection:
            self._connection.execute(
                "INSERT INTO document_version (document_version_id, application_id, "
                "profile_version_id, job_posting_version_id, kind, version, "
                "parent_document_version_id, status, content_json, content_hash, diff_json, "
                "evidence_json, prompt_version, template_version, provider, model, "
                "review_status, review_verdict, review_cycle, findings_json, reviewed_at, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, "
                "NULL, ?, NULL, NULL, 'not_started', NULL, NULL, NULL, NULL, ?, ?)",
                (
                    document_version_id,
                    record["application_id"],
                    record["profile_version_id"],
                    job_posting_version_id,
                    kind,
                    version,
                    parent_document_version_id,
                    json.dumps(content, ensure_ascii=False),
                    content_hash,
                    json.dumps(diff, ensure_ascii=False),
                    json.dumps(evidence_ids, ensure_ascii=False),
                    template_version,
                    timestamp,
                    timestamp,
                ),
            )
        row = self._connection.execute(
            "SELECT * FROM document_version WHERE document_version_id = ?",
            (document_version_id,),
        ).fetchone()
        assert row is not None
        return self._summary(dict(row))

    def _job_posting_version_id(self, record: dict) -> str:
        row = self._connection.execute(
            "SELECT job_posting_version_id FROM eligibility_assessment "
            "WHERE job_id = ? AND profile_version_id = ?",
            (record["job_id"], record["profile_version_id"]),
        ).fetchone()
        if row is None:
            raise DocumentError("not_found", "Eligibility belum dihitung.", 404)
        return row["job_posting_version_id"]

    def _next_version(self, application_id: str, kind: str) -> int:
        row = self._connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 AS next FROM document_version "
            "WHERE application_id = ? AND kind = ?",
            (application_id, kind),
        ).fetchone()
        return int(row["next"])

    def _latest_approval(self, document_version_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM document_approval WHERE document_version_id = ? "
            "ORDER BY decided_at DESC, approval_id DESC LIMIT 1",
            (document_version_id,),
        ).fetchone()
        return dict(row) if row else None

    def _touch_application(self, application_id: str) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE application SET updated_at = ? WHERE application_id = ?",
                (now_iso(), application_id),
            )

    def _summary(self, record: dict) -> dict:
        return self._summary_row(_version_row(record), self._latest_approval(record["document_version_id"]))

    def _summary_row(self, version: dict, approval: dict | None) -> dict:
        approved = bool(approval and approval["decision"] == "approved")
        findings = version.get("findings") or {}
        return {
            "document_version_id": version["document_version_id"],
            "application_id": version["application_id"],
            "profile_version_id": version["profile_version_id"],
            "job_posting_version_id": version["job_posting_version_id"],
            "kind": version["kind"],
            "version": version["version"],
            "status": version["status"],
            "content_hash": version["content_hash"],
            "review_status": version["review_status"],
            "findings_summary": review_rules.summary(findings.get("findings") or []),
            "approved": approved,
            "approval_id": approval["approval_id"] if approved else None,
            "exported": False,
            "export_id": None,
            "pdf_available": False,
            "created_at": version["created_at"],
            "updated_at": version["updated_at"],
        }

    def _approval_payload(self, row: dict) -> dict:
        return {
            "approval_id": row["approval_id"],
            "document_version_id": row["document_version_id"],
            "profile_version_id": row["profile_version_id"],
            "document_hash": row["document_hash"],
            "kind": row["kind"],
            "decision": row["decision"],
            "note": row["note"],
            "decided_at": row["decided_at"],
        }


def _version_row(row: dict) -> dict:
    record = dict(row)
    record["content"] = json.loads(record["content_json"])
    record["diff"] = json.loads(record["diff_json"]) if record.get("diff_json") else None
    record["evidence_ids"] = (
        json.loads(record["evidence_json"]) if record.get("evidence_json") else []
    )
    record["findings"] = (
        json.loads(record["findings_json"]) if record.get("findings_json") else None
    )
    return record


def _evidence_ids(content: dict) -> list[str]:
    refs: list[str] = []

    def collect(value) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "evidence_ids":
                    refs.extend(str(ref) for ref in item or [])
                else:
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(content)
    return sorted(set(refs))


RESERVED_EDIT_ROOTS = {"kind", "schema_version", "target", "missing", "language"}


def _apply_edit(content: dict, path: str, value) -> None:
    if not path or path.startswith(".") or path.endswith("."):
        raise _edit_error(path, "path tidak valid")
    parts = path.split(".")
    if parts[0] in RESERVED_EDIT_ROOTS:
        raise _edit_error(path, "field ini tidak boleh diedit")
    if "evidence_ids" in parts:
        raise _edit_error(path, "evidence tidak boleh diedit")
    node = content
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if isinstance(node, dict):
            if part not in node:
                raise _edit_error(path, "path tidak ditemukan pada konten")
            if last:
                _set_value(node, part, value, path)
            else:
                node = node[part]
        elif isinstance(node, list):
            try:
                position = int(part)
            except ValueError as exc:
                raise _edit_error(path, "indeks list tidak valid") from exc
            if not 0 <= position < len(node):
                raise _edit_error(path, "indeks list di luar rentang")
            if last:
                _set_value(node, position, value, path)
            else:
                node = node[position]
        else:
            raise _edit_error(path, "path tidak dapat ditelusuri")


def _set_value(node, key, value, path: str) -> None:
    current = node[key]
    if current is None:
        if not isinstance(value, (str, int, float, bool)):
            raise _edit_error(path, "nilai harus skalar")
    elif isinstance(current, str) and not isinstance(value, str):
        raise _edit_error(path, "nilai harus string")
    elif isinstance(current, int) and not isinstance(value, int):
        raise _edit_error(path, "nilai harus integer")
    elif isinstance(current, dict) and not isinstance(value, dict):
        raise _edit_error(path, "nilai harus object")
    elif isinstance(current, list) and not isinstance(value, list):
        raise _edit_error(path, "nilai harus list")
    node[key] = value


def _validate_content(content: dict, *, kind: str) -> None:
    if content.get("kind") != kind:
        raise _edit_error("kind", "kind tidak boleh berubah")
    if not isinstance(content.get("header"), dict):
        raise _edit_error("header", "header harus object")
    if not isinstance(content.get("target"), dict):
        raise _edit_error("target", "target harus object")
    if kind == "cv":
        summary = content.get("summary")
        if summary is not None and not isinstance(summary, dict):
            raise _edit_error("summary", "summary harus object atau null")
        for section in (
            "skills",
            "experience",
            "projects",
            "education",
            "certifications",
            "languages",
        ):
            if not isinstance(content.get(section), list):
                raise _edit_error(section, f"{section} harus list")
    elif not isinstance(content.get("paragraphs"), list):
        raise _edit_error("paragraphs", "paragraphs harus list")


def _edit_error(path: str, message: str) -> DocumentError:
    return DocumentError(
        "validation_failed",
        f"Edit ditolak: {message}.",
        400,
        details=[{"field": f"edits[{path}]", "code": "invalid_edit", "message": message}],
    )


def _encode_cursor(record: dict) -> str:
    payload = json.dumps(
        {
            "created_at": record["created_at"],
            "document_version_id": record["document_version_id"],
        },
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> dict:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
        if not isinstance(payload, dict):
            raise ValueError
        return {
            "created_at": str(payload["created_at"]),
            "document_version_id": str(payload["document_version_id"]),
        }
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise DocumentError("validation_failed", "cursor tidak valid.", 400) from exc
