"""Phase 3D: application workspace, filenames, and explicit re-analysis."""

from __future__ import annotations

import pytest

from gawe.export.naming import MAX_FILENAME_LENGTH, suggested_filename, with_collision_suffix
from gawe.services.tasks import TaskStore
from tests.test_discovery import GREENHOUSE, _Fetcher, _create_source, _use
from tests.test_assessment import _confirm, _run


def _matched_jobs(client, csrf, monkeypatch) -> list[dict]:
    source = _create_source(client, csrf, monkeypatch, company="Acme", board="acme")
    _use(client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)
    _run(client, csrf, source["source_id"])
    return client.get("/api/matches").json()["items"]


# -- naming ------------------------------------------------------------------
def test_filename_follows_contract_format_and_sanitises() -> None:
    name = suggested_filename("cv", "Sakbanullah", "Tokopedia", "Backend Developer")
    assert name == "CV_Sakbanullah_Tokopedia_Backend_Developer.pdf"
    cover = suggested_filename("cover_letter", "Sakbanullah", "Tokopedia", "Backend Developer")
    assert cover == "Cover_Letter_Sakbanullah_Tokopedia_Backend_Developer.pdf"


def test_filename_falls_back_and_strips_illegal_characters() -> None:
    name = suggested_filename("cv", None, 'Acme/Corp: "ID"', "  ")
    assert name == "CV_Candidate_Acme_Corp_ID_Position.pdf"
    assert len(name) <= MAX_FILENAME_LENGTH


def test_filename_collision_suffix_is_stable_and_bounded() -> None:
    base = suggested_filename("cv", "A", "B", "C")
    first = with_collision_suffix(base, "job_0123456789abcdef")
    assert first == with_collision_suffix(base, "job_0123456789abcdef")
    assert first != with_collision_suffix(base, "job_fedcba9876543210")
    assert first.endswith(".pdf")
    long_name = suggested_filename("cv", "x" * 200, "y" * 200, "z" * 200)
    assert len(long_name) <= MAX_FILENAME_LENGTH


