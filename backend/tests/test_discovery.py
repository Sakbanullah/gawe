"""Discovery run: profile gate, per-source status, raw evidence, and limits."""

from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from gawe.jobs.fetch import FetchError, FetchResponse, HostRateLimiter, http_fetch
from gawe.jobs.sources import registry as registry_module
from gawe.jobs.sources.base import AdapterError
from tests.conftest import extract_profile, latest_profile, upload_cv

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "jobs" / "raw"
GREENHOUSE = (FIXTURES / "greenhouse_board.json").read_text(encoding="utf-8")
LEVER = (FIXTURES / "lever_postings.json").read_text(encoding="utf-8")
ASHBY = (FIXTURES / "ashby_job_board.json").read_text(encoding="utf-8")


class _NoopLimiter:
    def wait(self, host: str) -> None:
        return None


class _Fetcher:
    def __init__(self, responses=None, fail_hosts=None, delay=0.0, truncated=False) -> None:
        self.responses = responses or {}
        self.fail_hosts = fail_hosts or {}
        self.delay = delay
        self.truncated = truncated
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def __call__(self, url: str) -> FetchResponse:
        with self._lock:
            self.calls.append(url)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            for host, error in self.fail_hosts.items():
                if host in url:
                    raise error
            for host, body in self.responses.items():
                if host in url:
                    return FetchResponse(200, body, url, truncated=self.truncated)
            raise FetchError("source_unavailable", "no fixture", retryable=True)
        finally:
            with self._lock:
                self.active -= 1


def _confirm(client, csrf) -> dict:
    upload_cv(client, csrf)
    extract_profile(client, csrf)
    profile = latest_profile(client)
    response = client.post(
        f"/api/setup/profiles/{profile['profile_version_id']}/confirm", headers=csrf, json={}
    )
    assert response.status_code == 200, response.json()
    return profile


def _create_source(client, csrf, monkeypatch, *, company, board, ats="greenhouse") -> dict:
    monkeypatch.setattr(registry_module, "validate_url", lambda url: SimpleNamespace(url=url))
    if ats == "greenhouse":
        careers_url = f"https://boards.greenhouse.io/{board}"
    elif ats == "lever":
        careers_url = f"https://jobs.lever.co/{board}"
    else:
        careers_url = f"https://jobs.ashbyhq.com/{board}"
    created = client.post(
        "/api/settings/sources",
        headers=csrf,
        json={
            "company": company,
            "market": "global",
            "careers_url": careers_url,
            "access_method": "ats_api",
            "ats": ats,
        },
    )
    assert created.status_code == 201, created.json()
    source_id = created.json()["source_id"]
    verified = client.patch(
        f"/api/settings/sources/{source_id}",
        headers=csrf,
        json={"verification_status": "verified", "enabled": True},
    )
    assert verified.status_code == 200, verified.json()
    return verified.json()


def _use(client, fetcher, monkeypatch) -> None:
    monkeypatch.setattr(client.app.state, "discovery_fetcher", fetcher, raising=False)
    monkeypatch.setattr(client.app.state, "discovery_limiter", _NoopLimiter(), raising=False)


def test_no_discovery_without_confirmed_profile(
    setup_client, csrf, monkeypatch
) -> None:
    _create_source(setup_client, csrf, monkeypatch, company="Acme", board="acme")
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)

    response = setup_client.post("/api/discovery/runs", headers=csrf, json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "profile_not_confirmed"
    assert fetcher.calls == []


def test_run_stores_jobs_with_source_and_raw_hash(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    greenhouse = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    lever = _create_source(
        setup_client, csrf, monkeypatch, company="Beta", board="beta", ats="lever"
    )
    fetcher = _Fetcher({"boards-api": GREENHOUSE, "api.lever.co": LEVER})
    _use(setup_client, fetcher, monkeypatch)

    response = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [greenhouse["source_id"], lever["source_id"]]}
    )
    assert response.status_code == 202, response.json()
    run_id = response.json()["run_id"]

    run = setup_client.get(f"/api/discovery/runs/{run_id}").json()
    assert run["status"] == "completed"
    assert run["profile_version_id"]
    assert run["counts"]["fetched"] == 4
    assert run["counts"]["new_jobs"] == 4
    assert {item["status"] for item in run["sources"]} == {"completed"}
    assert all(item["last_attempt_at"] for item in run["sources"])

    task = setup_client.get(f"/api/tasks/{response.json()['task_id']}").json()
    assert task["status"] == "completed"
    assert task["progress"]["percent"] == 100
    assert len(task["sources"]) == 2

    checked = setup_client.get(
        f"/api/settings/sources/{greenhouse['source_id']}"
    ).json()
    assert checked["last_checked_at"] is not None

    jobs = connection.execute(
        "SELECT * FROM job ORDER BY source_id, source_job_id"
    ).fetchall()
    assert len(jobs) == 4
    assert all(job["source_id"] and job["canonical_url"] and job["fetched_at"] for job in jobs)

    fetch = connection.execute(
        "SELECT * FROM source_fetch WHERE source_id = ?", (greenhouse["source_id"],)
    ).fetchone()
    assert fetch["raw_sha256"] == hashlib.sha256(GREENHOUSE.encode("utf-8")).hexdigest()
    assert fetch["final_url"] == "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
    assert json.loads(fetch["raw_json"])["meta"]["total"] == 2

    versions = connection.execute(
        "SELECT raw_sha256 FROM job_posting_version WHERE source_id = ?",
        (greenhouse["source_id"],),
    ).fetchall()
    assert len(versions) == 2
    assert all(
        row["raw_sha256"] == hashlib.sha256(GREENHOUSE.encode("utf-8")).hexdigest()
        for row in versions
    )


