"""Append-only profile version store.

Versions are never edited in place. Corrections on a draft update that draft;
corrections on a confirmed/superseded version create a new draft that derives
from it. Confirmation moves the active pointer; rollback only moves it back.
"""

from __future__ import annotations

import json
from typing import Any

from ..db.repo import Connection
from ..master_cv import new_id, now_iso
from ..master_cv.store import MasterCvError


class ProfileStore:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    # -- reads -----------------------------------------------------------
    def get(self, profile_version_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM profile_version WHERE profile_version_id = ?", (profile_version_id,)
        ).fetchone()
        return self._to_version(row) if row else None

    def active(self) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM profile_version WHERE active = 1 LIMIT 1"
        ).fetchone()
        return self._to_version(row) if row else None

    def latest(self) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM profile_version ORDER BY created_at DESC, profile_version_id DESC LIMIT 1"
        ).fetchone()
        return self._to_version(row) if row else None

    def require_confirmed(self) -> dict:
        """Gate for discovery and document work. Phase 2A exposes no bypass."""
        active = self.active()
        if active is None:
            raise MasterCvError(
                "profile_not_confirmed",
                "Profil belum dikonfirmasi. Discovery terkunci.",
                409,
            )
        return active

    def list(self, limit: int = 50, cursor: str | None = None) -> tuple[list[dict], str | None]:
        rows = self._connection.execute(
            "SELECT * FROM profile_version ORDER BY created_at DESC, profile_version_id DESC"
        ).fetchall()
        versions = [self._to_version(row) for row in rows]
        if cursor:
            versions = [item for item in versions if item["profile_version_id"] < cursor]
        page = versions[:limit]
        next_cursor = page[-1]["profile_version_id"] if len(versions) > limit else None
        return page, next_cursor

    def summaries_for_master_cv(self, master_cv_id: str) -> list[dict]:
        rows = self._connection.execute(
            "SELECT * FROM profile_version WHERE master_cv_id = ? ORDER BY version",
            (master_cv_id,),
        ).fetchall()
        return [self._to_summary(self._to_version(row)) for row in rows]

    # -- writes ----------------------------------------------------------
    def create(
        self,
        master_cv_id: str,
        content: dict,
        evidence: dict,
        conflicts: list[dict],
        derived_from: str | None = None,
    ) -> dict:
        profile_id = self._profile_id_for(master_cv_id)
        row = self._connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM profile_version WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        version = int(row[0]) + 1
        profile_version_id = new_id("prv")
        timestamp = now_iso()
        with self._connection:
            self._connection.execute(
                "INSERT INTO profile_version (profile_version_id, profile_id, master_cv_id, "
                "derived_from_profile_version_id, version, status, content_json, evidence_json, "
                "conflicts_json, active, confirmed_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, 0, NULL, ?, ?)",
                (
                    profile_version_id,
                    profile_id,
                    master_cv_id,
                    derived_from,
                    version,
                    json.dumps(content, ensure_ascii=False),
                    json.dumps(evidence, ensure_ascii=False),
                    json.dumps(conflicts, ensure_ascii=False),
                    timestamp,
                    timestamp,
                ),
            )
        record = self.get(profile_version_id)
        assert record is not None
        return record

    def _profile_id_for(self, master_cv_id: str) -> str:
        row = self._connection.execute(
            "SELECT profile_id FROM profile_version WHERE master_cv_id = ? LIMIT 1",
            (master_cv_id,),
        ).fetchone()
        return row[0] if row else new_id("prf")

    def save(self, version: dict, status: str | None = None) -> dict:
        with self._connection:
            self._connection.execute(
                "UPDATE profile_version SET content_json = ?, evidence_json = ?, "
                "conflicts_json = ?, status = ?, updated_at = ? WHERE profile_version_id = ?",
                (
                    json.dumps(version["content"], ensure_ascii=False),
                    json.dumps(version["evidence_index"], ensure_ascii=False),
                    json.dumps(version["conflicts"], ensure_ascii=False),
                    status or version["status"],
                    now_iso(),
                    version["profile_version_id"],
                ),
            )
        record = self.get(version["profile_version_id"])
        assert record is not None
        return record

    def record_correction(
        self, profile_version_id: str, path: str, old: Any, new: Any, reason: str | None
    ) -> None:
        self._record_correction(profile_version_id, path, old, new, reason)

    def _record_correction(
        self, profile_version_id: str, path: str, old: Any, new: Any, reason: str | None
    ) -> None:
        self._connection.execute(
            "INSERT INTO profile_correction (correction_id, profile_version_id, path, "
            "old_value_json, new_value_json, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                new_id("cor"),
                profile_version_id,
                path,
                json.dumps(old, ensure_ascii=False),
                json.dumps(new, ensure_ascii=False),
                reason,
                now_iso(),
            ),
        )

    def record_decision(self, profile_version_id: str | None, action: str, reason: str | None) -> None:
        self._record_decision(profile_version_id, action, reason)

    def _record_decision(self, profile_version_id: str | None, action: str, reason: str | None) -> None:
        self._connection.execute(
            "INSERT INTO profile_decision (decision_id, profile_version_id, action, reason, "
            "created_at) VALUES (?, ?, ?, ?, ?)",
            (new_id("dec"), profile_version_id, action, reason, now_iso()),
        )

    def confirm(self, profile_version_id: str, note: str | None) -> dict:
        version = self.get(profile_version_id)
        if version is None:
            raise MasterCvError("not_found", "Versi profil tidak ditemukan.", 404)
        if version["status"] == "superseded":
            raise MasterCvError("conflict", "Versi profil sudah superseded.", 409)
        if version["conflicts"]:
            raise MasterCvError(
                "profile_conflicts_unresolved",
                "Masih ada konflik profil yang belum diselesaikan.",
                409,
            )
        master = self._connection.execute(
            "SELECT status FROM master_cv WHERE master_cv_id = ?", (version["master_cv_id"],)
        ).fetchone()
        if master is None:
            raise MasterCvError("not_found", "Master CV tidak ditemukan.", 404)
        if master["status"] == "superseded":
            raise MasterCvError(
                "conflict",
                "Master CV sumber sudah superseded; ekstraksi ulang dari Master CV aktif.",
                409,
            )
        if version["status"] == "confirmed" and version["active"]:
            return version

        timestamp = now_iso()
        with self._connection:
            self._connection.execute(
                "UPDATE profile_version SET status = 'superseded', active = 0 "
                "WHERE status = 'confirmed' AND profile_version_id != ?",
                (profile_version_id,),
            )
            self._connection.execute(
                "UPDATE profile_version SET status = 'confirmed', active = 1, confirmed_at = ?, "
                "updated_at = ? WHERE profile_version_id = ?",
                (timestamp, timestamp, profile_version_id),
            )
            self._connection.execute(
                "UPDATE master_cv SET status = 'confirmed', active_profile_version_id = ? "
                "WHERE master_cv_id = ? AND status != 'superseded'",
                (profile_version_id, version["master_cv_id"]),
            )
            self._record_decision(profile_version_id, "profile_confirmed", note)
        record = self.get(profile_version_id)
        assert record is not None
        return record

    def rollback(self, target_profile_version_id: str, reason: str) -> dict:
        target = self.get(target_profile_version_id)
        if target is None:
            raise MasterCvError("not_found", "Versi profil target tidak ditemukan.", 404)
        if target["confirmed_at"] is None:
            raise MasterCvError("conflict", "Versi target belum pernah dikonfirmasi.", 409)
        if target["active"]:
            return target
        timestamp = now_iso()
        with self._connection:
            self._connection.execute(
                "UPDATE profile_version SET status = 'superseded', active = 0 "
                "WHERE status = 'confirmed' AND profile_version_id != ?",
                (target_profile_version_id,),
            )
            self._connection.execute(
                "UPDATE profile_version SET status = 'confirmed', active = 1, updated_at = ? "
                "WHERE profile_version_id = ?",
                (timestamp, target_profile_version_id),
            )
            self._connection.execute(
                "UPDATE master_cv SET status = 'confirmed', active_profile_version_id = ? "
                "WHERE master_cv_id = ? AND status != 'superseded'",
                (target_profile_version_id, target["master_cv_id"]),
            )
            self._record_decision(target_profile_version_id, "profile_rollback", reason)
        record = self.get(target_profile_version_id)
        assert record is not None
        return record

    # -- mapping ---------------------------------------------------------
    @staticmethod
    def _to_version(row: dict) -> dict:
        return {
            "profile_id": row["profile_id"],
            "profile_version_id": row["profile_version_id"],
            "master_cv_id": row["master_cv_id"],
            "derived_from_profile_version_id": row["derived_from_profile_version_id"],
            "version": row["version"],
            "status": row["status"],
            "content": json.loads(row["content_json"]),
            "evidence_index": json.loads(row["evidence_json"]),
            "conflicts": json.loads(row["conflicts_json"]),
            "active": bool(row["active"]),
            "confirmed_at": row["confirmed_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _to_summary(version: dict) -> dict:
        return {
            "profile_id": version["profile_id"],
            "profile_version_id": version["profile_version_id"],
            "master_cv_id": version["master_cv_id"],
            "derived_from_profile_version_id": version["derived_from_profile_version_id"],
            "version": version["version"],
            "status": version["status"],
            "active": version["active"],
            "confirmed_at": version["confirmed_at"],
            "created_at": version["created_at"],
            "updated_at": version["updated_at"],
        }
