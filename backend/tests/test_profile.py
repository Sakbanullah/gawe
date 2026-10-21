"""Profile extraction, evidence, conflicts, versioning, confirmation, gate."""

from __future__ import annotations

import hashlib
from pathlib import Path

from tests.conftest import (
    FIXTURE_CV,
    extract_profile,
    latest_profile,
    upload_cv,
)

FACT_KEYS = (
    "education",
    "experience",
    "skills",
    "projects",
    "certifications",
    "languages",
    "awards",
    "work_authorization",
)


def _confirmed(client, csrf) -> dict:
    upload_cv(client, csrf)
    extract_profile(client, csrf)
    profile = latest_profile(client)
    response = client.post(
        f"/api/setup/profiles/{profile['profile_version_id']}/confirm", headers=csrf, json={}
    )
    assert response.status_code == 200, response.json()
    return profile


def test_fake_provider_produces_profile_with_evidence(setup_client, csrf) -> None:
    upload_cv(setup_client, csrf)
    response = extract_profile(setup_client, csrf)
    assert response.status_code == 202
    task = setup_client.get(f"/api/tasks/{response.json()['task_id']}").json()
    assert task["status"] == "completed"
    assert task["result"]["counts"]["facts"] > 0

    profile = latest_profile(setup_client)
    assert profile["status"] == "draft"
    assert profile["content"]["personal"]["full_name"] == "Ayu Pratama"
    assert profile["content"]["experience"][0]["company"] == "PT Contoh Teknologi"


def test_zero_facts_without_evidence(setup_client, csrf) -> None:
    upload_cv(setup_client, csrf)
    extract_profile(setup_client, csrf)
    profile = latest_profile(setup_client)
    evidence_index = profile["evidence_index"]
    for key in FACT_KEYS:
        for item in profile["content"][key]:
            assert item["evidence"], f"{key} item without evidence"
            assert all(ref in evidence_index for ref in item["evidence"])
    for experience in profile["content"]["experience"]:
        for bullet in experience["bullets"]:
            assert bullet["evidence"]
            assert all(ref in evidence_index for ref in bullet["evidence"])


def test_evidence_quotes_exist_in_source(setup_client, csrf) -> None:
    upload_cv(setup_client, csrf)
    extract_profile(setup_client, csrf)
    profile = latest_profile(setup_client)
    source = FIXTURE_CV.read_text(encoding="utf-8")
    from gawe.ingest.types import normalize_text

    normalized = normalize_text(source)
    for item in profile["evidence_index"].values():
        assert normalize_text(item["quote"]) in normalized


def test_fake_provider_never_calls_network(setup_client, csrf, setup_config) -> None:
    from gawe.llm.providers.synthetic import SyntheticExtractProvider

    upload_cv(setup_client, csrf)
    extract_profile(setup_client, csrf)
    assert isinstance(setup_client.app.state.llm_client.provider, SyntheticExtractProvider)
    assert setup_client.app.state.llm_client.provider.calls


def test_reupload_detects_conflict(setup_client, csrf) -> None:
    _confirmed(setup_client, csrf)
    changed = FIXTURE_CV.read_text(encoding="utf-8").replace(
        "2020-03 – 2022-06", "2020-03 – 2022-08"
    )
    upload_cv(setup_client, csrf, data=changed.encode("utf-8"), name="candidate_001.md")
    extract_profile(setup_client, csrf)
    profile = latest_profile(setup_client)
    assert profile["conflicts"], "expected a detected conflict"
    paths = [conflict["path"] for conflict in profile["conflicts"]]
    assert any(path.startswith("experience.") for path in paths)