def test_one_failed_source_keeps_partial_results(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    greenhouse = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    lever = _create_source(
        setup_client, csrf, monkeypatch, company="Beta", board="beta", ats="lever"
    )
    fetcher = _Fetcher(
        {"boards-api": GREENHOUSE},
        fail_hosts={"api.lever.co": FetchError("source_unavailable", "blocked", retryable=False)},
    )
    _use(setup_client, fetcher, monkeypatch)

    response = setup_client.post(
        "/api/discovery/runs",
        headers=csrf,
        json={"source_ids": [greenhouse["source_id"], lever["source_id"]]},
    )
    assert response.status_code == 202
    run = setup_client.get(f"/api/discovery/runs/{response.json()['run_id']}").json()
    assert run["status"] == "partial"
    statuses = {item["source_id"]: item["status"] for item in run["sources"]}
    assert statuses[greenhouse["source_id"]] == "completed"
    assert statuses[lever["source_id"]] == "failed"
    failed = next(item for item in run["sources"] if item["status"] == "failed")
    assert failed["error"]["code"] == "source_unavailable"
    assert failed["error"]["retryable"] is False

    jobs = connection.execute("SELECT COUNT(*) FROM job").fetchone()
    assert jobs[0] == 2


def test_unverified_source_is_skipped_not_fetched(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    monkeypatch.setattr(registry_module, "validate_url", lambda url: SimpleNamespace(url=url))
    created = setup_client.post(
        "/api/settings/sources",
        headers=csrf,
        json={
            "company": "Acme",
            "market": "global",
            "careers_url": "https://boards.greenhouse.io/acme",
            "access_method": "ats_api",
            "ats": "greenhouse",
        },
    ).json()
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)

    response = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [created["source_id"]]}
    )
    assert response.status_code == 202
    run = setup_client.get(f"/api/discovery/runs/{response.json()['run_id']}").json()
    assert run["sources"][0]["status"] == "skipped"
    assert run["sources"][0]["error"]["code"] == "source_not_verified"
    assert fetcher.calls == []


