"""Adapter contract tests against stored fixture responses. No network."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from gawe.jobs import ADAPTERS
from gawe.jobs.sources.base import InvalidJob, RawJob, normalize

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "jobs" / "raw"
JOB_SCHEMA = json.loads(
    (ROOT / "docs" / "phase-00" / "contracts" / "job.schema.json").read_text(encoding="utf-8")
)

SOURCES = {
    "greenhouse": {
        "source_id": "src_greenhouse",
        "company": "Acme",
        "careers_url": "https://boards.greenhouse.io/acme",
    },
    "lever": {
        "source_id": "src_lever",
        "company": "Acme",
        "careers_url": "https://jobs.lever.co/acme",
    },
    "ashby": {
        "source_id": "src_ashby",
        "company": "Acme",
        "careers_url": "https://jobs.ashbyhq.com/acme",
    },
}


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _schema_record(record: dict, source: dict) -> dict:
    return {
        "job_id": "job_test",
        "job_posting_version_id": "jpv_test",
        "content_hash": record["content_hash"],
        "source": {
            "source_id": source["source_id"],
            "source_kind": "registry",
            "company": source["company"],
            "verification_status": "verified",
            "access_method": "ats_api",
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


@pytest.mark.parametrize(
    ("ats", "fixture", "count"),
    [
        ("greenhouse", "greenhouse_board.json", 2),
        ("lever", "lever_postings.json", 2),
        ("ashby", "ashby_job_board.json", 1),
    ],
)
def test_adapter_parses_fixture_and_matches_job_schema(ats, fixture, count) -> None:
    adapter = ADAPTERS[ats]
    source = SOURCES[ats]
    jobs = adapter.parse(_fixture(fixture), source)
    assert len(jobs) == count
    for raw in jobs:
        record = normalize(raw, source, "2026-10-20T00:00:00Z")
        assert record["source_id"] == source["source_id"]
        assert record["canonical_url"].startswith("https://")
        jsonschema.validate(_schema_record(record, source), JOB_SCHEMA)


def test_adapter_builds_documented_endpoints() -> None:
    assert ADAPTERS["greenhouse"].build_url(SOURCES["greenhouse"]) == (
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
    )
    assert ADAPTERS["lever"].build_url(SOURCES["lever"]) == (
        "https://api.lever.co/v0/postings/acme?mode=json"
    )
    assert ADAPTERS["ashby"].build_url(SOURCES["ashby"]) == (
        "https://api.ashbyhq.com/posting-api/job-board/acme?includeCompensation=true"
    )


def test_greenhouse_content_is_unescaped_twice() -> None:
    jobs = ADAPTERS["greenhouse"].parse(_fixture("greenhouse_board.json"), SOURCES["greenhouse"])
    record = normalize(jobs[0], SOURCES["greenhouse"], "2026-10-20T00:00:00Z")
    assert "Build & ship payment services" in record["description_text"]
    assert "<p>" not in record["description_text"]


def test_ashby_skips_unlisted_records() -> None:
    jobs = ADAPTERS["ashby"].parse(_fixture("ashby_job_board.json"), SOURCES["ashby"])
    assert [job.source_job_id for job in jobs] == ["ash-3001"]
    assert jobs.skipped == 1


@pytest.mark.parametrize(
    ("ats", "body", "expected"),
    [
        ("greenhouse", '{"jobs": ["not a record", {"title": "no id"}]}', 2),
        ("lever", '[null, {"text": "no id"}]', 2),
        ("ashby", '{"jobs": [{"id": "a", "isListed": false}, 7]}', 2),
    ],
)
def test_adapters_report_how_many_records_they_dropped(ats, body, expected) -> None:
    jobs = ADAPTERS[ats].parse(body, SOURCES[ats])
    assert len(jobs) == 0
    assert jobs.skipped == expected


def test_hybrid_is_marked_and_remote_detected() -> None:
    ashby = ADAPTERS["ashby"].parse(_fixture("ashby_job_board.json"), SOURCES["ashby"])[0]
    record = normalize(ashby, SOURCES["ashby"], "2026-10-20T00:00:00Z")
    assert record["work_mode"] == "hybrid"
    lever = ADAPTERS["lever"].parse(_fixture("lever_postings.json"), SOURCES["lever"])[0]
    record = normalize(lever, SOURCES["lever"], "2026-10-20T00:00:00Z")
    assert record["work_mode"] == "remote"
    assert record["employment_type"] == "full_time"


def test_empty_board_is_not_an_error() -> None:
    jobs = ADAPTERS["greenhouse"].parse('{"jobs": []}', SOURCES["greenhouse"])
    assert jobs == []


def test_normalize_rejects_empty_source_job_id() -> None:
    raw = RawJob(
        source_job_id="   ",
        title="Engineer",
        canonical_url="https://boards.greenhouse.io/acme/jobs/1",
        description_html="<p>Work.</p>",
    )
    with pytest.raises(InvalidJob):
        normalize(raw, SOURCES["greenhouse"], "2026-10-20T00:00:00Z")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("not a date", None),
        ("2026-10-20", "2026-10-20T00:00:00Z"),
        ("2026-10-20T07:30:00Z", "2026-10-20T07:30:00Z"),
        ("2026-10-20T07:30:00+07:00", "2026-10-20T00:30:00Z"),
        (1760941800000, "2025-10-20T06:30:00Z"),
    ],
)
def test_parse_timestamp_normalises_known_shapes_and_drops_unknown(
    value, expected
) -> None:
    from gawe.jobs.sources.base import parse_timestamp

    assert parse_timestamp(value) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Senior Backend Engineer", "senior"),
        ("Sr. Data Engineer", "senior"),
        ("Principal Engineer", "principal"),
        ("Staff Engineer", "unknown"),
        ("Engineering Lead", "lead"),
        ("Junior Developer", "junior"),
        ("Software Engineering Intern", "intern"),
        ("Backend Engineer", "unknown"),
    ],
)
def test_seniority_is_derived_only_from_clear_title_signals(title, expected) -> None:
    from gawe.jobs.sources.base import seniority_from_title

    assert seniority_from_title(title) == expected


def test_market_requires_an_explicit_country_name() -> None:
    from gawe.jobs.sources.base import market_from_location

    assert market_from_location("Jakarta, Indonesia") == "indonesia"
    assert market_from_location("Jakarta") == "unknown"
    assert market_from_location(None) == "unknown"


def test_normalize_applies_seniority_and_market_from_payload() -> None:
    raw = RawJob(
        source_job_id="1",
        title="Senior Engineer",
        canonical_url="https://boards.greenhouse.io/acme/jobs/1",
        description_html="<p>Work.</p>",
        location_raw="Jakarta, Indonesia",
        posted_at="not a date",
    )
    record = normalize(raw, SOURCES["greenhouse"], "2026-10-20T00:00:00Z")
    assert record["seniority"] == "senior"
    assert record["market"] == "indonesia"
    assert record["posted_at"] is None
