"""Source registry store: add, edit, disable, and verification gate."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from ...db.repo import Connection
from ...master_cv import new_id, now_iso
from ...security.url_guard import UnsafeUrl, validate_url
from .. import ADAPTERS
from ..health import is_due, next_run_at, retry_at, status_from

FETCHABLE = "verified"
VERIFICATION = {"unverified", "verified", "restricted", "broken"}
# Only an ATS or aggregator with an adapter can be fetched, so only those may be
# created. `html` and `manual_url` stay readable for rows written before this
# rule.
ACCESS_METHODS = {"ats_api", "aggregator"}
# A company board and an aggregator feed are validated differently: the first
# needs the company's own ATS host, the second its published feed host.
AGGREGATOR_ATS = {"himalayas"}
# Synthetic source for the manual-URL fallback (API-CONTRACTS.md 3.4): managed
# by the backend, never listed, never fetched by a discovery run.
MANUAL_SOURCE_ID = "manual_url"

# A source that has not produced a job for this long is reported as stale even
# when its last fetch succeeded (JOB-DISCOVERY.md §7: warn above 7 days).
STALE_AFTER_HOURS = 24 * 7


class SourceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 409,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []


def _validate_url(url: str) -> str:
    try:
        return validate_url(url).url
    except UnsafeUrl as exc:
        raise SourceError("url_rejected", f"careers_url ditolak: {exc}.", 400) from exc


def _validate_ats(ats: str, access_method: str, careers_url: str) -> None:
    """Reject an access method or ATS/host pair that no adapter can fetch.

    `html` used to be accepted as "unverified, no adapter yet". The UI then
    offered it as if a run would fetch it, while every run skipped the source
    with `source_unsupported`. The value is now rejected at write time instead of
    promising a fetch that never happens.
    """
    if access_method not in ACCESS_METHODS:
        raise SourceError(
            "validation_failed",
            "Metode akses belum didukung.",
            400,
            details=[
                {
                    "field": "access_method",
                    "code": "access_method_unsupported",
                    "message": (
                        "Hanya `ats_api` dan `aggregator` yang dapat ditambahkan. Sumber "
                        "tanpa API resmi memakai fallback URL manual di halaman Applications."
                    ),
                }
            ],
        )
    if access_method == "aggregator" and ats not in AGGREGATOR_ATS:
        raise SourceError(
            "validation_failed",
            "Aggregator tidak tersedia untuk akses feed.",
            400,
            details=[
                {
                    "field": "ats",
                    "code": "ats_unavailable",
                    "message": "Aggregator harus salah satu dari: "
                    + ", ".join(sorted(AGGREGATOR_ATS)),
                }
            ],
        )
    if access_method == "ats_api" and ats in AGGREGATOR_ATS:
        raise SourceError(
            "validation_failed",
            "Aggregator memakai metode akses `aggregator`.",
            400,
            details=[
                {
                    "field": "access_method",
                    "code": "access_method_unsupported",
                    "message": "Sumber aggregator memakai `aggregator`, bukan `ats_api`.",
                }
            ],
        )
    adapter = ADAPTERS.get(ats)
    if adapter is None:
        raise SourceError(
            "validation_failed",
            "ATS tidak tersedia untuk akses API.",
            400,
            details=[
                {
                    "field": "careers_url",
                    "code": "ats_unavailable",
                    "message": "ATS harus salah satu dari: " + ", ".join(sorted(ADAPTERS)),
                }
            ],
        )
    host = (urlsplit(careers_url).hostname or "").lower()
    if host not in adapter.CAREER_HOSTS:
        raise SourceError(
            "validation_failed",
            "Host careers_url tidak cocok dengan ATS.",
            400,
            details=[
                {
                    "field": "careers_url",
                    "code": "ats_host_mismatch",
                    "message": f"Host harus salah satu dari: {', '.join(adapter.CAREER_HOSTS)}",
                }
            ],
        )


def _iso_before_hours(hours: int) -> str:
    from datetime import datetime, timedelta, timezone

    stamp = datetime.now(timezone.utc) - timedelta(hours=hours)
    return stamp.isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> "datetime":
    from datetime import datetime, timezone

    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _is_stale(last_success_at: str | None, last_checked_at: str | None) -> bool:
    """No successful fetch for a week means the data may no longer be live."""
    from datetime import datetime, timedelta, timezone

    reference = last_success_at or last_checked_at
    if not reference:
        return False
    try:
        stamp = _parse_timestamp(reference)
    except ValueError:
        return False
    return stamp < datetime.now(timezone.utc) - timedelta(hours=STALE_AFTER_HOURS)


SCHEDULE_FIELDS = {
    "priority_order": (1, 1000),
    "fetch_interval_minutes": (5, 60 * 24 * 30),
    "daily_request_quota": (0, 100_000),
}


def _schedule_field(data: dict, name: str, default: int) -> int:
    value = data.get(name)
    return default if value is None else int(value)


def _validate_schedule(fields: dict) -> None:
    for name, (low, high) in SCHEDULE_FIELDS.items():
        if name not in fields:
            continue
        value = fields[name]
        if not isinstance(value, int) or not low <= value <= high:
            raise SourceError(
                "validation_failed",
                f"{name} harus bilangan bulat {low}-{high}.",
                400,
                details=[
                    {
                        "field": name,
                        "code": "out_of_range",
                        "message": f"{low}-{high}",
                    }
                ],
            )


class SourceRegistry:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def ensure_manual_source(self) -> dict:
        """Create the synthetic `manual_url` row if it is missing.

        Seeded lazily rather than by migration because test cleanup deletes
        every data row; the row must exist before a manual job can reference it.
        """
        self._connection.execute(
            "INSERT IGNORE INTO source_registry (source_id, company, market, careers_url, "
            "access_method, ats, verification_status, tos_notes, last_checked_at, enabled, "
            "created_at, updated_at) VALUES (?, ?, 'unknown', ?, 'manual_url', 'unknown', "
            "'verified', ?, NULL, 0, ?, ?)",
            (
                MANUAL_SOURCE_ID,
                "Manual URL",
                "https://example.com/manual-url",
                "Sumber sintetis: satu URL ditempel pengguna, divalidasi per request.",
                now_iso(),
                now_iso(),
            ),
        )
        record = self.get(MANUAL_SOURCE_ID)
        assert record is not None
        return record

    def get(self, source_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT *, (SELECT COUNT(*) FROM job j WHERE j.source_id = source_registry.source_id) "
            "AS job_count, "
            "(SELECT COALESCE(SUM(s.request_count), 0) FROM discovery_run_source s "
            "  WHERE s.source_id = source_registry.source_id "
            "  AND s.last_attempt_at >= ?) AS requests_24h "
            "FROM source_registry WHERE source_id = ?",
            (_iso_before_hours(24), source_id),
        ).fetchone()
        return self._to_public(row) if row else None

    def list(
        self,
        limit: int = 50,
        cursor: str | None = None,
        enabled: bool | None = None,
        verification_status: str | None = None,
    ) -> tuple[list[dict], str | None]:
        clauses: list[str] = ["source_id <> ?"]
        params: list[Any] = [MANUAL_SOURCE_ID]
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
            f"WHERE j.source_id = source_registry.source_id) AS job_count, "
            f"(SELECT COALESCE(SUM(s.request_count), 0) FROM discovery_run_source s "
            f"  WHERE s.source_id = source_registry.source_id "
            f"  AND s.last_attempt_at >= ?) AS requests_24h "
            f"FROM source_registry {where} ORDER BY priority_order, source_id DESC LIMIT ?",
            (_iso_before_hours(24), *params, limit + 1),
        ).fetchall()
        items = [self._to_public(row) for row in rows[:limit]]
        next_cursor = items[-1]["source_id"] if len(rows) > limit and items else None
        return items, next_cursor

    def enabled_verified(self) -> list[dict]:
        rows = self._connection.execute(
            "SELECT *, (SELECT COUNT(*) FROM job j WHERE j.source_id = source_registry.source_id) "
            "AS job_count, "
            "(SELECT COALESCE(SUM(s.request_count), 0) FROM discovery_run_source s "
            "  WHERE s.source_id = source_registry.source_id "
            "  AND s.last_attempt_at >= ?) AS requests_24h "
            "FROM source_registry WHERE enabled = 1 AND verification_status = ? "
            "AND source_id <> ? ORDER BY priority_order, source_id",
            (_iso_before_hours(24), FETCHABLE, MANUAL_SOURCE_ID),
        ).fetchall()
        return [self._to_public(row) for row in rows]

    def due(self, limit: int = 20) -> list[dict]:
        """Enabled and verified sources whose scheduled slot has arrived."""
        return [source for source in self.enabled_verified() if is_due(source["next_run_at"])][
            :limit
        ]

    def create(self, data: dict) -> dict:
        careers_url = _validate_url(data["careers_url"])
        _validate_ats(data["ats"], data["access_method"], careers_url)
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
                "created_at, updated_at, priority_order, fetch_interval_minutes, "
                "daily_request_quota) "
                "VALUES (?, ?, ?, ?, ?, ?, 'unverified', ?, NULL, 0, ?, ?, ?, ?, ?)",
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
                    _schedule_field(data, "priority_order", 100),
                    _schedule_field(data, "fetch_interval_minutes", 360),
                    _schedule_field(data, "daily_request_quota", 24),
                ),
            )
        record = self.get(source_id)
        assert record is not None
        return record

    def update(self, source_id: str, changes: dict) -> dict:
        if source_id == MANUAL_SOURCE_ID:
            raise SourceError(
                "not_found", "Sumber manual_url dikelola sistem dan tidak dapat diubah.", 404
            )
        current = self.get(source_id)
        if current is None:
            raise SourceError("not_found", "Sumber tidak ditemukan.", 404)
        fields = {name: value for name, value in changes.items() if value is not None}
        if "careers_url" in fields:
            fields["careers_url"] = _validate_url(fields["careers_url"])
        # Only a real change to the ATS binding is re-gated. A legacy row written
        # before `html` was rejected must still be disableable and re-verifiable,
        # so an unchanged value must not be re-validated.
        binding = {
            name: fields[name]
            for name in ("access_method", "ats", "careers_url")
            if name in fields and fields[name] != current[name]
        }
        if binding:
            _validate_ats(
                binding.get("ats", current["ats"]),
                binding.get("access_method", current["access_method"]),
                binding.get("careers_url", current["careers_url"]),
            )
        _validate_schedule(fields)
        resulting_enabled = bool(fields.get("enabled", current["enabled"]))
        resulting_status = fields.get("verification_status", current["verification_status"])
        if "verification_status" in fields and fields["verification_status"] not in VERIFICATION:
            raise SourceError("validation_failed", "Status verifikasi tidak valid.", 400)
        if "enabled" in fields:
            fields["enabled"] = 1 if fields["enabled"] else 0
            # A fresh enable must be due immediately; a disable drops the slot so
            # a later enable does not inherit it.
            fields["next_run_at"] = None
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

    def record_outcome(
        self,
        source: dict,
        timestamp: str,
        *,
        error_code: str | None = None,
        retry_after_s: int | None = None,
    ) -> None:
        """Persist health, failure streak, and the next scheduled slot."""
        failures = 0 if error_code is None else int(source.get("consecutive_failures") or 0) + 1
        interval = int(source.get("fetch_interval_minutes") or 360)
        now = _parse_timestamp(timestamp)
        if error_code is None:
            schedule = next_run_at(now, interval)
            success = timestamp
        else:
            schedule = retry_at(now, failures, interval, retry_after_s)
            success = source.get("last_success_at")
        with self._connection:
            self._connection.execute(
                "UPDATE source_registry SET health_status = ?, consecutive_failures = ?, "
                "last_error_code = ?, last_success_at = ?, next_run_at = ?, updated_at = ? "
                "WHERE source_id = ?",
                (
                    status_from(failures, ever_succeeded=bool(success)),
                    failures,
                    error_code,
                    success,
                    schedule,
                    timestamp,
                    source["source_id"],
                ),
            )

    @staticmethod
    def _to_public(row: dict) -> dict:
        last_success = row.get("last_success_at")
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
            "last_success_at": last_success,
            "health_status": row.get("health_status") or "unknown",
            "consecutive_failures": int(row.get("consecutive_failures") or 0),
            "last_error_code": row.get("last_error_code"),
            "next_run_at": row.get("next_run_at"),
            "priority_order": int(row.get("priority_order") or 100),
            "fetch_interval_minutes": int(row.get("fetch_interval_minutes") or 360),
            "daily_request_quota": int(row.get("daily_request_quota") or 0),
            "requests_last_24h": int(row.get("requests_24h") or 0),
            "stale": _is_stale(last_success, row["last_checked_at"]),
            "enabled": bool(row["enabled"]),
            "job_count": int(row.get("job_count") or 0),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