def test_no_enabled_sources_is_a_gate(setup_client, csrf) -> None:
    _confirm(setup_client, csrf)
    response = setup_client.post("/api/discovery/runs", headers=csrf, json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_enabled_sources"


def test_parallel_fetch_is_capped_at_three(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    ids = []
    for index in range(5):
        source = _create_source(
            setup_client, csrf, monkeypatch, company=f"Acme {index}", board=f"acme{index}"
        )
        ids.append(source["source_id"])
    fetcher = _Fetcher({"boards-api": GREENHOUSE}, delay=0.05)
    _use(setup_client, fetcher, monkeypatch)

    response = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": ids}
    )
    assert response.status_code == 202
    assert len(fetcher.calls) == 5
    assert 1 < fetcher.max_active <= 3


def test_fetch_all_stops_at_the_run_deadline(connection) -> None:
    from gawe.services.discovery_service import DiscoveryService

    fetcher = _Fetcher({"boards-api": GREENHOUSE}, delay=0.8)
    service = DiscoveryService(
        connection, None, None, fetcher=fetcher, max_workers=1, max_run_seconds=1
    )
    sources = [
        {
            "source_id": f"src_{index}",
            "ats": "greenhouse",
            "careers_url": "https://boards.greenhouse.io/acme",
        }
        for index in range(3)
    ]
    started = time.monotonic()
    results = service._fetch_all(sources)
    elapsed = time.monotonic() - started

    assert len(results) == len(sources)
    assert results[0].error is None
    assert [result.error.code for result in results[1:]] == ["run_timeout"] * 2
    assert all(result.error.retryable for result in results[1:])
    assert elapsed < 2.5


def test_rate_limiter_reserves_one_slot_per_host_per_second() -> None:
    sleeps: list[float] = []
    limiter = HostRateLimiter(min_interval=1.0, clock=lambda: 100.0, sleep=sleeps.append)
    limiter.wait("api.lever.co")
    limiter.wait("api.lever.co")
    limiter.wait("boards-api.greenhouse.io")
    assert sleeps == [1.0]


def test_app_shares_one_limiter_across_requests(setup_client) -> None:
    limiter = setup_client.app.state.discovery_limiter
    assert isinstance(limiter, HostRateLimiter)
    assert setup_client.app.state.discovery_limiter is limiter


def test_http_fetch_stops_on_403_and_429(monkeypatch) -> None:
    import urllib.error

    from gawe.jobs import fetch as fetch_module
    from gawe.security.url_guard import SafeUrl

    monkeypatch.setattr(
        fetch_module,
        "validate_url",
        lambda url: SafeUrl(url=url, host="api.lever.co", port=443),
    )

    def _raise(status):
        class _Opener:
            def open(self, *args, **kwargs):
                raise urllib.error.HTTPError(
                    "https://api.lever.co/v0/postings/acme", status, "denied", {}, None
                )

        return _Opener()

    for status in (403, 429):
        monkeypatch.setattr(urllib.request, "build_opener", lambda *a, **k: _raise(status))
        with pytest.raises(FetchError) as exc:
            http_fetch("https://api.lever.co/v0/postings/acme", frozenset({"api.lever.co"}))
        assert exc.value.code == "source_unavailable"
        assert exc.value.retryable is False
        assert exc.value.http_status == status


def test_http_fetch_rejects_host_outside_allowlist(monkeypatch) -> None:
    from gawe.jobs import fetch as fetch_module
    from gawe.security.url_guard import SafeUrl

    monkeypatch.setattr(
        fetch_module,
        "validate_url",
        lambda url: SafeUrl(url=url, host="api.lever.co", port=443),
    )
    with pytest.raises(FetchError) as exc:
        http_fetch("https://api.lever.co/v0/postings/acme", frozenset({"api.ashbyhq.com"}))
    assert exc.value.code == "source_unavailable"
    assert exc.value.retryable is False


@pytest.mark.parametrize(
    ("content_type", "accepted"),
    [
        ("application/json", True),
        ("application/json; charset=utf-8", True),
        ("application/vnd.api+json", True),
        ("text/html; charset=utf-8", False),
        ("text/plain", False),
    ],
)
def test_http_fetch_accepts_only_json_content_types(
    monkeypatch, content_type, accepted
) -> None:
    import urllib.request

    from gawe.jobs import fetch as fetch_module
    from gawe.security.url_guard import SafeUrl

    monkeypatch.setattr(
        fetch_module,
        "validate_url",
        lambda url: SafeUrl(url=url, host="api.lever.co", port=443),
    )

    class _Response:
        status = 200
        headers = {"Content-Type": content_type}

        def read(self, _size: int) -> bytes:
            return b'{"jobs": []}'

        def geturl(self) -> str:
            return "https://api.lever.co/v0/postings/acme"

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

    class _Opener:
        def open(self, *args, **kwargs):
            return _Response()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *a, **k: _Opener())
    if accepted:
        response = http_fetch(
            "https://api.lever.co/v0/postings/acme", frozenset({"api.lever.co"})
        )
        assert response.content_type == content_type
        assert response.final_url == "https://api.lever.co/v0/postings/acme"
    else:
        with pytest.raises(FetchError) as exc:
            http_fetch(
                "https://api.lever.co/v0/postings/acme", frozenset({"api.lever.co"})
            )
        assert exc.value.code == "source_unavailable"
        assert exc.value.retryable is False


@pytest.mark.parametrize("status", [403, 429])
def test_access_denied_source_does_not_stop_others(
    setup_client, csrf, monkeypatch, connection, status
) -> None:
    _confirm(setup_client, csrf)
    greenhouse = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    lever = _create_source(
        setup_client, csrf, monkeypatch, company="Beta", board="beta", ats="lever"
    )
    fetcher = _Fetcher(
        {"boards-api": GREENHOUSE},
        fail_hosts={
            "api.lever.co": FetchError(
                "source_unavailable",
                "Sumber menolak akses otomatis.",
                retryable=False,
                http_status=status,
            )
        },
    )
    _use(setup_client, fetcher, monkeypatch)

    response = setup_client.post(
        "/api/discovery/runs",
        headers=csrf,
        json={"source_ids": [greenhouse["source_id"], lever["source_id"]]},
    )
    assert response.status_code == 202
    run = setup_client.get(f"/api/discovery/runs/{response.json()['run_id']}").json()
    assert run["status"] == "partial"
    statuses = {item["source_id"]: item["status"] for item in run["sources"]}
    assert statuses[greenhouse["source_id"]] == "completed"
    assert statuses[lever["source_id"]] == "failed"
    assert connection.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 2

    task = setup_client.get(f"/api/tasks/{response.json()['task_id']}").json()
    assert task["retry"]["retryable"] is False
    retry = setup_client.post(
        f"/api/tasks/{task['task_id']}/retry",
        headers=csrf,
        json={"scope": "failed_sources"},
    )
    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "task_not_retryable"


