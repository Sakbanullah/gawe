"""Provider integration contract. No network, always part of the default suite.

Covers:
- extraction blocked without valid consent;
- consent scoped to configured provider, models, and data classes;
- the configured provider/model are the ones actually used;
- evidence and quotations trace back to the synthetic source;
- `prompt_hash` and provider/model metadata are recorded reproducibly;
- provider errors never fall back to another provider.

Live 9Router verification is a separate, explicitly opt-in test:
`tests/test_live_9router.py`. It never runs from this file.
"""

from __future__ import annotations

import hashlib
import json
import logging
import traceback
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gawe.api.app import _make_provider, create_app
from gawe.config import resolve_api_key
from gawe.db.repo import Connection
from gawe.ingest.text import parse_text
from gawe.ingest.types import normalize_text
from gawe.llm.client import LLMClient, LLMContractError
from gawe.llm.providers.base import Call, Completion, ProviderError
from gawe.llm.providers.fake import FakeProvider
from gawe.llm.providers.synthetic import SyntheticExtractProvider
from gawe.profile.extract import extract_profile, load_prompt, locator_text
from gawe.security.consent import ConsentStore, ConsentRequired

from .conftest import FIXTURE_CV, upload_cv

ROOT = Path(__file__).resolve().parents[2]


def assert_no_secret(text: str, secret: str, label: str) -> None:
    """Fail without echoing the secret into the pytest assertion output."""
    if secret in text:
        pytest.fail(f"{label} contains the API key")

PROFILE_SCHEMA = {
    "type": "object",
    "required": ["personal", "education", "experience", "skills", "evidence_index"],
    "properties": {
        "personal": {"type": "object"},
        "education": {"type": "array"},
        "experience": {"type": "array"},
        "skills": {"type": "array"},
        "evidence_index": {"type": "object"},
    },
}


class RecordingProvider:
    """Fake provider that also records its configured identity."""

    def __init__(self, provider_id: str = "provider_a") -> None:
        self.provider_id = provider_id
        self.calls: list[Call] = []
        self.inner = FakeProvider(['{"personal": {}, "education": [], "experience": [], '
                                   '"skills": [], "evidence_index": {}}'])

    def complete(self, call: Call) -> Completion:
        self.calls.append(call)
        return self.inner.complete(call)


class FailingProvider:
    """Always fails. Used to prove the client never switches provider."""

    provider_id = "provider_a"

    def __init__(self, retryable: bool = False) -> None:
        self.retryable = retryable
        self.calls: list[Call] = []

    def complete(self, call: Call) -> Completion:
        self.calls.append(call)
        raise ProviderError("provider_unavailable", retryable=self.retryable)


class _FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def _fake_completion_payload(text: str) -> dict:
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
    }


def _synthetic_document():
    return parse_text(FIXTURE_CV.read_bytes())


def _extract(config, connection: Connection, provider, run_doc_id: str = "doc_syn_001"):
    client = LLMClient(
        config=config,
        provider=provider,
        consent_store=ConsentStore(connection, config),
        connection=connection,
    )
    prompt_id, prompt_version, prompt_body = load_prompt(ROOT)
    document = _synthetic_document()
    content, evidence, conflicts, metadata = extract_profile(
        client, document, run_doc_id, prompt_body, prompt_id, prompt_version, None
    )
    return client, document, content, evidence, conflicts, metadata


