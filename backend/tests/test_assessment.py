"""Phase 3C: priority tier, requirements, eligibility gate, fit, ranking."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from gawe.eligibility.evaluate import evaluate
from gawe.jobs import requirements as requirement_rules
from gawe.jobs.priority import classify, geo_region, geo_scope, reachable_by_relocation
from gawe.match.score import score
from gawe.profile.store import ProfileStore
from gawe.ranking.rank import RankingError, rank
from gawe.services.assessment_service import (
    DESCRIPTION_MAX_BYTES,
    DESCRIPTION_MAX_CHARS,
    AssessmentService,
    truncate_description,
)
from tests.conftest import extract_profile, latest_profile, upload_cv
from tests.test_discovery import GREENHOUSE, _Fetcher, _create_source, _use

ROOT = Path(__file__).resolve().parents[2]
# The fixture file is the profile content itself; the store wraps it with the
# evidence index it was extracted with.
PROFILE_CONTENT = json.loads(
    (ROOT / "docs" / "phase-00" / "fixtures" / "profiles" / "profile_confirmed.json").read_text(
        encoding="utf-8"
    )
)
PROFILE = {
    "profile_version_id": PROFILE_CONTENT["profile_version_id"],
    "content": PROFILE_CONTENT,
    "evidence_index": PROFILE_CONTENT["evidence_index"],
}
RANKING_CASES = json.loads(
    (ROOT / "docs" / "phase-00" / "fixtures" / "ranking" / "ranking_cases.json").read_text(
        encoding="utf-8"
    )
)


def _job(**overrides) -> dict:
    job = {
        "job_id": "job_1",
        "job_posting_version_id": "jpv_1",
        "company": "Acme",
        "title": "Senior Backend Engineer",
        "location_raw": "Jakarta, Indonesia",
        "work_mode": "onsite",
        "market": "indonesia",
        "description_text": "Build services.",
    }
    job.update(overrides)
    return job


# -- priority tier -----------------------------------------------------------
@pytest.mark.parametrize(
    ("location", "mode", "text", "tier"),
    [
        ("Berlin, Germany", "onsite", "", "P1"),
        ("Berlin, Germany", "hybrid", "", "P1"),  # D15: hybrid counts as onsite
        ("Remote - Worldwide", "remote", "", "P2"),
        ("Remote", "remote", "open to candidates anywhere", "P2"),
        ("Jakarta, Indonesia", "remote", "", "P3"),
        ("Jakarta, Indonesia", "hybrid", "", "P4"),
        ("Jakarta, Indonesia", "onsite", "", "P4"),
        ("Remote", "remote", "", "unclassified"),  # D16: "remote" alone is not P2
        ("Berlin", "onsite", "", "unclassified"),  # no country named
        ("", "remote", "", "unclassified"),
        ("Jakarta, Indonesia", "unknown", "", "unclassified"),
        # A named region outranks the word "anywhere" in the description. Linear
        # writes "You can work from anywhere within those regions", which used to
        # promote a US/Europe-only role to global remote.
        ("Remote, AMER", "remote", "", "unclassified"),
        ("Remote, EMEA", "remote", "", "unclassified"),
        ("North America", "remote", "", "unclassified"),
        ("Europe", "remote", "", "unclassified"),
        ("Remote, London UK", "remote", "", "unclassified"),
        (
            "North America",
            "remote",
            "This role is open to candidates based in North America. "
            "You can work from anywhere within this region.",
            "unclassified",
        ),
        # APAC covers Indonesia, so it stays reachable.
        ("Remote, APAC", "remote", "", "P2"),
        # A region named only in the description still restricts the role.
        (
            "Remote",
            "remote",
            "This role is open to candidates based in the US and Europe.",
            "unclassified",
        ),
    ],
)
def test_priority_tier_classification(location, mode, text, tier) -> None:
    assert classify(location, mode, text)["tier"] == tier


@pytest.mark.parametrize(
    ("location", "text", "expected"),
    [
        ("Remote, Global", "", "worldwide"),
        ("Remote, APAC", "", "worldwide"),
        ("Jakarta, Indonesia", "", "indonesia"),
        ("Remote, AMER", "", "region_locked"),
        ("North America", "", "region_locked"),
        ("Singapore", "", "region_locked"),
        ("San Francisco, CA", "", "region_locked"),
        ("Hybrid (UK)", "", "region_locked"),
        ("Remote", "", "unknown"),
        # Marketing copy says "globally" without restricting the candidate pool.
        ("Remote, Global", "We are a globally distributed team.", "worldwide"),
        ("Remote", "globally distributed team", "unknown"),
        ("Remote", "You can work from anywhere within those regions.", "region_locked"),
    ],
)
def test_geo_scope_reads_the_location_before_the_prose(location, text, expected) -> None:
    assert geo_scope(location, text) == expected


@pytest.mark.parametrize(
    ("location", "title", "expected"),
    [
        # A region in the title is part of the posting, not marketing prose.
        ("Remote, Global", "Support Engineer (EMEA - Weekends)", "region_locked"),
        ("Remote", "Database Support Engineer (EMEA)", "region_locked"),
        # APAC covers Indonesia, so a title naming it stays reachable.
        ("Remote, Global", "Support Engineer (APAC)", "worldwide"),
        ("Remote, Global", "Platform Security Engineer (AMER/APAC)", "worldwide"),
        # A title naming no region decides nothing.
        ("Remote, Global", "Product Engineer", "worldwide"),
    ],
)
def test_geo_scope_reads_a_region_named_in_the_title(location, title, expected) -> None:
    assert geo_scope(location, "", title) == expected


def test_priority_classification_carries_reason_and_confidence() -> None:
    result = classify("Jakarta, Indonesia", "remote")
    assert result["tier"] == "P3"
    assert result["reason"]
    assert result["confidence"] in {"low", "medium", "high"}


# -- requirements ------------------------------------------------------------
def test_requirement_extraction_marks_must_and_nice_with_quotes() -> None:
    found = requirement_rules.extract(
        "Required: 5+ years backend experience. Nice to have: Kubernetes. "
        "You will build payment services."
    )
    by_kind = {item["kind"]: item for item in found}
    assert by_kind["must_have"]["category"] == "experience"
    assert by_kind["must_have"]["constraint"] == {"min_years": 5}
    assert by_kind["nice_to_have"]["category"] == "other"
    assert by_kind["must_have"]["quote"] in (
        "Required: 5+ years backend experience.",
        "Required: 5+ years backend experience",
    )
    assert all(item["requirement_id"].startswith("req_") for item in found)


def test_requirement_extraction_is_stable_and_skips_responsibilities() -> None:
    text = "You will build payment services and review pull requests."
    assert requirement_rules.extract(text) == []
    fallback = requirement_rules.fallback_requirement(text)
    assert fallback["kind"] == "responsibility"
    assert fallback["quote"] == text


# -- requirement sections, benefits, and EEO --------------------------------
def test_benefit_section_never_becomes_a_requirement() -> None:
    text = (
        "What you'll do You will build payment services. "
        "What we offer Competitive salary and equity. Health insurance and dental. "
        "5 weeks paid vacation, plus local statutory holidays."
    )
    assert requirement_rules.extract(text) == []


def test_eeo_statement_is_excluded_and_keeps_the_real_requirement() -> None:
    text = (
        "Required: 3+ years Python. Acme is an equal opportunity employer and all "
        "qualified applicants will receive consideration."
    )
    found = requirement_rules.extract(text)
    assert [item["kind"] for item in found] == ["must_have"]
    assert "equal opportunity" not in found[0]["text"]


def test_benefit_prose_without_a_heading_is_not_a_nice_to_have() -> None:
    found = requirement_rules.extract(
        "Nice to have: Kubernetes. We also offer competitive salary and equity."
    )
    assert [item["text"] for item in found] == ["Kubernetes."]


def test_requirement_section_item_without_a_cue_word_is_a_gate() -> None:
    found = requirement_rules.extract("Requirements: Kubernetes. Nice to have: Terraform.")
    by_kind = {item["kind"]: item["text"] for item in found}
    assert by_kind == {"must_have": "Kubernetes.", "nice_to_have": "Terraform."}


def test_responsibility_sentence_with_a_strong_cue_is_not_a_gate() -> None:
    text = "You'll work across sales and support teams and bring strong account leadership."
    assert requirement_rules.extract(text) == []


def test_ambiguous_skill_sentence_stays_a_skill_not_a_years_gate() -> None:
    found = requirement_rules.extract(
        "Requirements: Comfortable working with a high degree of ownership."
    )
    assert found and found[0]["category"] == "other"
    assert found[0]["kind"] == "must_have"
    assert found[0]["constraint"] is None


# -- eligibility -------------------------------------------------------------
def test_missing_must_have_skill_is_ineligible() -> None:
    """D25: the only blocking category."""
    job = _job(description_text="Required: Kubernetes.")
    result = evaluate(requirement_rules.extract(job["description_text"]), PROFILE, job)
    assert result["status"] == "ineligible"
    assert result["checks"][0]["category"] == "other"
    assert result["checks"][0]["result"] == "not_met"
    assert result["reason_summary"]


def test_listed_skill_is_eligible() -> None:
    job = _job(description_text="Required: Python.")
    result = evaluate(requirement_rules.extract(job["description_text"]), PROFILE, job)
    assert result["status"] == "eligible"
    assert result["checks"][0]["result"] == "met"


def test_experience_shortfall_never_blocks_eligibility() -> None:
    """D25: the user judges seniority; the gate only reports it."""
    job = _job(description_text="Required: 12+ years backend experience.")
    result = evaluate(requirement_rules.extract(job["description_text"]), PROFILE, job)
    assert result["status"] != "ineligible"
    check = result["checks"][0]
    assert check["category"] == "experience"
    assert check["result"] == "unknown"


def test_eligible_job_with_met_experience() -> None:
    job = _job(description_text="Required: 5+ years backend experience.")
    result = evaluate(requirement_rules.extract(job["description_text"]), PROFILE, job)
    assert result["status"] == "eligible"
    assert result["checks"][0]["result"] == "met"
    assert result["checks"][0]["job_quote"]
    assert result["checks"][0]["evidence_refs"]


def test_missing_work_authorization_is_a_check_not_a_blocker() -> None:
    """D25: a credential gap is recorded and left to the user."""
    job = _job(
        location_raw="Berlin, Germany",
        market="global",
        description_text="Must be authorized to work in the EU.",
    )
    result = evaluate(requirement_rules.extract(job["description_text"]), PROFILE, job)
    assert result["status"] != "ineligible"
    check = result["checks"][0]
    assert check["category"] == "work_authorization"
    assert check["result"] == "not_met"
    assert "EU" in check["job_quote"]


def test_unknown_requirement_no_longer_blocks_eligibility() -> None:
    """D25: only a missing skill blocks; a credential is reported, not gated."""
    job = _job(description_text="Required: fluency in Japanese language.")
    result = evaluate(requirement_rules.extract(job["description_text"]), PROFILE, job)
    assert result["status"] == "eligible"


def test_job_without_must_have_requirements_is_needs_review() -> None:
    job = _job(description_text="You will build payment services.")
    requirements = [requirement_rules.fallback_requirement(job["description_text"])]
    assert evaluate(requirements, PROFILE, job)["status"] == "needs_review"


def test_profile_without_confirmed_authorization_needs_review() -> None:
    profile = {**PROFILE, "content": {**PROFILE["content"], "work_authorization": []}}
    job = _job(
        location_raw="Berlin, Germany",
        market="global",
        description_text="Must be authorized to work in the EU.",
    )
    result = evaluate(requirement_rules.extract(job["description_text"]), profile, job)
    assert result["status"] == "needs_review"


def test_region_locked_posting_is_never_eligible() -> None:
    """A role open only to the US and Europe cannot be taken from Indonesia."""
    job = _job(
        location_raw="North America",
        market="global",
        work_mode="remote",
        description_text=(
            "Required: 5+ years backend experience. This role is open to candidates "
            "based in North America. You can work from anywhere within this region."
        ),
    )
    result = evaluate(requirement_rules.extract(job["description_text"]), PROFILE, job)
    assert result["status"] == "needs_review"
    assert result["geo_scope"] == "region_locked"
    assert "region" in result["reason_summary"]


def test_worldwide_posting_can_still_be_eligible() -> None:
    job = _job(
        location_raw="Remote, Global",
        market="global",
        work_mode="remote",
        description_text="Required: 5+ years backend experience.",
    )
    result = evaluate(requirement_rules.extract(job["description_text"]), PROFILE, job)
    assert result["status"] == "eligible"
    assert result["geo_scope"] == "worldwide"


def test_geo_scope_never_enters_the_fit_score() -> None:
    """Scope is a fact about the posting, not a requirement; fit must not see it."""
    job = _job(
        location_raw="Remote, AMER",
        market="global",
        work_mode="remote",
        description_text="Required: 5+ years backend experience.",
    )
    result = evaluate(requirement_rules.extract(job["description_text"]), PROFILE, job)
    assert all(check["category"] != "location" for check in result["checks"])


@pytest.mark.parametrize(
    ("location", "title", "expected"),
    [
        ("Jakarta, Indonesia", "", "indonesia"),
        # Southeast Asia wins over APAC: narrowest region first.
        ("Singapore", "Customer Success Manager, APAC", "sea"),
        ("Remote, APAC", "Software Engineer", "apac"),
        ("Australia", "Product Support Specialist, APAC", "oceania"),
        ("Remote, AMER", "", "amer"),
        ("Europe", "", "emea"),
        # Nothing named, nothing reported.
        ("Remote", "Product Engineer", None),
        (None, None, None),
    ],
)
def test_geo_region_reports_the_narrowest_named_region(location, title, expected) -> None:
    assert geo_region(location, title) == expected


@pytest.mark.parametrize(
    ("location", "title", "expected"),
    [
        # ASEAN and Australia/New Zealand: a candidate could move there.
        ("Singapore", "", True),
        ("Australia", "", True),
        # APAC is too broad to call reachable: it also covers India and Japan,
        # and a location naming it is `worldwide`, so this branch never runs.
        ("Remote, APAC", "Support Engineer (APAC)", False),
        # The Americas and EMEA need a work permit, which is a different question.
        ("Remote, AMER", "", False),
        ("Remote, EMEA", "", False),
        ("North America", "", False),
        ("Remote", "", False),
    ],
)
def test_relocation_reachability_stops_at_a_permit(location, title, expected) -> None:
    assert reachable_by_relocation(location, title) is expected


def test_region_locked_posting_names_relocation_as_the_open_question() -> None:
    """A willing candidate still is not eligible without employer confirmation."""
    job = _job(
        location_raw="Singapore",
        market="unknown",
        work_mode="remote",
        description_text="Required: 5+ years backend experience.",
    )
    profile = copy.deepcopy(PROFILE)
    profile["content"]["work_preferences"]["relocation"] = "conditional"
    result = evaluate(requirement_rules.extract(job["description_text"]), profile, job)
    assert result["status"] == "needs_review"
    assert "relokasi" in result["reason_summary"]


def test_region_locked_posting_without_relocation_stays_generic() -> None:
    job = _job(
        location_raw="Singapore",
        market="unknown",
        work_mode="remote",
        description_text="Required: 5+ years backend experience.",
    )
    profile = copy.deepcopy(PROFILE)
    profile["content"]["work_preferences"]["relocation"] = "no"
    result = evaluate(requirement_rules.extract(job["description_text"]), profile, job)
    assert result["status"] == "needs_review"
    assert "relokasi" not in result["reason_summary"]


# -- fit ---------------------------------------------------------------------
def test_fit_formula_and_verdict() -> None:
    checks = [
        {"requirement_id": "r1", "kind": "must_have", "result": "met", "reason": "", "evidence_refs": ["ev_1"]},
        {"requirement_id": "r2", "kind": "nice_to_have", "result": "unknown", "reason": "gap", "evidence_refs": []},
    ]
    fit = score(checks)
    # 100 * (0.60*1.0 + 0.15*0.0 + 0.25*0.5) = 72.5 -> 73
    assert fit["fit_score"] == 73
    assert fit["verdict"] == "moderate"
    assert [item["name"] for item in fit["components"]] == [
        "must_coverage",
        "nice_coverage",
        "experience_fit",
    ]
    assert fit["gaps"][0]["requirement_id"] == "r2"


def test_fit_is_weak_when_must_coverage_below_half() -> None:
    checks = [
        {"requirement_id": "r1", "kind": "must_have", "result": "unknown", "reason": "", "evidence_refs": []},
        {"requirement_id": "r2", "kind": "must_have", "result": "met", "reason": "", "evidence_refs": ["ev_1"]},
        {"requirement_id": "r3", "kind": "must_have", "result": "met", "reason": "", "evidence_refs": ["ev_1"]},
    ]
    fit = score(checks)
    assert fit["components"][0]["value"] == 0.6667
    assert fit["verdict"] in {"weak", "moderate"}


# -- ranking -----------------------------------------------------------------
@pytest.mark.parametrize("case", RANKING_CASES["cases"], ids=lambda case: case["case_id"])
def test_ranking_fixture_cases(case) -> None:
    result = rank(case["candidates"], case["tie_window"])
    assert [item["job_id"] for item in result["sections"]["eligible"]] == case[
        "expected_eligible_order"
    ]


def test_ranking_rejects_fit_score_on_needs_review() -> None:
    with pytest.raises(RankingError):
        rank(
            [
                {
                    "job_id": "job_x",
                    "eligibility_status": "needs_review",
                    "fit_score": 90,
                    "priority_tier": "P2",
                }
            ]
        )


def test_ranking_rejects_out_of_range_tie_window() -> None:
    with pytest.raises(RankingError):
        rank([], tie_window=RANKING_CASES["tie_window_max"] + 1)


def test_tier_change_does_not_change_fit_score() -> None:
    candidate = {
        "job_id": "job_a",
        "eligibility_status": "eligible",
        "fit_score": 80,
        "priority_tier": "P2",
        "posted_at": "2026-10-01T00:00:00Z",
    }
    other = {**candidate, "job_id": "job_b", "priority_tier": "P1"}
    first = rank([candidate, other])
    swapped = rank([candidate, {**other, "priority_tier": "P4"}])
    assert first["sections"]["eligible"][0]["fit_score"] == 80
    assert swapped["sections"]["eligible"][0]["fit_score"] == 80
    assert first["sections"]["eligible"][0]["job_id"] == "job_b"
    assert swapped["sections"]["eligible"][0]["job_id"] == "job_a"


# -- API ---------------------------------------------------------------------
def _confirm(client, csrf) -> dict:
    upload_cv(client, csrf)
    extract_profile(client, csrf)
    profile = latest_profile(client)
    response = client.post(
        f"/api/setup/profiles/{profile['profile_version_id']}/confirm", headers=csrf, json={}
    )
    assert response.status_code == 200, response.json()
    return profile


def _run(client, csrf, source_id: str) -> dict:
    response = client.post(
        "/api/discovery/runs", headers=csrf, json={"source_ids": [source_id]}
    )
    assert response.status_code == 202, response.json()
    return response.json()


def test_discovery_run_assesses_jobs_and_exposes_matches(
    setup_client, csrf, monkeypatch, connection
) -> None:
    profile = _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, company="Acme", board="acme")
    _use(setup_client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)
    run = _run(setup_client, csrf, source["source_id"])

    detail = setup_client.get(f"/api/discovery/runs/{run['run_id']}").json()
    assert detail["counts"]["eligible"] + detail["counts"]["needs_review"] + detail["counts"]["ineligible"] == 2

    matches = setup_client.get("/api/matches").json()
    assert matches["page"]["has_more"] is False
    assert matches["ranking"]["sort"] == "ranking"
    assert matches["ranking"]["primary"] == "fit_score_desc"
    assert matches["ranking"]["ranking_run_id"]
    assert len(matches["items"]) == 2
    assert all(item["profile_version_id"] == profile["profile_version_id"] for item in matches["items"])

    eligible = [item for item in matches["items"] if item["eligibility"]["status"] == "eligible"]
    assert eligible, matches["items"]
    assert all(item["fit"] is not None for item in eligible)
    assert all(item["job"]["priority_tier"] for item in matches["items"])

    # Fit exists only for eligible jobs.
    fit_rows = connection.execute("SELECT job_id FROM fit_assessment").fetchall()
    eligible_ids = {item["job"]["job_id"] for item in eligible}
    assert {row["job_id"] for row in fit_rows} == eligible_ids
    non_eligible = [
        row
        for row in connection.execute(
            "SELECT e.job_id FROM eligibility_assessment e LEFT JOIN fit_assessment f "
            "ON f.job_id = e.job_id WHERE e.status <> 'eligible'"
        ).fetchall()
        if row["job_id"]
    ]
    assert all(row["job_id"] not in eligible_ids for row in non_eligible)

    scores = [item["fit"]["fit_score"] for item in matches["items"] if item["fit"]]
    assert scores == sorted(scores, reverse=True)


def test_matches_filters_do_not_change_stored_scores(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, company="Acme", board="acme")
    _use(setup_client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)
    _run(setup_client, csrf, source["source_id"])

    before = connection.execute(
        "SELECT job_id, fit_score FROM fit_assessment ORDER BY job_id"
    ).fetchall()
    default = setup_client.get("/api/matches").json()

    filtered = setup_client.get("/api/matches", params={"min_fit_score": 99}).json()
    assert filtered["counts"]["hidden_by_min_fit_score"] >= 0
    assert all(item["fit"] is None or item["fit"]["fit_score"] >= 99 for item in filtered["items"])

    by_tier = setup_client.get("/api/matches", params={"sort": "priority_tier"}).json()
    assert by_tier["ranking"]["sort"] == "priority_tier"
    assert by_tier["ranking"]["primary"] == "fit_score_desc"
    assert {item["job"]["job_id"] for item in by_tier["items"]} == {
        item["job"]["job_id"] for item in default["items"]
    }

    after = connection.execute(
        "SELECT job_id, fit_score FROM fit_assessment ORDER BY job_id"
    ).fetchall()
    assert before == after


def test_match_detail_separates_eligibility_and_fit(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, company="Acme", board="acme")
    _use(setup_client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)
    _run(setup_client, csrf, source["source_id"])

    items = setup_client.get("/api/matches").json()["items"]
    for item in items:
        detail = setup_client.get(f"/api/matches/{item['job']['job_id']}").json()
        assert detail["eligibility"]["status"] == item["eligibility"]["status"]
        assert detail["job_detail"]["description_text"]
        if detail["eligibility"]["status"] == "eligible":
            assert detail["fit"]["fit_score"] == item["fit"]["fit_score"]
            assert detail["recommendation"] in {"apply_now", "consider", "stretch"}
        else:
            assert detail["fit"] is None
            assert detail["recommendation"] == detail["eligibility"]["status"]


def test_match_detail_unknown_job_is_404(setup_client, csrf) -> None:
    _confirm(setup_client, csrf)
    response = setup_client.get("/api/matches/job_missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_matches_requires_confirmed_profile(setup_client, csrf) -> None:
    response = setup_client.get("/api/matches")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "profile_not_confirmed"


def test_overview_counts_come_from_assessments(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, company="Acme", board="acme")
    _use(setup_client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)
    _run(setup_client, csrf, source["source_id"])

    matches = setup_client.get("/api/matches").json()
    overview = setup_client.get("/api/overview").json()
    assert overview["counts"]["eligible"] == matches["counts"]["eligible"]
    assert overview["counts"]["needs_review"] == matches["counts"]["needs_review"]
    assert overview["counts"]["ineligible"] == matches["counts"]["ineligible"]


def test_reassessment_is_idempotent(setup_client, csrf, monkeypatch, connection) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, company="Acme", board="acme")
    _use(setup_client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)
    _run(setup_client, csrf, source["source_id"])

    before = setup_client.get("/api/matches").json()
    service = AssessmentService(connection, ProfileStore(connection))
    service.assess_pending()
    service.recompute_ranking()
    after = setup_client.get("/api/matches").json()

    assert [item["job"]["job_id"] for item in after["items"]] == [
        item["job"]["job_id"] for item in before["items"]
    ]
    assert [item["fit"] for item in after["items"]] == [item["fit"] for item in before["items"]]
    assert connection.execute(
        "SELECT COUNT(*) AS total FROM eligibility_assessment"
    ).fetchone()["total"] == len(after["items"])


def test_two_jobs_sharing_requirement_text_keep_their_own_rows(
    setup_client, csrf, monkeypatch, connection
) -> None:
    """requirement_id hashes category and text, so two jobs share one id.

    The primary key used to be requirement_id alone, so the second job's row
    was folded into the first job's version and its detail lost the requirement.
    """
    _confirm(setup_client, csrf)
    requirement = "5+ years backend experience"
    board = json.dumps(
        {
            "jobs": [
                {
                    "id": 2001,
                    "title": "Backend Engineer",
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/2001",
                    "location": {"name": "Remote - Worldwide"},
                    "content": f"<p>Requirements:</p><ul><li>{requirement}</li></ul>",
                },
                {
                    "id": 2002,
                    "title": "Data Engineer",
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/2002",
                    "location": {"name": "Remote - Worldwide"},
                    "content": f"<p>Requirements:</p><ul><li>{requirement}</li></ul>",
                },
            ]
        }
    )
    source = _create_source(setup_client, csrf, monkeypatch, company="Acme", board="acme")
    _use(setup_client, _Fetcher({"boards-api": board}), monkeypatch)
    _run(setup_client, csrf, source["source_id"])

    rows = connection.execute(
        "SELECT job_posting_version_id, COUNT(*) AS total FROM job_requirement "
        "GROUP BY job_posting_version_id"
    ).fetchall()
    assert len(rows) == 2, rows
    assert all(row["total"] == 1 for row in rows), rows

    for item in setup_client.get("/api/matches").json()["items"]:
        detail = setup_client.get(f"/api/matches/{item['job']['job_id']}").json()
        assert detail["job_detail"]["requirements"], item["job"]["job_id"]


# -- 3D contract gaps --------------------------------------------------------
def test_matches_hidden_count_and_search_run_in_sql(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, company="Acme", board="acme")
    _use(setup_client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)
    _run(setup_client, csrf, source["source_id"])

    full = setup_client.get("/api/matches").json()
    below = [
        item
        for item in full["items"]
        if item["fit"] is not None and item["fit"]["fit_score"] < 99
    ]
    filtered = setup_client.get("/api/matches", params={"min_fit_score": 99}).json()
    assert filtered["counts"]["hidden_by_min_fit_score"] == len(below)
    assert len(filtered["items"]) == len(full["items"]) - len(below)

    title = full["items"][0]["job"]["title"].split()[0]
    found = setup_client.get("/api/matches", params={"q": title}).json()
    assert all(
        title.lower()
        in " ".join(
            [
                item["job"]["title"],
                item["job"]["company"],
                (item["job"]["location"] or {}).get("raw") or "",
            ]
        ).lower()
        for item in found["items"]
    )
    assert found["items"], found

    by_posted = setup_client.get("/api/matches", params={"sort": "posted_at_desc"}).json()
    epochs = [
        row["posted_at_epoch"]
        for row in connection.execute(
            "SELECT posted_at_epoch FROM job WHERE duplicate_of IS NULL ORDER BY job_id"
        ).fetchall()
    ]
    assert by_posted["ranking"]["sort"] == "posted_at_desc"
    assert epochs and all(isinstance(value, int) for value in epochs)


def test_matches_cursor_pages_without_offset(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, company="Acme", board="acme")
    _use(setup_client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)
    _run(setup_client, csrf, source["source_id"])

    first = setup_client.get("/api/matches", params={"limit": 1}).json()
    assert len(first["items"]) == 1
    assert first["page"]["has_more"] is True
    cursor = first["page"]["next_cursor"]
    assert cursor

    second = setup_client.get("/api/matches", params={"limit": 1, "cursor": cursor}).json()
    assert len(second["items"]) == 1
    assert second["page"]["has_more"] is False
    assert second["page"]["next_cursor"] is None
    assert second["items"][0]["job"]["job_id"] != first["items"][0]["job"]["job_id"]

    full = setup_client.get("/api/matches").json()
    assert [item["job"]["job_id"] for item in full["items"]] == [
        first["items"][0]["job"]["job_id"],
        second["items"][0]["job"]["job_id"],
    ]


def test_matches_rejects_invalid_or_foreign_cursor(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, company="Acme", board="acme")
    _use(setup_client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)
    _run(setup_client, csrf, source["source_id"])

    bad = setup_client.get("/api/matches", params={"cursor": "not-a-cursor"})
    assert bad.status_code == 400
    assert bad.json()["error"]["details"][0]["field"] == "cursor"

    cursor = setup_client.get("/api/matches", params={"limit": 1}).json()["page"]["next_cursor"]
    foreign = setup_client.get(
        "/api/matches", params={"limit": 1, "cursor": cursor, "sort": "fit_score_desc"}
    )
    assert foreign.status_code == 400
    assert foreign.json()["error"]["details"][0]["field"] == "cursor"


def test_description_truncation_respects_contract_limits() -> None:
    text, truncated = truncate_description("short")
    assert (text, truncated) == ("short", False)

    long_ascii = "a" * (DESCRIPTION_MAX_BYTES + 10)
    text, truncated = truncate_description(long_ascii)
    assert truncated is True
    assert len(text) <= DESCRIPTION_MAX_CHARS
    assert len(text.encode("utf-8")) <= DESCRIPTION_MAX_BYTES

    multibyte = "😀" * DESCRIPTION_MAX_CHARS
    text, truncated = truncate_description(multibyte)
    assert truncated is True
    assert len(text.encode("utf-8")) <= DESCRIPTION_MAX_BYTES
    assert not text.endswith("\ufffd")


def test_match_detail_matches_job_detail_contract(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, company="Acme", board="acme")
    _use(setup_client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)
    _run(setup_client, csrf, source["source_id"])

    item = setup_client.get("/api/matches").json()["items"][0]
    detail = setup_client.get(f"/api/matches/{item['job']['job_id']}").json()
    assert detail["job_detail"]["job"]["job_id"] == item["job"]["job_id"]
    assert detail["job_detail"]["description_truncated"] is False
    assert isinstance(detail["job_detail"]["requirements"], list)
    assert detail["job_detail"]["source"]["source_kind"] == "registry"
    assert detail["job_detail"]["source"]["source_id"] == item["job"]["source_id"]
    assert detail["eligibility"]["assessment_id"]
    assert detail["application_id"] is None


def test_tier_override_is_stored_and_leaves_fit_alone(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, company="Acme", board="acme")
    _use(setup_client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)
    _run(setup_client, csrf, source["source_id"])

    item = setup_client.get("/api/matches").json()["items"][0]
    job_id = item["job"]["job_id"]
    before_fit = item["fit"]
    ranking_before = connection.execute(
        "SELECT ranking_run_id FROM ranking_run ORDER BY computed_at DESC LIMIT 1"
    ).fetchone()["ranking_run_id"]

    response = setup_client.patch(
        f"/api/matches/{job_id}/tier", headers=csrf, json={"tier": "P1", "reason": "Relokasi"}
    )
    assert response.status_code == 200, response.json()
    assert response.json()["job"]["priority_tier"] == "P1"
    assert response.json()["fit"] == before_fit

    stored = connection.execute(
        "SELECT priority_tier_override FROM job WHERE job_id = ?", (job_id,)
    ).fetchone()
    assert stored["priority_tier_override"] == "P1"
    assert connection.execute(
        "SELECT ranking_run_id FROM ranking_run ORDER BY computed_at DESC LIMIT 1"
    ).fetchone()["ranking_run_id"] == ranking_before

    listed = setup_client.get("/api/matches", params={"tier": "P1"}).json()
    assert job_id in {row["job"]["job_id"] for row in listed["items"]}

    cleared = setup_client.patch(
        f"/api/matches/{job_id}/tier", headers=csrf, json={"tier": None, "reason": None}
    )
    assert cleared.status_code == 200, cleared.json()
    assert cleared.json()["job"]["priority_tier"] == item["job"]["priority_tier"]
    assert connection.execute(
        "SELECT priority_tier_override FROM job WHERE job_id = ?", (job_id,)
    ).fetchone()["priority_tier_override"] is None


def test_tier_override_validation(setup_client, csrf, monkeypatch) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, company="Acme", board="acme")
    _use(setup_client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)
    _run(setup_client, csrf, source["source_id"])
    job_id = setup_client.get("/api/matches").json()["items"][0]["job"]["job_id"]

    unknown_tier = setup_client.patch(
        f"/api/matches/{job_id}/tier", headers=csrf, json={"tier": "P9", "reason": "x"}
    )
    assert unknown_tier.status_code == 400
    assert unknown_tier.json()["error"]["details"][0]["field"] == "tier"

    missing_reason = setup_client.patch(
        f"/api/matches/{job_id}/tier", headers=csrf, json={"tier": "P2", "reason": "  "}
    )
    assert missing_reason.status_code == 400
    assert missing_reason.json()["error"]["details"][0]["field"] == "reason"

    no_csrf = setup_client.patch(f"/api/matches/{job_id}/tier", json={"tier": "P2", "reason": "x"})
    assert no_csrf.status_code == 403

    missing_job = setup_client.patch(
        "/api/matches/job_missing/tier", headers=csrf, json={"tier": "P2", "reason": "x"}
    )
    assert missing_job.status_code == 404


def test_assessment_failure_is_visible_on_run(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    source = _create_source(setup_client, csrf, monkeypatch, company="Acme", board="acme")
    _use(setup_client, _Fetcher({"boards-api": GREENHOUSE}), monkeypatch)

    def _boom(self):
        raise RuntimeError("assessment exploded")

    monkeypatch.setattr(AssessmentService, "assess_pending", _boom)
    run = _run(setup_client, csrf, source["source_id"])

    detail = setup_client.get(f"/api/discovery/runs/{run['run_id']}").json()
    assert detail["status"] == "partial"
    assert detail["error"]["code"] == "assessment_failed"
    assert detail["counts"]["fetched"] == 2
    assert {item["status"] for item in detail["sources"]} == {"completed"}

    task = setup_client.get(f"/api/tasks/{run['task_id']}").json()
    assert task["status"] == "partial"
    assert task["error"]["code"] == "assessment_failed"
