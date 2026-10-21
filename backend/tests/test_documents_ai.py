"""Phase 3: LLM writer, LLM reviewer, and the bounded rewrite loop.

No network. The provider double below builds a real draft from the profile in the
prompt, so every write reply is schema-valid and every review reply is scripted.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
import jsonschema
from fastapi.testclient import TestClient

from gawe.api.app import build_llm_client, create_app
from gawe.documents import draft
from gawe.llm.providers.base import Call, Completion
from gawe.llm.providers.synthetic import SyntheticExtractProvider
from tests.test_documents import _application, _detail
from tests.conftest import SETUP_CONFIG

REPO_ROOT = Path(__file__).resolve().parents[2]
BLOCK_RE = re.compile(r"<untrusted>\s*(.*?)\s*</untrusted>", re.DOTALL)


class ScriptedProvider:
    """Answers `write` with a real draft, `review` with a queued report.

    `extract` is delegated to the synthetic provider so the setup path still
    produces a confirmed profile without a network call.
    """

    provider_id = "fake"

    def __init__(self, reviews: list[dict], mutate=None) -> None:
        self.reviews = list(reviews)
        self.mutate = mutate
        self.calls: list[Call] = []
        self._extract = SyntheticExtractProvider()

    def complete(self, call: Call) -> Completion:
        self.calls.append(call)
        if call.role == "extract":
            return self._extract.complete(call)
        blocks = BLOCK_RE.findall(call.messages[-1].get("content", ""))
        if call.role == "review":
            report = self.reviews.pop(0) if self.reviews else _pass_report()
            return Completion(text=json.dumps(report), input_tokens=10, output_tokens=10)
        job_payload = json.loads(blocks[0])
        profile = json.loads(blocks[1])
        kind = "cover_letter" if "kind\": \"cover_letter" in json.dumps(blocks[3]) else "cv"
        content = draft.build(kind, profile, job_payload, "en")
        # `missing` is service-computed and not part of the model's schema.
        content.pop("missing", None)
        if self.mutate is not None:
            self.mutate(content)
        return Completion(text=json.dumps(content), input_tokens=10, output_tokens=10)


def _pass_report(score: float = 8.4) -> dict:
    return {
        "verdict": "pass",
        "overall_score": score,
        "dimension_scores": {
            "clarity": score,
            "relevance": score,
            "credibility": score,
            "differentiation": score,
            "professional_quality": score,
        },
        "findings": [],
    }


def _report(score: float, findings: list[dict] | None = None, verdict="changes_required") -> dict:
    report = _pass_report(score)
    report["verdict"] = verdict
    report["findings"] = findings or []
    return report


def _finding(severity="major", quote="Built the billing service.") -> dict:
    return {
        "finding_id": "f_001",
        "severity": severity,
        "category": "relevance",
        "location": {"doc": "cv", "section": "summary", "bullet_id": None},
        "quote": quote,
        "problem": "Ringkasan tidak menyebut requirement utama.",
        "evidence_refs": [],
        "suggested_fix": "Sebut satu bukti yang relevan.",
        "auto_fixable": True,
    }


@pytest.fixture
def ai_root(tmp_path: Path) -> Path:
    """A root directory that carries the real prompt files and schemas."""
    shutil.copytree(REPO_ROOT / "docs" / "phase-00", tmp_path / "docs" / "phase-00")
    (tmp_path / "config.toml").write_text(SETUP_CONFIG, encoding="utf-8")
    return tmp_path


def _client(setup_config, provider, root: Path) -> TestClient:
    """Build an app whose document service sees prompts and a scripted provider."""
    setup_config.root_dir = root
    llm = build_llm_client(setup_config, provider=provider)
    return TestClient(create_app(setup_config, llm_client=llm))


def _generate(client, csrf, application_id: str, kinds=("cv",)) -> dict:
    response = client.post(
        f"/api/applications/{application_id}/documents",
        headers=csrf,
        json={"kinds": list(kinds), "language": "en"},
    )
    assert response.status_code == 202, response.json()
    task = client.get(f"/api/tasks/{response.json()['task_id']}").json()
    assert task["status"] == "completed", task
    return task["result"]


# -- loop behaviour ---------------------------------------------------------
def test_pass_on_first_iteration_creates_one_version(
    setup_config, _clean_database, ai_root, monkeypatch
) -> None:
    provider = ScriptedProvider([_pass_report(8.4)])
    with _client(setup_config, provider, ai_root) as client:
        csrf = {"X-CSRF-Token": client.get("/api/session").json()["csrf_token"]}
        application_id, _ = _application(client, csrf, monkeypatch)
        result = _generate(client, csrf, application_id)

        assert len(result["document_version_ids"]) == 1
        document = result["documents"][0]
        assert document["iteration"] == 1
        assert document["stop_reason"] == "passed"
        assert document["score"] == 8.4
        assert document["passed"] is True
        assert [call.role for call in provider.calls if call.role != "extract"] == [
            "write",
            "review",
        ]


def test_low_score_rewrites_until_threshold(
    setup_config, _clean_database, ai_root, monkeypatch
) -> None:
    provider = ScriptedProvider([_report(6.0, [_finding()]), _report(7.4, [_finding()]), _pass_report(8.2)])
    with _client(setup_config, provider, ai_root) as client:
        csrf = {"X-CSRF-Token": client.get("/api/session").json()["csrf_token"]}
        application_id, _ = _application(client, csrf, monkeypatch)
        result = _generate(client, csrf, application_id)

        document = result["documents"][0]
        assert document["iteration"] == 3
        assert document["stop_reason"] == "passed"
        versions = client.get(f"/api/applications/{application_id}/documents").json()["items"]
        assert [item["version"] for item in versions] == [3, 2, 1]
        detail = _detail(client, application_id, versions[0]["document_version_id"])
        assert detail["parent_document_version_id"] == versions[1]["document_version_id"]


def test_high_score_with_blocker_still_fails(
    setup_config, _clean_database, ai_root, monkeypatch
) -> None:
    blocker = _finding("blocker", "Tanggal 2024-01 tidak ada di profil.")
    provider = ScriptedProvider([_report(9.6, [blocker]), _report(9.7, [blocker])])
    with _client(setup_config, provider, ai_root) as client:
        csrf = {"X-CSRF-Token": client.get("/api/session").json()["csrf_token"]}
        application_id, _ = _application(client, csrf, monkeypatch)
        result = _generate(client, csrf, application_id)

        document = result["documents"][0]
        assert document["passed"] is False
        assert document["stop_reason"] in {"stagnated", "iteration_limit"}


def test_stagnation_stops_the_loop(
    setup_config, _clean_database, ai_root, monkeypatch
) -> None:
    provider = ScriptedProvider([_report(7.0, [_finding()]), _report(7.2, [_finding()])])
    with _client(setup_config, provider, ai_root) as client:
        csrf = {"X-CSRF-Token": client.get("/api/session").json()["csrf_token"]}
        application_id, _ = _application(client, csrf, monkeypatch)
        result = _generate(client, csrf, application_id)

        document = result["documents"][0]
        assert document["iteration"] == 2
        assert document["stop_reason"] == "stagnated"
        assert document["passed"] is False


def test_iteration_budget_is_global_across_versions(
    setup_config, _clean_database, ai_root, monkeypatch
) -> None:
    scores = [5.0, 6.0, 7.0, 7.5, 8.0]
    provider = ScriptedProvider([_report(score, [_finding()]) for score in scores])
    with _client(setup_config, provider, ai_root) as client:
        csrf = {"X-CSRF-Token": client.get("/api/session").json()["csrf_token"]}
        application_id, _ = _application(client, csrf, monkeypatch)
        result = _generate(client, csrf, application_id)

        document = result["documents"][0]
        assert document["iteration"] == 5
        assert document["stop_reason"] == "iteration_limit"
        versions = client.get(f"/api/applications/{application_id}/documents").json()["items"]
        assert len(versions) == 5

        # A sixth rewrite is refused: the counter lives on the chain, not the row.
        latest = versions[0]
        response = client.post(
            f"/api/applications/{application_id}/documents/"
            f"{latest['document_version_id']}/regenerate",
            headers=csrf,
            json={"base_content_hash": latest["content_hash"], "reason": "user_requested"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["details"][0]["code"] == "iteration_limit"


def test_review_unavailable_never_passes(
    setup_config, _clean_database, ai_root, monkeypatch
) -> None:
    provider = ScriptedProvider([])
    provider.reviews = []
    with _client(setup_config, provider, ai_root) as client:
        csrf = {"X-CSRF-Token": client.get("/api/session").json()["csrf_token"]}
        application_id, _ = _application(client, csrf, monkeypatch)
        # A schema-invalid review reply must degrade, not pass.
        provider.reviews = [{"verdict": "pass"}]
        result = _generate(client, csrf, application_id)

        document = result["documents"][0]
        assert document["passed"] is False
        assert document["stop_reason"] == "review_unavailable"


def test_approval_rejects_version_that_did_not_pass(
    setup_config, _clean_database, ai_root, monkeypatch
) -> None:
    provider = ScriptedProvider([_report(7.9, [_finding("minor")])] * 5)
    with _client(setup_config, provider, ai_root) as client:
        csrf = {"X-CSRF-Token": client.get("/api/session").json()["csrf_token"]}
        application_id, _ = _application(client, csrf, monkeypatch)
        result = _generate(client, csrf, application_id)
        version_id = result["document_version_ids"][0]
        detail = _detail(client, application_id, version_id)
        assert detail["findings"]["passed"] is False

        response = client.post(
            f"/api/applications/{application_id}/documents/{version_id}/approval",
            headers=csrf,
            json={
                "decision": "approved",
                "content_hash": detail["content_hash"],
                "note": None,
            },
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "review_not_completed"


def test_writer_metadata_records_provider_and_prompt_version(
    setup_config, _clean_database, ai_root, monkeypatch
) -> None:
    provider = ScriptedProvider([_pass_report()])
    with _client(setup_config, provider, ai_root) as client:
        csrf = {"X-CSRF-Token": client.get("/api/session").json()["csrf_token"]}
        application_id, _ = _application(client, csrf, monkeypatch)
        result = _generate(client, csrf, application_id)
        detail = _detail(client, application_id, result["document_version_ids"][0])
        assert detail["provider"] == "fake"
        assert detail["prompt_version"] == "0.2.0"
        assert detail["findings"]["overall_score"] == 8.4


def test_stored_report_matches_findings_schema(
    setup_config, _clean_database, ai_root, monkeypatch
) -> None:
    provider = ScriptedProvider([_report(6.5, [_finding()]), _pass_report(8.1)])
    schema = json.loads(
        (REPO_ROOT / "docs" / "phase-00" / "contracts" / "findings.schema.json").read_text(
            encoding="utf-8"
        )
    )
    with _client(setup_config, provider, ai_root) as client:
        csrf = {"X-CSRF-Token": client.get("/api/session").json()["csrf_token"]}
        application_id, _ = _application(client, csrf, monkeypatch)
        result = _generate(client, csrf, application_id)
        for version_id in result["document_version_ids"]:
            detail = _detail(client, application_id, version_id)
            jsonschema.validate(detail["findings"], schema)


def test_invalid_write_output_falls_back_to_deterministic_draft(
    setup_config, _clean_database, ai_root, monkeypatch
) -> None:
    provider = ScriptedProvider([_pass_report()])
    provider.mutate = lambda content: content.update({"kind": "not_a_document"})
    with _client(setup_config, provider, ai_root) as client:
        csrf = {"X-CSRF-Token": client.get("/api/session").json()["csrf_token"]}
        application_id, _ = _application(client, csrf, monkeypatch)
        result = _generate(client, csrf, application_id)
        detail = _detail(client, application_id, result["document_version_ids"][0])
        assert detail["content"]["kind"] == "cv"
        assert detail["content"]["header"]["full_name"]
        # The write call happened, its reply was rejected, and the fallback is
        # recorded as unattributed rather than credited to the model.
        assert detail["provider"] is None
        assert detail["prompt_version"] is None


def test_missing_prompts_leave_the_version_unreviewed(
    setup_config, _clean_database, monkeypatch
) -> None:
    provider = ScriptedProvider([_pass_report()])
    with _client(setup_config, provider, Path("does-not-exist")) as client:
        csrf = {"X-CSRF-Token": client.get("/api/session").json()["csrf_token"]}
        application_id, _ = _application(client, csrf, monkeypatch)
        result = _generate(client, csrf, application_id)
        document = result["documents"][0]
        assert document["stop_reason"] == "review_skipped"
        assert document["passed"] is None
        assert not [call for call in provider.calls if call.role != "extract"]