def test_retry_defaults_to_failed_sources_keeping_successful_results(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    greenhouse = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    lever = _create_source(
        setup_client, csrf, monkeypatch, company="Beta", board="beta", ats="lever"
    )
    fetcher = _Fetcher(
        {"boards-api": GREENHOUSE, "api.lever.co": LEVER},
        fail_hosts={
            "api.lever.co": FetchError("source_unavailable", "timeout", retryable=True)
        },
    )
    _use(setup_client, fetcher, monkeypatch)

    first = setup_client.post(
        "/api/discovery/runs",
        headers=csrf,
        json={"source_ids": [greenhouse["source_id"], lever["source_id"]]},
    ).json()
    assert setup_client.get(f"/api/discovery/runs/{first['run_id']}").json()[
        "status"
    ] == "partial"

    fetcher.fail_hosts = {}
    retry = setup_client.post(
        f"/api/tasks/{first['task_id']}/retry",
        headers=csrf,
    )
    assert retry.status_code == 202, retry.json()
    body = retry.json()
    assert body["task_id"] != first["task_id"]
    assert body["run_id"] != first["run_id"]

    task = setup_client.get(f"/api/tasks/{body['task_id']}").json()
    assert task["status"] == "completed"
    assert task["retry"]["attempt"] == 2
    assert task["retry"]["retried_from_task_id"] == first["task_id"]
    assert [item["source_id"] for item in task["sources"]] == [lever["source_id"]]
    assert task["sources"][0]["retry_count"] == 1

    jobs = connection.execute(
        "SELECT source_id, COUNT(*) AS total FROM job GROUP BY source_id"
    ).fetchall()
    counts = {row["source_id"]: row["total"] for row in jobs}
    assert counts == {greenhouse["source_id"]: 2, lever["source_id"]: 2}

    old_task = setup_client.get(f"/api/tasks/{first['task_id']}").json()
    assert old_task["status"] == "partial"


def test_retry_scope_all_repeats_every_source(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    greenhouse = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    lever = _create_source(
        setup_client, csrf, monkeypatch, company="Beta", board="beta", ats="lever"
    )
    fetcher = _Fetcher(
        {"boards-api": GREENHOUSE, "api.lever.co": LEVER},
        fail_hosts={
            "api.lever.co": FetchError("source_unavailable", "timeout", retryable=True)
        },
    )
    _use(setup_client, fetcher, monkeypatch)

    first = setup_client.post(
        "/api/discovery/runs",
        headers=csrf,
        json={"source_ids": [greenhouse["source_id"], lever["source_id"]]},
    ).json()

    fetcher.fail_hosts = {}
    retry = setup_client.post(
        f"/api/tasks/{first['task_id']}/retry",
        headers=csrf,
        json={"scope": "all"},
    )
    assert retry.status_code == 202, retry.json()
    task = setup_client.get(f"/api/tasks/{retry.json()['task_id']}").json()
    assert {item["source_id"] for item in task["sources"]} == {
        greenhouse["source_id"],
        lever["source_id"],
    }


def test_retry_scope_failed_sources_rejected_for_other_tasks(
    setup_client, csrf
) -> None:
    upload_cv(setup_client, csrf)
    extraction = setup_client.post("/api/setup/master-cv/extractions", headers=csrf)
    assert extraction.status_code == 202

    retry = setup_client.post(
        f"/api/tasks/{extraction.json()['task_id']}/retry",
        headers=csrf,
        json={"scope": "failed_sources"},
    )
    assert retry.status_code == 400
    error = retry.json()["error"]
    assert error["code"] == "validation_failed"
    assert error["details"][0]["code"] == "retry_scope_unsupported"


def test_duplicate_source_ids_are_deduplicated(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)

    response = setup_client.post(
        "/api/discovery/runs",
        headers=csrf,
        json={"source_ids": [source["source_id"], source["source_id"]]},
    )
    assert response.status_code == 202, response.json()
    run = setup_client.get(f"/api/discovery/runs/{response.json()['run_id']}").json()
    assert [item["source_id"] for item in run["sources"]] == [source["source_id"]]
    assert len(fetcher.calls) == 1


def test_persist_failure_fails_source_not_whole_run(
    setup_client, csrf, monkeypatch, connection
) -> None:
    from gawe.services.discovery_service import DiscoveryService

    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)

    def explode(self, run_id, result):
        raise RuntimeError("persist failed")

    monkeypatch.setattr(DiscoveryService, "_persist_source", explode)
    response = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    )
    assert response.status_code == 202, response.json()
    run = setup_client.get(f"/api/discovery/runs/{response.json()['run_id']}").json()
    assert run["status"] == "failed"
    assert run["sources"][0]["status"] == "failed"
    task = setup_client.get(f"/api/tasks/{response.json()['task_id']}").json()
    assert task["status"] == "failed"
    assert task["finished_at"] is not None
    assert connection.execute(
        "SELECT COUNT(*) FROM task WHERE status IN ('queued','processing')"
    ).fetchone()[0] == 0


