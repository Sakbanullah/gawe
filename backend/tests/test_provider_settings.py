"""D24: provider endpoint and API key edited from the browser.

No network. The keyring is replaced with an in-memory dict and the connection
test is exercised through a stub `urlopen`.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from gawe.services import provider_service

BASE = "https://router.example/v1"
ROLES = {
    "extract": "model-x",
    "classify": "model-y",
    "write": "model-z",
    "review": "model-w",
}


@pytest.fixture
def keyring_stub(monkeypatch):
    store: dict[tuple[str, str], str] = {}

    class Fake:
        @staticmethod
        def set_password(service, name, value):
            store[(service, name)] = value

        @staticmethod
        def get_password(service, name):
            return store.get((service, name))

    monkeypatch.setattr("keyring.set_password", Fake.set_password)
    monkeypatch.setattr("keyring.get_password", Fake.get_password)
    monkeypatch.setattr(provider_service, "key_writable", lambda: True)
    return store


def _put(client, csrf, **overrides):
    body = {"provider_id": "router", "base_url": BASE, "roles": ROLES}
    body.update(overrides)
    return client.put("/api/settings/provider", headers=csrf, json=body)


def test_get_provider_never_returns_a_secret(setup_client, csrf) -> None:
    response = setup_client.get("/api/settings/provider", headers=csrf)
    assert response.status_code == 200, response.json()
    body = response.json()
    assert set(body["roles"]) == {"extract", "classify", "write", "review"}
    assert "api_key" not in body
    assert body["key_source"] in {"keyring", "env", "missing"}


def test_update_writes_the_endpoint_and_the_key(setup_client, csrf, keyring_stub) -> None:
    response = _put(setup_client, csrf, api_key="sk-secret-value")
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["base_url"] == BASE
    assert body["configured"] is True
    assert body["key_source"] == "keyring"
    assert "sk-secret-value" not in json.dumps(body)

    saved = setup_client.get("/api/settings/provider", headers=csrf).json()
    assert saved["base_url"] == BASE
    assert saved["roles"]["write"]["model"] == "model-z"


def test_key_lands_in_the_keyring_not_in_config(setup_client, csrf, keyring_stub, setup_root) -> None:
    assert _put(setup_client, csrf, api_key="sk-abc").status_code == 200
    assert keyring_stub[("gawe", provider_service.DEFAULT_KEY_REF)] == "sk-abc"
    config_text = (setup_root / "config.toml").read_text(encoding="utf-8")
    assert "sk-abc" not in config_text
    assert BASE in config_text


def test_other_config_sections_survive_the_write(setup_client, csrf, keyring_stub, setup_root) -> None:
    before = (setup_root / "config.toml").read_text(encoding="utf-8")
    assert _put(setup_client, csrf, api_key="sk-abc").status_code == 200
    after = (setup_root / "config.toml").read_text(encoding="utf-8")
    for marker in ("[database]", "[privacy]", "[retention]", "[frontend]"):
        assert marker in before and marker in after


def test_update_rejects_a_plain_http_endpoint(setup_client, csrf, keyring_stub) -> None:
    response = _put(setup_client, csrf, base_url="http://router.example/v1")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_base_url"


def test_update_rejects_a_local_endpoint(setup_client, csrf, keyring_stub) -> None:
    for url in ("https://localhost/v1", "https://127.0.0.1/v1", "https://api.local/v1"):
        response = _put(setup_client, csrf, base_url=url)
        assert response.status_code == 400, url
        assert response.json()["error"]["code"] == "invalid_base_url"


def test_update_rejects_an_endpoint_with_credentials(setup_client, csrf, keyring_stub) -> None:
    response = _put(setup_client, csrf, base_url="https://user:pass@router.example/v1")
    assert response.status_code == 400


def test_update_requires_a_model_per_role(setup_client, csrf, keyring_stub) -> None:
    broken = {**ROLES, "write": "  "}
    response = _put(setup_client, csrf, roles=broken)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_model"


def test_update_without_a_key_keeps_the_endpoint(setup_client, csrf, keyring_stub) -> None:
    assert _put(setup_client, csrf, api_key="sk-first").status_code == 200
    second = _put(setup_client, csrf, base_url="https://router2.example/v1")
    assert second.status_code == 200, second.json()
    assert second.json()["base_url"] == "https://router2.example/v1"
    assert keyring_stub[("gawe", provider_service.DEFAULT_KEY_REF)] == "sk-first"


# -- connection test ---------------------------------------------------------
class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_connection_test_reports_models(setup_client, csrf, keyring_stub, monkeypatch) -> None:
    assert _put(setup_client, csrf, api_key="sk-abc").status_code == 200
    seen: dict = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        payload = {"data": [{"id": "model-a"}, {"id": "model-b"}]}
        return _Response(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    response = setup_client.post("/api/settings/provider/test", headers=csrf)
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["ok"] is True
    assert body["models"] == ["model-a", "model-b"]
    assert seen["url"] == f"{BASE}/models"
    assert seen["auth"] == "Bearer sk-abc"


def test_connection_test_without_a_key_is_409(setup_client, csrf, keyring_stub, monkeypatch) -> None:
    assert _put(setup_client, csrf).status_code == 200
    monkeypatch.delenv("GAWE_LLM_API_KEY", raising=False)
    response = setup_client.post("/api/settings/provider/test", headers=csrf)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "api_key_missing"


def test_connection_test_maps_401_to_a_readable_error(
    setup_client, csrf, keyring_stub, monkeypatch
) -> None:
    assert _put(setup_client, csrf, api_key="sk-bad").status_code == 200

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    response = setup_client.post("/api/settings/provider/test", headers=csrf)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "test_unauthorized"
