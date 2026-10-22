"""Phase 3B: canonical URLs, cross-source dedupe, and idempotent re-runs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gawe.jobs.dedupe import find_duplicate
from gawe.jobs.normalize import canonical_url, city_of, fingerprint, location_key
from gawe.jobs.sources.base import RawJob, normalize
from tests.conftest import extract_profile, latest_profile, upload_cv
from tests.test_discovery import GREENHOUSE, _Fetcher, _create_source, _use

SOURCE = {
    "source_id": "src_acme",
    "company": "Acme",
    "careers_url": "https://boards.greenhouse.io/acme",
}
OTHER_SOURCE = {**SOURCE, "source_id": "src_beta", "careers_url": "https://jobs.lever.co/beta"}
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "jobs" / "raw"
ASHBY = (FIXTURES / "ashby_job_board.json").read_text(encoding="utf-8")


def _record(**overrides) -> dict:
    raw = RawJob(
        source_job_id=overrides.pop("source_job_id", "1"),
        title=overrides.pop("title", "Senior Backend Engineer"),
        canonical_url=overrides.pop(
            "canonical_url", "https://boards.greenhouse.io/acme/jobs/1"
        ),
        description_html="<p>Build services.</p>",
        location_raw=overrides.pop("location_raw", "Jakarta, Indonesia"),
    )
    return normalize(raw, SOURCE, "2026-10-20T00:00:00Z")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://a.example/jobs/1", "https://a.example/jobs/1"),
        ("https://a.example/jobs/1/", "https://a.example/jobs/1"),
        ("https://A.example/jobs/1", "https://a.example/jobs/1"),
        (
            "https://a.example/jobs/1?utm_source=x&utm_medium=y&gh_src=abc&ref=z",
            "https://a.example/jobs/1",
        ),
        ("https://a.example/jobs/1?dept=eng&utm_campaign=q", "https://a.example/jobs/1?dept=eng"),
        ("https://a.example/jobs/1#apply", "https://a.example/jobs/1"),
    ],
)
def test_canonical_url_drops_tracking_and_trailing_slash(url, expected) -> None:
    assert canonical_url(url) == expected


def test_normalize_stores_canonical_url() -> None:
    record = _record(canonical_url="https://boards.greenhouse.io/acme/jobs/1/?utm_source=li")
    assert record["canonical_url"] == "https://boards.greenhouse.io/acme/jobs/1"


def test_fingerprint_ignores_case_punctuation_and_trailing_city() -> None:
    left = _record(title="Senior Backend Engineer", location_raw="Jakarta, Indonesia")
    right = _record(title="senior  backend-engineer", location_raw="JAKARTA")
    assert left["fingerprint"] == right["fingerprint"]
    assert city_of("Jakarta, Indonesia") == "jakarta"


def test_fingerprint_differs_on_employment_type() -> None:
    left = _record()
    right = {**left, "employment_type": "contract"}
    assert fingerprint(left) != fingerprint(right)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Jakarta, Indonesia", "jakarta"),
        ("JAKARTA", "jakarta"),
        ("Remote, AMER", "amer"),
        ("Remote, EMEA", "emea"),
        ("Remote, APAC", "apac"),
        ("Remote, Global", "anywhere"),
        ("Remote", "anywhere"),
        ("North America", "north america"),
        ("San Francisco, CA", "san francisco"),
        ("Hybrid (UK)", "hybrid uk"),
    ],
)
def test_location_key_keeps_the_region_that_names_the_scope(raw, expected) -> None:
    assert location_key(raw) == expected


def test_fingerprint_separates_regional_postings_of_the_same_role() -> None:
    """AMER and EMEA are two postings, not one; city_of made both "remote"."""
    amer = _record(title="Support Engineer (AMER - Weekends)", location_raw="Remote, AMER")
    emea = _record(title="Support Engineer (EMEA - Weekends)", location_raw="Remote, EMEA")
    assert city_of("Remote, AMER") == city_of("Remote, EMEA")
    assert amer["fingerprint"] != emea["fingerprint"]


def _insert_job(connection, record: dict, job_id: str, source_id: str) -> None:
    connection.execute(
        "INSERT INTO job (job_id, source_id, source_job_id, canonical_url, company, title, "
        "location_json, work_mode, employment_type, seniority, market, fetched_at, status, "
        "duplicate_of, fingerprint, completeness_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', NULL, ?, '{}', ?, ?)",
        (
            job_id,
            source_id,
            record["source_job_id"],
            record["canonical_url"],
            record["company"],
            record["title"],
            json.dumps(record["location"]),
            record["work_mode"],
            record["employment_type"],
            record["seniority"],
            record["market"],
            "2026-10-20T00:00:00Z",
            record["fingerprint"],
            "2026-10-20T00:00:00Z",
            "2026-10-20T00:00:00Z",
        ),
    )


def _register(connection, source_id: str) -> None:
    connection.execute(
        "INSERT INTO source_registry (source_id, company, market, careers_url, access_method, "
        "ats, verification_status, enabled, created_at, updated_at) VALUES "
        "(?, 'Acme', 'global', 'https://boards.greenhouse.io/acme', 'ats_api', 'greenhouse', "
        "'verified', 1, '2026-10-20T00:00:00Z', '2026-10-20T00:00:00Z')",
        (source_id,),
    )


def test_canonical_url_match_links_duplicate_without_deleting(connection) -> None:
    _register(connection, SOURCE["source_id"])
    _register(connection, OTHER_SOURCE["source_id"])
    first = _record()
    _insert_job(connection, first, "job_a", SOURCE["source_id"])
    duplicate = _record(source_job_id="2")
    _insert_job(connection, duplicate, "job_b", OTHER_SOURCE["source_id"])

    assert find_duplicate(connection, "job_b", duplicate) == "job_a"
    total = connection.execute("SELECT COUNT(*) AS total FROM job").fetchone()["total"]
    assert total == 2


def test_cross_source_fingerprint_links_duplicate(connection) -> None:
    _register(connection, SOURCE["source_id"])
    _register(connection, OTHER_SOURCE["source_id"])
    first = _record()
    _insert_job(connection, first, "job_a", SOURCE["source_id"])
    same_role = _record(source_job_id="lev-1", canonical_url="https://jobs.lever.co/beta/1")
    _insert_job(connection, same_role, "job_b", OTHER_SOURCE["source_id"])

    assert find_duplicate(connection, "job_b", same_role) == "job_a"


def test_fuzzy_match_requires_same_company_and_city(connection) -> None:
    _register(connection, SOURCE["source_id"])
    first = _record()
    _insert_job(connection, first, "job_a", SOURCE["source_id"])

    near = _record(
        source_job_id="2",
        title="Senior Backend Engineer II",
        canonical_url="https://boards.greenhouse.io/acme/jobs/2",
    )
    _insert_job(connection, near, "job_b", SOURCE["source_id"])
    assert find_duplicate(connection, "job_b", near) == "job_a"

    # Same close title in a different city is a different role.
    far = _record(
        source_job_id="3",
        title="Senior Backend Engineer II",
        canonical_url="https://boards.greenhouse.io/acme/jobs/3",
        location_raw="Berlin, Germany",
    )
    _insert_job(connection, far, "job_c", SOURCE["source_id"])
    assert find_duplicate(connection, "job_c", far) is None


def test_regional_postings_of_one_role_are_not_merged(connection) -> None:
    """AMER and EMEA are separate postings; merging one into the other hides a job."""
    _register(connection, SOURCE["source_id"])
    amer = _record(
        title="Support Engineer (AMER - Weekends)",
        location_raw="Remote, AMER",
        canonical_url="https://boards.greenhouse.io/acme/jobs/amer",
    )
    _insert_job(connection, amer, "job_amer", SOURCE["source_id"])
    emea = _record(
        source_job_id="2",
        title="Support Engineer (EMEA - Weekends)",
        location_raw="Remote, EMEA",
        canonical_url="https://boards.greenhouse.io/acme/jobs/emea",
    )
    _insert_job(connection, emea, "job_emea", SOURCE["source_id"])

    assert find_duplicate(connection, "job_emea", emea) is None


def test_identical_title_in_a_different_region_is_a_different_job(connection) -> None:
    _register(connection, SOURCE["source_id"])
    europe = _record(
        title="Developer Relations",
        location_raw="Remote, Europe",
        canonical_url="https://boards.greenhouse.io/acme/jobs/eu",
    )
    _insert_job(connection, europe, "job_eu", SOURCE["source_id"])
    america = _record(
        source_job_id="2",
        title="Developer Relations",
        location_raw="Remote, North America",
        canonical_url="https://boards.greenhouse.io/acme/jobs/na",
    )
    _insert_job(connection, america, "job_na", SOURCE["source_id"])

    assert find_duplicate(connection, "job_na", america) is None


def test_duplicate_chain_resolves_to_the_canonical_job(connection) -> None:
    _register(connection, SOURCE["source_id"])
    first = _record()
    _insert_job(connection, first, "job_a", SOURCE["source_id"])
    second = _record(source_job_id="2")
    _insert_job(connection, second, "job_b", SOURCE["source_id"])
    third = _record(source_job_id="3")
    _insert_job(connection, third, "job_c", SOURCE["source_id"])
    connection.execute("UPDATE job SET duplicate_of = 'job_a' WHERE job_id = 'job_b'")

    assert find_duplicate(connection, "job_c", third) == "job_a"


def _confirm(client, csrf) -> None:
    upload_cv(client, csrf)
    extract_profile(client, csrf)
    profile = latest_profile(client)
    response = client.post(
        f"/api/setup/profiles/{profile['profile_version_id']}/confirm", headers=csrf, json={}
    )
    assert response.status_code == 200, response.json()


def _run(client, csrf, source_id: str) -> dict:
    response = client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source_id]}
    )
    assert response.status_code == 202, response.json()
    return client.get(f"/api/discovery/runs/{response.json()['run_id']}").json()


def test_run_rerun_is_idempotent_and_keeps_duplicate_links(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    greenhouse = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    lever = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="beta", ats="lever"
    )
    # Same role published on both boards under different ids and URLs.
    lever_payload = [
        {
            "id": "lev-1001",
            "text": "Senior Backend Engineer",
            "categories": {"location": "Remote - Worldwide"},
            "description": "<div>Build services.</div>",
            "hostedUrl": "https://jobs.lever.co/beta/lev-1001",
        }
    ]
    fetcher = _Fetcher(
        {"boards-api": GREENHOUSE, "api.lever": json.dumps(lever_payload)}
    )
    _use(setup_client, fetcher, monkeypatch)

    first = _run(setup_client, csrf, greenhouse["source_id"])
    assert first["status"] == "completed"
    _run(setup_client, csrf, lever["source_id"])

    jobs = connection.execute(
        "SELECT job_id, source_id, duplicate_of, fingerprint FROM job ORDER BY created_at, job_id"
    ).fetchall()
    assert len(jobs) == 3
    linked = [row for row in jobs if row["duplicate_of"]]
    assert len(linked) == 1
    canonical = next(row for row in jobs if row["job_id"] == linked[0]["duplicate_of"])
    assert canonical["source_id"] == greenhouse["source_id"]
    assert linked[0]["fingerprint"] == canonical["fingerprint"]

    before = {(row["job_id"], row["duplicate_of"]) for row in jobs}
    _run(setup_client, csrf, greenhouse["source_id"])
    _run(setup_client, csrf, lever["source_id"])
    after = {
        (row["job_id"], row["duplicate_of"])
        for row in connection.execute(
            "SELECT job_id, duplicate_of FROM job"
        ).fetchall()
    }
    assert after == before
    total = connection.execute("SELECT COUNT(*) AS total FROM job").fetchone()["total"]
    assert total == 3


def test_rerun_refreshes_a_stale_fingerprint(
    setup_client, csrf, monkeypatch, connection
) -> None:
    """A normalisation change must reach stored rows, not only new ones."""
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    _use(setup_client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)
    _run(setup_client, csrf, source["source_id"])

    connection.execute("UPDATE job SET fingerprint = ?", ("0" * 64,))
    _run(setup_client, csrf, source["source_id"])

    stored = connection.execute("SELECT fingerprint FROM job").fetchall()
    assert stored
    assert all(row["fingerprint"] != "0" * 64 for row in stored)


def test_closed_jobs_stay_stored_and_are_not_duplicate_targets(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme"
    )
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)
    _run(setup_client, csrf, source["source_id"])

    payload = json.loads(GREENHOUSE)
    payload["jobs"] = payload["jobs"][:1]
    fetcher.responses = {"boards-api": json.dumps(payload)}
    _run(setup_client, csrf, source["source_id"])

    rows = connection.execute(
        "SELECT source_job_id, status FROM job ORDER BY source_job_id"
    ).fetchall()
    assert {row["source_job_id"]: row["status"] for row in rows} == {
        "1001": "open",
        "1002": "closed",
    }


def test_ashby_board_still_normalizes_after_dedupe_fields(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(
        setup_client, csrf, monkeypatch, company="Acme", board="acme", ats="ashby"
    )
    _use(setup_client, _Fetcher({"api.ashbyhq": ASHBY}), monkeypatch)
    run = _run(setup_client, csrf, source["source_id"])
    assert run["status"] == "completed"
    row = connection.execute("SELECT fingerprint, duplicate_of FROM job").fetchone()
    assert len(row["fingerprint"]) == 64
    assert row["duplicate_of"] is None
