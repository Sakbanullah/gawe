"""Immutable, content-addressed Master CV store.

Files are written once under `data/master_cv/<sha256>/`. Metadata lives in
MySQL; the filesystem path is never exposed through the API.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..db.repo import Connection
from ..ingest.validate import ValidatedUpload

STATUSES = ("uploaded", "extracted", "confirmed", "superseded")


class MasterCvError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 409,
        *,
        active_task_id: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.active_task_id = active_task_id


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MasterCvStore:
    def __init__(self, connection: Connection, data_dir: Path) -> None:
        self._connection = connection
        self._root = data_dir / "master_cv"

    # -- storage ---------------------------------------------------------
    def _path_for(self, sha256: str, extension: str) -> Path:
        return self._root / sha256 / f"original{extension}"

    def store_file(self, sha256: str, extension: str, data: bytes) -> Path:
        path = self._path_for(sha256, extension)
        if path.is_file():
            if sha256_bytes(path.read_bytes()) != sha256:
                raise MasterCvError("conflict", "File tersimpan tidak cocok dengan hash.", 500)
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_bytes(data)
        if sha256_bytes(temp.read_bytes()) != sha256:
            temp.unlink(missing_ok=True)
            raise MasterCvError("conflict", "Hash file tidak cocok setelah ditulis.", 500)
        temp.replace(path)
        return path

    def file_path(self, record: dict) -> Path:
        extension = Path(record["original_file"]["filename"]).suffix.lower()
        path = self._path_for(record["original_file"]["sha256"], extension)
        if not path.is_file():
            raise MasterCvError("not_found", "File Master CV tidak ditemukan.", 404)
        return path

    # -- records ---------------------------------------------------------
    def active(self) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM master_cv WHERE status != 'superseded' "
            "ORDER BY uploaded_at DESC LIMIT 1"
        ).fetchone()
        return self._to_record(row) if row else None

    def get(self, master_cv_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM master_cv WHERE master_cv_id = ?", (master_cv_id,)
        ).fetchone()
        return self._to_record(row) if row else None

    def by_sha256(self, sha256: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM master_cv WHERE sha256 = ?", (sha256,)
        ).fetchone()
        return self._to_record(row) if row else None

    def upload(self, upload: ValidatedUpload) -> tuple[dict, bool]:
        sha256 = sha256_bytes(upload.data)
        existing = self.by_sha256(sha256)
        if existing is not None:
            self.store_file(sha256, upload.extension, upload.data)
            return existing, True

        self.store_file(sha256, upload.extension, upload.data)
        master_cv_id = new_id("mcv")
        uploaded_at = now_iso()
        with self._connection:
            self._connection.execute(
                "UPDATE master_cv SET status = 'superseded' WHERE status != 'superseded'"
            )
            self._connection.execute(
                "INSERT INTO master_cv (master_cv_id, sha256, filename, mime, size_bytes, "
                "page_count, status, active_profile_version_id, extraction_task_id, uploaded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'uploaded', NULL, NULL, ?)",
                (
                    master_cv_id,
                    sha256,
                    upload.filename,
                    upload.mime,
                    len(upload.data),
                    upload.page_count,
                    uploaded_at,
                ),
            )
        record = self.get(master_cv_id)
        assert record is not None
        return record, False

    # -- parsed source document -----------------------------------------
    def save_document(self, master_cv_id: str, document) -> str:
        import json

        record = self.get(master_cv_id)
        if record is None:
            raise MasterCvError("not_found", "Master CV tidak ditemukan.", 404)
        doc_id = new_id("doc")
        with self._connection:
            self._connection.execute(
                "INSERT INTO source_document (doc_id, master_cv_id, sha256, mime, page_count, "
                "blocks_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    doc_id,
                    master_cv_id,
                    record["original_file"]["sha256"],
                    record["original_file"]["mime"],
                    document.page_count,
                    json.dumps(document.as_json(), ensure_ascii=False),
                    now_iso(),
                ),
            )
        return doc_id

    def get_document(self, master_cv_id: str):
        import json

        from ..ingest.types import DocumentText

        row = self._connection.execute(
            "SELECT blocks_json FROM source_document WHERE master_cv_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (master_cv_id,),
        ).fetchone()
        if row is None:
            return None
        return DocumentText.from_json(json.loads(row["blocks_json"]))

    def update(self, master_cv_id: str, **fields: object) -> None:
        allowed = {"status", "active_profile_version_id", "extraction_task_id", "page_count"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown master_cv fields: {sorted(unknown)}")
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self._connection:
            self._connection.execute(
                f"UPDATE master_cv SET {assignments} WHERE master_cv_id = ?",
                (*fields.values(), master_cv_id),
            )

    def mark_extracted(self, master_cv_id: str, task_id: str) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE master_cv SET status = 'extracted', extraction_task_id = ? "
                "WHERE master_cv_id = ? AND status = 'uploaded'",
                (task_id, master_cv_id),
            )

    @staticmethod
    def _to_record(row: dict) -> dict:
        return {
            "master_cv_id": row["master_cv_id"],
            "original_file": {
                "sha256": row["sha256"],
                "filename": row["filename"],
                "mime": row["mime"],
                "size_bytes": row["size_bytes"],
                "page_count": row["page_count"],
                "uploaded_at": row["uploaded_at"],
            },
            "status": row["status"],
            "active_profile_version_id": row["active_profile_version_id"],
            "extraction_task_id": row["extraction_task_id"],
            "uploaded_at": row["uploaded_at"],
        }
