from __future__ import annotations

from fastapi.testclient import TestClient

import pytest

from gawe.api.app import create_app
from gawe.db import repo

# Every test here builds an app against the test schema and asserts empty counts.
pytestmark = pytest.mark.usefixtures("_clean_database")


def _client(config) -> TestClient:
    return TestClient(create_app(config))


def test_session_sets_cookies_and_returns_token(config) -> None:
    with _client(config) as client:
        response = client.get("/api/session")
    assert response.status_code == 200
    body = response.json()
    assert body["csrf_header"] == "X-CSRF-Token"
    assert body["csrf_token"]
    cookies = response.headers.get_list("set-cookie")
    assert any("gawe_session=" in value and "HttpOnly" in value for value in cookies)
    assert any("gawe_csrf=" in value and "HttpOnly" not in value for value in cookies)


def test_overview_shape(config) -> None:
    with _client(config) as client:
        response = client.get("/api/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["next_action"]["code"] == "upload_master_cv"
    assert body["counts"]["eligible"] == 0
    assert body["provider_configured"] is True


def test_mutation_without_csrf_is_rejected(config) -> None:
    with _client(config) as client:
        response = client.post("/api/overview")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_invalid"


def test_mutation_with_valid_csrf_reaches_routing(config) -> None:
    with _client(config) as client:
        session = client.get("/api/session").json()
        response = client.post(
            "/api/overview", headers={"X-CSRF-Token": session["csrf_token"]}
        )
    assert response.status_code == 405


def test_app_does_not_hold_a_shared_connection(config) -> None:
    from gawe.api.app import create_app

    app = create_app(config)
    assert app.state.db is None
    with TestClient(app) as client:
        assert client.get("/api/overview").status_code == 200


def test_startup_runs_migrations(config) -> None:
    with _client(config) as client:
        assert client.get("/api/overview").status_code == 200
    connection = repo.connect(config.database)
    assert repo.schema_version(connection) == "0011_documents"
    connection.close()
