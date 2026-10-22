"""Himalayas end to end: a paged walk, its quota cost, and its evidence."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from gawe.jobs.fetch import FetchError, FetchResponse
from gawe.jobs.sources import registry as registry_module
from tests.conftest import extract_profile, latest_profile, upload_cv

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "jobs" / "raw"
FEED = (FIXTURES / "himalayas_feed.json").read_text(encoding="utf-8")


class _NoopLimiter:
    def wait(self, host: str) -> None:
        return None


class _FeedFetcher:
    """Serves the same fixture for every page, so the walk fills its budget."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, url: str) -> FetchResponse:
        self.calls.append(url)
        return FetchResponse(200, FEED, url)


class _FailsOnPage:
    """Answers ``ok`` pages, then fails: the spent requests still count."""

    def __init__(self, ok: int) -> None:
        self.ok = ok
        self.calls: list[str] = []

    def __call__(self, url: str) -> FetchResponse:
        self.calls.append(url)
        if len(self.calls) > self.ok:
            raise FetchError("source_unavailable", "Sumber tidak dapat dihubungi.", retryable=True)
        return FetchResponse(200, FEED, url)


def _confirm(client, csrf) -> None:
    upload_cv(client, csrf)
    extract_profile(client, csrf)
    profile = latest_profile(client)
    response = client.post(
        f"/api/setup/profiles/{profile['profile_version_id']}/confirm", headers=csrf, json={}
    )
    assert response.status_code == 200, response.json()


def _create_himalayas(client, csrf, monkeypatch, *, quota: int = 24) -> dict:
    monkeypatch.setattr(registry_module, "validate_url", lambda url: SimpleNamespace(url=url))
    created = client.post(
        "/api/settings/sources",
        headers=csrf,
        json={
            "company": "Himalayas",
            "market": "global",
            "careers_url": "https://himalayas.app/jobs",
            "access_method": "aggregator",
            "ats": "himalayas",
            "daily_request_quota": quota,
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


def _run(client, csrf, source_id: str) -> dict:
    response = client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source_id]}
    )
    assert response.status_code == 202, response.json()
    return client.get(f"/api/discovery/runs/{response.json()['run_id']}").json()


def _use(client, monkeypatch, fetcher) -> None:
    monkeypatch.setattr(client.app.state, "discovery_fetcher", fetcher, raising=False)
    monkeypatch.setattr(client.app.state, "discovery_limiter", _NoopLimiter(), raising=False)


def test_a_run_walks_five_pages_and_counts_five_requests(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_himalayas(setup_client, csrf, monkeypatch)
    fetcher = _FeedFetcher()
    _use(setup_client, monkeypatch, fetcher)

    _run(setup_client, csrf, source["source_id"])

    assert len(fetcher.calls) == 5
    assert fetcher.calls[0] == "https://himalayas.app/jobs/api?limit=20"
    assert "cursor=" in fetcher.calls[1]
    row = connection.execute(
        "SELECT request_count, status FROM discovery_run_source WHERE source_id = ?",
        (source["source_id"],),
    ).fetchone()
    assert row["status"] == "completed"
    assert row["request_count"] == 5
    listed = setup_client.get("/api/settings/sources").json()["items"]
    listed_source = next(item for item in listed if item["source_id"] == source["source_id"])
    assert listed_source["requests_last_24h"] == 5


def test_a_partial_walk_never_closes_jobs(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_himalayas(setup_client, csrf, monkeypatch)
    _use(setup_client, monkeypatch, _FeedFetcher())

    run = _run(setup_client, csrf, source["source_id"])

    assert run["sources"][0]["close_skipped"]["code"] == "partial_snapshot"
    assert connection.execute(
        "SELECT COUNT(*) FROM job WHERE status = 'closed'"
    ).fetchone()[0] == 0


def test_the_stored_evidence_is_a_page_manifest(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_himalayas(setup_client, csrf, monkeypatch)
    _use(setup_client, monkeypatch, _FeedFetcher())

    _run(setup_client, csrf, source["source_id"])

    raw = connection.execute(
        "SELECT raw_json FROM source_fetch WHERE source_id = ?", (source["source_id"],)
    ).fetchone()["raw_json"]
    manifest = json.loads(raw)
    assert [page["page"] for page in manifest["pages"]] == [1, 2, 3, 4, 5]
    assert all(page["sha256"] for page in manifest["pages"])
    assert "Grafana" not in raw


def test_records_keep_their_own_company(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_himalayas(setup_client, csrf, monkeypatch)
    _use(setup_client, monkeypatch, _FeedFetcher())

    _run(setup_client, csrf, source["source_id"])

    companies = {
        row["company"] for row in connection.execute("SELECT company FROM job").fetchall()
    }
    assert companies == {"Grafana Labs", "volga-partners"}


def test_the_skipped_records_are_reported_by_reason(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    source = _create_himalayas(setup_client, csrf, monkeypatch)
    _use(setup_client, monkeypatch, _FeedFetcher())

    run = _run(setup_client, csrf, source["source_id"])

    stats = run["sources"][0]["stats"]
    assert stats["skip_reasons"] == {"missing_company": 5, "duplicate_guid": 8}
    assert stats["requests"] == 5


def test_a_quota_that_cannot_pay_for_five_pages_skips_the_source(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    source = _create_himalayas(setup_client, csrf, monkeypatch, quota=4)
    fetcher = _FeedFetcher()
    _use(setup_client, monkeypatch, fetcher)

    run = _run(setup_client, csrf, source["source_id"])

    assert run["sources"][0]["status"] == "skipped"
    assert run["sources"][0]["error"]["code"] == "source_quota_exhausted"
    assert fetcher.calls == []


def test_a_failed_page_still_spends_the_requests_it_made(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_himalayas(setup_client, csrf, monkeypatch)
    fetcher = _FailsOnPage(ok=2)
    _use(setup_client, monkeypatch, fetcher)

    run = _run(setup_client, csrf, source["source_id"])

    assert run["sources"][0]["status"] == "failed"
    # Three requests were sent: two answered, the third failed. All three are
    # spent against the daily quota.
    assert len(fetcher.calls) == 3
    row = connection.execute(
        "SELECT request_count, status FROM discovery_run_source WHERE source_id = ?",
        (source["source_id"],),
    ).fetchone()
    assert row["status"] == "failed"
    assert row["request_count"] == 3


def test_a_failed_walk_closes_nothing(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_himalayas(setup_client, csrf, monkeypatch)
    _use(setup_client, monkeypatch, _FailsOnPage(ok=1))

    _run(setup_client, csrf, source["source_id"])

    assert connection.execute(
        "SELECT COUNT(*) FROM job WHERE status = 'closed'"
    ).fetchone()[0] == 0
