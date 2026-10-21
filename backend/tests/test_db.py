"""MySQL migrations, schema guards, constraints, and transaction atomicity."""

from __future__ import annotations

from pathlib import Path

import pymysql
import pytest
import uuid

from gawe.db import repo
from gawe.profile.store import ProfileStore
from tests.conftest import TEST_SCHEMA, database_config

# Latest migration filename, so adding a migration does not rewrite every assertion.
LATEST_SCHEMA = sorted(path.stem for path in repo.MIGRATIONS_DIR.glob("*.sql"))[-1]

TABLES = {
    "schema_version",
    "consent_record",
    "llm_call",
    "master_cv",
    "source_document",
    "profile_version",
    "profile_correction",
    "profile_decision",
    "task",
    "source_registry",
    "discovery_run",
    "discovery_run_source",
    "source_fetch",
    "job",
    "job_posting_version",
    "job_requirement",
    "eligibility_assessment",
    "fit_assessment",
    "ranking_run",
    "application",
    "document_version",
    "document_approval",
}


def _insert_master_cv(connection, master_cv_id: str = "mcv_1", sha: str = "a" * 64) -> None:
    connection.execute(
        "INSERT INTO master_cv (master_cv_id, sha256, filename, mime, size_bytes, "
        "page_count, status, uploaded_at) VALUES (?, ?, 'cv.md', 'text/markdown', 10, 1, "
        "'uploaded', '2026-10-19T00:00:00Z')",
        (master_cv_id, sha),
    )


def _insert_profile(connection, profile_version_id: str, version: int, active: int,
                    profile_id: str = "prf_1") -> None:
    connection.execute(
        "INSERT INTO profile_version (profile_version_id, profile_id, master_cv_id, version, "
        "status, content_json, evidence_json, conflicts_json, active, created_at, updated_at) "
        "VALUES (?, ?, 'mcv_1', ?, 'draft', '{}', '{}', '[]', ?, "
        "'2026-10-19T00:00:00Z', '2026-10-19T00:00:00Z')",
        (profile_version_id, profile_id, version, active),
    )


def test_migration_applies_and_is_idempotent(connection) -> None:
    assert repo.schema_version(connection) == LATEST_SCHEMA
    assert repo.migrate(connection) == []
    assert repo.schema_version(connection) == LATEST_SCHEMA


def test_tables_exist(connection) -> None:
    names = {
        row["name"]
        for row in connection.execute(
            "SELECT table_name AS name FROM information_schema.tables "
            "WHERE table_schema = DATABASE()"
        ).fetchall()
    }
    assert TABLES <= names


def _consent_columns(connection) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(
            "SELECT column_name AS name FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = 'consent_record'"
        ).fetchall()
    }


def test_consent_migration_handles_unapplied_and_partial_schema(tmp_path: Path) -> None:
    """0003 must apply to a fresh schema and re-run after a partial apply."""
    settings = database_config().model_copy(
        update={"name": f"{repo.TEST_SCHEMA_PREFIX}consent_{uuid.uuid4().hex[:8]}"}
    )
    repo.ensure_schema(settings)
    db = repo.connect(settings)
    try:
        pre_0003 = tmp_path / "pre_0003"
        pre_0003.mkdir()
        for name in ("0001_initial.sql", "0002_setup.sql"):
            (pre_0003 / name).write_text(
                (repo.MIGRATIONS_DIR / name).read_text(encoding="utf-8"), encoding="utf-8"
            )
        assert repo.migrate(db, pre_0003) == ["0001_initial", "0002_setup"]
        assert "text_version" not in _consent_columns(db)

        db.execute(
            "INSERT INTO consent_record (consent_id, consent_type, provider_id, "
            "model_snapshot, text, granted_at, revoked_at) VALUES "
            "('consent_old', 'cloud_data_processing', 'provider_a', '{}', 'old text', "
            "'2026-10-18T00:00:00Z', NULL)"
        )
        # Simulate a partial apply: one column exists, schema_version not recorded.
        db.execute(
            "ALTER TABLE consent_record ADD COLUMN text_version VARCHAR(100) "
            "NOT NULL DEFAULT ''"
        )

        assert repo.migrate(db) == [
            path.stem
            for path in sorted(repo.MIGRATIONS_DIR.glob("*.sql"))
            if path.stem > "0002_setup"
        ]
        assert {"text_version", "text_sha256", "data_classes_json"} <= _consent_columns(db)
        row = db.execute(
            "SELECT text_version, text_sha256, data_classes_json FROM consent_record "
            "WHERE consent_id = 'consent_old'"
        ).fetchone()
        assert row["text_version"] == ""
        assert row["text_sha256"] == ""
        assert row["data_classes_json"] is None
        assert repo.migrate(db) == []
    finally:
        db.close()
        repo.drop_schema(settings)


def test_failed_migration_records_nothing(tmp_path: Path, connection) -> None:
    broken = tmp_path / "migrations"
    broken.mkdir()
    (broken / "0003_broken.sql").write_text("CREATE TABLE ok (id TEXT); THIS IS NOT SQL;")
    with pytest.raises(repo.MigrationError) as exc:
        repo.migrate(connection, broken)
    assert "0003_broken" in str(exc.value)
    assert repo.schema_version(connection) == LATEST_SCHEMA


def test_duplicate_master_cv_sha256_is_rejected(connection) -> None:
    _insert_master_cv(connection, "mcv_1", "b" * 64)
    with pytest.raises(pymysql.IntegrityError):
        _insert_master_cv(connection, "mcv_2", "b" * 64)


def test_profile_version_number_is_unique_per_profile(connection) -> None:
    _insert_master_cv(connection)
    _insert_profile(connection, "prv_1", 1, 0)
    with pytest.raises(pymysql.IntegrityError):
        _insert_profile(connection, "prv_2", 1, 0)


