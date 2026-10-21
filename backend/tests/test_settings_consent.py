"""Consent API: grant, read, revoke, expired text, and provider blocking."""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from gawe.api.app import create_app
from gawe.security import consent as consent_module

# Consent history must start empty for every test in this module.
pytestmark = pytest.mark.usefixtures("_clean_database")


@pytest.fixture
def cloud_client(config):
    with TestClient(create_app(config)) as client:
        yield client


@pytest.fixture
def headers(cloud_client) -> dict[str, str]:
    return {"X-CSRF-Token": cloud_client.get("/api/session").json()["csrf_token"]}


def _grant_body(provider_id: str = "provider_a") -> dict:
    return {
        "consent_type": "cloud_data_processing",
        "scope": {
            "data_classes": ["cv_text", "job_description", "profile_slice"],
            "provider_id": provider_id,
        },
        "accepted": True,
    }


def test_get_consent_requires_consent(cloud_client) -> None:
    body = cloud_client.get("/api/settings/consent").json()
    assert body["required"] is True
    assert body["granted"] is False
    assert body["current"] is None
    assert body["required_text"]["text_version"]
    assert body["required_text"]["text_sha256"]
    assert body["required_scope"]["provider_id"] == "provider_a"
    assert body["history"] == []
    assert body["history_truncated"] is False


def test_grant_and_read_consent(cloud_client, headers) -> None:
    response = cloud_client.post("/api/settings/consent", headers=headers, json=_grant_body())
    assert response.status_code == 201
    record = response.json()
    assert record["consent_type"] == "cloud_data_processing"
    assert record["text_version"] == consent_module.CONSENT_TEXT_VERSION
    assert record["scope"]["model_roles"] == {
        "extract": "model-x",
        "classify": "model-x",
        "write": "model-y",
        "review": "model-z",
    }

    body = cloud_client.get("/api/settings/consent").json()
    assert body["required"] is False
    assert body["granted"] is True
    assert body["current"]["consent_id"] == record["consent_id"]
    assert len(body["history"]) == 1


def test_client_cannot_set_text_version(cloud_client, headers) -> None:
    body = {**_grant_body(), "text_version": "2099-01-01.1"}
    response = cloud_client.post("/api/settings/consent", headers=headers, json=body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_failed"
    assert cloud_client.get("/api/settings/consent").json()["granted"] is False


def test_grant_rejects_wrong_scope(cloud_client, headers) -> None:
    body = _grant_body(provider_id="provider_b")
    response = cloud_client.post("/api/settings/consent", headers=headers, json=body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_failed"


def test_revoke_consent(cloud_client, headers) -> None:
    record = cloud_client.post(
        "/api/settings/consent", headers=headers, json=_grant_body()
    ).json()
    response = cloud_client.delete(
        f"/api/settings/consent/{record['consent_id']}", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["revoked_at"] is not None

    body = cloud_client.get("/api/settings/consent").json()
    assert body["granted"] is False
    assert body["required"] is True
    assert body["current"] is None
    assert len(body["history"]) == 1
    assert body["history"][0]["revoked_at"] is not None


def test_revoke_unknown_consent_is_404(cloud_client, headers) -> None:
    response = cloud_client.delete("/api/settings/consent/missing", headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_history_limit_is_validated(cloud_client) -> None:
    response = cloud_client.get("/api/settings/consent?history_limit=0")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_failed"


def test_expired_text_version_requires_new_consent(
    cloud_client, headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    cloud_client.post("/api/settings/consent", headers=headers, json=_grant_body())
    monkeypatch.setattr(consent_module, "CONSENT_TEXT_VERSION", "2026-11-01.1")

    body = cloud_client.get("/api/settings/consent").json()
    assert body["granted"] is False
    assert body["required"] is True
    assert body["current"]["text_version"] == "2026-10-19.1"


def test_extraction_without_consent_is_blocked(config) -> None:
    from tests.conftest import upload_cv

    with TestClient(create_app(config)) as client:
        session = client.get("/api/session").json()
        headers = {"X-CSRF-Token": session["csrf_token"]}
        assert upload_cv(client, headers).status_code == 201
        response = client.post("/api/setup/master-cv/extractions", headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "consent_required"
