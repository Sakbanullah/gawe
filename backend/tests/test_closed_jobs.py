"""D4: a closed job leaves Matches but never breaks an existing workspace."""

from __future__ import annotations

import json

from gawe.profile.store import ProfileStore
from gawe.services.assessment_service import AssessmentService
from tests.test_assessment import _confirm, _run
from tests.document_plan_helper import plan_and_approve
from tests.test_discovery import GREENHOUSE, _Fetcher, _create_source, _use


def _source_id(client) -> str:
    """The single source registered by the caller, read back from the API."""
    items = client.get("/api/settings/sources").json()["items"]
    assert len(items) == 1, items
    return items[0]["source_id"]


def _job_id(connection, source_job_id: str) -> str:
    row = connection.execute(
        "SELECT job_id FROM job WHERE source_job_id = ?", (source_job_id,)
    ).fetchone()
    assert row is not None, source_job_id
    return row["job_id"]


def _drop_job(fetcher, source_job_id: str) -> None:
    """Make the next snapshot cover the board minus one job."""
    payload = json.loads(GREENHOUSE)
    kept = [job for job in payload["jobs"] if str(job["id"]) != source_job_id]
    fetcher.responses = {"boards-api": json.dumps({"jobs": kept, "meta": {"total": len(kept)}})}


def _two_runs_then_close(client, csrf, monkeypatch) -> tuple[str, _Fetcher]:
    """Store both jobs, then close the second one by leaving it out of the board."""
    _confirm(client, csrf)
    _create_source(client, csrf, monkeypatch, company="Acme", board="acme")
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(client, fetcher, monkeypatch)
    source_id = _source_id(client)
    _run(client, csrf, source_id)
    _drop_job(fetcher, "1002")
    _run(client, csrf, source_id)
    return source_id, fetcher


