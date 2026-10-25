"""Phase 3D: deterministic drafts, versioning, review, and approval binding."""

from __future__ import annotations

import json

from gawe.documents import draft
from gawe.documents import review as review_rules
from tests.test_applications import _matched_jobs
from tests.test_assessment import _confirm


def _application(client, csrf, monkeypatch) -> tuple[str, dict]:
    _confirm(client, csrf)
    items = _matched_jobs(client, csrf, monkeypatch)
    eligible = next(item for item in items if item["eligibility"]["status"] == "eligible")
    created = client.post(
        "/api/applications", headers=csrf, json={"job_id": eligible["job"]["job_id"]}
    )
    assert created.status_code == 201, created.json()
    return created.json()["application_id"], eligible["job"]


def _generate(client, csrf, application_id: str, kinds=("cv", "cover_letter")) -> list[dict]:
    response = client.post(
        f"/api/applications/{application_id}/documents",
        headers=csrf,
        json={"kinds": list(kinds), "language": "en"},
    )
    assert response.status_code == 202, response.json()
    assert response.json()["type"] == "document_generation"
    assert response.json()["status"] == "completed"
    return client.get(f"/api/applications/{application_id}/documents").json()["items"]


def _detail(client, application_id: str, document_version_id: str) -> dict:
    response = client.get(
        f"/api/applications/{application_id}/documents/{document_version_id}"
    )
    assert response.status_code == 200, response.json()
    return response.json()


def _review(client, csrf, application_id: str, document_version_id: str) -> dict:
    response = client.post(
        f"/api/applications/{application_id}/documents/{document_version_id}/review",
        headers=csrf,
    )
    assert response.status_code == 202, response.json()
    assert response.json()["status"] == "completed"
    return _detail(client, application_id, document_version_id)


def _approve(
    client,
    csrf,
    application_id: str,
    document_version_id: str,
    content_hash: str,
    decision="approved",
    note=None,
):
    return client.post(
        f"/api/applications/{application_id}/documents/{document_version_id}/approval",
        headers=csrf,
        json={"decision": decision, "content_hash": content_hash, "note": note},
    )


# -- draft rules -------------------------------------------------------------
def test_required_missing_blocks_documents_without_name_or_facts() -> None:
    empty = {
        "kind": "cv",
        "header": {"full_name": None},
        "experience": [],
        "projects": [],
        "education": [],
    }
    problems = draft.required_missing(empty)
    assert {item["field"] for item in problems} == {
        "header.full_name",
        "experience|projects|education",
    }


def test_content_hash_is_canonical_and_changes_with_content() -> None:
    content = {"b": 2, "a": [1, {"c": "x"}]}
    same = {"a": [1, {"c": "x"}], "b": 2}
    assert draft.content_hash(content) == draft.content_hash(same)
    changed = {"a": [1, {"c": "y"}], "b": 2}
    assert draft.content_hash(content) != draft.content_hash(changed)


def test_diff_between_reports_changed_paths() -> None:
    before = {"summary": {"text": "old"}, "skills": ["a"]}
    after = {"summary": {"text": "new"}, "skills": ["a"]}
    result = draft.diff_between(before, after, "docv_parent")
    assert result["base"] == "document_version"
    assert result["base_document_version_id"] == "docv_parent"
    assert result["items"] == [
        {"path": "summary.text", "change": "changed", "before": "old", "after": "new"}
    ]


def test_review_flags_claim_without_evidence() -> None:
    content = {
        "kind": "cv",
        "header": {"full_name": "Ayu Pratama"},
        "summary": None,
        "skills": [],
        "experience": [
            {
                "id": "exp_1",
                "company": "Acme",
                "title": "Engineer",
                "bullets": [{"id": "b1", "text": "Built payments.", "evidence_ids": []}],
            }
        ],
        "projects": [],
        "education": [],
        "certifications": [],
        "languages": [],
    }
    report = review_rules.review(content, {})
    assert report["verdict"] == "changes_required"
    assert any(item["severity"] == "major" for item in report["findings"])