# -- workspace ---------------------------------------------------------------
def test_application_requires_confirmed_profile(setup_client, csrf) -> None:
    response = setup_client.post(
        "/api/applications", headers=csrf, json={"job_id": "job_1"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "profile_not_confirmed"


def test_create_application_from_job_is_idempotent(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    job = _matched_jobs(setup_client, csrf, monkeypatch)[0]["job"]

    created = setup_client.post(
        "/api/applications", headers=csrf, json={"job_id": job["job_id"]}
    )
    assert created.status_code == 201, created.json()
    body = created.json()
    assert body["deduplicated"] is False
    assert body["job_id"] == job["job_id"]

    again = setup_client.post(
        "/api/applications", headers=csrf, json={"job_id": job["job_id"]}
    )
    assert again.status_code == 200
    assert again.json()["deduplicated"] is True
    assert again.json()["application_id"] == body["application_id"]

    listed = setup_client.get("/api/applications").json()
    assert [item["application_id"] for item in listed["items"]] == [body["application_id"]]


def test_workspace_shows_job_eligibility_and_suggested_filenames(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    items = _matched_jobs(setup_client, csrf, monkeypatch)
    eligible = next(item for item in items if item["eligibility"]["status"] == "eligible")

    created = setup_client.post(
        "/api/applications", headers=csrf, json={"job_id": eligible["job"]["job_id"]}
    ).json()
    workspace = setup_client.get(f"/api/applications/{created['application_id']}").json()

    assert workspace["job"]["job_id"] == eligible["job"]["job_id"]
    assert workspace["job_posting_version_id"] == eligible["job"]["job_posting_version_id"]
    assert workspace["eligibility"]["status"] == "eligible"
    assert workspace["fit"]["fit_score"] == eligible["fit"]["fit_score"]
    assert workspace["documents"] == {"cv": [], "cover_letter": []}
    assert workspace["suggested_filenames"]["cv"].startswith("CV_")
    assert workspace["suggested_filenames"]["cover_letter"].startswith("Cover_Letter_")
    assert workspace["suggested_filenames"]["cv"].endswith(".pdf")
    assert workspace["status"] == "not_started"
    assert workspace["next_action"]["code"] == "review_documents"

    # Match rows now point at their workspace; the backend owns that link.
    matches = setup_client.get("/api/matches").json()["items"]
    linked = [item for item in matches if item["application_id"]]
    assert [item["application_id"] for item in linked] == [created["application_id"]]


def test_workspace_keeps_needs_review_blocked(setup_client, csrf, monkeypatch) -> None:
    _confirm(setup_client, csrf)
    items = _matched_jobs(setup_client, csrf, monkeypatch)
    blocked = [item for item in items if item["eligibility"]["status"] != "eligible"]
    if not blocked:
        pytest.skip("fixture produced only eligible jobs")
    job = blocked[0]["job"]
    created = setup_client.post(
        "/api/applications", headers=csrf, json={"job_id": job["job_id"]}
    ).json()
    workspace = setup_client.get(f"/api/applications/{created['application_id']}").json()

    assert workspace["fit"] is None
    assert workspace["documents"] == {"cv": [], "cover_letter": []}
    assert workspace["next_action"]["code"] in {"review_matches", "none"}

    fit = setup_client.get(f"/api/applications/{created['application_id']}/fit")
    assert fit.status_code == 409
    assert fit.json()["error"]["code"] == "fit_not_available"


def test_application_job_and_eligibility_endpoints(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    job = _matched_jobs(setup_client, csrf, monkeypatch)[0]["job"]
    created = setup_client.post(
        "/api/applications", headers=csrf, json={"job_id": job["job_id"]}
    ).json()

    detail = setup_client.get(f"/api/applications/{created['application_id']}/job")
    assert detail.status_code == 200
    assert detail.json()["job"]["job_id"] == job["job_id"]

    eligibility = setup_client.get(
        f"/api/applications/{created['application_id']}/eligibility"
    )
    assert eligibility.status_code == 200
    assert eligibility.json()["job_id"] == job["job_id"]

    missing = setup_client.get("/api/applications/app_missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


MANUAL_PAGE = """
<html><head>
<title>Senior Backend Engineer - Acme</title>
<meta property="og:site_name" content="Acme">
</head><body>
<h1>Senior Backend Engineer</h1>
<p>We need a backend engineer with Python and PostgreSQL experience.
You will build payment services and own reliability for the billing API.</p>
</body></html>
"""


def _manual_fetcher(monkeypatch, client, page: str = MANUAL_PAGE):
    fetcher = _Fetcher(
        {"robots.txt": "User-agent: *\nAllow: /\n", "example.com": page}
    )
    monkeypatch.setattr(client.app.state, "manual_url_fetcher", fetcher, raising=False)
    return fetcher


def test_manual_url_fallback_creates_workspace(setup_client, csrf, monkeypatch) -> None:
    _confirm(setup_client, csrf)
    fetcher = _manual_fetcher(monkeypatch, setup_client)

    response = setup_client.post(
        "/api/applications", headers=csrf, json={"url": "https://example.com/jobs/1"}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["job_id"].startswith("job_")

    workspace = setup_client.get(f"/api/applications/{body['application_id']}").json()
    assert workspace["job"]["title"] == "Senior Backend Engineer"
    assert workspace["job"]["company"] == "Acme"
    assert workspace["job"]["source_id"] == "manual_url"
    assert any("example.com/jobs/1" in call for call in fetcher.calls)
    assert any("robots.txt" in call for call in fetcher.calls)

    # The synthetic source never shows up as a registry entry.
    sources = setup_client.get("/api/settings/sources").json()["items"]
    assert all(item["source_id"] != "manual_url" for item in sources)


def test_manual_url_rejects_non_https(setup_client, csrf, monkeypatch) -> None:
    _confirm(setup_client, csrf)
    _manual_fetcher(monkeypatch, setup_client)
    response = setup_client.post(
        "/api/applications", headers=csrf, json={"url": "http://example.com/jobs/1"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "url_rejected"


def test_manual_url_respects_robots(setup_client, csrf, monkeypatch) -> None:
    _confirm(setup_client, csrf)
    _manual_fetcher(
        monkeypatch,
        setup_client,
        page="",  # unused: robots denies first
    )
    fetcher = _Fetcher({"robots.txt": "User-agent: *\nDisallow: /jobs\n"})
    monkeypatch.setattr(setup_client.app.state, "manual_url_fetcher", fetcher, raising=False)
    response = setup_client.post(
        "/api/applications", headers=csrf, json={"url": "https://example.com/jobs/1"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "robots_disallowed"


def test_rerun_analysis_is_explicit_and_leaves_scores_stable(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    job = _matched_jobs(setup_client, csrf, monkeypatch)[0]["job"]
    created = setup_client.post(
        "/api/applications", headers=csrf, json={"job_id": job["job_id"]}
    ).json()
    before = connection.execute(
        "SELECT job_id, fit_score FROM fit_assessment ORDER BY job_id"
    ).fetchall()

    response = setup_client.post(
        f"/api/applications/{created['application_id']}/analysis",
        headers=csrf,
        json={"reason": "user_requested"},
    )
    assert response.status_code == 202, response.json()
    assert response.json()["type"] == "analysis"
    assert response.json()["status"] == "completed"

    task = setup_client.get(f"/api/tasks/{response.json()['task_id']}").json()
    assert task["application_id"] == created["application_id"]
    assert task["status"] == "completed"

    after = connection.execute(
        "SELECT job_id, fit_score FROM fit_assessment ORDER BY job_id"
    ).fetchall()
    assert before == after


def test_second_analysis_is_rejected_with_the_active_task_id(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    job = _matched_jobs(setup_client, csrf, monkeypatch)[0]["job"]
    created = setup_client.post(
        "/api/applications", headers=csrf, json={"job_id": job["job_id"]}
    ).json()
    # One active task per application_id, regardless of type (API-CONTRACTS §4.3).
    TaskStore(connection).create(
        "review", ["review"], created["application_id"]
    )
    active = connection.execute(
        "SELECT task_id FROM task WHERE application_id = ? AND status = 'queued'",
        (created["application_id"],),
    ).fetchone()
    assert active is not None

    response = setup_client.post(
        f"/api/applications/{created['application_id']}/analysis",
        headers=csrf,
        json={"reason": "user_requested"},
    )
    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "task_already_running"
    assert body["active_task_id"] == active["task_id"]


def test_list_applications_filters_by_status_and_rejects_bad_cursor(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    job = _matched_jobs(setup_client, csrf, monkeypatch)[0]["job"]
    setup_client.post("/api/applications", headers=csrf, json={"job_id": job["job_id"]})

    matched = setup_client.get("/api/applications?status=not_started").json()["items"]
    assert len(matched) == 1

    empty = setup_client.get("/api/applications?status=exported").json()["items"]
    assert empty == []

    invalid_status = setup_client.get("/api/applications?status=bogus")
    assert invalid_status.status_code == 400

    invalid_cursor = setup_client.get("/api/applications?cursor=not-a-cursor")
    assert invalid_cursor.status_code == 400
    assert invalid_cursor.json()["error"]["code"] == "validation_failed"


def test_rerun_analysis_requires_csrf(setup_client, csrf, monkeypatch) -> None:
    _confirm(setup_client, csrf)
    job = _matched_jobs(setup_client, csrf, monkeypatch)[0]["job"]
    created = setup_client.post(
        "/api/applications", headers=csrf, json={"job_id": job["job_id"]}
    ).json()
    response = setup_client.post(
        f"/api/applications/{created['application_id']}/analysis",
        json={"reason": "user_requested"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_invalid"


def test_cancel_archives_workspace_without_deleting_it(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    job = _matched_jobs(setup_client, csrf, monkeypatch)[0]["job"]
    created = setup_client.post(
        "/api/applications", headers=csrf, json={"job_id": job["job_id"]}
    ).json()
    application_id = created["application_id"]

    cancelled = setup_client.post(
        f"/api/applications/{application_id}/cancel",
        headers=csrf,
        json={"reason": "lowongan ditutup"},
    )
    assert cancelled.status_code == 200, cancelled.json()
    assert cancelled.json()["cancelled_at"]

    # Hidden from the active list, still reachable in the archive.
    active = setup_client.get("/api/applications").json()
    assert active["items"] == []
    archive = setup_client.get(
        "/api/applications", params={"include_cancelled": "true"}
    ).json()
    assert [item["status"] for item in archive["items"]] == ["cancelled"]
    assert archive["items"][0]["cancel_reason"] == "lowongan ditutup"

    # The record and its workspace still exist.
    assert setup_client.get(f"/api/applications/{application_id}").status_code == 200
    by_status = setup_client.get(
        "/api/applications", params={"status": "cancelled"}
    ).json()
    assert len(by_status["items"]) == 1

    # Cancelling twice is idempotent.
    again = setup_client.post(
        f"/api/applications/{application_id}/cancel", headers=csrf, json={}
    )
    assert again.status_code == 200
    assert again.json()["cancelled_at"] == cancelled.json()["cancelled_at"]


def test_cancel_requires_csrf(setup_client, csrf, monkeypatch) -> None:
    _confirm(setup_client, csrf)
    job = _matched_jobs(setup_client, csrf, monkeypatch)[0]["job"]
    created = setup_client.post(
        "/api/applications", headers=csrf, json={"job_id": job["job_id"]}
    ).json()
    response = setup_client.post(f"/api/applications/{created['application_id']}/cancel")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_invalid"


def test_cancel_rejects_running_task(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    job = _matched_jobs(setup_client, csrf, monkeypatch)[0]["job"]
    created = setup_client.post(
        "/api/applications", headers=csrf, json={"job_id": job["job_id"]}
    ).json()
    application_id = created["application_id"]
    TaskStore(connection).create("document_generation", ["draft"], application_id)

    response = setup_client.post(
        f"/api/applications/{application_id}/cancel", headers=csrf, json={}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "task_already_running"