def test_confirm_blocked_while_conflicts_unresolved(setup_client, csrf) -> None:
    _confirmed(setup_client, csrf)
    changed = FIXTURE_CV.read_text(encoding="utf-8").replace(
        "2020-03 – 2022-06", "2020-03 – 2022-08"
    )
    upload_cv(setup_client, csrf, data=changed.encode("utf-8"))
    extract_profile(setup_client, csrf)
    profile = latest_profile(setup_client)
    response = setup_client.post(
        f"/api/setup/profiles/{profile['profile_version_id']}/confirm", headers=csrf, json={}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "profile_conflicts_unresolved"


def test_conflict_resolution_then_confirm(setup_client, csrf) -> None:
    _confirmed(setup_client, csrf)
    changed = FIXTURE_CV.read_text(encoding="utf-8").replace(
        "2020-03 – 2022-06", "2020-03 – 2022-08"
    )
    upload_cv(setup_client, csrf, data=changed.encode("utf-8"))
    extract_profile(setup_client, csrf)
    draft = latest_profile(setup_client)
    conflict = draft["conflicts"][0]
    response = setup_client.patch(
        f"/api/setup/profiles/{draft['profile_version_id']}",
        headers=csrf,
        json={
            "expected_version": draft["version"],
            "corrections": [
                {"path": f"conflicts.{conflict['conflict_id']}", "value": conflict["candidates"][1]["value"]}
            ],
        },
    )
    assert response.status_code == 200, response.json()
    assert response.json()["conflicts"] == []
    confirmed = setup_client.post(
        f"/api/setup/profiles/{draft['profile_version_id']}/confirm", headers=csrf, json={}
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"


def test_correction_requires_matching_version(setup_client, csrf) -> None:
    upload_cv(setup_client, csrf)
    extract_profile(setup_client, csrf)
    profile = latest_profile(setup_client)
    response = setup_client.patch(
        f"/api/setup/profiles/{profile['profile_version_id']}",
        headers=csrf,
        json={"expected_version": 99, "corrections": [{"path": "personal.phone", "value": "+62"}]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "version_conflict"


def test_correction_on_confirmed_creates_new_draft(setup_client, csrf) -> None:
    confirmed = _confirmed(setup_client, csrf)
    response = setup_client.patch(
        f"/api/setup/profiles/{confirmed['profile_version_id']}",
        headers=csrf,
        json={
            "expected_version": confirmed["version"],
            "corrections": [{"path": "personal.phone", "value": "+62 811 000 000", "reason": "typo"}],
        },
    )
    assert response.status_code == 201
    draft = response.json()
    assert draft["status"] == "draft"
    assert draft["derived_from_profile_version_id"] == confirmed["profile_version_id"]
    assert draft["content"]["personal"]["phone"] == "+62 811 000 000"

    untouched = setup_client.get(
        f"/api/setup/profiles/{confirmed['profile_version_id']}"
    ).json()
    assert untouched["status"] == "confirmed"
    assert untouched["active"] is True
    assert untouched["content"]["personal"]["phone"] == "+62 21 0000 0000"


def test_rollback_moves_active_pointer_without_new_version(setup_client, csrf) -> None:
    first = _confirmed(setup_client, csrf)
    corrected = setup_client.patch(
        f"/api/setup/profiles/{first['profile_version_id']}",
        headers=csrf,
        json={"expected_version": 1, "corrections": [{"path": "personal.phone", "value": "+62 811"}]},
    ).json()
    assert setup_client.post(
        f"/api/setup/profiles/{corrected['profile_version_id']}/confirm", headers=csrf, json={}
    ).status_code == 200

    versions_before = len(setup_client.get("/api/setup/profiles").json()["items"])
    response = setup_client.post(
        "/api/setup/profile/rollback",
        headers=csrf,
        json={"target_profile_version_id": first["profile_version_id"], "reason": "wrong correction"},
    )
    assert response.status_code == 200
    assert response.json()["profile_version_id"] == first["profile_version_id"]
    assert response.json()["active"] is True
    versions_after = len(setup_client.get("/api/setup/profiles").json()["items"])
    assert versions_before == versions_after


def test_rollback_rejects_unconfirmed_target(setup_client, csrf) -> None:
    _confirmed(setup_client, csrf)
    upload_cv(setup_client, csrf, data=b"# Second CV\n\n- Python\n", name="second.md")
    extract_profile(setup_client, csrf)
    draft = latest_profile(setup_client)
    response = setup_client.post(
        "/api/setup/profile/rollback",
        headers=csrf,
        json={"target_profile_version_id": draft["profile_version_id"], "reason": "test"},
    )
    assert response.status_code == 409


def test_discovery_gate_stays_locked_until_confirmed(setup_client, csrf) -> None:
    assert setup_client.get("/api/overview").json()["next_action"]["code"] == "upload_master_cv"
    upload_cv(setup_client, csrf)
    assert setup_client.get("/api/overview").json()["next_action"]["code"] == "review_profile"
    extract_profile(setup_client, csrf)
    assert setup_client.get("/api/overview").json()["next_action"]["code"] == "confirm_profile"
    profile = latest_profile(setup_client)
    setup_client.post(
        f"/api/setup/profiles/{profile['profile_version_id']}/confirm", headers=csrf, json={}
    )
    assert setup_client.get("/api/overview").json()["next_action"]["code"] == "run_discovery"


def test_master_cv_unchanged_after_profile_edit(
    setup_client, csrf, setup_root: Path
) -> None:
    confirmed = _confirmed(setup_client, csrf)
    sha = confirmed["master_cv_id"]
    record_before = setup_client.get("/api/setup/master-cv").json()
    stored = (
        setup_root
        / "data"
        / "master_cv"
        / record_before["original_file"]["sha256"]
        / "original.md"
    )
    bytes_before = stored.read_bytes()

    setup_client.patch(
        f"/api/setup/profiles/{confirmed['profile_version_id']}",
        headers=csrf,
        json={"expected_version": 1, "corrections": [{"path": "personal.phone", "value": "+62 811"}]},
    )
    record_after = setup_client.get("/api/setup/master-cv").json()
    assert record_after["master_cv_id"] == sha
    assert record_after["original_file"]["sha256"] == record_before["original_file"]["sha256"]
    assert stored.read_bytes() == bytes_before
    assert hashlib.sha256(bytes_before).hexdigest() == record_before["original_file"]["sha256"]


def test_extraction_requires_master_cv(setup_client, csrf) -> None:
    response = extract_profile(setup_client, csrf)
    assert response.status_code == 404