def test_run_insert_failure_rolls_back_task(
    setup_client, setup_config, csrf, monkeypatch, connection
) -> None:
    from fastapi.testclient import TestClient

    from gawe.api.app import create_app
    from gawe.services import discovery_service as discovery_module

    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)
    first = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    ).json()
    task_count = connection.execute("SELECT COUNT(*) FROM task").fetchone()[0]
    original = discovery_module.new_id

    def collide(prefix: str) -> str:
        return first["run_id"] if prefix == "run" else original(prefix)

    monkeypatch.setattr(discovery_module, "new_id", collide)
    with TestClient(create_app(setup_config), raise_server_exceptions=False) as client:
        headers = {"X-CSRF-Token": client.get("/api/session").json()["csrf_token"]}
        response = client.post(
            "/api/discovery/runs",
            headers=headers,
            json={"source_ids": [source["source_id"]]},
        )
    assert response.status_code == 500
    assert connection.execute("SELECT COUNT(*) FROM task").fetchone()[0] == task_count
    assert connection.execute(
        "SELECT COUNT(*) FROM task WHERE status IN ('queued','processing')"
    ).fetchone()[0] == 0


def test_concurrent_start_is_rejected_and_lock_is_released(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    started = threading.Event()
    release = threading.Event()

    class _BlockingFetcher:
        def __call__(self, url: str) -> FetchResponse:
            started.set()
            assert release.wait(5)
            return FetchResponse(200, GREENHOUSE, url)

    _use(setup_client, _BlockingFetcher(), monkeypatch)
    result: dict = {}

    def first_run() -> None:
        result["response"] = setup_client.post(
            "/api/discovery/runs",
            headers=csrf,
            json={"source_ids": [source["source_id"]]},
        )

    thread = threading.Thread(target=first_run)
    thread.start()
    assert started.wait(5)
    second = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "task_already_running"
    active = connection.execute(
        "SELECT task_id FROM task WHERE type = 'discovery' "
        "AND status IN ('queued','processing')"
    ).fetchone()
    assert second.json()["error"]["active_task_id"] == active["task_id"]
    release.set()
    thread.join(10)
    assert result["response"].status_code == 202
    assert connection.execute(
        "SELECT IS_FREE_LOCK('gawe_discovery_run') AS free"
    ).fetchone()["free"] == 1


def test_repeated_content_reuses_version_and_keeps_latest_pointer(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)

    def run_once() -> dict:
        response = setup_client.post(
            "/api/discovery/runs",
            headers=csrf,
            json={"source_ids": [source["source_id"]]},
        )
        assert response.status_code == 202, response.json()
        run = setup_client.get(f"/api/discovery/runs/{response.json()['run_id']}").json()
        assert run["status"] == "completed"
        return run

    run_once()
    first_hash = connection.execute(
        "SELECT v.content_hash FROM job_posting_version v "
        "JOIN job j ON j.job_id = v.job_id "
        "WHERE j.source_id = ? AND j.source_job_id = '1001'",
        (source["source_id"],),
    ).fetchone()["content_hash"]

    payload = json.loads(GREENHOUSE)
    payload["jobs"][0]["title"] = "Senior Backend Engineer (Updated)"
    fetcher.responses = {"boards-api": json.dumps(payload)}
    run_once()
    second_hash = connection.execute(
        "SELECT v.content_hash FROM job_posting_version v "
        "JOIN job j ON j.job_id = v.job_id "
        "WHERE j.source_id = ? AND j.source_job_id = '1001' "
        "ORDER BY v.created_at DESC LIMIT 1",
        (source["source_id"],),
    ).fetchone()["content_hash"]
    assert second_hash != first_hash

    fetcher.responses = {"boards-api": GREENHOUSE}
    run_once()

    versions = connection.execute(
        "SELECT v.job_posting_version_id, v.content_hash FROM job_posting_version v "
        "JOIN job j ON j.job_id = v.job_id "
        "WHERE j.source_id = ? AND j.source_job_id = '1001' ORDER BY v.created_at",
        (source["source_id"],),
    ).fetchall()
    assert len(versions) == 2
    first_job = connection.execute(
        "SELECT latest_version_id FROM job WHERE source_id = ? AND source_job_id = '1001'",
        (source["source_id"],),
    ).fetchone()
    assert first_job["latest_version_id"] in {
        row["job_posting_version_id"] for row in versions if row["content_hash"] == first_hash
    }


def test_updated_content_refreshes_job_summary_columns(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)
    setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    )

    payload = json.loads(GREENHOUSE)
    payload["jobs"][0]["title"] = "Senior Backend Engineer (Updated)"
    payload["jobs"][0]["location"] = {"name": "Jakarta, Indonesia"}
    fetcher.responses = {"boards-api": json.dumps(payload)}
    response = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    )
    assert response.status_code == 202, response.json()

    job = connection.execute(
        "SELECT title, location_json, seniority, market FROM job "
        "WHERE source_id = ? AND source_job_id = '1001'",
        (source["source_id"],),
    ).fetchone()
    assert job["title"] == "Senior Backend Engineer (Updated)"
    assert json.loads(job["location_json"])["raw"] == "Jakarta, Indonesia"
    assert job["seniority"] == "senior"
    assert job["market"] == "indonesia"