def test_closed_job_is_hidden_from_matches_and_counts(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _two_runs_then_close(setup_client, csrf, monkeypatch)
    closed = _job_id(connection, "1002")
    assert connection.execute(
        "SELECT status FROM job WHERE job_id = ?", (closed,)
    ).fetchone()["status"] == "closed"

    listed = setup_client.get("/api/matches").json()
    assert closed not in {item["job"]["job_id"] for item in listed["items"]}
    assert len(listed["items"]) == 1

    # Counts describe the list, not the whole assessment table.
    assessed = connection.execute(
        "SELECT COUNT(*) AS n FROM eligibility_assessment e JOIN job j "
        "ON j.job_id = e.job_id WHERE j.status = 'open' AND j.duplicate_of IS NULL"
    ).fetchone()["n"]
    assert sum(
        listed["counts"][key] for key in ("eligible", "needs_review", "ineligible")
    ) == assessed


def test_closed_job_detail_is_409_not_404(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _two_runs_then_close(setup_client, csrf, monkeypatch)
    closed = _job_id(connection, "1002")

    response = setup_client.get(f"/api/matches/{closed}")
    assert response.status_code == 409, response.json()
    assert response.json()["error"]["code"] == "job_not_open"

    unknown = setup_client.get("/api/matches/job_missing")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "not_found"


def test_open_job_detail_still_works(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _two_runs_then_close(setup_client, csrf, monkeypatch)
    opened = _job_id(connection, "1001")
    assert setup_client.get(f"/api/matches/{opened}").status_code == 200


def test_existing_workspace_stays_reachable_after_the_job_closes(
    setup_client, csrf, monkeypatch, connection
) -> None:
    """The gate that matters: closing a job must not lock the user out."""
    _confirm(setup_client, csrf)
    _create_source(setup_client, csrf, monkeypatch, company="Acme", board="acme")
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)
    source_id = _source_id(setup_client)
    _run(setup_client, csrf, source_id)

    job_id = _job_id(connection, "1002")
    created = setup_client.post(
        "/api/applications", headers=csrf, json={"job_id": job_id}
    )
    assert created.status_code == 201, created.json()
    application_id = created.json()["application_id"]

    _drop_job(fetcher, "1002")
    _run(setup_client, csrf, source_id)
    assert connection.execute(
        "SELECT status FROM job WHERE job_id = ?", (job_id,)
    ).fetchone()["status"] == "closed"

    workspace = setup_client.get(f"/api/applications/{application_id}")
    assert workspace.status_code == 200, workspace.json()
    assert workspace.json()["job"]["job_id"] == job_id

    job_detail = setup_client.get(f"/api/applications/{application_id}/job")
    assert job_detail.status_code == 200, job_detail.json()

    listed = setup_client.get("/api/applications").json()["items"]
    assert application_id in {item["application_id"] for item in listed}


def test_documents_still_generate_and_review_after_the_job_closes(
    setup_client, csrf, monkeypatch, connection
) -> None:
    """Drafting and review need the job context, and the workspace keeps it."""
    _confirm(setup_client, csrf)
    _create_source(setup_client, csrf, monkeypatch, company="Acme", board="acme")
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)
    source_id = _source_id(setup_client)
    _run(setup_client, csrf, source_id)

    items = setup_client.get("/api/matches").json()["items"]
    eligible = next(item for item in items if item["eligibility"]["status"] == "eligible")
    job_id = eligible["job"]["job_id"]
    source_job_id = connection.execute(
        "SELECT source_job_id FROM job WHERE job_id = ?", (job_id,)
    ).fetchone()["source_job_id"]

    created = setup_client.post(
        "/api/applications", headers=csrf, json={"job_id": job_id}
    )
    assert created.status_code == 201, created.json()
    application_id = created.json()["application_id"]

    _drop_job(fetcher, source_job_id)
    _run(setup_client, csrf, source_id)
    assert connection.execute(
        "SELECT status FROM job WHERE job_id = ?", (job_id,)
    ).fetchone()["status"] == "closed"

    plan_and_approve(setup_client, csrf, application_id, "en")
    generated = setup_client.post(
        f"/api/applications/{application_id}/documents",
        headers=csrf,
        json={"kinds": ["cv"], "language": "en"},
    )
    assert generated.status_code == 202, generated.json()
    versions = setup_client.get(f"/api/applications/{application_id}/documents").json()
    document_version_id = versions["items"][0]["document_version_id"]

    reviewed = setup_client.post(
        f"/api/applications/{application_id}/documents/{document_version_id}/review",
        headers=csrf,
    )
    assert reviewed.status_code == 202, reviewed.json()


def test_duplicate_application_on_a_closed_job_is_still_deduplicated(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    _create_source(setup_client, csrf, monkeypatch, company="Acme", board="acme")
    fetcher = _Fetcher({"boards-api": GREENHOUSE})
    _use(setup_client, fetcher, monkeypatch)
    source_id = _source_id(setup_client)
    _run(setup_client, csrf, source_id)

    job_id = _job_id(connection, "1002")
    first = setup_client.post("/api/applications", headers=csrf, json={"job_id": job_id})
    assert first.status_code == 201, first.json()

    _drop_job(fetcher, "1002")
    _run(setup_client, csrf, source_id)

    again = setup_client.post("/api/applications", headers=csrf, json={"job_id": job_id})
    assert again.status_code == 200, again.json()
    assert again.json()["deduplicated"] is True
    assert again.json()["application_id"] == first.json()["application_id"]


def test_new_application_on_a_closed_job_is_rejected(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _two_runs_then_close(setup_client, csrf, monkeypatch)
    closed = _job_id(connection, "1002")

    response = setup_client.post(
        "/api/applications", headers=csrf, json={"job_id": closed}
    )
    assert response.status_code == 409, response.json()
    assert response.json()["error"]["code"] == "job_not_open"
    assert connection.execute(
        "SELECT COUNT(*) AS n FROM application WHERE job_id = ?", (closed,)
    ).fetchone()["n"] == 0


def test_tier_override_on_a_closed_job_is_rejected(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _two_runs_then_close(setup_client, csrf, monkeypatch)
    closed = _job_id(connection, "1002")

    response = setup_client.patch(
        f"/api/matches/{closed}/tier",
        headers=csrf,
        json={"tier": "P1", "reason": "Relokasi"},
    )
    assert response.status_code == 409, response.json()
    assert response.json()["error"]["code"] == "job_not_open"
    assert connection.execute(
        "SELECT priority_tier_override FROM job WHERE job_id = ?", (closed,)
    ).fetchone()["priority_tier_override"] is None


def test_fit_count_skips_closed_jobs(
    setup_client, csrf, monkeypatch, connection
) -> None:
    """B8: `fit_computed` follows the same open-job scope as the tier counts."""
    _two_runs_then_close(setup_client, csrf, monkeypatch)
    closed = connection.execute(
        "SELECT job_id, latest_version_id FROM job WHERE status = 'closed'"
    ).fetchone()
    profile_version_id = connection.execute(
        "SELECT profile_version_id FROM eligibility_assessment LIMIT 1"
    ).fetchone()["profile_version_id"]
    service = AssessmentService(connection, ProfileStore(connection))
    before = service.counts(profile_version_id)["fit_computed"]
    # The open job keeps its fit row, so the count must start above zero for the
    # closed row below to prove anything.
    assert before >= 1

    connection.execute(
        "INSERT INTO fit_assessment (assessment_id, job_id, job_posting_version_id, "
        "profile_version_id, fit_score, verdict, confidence, components_json, "
        "gaps_json, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "fit_closed",
            closed["job_id"],
            closed["latest_version_id"],
            profile_version_id,
            90,
            "strong",
            "high",
            "{}",
            "[]",
            "2026-10-22T00:00:00Z",
        ),
    )

    assert service.counts(profile_version_id)["fit_computed"] == before


def test_overview_counts_skip_closed_jobs(
    setup_client, csrf, monkeypatch
) -> None:
    _two_runs_then_close(setup_client, csrf, monkeypatch)
    matches = setup_client.get("/api/matches").json()
    overview = setup_client.get("/api/overview").json()
    for key in ("eligible", "needs_review", "ineligible"):
        assert overview["counts"][key] == matches["counts"][key]
