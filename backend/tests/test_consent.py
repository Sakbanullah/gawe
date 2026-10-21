from __future__ import annotations

import pytest

from gawe.config import Config
from gawe.db.repo import Connection
from gawe.security import consent as consent_module
from gawe.security.consent import (
    CONSENT_TEXT_SHA256,
    CONSENT_TEXT_VERSION,
    ConsentAlreadyRevoked,
    ConsentNotFound,
    ConsentRequired,
    ConsentStore,
)


def _store(connection: Connection, config: Config) -> ConsentStore:
    return ConsentStore(connection, config)


def test_consent_required_before_grant(connection: Connection, config: Config) -> None:
    with pytest.raises(ConsentRequired):
        _store(connection, config).require()


def test_grant_persists_text_version_and_scope(connection: Connection, config: Config) -> None:
    store = _store(connection, config)
    record = store.grant()

    assert record["consent_type"] == "cloud_data_processing"
    assert record["text_version"] == CONSENT_TEXT_VERSION
    assert record["scope"]["provider_id"] == config.llm.active_provider
    assert record["scope"]["model_roles"] == dict(config.llm.roles)
    assert sorted(record["scope"]["data_classes"]) == [
        "cv_text",
        "job_description",
        "profile_slice",
    ]

    row = connection.execute(
        "SELECT text_version, text_sha256, provider_id, model_snapshot, data_classes_json "
        "FROM consent_record"
    ).fetchone()
    assert row["text_version"] == CONSENT_TEXT_VERSION
    assert row["text_sha256"] == CONSENT_TEXT_SHA256
    assert row["provider_id"] == config.llm.active_provider
    store.require()


def test_status_reports_granted_and_history(connection: Connection, config: Config) -> None:
    store = _store(connection, config)
    status = store.status()
    assert status["required"] is True
    assert status["granted"] is False
    assert status["current"] is None
    assert status["required_text"]["text_sha256"] == CONSENT_TEXT_SHA256

    store.grant()
    status = store.status()
    assert status["required"] is False
    assert status["granted"] is True
    assert status["current"]["text_version"] == CONSENT_TEXT_VERSION
    assert len(status["history"]) == 1
    assert status["history_truncated"] is False


def test_revoke_marks_record_and_blocks_provider(connection: Connection, config: Config) -> None:
    store = _store(connection, config)
    record = store.grant()

    revoked = store.revoke(record["consent_id"])
    assert revoked["revoked_at"] is not None
    assert store.current() is None
    assert store.status()["required"] is True
    with pytest.raises(ConsentRequired):
        store.require()

    row = connection.execute("SELECT revoked_at FROM consent_record").fetchone()
    assert row["revoked_at"] is not None


def test_revoke_unknown_or_twice_fails(connection: Connection, config: Config) -> None:
    store = _store(connection, config)
    with pytest.raises(ConsentNotFound):
        store.revoke("missing")
    record = store.grant()
    store.revoke(record["consent_id"])
    with pytest.raises(ConsentAlreadyRevoked):
        store.revoke(record["consent_id"])


def test_expired_text_version_requires_new_consent(
    connection: Connection, config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(connection, config)
    store.grant()

    monkeypatch.setattr(consent_module, "CONSENT_TEXT_VERSION", "2026-11-01.1")
    assert store.status()["granted"] is False
    assert store.status()["required"] is True
    with pytest.raises(ConsentRequired):
        store.require()


def test_provider_or_model_change_invalidates_consent(
    connection: Connection, config: Config
) -> None:
    store = _store(connection, config)
    store.grant()

    changed = config.model_copy(deep=True)
    changed.llm.roles["extract"] = "model-new"
    status = ConsentStore(connection, changed).status()
    assert status["granted"] is False
    assert status["model_changed_since_consent"] is True
    assert status["provider_changed_since_consent"] is False

    changed = config.model_copy(deep=True)
    changed.llm.active_provider = "provider_b"
    changed.llm.providers["provider_b"] = changed.llm.providers["provider_a"]
    status = ConsentStore(connection, changed).status()
    assert status["granted"] is False
    assert status["provider_changed_since_consent"] is True


def test_fake_provider_needs_no_consent(connection: Connection, config: Config) -> None:
    fake = config.model_copy(deep=True)
    fake.llm.active_provider = "fake"
    fake.llm.providers = {"fake": fake.llm.providers["provider_a"].model_copy(
        update={"type": "fake"}
    )}
    store = ConsentStore(connection, fake)
    assert store.cloud_required() is False
    assert store.status()["required"] is False
    store.require()
