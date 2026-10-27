"""Requirement extraction against the database: the cache and the audit row.

`job_requirement` is keyed by posting version, and a version is unique per
content hash, so the stored rows *are* the cache: a second assessment of the
same version must not pay for the same reading twice. Only rows the model wrote
count as a hit. A deterministic reading is cheap to recompute, and freezing it
would keep a posting that was first assessed without a provider on the fallback
forever.

The app is not used to drive assessment here, only to store the posting: the
prompt files live under the repository root, while a test app is rooted in a tmp
directory.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from gawe.api.app import create_app
from gawe.config import load_config
from gawe.llm.client import LLMClient
from gawe.llm.providers.base import Call, Completion
from gawe.profile.store import ProfileStore
from gawe.services.assessment_service import AssessmentService
from tests.conftest import extract_profile, latest_profile, upload_cv

ROOT = Path(__file__).resolve().parents[2]
DESCRIPTIONS = Path(__file__).resolve().parent / "fixtures" / "jobs" / "descriptions"
JOBSTREET_PAGE = "https://id.jobstreet.com/backend-engineer-jobs"
DESCRIPTION = (DESCRIPTIONS / "jobstreet_backend_id.txt").read_text(encoding="utf-8")

# Every quote is copied from the fixture, so it survives the quote check.
REPLY = {
    "requirements": [
        {
            "requirement_id": "r1",
            "kind": "must_have",
            "text": "Minimal 3 tahun pengalaman membangun backend dengan Python",
            "quote": "Minimal 3 tahun pengalaman membangun backend dengan Python",
            "skill": "Python",
            "weight": None,
        },
        {
            "requirement_id": "r2",
            "kind": "must_have",
            "text": "Menguasai FastAPI atau Django REST Framework",
            "quote": "Menguasai FastAPI atau Django REST Framework",
            "skill": "FastAPI",
            "weight": None,
        },
        {
            "requirement_id": "r3",
            "kind": "nice_to_have",
            "text": "Diutamakan yang pernah menangani sistem pembayaran",
            "quote": "Diutamakan yang pernah menangani sistem pembayaran",
            "skill": None,
            "weight": None,
        },
    ],
    "no_must_have_found": False,
}


class RequirementProvider:
    """Answers `extract` with requirement JSON; counts its calls."""

    provider_id = "fake"

    def __init__(self, reply: dict = REPLY) -> None:
        self.reply = reply
        self.calls: list[Call] = []

    def complete(self, call: Call) -> Completion:
        self.calls.append(call)
        return Completion(text=json.dumps(self.reply), input_tokens=900, output_tokens=200)


def _service(connection, provider: RequirementProvider) -> AssessmentService:
    config = load_config(_written_config())
    # The stub provider is local, so the cloud gate does not apply.
    config.privacy.cloud_consent_required = False
    client = LLMClient(config=config, provider=provider, connection=connection)
    return AssessmentService(
        connection, ProfileStore(connection), llm_client=client, root_dir=ROOT
    )


def _written_config() -> Path:
    """A minimal config, written once, so the test never reads the user's own."""
    path = ROOT / "temporary" / "test-requirements-config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '[llm]\nactive_provider = "provider_a"\n'
        '[llm.providers.provider_a]\ntype = "fake"\n'
        '[llm.roles]\nextract = "model-x"\nclassify = "model-x"\n'
        'write = "model-y"\nreview = "model-z"\n',
        encoding="utf-8",
    )
    return path


def _confirm_profile(client: TestClient, csrf: dict[str, str]) -> dict[str, str]:
    upload_cv(client, csrf)
    extract_profile(client, csrf)
    profile = latest_profile(client)
    response = client.post(
        f"/api/setup/profiles/{profile['profile_version_id']}/confirm", headers=csrf, json={}
    )
    assert response.status_code == 200, response.json()
    return csrf


def _imported_job(client: TestClient, csrf: dict[str, str]) -> str:
    csrf = _confirm_profile(client, csrf)
    token = client.post("/api/settings/browser-import-token", headers=csrf).json()["token"]
    response = client.post(
        "/api/import/browser",
        headers={**csrf, "X-Gawe-Token": token},
        json={
            "source": "jobstreet",
            "page_url": JOBSTREET_PAGE,
            "mode": "detail",
            "detail": {
                "title": "Backend Engineer (Python)",
                "url": "https://id.jobstreet.com/job/998877",
                "company": "PT Nusantara Digital",
                "location": "Jakarta Selatan, Jakarta Raya",
                "description": DESCRIPTION,
            },
        },
    )
    assert response.status_code == 200, response.json()
    return response.json()["job_ids"][0]


def _version_id(connection, job_id: str) -> str:
    return connection.execute(
        "SELECT latest_version_id FROM job WHERE job_id = ?", (job_id,)
    ).fetchone()["latest_version_id"]


def _rows(connection, version_id: str) -> list[dict]:
    return [
        dict(row)
        for row in connection.execute(
            "SELECT requirement_id, kind, category, text, weight, source "
            "FROM job_requirement WHERE job_posting_version_id = ? ORDER BY text",
            (version_id,),
        ).fetchall()
    ]


