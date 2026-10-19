"""Discovery run orchestration for Phase 3A.

Network work runs in a bounded thread pool (max 3). Database writes stay on the
calling thread so a connection is never shared between workers.

shortcut: the run executes synchronously inside the request, like profile
extraction. Move it to a worker thread when the UI needs live progress.
"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from ..db.repo import Connection
from ..jobs import ADAPTERS
from ..jobs.fetch import FetchError, FetchResponse, HostRateLimiter, fetch_source
from ..jobs.sources.base import AdapterError, InvalidJob, RawJob, normalize
from ..jobs.sources.registry import FETCHABLE, SourceError, SourceRegistry
from ..master_cv import new_id, now_iso
from ..master_cv.store import MasterCvError
from ..profile.store import ProfileStore
from .tasks import MAX_ATTEMPTS, TaskStore

RUN_STAGES = ["fetch"]
DEFAULT_WORKERS = 3



@dataclass
class _SourceResult:
    source: dict
    response: FetchResponse | None = None
    jobs: list[RawJob] | None = None
    error: FetchError | None = None


class DiscoveryService:
    def __init__(
        self,
        connection: Connection,
        profile_store: ProfileStore,
        task_store: TaskStore,
        *,
        fetcher=None,
        limiter: HostRateLimiter | None = None,
        max_workers: int = DEFAULT_WORKERS,
    ) -> None:
        self._connection = connection
        self._profiles = profile_store
        self._tasks = task_store
        self._registry = SourceRegistry(connection)
        self._fetcher = fetcher
        self._limiter = limiter or HostRateLimiter()
        self._max_workers = max_workers

    def start_run(
        self,
        source_ids: list[str] | None = None,
        profile_version_id: str | None = None,
        *,
        attempt: int = 1,
        retried_from_task_id: str | None = None,
        retry_counts: dict[str, int] | None = None,
    ) -> dict:
        profile = self._profiles.require_confirmed()
        if profile_version_id and profile_version_id != profile["profile_version_id"]:
            raise MasterCvError(
                "profile_version_mismatch",
                "profile_version_id bukan profil confirmed yang aktif.",
                409,
            )
        active = self._tasks.active_discovery()
        if active is not None:
            raise MasterCvError(
                "task_already_running",
                "Sudah ada run discovery aktif.",
                409,
            )
        sources = self._select_sources(source_ids)
        if not sources:
            raise SourceError(
                "no_enabled_sources",
                "Tidak ada sumber verified dan enabled untuk dijalankan.",
                409,
            )

        task = self._tasks.create(
            "discovery",
            RUN_STAGES,
            attempt=attempt,
            retried_from_task_id=retried_from_task_id,
        )
        retry_counts = retry_counts or {}
        run_id = new_id("run")
        started_at = now_iso()
        fetchable: list[dict] = []
        with self._connection:
            self._connection.execute(
                "INSERT INTO discovery_run (run_id, task_id, profile_version_id, status, "
                "counts_json, error_json, started_at, finished_at) "
                "VALUES (?, ?, ?, 'processing', '{}', NULL, ?, NULL)",
                (run_id, task["task_id"], profile["profile_version_id"], started_at),
            )
            for source in sources:
                reason = _skip_reason(source)
                if reason is None:
                    fetchable.append(source)
                self._connection.execute(
                    "INSERT INTO discovery_run_source (run_id, source_id, company, status, "
                    "fetched_count, accepted_count, duplicate_count, retry_count, "
                    "last_attempt_at, error_json) VALUES (?, ?, ?, ?, 0, 0, 0, ?, NULL, ?)",
                    (
                        run_id,
                        source["source_id"],
                        source["company"],
                        "queued" if reason is None else "skipped",
                        retry_counts.get(source["source_id"], 0),
                        None if reason is None else json.dumps(reason),
                    ),
                )

        self._tasks.start_stage(task["task_id"], "fetch")
        results = self._fetch_all(fetchable)
        self._tasks.finish_stage(task["task_id"], "fetch")
        counts = {"fetched": 0, "new_jobs": 0, "duplicates": 0}
        failed = 0
        succeeded = 0
        for result in results:
            outcome = self._persist_source(run_id, result)
            counts["fetched"] += outcome["fetched"]
            counts["new_jobs"] += outcome["accepted"]
            counts["duplicates"] += outcome["duplicates"]
            if outcome["status"] == "failed":
                failed += 1
            elif outcome["status"] == "completed":
                succeeded += 1

        status = _aggregate_status(succeeded, failed)
        finished_at = now_iso()
        full_counts = {
            **counts,
            "eligible": 0,
            "needs_review": 0,
            "ineligible": 0,
            "fit_computed": 0,
        }
        with self._connection:
            self._connection.execute(
                "UPDATE discovery_run SET status = ?, counts_json = ?, finished_at = ? "
                "WHERE run_id = ?",
                (status, json.dumps(full_counts), finished_at, run_id),
            )
        result_payload = {
            "run_id": run_id,
            "profile_version_id": profile["profile_version_id"],
            "counts": full_counts,
        }
        if status == "failed":
            retryable = any(result.error and result.error.retryable for result in results)
            self._tasks.finish(
                task["task_id"],
                status,
                result=result_payload,
                error={
                    "code": "discovery_failed",
                    "message": "Semua sumber gagal diambil.",
                    "stage": "fetch",
                    "retryable": retryable,
                    "run_id": run_id,
                    "request_id": None,
                    "details": [],
                },
            )
        else:
            self._tasks.finish(task["task_id"], status, result=result_payload)
        return self.get_run(run_id)

    def retry(
        self,
        task_id: str,
        *,
        scope: str = "failed_sources",
        source_ids: list[str] | None = None,
    ) -> dict:
        """Repeat failed or partial sources; successful results stay untouched."""
        task = self._tasks.get(task_id)
        if task is None:
            raise MasterCvError("not_found", "Task tidak ditemukan.", 404)
        if task["status"] in {"queued", "processing"}:
            raise MasterCvError("task_not_finished", "Task belum selesai.", 409)
        if not task["retry"]["retryable"]:
            raise MasterCvError("task_not_retryable", "Task tidak dapat diulang.", 409)
        attempt = int(task["retry"]["attempt"]) + 1
        if attempt > MAX_ATTEMPTS:
            raise MasterCvError(
                "task_not_retryable", "Batas maksimum attempt tercapai.", 409
            )
        run = self._run_for_task(task_id)
        if run is None:
            raise MasterCvError("task_not_retryable", "Run discovery tidak ditemukan.", 409)
        candidates = run["sources"]
        if scope == "failed_sources":
            candidates = [
                item
                for item in candidates
                if item["status"] in {"failed", "partial"}
                and (item["error"] or {}).get("retryable") is True
            ]
            if source_ids:
                wanted = set(source_ids)
                candidates = [item for item in candidates if item["source_id"] in wanted]
        if not candidates:
            raise MasterCvError(
                "task_not_retryable", "Tidak ada sumber yang dapat diulang.", 409
            )
        return self.start_run(
            source_ids=[item["source_id"] for item in candidates],
            attempt=attempt,
            retried_from_task_id=task_id,
            retry_counts={
                item["source_id"]: int(item["retry_count"]) + 1 for item in candidates
            },
        )

    def _run_for_task(self, task_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT run_id FROM discovery_run WHERE task_id = ? "
            "ORDER BY started_at DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        return self.get_run(row["run_id"]) if row else None

    def _select_sources(self, source_ids: list[str] | None) -> list[dict]:
        if not source_ids:
            return self._registry.enabled_verified()
        selected: list[dict] = []
        missing: list[str] = []
        for source_id in source_ids:
            record = self._registry.get(source_id)
            if record is None:
                missing.append(source_id)
            else:
                selected.append(record)
        if missing:
            raise SourceError(
                "not_found", f"Sumber tidak ditemukan: {', '.join(missing)}.", 404
            )
        return selected

    def _fetch_all(self, sources: list[dict]) -> list[_SourceResult]:
        if not sources:
            return []
        results: list[_SourceResult] = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = [pool.submit(self._fetch_one, source) for source in sources]
            for future in futures:
                results.append(future.result())
        return results

    def _fetch_one(self, source: dict) -> _SourceResult:
        adapter = ADAPTERS[source["ats"]]
        try:
            response = fetch_source(
                source, adapter, fetcher=self._fetcher, limiter=self._limiter
            )
        except FetchError as exc:
            return _SourceResult(source=source, error=exc)
        try:
            jobs = adapter.parse(response.body, source)
        except AdapterError as exc:
            return _SourceResult(
                source=source,
                response=response,
                error=FetchError("source_parse_failed", str(exc), retryable=False),
            )
        return _SourceResult(source=source, response=response, jobs=jobs)

    def _persist_source(self, run_id: str, result: _SourceResult) -> dict:
        source = result.source
        fetched_at = now_iso()
        self._registry.mark_checked(source["source_id"], fetched_at)
        if result.error is not None:
            error = _error_payload(result.error, run_id)
            raw = result.response.body if result.response else ""
            self._store_fetch(run_id, source["source_id"], result.response, raw, error)
            self._update_source_progress(
                run_id, source["source_id"], status="failed", fetched=0, accepted=0,
                duplicates=0, error=error,
            )
            return {"status": "failed", "fetched": 0, "accepted": 0, "duplicates": 0}

        raw = result.response.body if result.response else ""
        self._store_fetch(run_id, source["source_id"], result.response, raw, None)
        raw_sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        fetched = 0
        accepted = 0
        duplicates = 0
        seen: set[str] = set()
        for raw_job in result.jobs or []:
            fetched += 1
            try:
                record = normalize(raw_job, source, fetched_at)
            except InvalidJob:
                continue
            seen.add(record["source_job_id"])
            created = self._store_job(record, raw_sha, fetched_at)
            if created:
                accepted += 1
            else:
                duplicates += 1
        closed = self._close_missing(source["source_id"], seen, fetched_at)
        self._update_source_progress(
            run_id, source["source_id"], status="completed", fetched=fetched,
            accepted=accepted, duplicates=duplicates, error=None,
        )
        return {
            "status": "completed",
            "fetched": fetched,
            "accepted": accepted,
            "duplicates": duplicates,
            "closed": closed,
        }

    def _store_fetch(
        self,
        run_id: str,
        source_id: str,
        response: FetchResponse | None,
        raw: str,
        error: dict | None,
    ) -> None:
        raw_sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        with self._connection:
            self._connection.execute(
                "INSERT INTO source_fetch (fetch_id, run_id, source_id, status, http_status, "
                "fetched_at, raw_sha256, raw_json, error_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("fet"),
                    run_id,
                    source_id,
                    "completed" if error is None else "failed",
                    response.status_code if response else None,
                    now_iso(),
                    raw_sha,
                    raw,
                    json.dumps(error) if error else None,
                ),
            )

    def _store_job(self, record: dict, raw_sha: str, fetched_at: str) -> bool:
        existing = self._connection.execute(
            "SELECT job_id, latest_version_id FROM job WHERE source_id = ? AND source_job_id = ?",
            (record["source_id"], record["source_job_id"]),
        ).fetchone()
        if existing is not None:
            version = self._connection.execute(
                "SELECT content_hash FROM job_posting_version WHERE job_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (existing["job_id"],),
            ).fetchone()
            latest = existing["latest_version_id"]
            if version is None or version["content_hash"] != record["content_hash"]:
                latest = self._insert_version(existing["job_id"], record, raw_sha, fetched_at)
            with self._connection:
                self._connection.execute(
                    "UPDATE job SET fetched_at = ?, latest_version_id = ?, status = 'open', "
                    "updated_at = ? WHERE job_id = ?",
                    (fetched_at, latest, now_iso(), existing["job_id"]),
                )
            return False

        job_id = new_id("job")
        timestamp = now_iso()
        with self._connection:
            self._connection.execute(
                "INSERT INTO job (job_id, source_id, source_job_id, canonical_url, apply_url, "
                "company, title, location_json, work_mode, employment_type, seniority, market, "
                "posted_at, fetched_at, status, duplicate_of, latest_version_id, "
                "completeness_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', NULL, NULL, ?, ?, ?)",
                (
                    job_id,
                    record["source_id"],
                    record["source_job_id"],
                    record["canonical_url"],
                    record["apply_url"],
                    record["company"],
                    record["title"],
                    json.dumps(record["location"], ensure_ascii=False),
                    record["work_mode"],
                    record["employment_type"],
                    record["seniority"],
                    record["market"],
                    record["posted_at"],
                    fetched_at,
                    json.dumps(record["completeness"], ensure_ascii=False),
                    timestamp,
                    timestamp,
                ),
            )
        version_id = self._insert_version(job_id, record, raw_sha, fetched_at)
        with self._connection:
            self._connection.execute(
                "UPDATE job SET latest_version_id = ? WHERE job_id = ?", (version_id, job_id)
            )
        return True

    def _close_missing(self, source_id: str, seen: set[str], timestamp: str) -> int:
        """Mark jobs absent from a successful fetch as closed; never delete them."""
        rows = self._connection.execute(
            "SELECT job_id, source_job_id FROM job WHERE source_id = ? AND status = 'open'",
            (source_id,),
        ).fetchall()
        missing = [row["job_id"] for row in rows if row["source_job_id"] not in seen]
        if not missing:
            return 0
        with self._connection:
            for job_id in missing:
                self._connection.execute(
                    "UPDATE job SET status = 'closed', updated_at = ? WHERE job_id = ?",
                    (timestamp, job_id),
                )
        return len(missing)

    def _insert_version(self, job_id: str, record: dict, raw_sha: str, fetched_at: str) -> str:
        version_id = new_id("jpv")
        with self._connection:
            self._connection.execute(
                "INSERT INTO job_posting_version (job_posting_version_id, job_id, source_id, "
                "content_hash, description_text, raw_sha256, fetched_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    version_id,
                    job_id,
                    record["source_id"],
                    record["content_hash"],
                    record["description_text"],
                    raw_sha,
                    fetched_at,
                    now_iso(),
                ),
            )
        return version_id

    def _update_source_progress(
        self,
        run_id: str,
        source_id: str,
        *,
        status: str,
        fetched: int,
        accepted: int,
        duplicates: int,
        error: dict | None,
    ) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE discovery_run_source SET status = ?, fetched_count = ?, "
                "accepted_count = ?, duplicate_count = ?, last_attempt_at = ?, error_json = ? "
                "WHERE run_id = ? AND source_id = ?",
                (
                    status,
                    fetched,
                    accepted,
                    duplicates,
                    now_iso(),
                    json.dumps(error) if error else None,
                    run_id,
                    source_id,
                ),
            )

    def get_run(self, run_id: str) -> dict:
        row = self._connection.execute(
            "SELECT * FROM discovery_run WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise MasterCvError("not_found", "Run discovery tidak ditemukan.", 404)
        return self._to_run(row)

    def list_runs(self, limit: int = 50, cursor: str | None = None) -> tuple[list[dict], str | None]:
        rows = self._connection.execute(
            "SELECT * FROM discovery_run ORDER BY started_at DESC, run_id DESC"
        ).fetchall()
        runs = [self._to_run(row) for row in rows]
        if cursor:
            runs = [run for run in runs if run["run_id"] < cursor]
        page = runs[:limit]
        return page, page[-1]["run_id"] if len(runs) > limit and page else None

    def _to_run(self, row: dict) -> dict:
        sources = [
            _to_progress(item)
            for item in self._connection.execute(
                "SELECT * FROM discovery_run_source WHERE run_id = ? ORDER BY company",
                (row["run_id"],),
            ).fetchall()
        ]
        return {
            "run_id": row["run_id"],
            "task_id": row["task_id"],
            "status": row["status"],
            "profile_version_id": row["profile_version_id"],
            "sources": sources,
            "counts": json.loads(row["counts_json"]),
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "error": json.loads(row["error_json"]) if row["error_json"] else None,
        }


def _skip_reason(source: dict) -> dict | None:
    if not source["enabled"]:
        return _skip_error("source_not_verified", "Sumber nonaktif.")
    if source["verification_status"] != FETCHABLE:
        return _skip_error("source_not_verified", "Sumber belum diverifikasi.")
    if source["ats"] not in ADAPTERS:
        return _skip_error("source_unsupported", "Adapter ATS belum tersedia.")
    if source["access_method"] != "ats_api":
        return _skip_error("source_unsupported", "Adapter HTML belum tersedia.")
    return None


def _skip_error(code: str, message: str) -> dict:
    return {
        "code": code,
        "message": message,
        "stage": "fetch",
        "retryable": False,
        "run_id": None,
        "request_id": None,
        "details": [],
    }


def _error_payload(error: FetchError, run_id: str) -> dict:
    return {
        "code": error.code,
        "message": error.message[:500],
        "stage": "fetch",
        "retryable": error.retryable,
        "run_id": run_id,
        "request_id": None,
        "details": [],
    }


def _aggregate_status(succeeded: int, failed: int) -> str:
    if failed and succeeded:
        return "partial"
    if failed:
        return "failed"
    return "completed"


def _to_progress(row: dict) -> dict:
    return {
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
