"""Human eligibility review (D21) and the full-description extension path."""

from __future__ import annotations

from tests.test_assessment import _confirm

SEARCH = "https://id.jobstreet.com/backend-engineer-jobs?page=2"
JOB_URL = "https://id.jobstreet.com/id/job/95319880"
DETAIL_URL = "https://id.jobstreet.com/id/job/95319880?type=standard"

DESCRIPTION = "\n".join(
    [
        "Senior Backend Engineer",
        "PT Contoh Teknologi",
        "Requirements",
        "Minimum 5 years of experience building backend services in Python.",
        "Bachelor degree in Computer Science or equivalent.",
        "Strong knowledge of PostgreSQL and Docker.",
        "Responsibilities",
        "Build and maintain the payment service.",
    ]
)


def _token(client, csrf) -> dict[str, str]:
    response = client.get("/api/settings/browser-import-token", headers=csrf)
    assert response.status_code == 200, response.json()
    return {"X-Gawe-Token": response.json()["token"]}


def _card() -> dict:
    return {
        "title": "Senior Backend Engineer",
        "url": JOB_URL,
        "company": "PT Contoh Teknologi",
        "location": "Jakarta",
        "snippet": "Membangun layanan backend Python dan SQL untuk tim data.",
        "posted_at": "2026-10-20",
    }


def _import_card(client, csrf) -> dict:
    _confirm(client, csrf)
    token = _token(client, csrf)
    response = client.post(
        "/api/import/browser",
        json={"source": "jobstreet", "page_url": SEARCH, "jobs": [_card()]},
        headers=token,
    )
    assert response.status_code == 200, response.json()
    return response.json()


def _detail() -> dict:
    return {
        "title": "Senior Backend Engineer",
        "url": JOB_URL,
        "company": "PT Contoh Teknologi",
        "location": "Jakarta",
        "posted_at": "2026-10-20",
        "description": DESCRIPTION,
    }


def _review(client, csrf, job_id: str, status, reason):
    return client.patch(
        f"/api/matches/{job_id}/eligibility",
        headers=csrf,
        json={"status": status, "reason": reason},
    )


# -- full description --------------------------------------------------------
def test_detail_updates_the_same_job_instead_of_creating_a_second(setup_client, csrf) -> None:
    first = _import_card(setup_client, csrf)
    assert first["accepted"] == 1
    job_id = first["job_ids"][0]

    token = _token(setup_client, csrf)
    response = setup_client.post(
        "/api/import/browser",
        json={"source": "jobstreet", "page_url": DETAIL_URL, "mode": "detail", "detail": _detail()},
        headers=token,
    )
    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["mode"] == "detail"
    assert payload["job_ids"] == [job_id]
    assert payload["duplicates"] == 1
    assert payload["accepted"] == 0

    detail = setup_client.get(f"/api/matches/{job_id}")
    assert detail.status_code == 200, detail.json()
    body = detail.json()
    assert "Minimum 5 years of experience" in body["job_detail"]["description_text"]
    posted = [field for field in body["job_detail"]["job"]["completeness"]["missing_fields"]]
    assert "posted_at" not in posted