def test_legacy_job_without_apply_url_is_backfilled_without_a_new_version(
    setup_client, csrf, monkeypatch, connection
) -> None:
    """A row stored before the adapter fix gets the URL on the next fetch.

    Same payload and same content hash: no new posting version, same job_id.
    """
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme", ats="ashby"
    )
    fetcher = _Fetcher({"api.ashbyhq.com": ASHBY})
    _use(setup_client, fetcher, monkeypatch)

    def run_once() -> None:
        response = setup_client.post(
            "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
        )
        assert response.status_code == 202, response.json()

    def job_row() -> dict:
        return connection.execute(
            "SELECT job_id, apply_url FROM job WHERE source_id = ? AND source_job_id = 'ash-3001'",
            (source["source_id"],),
        ).fetchone()

    def version_count() -> int:
        return connection.execute(
            "SELECT COUNT(*) AS n FROM job_posting_version WHERE job_id = ?",
            (job_row()["job_id"],),
        ).fetchone()["n"]

    run_once()
    assert job_row()["apply_url"] == "https://jobs.ashbyhq.com/acme/ash-3001/application"
    job_id = job_row()["job_id"]
    assert version_count() == 1

    # Emulate a row written before the adapter supplied apply_url.
    connection.execute("UPDATE job SET apply_url = NULL WHERE job_id = ?", (job_id,))

    run_once()
    assert job_row()["apply_url"] == "https://jobs.ashbyhq.com/acme/ash-3001/application"
    assert job_row()["job_id"] == job_id
    assert version_count() == 1


def test_stored_apply_url_survives_a_snapshot_without_it(
    setup_client, csrf, monkeypatch, connection
) -> None:
    """A source that stops sending applyUrl must not erase the stored URL."""
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme", ats="ashby"
    )
    fetcher = _Fetcher({"api.ashbyhq.com": ASHBY})
    _use(setup_client, fetcher, monkeypatch)

    def run_once() -> None:
        response = setup_client.post(
            "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
        )
        assert response.status_code == 202, response.json()

    def job_row() -> dict:
        return connection.execute(
            "SELECT job_id, apply_url FROM job WHERE source_id = ? AND source_job_id = 'ash-3001'",
            (source["source_id"],),
        ).fetchone()

    run_once()
    stored = job_row()["apply_url"]
    assert stored

    payload = json.loads(ASHBY)
    payload["jobs"][0].pop("applyUrl")
    fetcher.responses = {"api.ashbyhq.com": json.dumps(payload)}

    run_once()
    assert job_row()["apply_url"] == stored
    versions = connection.execute(
        "SELECT COUNT(*) AS n FROM job_posting_version WHERE job_id = ?",
        (job_row()["job_id"],),
    ).fetchone()["n"]
    assert versions == 1


def test_content_change_without_apply_url_keeps_the_stored_one(
    setup_client, csrf, monkeypatch, connection
) -> None:
    """The new-version path must not overwrite a valid URL with NULL either."""
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme", ats="ashby"
    )
    fetcher = _Fetcher({"api.ashbyhq.com": ASHBY})
    _use(setup_client, fetcher, monkeypatch)

    def run_once() -> None:
        response = setup_client.post(
            "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
        )
        assert response.status_code == 202, response.json()

    run_once()
    stored = connection.execute(
        "SELECT job_id, apply_url FROM job WHERE source_id = ? AND source_job_id = 'ash-3001'",
        (source["source_id"],),
    ).fetchone()["apply_url"]
    assert stored

    payload = json.loads(ASHBY)
    payload["jobs"][0]["title"] = "Senior Frontend Engineer"
    payload["jobs"][0].pop("applyUrl")
    fetcher.responses = {"api.ashbyhq.com": json.dumps(payload)}

    run_once()
    row = connection.execute(
        "SELECT j.job_id, j.apply_url, j.title, COUNT(v.job_posting_version_id) AS versions "
        "FROM job j JOIN job_posting_version v ON v.job_id = j.job_id "
        "WHERE j.source_id = ? AND j.source_job_id = 'ash-3001' GROUP BY j.job_id",
        (source["source_id"],),
    ).fetchone()
    assert row["title"] == "Senior Frontend Engineer"
    assert row["versions"] == 2
    assert row["apply_url"] == stored