# -- consent gate -----------------------------------------------------------
def test_extraction_is_blocked_without_consent(config, connection: Connection) -> None:
    provider = RecordingProvider()
    app = create_app(
        config,
        llm_client=LLMClient(config=config, provider=provider, consent_store=None),
    )
    with TestClient(app) as client:
        headers = {"X-CSRF-Token": client.get("/api/session").json()["csrf_token"]}
        assert upload_cv(client, headers).status_code == 201
        response = client.post("/api/setup/master-cv/extractions", headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "consent_required"
    assert provider.calls == [], "provider was reached without consent"


def test_consent_scope_is_provider_model_and_data_classes(
    config, connection: Connection
) -> None:
    store = ConsentStore(connection, config)
    required = store.required_scope()
    assert required["provider_id"] == config.llm.active_provider
    assert required["model_roles"] == dict(config.llm.roles)
    assert sorted(required["data_classes"]) == [
        "cv_text",
        "job_description",
        "profile_slice",
    ]

    store.grant()
    store.require()

    changed_model = config.model_copy(deep=True)
    changed_model.llm.roles["extract"] = "model-other"
    with pytest.raises(ConsentRequired):
        ConsentStore(connection, changed_model).require()

    changed_provider = config.model_copy(deep=True)
    changed_provider.llm.active_provider = "provider_b"
    changed_provider.llm.providers["provider_b"] = config.llm.providers["provider_a"]
    with pytest.raises(ConsentRequired):
        ConsentStore(connection, changed_provider).require()

    # A record that omits one required data class is not valid.
    connection.execute(
        "UPDATE consent_record SET data_classes_json = ?",
        (json.dumps(["cv_text", "profile_slice"]),),
    )
    with pytest.raises(ConsentRequired):
        store.require()


# -- configured provider and model -----------------------------------------
def test_adapter_sends_configured_model_and_never_invents_a_provider(
    config, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[urllib.request.Request] = []

    def capture(request, timeout=None):
        sent.append(request)
        return _FakeHTTPResponse(_fake_completion_payload('{"ok": true}'))

    monkeypatch.setattr(urllib.request, "urlopen", capture)
    monkeypatch.delenv("GAWE_LLM_API_KEY", raising=False)

    keyless = config.model_copy(deep=True)
    keyless.llm.providers["provider_a"].api_key_ref = None
    provider = _make_provider(keyless)
    assert provider.provider_id == config.llm.active_provider
    assert provider.base_url == config.llm.providers["provider_a"].base_url.rstrip("/")

    provider.complete(
        Call(
            role="extract",
            model=config.llm.roles["extract"],
            messages=[{"role": "user", "content": "synthetic"}],
            temperature=0.0,
            max_tokens=64,
            timeout_s=5,
        )
    )

    assert len(sent) == 1
    body = json.loads(sent[0].data.decode("utf-8"))
    assert body["model"] == config.llm.roles["extract"]
    assert sent[0].full_url == (
        config.llm.providers["provider_a"].base_url.rstrip("/") + "/chat/completions"
    )
    assert sent[0].get_header("Authorization") is None


def test_api_key_comes_from_env_only_when_configured(
    config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GAWE_LLM_API_KEY", raising=False)
    assert resolve_api_key(None) is None
    monkeypatch.setenv("GAWE_LLM_API_KEY", "synthetic-test-key")
    assert resolve_api_key(None) == "synthetic-test-key"

    env_only = config.model_copy(deep=True)
    env_only.llm.providers["provider_a"].api_key_ref = None
    provider = _make_provider(env_only)
    assert provider.api_key == "synthetic-test-key"
    assert "synthetic-test-key" not in json.dumps(config.snapshot())


def test_provider_failure_never_exposes_the_api_key(
    config, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "synthetic-provider-key-not-for-output"
    monkeypatch.setenv("GAWE_LLM_API_KEY", secret)
    keyless = config.model_copy(deep=True)
    keyless.llm.providers["provider_a"].api_key_ref = None
    provider = _make_provider(keyless)
    if provider.api_key != secret:
        pytest.fail("provider did not receive the resolved API key")

    def reject(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", reject)
    with pytest.raises(ProviderError) as exc:
        provider.complete(
            Call(
                role="extract",
                model=config.llm.roles["extract"],
                messages=[{"role": "user", "content": "synthetic"}],
                temperature=0.0,
                max_tokens=64,
                timeout_s=5,
            )
        )

    assert_no_secret(str(exc.value), secret, "exception message")
    assert_no_secret(
        "".join(traceback.format_exception(exc.value)), secret, "exception traceback"
    )
    assert_no_secret(json.dumps(config.snapshot()), secret, "config snapshot")
    assert_no_secret(config.model_dump_json(), secret, "config dump")


def test_active_provider_selects_the_configured_provider(
    config, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = config.model_copy(deep=True)
    other.llm.providers["provider_b"] = other.llm.providers["provider_a"].model_copy(
        update={"base_url": "https://provider-b.example/v1"}
    )
    other.llm.active_provider = "provider_b"

    provider = _make_provider(other)
    assert provider.provider_id == "provider_b"
    assert provider.base_url == "https://provider-b.example/v1"
    assert "provider-a.example" not in provider.base_url


# -- evidence traceability --------------------------------------------------
def test_evidence_and_quotes_trace_to_the_synthetic_source(
    config, connection: Connection
) -> None:
    ConsentStore(connection, config).grant()
    _, document, content, evidence, _, _ = _extract(
        config, connection, SyntheticExtractProvider()
    )

    source = normalize_text(document.text)
    assert evidence, "synthetic provider produced no evidence"
    for evidence_id, item in evidence.items():
        assert item["doc_id"] == "doc_syn_001"
        assert item["source"] == "cv"
        assert normalize_text(item["quote"]) in source, evidence_id
        assert item["locator"] is not None

    facts = [item for key in ("education", "experience", "skills") for item in content[key]]
    assert facts
    for fact in facts:
        assert fact["evidence"]
        assert all(ref in evidence for ref in fact["evidence"])
    for experience in content["experience"]:
        for bullet in experience["bullets"]:
            assert bullet["evidence"]
            assert all(ref in evidence for ref in bullet["evidence"])


# -- reproducibility --------------------------------------------------------
def test_prompt_hash_and_metadata_are_reproducible(
    config, connection: Connection
) -> None:
    ConsentStore(connection, config).grant()
    _, document, _, _, _, first = _extract(config, connection, SyntheticExtractProvider())
    _, _, _, _, _, second = _extract(config, connection, SyntheticExtractProvider())

    prompt_id, prompt_version, prompt_body = load_prompt(ROOT)
    messages = [
        {"role": "system", "content": prompt_body},
        {
            "role": "user",
            "content": "<untrusted>\n" + locator_text(document) + "\n</untrusted>",
        },
    ]
    expected_hash = hashlib.sha256(
        json.dumps(messages, sort_keys=True).encode("utf-8")
    ).hexdigest()

    assert first["prompt_hash"] == second["prompt_hash"] == expected_hash
    assert first["response_hash"] == second["response_hash"]
    assert first["prompt_id"] == prompt_id
    assert first["prompt_version"] == prompt_version
    assert first["model"] == config.llm.roles["extract"]
    assert first["config_snapshot_id"] == second["config_snapshot_id"]

    rows = connection.execute(
        "SELECT provider, model, prompt_id, prompt_hash, response_hash, error_code "
        "FROM llm_call ORDER BY created_at"
    ).fetchall()
    assert len(rows) == 2
    for row in rows:
        assert row["provider"] == "fake"
        assert row["model"] == config.llm.roles["extract"]
        assert row["prompt_id"] == prompt_id
        assert row["prompt_hash"] == expected_hash
        assert row["error_code"] is None


def test_prompt_hash_changes_with_source_text(config, connection: Connection) -> None:
    ConsentStore(connection, config).grant()
    client = LLMClient(
        config=config,
        provider=SyntheticExtractProvider(),
        consent_store=ConsentStore(connection, config),
        connection=connection,
    )
    prompt_id, prompt_version, prompt_body = load_prompt(ROOT)
    first = extract_profile(
        client, _synthetic_document(), "doc_a", prompt_body, prompt_id, prompt_version, None
    )
    second = extract_profile(
        client, parse_text(FIXTURE_CV.read_bytes() + b"\n- Synthetic extra line\n"),
        "doc_b", prompt_body, prompt_id, prompt_version, None,
    )
    assert first[3]["prompt_hash"] != second[3]["prompt_hash"]


def test_log_has_metadata_only(
    config, connection: Connection, caplog, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "synthetic-log-key-not-for-output"
    monkeypatch.setenv("GAWE_LLM_API_KEY", secret)
    ConsentStore(connection, config).grant()
    caplog.set_level(logging.INFO, logger="gawe.llm.client")
    _extract(config, connection, SyntheticExtractProvider())

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "prompt_hash=" in logged
    assert "provider=" in logged
    assert "Ayu Pratama" not in logged
    assert "ayu.pratama@example.com" not in logged
    assert "PT Contoh Teknologi" not in logged
    assert secret not in logged


# -- no cross-provider fallback --------------------------------------------
def test_provider_error_does_not_fall_back(config, connection: Connection) -> None:
    provider = FailingProvider(retryable=False)
    client = LLMClient(
        config=config, provider=provider, consent_store=None, connection=connection
    )

    with pytest.raises(LLMContractError) as exc:
        client.generate("extract", [{"role": "user", "content": "cv"}], PROFILE_SCHEMA, 0.0, 64)

    assert exc.value.code == "provider_unavailable"
    assert len(provider.calls) == 1
    assert connection.execute("SELECT COUNT(*) AS n FROM llm_call").fetchone()["n"] == 0
    assert client.provider is provider


def test_retryable_error_retries_same_provider_only(config) -> None:
    provider = FailingProvider(retryable=True)
    client = LLMClient(
        config=config,
        provider=provider,
        consent_store=None,
        sleep=lambda _seconds: None,
    )

    with pytest.raises(LLMContractError):
        client.generate("extract", [{"role": "user", "content": "cv"}], PROFILE_SCHEMA, 0.0, 64)

    assert len(provider.calls) == 1 + config.llm.max_retries
    assert {call.model for call in provider.calls} == {config.llm.roles["extract"]}


def test_single_active_provider_is_the_only_one_constructed(
    config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GAWE_LLM_API_KEY", raising=False)
    two_providers = config.model_copy(deep=True)
    two_providers.llm.providers["provider_b"] = two_providers.llm.providers[
        "provider_a"
    ].model_copy(update={"base_url": "https://provider-b.example/v1"})

    provider = _make_provider(two_providers)
    assert provider.provider_id == two_providers.llm.active_provider
    assert provider.base_url == two_providers.llm.providers[
        two_providers.llm.active_provider
    ].base_url.rstrip("/")
