"""Application workspace: one per job, created from a matched job.

Phase 3D slice. Documents exist as deterministic drafts with versions, review,
and approval. LaTeX/PDF and export are still out of scope (D6 OPEN), so no
document claims `pdf_available` or `exported`.
"""

from __future__ import annotations

import base64
import binascii
import json

from ..db.repo import Connection
from ..export.naming import suggested_filename, with_collision_suffix
from ..master_cv import new_id, now_iso
from ..profile.store import ProfileStore
from .assessment_service import AssessmentService
from .discovery_service import DiscoveryService
from .document_service import DocumentService
from .tasks import TaskStore

ANALYSIS_STAGES = ["eligibility"]


class ApplicationError(Exception):
    def __init__(
        self, code: str, message: str, status_code: int, active_task_id: str | None = None
    ) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.active_task_id = active_task_id


class ApplicationService:
    def __init__(self, connection: Connection, profile_store: ProfileStore) -> None:
        self._connection = connection
        self._profiles = profile_store
        self._assessments = AssessmentService(connection, profile_store)
        self._tasks = TaskStore(connection)
        self._documents = DocumentService(connection, profile_store)

    # -- writes ----------------------------------------------------------
    def create(self, job_id: str) -> tuple[dict, bool]:
        """Create the workspace for a job; an existing one is returned as-is.

        The existing check runs first: a job that closed after the user started an
        application must still answer `200 deduplicated`, not `409`.
        """
        profile = self._profiles.require_confirmed()
        existing = self._by_job(job_id)
        if existing is not None:
            return existing, True
        match = self._assessments.match(job_id, profile["profile_version_id"])
        if match is None:
            if self._assessments.job_status(job_id) not in (None, "open"):
                raise ApplicationError(
                    "job_not_open",
                    "Lowongan sudah ditutup; tidak dapat membuat aplikasi baru.",
                    409,
                )
            raise ApplicationError(
                "not_found", "Job tidak ditemukan atau belum dianalisis.", 404
            )
        application_id = new_id("app")
        timestamp = now_iso()
        with self._connection:
            self._connection.execute(
                "INSERT INTO application (application_id, job_id, profile_version_id, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (application_id, job_id, profile["profile_version_id"], timestamp, timestamp),
            )
        record = self._row(application_id)
        assert record is not None
        return record, False

    def create_from_url(
        self, url: str, discovery: DiscoveryService, text: str | None = None
    ) -> tuple[dict, bool]:
        """Manual-URL fallback: ingest one pasted job page, then create the workspace."""
        profile = self._profiles.require_confirmed()
        result = discovery.ingest_manual_url(url, text=text)
        return self.create(result["job_id"])

    def rerun_analysis(self, application_id: str) -> dict:
        """Explicit re-analysis; nothing here is triggered automatically.

        Runs synchronously like discovery: the task is already final when the
        response arrives (API-CONTRACTS §4.3).
        """
        record = self._row(application_id)
        if record is None:
            raise ApplicationError("not_found", "Workspace tidak ditemukan.", 404)
        active = self._active_task(application_id)
        if active is not None:
            raise ApplicationError(
                "task_already_running",
                "Sudah ada task aktif untuk workspace ini.",
                409,
                active_task_id=active,
            )
        profile = self._profiles.require_confirmed()
        task = self._tasks.create("analysis", ANALYSIS_STAGES, application_id)
        task_id = task["task_id"]
        self._tasks.start_stage(task_id, "eligibility")
        result = self._assessments.assess_job(record["job_id"], profile)
        if result is None:
            self._tasks.finish(
                task_id,
                "failed",
                error={
                    "code": "not_found",
                    "message": "Job workspace tidak ditemukan.",
                    "stage": "eligibility",
                    "retryable": False,
                    "run_id": None,
                    "request_id": None,
                    "details": [],
                },
            )
            raise ApplicationError("not_found", "Job workspace tidak ditemukan.", 404)
        self._assessments.recompute_ranking()
        self._tasks.finish_stage(task_id, "eligibility")
        self._tasks.finish(
            task_id, "completed", result={"eligibility_status": result["status"]}
        )
        with self._connection:
            self._connection.execute(
                "UPDATE application SET updated_at = ? WHERE application_id = ?",
                (now_iso(), application_id),
            )
        return {"task_id": task_id, "status": "completed"}

    # -- reads -----------------------------------------------------------
    def list(
        self,
        limit: int = 50,
        cursor: str | None = None,
        status: str | None = None,
        include_cancelled: bool = False,
    ) -> tuple[list[dict], str | None]:
        rows = self._connection.execute(
            "SELECT * FROM application ORDER BY created_at DESC, application_id DESC"
        ).fetchall()
        records = [dict(row) for row in rows]
        if cursor:
            key = _decode_cursor(cursor)
            records = [
                record
                for record in records
                if (record["created_at"], record["application_id"])
                < (key["created_at"], key["application_id"])
            ]
        items: list[dict] = []
        scanned = 0
        for record in records:
            scanned += 1
            summary = self._summary(record)
            if summary is None:
                continue
            if status and summary["status"] != status:
                continue
            # Cancelled workspaces are archived, not deleted: hidden from the
            # active list unless the caller asks for the archive or filters on it.
            if (
                summary["status"] == "cancelled"
                and not include_cancelled
                and status != "cancelled"
            ):
                continue
            items.append(summary)
            if len(items) == limit:
                break
        has_more = scanned < len(records)
        next_cursor = _encode_cursor(records[scanned - 1]) if has_more and scanned else None
        return items, next_cursor

    def get(self, application_id: str) -> dict | None:
        return self._row(application_id)

    def cancel(self, application_id: str, reason: str | None) -> dict:
        """Archive a workspace the user is no longer pursuing.

        The row stays: an approval is bound to a document version and its hash,
        so deleting it would cut the audit trail. A cancelled workspace keeps
        its documents but drops out of the active list.
        """
        record = self._row(application_id)
        if record is None:
            raise ApplicationError("not_found", "Workspace tidak ditemukan.", 404)
        if record.get("cancelled_at"):
            return record
        active = self._active_task(application_id)
        if active is not None:
            raise ApplicationError(
                "task_already_running",
                "Sudah ada task aktif untuk workspace ini.",
                409,
                active_task_id=active,
            )
        approved = self._connection.execute(
            "SELECT document_version_id FROM document_version "
            "WHERE application_id = ? AND status = 'approved' LIMIT 1",
            (application_id,),
        ).fetchone()
        if approved is not None:
            raise ApplicationError(
                "approval_exists",
                "Dokumen workspace ini sudah disetujui; arsip tetap disimpan, "
                "tetapi pembatalan ditolak agar approval tidak hilang dari daftar.",
                409,
            )
        timestamp = now_iso()
        with self._connection:
            self._connection.execute(
                "UPDATE application SET cancelled_at = ?, cancel_reason = ?, updated_at = ? "
                "WHERE application_id = ?",
                (timestamp, (reason or "").strip()[:500] or None, timestamp, application_id),
            )
        return self._row(application_id) or record

    def eligibility(self, application_id: str) -> dict | None:
        record = self._row(application_id)
        if record is None:
            raise ApplicationError("not_found", "Workspace tidak ditemukan.", 404)
        return self._assessments.eligibility_for(
            record["job_id"], record["profile_version_id"]
        )

    def fit(self, application_id: str) -> dict | None:
        record = self._row(application_id)
        if record is None:
            raise ApplicationError("not_found", "Workspace tidak ditemukan.", 404)
        return self._assessments.fit_for(record["job_id"], record["profile_version_id"])

    def workspace(self, application_id: str) -> dict:
        record = self._row(application_id)
        if record is None:
            raise ApplicationError("not_found", "Workspace tidak ditemukan.", 404)
        match = self._assessments.match(
            record["job_id"], record["profile_version_id"], include_closed=True
        )
        if match is None:
            raise ApplicationError(
                "not_found", "Job workspace belum dianalisis.", 404
            )
        eligibility = match["eligibility"]
        profile = self._profiles.get(record["profile_version_id"])
        documents = self._documents.summaries(application_id)
        active_task = self._active_task(application_id)
        return {
            "application_id": record["application_id"],
            "status": _status(eligibility["status"], documents, active_task),
            "job": match["job"],
            "job_posting_version_id": match["job"]["job_posting_version_id"],
            "profile_version_id": record["profile_version_id"],
            "eligibility": eligibility,
            "fit": match["fit"],
            "documents": documents,
            "suggested_filenames": self._filenames(match["job"], profile),
            "next_action": _next_action(eligibility["status"], documents),
            "active_task_id": active_task,
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
        }

    def job_detail(self, application_id: str) -> dict:
        record = self._row(application_id)
        if record is None:
            raise ApplicationError("not_found", "Workspace tidak ditemukan.", 404)
        detail = self._assessments.detail(
            record["job_id"], record["profile_version_id"], include_closed=True
        )
        if detail is None:
            raise ApplicationError("not_found", "Job workspace tidak ditemukan.", 404)
        return detail["job_detail"]

    # -- internals -------------------------------------------------------
    def _row(self, application_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM application WHERE application_id = ?", (application_id,)
        ).fetchone()
        return dict(row) if row else None

    def _by_job(self, job_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM application WHERE job_id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None

    def _active_task(self, application_id: str) -> str | None:
        row = self._connection.execute(
            "SELECT task_id FROM task WHERE application_id = ? "
            "AND status IN ('queued','processing') ORDER BY created_at DESC LIMIT 1",
            (application_id,),
        ).fetchone()
        return row["task_id"] if row else None

    def _summary(self, record: dict) -> dict | None:
        match = self._assessments.match(
            record["job_id"], record["profile_version_id"], include_closed=True
        )
        if match is None:
            # No assessment left for this workspace; never invent eligibility or fit.
            return None
        documents = self._documents.summaries(record["application_id"])
        active_task = self._active_task(record["application_id"])
        return {
            "application_id": record["application_id"],
            "job": match["job"],
            "status": _status(
                match["eligibility"]["status"],
                documents,
                active_task,
                record.get("cancelled_at"),
            ),
            "cancelled_at": record.get("cancelled_at"),
            "cancel_reason": record.get("cancel_reason"),
            "profile_version_id": record["profile_version_id"],
            "eligibility_status": match["eligibility"]["status"],
            "fit_score": match["fit"]["fit_score"] if match["fit"] else None,
            "document_counts": self._documents.counts(record["application_id"]),
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
        }

    def _filenames(self, job: dict, profile: dict | None) -> dict:
        candidate = ((profile or {}).get("content", {}).get("personal") or {}).get("full_name")
        names = {
            kind: suggested_filename(kind, candidate, job["company"], job["title"])
            for kind in ("cv", "cover_letter")
        }
        # Two jobs can share company and position; the suffix stays stable per job.
        collision = self._connection.execute(
            "SELECT COUNT(*) AS total FROM job WHERE company = ? AND title = ? AND job_id != ?",
            (job["company"], job["title"], job["job_id"]),
        ).fetchone()
        if collision and int(collision["total"]) > 0:
            names = {
                kind: with_collision_suffix(name, job["job_id"])
                for kind, name in names.items()
            }
        return names


def _encode_cursor(record: dict) -> str:
    payload = json.dumps(
        {"created_at": record["created_at"], "application_id": record["application_id"]},
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
            "application_id": str(payload["application_id"]),
        }
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise ApplicationError("validation_failed", "cursor tidak valid.", 400) from exc


def _status(
    eligibility_status: str,
    documents: dict,
    active_task: str | None = None,
    cancelled_at: str | None = None,
) -> str:
    """Application status projection (API-CONTRACTS §4.11).

    Document states win over eligibility once a version exists; export is never
    projected because no export record can be created yet. A cancelled
    workspace is reported first: whatever its documents say, the user stopped
    pursuing it.
    """
    if cancelled_at:
        return "cancelled"
    if active_task:
        return "processing"
    if eligibility_status == "needs_review":
        return "needs_review"
    versions = [version for group in documents.values() for version in group]
    if any(version["status"] == "outdated" for version in versions):
        return "outdated"
    if any(version["status"] == "in_review" for version in versions):
        return "in_review"
    if any(version["status"] == "approved" for version in versions):
        return "approved"
    return "not_started"


def _next_action(eligibility_status: str, documents: dict) -> dict:
    if eligibility_status == "needs_review":
        return {
            "code": "review_matches",
            "label": "Tinjau requirement yang belum jelas",
            "target_route": "/matches",
            "reason": "Eligibility needs_review memblokir pembuatan dokumen.",
        }
    if eligibility_status == "ineligible":
        return {
            "code": "none",
            "label": "Tidak ada aksi dokumen",
            "target_route": "/matches",
            "reason": "Ineligible tidak masuk alur dokumen normal (D21 tetap OPEN).",
        }
    versions = [version for group in documents.values() for version in group]
    if not versions:
        return {
            "code": "review_documents",
            "label": "Buat dokumen lamaran",
            "reason": "Eligibility eligible. Dokumen belum dibuat.",
        }
    if any(version["status"] in {"draft", "in_review"} for version in versions):
        return {
            "code": "review_documents",
            "label": "Periksa dan setujui dokumen",
            "reason": "Versi dokumen menunggu review atau approval pengguna.",
        }
    if any(version["status"] == "approved" for version in versions):
        return {
            "code": "none",
            "label": "Dokumen disetujui",
            "reason": "Ekspor belum tersedia pada milestone ini (D6 OPEN).",
        }
    return {"code": "none", "label": "Belum ada aksi dokumen"}
