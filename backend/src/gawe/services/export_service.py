"""Export records: approved version -> LaTeX -> PDF -> stored file.

Rules from DOCUMENT-GENERATION.md §9-§11 and API-CONTRACTS.md §3.8:
only an approved version with a matching content hash can be exported, a new
version never inherits an old approval, and a failed compile is never
`exported`.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from pathlib import Path

from ..db.repo import Connection
from ..documents import render
from ..master_cv import new_id, now_iso
from ..export import naming
from .tasks import TaskStore

EXPORT_STAGES = ["render", "compile", "qa"]


class ExportError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        details: list[dict] | None = None,
        active_task_id: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []
        self.active_task_id = active_task_id


class ExportService:
    def __init__(self, connection: Connection, data_dir: Path) -> None:
        self._connection = connection
        self._data_dir = data_dir
        self._tasks = TaskStore(connection)

    def create(
        self,
        application_id: str,
        document_version_id: str,
        *,
        kind: str,
        content_hash: str,
        filename: str | None = None,
        tectonic: str | None = None,
    ) -> dict:
        """Validate, then run the export inside an `export` task.

        The toolchain check happens before the task exists so an unavailable PDF
        engine is a plain `503 toolchain_unavailable`, not a half-finished export.
        """
        version = self._version(application_id, document_version_id)
        if version["kind"] != kind:
            raise ExportError(
                "validation_failed",
                "kind tidak cocok dengan versi dokumen.",
                400,
                details=[
                    {
                        "field": "kind",
                        "code": "mismatch",
                        "message": "kind harus sama dengan kind versi dokumen.",
                    }
                ],
            )
        if version["content_hash"] != content_hash:
            raise ExportError(
                "approval_hash_mismatch",
                "content_hash tidak cocok dengan versi dokumen.",
                409,
            )
        approval = self._approval(document_version_id)
        if approval is None or approval["decision"] != "approved":
            raise ExportError(
                "export_not_ready",
                "Hanya versi yang disetujui dapat diekspor.",
                409,
            )
        if approval["document_hash"] != version["content_hash"]:
            raise ExportError(
                "approval_hash_mismatch",
                "Approval tidak cocok dengan hash versi ini.",
                409,
            )
        engine = tectonic if tectonic is not None else render.find_tectonic()
        if engine is None:
            raise ExportError(
                "toolchain_unavailable",
                "Mesin PDF belum tersedia.",
                503,
            )
        self._require_no_active_task(application_id)

        final_name = self._filename(application_id, version, filename)
        task = self._tasks.create("export", EXPORT_STAGES, application_id)
        task_id = task["task_id"]
        try:
            self._tasks.start_stage(task_id, "render")
            export_id = new_id("exp")
            timestamp = now_iso()
            tex_source = render.build(version["content"])
            self._tasks.finish_stage(task_id, "render")

            self._tasks.start_stage(task_id, "compile")
            try:
                pdf_bytes, _log = render.compile_pdf(tex_source, tectonic=engine)
            except render.RenderError as exc:
                record = self._record(
                    export_id=export_id,
                    version=version,
                    filename=final_name,
                    status="tex_only",
                    created_at=timestamp,
                    error={"code": exc.code, "message": exc.message},
                    tex_source=tex_source,
                    pdf_bytes=None,
                )
                self._tasks.finish_stage(task_id, "compile")
                return self._tasks.complete(task_id, {"export": record})
            self._tasks.finish_stage(task_id, "compile")

            self._tasks.start_stage(task_id, "qa")
            report = render.qa(pdf_bytes, version["kind"])
            self._tasks.finish_stage(task_id, "qa")
            if not report["ok"]:
                record = self._record(
                    export_id=export_id,
                    version=version,
                    filename=final_name,
                    status="failed",
                    created_at=timestamp,
                    error={
                        "code": report["problems"][0]["code"],
                        "message": report["problems"][0]["message"],
                        "qa": report,
                    },
                    tex_source=tex_source,
                    pdf_bytes=None,
                )
                return self._tasks.complete(task_id, {"export": record})

            record = self._record(
                export_id=export_id,
                version=version,
                filename=final_name,
                status="exported",
                created_at=timestamp,
                error=None,
                tex_source=tex_source,
                pdf_bytes=pdf_bytes,
                qa=report,
            )
            return self._tasks.complete(task_id, {"export": record})
        except Exception as exc:  # noqa: BLE001 - task must not stay `processing`
            self._tasks.fail(task_id, "export_failed", "Ekspor gagal.", "qa")
            raise exc

    def list(
        self, application_id: str, limit: int = 50, cursor: str | None = None
    ) -> tuple[list[dict], str | None]:
        self._application(application_id)
        rows = self._connection.execute(
            "SELECT * FROM export_record WHERE application_id = ? "
            "ORDER BY created_at DESC, export_id DESC",
            (application_id,),
        ).fetchall()
        records = [dict(row) for row in rows]
        if cursor:
            key = _decode_cursor(cursor)
            records = [
                record
                for record in records
                if (record["created_at"], record["export_id"])
                < (key["created_at"], key["export_id"])
            ]
        items = [self._payload(record) for record in records[:limit]]
        next_cursor = (
            _encode_cursor(records[limit - 1]) if len(records) > limit and limit > 0 else None
        )
        return items, next_cursor

    def get(self, application_id: str, export_id: str) -> dict:
        row = self._connection.execute(
            "SELECT * FROM export_record WHERE application_id = ? AND export_id = ?",
            (application_id, export_id),
        ).fetchone()
        if row is None:
            raise ExportError("not_found", "Export tidak ditemukan.", 404)
        return self._payload(dict(row))

    def path_for(self, application_id: str, export_id: str) -> Path:
        record = self.get(application_id, export_id)
        if record["status"] != "exported" or not record["download_url"]:
            raise ExportError(
                "export_not_ready", "File final tidak tersedia untuk export ini.", 409
            )
        return self._data_dir / "applications" / application_id / "exports" / record["filename"]

    # -- internals -------------------------------------------------------
    def _application(self, application_id: str) -> dict:
        row = self._connection.execute(
            "SELECT * FROM application WHERE application_id = ?", (application_id,)
        ).fetchone()
        if row is None:
            raise ExportError("not_found", "Workspace tidak ditemukan.", 404)
        return dict(row)

    def _require_no_active_task(self, application_id: str) -> None:
        row = self._connection.execute(
            "SELECT task_id FROM task WHERE application_id = ? "
            "AND status IN ('queued','processing') ORDER BY created_at DESC LIMIT 1",
            (application_id,),
        ).fetchone()
        if row is not None:
            raise ExportError(
                "task_already_running",
                "Sudah ada task aktif untuk workspace ini.",
                409,
                active_task_id=row["task_id"],
            )

    def _record(
        self,
        *,
        export_id: str,
        version: dict,
        filename: str,
        status: str,
        created_at: str,
        error: dict | None,
        tex_source: str,
        pdf_bytes: bytes | None,
        qa: dict | None = None,
    ) -> dict:
        application_id = version["application_id"]
        base = self._data_dir / "applications" / application_id
        exports_dir = base / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)

        tex_path = exports_dir / f"{export_id}.tex"
        tex_path.write_text(tex_source, encoding="utf-8")
        if pdf_bytes is not None:
            (exports_dir / filename).write_bytes(pdf_bytes)

        pdf_sha = hashlib.sha256(pdf_bytes).hexdigest() if pdf_bytes else None
        download_url = (
            f"/api/applications/{application_id}/exports/{export_id}/download"
            if status == "exported"
            else None
        )
        exported_at = created_at if status == "exported" else None
        with self._connection:
            self._connection.execute(
                "INSERT INTO export_record (export_id, application_id, document_version_id, "
                "profile_version_id, document_hash, kind, filename, status, created_at, "
                "exported_at, error_json, download_url, pdf_sha256, qa_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    export_id,
                    application_id,
                    version["document_version_id"],
                    version["profile_version_id"],
                    version["content_hash"],
                    version["kind"],
                    filename,
                    status,
                    created_at,
                    exported_at,
                    json.dumps(error, ensure_ascii=False) if error else None,
                    download_url,
                    pdf_sha,
                    json.dumps(qa, ensure_ascii=False) if qa else None,
                ),
            )
            if status == "exported":
                self._connection.execute(
                    "UPDATE document_version SET status = 'exported', updated_at = ? "
                    "WHERE document_version_id = ?",
                    (created_at, version["document_version_id"]),
                )
            self._connection.execute(
                "UPDATE application SET updated_at = ? WHERE application_id = ?",
                (created_at, application_id),
            )
        row = self._connection.execute(
            "SELECT * FROM export_record WHERE export_id = ?", (export_id,)
        ).fetchone()
        assert row is not None
        return self._payload(dict(row))

    def _filename(self, application_id: str, version: dict, requested: str | None) -> str:
        if requested:
            candidate = naming.sanitize(requested, version["kind"])
        else:
            job = self._connection.execute(
                "SELECT company, title FROM job WHERE job_id = ?", (version["job_id"],)
            ).fetchone()
            profile_name = self._profile_name(version["profile_version_id"])
            candidate = naming.suggested_filename(
                version["kind"],
                profile_name,
                job["company"] if job else None,
                job["title"] if job else None,
            )
        taken = self._connection.execute(
            "SELECT 1 FROM export_record WHERE application_id = ? AND filename = ? "
            "AND status = 'exported'",
            (application_id, candidate),
        ).fetchone()
        if taken is not None:
            candidate = naming.with_collision_suffix(candidate, version["job_id"])
        return candidate

    def _profile_name(self, profile_version_id: str) -> str | None:
        row = self._connection.execute(
            "SELECT content_json FROM profile_version WHERE profile_version_id = ?",
            (profile_version_id,),
        ).fetchone()
        if row is None:
            return None
        return (json.loads(row["content_json"]).get("personal") or {}).get("full_name")

    def _version(self, application_id: str, document_version_id: str) -> dict:
        row = self._connection.execute(
            "SELECT d.*, a.job_id FROM document_version d "
            "JOIN application a ON a.application_id = d.application_id "
            "WHERE d.application_id = ? AND d.document_version_id = ?",
            (application_id, document_version_id),
        ).fetchone()
        if row is None:
            raise ExportError("not_found", "Versi dokumen tidak ditemukan.", 404)
        record = dict(row)
        record["content"] = json.loads(record["content_json"])
        return record

    def _approval(self, document_version_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM document_approval WHERE document_version_id = ? "
            "ORDER BY decided_at DESC, approval_id DESC LIMIT 1",
            (document_version_id,),
        ).fetchone()
        return dict(row) if row else None

    def _payload(self, row: dict) -> dict:
        return {
            "export_id": row["export_id"],
            "application_id": row["application_id"],
            "document_version_id": row["document_version_id"],
            "profile_version_id": row["profile_version_id"],
            "document_hash": row["document_hash"],
            "kind": row["kind"],
            "filename": row["filename"],
            "status": row["status"],
            "created_at": row["created_at"],
            "exported_at": row["exported_at"],
            "error": json.loads(row["error_json"]) if row["error_json"] else None,
            "download_url": row["download_url"],
            "pdf_sha256": row["pdf_sha256"],
            "qa": json.loads(row["qa_json"]) if row["qa_json"] else None,
        }


def _encode_cursor(record: dict) -> str:
    payload = json.dumps(
        {"created_at": record["created_at"], "export_id": record["export_id"]},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> dict:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
        if not isinstance(payload, dict):
            raise ValueError
        return {"created_at": str(payload["created_at"]), "export_id": str(payload["export_id"])}
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise ExportError("validation_failed", "cursor tidak valid.", 400) from exc
