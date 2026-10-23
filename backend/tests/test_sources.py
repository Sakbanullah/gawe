"""Source registry API: create, verify, enable, disable, and URL guard."""

from __future__ import annotations

from types import SimpleNamespace

from gawe.jobs.sources import registry as registry_module

BASE = {
    "company": "Acme",
    "market": "global",
    "careers_url": "https://boards.greenhouse.io/acme",
    "access_method": "ats_api",
    "ats": "greenhouse",
}


def _allow_public_urls(monkeypatch) -> None:
    monkeypatch.setattr(
        registry_module, "validate_url", lambda url: SimpleNamespace(url=url)
    )


def test_new_source_is_unverified_and_disabled(setup_client, csrf, monkeypatch) -> None:
    _allow_public_urls(monkeypatch)
    response = setup_client.post("/api/settings/sources", headers=csrf, json=BASE)
    assert response.status_code == 201, response.json()
    source = response.json()
    assert source["verification_status"] == "unverified"
    assert source["enabled"] is False
    assert source["job_count"] == 0
    assert source["last_checked_at"] is None


def test_unverified_source_cannot_be_enabled(setup_client, csrf, monkeypatch) -> None:
    _allow_public_urls(monkeypatch)
    created = setup_client.post("/api/settings/sources", headers=csrf, json=BASE).json()
    response = setup_client.patch(
        f"/api/settings/sources/{created['source_id']}",
        headers=csrf,
        json={"enabled": True},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "source_not_verified"


def test_verify_then_enable_and_disable(setup_client, csrf, monkeypatch) -> None:
    _allow_public_urls(monkeypatch)
    created = setup_client.post("/api/settings/sources", headers=csrf, json=BASE).json()
    source_id = created["source_id"]

    verified = setup_client.patch(
        f"/api/settings/sources/{source_id}",
        headers=csrf,
        json={"verification_status": "verified"},
    )
    assert verified.status_code == 200
    assert verified.json()["verification_status"] == "verified"
    assert verified.json()["enabled"] is False

    enabled = setup_client.patch(
        f"/api/settings/sources/{source_id}", headers=csrf, json={"enabled": True}
    )
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    disabled = setup_client.patch(
        f"/api/settings/sources/{source_id}", headers=csrf, json={"enabled": False}
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False


def test_edit_changes_company_and_careers_url(
    setup_client, csrf, monkeypatch
) -> None:
    _allow_public_urls(monkeypatch)
    created = setup_client.post("/api/settings/sources", headers=csrf, json=BASE).json()
    response = setup_client.patch(
        f"/api/settings/sources/{created['source_id']}",
        headers=csrf,
        json={
            "company": "Acme Baru",
            "careers_url": "https://jobs.lever.co/acme",
            "ats": "lever",
            "tos_notes": "diizinkan",
        },
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["company"] == "Acme Baru"
    assert updated["careers_url"] == "https://jobs.lever.co/acme"
    assert updated["ats"] == "lever"
    assert updated["tos_notes"] == "diizinkan"
    assert updated["verification_status"] == "unverified"


def test_ats_must_match_careers_url_host_on_create(
    setup_client, csrf, monkeypatch
) -> None:
    _allow_public_urls(monkeypatch)
    response = setup_client.post(
        "/api/settings/sources",
        headers=csrf,
        json={**BASE, "careers_url": "https://jobs.lever.co/acme"},
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert error["details"][0]["field"] == "careers_url"
    assert error["details"][0]["code"] == "ats_host_mismatch"


def test_ats_must_match_careers_url_host_on_update(
    setup_client, csrf, monkeypatch
) -> None:
    _allow_public_urls(monkeypatch)
    created = setup_client.post("/api/settings/sources", headers=csrf, json=BASE).json()
    response = setup_client.patch(
        f"/api/settings/sources/{created['source_id']}",
        headers=csrf,
        json={"careers_url": "https://jobs.lever.co/acme"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["code"] == "ats_host_mismatch"


def test_ats_api_requires_a_known_adapter(setup_client, csrf, monkeypatch) -> None:
    _allow_public_urls(monkeypatch)
    response = setup_client.post(
        "/api/settings/sources",
        headers=csrf,
        json={**BASE, "ats": "unknown"},
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert error["details"][0]["code"] == "ats_unavailable"


def test_html_source_is_rejected_because_no_adapter_can_fetch_it(
    setup_client, csrf, monkeypatch
) -> None:
    _allow_public_urls(monkeypatch)
    response = setup_client.post(
        "/api/settings/sources",
        headers=csrf,
        json={
            **BASE,
            "careers_url": "https://careers.example.com/acme",
            "access_method": "html",
            "ats": "unknown",
        },
    )
    assert response.status_code == 400, response.json()
    error = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert error["details"][0]["field"] == "access_method"


def test_aggregator_is_rejected_until_a_feed_has_an_adapter(
    setup_client, csrf, monkeypatch
) -> None:
    """No aggregator adapter ships since Himalayas was dropped from the sources."""
    _allow_public_urls(monkeypatch)
    payload = {
        "company": "Example Feed",
        "market": "global",
        "careers_url": "https://boards.greenhouse.io/acme",
        "access_method": "aggregator",
        "ats": "greenhouse",
    }
    response = setup_client.post("/api/settings/sources", headers=csrf, json=payload)
    assert response.status_code == 400, response.json()
    assert response.json()["error"]["details"][0]["field"] == "access_method"


def test_an_unknown_ats_is_rejected(setup_client, csrf, monkeypatch) -> None:
    _allow_public_urls(monkeypatch)
    payload = {**BASE, "ats": "unknown"}
    response = setup_client.post("/api/settings/sources", headers=csrf, json=payload)
    assert response.status_code == 400, response.json()
    assert response.json()["error"]["details"][0]["code"] == "ats_unavailable"


def test_a_removed_ats_is_not_accepted_by_the_contract(
    setup_client, csrf, monkeypatch
) -> None:
    """`himalayas` left the `ats` enum when its adapter was deleted."""
    _allow_public_urls(monkeypatch)
    payload = {**BASE, "ats": "himalayas"}
    response = setup_client.post("/api/settings/sources", headers=csrf, json=payload)
    assert response.status_code == 400, response.json()
    assert response.json()["error"]["details"][0]["field"] == "ats"


def test_broken_or_restricted_source_cannot_stay_enabled(
    setup_client, csrf, monkeypatch
) -> None:
    _allow_public_urls(monkeypatch)
    created = setup_client.post("/api/settings/sources", headers=csrf, json=BASE).json()
    source_id = created["source_id"]
    setup_client.patch(
        f"/api/settings/sources/{source_id}",
        headers=csrf,
        json={"verification_status": "verified", "enabled": True},
    )
    response = setup_client.patch(
        f"/api/settings/sources/{source_id}",
        headers=csrf,
        json={"verification_status": "restricted"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "source_not_verified"


def test_insecure_careers_url_is_rejected(setup_client, csrf) -> None:
    payload = {**BASE, "careers_url": "http://boards.greenhouse.io/acme"}
    response = setup_client.post("/api/settings/sources", headers=csrf, json=payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "url_rejected"


def test_manual_url_is_not_user_managed(setup_client, csrf, monkeypatch) -> None:
    _allow_public_urls(monkeypatch)
    payload = {**BASE, "access_method": "manual_url"}
    response = setup_client.post("/api/settings/sources", headers=csrf, json=payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_failed"


def test_list_filters_and_pagination(setup_client, csrf, monkeypatch) -> None:
    _allow_public_urls(monkeypatch)
    first = setup_client.post(
        "/api/settings/sources", headers=csrf, json={**BASE, "company": "Alpha"}
    ).json()
    setup_client.post(
        "/api/settings/sources",
        headers=csrf,
        json={**BASE, "company": "Beta", "careers_url": "https://boards.greenhouse.io/beta"},
    )
    setup_client.patch(
        f"/api/settings/sources/{first['source_id']}",
        headers=csrf,
        json={"verification_status": "verified"},
    )

    verified = setup_client.get(
        "/api/settings/sources", params={"verification_status": "verified"}
    ).json()
    assert [item["company"] for item in verified["items"]] == ["Alpha"]

    page = setup_client.get("/api/settings/sources", params={"limit": 1}).json()
    assert len(page["items"]) == 1
    assert page["page"]["has_more"] is True
    assert page["page"]["next_cursor"] == page["items"][0]["source_id"]


def test_a_legacy_html_row_can_still_be_updated(
    setup_client, csrf, monkeypatch, connection
) -> None:
    """B7: the Edit modal resends the stored binding, so an unchanged value must not re-gate."""
    _allow_public_urls(monkeypatch)
    connection.execute(
        "INSERT INTO source_registry (source_id, company, market, careers_url, "
        "access_method, ats, verification_status, enabled, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "src_legacy",
            "Legacy",
            "global",
            "https://careers.example.com/acme",
            "html",
            "unknown",
            "unverified",
            0,
            "2026-10-01T00:00:00Z",
            "2026-10-01T00:00:00Z",
        ),
    )
    response = setup_client.patch(
        "/api/settings/sources/src_legacy",
        headers=csrf,
        json={
            "company": "Legacy",
            "careers_url": "https://careers.example.com/acme",
            "market": "global",
            "ats": "unknown",
            "verification_status": "verified",
        },
    )
    assert response.status_code == 200, response.json()
    assert response.json()["verification_status"] == "verified"