def test_detail_without_a_description_is_rejected(setup_client, csrf) -> None:
    _import_card(setup_client, csrf)
    token = _token(setup_client, csrf)
    detail = {**_detail(), "description": "terlalu pendek"}
    response = setup_client.post(
        "/api/import/browser",
        json={"source": "jobstreet", "page_url": DETAIL_URL, "mode": "detail", "detail": detail},
        headers=token,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "description_too_short"


def test_detail_mode_requires_the_detail_object(setup_client, csrf) -> None:
    token = _token(setup_client, csrf)
    response = setup_client.post(
        "/api/import/browser",
        json={"source": "jobstreet", "page_url": DETAIL_URL, "mode": "detail"},
        headers=token,
    )
    assert response.status_code == 400


def test_card_posted_date_is_stored(setup_client, csrf, connection) -> None:
    payload = _import_card(setup_client, csrf)
    row = connection.execute(
        "SELECT posted_at FROM job WHERE job_id = ?", (payload["job_ids"][0],)
    ).fetchone()
    assert row["posted_at"].startswith("2026-10-20")


# -- human review (D21) ------------------------------------------------------
def test_review_marks_a_needs_review_job_eligible(setup_client, csrf) -> None:
    payload = _import_card(setup_client, csrf)
    job_id = payload["job_ids"][0]
    assert payload["eligibility"]["status"] == "needs_review"

    response = _review(setup_client, csrf, job_id, "eligible", "Deskripsi dibaca; syarat dipenuhi.")
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["eligibility"]["status"] == "eligible"
    assert body["eligibility"]["auto_status"] == "needs_review"
    assert body["eligibility"]["override_reason"].startswith("Deskripsi dibaca")


def test_review_can_close_a_job_as_ineligible(setup_client, csrf) -> None:
    payload = _import_card(setup_client, csrf)
    job_id = payload["job_ids"][0]
    response = _review(setup_client, csrf, job_id, "ineligible", "Butuh gelar sarjana yang tidak ada.")
    assert response.status_code == 200, response.json()
    assert response.json()["eligibility"]["status"] == "ineligible"
    assert response.json()["eligibility"]["auto_status"] == "needs_review"


def test_review_requires_a_reason(setup_client, csrf) -> None:
    payload = _import_card(setup_client, csrf)
    job_id = payload["job_ids"][0]
    response = _review(setup_client, csrf, job_id, "eligible", None)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_failed"

    blank = _review(setup_client, csrf, job_id, "eligible", "   ")
    assert blank.status_code == 400


def test_review_rejects_a_job_that_is_already_eligible(setup_client, csrf) -> None:
    payload = _import_card(setup_client, csrf)
    job_id = payload["job_ids"][0]
    assert _review(setup_client, csrf, job_id, "eligible", "ok").status_code == 200

    again = _review(setup_client, csrf, job_id, "ineligible", "berubah pikiran")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "override_not_allowed"


def test_review_can_be_cleared(setup_client, csrf) -> None:
    payload = _import_card(setup_client, csrf)
    job_id = payload["job_ids"][0]
    assert _review(setup_client, csrf, job_id, "eligible", "ok").status_code == 200

    cleared = _review(setup_client, csrf, job_id, None, None)
    assert cleared.status_code == 200, cleared.json()
    assert cleared.json()["eligibility"]["status"] == "needs_review"
    assert cleared.json()["eligibility"]["override_reason"] is None


def test_review_is_scoped_to_the_posting_version(setup_client, csrf) -> None:
    """A re-import stores a new posting version; the old decision stays there."""
    payload = _import_card(setup_client, csrf)
    job_id = payload["job_ids"][0]
    assert _review(setup_client, csrf, job_id, "eligible", "sudah saya baca").status_code == 200

    token = _token(setup_client, csrf)
    again = setup_client.post(
        "/api/import/browser",
        json={"source": "jobstreet", "page_url": DETAIL_URL, "mode": "detail", "detail": _detail()},
        headers=token,
    )
    assert again.status_code == 200, again.json()
    # The detail import stores a new posting version, so the new version is
    # judged by the rules alone; the decision stays with the version the
    # reviewer actually read.
    eligibility = again.json()["eligibility"]
    assert eligibility["override_reason"] is None
    assert eligibility["status"] == eligibility["auto_status"]


def test_review_is_dropped_when_the_posting_changes(setup_client, csrf) -> None:
    """A new posting version changes the requirements the reviewer read."""
    payload = _import_card(setup_client, csrf)
    job_id = payload["job_ids"][0]
    assert _review(setup_client, csrf, job_id, "eligible", "sudah saya baca").status_code == 200

    token = _token(setup_client, csrf)
    changed = _detail()["description"].replace(
        "Build and maintain the payment service.",
        "Build and maintain the payment service. Wajib onsite 5 hari di Jakarta.",
    )
    again = setup_client.post(
        "/api/import/browser",
        json={
            "source": "jobstreet",
            "page_url": DETAIL_URL,
            "mode": "detail",
            "detail": {**_detail(), "description": changed},
        },
        headers=token,
    )
    assert again.status_code == 200, again.json()

    # The re-import assesses the new posting version; the override belonged to
    # the old one and must not follow it.
    eligibility = setup_client.get(f"/api/matches/{job_id}").json()["eligibility"]
    assert eligibility["override_reason"] is None
    assert eligibility["status"] == eligibility["auto_status"]


def test_review_of_an_unknown_job_is_404(setup_client, csrf) -> None:
    _confirm(client=setup_client, csrf=csrf)
    response = _review(setup_client, csrf, "job_missing", "eligible", "ok")
    assert response.status_code == 404