def test_overview_reflects_latest_discovery_run(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)

    before = setup_client.get("/api/overview").json()
    assert before["discovery"] is None
    assert before["counts"]["total_jobs"] == 0
    assert before["recent_activity"] == []

    started = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    ).json()
    overview = setup_client.get("/api/overview").json()
    assert overview["discovery"]["run_id"] == started["run_id"]
    assert overview["counts"]["total_jobs"] == 2
    assert overview["active_task_id"] is None
    assert overview["recent_activity"][0]["workflow"] == "discovery"
    assert overview["recent_activity"][0]["task_id"] == started["task_id"]


def test_run_history_paginates_by_started_at_and_run_id(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)
    run_ids = []
    for _ in range(3):
        created = setup_client.post(
            "/api/discovery/runs",
            headers=csrf,
            json={"source_ids": [source["source_id"]]},
        )
        assert created.status_code == 202, created.json()
        run_ids.append(created.json()["run_id"])

    first = setup_client.get("/api/discovery/runs?limit=2").json()
    assert [item["run_id"] for item in first["items"]] == run_ids[::-1][:2]
    assert first["page"]["has_more"] is True
    second = setup_client.get(
        f"/api/discovery/runs?limit=2&cursor={first['page']['next_cursor']}"
    ).json()
    assert [item["run_id"] for item in second["items"]] == [run_ids[0]]
    assert second["page"]["has_more"] is False
    assert second["page"]["next_cursor"] is None


def test_truncated_description_is_persisted(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    payload = json.loads(GREENHOUSE)
    payload["jobs"] = [
        {
            **payload["jobs"][0],
            "content": "<p>" + ("x" * 90000) + "</p>",
        }
    ]
    fetcher = _Fetcher({"boards-api": json.dumps(payload)})
    _use(setup_client, fetcher, monkeypatch)
    created = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    )
    assert created.status_code == 202, created.json()

    job = connection.execute(
        "SELECT description_truncated FROM job WHERE source_id = ?",
        (source["source_id"],),
    ).fetchone()
    assert job["description_truncated"] == 1

    run = setup_client.get(f"/api/discovery/runs/{created.json()['run_id']}").json()
    assert run["sources"][0]["stats"]["truncated"] == 1


def test_run_reports_records_the_adapter_dropped(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme", ats="ashby"
    )
    fetcher = _Fetcher({"api.ashbyhq.com": ASHBY})
    _use(setup_client, fetcher, monkeypatch)
    created = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    )
    assert created.status_code == 202, created.json()

    run = setup_client.get(f"/api/discovery/runs/{created.json()['run_id']}").json()
    stats = run["sources"][0]["stats"]
    assert stats["skipped"] == 1
    assert stats["invalid"] == 0
    assert stats["truncated"] == 0
    assert run["sources"][0]["fetched_count"] == 1


def test_empty_snapshot_does_not_close_jobs(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)
    setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    )

    fetcher.responses = {"boards-api": '{"jobs": []}'}
    response = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    ).json()
    run = setup_client.get(f"/api/discovery/runs/{response['run_id']}").json()
    assert run["status"] == "completed"
    assert run["sources"][0]["close_skipped"]["code"] == "empty_snapshot"
    assert connection.execute(
        "SELECT COUNT(*) FROM job WHERE status = 'open'"
    ).fetchone()[0] == 2


def test_invalid_snapshot_does_not_close_jobs(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)
    setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    )

    fetcher.responses = {
        "boards-api": json.dumps(
            {"jobs": [{"id": 1, "absolute_url": "https://boards.greenhouse.io/acme/jobs/1"}]}
        )
    }
    response = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    ).json()
    run = setup_client.get(f"/api/discovery/runs/{response['run_id']}").json()
    assert run["status"] == "completed"
    assert run["sources"][0]["close_skipped"]["code"] == "all_records_invalid"
    assert connection.execute(
        "SELECT COUNT(*) FROM job WHERE status = 'open'"
    ).fetchone()[0] == 2


def test_high_invalid_ratio_does_not_close_jobs(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)
    setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    )

    payload = json.loads(GREENHOUSE)
    payload["jobs"] = [
        payload["jobs"][0],
        {"id": 9, "absolute_url": "https://boards.greenhouse.io/acme/jobs/9"},
        {"id": 10, "absolute_url": "https://boards.greenhouse.io/acme/jobs/10"},
    ]
    fetcher.responses = {"boards-api": json.dumps(payload)}
    response = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    ).json()
    run = setup_client.get(f"/api/discovery/runs/{response['run_id']}").json()
    assert run["status"] == "completed"
    assert run["sources"][0]["close_skipped"]["code"] == "invalid_ratio_high"
    assert connection.execute(
        "SELECT COUNT(*) FROM job WHERE status = 'open'"
    ).fetchone()[0] == 2


