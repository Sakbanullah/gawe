"""Phase 7 extension bridge: token pairing and browser job import."""

from __future__ import annotations

from tests.test_assessment import _confirm

PAGE = "https://id.jobstreet.com/backend-engineer-jobs?page=2"


def _ready(client, csrf) -> str:
    """Confirmed profile, so an import can be assessed."""
    _confirm(client, csrf)
    return "ok"


def _token(client, csrf) -> dict[str, str]:
    response = client.get("/api/settings/browser-import-token", headers=csrf)
    assert response.status_code == 200, response.json()
    return {"X-Gawe-Token": response.json()["token"]}


def _card(url: str = "https://id.jobstreet.com/job/123456", title: str = "Backend Engineer"):
    return {
        "title": title,
        "url": url,
        "company": "PT Contoh",
        "location": "Jakarta",
        "salary": None,
        "snippet": "Membangun layanan backend Python dan SQL untuk tim data.",
    }


def test_import_requires_a_valid_token(setup_client, csrf) -> None:
    body = {"source": "jobstreet", "page_url": PAGE, "jobs": [_card()]}
    missing = setup_client.post("/api/import/browser", json=body)
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "import_token_invalid"

    wrong = setup_client.post(
        "/api/import/browser", json=body, headers={"X-Gawe-Token": "not-the-token"}
    )
    assert wrong.status_code == 401


def test_import_rejects_a_page_outside_the_source_host(setup_client, csrf) -> None:
    _ready(setup_client, csrf)
    token = _token(setup_client, csrf)
    response = setup_client.post(
        "/api/import/browser",
        json={"source": "jobstreet", "page_url": "https://evil.example/jobs", "jobs": [_card()]},
        headers=token,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "url_host_not_allowed"


def test_import_rejects_a_job_url_outside_the_source_host(setup_client, csrf) -> None:
    _ready(setup_client, csrf)
    token = _token(setup_client, csrf)
    response = setup_client.post(
        "/api/import/browser",
        json={
            "source": "jobstreet",
            "page_url": PAGE,
            "jobs": [_card(url="https://evil.example/job/1")],
        },
        headers=token,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["rejected"] == 1
    assert payload["accepted"] == 0
    assert payload["rejected_details"][0]["reason"] == "url_host_not_allowed"


def test_import_rejects_more_than_the_per_request_limit(setup_client, csrf) -> None:
    _ready(setup_client, csrf)
    token = _token(setup_client, csrf)
    response = setup_client.post(
        "/api/import/browser",
        json={
            "source": "jobstreet",
            "page_url": PAGE,
            "jobs": [_card(url=f"https://id.jobstreet.com/job/{index}") for index in range(51)],
        },
        headers=token,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_failed"


def test_import_counts_duplicates_without_creating_twice(setup_client, csrf) -> None:
    _ready(setup_client, csrf)
    token = _token(setup_client, csrf)
    body = {"source": "jobstreet", "page_url": PAGE, "jobs": [_card()]}

    first = setup_client.post("/api/import/browser", json=body, headers=token)
    assert first.status_code == 200, first.json()
    assert first.json()["accepted"] == 1
    assert first.json()["duplicates"] == 0

    second = setup_client.post("/api/import/browser", json=body, headers=token)
    assert second.status_code == 200, second.json()
    assert second.json()["accepted"] == 0
    assert second.json()["duplicates"] == 1


def test_imported_job_is_assessed_and_never_fetched(setup_client, csrf, connection) -> None:
    _ready(setup_client, csrf)
    token = _token(setup_client, csrf)
    response = setup_client.post(
        "/api/import/browser",
        json={"source": "jobstreet", "page_url": PAGE, "jobs": [_card()]},
        headers=token,
    )
    assert response.status_code == 200, response.json()
    job_id = response.json()["job_ids"][0]

    row = connection.execute(
        "SELECT j.job_id, j.status, s.source_id, s.enabled, s.access_method "
        "FROM job j JOIN source_registry s ON s.source_id = j.source_id "
        "WHERE j.job_id = ?",
        (job_id,),
    ).fetchone()
    assert row is not None
    assert row["source_id"] == "manual_url"
    assert int(row["enabled"]) == 0
    assert row["access_method"] == "manual_url"

    apply_url = connection.execute(
        "SELECT apply_url FROM job WHERE job_id = ?", (job_id,)
    ).fetchone()
    assert apply_url["apply_url"] == "https://id.jobstreet.com/job/123456"

    assessment = connection.execute(
        "SELECT status FROM eligibility_assessment WHERE job_id = ?", (job_id,)
    ).fetchone()
    assert assessment is not None


def test_import_rejects_a_web_page_origin(setup_client, csrf) -> None:
    token = _token(setup_client, csrf)
    response = setup_client.post(
        "/api/import/browser",
        json={"source": "jobstreet", "page_url": PAGE, "jobs": [_card()]},
        headers={**token, "Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_not_allowed"


def test_issuing_a_token_replaces_the_previous_one(setup_client, csrf) -> None:
    first = _token(setup_client, csrf)
    second = _token(setup_client, csrf)
    assert first["X-Gawe-Token"] != second["X-Gawe-Token"]
    body = {"source": "jobstreet", "page_url": PAGE, "jobs": [_card()]}
    stale = setup_client.post("/api/import/browser", json=body, headers=first)
    assert stale.status_code == 401
    fresh = setup_client.post("/api/import/browser", json=body, headers=second)
    assert fresh.status_code in (200, 409), fresh.json()