def test_only_one_active_profile_version(connection) -> None:
    _insert_master_cv(connection)
    _insert_profile(connection, "prv_1", 1, 1)
    with pytest.raises(pymysql.IntegrityError):
        _insert_profile(connection, "prv_2", 2, 1)


def test_inactive_profile_versions_are_unlimited(connection) -> None:
    _insert_master_cv(connection)
    _insert_profile(connection, "prv_1", 1, 0)
    _insert_profile(connection, "prv_2", 2, 0)
    rows = connection.execute("SELECT COUNT(*) AS total FROM profile_version").fetchone()
    assert rows["total"] == 2


def test_foreign_key_rejects_unknown_master_cv(connection) -> None:
    with pytest.raises(pymysql.IntegrityError):
        connection.execute(
            "INSERT INTO source_document (doc_id, master_cv_id, sha256, mime, blocks_json, "
            "created_at) VALUES ('doc_1', 'missing', ?, 'text/markdown', '{}', "
            "'2026-10-19T00:00:00Z')",
            ("c" * 64,),
        )


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO discovery_run (run_id, task_id, profile_version_id, status, "
        "counts_json, started_at) VALUES ('run_x', 'missing', 'missing', 'queued', '{}', "
        "'2026-10-20T00:00:00Z')",
        "INSERT INTO source_fetch (fetch_id, run_id, source_id, status, fetched_at, "
        "raw_sha256, raw_json) VALUES ('fet_x', 'run_x', 'missing', 'completed', "
        "'2026-10-20T00:00:00Z', 'x', '{}')",
        "INSERT INTO job (job_id, source_id, source_job_id, canonical_url, company, title, "
        "location_json, work_mode, employment_type, seniority, market, fetched_at, status, "
        "completeness_json, created_at, updated_at) VALUES ('job_x', 'missing', '1', "
        "'https://example.com/1', 'Acme', 'Engineer', '{}', 'onsite', 'full_time', "
        "'unknown', 'unknown', '2026-10-20T00:00:00Z', 'open', '{}', "
        "'2026-10-20T00:00:00Z', '2026-10-20T00:00:00Z')",
    ],
)
def test_discovery_foreign_keys_reject_orphans(connection, statement) -> None:
    with pytest.raises(pymysql.IntegrityError):
        connection.execute(statement)


def test_multi_table_transaction_rolls_back(connection) -> None:
    with pytest.raises(pymysql.IntegrityError):
        with connection:
            _insert_master_cv(connection)
            _insert_master_cv(connection)  # duplicate primary key aborts the block
    rows = connection.execute("SELECT COUNT(*) AS total FROM master_cv").fetchone()
    assert rows["total"] == 0


def test_confirm_rolls_back_when_decision_write_fails(connection, monkeypatch) -> None:
    _insert_master_cv(connection)
    _insert_profile(connection, "prv_1", 1, 0)
    store = ProfileStore(connection)

    def explode(*args, **kwargs):
        raise pymysql.IntegrityError("decision write failed")

    monkeypatch.setattr(ProfileStore, "_record_decision", staticmethod(explode))
    with pytest.raises(pymysql.IntegrityError):
        store.confirm("prv_1", None)

    version = connection.execute(
        "SELECT status, active FROM profile_version WHERE profile_version_id = 'prv_1'"
    ).fetchone()
    assert version["status"] == "draft"
    assert version["active"] == 0
    master = connection.execute("SELECT status FROM master_cv WHERE master_cv_id = 'mcv_1'").fetchone()
    assert master["status"] == "uploaded"


def test_drop_schema_rejects_non_test_names() -> None:
    with pytest.raises(repo.SchemaNameError):
        repo.validate_schema_name("gawe", for_drop=True)
    with pytest.raises(repo.SchemaNameError):
        repo.validate_schema_name("gawe_test_x; DROP DATABASE gawe", for_drop=True)
    with pytest.raises(repo.SchemaNameError):
        repo.validate_schema_name("mysql", for_drop=True)
    assert repo.validate_schema_name(TEST_SCHEMA, for_drop=True) == TEST_SCHEMA


def test_require_test_schema_rejects_development_schema() -> None:
    with pytest.raises(repo.SchemaNameError):
        repo.require_test_schema("gawe")
    with pytest.raises(repo.SchemaNameError):
        repo.require_test_schema("gawe_test_x; DROP DATABASE gawe")
    assert repo.require_test_schema(TEST_SCHEMA) == TEST_SCHEMA


def test_drop_schema_never_targets_development_schema(monkeypatch) -> None:
    development = database_config().model_copy(update={"name": "gawe"})
    monkeypatch.setattr(
        repo, "_raw_connect", lambda *a, **k: pytest.fail("must not connect before validating")
    )
    with pytest.raises(repo.SchemaNameError):
        repo.drop_schema(development)


def test_reset_keeps_schema_and_migration_history(connection) -> None:
    _insert_master_cv(connection)
    repo.reset(connection)
    assert repo.schema_version(connection) == LATEST_SCHEMA
    rows = connection.execute("SELECT COUNT(*) AS total FROM master_cv").fetchone()
    assert rows["total"] == 0


def test_ensure_schema_is_idempotent() -> None:
    settings = database_config().model_copy(
        update={"name": f"{repo.TEST_SCHEMA_PREFIX}ensure_{uuid.uuid4().hex[:8]}"}
    )
    try:
        repo.ensure_schema(settings)
        repo.ensure_schema(settings)
        db = repo.connect(settings)
        try:
            assert repo.schema_version(db) == "none"
        finally:
            db.close()
    finally:
        repo.drop_schema(settings)