def test_truncated_payload_does_not_close_jobs(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)
    setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    )

    fetcher.truncated = True
    response = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    ).json()
    run = setup_client.get(f"/api/discovery/runs/{response['run_id']}").json()
    assert run["status"] == "completed"
    assert run["sources"][0]["close_skipped"]["code"] == "payload_truncated"
    assert connection.execute(
        "SELECT COUNT(*) FROM job WHERE status = 'open'"
    ).fetchone()[0] == 2


def test_jobs_absent_from_successful_fetch_are_closed_not_deleted(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)

    setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    )
    assert connection.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 2

    payload = json.loads(GREENHOUSE)
    payload["jobs"] = payload["jobs"][:1]
    fetcher.responses = {"boards-api": json.dumps(payload)}
    second = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    ).json()
    run = setup_client.get(f"/api/discovery/runs/{second['run_id']}").json()
    assert run["status"] == "completed"

    rows = connection.execute(
        "SELECT source_job_id, status FROM job ORDER BY source_job_id"
    ).fetchall()
    assert len(rows) == 2
    assert [row["status"] for row in rows].count("closed") == 1
    assert [row["status"] for row in rows].count("open") == 1

    fetcher.responses = {"boards-api": GREENHOUSE}
    setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    )
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM job WHERE status = 'open'"
        ).fetchone()[0]
        == 2
    )


def test_restricted_and_disabled_sources_are_skipped(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    restricted = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    disabled = _create_source(
        setup_client, csrf, monkeypatch, company="Beta", board="beta"
    )
    for source in (restricted, disabled):
        assert setup_client.patch(
            f"/api/settings/sources/{source['source_id']}",
            headers=csrf,
            json={"enabled": False},
        ).status_code == 200
    assert setup_client.patch(
        f"/api/settings/sources/{restricted['source_id']}",
        headers=csrf,
        json={"verification_status": "restricted"},
    ).status_code == 200

    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)
    response = setup_client.post(
        "/api/discovery/runs",
        headers=csrf,
        json={"source_ids": [restricted["source_id"], disabled["source_id"]]},
    )
    assert response.status_code == 202
    run = setup_client.get(f"/api/discovery/runs/{response.json()['run_id']}").json()
    assert {item["status"] for item in run["sources"]} == {"skipped"}
    assert fetcher.calls == []


def test_unexpected_fetch_exception_fails_run_without_blocking_next_run(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    fetcher = _Fetcher(fail_hosts={"boards-api": RuntimeError("boom")})
    _use(setup_client, fetcher, monkeypatch)

    first = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    )
    assert first.status_code == 202, first.json()
    run = setup_client.get(f"/api/discovery/runs/{first.json()['run_id']}").json()
    assert run["status"] == "failed"
    assert run["finished_at"] is not None
    assert run["sources"][0]["status"] == "failed"
    assert run["sources"][0]["error"]["code"] == "source_error"

    task = setup_client.get(f"/api/tasks/{first.json()['task_id']}").json()
    assert task["status"] == "failed"
    assert task["error"]["code"] == "discovery_failed"

    second = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    )
    assert second.status_code == 202, second.json()
    assert second.json()["task_id"] != first.json()["task_id"]


def test_stale_discovery_task_is_recovered(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)

    first = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    ).json()
    assert setup_client.get(f"/api/tasks/{first['task_id']}").json()["status"] == "completed"

    connection.execute(
        "UPDATE task SET status = 'processing', updated_at = ? WHERE task_id = ?",
        ("2020-01-01T00:00:00Z", first["task_id"]),
    )
    connection.execute(
        "UPDATE discovery_run SET status = 'processing', finished_at = NULL WHERE run_id = ?",
        (first["run_id"],),
    )
    connection.commit()

    blocked = setup_client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source["source_id"]]}
    )
    assert blocked.status_code == 202, blocked.json()

    stale_task = setup_client.get(f"/api/tasks/{first['task_id']}").json()
    assert stale_task["status"] == "failed"
    assert stale_task["error"]["code"] == "stale_run"
    stale_run = setup_client.get(f"/api/discovery/runs/{first['run_id']}").json()
    assert stale_run["status"] == "failed"
    assert stale_run["finished_at"] is not None


def test_adapter_error_from_build_url_is_contained(
    setup_client, csrf, monkeypatch
) -> None:
    from gawe.jobs.sources import greenhouse as greenhouse_module

    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )

    def explode(_source):
        raise AdapterError("greenhouse board token is invalid")

    monkeypatch.setattr(greenhouse_module, "build_url", explode)
    _use(setup_client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)

    response = setup_client.post(
        "/api/discovery/runs",
        headers=csrf,
        json={"source_ids": [source["source_id"]]},
    )
    assert response.status_code == 202, response.json()
    run = setup_client.get(f"/api/discovery/runs/{response.json()['run_id']}").json()
    assert run["status"] == "failed"
    assert run["sources"][0]["status"] == "failed"
    assert run["sources"][0]["error"]["code"] == "source_unavailable"
    assert run["sources"][0]["error"]["retryable"] is False

