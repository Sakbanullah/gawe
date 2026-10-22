"""Himalayas adapter: company resolution, paging, and attribution. No network."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from gawe.jobs import ADAPTERS
from gawe.jobs.sources import himalayas
from gawe.jobs.sources.base import AdapterError, normalize

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "jobs" / "raw"
JOB_SCHEMA = json.loads(
    (ROOT / "docs" / "phase-00" / "contracts" / "job.schema.json").read_text(encoding="utf-8")
)
FEED = (FIXTURES / "himalayas_feed.json").read_text(encoding="utf-8")
SOURCE = {
    "source_id": "src_himalayas",
    "company": "Himalayas",
    "careers_url": "https://himalayas.app/jobs",
}


def _schema_record(record: dict) -> dict:
    return {
        "job_id": "job_test",
        "job_posting_version_id": "jpv_test",
        "content_hash": record["content_hash"],
        "source": {
            "source_id": SOURCE["source_id"],
            "source_kind": "registry",
            "company": SOURCE["company"],
            "verification_status": "verified",
            "access_method": "aggregator",
        },
        "company": record["company"],
        "title": record["title"],
        "location": record["location"],
        "work_mode": record["work_mode"],
        "employment_type": record["employment_type"],
        "seniority": record["seniority"],
        "market": record["market"],
        "posted_at": record["posted_at"],
        "fetched_at": record["fetched_at"],
        "canonical_url": record["canonical_url"],
        "apply_url": record["apply_url"],
        "apply_url_status": record["apply_url_status"],
        "priority_tier": record["priority_tier"],
        "priority_reason": record["priority_reason"],
        "priority_confidence": record["priority_confidence"],
        "description_text": record["description_text"],
        "description_truncated": record["description_truncated"],
        "requirements": record["requirements"],
        "duplicate_of": record["duplicate_of"],
        "completeness": record["completeness"],
    }


def test_a_named_company_is_used_as_published() -> None:
    jobs = ADAPTERS["himalayas"].parse(FEED, SOURCE)
    record = normalize(jobs[0], SOURCE, "2026-10-22T00:00:00Z")
    assert record["company"] == "Grafana Labs"
    assert "company_name" not in record["completeness"]["missing_fields"]
    jsonschema.validate(_schema_record(record), JOB_SCHEMA)


def test_a_missing_company_name_falls_back_to_the_slug() -> None:
    jobs = ADAPTERS["himalayas"].parse(FEED, SOURCE)
    record = normalize(jobs[1], SOURCE, "2026-10-22T00:00:00Z")
    assert record["company"] == "volga-partners"
    # A slug is not a published name, so the gap stays visible in completeness.
    assert "company_name" in record["completeness"]["missing_fields"]


def test_a_record_without_any_company_is_dropped() -> None:
    jobs = ADAPTERS["himalayas"].parse(FEED, SOURCE)
    assert len(jobs) == 2
    assert jobs.skip_reasons == {"missing_company": 1}


def test_the_aggregator_is_never_used_as_the_company() -> None:
    jobs = ADAPTERS["himalayas"].parse(FEED, SOURCE)
    for raw in jobs:
        record = normalize(raw, SOURCE, "2026-10-22T00:00:00Z")
        assert record["company"] != SOURCE["company"]


def test_apply_url_is_passed_through_unchanged() -> None:
    jobs = ADAPTERS["himalayas"].parse(FEED, SOURCE)
    record = normalize(jobs[0], SOURCE, "2026-10-22T00:00:00Z")
    assert record["apply_url"] == (
        "https://himalayas.app/companies/grafana-labs/jobs/"
        "staff-technical-writer-remote-usa?utm_source=api"
    )


def test_a_record_without_an_apply_link_keeps_no_apply_url() -> None:
    body = json.dumps(
        {
            "jobs": [
                {
                    "guid": "https://himalayas.app/companies/acme/jobs/x",
                    "title": "Engineer",
                    "companyName": "Acme",
                    "description": "<p>Work.</p>",
                }
            ]
        }
    )
    jobs = ADAPTERS["himalayas"].parse(body, SOURCE)
    assert jobs[0].apply_url is None


def test_posted_at_stays_unknown() -> None:
    """`pubDate` is the last update, not the posting date (O6)."""
    jobs = ADAPTERS["himalayas"].parse(FEED, SOURCE)
    record = normalize(jobs[0], SOURCE, "2026-10-22T00:00:00Z")
    assert record["posted_at"] is None
    assert "posted_at" in record["completeness"]["missing_fields"]


def test_an_empty_location_list_stays_unknown() -> None:
    jobs = ADAPTERS["himalayas"].parse(FEED, SOURCE)
    record = normalize(jobs[1], SOURCE, "2026-10-22T00:00:00Z")
    assert record["work_mode"] == "remote"
    # No restriction list means the source published no location. Calling that
    # "worldwide" would lift the geo scope without evidence.
    assert record["location"]["raw"] is None
    assert record["market"] == "unknown"
    assert "location" in record["completeness"]["missing_fields"]


def test_a_walked_page_set_is_never_the_whole_board() -> None:
    jobs = ADAPTERS["himalayas"].parse_pages([FEED], SOURCE)
    assert jobs.complete is False


def test_duplicate_guids_across_pages_are_read_once() -> None:
    jobs = ADAPTERS["himalayas"].parse_pages([FEED, FEED], SOURCE)
    assert len(jobs) == 2
    assert jobs.skip_reasons["duplicate_guid"] == 2


def test_the_feed_url_carries_the_cursor() -> None:
    adapter = ADAPTERS["himalayas"]
    assert adapter.build_url(SOURCE) == "https://himalayas.app/jobs/api?limit=20"
    assert (
        adapter.build_url(SOURCE, "a b")
        == "https://himalayas.app/jobs/api?limit=20&cursor=a%20b"
    )


def test_the_walk_is_capped_at_five_pages() -> None:
    assert himalayas.MAX_REQUESTS == 5
    assert himalayas.PAGE_LIMIT == 20


def test_next_cursor_ends_the_walk() -> None:
    assert himalayas.next_cursor(FEED) == "eyJvZmZzZXQiOjIwfQ=="
    assert himalayas.next_cursor(json.dumps({"jobs": [], "nextCursor": None})) is None


def test_the_api_key_is_optional_and_read_from_the_environment(monkeypatch) -> None:
    monkeypatch.delenv(himalayas.API_KEY_ENV, raising=False)
    assert himalayas.headers() is None
    monkeypatch.setenv(himalayas.API_KEY_ENV, "k-123")
    assert himalayas.headers() == {"Authorization": "Bearer k-123"}


@pytest.mark.parametrize("body", ["{}", '{"jobs": "nope"}', "not json"])
def test_a_payload_without_a_jobs_list_is_rejected(body: str) -> None:
    with pytest.raises(AdapterError):
        ADAPTERS["himalayas"].parse(body, SOURCE)
