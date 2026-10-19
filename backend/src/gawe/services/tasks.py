"""In-process task records for Phase 2A.

shortcut: extraction runs synchronously inside the request so the fake-provider
path is deterministic. Move it to a worker thread when a real provider can take
seconds per call.
"""

from __future__ import annotations

import json

from ..db.repo import Connection
from ..master_cv import new_id, now_iso

MAX_ATTEMPTS = 3


def _progress(stages: list[str]) -> dict:
    return {
        "current_stage": stages[0] if stages else None,
        "completed_units": 0,
        "total_units": len(stages),
        "percent": 0,
        "stages": [
            {"name": name, "status": "pending", "started_at": None, "finished_at": None}
            for name in stages
        ],
    }


def _retryable(status: str, task_type: str, sources: list[dict]) -> bool:
    if status not in {"failed", "partial"}:
        return False
    if task_type != "discovery":
        return True
    return any((source["error"] or {}).get("retryable") is True for source in sources)


class TaskStore:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create(
        self,
        task_type: str,
        stages: list[str],
        application_id: str | None = None,
        *,
        attempt: int = 1,
        retried_from_task_id: str | None = None,
    ) -> dict:
        task_id = new_id("tsk")
        timestamp = now_iso()
        with self._connection:
            self._connection.execute(
                "INSERT INTO task (task_id, type, status, application_id, progress_json, "
                "result_json, error_json, created_at, updated_at, finished_at, attempt, "
                "retried_from_task_id) VALUES (?, ?, 'queued', ?, ?, NULL, NULL, ?, ?, NULL, ?, ?)",
                (
                    task_id,
                    task_type,
                    application_id,
                    json.dumps(_progress(stages)),
                    timestamp,
                    timestamp,
                    attempt,
                    retried_from_task_id,
                ),
            )
        record = self.get(task_id)
        assert record is not None
        return record

    def get(self, task_id: str) -> dict | None:
        row = self._connection.execute("SELECT * FROM task WHERE task_id = ?", (task_id,)).fetchone()
        return self._to_task(row) if row else None

    def active_for(self) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM task WHERE type = 'profile_extraction' AND status IN ('queued','processing') "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return self._to_task(row) if row else None

    def start_stage(self, task_id: str, stage: str) -> None:
        self._update(task_id, status="processing", stage=stage, stage_status="processing")

    def finish_stage(self, task_id: str, stage: str) -> None:
        self._update(task_id, stage=stage, stage_status="completed")

    def complete(self, task_id: str, result: dict) -> dict:
        self._update(task_id, status="completed", result=result)
        return self.get(task_id) or {}

    def finish(
        self,
        task_id: str,
        status: str,
        result: dict | None = None,
        error: dict | None = None,
    ) -> dict:
        self._update(task_id, status=status, result=result, error=error)
        return self.get(task_id) or {}

    def active_discovery(self) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM task WHERE type = 'discovery' AND status IN ('queued','processing') "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return self._to_task(row) if row else None

    def fail(self, task_id: str, code: str, message: str, stage: str) -> dict:
        error = {
            "code": code,
            "message": message,
            "stage": stage,
            "retryable": True,
            "run_id": None,
            "request_id": None,
            "details": [],
        }
        self._update(task_id, status="failed", error=error)
        return self.get(task_id) or {}

    def _update(
        self,
        task_id: str,
        status: str | None = None,
        stage: str | None = None,
        stage_status: str | None = None,
        result: dict | None = None,
        error: dict | None = None,
    ) -> None:
        task = self.get(task_id)
        if task is None:
            return
        progress = task["progress"]
        timestamp = now_iso()
        if stage is not None:
            for item in progress["stages"]:
                if item["name"] == stage:
                    if stage_status == "processing":
                        item["started_at"] = timestamp
                        progress["current_stage"] = stage
                    elif stage_status == "completed":
                        item["status"] = "completed"
                        item["finished_at"] = timestamp
            progress["completed_units"] = sum(
                1 for item in progress["stages"] if item["status"] == "completed"
            )
            if progress["total_units"]:
                progress["percent"] = int(
                    100 * progress["completed_units"] / progress["total_units"]
                )
        finished_at = timestamp if status in {"completed", "failed", "partial"} else None
        with self._connection:
            self._connection.execute(
                "UPDATE task SET status = COALESCE(?, status), progress_json = ?, "
                "result_json = COALESCE(?, result_json), error_json = COALESCE(?, error_json), "
                "updated_at = ?, finished_at = COALESCE(?, finished_at) WHERE task_id = ?",
                (
                    status,
                    json.dumps(progress),
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    json.dumps(error, ensure_ascii=False) if error is not None else None,
                    timestamp,
                    finished_at,
                    task_id,
                ),
            )

    def _to_task(self, row: dict) -> dict:
        sources = self._sources_for(row["task_id"], row["type"])
        return {
            "task_id": row["task_id"],
            "type": row["type"],
            "status": row["status"],
            "application_id": row["application_id"],
            "progress": json.loads(row["progress_json"]),
            "sources": sources,
            "retry": {
                "retryable": _retryable(row["status"], row["type"], sources),
                "attempt": int(row.get("attempt") or 1),
                "max_attempts": MAX_ATTEMPTS,
                "retry_after_seconds": None,
                "retried_from_task_id": row.get("retried_from_task_id"),
            },
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": json.loads(row["error_json"]) if row["error_json"] else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "finished_at": row["finished_at"],
        }

    def _sources_for(self, task_id: str, task_type: str) -> list[dict]:
        if task_type != "discovery":
            return []
        rows = self._connection.execute(
            "SELECT s.* FROM discovery_run_source s "
            "JOIN discovery_run r ON r.run_id = s.run_id WHERE r.task_id = ? ORDER BY s.company",
            (task_id,),
        ).fetchall()
        return [
            {
                "source_id": row["source_id"],
                "company": row["company"],
                "status": row["status"],
                "fetched_count": row["fetched_count"],
                "accepted_count": row["accepted_count"],
                "duplicate_count": row["duplicate_count"],
                "retry_count": row["retry_count"],
                "last_attempt_at": row["last_attempt_at"],
                "error": json.loads(row["error_json"]) if row["error_json"] else None,
            }
            for row in rows
        ]
