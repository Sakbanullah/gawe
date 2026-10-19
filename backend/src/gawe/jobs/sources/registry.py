"""Source registry store: add, edit, disable, and verification gate."""

from __future__ import annotations

from typing import Any

from ...db.repo import Connection
from ...master_cv import new_id, now_iso
from ...security.url_guard import UnsafeUrl, validate_url

FETCHABLE = "verified"
VERIFICATION = {"unverified", "verified", "restricted", "broken"}


class SourceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code


def _validate_url(url: str) -> str:
    try:
        return validate_url(url).url
    except UnsafeUrl as exc:
        raise SourceError("url_rejected", f"careers_url ditolak: {exc}.", 400) from exc


class SourceRegistry:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get(self, source_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT *, (SELECT COUNT(*) FROM job j WHERE j.source_id = source_registry.source_id) "
            "AS job_count FROM source_registry WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        return self._to_public(row) if row else None

    def list(
        self,
        limit: int = 50,
        cursor: str | None = None,
        enabled: bool | None = None,
        verification_status: str | None = None,
    ) -> tuple[list[dict], str | None]:
        clauses: list[str] = []
        params: list[Any] = []
        if enabled is not None:
            clauses.append("enabled = ?")
            params.append(1 if enabled else 0)
        if verification_status is not None:
            clauses.append("verification_status = ?")
            params.append(verification_status)
        if cursor:
            clauses.append("source_id < ?")
            params.append(cursor)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._connection.execute(
            f"SELECT *, (SELECT COUNT(*) FROM job j "
            f"WHERE j.source_id = source_registry.source_id) AS job_count "
            f"FROM source_registry {where} ORDER BY source_id DESC LIMIT ?",
            (*params, limit + 1),
        ).fetchall()
        items = [self._to_public(row) for row in rows[:limit]]
        next_cursor = items[-1]["source_id"] if len(rows) > limit and items else None
        return items, next_cursor

    def enabled_verified(self) -> list[dict]:
        rows = self._connection.execute(
            "SELECT *, (SELECT COUNT(*) FROM job j WHERE j.source_id = source_registry.source_id) "
            "AS job_count FROM source_registry WHERE enabled = 1 AND verification_status = ? "
            "ORDER BY source_id",
            (FETCHABLE,),
        ).fetchall()
        return [self._to_public(row) for row in rows]

    def create(self, data: dict) -> dict:
        careers_url = _validate_url(data["careers_url"])
        if data.get("enabled"):
            raise SourceError(
                "source_not_verified",
                "Sumber baru selalu unverified dan tidak boleh diaktifkan.",
            )
        source_id = new_id("src")
        timestamp = now_iso()
        with self._connection:
            self._connection.execute(
                "INSERT INTO source_registry (source_id, company, market, careers_url, "
                "access_method, ats, verification_status, tos_notes, last_checked_at, enabled, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'unverified', ?, NULL, 0, ?, ?)",
                (
                    source_id,
                    data["company"].strip(),
                    data["market"],
                    careers_url,
                    data["access_method"],
                    data["ats"],
                    data.get("tos_notes"),
                    timestamp,
                    timestamp,
                ),
            )
        record = self.get(source_id)
        assert record is not None
        return record

    def update(self, source_id: str, changes: dict) -> dict:
        current = self.get(source_id)
        if current is None:
            raise SourceError("not_found", "Sumber tidak ditemukan.", 404)
        fields = {name: value for name, value in changes.items() if value is not None}
        if "careers_url" in fields:
            fields["careers_url"] = _validate_url(fields["careers_url"])
        resulting_enabled = bool(fields.get("enabled", current["enabled"]))
        resulting_status = fields.get("verification_status", current["verification_status"])
        if "verification_status" in fields and fields["verification_status"] not in VERIFICATION:
            raise SourceError("validation_failed", "Status verifikasi tidak valid.", 400)
        if "enabled" in fields:
            fields["enabled"] = 1 if fields["enabled"] else 0
        if resulting_enabled and resulting_status != FETCHABLE:
            raise SourceError(
                "source_not_verified",
                "Sumber hanya boleh diaktifkan setelah diverifikasi.",
            )
        if not fields:
            return current
        fields["updated_at"] = now_iso()
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self._connection:
            self._connection.execute(
                f"UPDATE source_registry SET {assignments} WHERE source_id = ?",
                (*fields.values(), source_id),
            )
        record = self.get(source_id)
        assert record is not None
        return record

    def mark_checked(self, source_id: str, timestamp: str) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE source_registry SET last_checked_at = ?, updated_at = ? "
                "WHERE source_id = ?",
                (timestamp, timestamp, source_id),
            )

    @staticmethod
    def _to_public(row: dict) -> dict:
        return {
            "source_id": row["source_id"],
            "company": row["company"],
            "market": row["market"],
            "careers_url": row["careers_url"],
            "access_method": row["access_method"],
            "ats": row["ats"],
            "verification_status": row["verification_status"],
            "tos_notes": row["tos_notes"],
            "last_checked_at": row["last_checked_at"],
            "enabled": bool(row["enabled"]),
            "job_count": int(row.get("job_count") or 0),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