def test_review_flags_unknown_evidence() -> None:
    content = {
        "kind": "cv",
        "header": {"full_name": "Ayu Pratama"},
        "summary": None,
        "skills": [],
        "experience": [
            {
                "id": "exp_1",
                "company": "Acme",
                "title": "Engineer",
                "bullets": [
                    {"id": "b1", "text": "Built payments.", "evidence_ids": ["ev_missing"]}
                ],
            }
        ],
        "projects": [],
        "education": [],
        "certifications": [],
        "languages": [],
    }
    report = review_rules.review(content, {})
    assert report["verdict"] == "changes_required"
    assert any(item["severity"] == "blocker" for item in report["findings"])


# -- generation --------------------------------------------------------------
def test_generation_requires_eligible(setup_client, csrf, monkeypatch) -> None:
    _confirm(setup_client, csrf)
    items = _matched_jobs(setup_client, csrf, monkeypatch)
    blocked = [item for item in items if item["eligibility"]["status"] == "needs_review"]
    if not blocked:
        blocked = [item for item in items if item["eligibility"]["status"] != "eligible"]
    if not blocked:
        return
    job = blocked[0]["job"]
    created = setup_client.post(
        "/api/applications", headers=csrf, json={"job_id": job["job_id"]}
    ).json()

    response = setup_client.post(
        f"/api/applications/{created['application_id']}/documents",
        headers=csrf,
        json={"kinds": ["cv"], "language": "en"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] in {
        "eligibility_needs_review",
        "eligibility_not_eligible",
    }


def test_generation_is_deterministic_and_uses_profile_facts(
    setup_client, csrf, monkeypatch
) -> None:
    application_id, job = _application(setup_client, csrf, monkeypatch)
    first = _generate(setup_client, csrf, application_id, kinds=("cv",))
    second = _generate(setup_client, csrf, application_id, kinds=("cv",))

    assert [item["kind"] for item in first] == ["cv"]
    by_version = {item["version"]: item for item in second}
    assert set(by_version) == {1, 2}
    detail_one = _detail(setup_client, application_id, by_version[1]["document_version_id"])
    detail_two = _detail(setup_client, application_id, by_version[2]["document_version_id"])
    assert detail_one["content"] == detail_two["content"]
    assert detail_one["content_hash"] == detail_two["content_hash"]

    content = detail_one["content"]
    assert content["kind"] == "cv"
    assert content["target"]["job_id"] == job["job_id"]
    assert content["header"]["full_name"]
    assert content["experience"]
    assert all(
        bullet["evidence_ids"]
        for role in content["experience"]
        for bullet in role["bullets"]
    )
    assert detail_one["diff"]["base"] == "master_cv"
    assert detail_one["pdf_available"] is False
    assert detail_one["exported"] is False

    workspace = setup_client.get(f"/api/applications/{application_id}").json()
    assert sorted(item["version"] for item in workspace["documents"]["cv"]) == [1, 2]
    assert workspace["next_action"]["code"] == "review_documents"
    summary = setup_client.get("/api/applications").json()["items"][0]
    assert summary["document_counts"] == {
        "cv_versions": 2,
        "cover_letter_versions": 0,
        "pending_review": 2,
    }


def test_generate_rejects_duplicate_kinds(setup_client, csrf, monkeypatch) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    response = setup_client.post(
        f"/api/applications/{application_id}/documents",
        headers=csrf,
        json={"kinds": ["cv", "cv"], "language": "en"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_failed"


# -- review and approval -----------------------------------------------------
def test_review_then_approval_is_bound_to_version_and_hash(
    setup_client, csrf, monkeypatch
) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    version = _generate(setup_client, csrf, application_id, kinds=("cv",))[0]

    missing = setup_client.get(
        f"/api/applications/{application_id}/documents/{version['document_version_id']}/findings"
    )
    assert missing.status_code == 404

    before = _approve(
        setup_client, csrf, application_id, version["document_version_id"], "f" * 64
    )
    assert before.status_code == 409
    assert before.json()["error"]["code"] == "approval_hash_mismatch"

    not_reviewed = _approve(
        setup_client, csrf, application_id, version["document_version_id"], version["content_hash"]
    )
    assert not_reviewed.status_code == 409
    assert not_reviewed.json()["error"]["code"] == "review_not_completed"

    reviewed = _review(setup_client, csrf, application_id, version["document_version_id"])
    assert reviewed["review_status"] == "completed"
    assert reviewed["review_verdict"] == "pass"
    assert reviewed["status"] == "in_review"

    findings = setup_client.get(
        f"/api/applications/{application_id}/documents/{version['document_version_id']}/findings"
    )
    assert findings.status_code == 200
    assert findings.json()["verdict"] == "pass"

    approved = _approve(
        setup_client, csrf, application_id, version["document_version_id"], version["content_hash"]
    )
    assert approved.status_code == 201, approved.json()
    assert approved.json()["decision"] == "approved"
    assert approved.json()["document_hash"] == version["content_hash"]

    replay = _approve(
        setup_client, csrf, application_id, version["document_version_id"], version["content_hash"]
    )
    assert replay.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["approval_id"] == approved.json()["approval_id"]

    workspace = setup_client.get(f"/api/applications/{application_id}").json()
    assert workspace["status"] == "approved"
    assert workspace["documents"]["cv"][0]["approved"] is True

    blocked_review = setup_client.post(
        f"/api/applications/{application_id}/documents/{version['document_version_id']}/review",
        headers=csrf,
    )
    assert blocked_review.status_code == 409
    assert blocked_review.json()["error"]["details"][0]["code"] == "version_already_approved"

    blocked_change = _approve(
        setup_client,
        csrf,
        application_id,
        version["document_version_id"],
        version["content_hash"],
        decision="changes_requested",
        note="Tolong ubah summary.",
    )
    assert blocked_change.status_code == 409
    assert blocked_change.json()["error"]["details"][0]["code"] == "version_already_approved"


def test_generation_blocks_outdated_eligibility(setup_client, csrf, monkeypatch, connection) -> None:
    application_id, job = _application(setup_client, csrf, monkeypatch)
    workspace = setup_client.get(f"/api/applications/{application_id}").json()
    connection.execute(
        "UPDATE eligibility_assessment SET status_outdated = 1 "
        "WHERE job_id = ? AND profile_version_id = ?",
        (job["job_id"], workspace["profile_version_id"]),
    )
    response = setup_client.post(
        f"/api/applications/{application_id}/documents",
        headers=csrf,
        json={"kinds": ["cv"], "language": "en"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"][0]["code"] == "assessment_outdated"


def test_revision_creates_new_version_and_never_inherits_approval(
    setup_client, csrf, monkeypatch
) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    version = _generate(setup_client, csrf, application_id, kinds=("cv",))[0]
    _review(setup_client, csrf, application_id, version["document_version_id"])
    approved = _approve(
        setup_client, csrf, application_id, version["document_version_id"], version["content_hash"]
    )
    assert approved.status_code == 201

    revised = setup_client.post(
        f"/api/applications/{application_id}/documents/{version['document_version_id']}/revisions",
        headers=csrf,
        json={
            "base_content_hash": version["content_hash"],
            "edits": [{"path": "summary.text", "value": "Edited summary."}],
            "note": "tighten",
        },
    )
    assert revised.status_code == 201, revised.json()
    new_version = revised.json()
    assert new_version["version"] == 2
    assert new_version["status"] == "draft"
    assert new_version["approved"] is False
    assert new_version["review_status"] == "not_started"
    assert new_version["content_hash"] != version["content_hash"]

    detail = _detail(setup_client, application_id, new_version["document_version_id"])
    assert detail["content"]["summary"]["text"] == "Edited summary."
    assert detail["diff"]["base"] == "document_version"
    assert detail["diff"]["base_document_version_id"] == version["document_version_id"]

    old = _detail(setup_client, application_id, version["document_version_id"])
    assert old["approved"] is True
    assert old["content_hash"] == version["content_hash"]

    stale = setup_client.post(
        f"/api/applications/{application_id}/documents/{version['document_version_id']}/revisions",
        headers=csrf,
        json={
            "base_content_hash": "0" * 64,
            "edits": [{"path": "summary.text", "value": "stale"}],
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"


def test_approval_blocks_missing_required_data(setup_client, csrf, monkeypatch) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    version = _generate(setup_client, csrf, application_id, kinds=("cv",))[0]
    revised = setup_client.post(
        f"/api/applications/{application_id}/documents/{version['document_version_id']}/revisions",
        headers=csrf,
        json={
            "base_content_hash": version["content_hash"],
            "edits": [{"path": "header.full_name", "value": ""}],
        },
    ).json()
    reviewed = _review(setup_client, csrf, application_id, revised["document_version_id"])
    assert reviewed["review_verdict"] == "changes_required"

    response = _approve(
        setup_client, csrf, application_id, revised["document_version_id"], revised["content_hash"]
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    codes = {item["code"] for item in response.json()["error"]["details"]}
    assert "missing_required_field" in codes


def test_cover_letter_is_approvable_when_it_has_a_claim(
    setup_client, csrf, monkeypatch
) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    version = _generate(setup_client, csrf, application_id, kinds=("cover_letter",))[0]
    reviewed = _review(setup_client, csrf, application_id, version["document_version_id"])
    assert reviewed["review_verdict"] == "pass"
    assert reviewed["content"]["kind"] == "cover_letter"
    assert reviewed["content"]["paragraphs"]
    approved = _approve(
        setup_client, csrf, application_id, version["document_version_id"], version["content_hash"]
    )
    assert approved.status_code == 201, approved.json()


def test_approval_detects_content_changed_out_of_band(
    setup_client, csrf, monkeypatch, connection
) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    version = _generate(setup_client, csrf, application_id, kinds=("cv",))[0]
    _review(setup_client, csrf, application_id, version["document_version_id"])
    row = connection.execute(
        "SELECT content_json FROM document_version WHERE document_version_id = ?",
        (version["document_version_id"],),
    ).fetchone()
    content = json.loads(row["content_json"])
    content["header"]["full_name"] = "Someone Else"
    connection.execute(
        "UPDATE document_version SET content_json = ? WHERE document_version_id = ?",
        (json.dumps(content, ensure_ascii=False), version["document_version_id"]),
    )

    response = _approve(
        setup_client, csrf, application_id, version["document_version_id"], version["content_hash"]
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "approval_hash_mismatch"


def test_approved_version_rejects_other_decisions(setup_client, csrf, monkeypatch) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    version = _generate(setup_client, csrf, application_id, kinds=("cv",))[0]
    _review(setup_client, csrf, application_id, version["document_version_id"])
    assert (
        _approve(
            setup_client,
            csrf,
            application_id,
            version["document_version_id"],
            version["content_hash"],
        ).status_code
        == 201
    )
    response = _approve(
        setup_client,
        csrf,
        application_id,
        version["document_version_id"],
        version["content_hash"],
        decision="changes_requested",
        note="Tolong ubah summary.",
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"][0]["code"] == "version_already_approved"


def test_approval_rechecks_eligibility(setup_client, csrf, monkeypatch, connection) -> None:
    application_id, job = _application(setup_client, csrf, monkeypatch)
    version = _generate(setup_client, csrf, application_id, kinds=("cv",))[0]
    _review(setup_client, csrf, application_id, version["document_version_id"])
    workspace = setup_client.get(f"/api/applications/{application_id}").json()

    connection.execute(
        "UPDATE eligibility_assessment SET status = 'needs_review' "
        "WHERE job_id = ? AND profile_version_id = ?",
        (job["job_id"], workspace["profile_version_id"]),
    )
    response = _approve(
        setup_client, csrf, application_id, version["document_version_id"], version["content_hash"]
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "eligibility_needs_review"


def test_regenerate_creates_new_version(setup_client, csrf, monkeypatch) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    version = _generate(setup_client, csrf, application_id, kinds=("cover_letter",))[0]
    response = setup_client.post(
        f"/api/applications/{application_id}/documents/{version['document_version_id']}/regenerate",
        headers=csrf,
        json={"base_content_hash": version["content_hash"], "reason": "user_requested"},
    )
    assert response.status_code == 202, response.json()
    items = setup_client.get(f"/api/applications/{application_id}/documents").json()["items"]
    by_version = {item["version"]: item for item in items}
    assert set(by_version) == {1, 2}
    assert by_version[2]["content_hash"] == version["content_hash"]


def test_document_routes_require_csrf(setup_client, csrf, monkeypatch) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    response = setup_client.post(
        f"/api/applications/{application_id}/documents",
        json={"kinds": ["cv"], "language": "en"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_invalid"


def test_document_list_paginates_and_missing_ids_are_404(
    setup_client, csrf, monkeypatch
) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    _generate(setup_client, csrf, application_id)

    first = setup_client.get(f"/api/applications/{application_id}/documents?limit=1").json()
    assert len(first["items"]) == 1
    assert first["page"]["has_more"] is True
    cursor = first["page"]["next_cursor"]
    second = setup_client.get(
        f"/api/applications/{application_id}/documents?limit=1&cursor={cursor}"
    ).json()
    assert len(second["items"]) == 1
    assert second["items"][0]["document_version_id"] != first["items"][0]["document_version_id"]

    missing = setup_client.get(f"/api/applications/{application_id}/documents/docv_missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_revision_rejects_unknown_path(setup_client, csrf, monkeypatch) -> None:
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    version = _generate(setup_client, csrf, application_id, kinds=("cv",))[0]
    for path in ("header.unknown", "kind", "schema_version", "target"):
        response = setup_client.post(
            f"/api/applications/{application_id}/documents/{version['document_version_id']}/revisions",
            headers=csrf,
            json={
                "base_content_hash": version["content_hash"],
                "edits": [{"path": path, "value": "x"}],
            },
        )
        assert response.status_code == 400, path
        assert response.json()["error"]["code"] == "validation_failed"

    wrong_type = setup_client.post(
        f"/api/applications/{application_id}/documents/{version['document_version_id']}/revisions",
        headers=csrf,
        json={
            "base_content_hash": version["content_hash"],
            "edits": [{"path": "summary", "value": "x"}],
        },
    )
    assert wrong_type.status_code == 400

    evidence_edit = setup_client.post(
        f"/api/applications/{application_id}/documents/{version['document_version_id']}/revisions",
        headers=csrf,
        json={
            "base_content_hash": version["content_hash"],
            "edits": [{"path": "experience.0.bullets.0.evidence_ids", "value": []}],
        },
    )
    assert evidence_edit.status_code == 400


def test_analysis_task_does_not_block_document_generation(
    setup_client, csrf, monkeypatch, connection
) -> None:
    """An unrelated analysis task must not lock the document workflow."""
    application_id, _ = _application(setup_client, csrf, monkeypatch)
    with connection:
        connection.execute(
            "INSERT INTO task (task_id, type, status, application_id, progress_json, "
            "result_json, error_json, created_at, updated_at, finished_at, attempt, "
            "retried_from_task_id) VALUES ('tsk_running_analysis', 'analysis', 'processing', "
            "?, '{}', NULL, NULL, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', NULL, 1, NULL)",
            (application_id,),
        )
    documents = _generate(setup_client, csrf, application_id, kinds=("cv",))
    assert len(documents) == 1
