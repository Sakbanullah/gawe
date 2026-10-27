"""A job whose description yields no mandatory requirement cannot be scored.

The old behaviour was a perfect fit: `_coverage([])` returned 1.0, so a posting
with no readable requirement scored as if every requirement were met. Now
`match/score.score` returns ``None`` and nothing is stored, which the ranking,
the `min_fit_score` filter, and the UI all have to survive.
"""

from __future__ import annotations

import pytest

from gawe.match.score import score
from gawe.ranking.rank import rank


def _check(kind: str, result: str = "met") -> dict:
    return {
        "requirement_id": f"req_{kind}",
        "category": "other",
        "kind": kind,
        "result": result,
        "job_quote": "Kubernetes",
        "profile_ref": "skills",
        "evidence_refs": [],
        "reason": "",
    }


def test_no_mandatory_requirement_is_not_a_perfect_score() -> None:
    assert score([]) is None
    assert score([_check("responsibility")]) is None
    assert score([_check("nice_to_have")]) is None


def test_one_mandatory_requirement_is_scored_as_before() -> None:
    """0.60*1.0 + 0.15*1.0 (no nice-to-have) + 0.25*0.5 = 87.5 -> 88."""
    fit = score([_check("must_have")])
    assert fit is not None
    assert fit["fit_score"] == 88
    assert fit["verdict"] == "strong"


def test_ranking_ignores_an_unscored_eligible_candidate() -> None:
    result = rank(
        [
            {
                "job_id": "job_unscored",
                "eligibility_status": "eligible",
                "fit_score": None,
                "priority_tier": "P2",
            },
            {
                "job_id": "job_scored",
                "eligibility_status": "eligible",
                "fit_score": 80,
                "priority_tier": "P2",
            },
        ]
    )
    assert [item["job_id"] for item in result["sections"]["eligible"]] == ["job_scored"]
    assert result["data_issues"] == [
        {"job_id": "job_unscored", "reason": "missing_fit_score"}
    ]


@pytest.mark.parametrize("eligibility", ["needs_review", "ineligible"])
def test_unscored_non_eligible_candidate_is_not_an_error(eligibility: str) -> None:
    result = rank(
        [
            {
                "job_id": "job_x",
                "eligibility_status": eligibility,
                "fit_score": None,
                "priority_tier": "P3",
            }
        ]
    )
    assert result["counts"][eligibility] == 1
    assert result["data_issues"] == []


# -- the API and the stored rows ---------------------------------------------
PAGE = "https://id.jobstreet.com/backend-engineer-jobs"


def _import_card(client, csrf) -> str:
    """A card import: only a snippet, no readable requirement."""
    from tests.test_assessment import _confirm
    from tests.test_browser_import import _token

    _confirm(client, csrf)
    token = _token(client, csrf)
    response = client.post(
        "/api/import/browser",
        headers=token,
        json={
            "source": "jobstreet",
            "page_url": PAGE,
            "jobs": [
                {
                    "title": "Platform Engineer",
                    "url": "https://id.jobstreet.com/job/554433",
                    "company": "PT Contoh",
                    "location": "Jakarta",
                    "snippet": "Membangun layanan backend Python dan SQL.",
                }
            ],
        },
    )
    assert response.status_code == 200, response.json()
    return response.json()["job_ids"][0]


def test_snippet_only_job_stores_no_fit_and_says_why(
    setup_client, csrf, connection
) -> None:
    job_id = _import_card(setup_client, csrf)

    fit_rows = connection.execute(
        "SELECT COUNT(*) AS total FROM fit_assessment f JOIN job j "
        "ON j.latest_version_id = f.job_posting_version_id WHERE j.job_id = ?",
        (job_id,),
    ).fetchone()["total"]
    assert fit_rows == 0

    detail = setup_client.get(f"/api/matches/{job_id}").json()
    assert detail["eligibility"]["status"] == "needs_review"
    assert detail["fit"] is None
    # The UI needs a reason, not an empty score card.
    assert "snippet_only" in detail["job_detail"]["job"]["completeness"]["missing_fields"]


def test_min_fit_score_filter_survives_a_job_without_a_score(
    setup_client, csrf
) -> None:
    _import_card(setup_client, csrf)

    response = setup_client.get("/api/matches", params={"min_fit_score": 99})
    assert response.status_code == 200, response.json()
    payload = response.json()
    assert all(item["fit"] is None or item["fit"]["fit_score"] >= 99 for item in payload["items"])
    assert payload["counts"]["hidden_by_min_fit_score"] >= 0


def test_min_fit_score_never_hides_a_job_that_has_no_score(
    setup_client, csrf
) -> None:
    """A job with no readable requirement is not "below 99": it is unknown."""
    job_id = _import_card(setup_client, csrf)

    payload = setup_client.get("/api/matches", params={"min_fit_score": 99}).json()
    listed = {item["job"]["job_id"] for item in payload["items"]}
    assert job_id in listed
    assert payload["counts"]["hidden_by_min_fit_score"] == 0

