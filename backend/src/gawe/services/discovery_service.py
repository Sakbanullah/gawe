"""Discovery run orchestration for Phase 3A.

Network work runs in a bounded thread pool (max 3). Database writes stay on the
calling thread so a connection is never shared between workers.

shortcut: the run executes synchronously inside the request, like profile
extraction. Move it to a worker thread when the UI needs live progress.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ..db.repo import Connection
from ..jobs import ADAPTERS, robots
from ..jobs.dedupe import link_duplicate
from ..jobs.fetch import (
    FetchError,
    FetchResponse,
    HostRateLimiter,
    fetch_document,
    fetch_source,
)
from ..jobs.health import quota_exhausted
from ..jobs.sources import manual
from ..jobs.sources.base import (
    AdapterError,
    InvalidJob,
    RawJob,
    company_of,
    normalize,
)
from ..jobs.sources.registry import (
    FETCHABLE,
    MANUAL_SOURCE_ID,
    SourceError,
    SourceRegistry,
)
from ..master_cv import new_id, now_iso
from ..master_cv.store import MasterCvError
from ..profile.store import ProfileStore
from ..ranking.rank import RankingError
from ..security.url_guard import UnsafeUrl, validate_url
from .assessment_service import AssessmentService
from .tasks import MAX_ATTEMPTS, TaskStore

RUN_STAGES = ["fetch"]
DEFAULT_WORKERS = 3
DEFAULT_MAX_RUN_S = 600
logger = logging.getLogger(__name__)

# A snapshot is trusted for closing absent jobs only when most records parsed
# into a normalisable job. Above this ratio the payload is treated as suspect.
MAX_INVALID_RATIO = 0.5

# D-B approved: a discovery task is stale when its heartbeat stops for this
# long. Heartbeats fire once per persisted source, so a run blocked inside one
# slow fetch can still be reaped; raise this if long single fetches are expected.
STALE_AFTER_S = 600

# Named MySQL lock serialises run creation across connections and processes.
# GET_LOCK/RELEASE_LOCK are connection-scoped; DiscoveryService owns exactly one
# physical connection, so both calls use the same session.
DISCOVERY_LOCK = "gawe_discovery_run"

_ACTIVE_LOCK = threading.Lock()
# shortcut: in-process only. A single-user local server runs one process, so a
# live run always appears here; add a shared lease if multiple workers arrive.
_ACTIVE_TASKS: set[str] = set()


def _mark_active(task_id: str) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_TASKS.add(task_id)


def _clear_active(task_id: str) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_TASKS.discard(task_id)


@dataclass
class _SourceResult:
    source: dict
    response: FetchResponse | None = None
    jobs: list[RawJob] | None = None
    skipped: int = 0
    error: FetchError | None = None
    not_modified: bool = False
    # False when the payload is a page, not the whole board.
    complete: bool = True
    # HTTP requests actually spent, whatever the outcome. The daily quota counts
    # these, not attempts.
    requests: int = 1
    # Evidence body to store, currently always the raw response body.
    raw: str | None = None
    # Why the adapter dropped records, keyed by reason.
    skip_reasons: dict[str, int] = field(default_factory=dict)


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
        max_run_seconds: int = DEFAULT_MAX_RUN_S,
        document_fetcher=None,
        llm_client=None,
        root_dir=None,
    ) -> None:
        self._connection = connection
        self._profiles = profile_store
        self._tasks = task_store
        self._registry = SourceRegistry(connection)
        self._fetcher = fetcher
        self._limiter = limiter or HostRateLimiter()
        self._max_workers = max_workers
        self._max_run_seconds = max_run_seconds
        self._document_fetcher = document_fetcher
        # Passed to assessment so requirement extraction can use the `extract`
        # role. Left as None in contexts that must not call a model.
        self._llm = llm_client
        self._root_dir = root_dir

    def start_run(
        self,
        source_ids: list[str] | None = None,
        profile_version_id: str | None = None,
        *,
        attempt: int = 1,
        retried_from_task_id: str | None = None,
        retry_counts: dict[str, int] | None = None,
        due_only: bool = False,
    ) -> dict:
        profile = self._profiles.require_confirmed()
        if profile_version_id and profile_version_id != profile["profile_version_id"]:
            raise MasterCvError(
                "profile_version_mismatch",
                "profile_version_id bukan profil confirmed yang aktif.",
                409,
            )
        self._reap_stale()
        if not self._acquire_lock():
            active = self._tasks.active_discovery()
            raise MasterCvError(
                "task_already_running",
                "Sudah ada run discovery aktif.",
                409,
                active_task_id=active["task_id"] if active else None,
            )
        task_id: str | None = None
        run_id: str | None = None
        try:
            active = self._tasks.active_discovery()
            if active is not None:
                raise MasterCvError(
                    "task_already_running",
                    "Sudah ada run discovery aktif.",
                    409,
                    active_task_id=active["task_id"],
                )
            sources = self._select_sources(source_ids, due_only=due_only)
            if not sources:
                raise SourceError(
                    "no_enabled_sources",
                    "Tidak ada sumber verified dan enabled untuk dijalankan.",
                    409,
                )

            retry_counts = retry_counts or {}
            run_id = new_id("run")
            started_at = now_iso()
            fetchable: list[dict] = []
            # The quota is checked per source against everything the source would
            # spend in this run, so a source is fetched whole or not at all. A
            # partially fetched source is a partial snapshot, and a partial
            # snapshot must never close absent jobs.
            reasons = {
                source["source_id"]: _skip_reason(
                    source, planned_requests=_planned_requests(source)
                )
                for source in sources
            }
            # One transaction: a failure here leaves neither task nor run behind.
            with self._connection:
                task = self._tasks.create(
                    "discovery",
                    RUN_STAGES,
                    attempt=attempt,
                    retried_from_task_id=retried_from_task_id,
                )
                task_id = task["task_id"]
                self._connection.execute(
                    "INSERT INTO discovery_run (run_id, task_id, profile_version_id, status, "
                    "counts_json, error_json, started_at, finished_at) "
                    "VALUES (?, ?, ?, 'processing', '{}', NULL, ?, NULL)",
                    (run_id, task_id, profile["profile_version_id"], started_at),
                )
                for source in sources:
                    reason = reasons[source["source_id"]]
                    if reason is None:
                        fetchable.append(source)
                    self._connection.execute(
                        "INSERT INTO discovery_run_source (run_id, source_id, company, status, "
                        "fetched_count, accepted_count, duplicate_count, retry_count, "
                        "request_count, last_attempt_at, error_json) "
                        "VALUES (?, ?, ?, ?, 0, 0, 0, ?, 0, NULL, ?)",
                        (
                            run_id,
                            source["source_id"],
                            source["company"],
                            "queued" if reason is None else "skipped",
                            retry_counts.get(source["source_id"], 0),
                            None if reason is None else json.dumps(reason),
                        ),
                    )
            _mark_active(task_id)

            self._tasks.start_stage(task_id, "fetch")
            results = self._fetch_all(fetchable)
            self._tasks.finish_stage(task_id, "fetch")
            counts = {"fetched": 0, "new_jobs": 0, "duplicates": 0}
            failed = 0
            succeeded = 0
            for result in results:
                try:
                    outcome = self._persist_source(run_id, result)
                except Exception:
                    outcome = self._fail_source(run_id, result)
                self._tasks.heartbeat(task_id)
                counts["fetched"] += outcome["fetched"]
                counts["new_jobs"] += outcome["accepted"]
                counts["duplicates"] += outcome["duplicates"]
                if outcome["status"] == "failed":
                    failed += 1
                elif outcome["status"] == "completed":
                    succeeded += 1

            status = _aggregate_status(succeeded, failed)
            finished_at = now_iso()
            assessment, assessment_error = self._assess(profile)
            if assessment_error is not None:
                # Fetched data is stored, but the run is not fully done.
                assessment_error = {**assessment_error, "run_id": run_id}
                if status == "completed":
                    status = "partial"
            full_counts = {
                **counts,
                "eligible": assessment["eligible"],
                "needs_review": assessment["needs_review"],
                "ineligible": assessment["ineligible"],
                "fit_computed": assessment["eligible"],
            }
            with self._connection:
                self._connection.execute(
                    "UPDATE discovery_run SET status = ?, counts_json = ?, "
                    "error_json = COALESCE(error_json, ?), finished_at = ? WHERE run_id = ?",
                    (
                        status,
                        json.dumps(full_counts),
                        json.dumps(assessment_error) if assessment_error else None,
                        finished_at,
                        run_id,
                    ),
                )
            result_payload = {
                "run_id": run_id,
                "profile_version_id": profile["profile_version_id"],
                "counts": full_counts,
            }
            if status == "failed":
                retryable = any(result.error and result.error.retryable for result in results)
                self._tasks.finish(
                    task_id,
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
                self._tasks.finish(
                    task_id, status, result=result_payload, error=assessment_error
                )
            return self.get_run(run_id)
        except BaseException:
            if task_id is not None and run_id is not None:
                self._fail_run(run_id, task_id)
            raise
        finally:
            if task_id is not None:
                _clear_active(task_id)
            self._release_lock()

    def ingest_manual_url(
        self, url: str, profile_version_id: str | None = None, text: str | None = None
    ) -> dict:
        """Fetch one pasted job URL, store it, and assess it.

        This is the fallback path from JOB-DISCOVERY.md §1: one page, no link
        following, `robots.txt` checked, URL guard applied. It records a normal
        discovery run so the raw response, hash, and `fetched_at` stay auditable.

        When `text` is supplied the page is not fetched at all: that is the
        escape hatch for a 403/429 or a JavaScript shell, where the user pastes
        the description instead. The URL is still required and still validated,
        because it is the job's identity and its apply target.
        """
        profile = self._profiles.require_confirmed()
        if profile_version_id and profile_version_id != profile["profile_version_id"]:
            raise MasterCvError(
                "profile_version_mismatch",
                "profile_version_id bukan profil confirmed yang aktif.",
                409,
            )
        try:
            validate_url(url)
        except UnsafeUrl as exc:
            raise MasterCvError("url_rejected", f"URL ditolak: {exc}.", 400) from exc
        source = self._registry.ensure_manual_source()

        pasted = (text or "").strip()
        if pasted:
            response = None
            raw = pasted
            try:
                raw_job = manual.from_text(pasted, url)
            except AdapterError as exc:
                raise MasterCvError("manual_page_unreadable", str(exc), 400) from exc
        else:
            allowed, reason = robots.check(url, fetcher=self._document_fetcher)
            if not allowed:
                raise MasterCvError("robots_disallowed", reason or "robots.txt menolak.", 400)
            try:
                response = self._fetch_document(url)
                raw_job = manual.parse(response.body, url)
            except FetchError as exc:
                # A manual page is one the user chose; a blocked or broken fetch
                # is an input problem, not a server fault. `url_rejected` and
                # `source_not_found` keep their own code because the UI reacts
                # to them differently (API-CONTRACTS.md §3.4).
                code = (
                    exc.code
                    if exc.code in ("url_rejected", "source_not_found")
                    else "manual_fetch_failed"
                )
                raise MasterCvError(code, exc.message, 400) from exc
            except AdapterError as exc:
                raise MasterCvError("manual_page_unreadable", str(exc), 400) from exc
            raw = response.body

        run_id = new_id("run")
        task_id: str | None = None
        started_at = now_iso()
        try:
            with self._connection:
                task = self._tasks.create("discovery", RUN_STAGES)
                task_id = task["task_id"]
                self._connection.execute(
                    "INSERT INTO discovery_run (run_id, task_id, profile_version_id, status, "
                    "counts_json, error_json, started_at, finished_at) "
                    "VALUES (?, ?, ?, 'processing', '{}', NULL, ?, NULL)",
                    (run_id, task_id, profile["profile_version_id"], started_at),
                )
                self._connection.execute(
                    "INSERT INTO discovery_run_source (run_id, source_id, company, status, "
                    "fetched_count, accepted_count, duplicate_count, retry_count, "
                    "last_attempt_at, error_json) VALUES (?, ?, ?, 'queued', 0, 0, 0, 0, NULL, NULL)",
                    (run_id, MANUAL_SOURCE_ID, manual.COMPANY),
                )
            self._tasks.start_stage(task_id, "fetch")
            fetched_at = now_iso()
            raw_sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            record = normalize(
                raw_job,
                {**source, "company": company_of(raw_job, manual.COMPANY)},
                fetched_at,
            )
            self._store_fetch(run_id, MANUAL_SOURCE_ID, response, raw, None)
            created, job_id, _version_added = self._store_job(record, raw_sha, fetched_at)
            link_duplicate(self._connection, job_id, record)
            self._update_source_progress(
                run_id,
                MANUAL_SOURCE_ID,
                status="completed",
                fetched=1,
                accepted=1 if created else 0,
                duplicates=0 if created else 1,
                error=None,
                close_skipped=None,
                stats={"manual_text": True} if pasted else {"manual_url": True},
                # Pasted text costs no request; a fetched page costs one.
                requests=0 if pasted else 1,
            )
            self._tasks.finish_stage(task_id, "fetch")
            assessment, assessment_error = self._assess(profile)
            counts = {
                "fetched": 1,
                "new_jobs": 1 if created else 0,
                "duplicates": 0 if created else 1,
                "eligible": assessment["eligible"],
                "needs_review": assessment["needs_review"],
                "ineligible": assessment["ineligible"],
                "fit_computed": assessment["eligible"],
            }
            status = "partial" if assessment_error else "completed"
            if assessment_error:
                assessment_error = {**assessment_error, "run_id": run_id}
            with self._connection:
                self._connection.execute(
                    "UPDATE discovery_run SET status = ?, counts_json = ?, error_json = ?, "
                    "finished_at = ? WHERE run_id = ?",
                    (
                        status,
                        json.dumps(counts),
                        json.dumps(assessment_error) if assessment_error else None,
                        now_iso(),
                        run_id,
                    ),
                )
            self._tasks.finish(
                task_id,
                status,
                result={
                    "run_id": run_id,
                    "profile_version_id": profile["profile_version_id"],
                    "counts": counts,
                    "job_id": job_id,
                },
                error=assessment_error,
            )
            return {"run_id": run_id, "job_id": job_id, "created": created}
        except BaseException:
            if task_id is not None:
                self._fail_run(run_id, task_id)
            raise

    def _fetch_document(self, url: str) -> FetchResponse:
        host = (urlsplit(url).hostname or "").lower()
        self._limiter.wait(host)
        if self._document_fetcher is not None:
            return self._document_fetcher(url)
        return fetch_document(url, allowed_hosts=frozenset({host}))

    def _assess(self, profile: dict) -> tuple[dict, dict | None]:
        """Assess new jobs after the fetch stage.

        A failure here must not lose the fetch evidence, but it must also not be
        hidden: the caller reports ``assessment_failed`` on the run.
        """
        try:
            service = AssessmentService(
                self._connection,
                self._profiles,
                llm_client=self._llm,
                root_dir=self._root_dir,
            )
            result = service.assess_pending()
            service.recompute_ranking()
            return result, None
        except RankingError as exc:
            # Eligibility and fit are already stored; only the ordering failed.
            # Reporting it as `assessment_failed` hid that, so the run says which
            # stage broke.
            logger.warning("ranking failed: %s", exc)
            return (
                {"eligible": 0, "needs_review": 0, "ineligible": 0},
                {
                    "code": "ranking_failed",
                    "message": "Lowongan dan analisis tersimpan, tetapi ranking gagal dihitung.",
                    "stage": "ranking",
                    "retryable": False,
                    "run_id": None,
                    "request_id": None,
                    "details": [],
                },
            )
        except Exception as exc:
            # Metadata only: no description, profile, or document content in logs.
            logger.warning("assessment failed: %s", type(exc).__name__)
            return (
                {"eligible": 0, "needs_review": 0, "ineligible": 0},
                {
                    "code": "assessment_failed",
                    "message": "Lowongan tersimpan tetapi analisis eligibility/fit gagal.",
                    "stage": "eligibility",
                    # No failed source to retry: the fetch data is already stored.
                    "retryable": False,
                    "run_id": None,
                    "request_id": None,
                    "details": [],
                },
            )

    def _acquire_lock(self) -> bool:
        row = self._connection.execute(
            "SELECT GET_LOCK(?, 0) AS acquired", (DISCOVERY_LOCK,)
        ).fetchone()
        return bool(row and row["acquired"] == 1)

    def _release_lock(self) -> None:
        try:
            self._connection.execute("SELECT RELEASE_LOCK(?)", (DISCOVERY_LOCK,))
        except Exception:
            # A broken connection drops its own locks server-side.
            return

    def _fail_source(self, run_id: str, result: _SourceResult) -> dict:
        error = _error_payload(
            FetchError("source_error", "Sumber gagal diproses.", retryable=True), run_id
        )
        try:
            self._store_fetch(
                run_id,
                result.source["source_id"],
                result.response,
                result.response.body if result.response else "",
                error,
            )
            self._update_source_progress(
                run_id,
                result.source["source_id"],
                status="failed",
                fetched=0,
                accepted=0,
                duplicates=0,
                error=error,
                close_skipped=None,
                stats=None,
                requests=result.requests,
            )
        except Exception:
            # The outer lifecycle handler fails the whole run if the DB is gone.
            pass
        return {"status": "failed", "fetched": 0, "accepted": 0, "duplicates": 0}

    def _fail_run(self, run_id: str, task_id: str) -> None:
        """Fail an unfinished run and its task; never overwrite a final status."""
        timestamp = now_iso()
        error = {
            "code": "internal_error",
            "message": "Run discovery gagal karena kesalahan internal.",
            "stage": "fetch",
            "retryable": True,
            "run_id": run_id,
            "request_id": None,
            "details": [],
        }
        try:
            run = self._connection.execute(
                "SELECT status, counts_json FROM discovery_run WHERE run_id = ?", (run_id,)
            ).fetchone()
            task = self._tasks.get(task_id)
            if task is not None and task["status"] in {"queued", "processing"}:
                if run is not None and run["status"] in {"completed", "partial"}:
                    # The run finished; keep the task in the same direction.
                    self._tasks.finish(
                        task_id,
                        run["status"],
                        result={
                            "run_id": run_id,
                            "counts": json.loads(run["counts_json"] or "{}"),
                        },
                    )
                    return
                self._tasks.finish(task_id, "failed", error=error)
            with self._connection:
                self._connection.execute(
                    "UPDATE discovery_run SET status = 'failed', error_json = ?, finished_at = ? "
                    "WHERE run_id = ? AND status = 'processing'",
                    (json.dumps(error), timestamp, run_id),
                )
                self._connection.execute(
                    "UPDATE discovery_run_source SET status = 'failed', error_json = ?, "
                    "last_attempt_at = ? WHERE run_id = ? AND status IN ('queued', 'processing')",
                    (json.dumps(error), timestamp, run_id),
                )
        except Exception:
            # A broken connection must not mask the original failure.
            return

    def _reap_stale(self) -> None:
        """Fail discovery tasks whose heartbeat stopped and that no live run owns."""
        with _ACTIVE_LOCK:
            active = set(_ACTIVE_TASKS)
        stale = self._tasks.reap_stale(
            exclude=active, older_than_s=STALE_AFTER_S, types=("discovery",)
        )
        if not stale:
            return
        error = {
            "code": "stale_run",
            "message": "Run discovery berhenti sebelum selesai.",
            "stage": "fetch",
            "retryable": True,
            "run_id": None,
            "request_id": None,
            "details": [],
        }
        placeholders = ", ".join("?" for _ in stale)
        with self._connection:
            self._connection.execute(
                f"UPDATE discovery_run SET status = 'failed', error_json = ?, finished_at = ? "
                f"WHERE status = 'processing' AND task_id IN ({placeholders})",
                (json.dumps(error), now_iso(), *stale),
            )

    def retry(
        self,
        task_id: str,
        *,
        scope: str | None = None,
        source_ids: list[str] | None = None,
    ) -> dict:
        """Repeat failed or partial sources; successful results stay untouched.

        ``scope=None`` is the default and means "failed sources only". ``all``
        must be requested explicitly and then repeats every source of the run.
        """
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
        if scope in {None, "failed_sources"}:
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

    def _select_sources(
        self, source_ids: list[str] | None, *, due_only: bool = False
    ) -> list[dict]:
        if not source_ids:
            return self._registry.due() if due_only else self._registry.enabled_verified()
        selected: list[dict] = []
        missing: list[str] = []
        seen: set[str] = set()
        for source_id in source_ids:
            if source_id in seen:
                continue
            seen.add(source_id)
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
        # The stored ETag is read here, on the caller's thread: the fetch workers
        # must not touch the shared MySQL connection.
        etags = {source["source_id"]: self._stored_etag(source["source_id"]) for source in sources}
        deadline = time.monotonic() + self._max_run_seconds
        results: list[_SourceResult] = []
        pool = ThreadPoolExecutor(max_workers=self._max_workers)
        try:
            futures = [
                (pool.submit(self._fetch_one, source, etags[source["source_id"]]), source)
                for source in sources
            ]
            for future, source in futures:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    results.append(_timeout_result(source))
                    continue
                try:
                    results.append(future.result(timeout=remaining))
                except FuturesTimeout:
                    results.append(_timeout_result(source))
                except Exception:
                    results.append(
                        _SourceResult(
                            source=source,
                            error=FetchError(
                                "source_error", "Sumber gagal diambil.", retryable=True
                            ),
                        )
                    )
        finally:
            # A source still blocked in a fetch is abandoned; its own HTTP
            # timeout bounds it, and the run must not wait past the deadline.
            pool.shutdown(wait=False, cancel_futures=True)
        return results

    def _fetch_one(self, source: dict, etag: str | None = None) -> _SourceResult:
        adapter = ADAPTERS.get(source["ats"])
        if adapter is None:
            return _SourceResult(
                source=source,
                error=FetchError(
                    "source_unsupported", "Adapter ATS belum tersedia.", retryable=False
                ),
                requests=0,
            )
        requests = 1
        try:
            response = fetch_source(
                source,
                adapter,
                fetcher=self._fetcher,
                limiter=self._limiter,
                etag=etag,
            )
        except FetchError as exc:
            # The request was attempted, so it is spent even though it failed.
            return _SourceResult(
                source=source, error=exc, requests=getattr(exc, "requests", 1)
            )
        except AdapterError as exc:
            return _SourceResult(
                source=source,
                error=FetchError("source_unavailable", str(exc), retryable=False),
                requests=1,
            )
        except Exception:
            return _SourceResult(
                source=source,
                error=FetchError("source_error", "Sumber gagal diambil.", retryable=True),
                requests=1,
            )
        if response.not_modified:
            # Nothing changed on the board, so nothing to parse, store or close.
            return _SourceResult(
                source=source,
                response=response,
                jobs=[],
                skipped=0,
                not_modified=True,
                requests=requests,
            )
        try:
            jobs = adapter.parse(response.body, source)
            raw = response.body
        except AdapterError as exc:
            return _SourceResult(
                source=source,
                response=response,
                error=FetchError("source_parse_failed", str(exc), retryable=False),
                requests=requests,
            )
        except Exception:
            return _SourceResult(
                source=source,
                response=response,
                error=FetchError("source_error", "Payload sumber tidak dapat dibaca.", retryable=False),
                requests=requests,
            )
        return _SourceResult(
            source=source,
            response=response,
            jobs=jobs,
            skipped=jobs.skipped,
            complete=getattr(jobs, "complete", True),
            requests=requests,
            raw=raw,
            skip_reasons=getattr(jobs, "skip_reasons", {}),
        )

    def _persist_source(self, run_id: str, result: _SourceResult) -> dict:
        source = result.source
        fetched_at = now_iso()
        self._registry.mark_checked(source["source_id"], fetched_at)
        if result.error is not None:
            error = _error_payload(result.error, run_id)
            raw = result.response.body if result.response else ""
            self._store_fetch(run_id, source["source_id"], result.response, raw, error)
            # Health and the next slot are recorded for every attempt, so a
            # failing board backs off instead of being retried on the next run.
            self._registry.record_outcome(
                source,
                fetched_at,
                error_code=result.error.code,
                retry_after_s=result.error.retry_after_s,
            )
            self._update_source_progress(
                run_id, source["source_id"], status="failed", fetched=0, accepted=0,
                duplicates=0, error=error, close_skipped=None, stats=None,
                requests=result.requests,
            )
            return {"status": "failed", "fetched": 0, "accepted": 0, "duplicates": 0}

        if result.not_modified:
            # The board answered 304, so the stored snapshot still holds. Nothing
            # is parsed and nothing is closed: an empty "seen" set would mark
            # every job as missing. No fetch row is written because there is no
            # payload to keep; the previous row still describes the content.
            self._registry.record_outcome(source, fetched_at)
            self._update_source_progress(
                run_id, source["source_id"], status="completed", fetched=0, accepted=0,
                duplicates=0, error=None, close_skipped=None,
                stats={"not_modified": 1}, requests=result.requests,
            )
            return {"status": "completed", "fetched": 0, "accepted": 0, "duplicates": 0}

        raw = result.raw if result.raw is not None else (
            result.response.body if result.response else ""
        )
        self._store_fetch(run_id, source["source_id"], result.response, raw, None)
        raw_sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        fetched = 0
        invalid = 0
        accepted = 0
        duplicates = 0
        truncated = 0
        stale = 0
        seen: set[str] = set()
        for raw_job in result.jobs or []:
            fetched += 1
            try:
                record = normalize(raw_job, source, fetched_at)
            except InvalidJob:
                invalid += 1
                continue
            seen.add(record["source_job_id"])
            if record["description_truncated"]:
                truncated += 1
            if record["completeness"]["stale"]:
                stale += 1
            created, job_id, _version_added = self._store_job(record, raw_sha, fetched_at)
            if created:
                accepted += 1
            else:
                duplicates += 1
            # Cross-source duplicates are recorded in duplicate_of; duplicate_count
            # keeps its documented meaning of "already seen on this source".
            link_duplicate(self._connection, job_id, record)
        close_skipped = _close_decision(fetched, invalid, seen, result.response)
        if close_skipped is None and not result.complete:
            # A page is not the board. Closing on a partial snapshot would mark
            # every job on another page as gone.
            close_skipped = _skip_error(
                "partial_snapshot",
                "Payload hanya sebagian dari board; penutupan lowongan dilewati.",
            )
        closed = 0 if close_skipped else self._close_missing(
            source["source_id"], seen, fetched_at
        )
        self._registry.record_outcome(source, fetched_at)
        stats = {
            "skipped": result.skipped,
            "invalid": invalid,
            "truncated": truncated,
            "stale": stale,
            "requests": result.requests,
        }
        if result.skip_reasons:
            stats["skip_reasons"] = result.skip_reasons
        self._update_source_progress(
            run_id, source["source_id"], status="completed", fetched=fetched,
            accepted=accepted, duplicates=duplicates, error=None,
            close_skipped=close_skipped, stats=stats, requests=result.requests,
        )
        return {
            "status": "completed",
            "fetched": fetched,
            "accepted": accepted,
            "duplicates": duplicates,
            "closed": closed,
            "close_skipped": close_skipped,
            "stats": stats,
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
                "fetched_at, raw_sha256, raw_json, error_json, final_url, etag) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    response.final_url if response else None,
                    response.etag if response else None,
                ),
            )

    def _stored_etag(self, source_id: str) -> str | None:
        """Last ETag that came with a full payload for this source."""
        row = self._connection.execute(
            "SELECT etag FROM source_fetch WHERE source_id = ? AND etag IS NOT NULL "
            "AND status = 'completed' ORDER BY fetched_at DESC LIMIT 1",
            (source_id,),
        ).fetchone()
        return row["etag"] if row else None

    def _store_job(self, record: dict, raw_sha: str, fetched_at: str) -> tuple[bool, str, bool]:
        """Returns ``(created, job_id, version_added)``.

        ``version_added`` is True only when a posting version was inserted, so a
        caller can tell a real content change from a repeated import.
        """
        existing = self._connection.execute(
            "SELECT job_id, latest_version_id FROM job WHERE source_id = ? AND source_job_id = ?",
            (record["source_id"], record["source_job_id"]),
        ).fetchone()
        if existing is not None:
            version = self._connection.execute(
                "SELECT job_posting_version_id, content_hash FROM job_posting_version "
                "WHERE job_id = ? AND content_hash = ?",
                (existing["job_id"], record["content_hash"]),
            ).fetchone()
            timestamp = now_iso()
            if version is None:
                latest = self._insert_version(
                    existing["job_id"], record, raw_sha, fetched_at
                )
                with self._connection:
                    self._connection.execute(
                        "UPDATE job SET canonical_url = ?, apply_url = COALESCE(?, apply_url), "
                        "company = ?, "
                        "title = ?, location_json = ?, work_mode = ?, employment_type = ?, "
                        "seniority = ?, market = ?, posted_at = ?, posted_at_epoch = ?, "
                        "fetched_at = ?, "
                        "last_seen_at = ?, latest_version_id = ?, description_truncated = ?, "
                        "stale = ?, fingerprint = ?, status = 'open', updated_at = ? "
                        "WHERE job_id = ?",
                        (
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
                            posted_epoch(record["posted_at"]),
                            fetched_at,
                            fetched_at,
                            latest,
                            1 if record["description_truncated"] else 0,
                            1 if record["completeness"]["stale"] else 0,
                            record["fingerprint"],
                            timestamp,
                            existing["job_id"],
                        ),
                    )
            else:
                # Same content: no new version, but a stored job may predate the
                # adapter that supplies apply_url. COALESCE keeps an existing
                # URL when this snapshot has none, so a source that drops the
                # field never erases a valid link. The fingerprint is derived
                # from the record, so refreshing it keeps dedupe consistent
                # after a normalisation change.
                with self._connection:
                    self._connection.execute(
                        "UPDATE job SET fetched_at = ?, last_seen_at = ?, "
                        "latest_version_id = ?, status = 'open', fingerprint = ?, "
                        "apply_url = COALESCE(?, apply_url), posted_at_epoch = ?, "
                        "updated_at = ? "
                        "WHERE job_id = ?",
                        (
                            fetched_at,
                            fetched_at,
                            version["job_posting_version_id"],
                            record["fingerprint"],
                            record["apply_url"],
                            posted_epoch(record["posted_at"]),
                            timestamp,
                            existing["job_id"],
                        ),
                    )
            return False, existing["job_id"], version is None

        job_id = new_id("job")
        timestamp = now_iso()
        with self._connection:
            self._connection.execute(
                "INSERT INTO job (job_id, source_id, source_job_id, canonical_url, apply_url, "
                "company, title, location_json, work_mode, employment_type, seniority, market, "
                "posted_at, posted_at_epoch, fetched_at, status, duplicate_of, fingerprint, "
                "latest_version_id, "
                "description_truncated, stale, completeness_json, created_at, updated_at, "
                "last_seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', NULL, ?, NULL, ?, ?, "
                "?, ?, ?, ?)",
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
                    posted_epoch(record["posted_at"]),
                    fetched_at,
                    record["fingerprint"],
                    1 if record["description_truncated"] else 0,
                    1 if record["completeness"]["stale"] else 0,
                    json.dumps(record["completeness"], ensure_ascii=False),
                    timestamp,
                    timestamp,
                    fetched_at,
                ),
            )
        version_id = self._insert_version(job_id, record, raw_sha, fetched_at)
        with self._connection:
            self._connection.execute(
                "UPDATE job SET latest_version_id = ? WHERE job_id = ?", (version_id, job_id)
            )
        return True, job_id, True

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
        close_skipped: dict | None,
        stats: dict | None,
        requests: int = 1,
    ) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE discovery_run_source SET status = ?, fetched_count = ?, "
                "accepted_count = ?, duplicate_count = ?, request_count = ?, "
                "last_attempt_at = ?, error_json = ?, "
                "close_skipped_json = ?, stats_json = ? WHERE run_id = ? AND source_id = ?",
                (
                    status,
                    fetched,
                    accepted,
                    duplicates,
                    requests,
                    now_iso(),
                    json.dumps(error) if error else None,
                    json.dumps(close_skipped) if close_skipped else None,
                    json.dumps(stats) if stats else None,
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
        """Keyset pagination on (started_at, run_id); sources load in one query."""
        params: list = []
        where = ""
        if cursor:
            anchor = self._connection.execute(
                "SELECT started_at, run_id FROM discovery_run WHERE run_id = ?", (cursor,)
            ).fetchone()
            if anchor is None:
                return [], None
            where = "WHERE started_at < ? OR (started_at = ? AND run_id < ?)"
            params = [anchor["started_at"], anchor["started_at"], anchor["run_id"]]
        rows = self._connection.execute(
            f"SELECT * FROM discovery_run {where} "
            "ORDER BY started_at DESC, run_id DESC LIMIT ?",
            (*params, limit + 1),
        ).fetchall()
        has_more = len(rows) > limit
        page = rows[:limit]
        run_ids = [row["run_id"] for row in page]
        sources: dict[str, list[dict]] = {run_id: [] for run_id in run_ids}
        if run_ids:
            placeholders = ", ".join("?" for _ in run_ids)
            for item in self._connection.execute(
                f"SELECT * FROM discovery_run_source WHERE run_id IN ({placeholders}) "
                "ORDER BY company",
                run_ids,
            ).fetchall():
                sources[item["run_id"]].append(_to_progress(item))
        runs = [self._to_run(row, sources[row["run_id"]]) for row in page]
        return runs, (page[-1]["run_id"] if has_more else None)

    def job_total(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) AS total FROM job").fetchone()
        return int(row["total"]) if row else 0

    def _to_run(self, row: dict, sources: list[dict] | None = None) -> dict:
        if sources is None:
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


def _close_decision(
    fetched: int, invalid: int, seen: set[str], response: FetchResponse | None
) -> dict | None:
    """Return a diagnosis when this snapshot must not close absent jobs."""
    if response is not None and response.truncated:
        return _skip_error("payload_truncated", "Payload sumber terindikasi terpotong.")
    if fetched == 0:
        return _skip_error("empty_snapshot", "Snapshot tidak memuat record.")
    if not seen:
        return _skip_error(
            "all_records_invalid", "Semua record gagal dinormalisasi."
        )
    if invalid / fetched > MAX_INVALID_RATIO:
        return _skip_error(
            "invalid_ratio_high",
            f"Rasio record invalid melebihi {MAX_INVALID_RATIO:.0%}.",
        )
    return None


def _planned_requests(source: dict) -> int:
    """HTTP requests this source will spend in one run, at most.

    The quota check must reserve the whole run, so a source is skipped whole
    rather than fetched partially.
    """
    adapter = ADAPTERS.get(source.get("ats") or "")
    return max(1, int(getattr(adapter, "MAX_REQUESTS", 1)))


def _skip_reason(source: dict, *, planned_requests: int = 1) -> dict | None:
    if not source["enabled"]:
        return _skip_error("source_not_verified", "Sumber nonaktif.")
    if source["verification_status"] != FETCHABLE:
        return _skip_error("source_not_verified", "Sumber belum diverifikasi.")
    if source["access_method"] != "ats_api":
        return _skip_error("source_unsupported", "Sumber tanpa akses API tidak di-fetch.")
    if source["ats"] not in ADAPTERS:
        return _skip_error("source_unsupported", "Adapter ATS belum tersedia.")
    quota = int(source.get("daily_request_quota") or 0)
    if quota <= 0:
        return None
    used = int(source.get("requests_last_24h") or 0)
    # Skip the source whole when the remaining quota cannot cover this run. A
    # half-fetched fetch would look like a partial board, and a partial board
    # must never close absent jobs.
    if quota_exhausted(used, quota) or used + planned_requests > quota:
        return _skip_error(
            "source_quota_exhausted",
            "Kuota request harian sumber tidak cukup untuk kebutuhan run.",
        )
    return None


def posted_epoch(value: str | None) -> int:
    """Unix seconds for an ISO timestamp; 0 when unknown (sorts last)."""
    if not value:
        return 0
    try:
        from datetime import datetime, timezone

        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def _timeout_result(source: dict) -> _SourceResult:
    # shortcut: a timed-out source is charged one request even though it may have
    # spent more. Upgrade if quota accounting must be exact on timeouts.
    return _SourceResult(
        source=source,
        error=FetchError(
            "run_timeout", "Batas durasi run discovery tercapai.", retryable=True
        ),
    )


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
        "close_skipped": (
            json.loads(row["close_skipped_json"]) if row["close_skipped_json"] else None
        ),
        "stats": json.loads(row["stats_json"]) if row["stats_json"] else None,
    }