def test_model_reading_is_stored_once_and_reused(
    setup_client: TestClient, csrf: dict[str, str], connection
) -> None:
    job_id = _imported_job(setup_client, csrf)
    version_id = _version_id(connection, job_id)
    # A detail page carries the full text, so it is not a teaser.
    completeness = connection.execute(
        "SELECT completeness_json FROM job WHERE job_id = ?", (job_id,)
    ).fetchone()["completeness_json"]
    assert "snippet_only" not in completeness
    # Start from "never extracted" so the model is the only source available.
    connection.execute(
        "DELETE FROM job_requirement WHERE job_posting_version_id = ?", (version_id,)
    )

    provider = RequirementProvider()
    service = _service(connection, provider)
    service.assess_job(job_id)

    rows = _rows(connection, version_id)
    texts = [row["text"] for row in rows]
    assert "Menguasai FastAPI atau Django REST Framework" in texts
    assert {row["source"] for row in rows} == {"llm"}
    assert [row["weight"] for row in rows if row["kind"] == "must_have"] == [1.0, 1.0]
    assert len(provider.calls) == 1

    # Same posting version: the rows are the cache, so nothing is re-asked.
    service.assess_job(job_id)
    assert len(provider.calls) == 1
    assert [row["text"] for row in _rows(connection, version_id)] == texts


def test_call_is_recorded_in_llm_call_with_metadata_only(
    setup_client: TestClient, csrf: dict[str, str], connection
) -> None:
    job_id = _imported_job(setup_client, csrf)
    version_id = _version_id(connection, job_id)
    connection.execute(
        "DELETE FROM job_requirement WHERE job_posting_version_id = ?", (version_id,)
    )

    provider = RequirementProvider()
    _service(connection, provider).assess_job(job_id)

    row = connection.execute(
        "SELECT role, provider, model, prompt_id, prompt_hash, response_hash, "
        "input_tokens, output_tokens FROM llm_call "
        "WHERE prompt_id = 'parse_requirements'"
    ).fetchone()
    assert row is not None
    assert row["role"] == "extract"
    assert row["provider"] == "fake"
    assert row["model"] == "model-x"
    assert row["input_tokens"] == 900
    assert row["output_tokens"] == 200
    assert len(row["prompt_hash"]) == 64
    # Metadata only: no posting text reaches the audit row.
    assert "Minimal 3 tahun" not in " ".join(
        str(row[key]) for key in ("prompt_id", "prompt_hash", "response_hash", "model")
    )


def test_fallback_row_is_retried_once_a_provider_is_available(
    setup_client: TestClient, csrf: dict[str, str], connection
) -> None:
    job_id = _imported_job(setup_client, csrf)
    version_id = _version_id(connection, job_id)
    # Simulate a run with no provider: the store kept the zero-weight fallback.
    connection.execute(
        "DELETE FROM job_requirement WHERE job_posting_version_id = ?", (version_id,)
    )
    connection.execute(
        "INSERT INTO job_requirement (requirement_id, job_posting_version_id, kind, "
        "category, text, quote, weight, constraint_json, source, created_at) "
        "VALUES ('req_fallback', ?, 'responsibility', 'other', 'deskripsi', 'deskripsi', "
        "0.0, NULL, 'fallback', '2026-10-20T00:00:00Z')",
        (version_id,),
    )

    provider = RequirementProvider()
    _service(connection, provider).assess_job(job_id)

    assert len(provider.calls) == 1
    rows = _rows(connection, version_id)
    assert "deskripsi" not in [row["text"] for row in rows]
    assert {row["source"] for row in rows} == {"llm"}


def test_a_model_reading_that_finds_nothing_is_cached_too(
    setup_client: TestClient, csrf: dict[str, str], connection
) -> None:
    """A failed reading is retried; a model saying "no requirement" is an answer."""
    job_id = _imported_job(setup_client, csrf)
    version_id = _version_id(connection, job_id)
    connection.execute(
        "DELETE FROM job_requirement WHERE job_posting_version_id = ?", (version_id,)
    )

    provider = RequirementProvider({"requirements": [], "no_must_have_found": True})
    service = _service(connection, provider)
    service.assess_job(job_id)

    rows = _rows(connection, version_id)
    assert [row["kind"] for row in rows] == ["responsibility"]
    assert {row["source"] for row in rows} == {"llm"}

    service.assess_job(job_id)
    assert len(provider.calls) == 1


def test_a_deterministic_reading_is_recomputed_not_frozen(
    setup_client: TestClient, csrf: dict[str, str], connection
) -> None:
    """Cheap to recompute, and freezing it would hide a later provider."""
    job_id = _imported_job(setup_client, csrf)
    version_id = _version_id(connection, job_id)
    rows = _rows(connection, version_id)
    assert rows and {row["source"] for row in rows} == {"regex"}

    provider = RequirementProvider()
    _service(connection, provider).assess_job(job_id)

    # The posting was already read, but not by the model, so the model is asked.
    assert len(provider.calls) == 1
    assert {row["source"] for row in _rows(connection, version_id)} == {"llm"}
