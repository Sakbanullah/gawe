"""`POST .../revision-request`: only checked findings, and only real ones."""

from __future__ import annotations

from dataclasses import replace

from gawe.services import document_service
from tests.test_documents import _application, _generate


def _path(application_id: str, version_id: str) -> str:
    return f"/api/applications/{application_id}/documents/{version_id}/revision-request"


def _edited(client, csrf, application_id: str, version: dict) -> dict:
    response = client.post(
        f"/api/applications/{application_id}/documents/{version['document_version_id']}/revisions",
        headers=csrf,
        json={
            "base_content_hash": version["content_hash"],
            "edits": [{"path": "summary.text", "value": "Led every migration alone."}],
        },
    )
    assert response.status_code == 201, response.json()
    return response.json()


def test_revision_request_needs_at_least_one_finding(setup_client, csrf, monkeypatch) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    version = _generate(setup_client, csrf, application_id, kinds=("cover_letter",))[0]
    response = setup_client.post(
        _path(application_id, version["document_version_id"]),
        headers=csrf,
        json={
            "base_content_hash": version["content_hash"],
            "reason": "review_changes",
            "finding_ids": [],
        },
    )
    assert response.status_code == 400, response.json()
    assert response.json()["error"]["code"] in {"validation_failed", "empty"}


def test_revision_request_rejects_an_unknown_finding(setup_client, csrf, monkeypatch) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    version = _generate(setup_client, csrf, application_id, kinds=("cv",))[0]
    target = _edited(setup_client, csrf, application_id, version)
    response = setup_client.post(
        _path(application_id, target["document_version_id"]),
        headers=csrf,
        json={
            "base_content_hash": target["content_hash"],
            "reason": "review_changes",
            "finding_ids": ["f_does_not_exist"],
        },
    )
    assert response.status_code == 400, response.json()
    assert response.json()["error"]["code"] == "unknown_finding"


def test_revision_request_rejects_a_stale_hash(setup_client, csrf, monkeypatch) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    version = _generate(setup_client, csrf, application_id, kinds=("cover_letter",))[0]
    response = setup_client.post(
        _path(application_id, version["document_version_id"]),
        headers=csrf,
        json={
            "base_content_hash": "0" * 64,
            "reason": "review_changes",
            "finding_ids": ["f1"],
        },
    )
    assert response.status_code == 409, response.json()
    assert response.json()["error"]["code"] == "version_conflict"


def test_revision_request_creates_a_new_version(setup_client, csrf, monkeypatch) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    version = _generate(setup_client, csrf, application_id, kinds=("cv",))[0]
    target = _edited(setup_client, csrf, application_id, version)
    reviewed = setup_client.post(
        f"/api/applications/{application_id}/documents/{target['document_version_id']}/review",
        headers=csrf,
    )
    assert reviewed.status_code == 202, reviewed.json()

    # Whatever this version reports, ask for a revision of exactly those ids.
    findings = setup_client.get(
        f"/api/applications/{application_id}/documents/{target['document_version_id']}/findings"
    ).json()["findings"]
    ids = [item["finding_id"] for item in findings] or ["fnd_001"]
    response = setup_client.post(
        _path(application_id, target["document_version_id"]),
        headers=csrf,
        json={
            "base_content_hash": target["content_hash"],
            "reason": "review_changes",
            "finding_ids": ids,
            "note": "perbaiki temuan yang dicentang",
        },
    )
    if findings:
        assert response.status_code == 202, response.json()
        items = setup_client.get(
            f"/api/applications/{application_id}/documents"
        ).json()["items"]
        newest = max(items, key=lambda item: item["version"])
        assert newest["version"] > target["version"]
        assert newest["status"] in {"draft", "in_review"}
        assert newest["approved"] is False
    else:
        # No finding on this version: the id is unknown, so it must be rejected.
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "unknown_finding"


def test_resolved_findings_are_not_a_valid_selection() -> None:
    """A checked finding the review already resolved has nothing left to fix."""
    parent = {
        "findings": {
            "findings": [
                {"finding_id": "f1", "status": "resolved"},
                {"finding_id": "f2", "status": "open"},
            ]
        }
    }
    known = document_service._selectable_findings(parent)
    assert "f1" not in known
    assert "f2" in known
