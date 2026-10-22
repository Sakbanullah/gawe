"""Source health, backoff, quota, partial snapshots, and the scheduler gate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from gawe.jobs.health import is_due, quota_exhausted, retry_at, status_from
from gawe.jobs.sources import greenhouse
from gawe.jobs.sources import registry as registry_module
from gawe.jobs.sources.base import ParsedJobs
from gawe.services.scheduler import DiscoveryScheduler
from tests.conftest import extract_profile, latest_profile, upload_cv

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "jobs" / "raw"
GREENHOUSE = (FIXTURES / "greenhouse_board.json").read_text(encoding="utf-8")


class _NoopLimiter:
    def wait(self, host: str) -> None:
        return None


class _Fetcher:
    def __init__(self, responses=None, fail_hosts=None) -> None:
        self.responses = responses or {}
        self.fail_hosts = fail_hosts or {}
        self.calls: list[str] = []

    def __call__(self, url: str):
        from gawe.jobs.fetch import FetchError, FetchResponse

        self.calls.append(url)
        for host, error in self.fail_hosts.items():
            if host in url:
                raise error
        for host, body in self.responses.items():
            if host in url:
                return FetchResponse(200, body, url)
        raise FetchError("source_unavailable", "no fixture", retryable=True)


def _confirm(client, csrf) -> dict:
    upload_cv(client, csrf)
    extract_profile(client, csrf)
    profile = latest_profile(client)
    response = client.post(
        f"/api/setup/profiles/{profile['profile_version_id']}/confirm", headers=csrf, json={}
    )
    assert response.status_code == 200, response.json()
    return profile


def _create_source(client, csrf, monkeypatch, **extra) -> dict:
    monkeypatch.setattr(registry_module, "validate_url", lambda url: SimpleNamespace(url=url))
    created = client.post(
        "/api/settings/sources",
        headers=csrf,
        json={
            "company": "Acme",
            "market": "global",
            "careers_url": "https://boards.greenhouse.io/acme",
            "access_method": "ats_api",
            "ats": "greenhouse",
            **extra,
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


def _run(client, csrf, source_id) -> dict:
    response = client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source_id]}
    )
    assert response.status_code == 202, response.json()
    return client.get(f"/api/discovery/runs/{response.json()['run_id']}").json()


def _source(client, source_id) -> dict:
    return client.get(f"/api/settings/sources/{source_id}").json()


def test_successful_run_marks_the_source_healthy(setup_client, csrf, monkeypatch) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch)
    _use(setup_client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)

    _run(setup_client, csrf, source["source_id"])

    after = _source(setup_client, source["source_id"])
    assert after["health_status"] == "healthy"
    assert after["consecutive_failures"] == 0
    assert after["last_success_at"] is not None
    assert after["last_error_code"] is None
    assert after["next_run_at"] is not None
    assert after["requests_last_24h"] == 1
    assert after["stale"] is False


def test_failed_fetch_degrades_and_backs_off(setup_client, csrf, monkeypatch) -> None:
    from gawe.jobs.fetch import FetchError

    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch)
    _use(
        setup_client,
        _Fetcher(
            fail_hosts={
                "boards-api": FetchError("source_unavailable", "down", retryable=True)
            }
        ),
        monkeypatch,
    )

    _run(setup_client, csrf, source["source_id"])

    after = _source(setup_client, source["source_id"])
    assert after["health_status"] == "degraded"
    assert after["consecutive_failures"] == 1
    assert after["last_error_code"] == "source_unavailable"
    assert is_due(after["next_run_at"]) is False


def test_three_failures_report_the_source_as_broken(
    setup_client, csrf, monkeypatch
) -> None:
    from gawe.jobs.fetch import FetchError

    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch)
    _use(
        setup_client,
        _Fetcher(
            fail_hosts={
                "boards-api": FetchError("source_unavailable", "down", retryable=True)
            }
        ),
        monkeypatch,
    )
    for _ in range(3):
        _run(setup_client, csrf, source["source_id"])

    after = _source(setup_client, source["source_id"])
    assert after["health_status"] == "broken"
    assert after["consecutive_failures"] == 3


def test_retry_after_is_a_floor_for_the_next_slot(
    setup_client, csrf, monkeypatch
) -> None:
    from gawe.jobs.fetch import FetchError

    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, fetch_interval_minutes=5)
    _use(
        setup_client,
        _Fetcher(
            fail_hosts={
                "boards-api": FetchError(
                    "rate_limited", "slow down", retryable=True, retry_after_s=7200
                )
            }
        ),
        monkeypatch,
    )

    before = datetime.now(timezone.utc)
    _run(setup_client, csrf, source["source_id"])

    after = _source(setup_client, source["source_id"])
    slot = datetime.fromisoformat(after["next_run_at"].replace("Z", "+00:00"))
    # 5 minute interval backs off to 5 minutes; Retry-After wins.
    assert slot >= before + timedelta(seconds=7200 - 5)


def test_quota_exhausted_source_is_skipped(setup_client, csrf, monkeypatch) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, daily_request_quota=1)
    _use(setup_client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)

    _run(setup_client, csrf, source["source_id"])
    second = _run(setup_client, csrf, source["source_id"])

    assert second["sources"][0]["status"] == "skipped"
    assert second["sources"][0]["error"]["code"] == "source_quota_exhausted"


def test_quota_counts_requests_not_attempts(
    setup_client, csrf, monkeypatch, connection
) -> None:
    """One attempt may spend several requests; the quota must see them all."""
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, daily_request_quota=10)
    _use(setup_client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)

    _run(setup_client, csrf, source["source_id"])

    connection.execute(
        "UPDATE discovery_run_source SET request_count = 3 WHERE source_id = ?",
        (source["source_id"],),
    )
    assert _source(setup_client, source["source_id"])["requests_last_24h"] == 3


def test_a_304_still_spends_a_request(setup_client, csrf, monkeypatch) -> None:
    from gawe.jobs.fetch import FetchResponse

    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, daily_request_quota=10)

    class _NotModified:
        def __call__(self, url: str):
            return FetchResponse(304, "", url, not_modified=True)

    _use(setup_client, _NotModified(), monkeypatch)
    _run(setup_client, csrf, source["source_id"])

    assert _source(setup_client, source["source_id"])["requests_last_24h"] == 1


def test_a_failed_request_still_spends_quota(
    setup_client, csrf, monkeypatch, connection
) -> None:
    from gawe.jobs.fetch import FetchError

    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, daily_request_quota=10)
    _use(
        setup_client,
        _Fetcher(fail_hosts={"boards-api": FetchError("source_unavailable", "down", retryable=True)}),
        monkeypatch,
    )

    _run(setup_client, csrf, source["source_id"])

    row = connection.execute(
        "SELECT status, request_count, last_attempt_at FROM discovery_run_source "
        "WHERE source_id = ?",
        (source["source_id"],),
    ).fetchone()
    assert row["status"] == "failed"
    assert row["request_count"] == 1
    assert row["last_attempt_at"] is not None
    assert _source(setup_client, source["source_id"])["requests_last_24h"] == 1


def test_quota_that_cannot_cover_the_run_skips_the_source_whole(
    setup_client, csrf, monkeypatch
) -> None:
    """A source that pages needs its whole run reserved before the first request."""
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, daily_request_quota=2)
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)
    monkeypatch.setattr(greenhouse, "MAX_REQUESTS", 3, raising=False)

    run = _run(setup_client, csrf, source["source_id"])

    assert run["sources"][0]["status"] == "skipped"
    assert run["sources"][0]["error"]["code"] == "source_quota_exhausted"
    assert fetcher.calls == []


def test_partial_snapshot_does_not_close_jobs(setup_client, csrf, monkeypatch, connection) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch)
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)
    _run(setup_client, csrf, source["source_id"])

    record = _source(setup_client, source["source_id"])
    real = greenhouse.parse(GREENHOUSE, record)
    monkeypatch.setattr(
        greenhouse,
        "parse",
        lambda body, src: ParsedJobs(list(real), skipped=real.skipped, complete=False),
    )

    run = _run(setup_client, csrf, source["source_id"])

    assert run["sources"][0]["close_skipped"]["code"] == "partial_snapshot"
    assert connection.execute(
        "SELECT COUNT(*) FROM job WHERE status = 'open'"
    ).fetchone()[0] == 2


def test_health_endpoint_lists_every_source(setup_client, csrf, monkeypatch) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch)

    items = setup_client.get("/api/settings/sources/health").json()["items"]

    assert [item["source_id"] for item in items] == [source["source_id"]]
    assert items[0]["health_status"] == "unknown"
    assert items[0]["requests_last_24h"] == 0


def test_due_skips_a_source_scheduled_in_the_future(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch)
    future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    connection.execute(
        "UPDATE source_registry SET next_run_at = ? WHERE source_id = ?",
        (future, source["source_id"]),
    )

    assert registry_module.SourceRegistry(connection).due() == []


def test_scheduler_tick_does_nothing_without_a_confirmed_profile(
    setup_client, config
) -> None:
    assert DiscoveryScheduler(config).tick() is None


def test_health_helpers_are_pure_functions() -> None:
    assert status_from(0, ever_succeeded=False) == "unknown"
    assert status_from(0, ever_succeeded=True) == "healthy"
    assert status_from(1, ever_succeeded=True) == "degraded"
    assert status_from(3, ever_succeeded=True) == "broken"
    assert quota_exhausted(0, 0) is False  # 0 means "no quota"
    assert quota_exhausted(5, 5) is True
    assert is_due(None) is True
    assert is_due("not-a-date") is True
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert is_due("2026-01-01T00:00:00Z", now) is True
    assert is_due("2026-01-02T00:00:00Z", now) is False
    assert retry_at(now, 1, 60) == "2026-01-01T01:00:00Z"
