"""Fit-first ranking with tier as a tie-breaker inside a band.

Implements docs/phase-00/contracts/ranking.md §3. The band is measured from the
highest score in the band, so scores cannot chain into an ever-widening group.
"""

from __future__ import annotations

TIER_RANK = {"P1": 1, "P2": 2, "P3": 3, "P4": 4, "unclassified": 5}
DEFAULT_TIE_WINDOW = 0
MAX_TIE_WINDOW = 20
PRIMARY = "fit_score_desc"
TIE_BREAKER = ["priority_tier", "posted_at_desc", "job_id"]


class RankingError(ValueError):
    """Candidate list violates a documented ranking invariant."""


def _known_tier(value: object) -> str:
    return value if value in TIER_RANK else "unclassified"


def _tier_issues(candidates: list[dict]) -> list[dict]:
    """One entry per candidate whose tier is outside the scale."""
    return [
        {
            "job_id": item["job_id"],
            "reason": "unknown_priority_tier",
            "value": item.get("priority_tier"),
        }
        for item in candidates
        if item.get("priority_tier") not in TIER_RANK
    ]


def _score_issues(candidates: list[dict]) -> list[dict]:
    """Eligible candidates with no stored score; they are left out of the order."""
    return [
        {"job_id": item["job_id"], "reason": "missing_fit_score"}
        for item in candidates
        if item["eligibility_status"] == "eligible" and not isinstance(item.get("fit_score"), int)
    ]


def rank(candidates: list[dict], tie_window: int = DEFAULT_TIE_WINDOW) -> dict:
    """Return ordered ``sections`` plus ``counts``; never scores non-eligible jobs."""
    if not 0 <= tie_window <= MAX_TIE_WINDOW:
        raise RankingError("tie_window must be between 0 and 20")
    # A missing score and an outside-scale tier are stored data problems, not a
    # broken run. Both used to raise, so one row stopped every other job from
    # being ranked. They are reported in ``data_issues`` and the rest sorts.
    issues = _tier_issues(candidates) + _score_issues(candidates)
    _validate(candidates, issues)
    items = [
        {**item, "priority_tier": _known_tier(item.get("priority_tier"))}
        for item in candidates
        if not (
            item["eligibility_status"] == "eligible"
            and not isinstance(item.get("fit_score"), int)
        )
    ]

    eligible = sorted(
        (item for item in items if item["eligibility_status"] == "eligible"),
        key=lambda item: (-item["fit_score"], item["job_id"]),
    )
    ordered: list[dict] = []
    band_id = 0
    index = 0
    while index < len(eligible):
        band_top = eligible[index]["fit_score"]
        band: list[dict] = []
        while (
            index < len(eligible)
            and band_top - eligible[index]["fit_score"] <= tie_window
        ):
            band.append(eligible[index])
            index += 1
        band.sort(key=lambda item: item.get("posted_at") or "", reverse=True)
        band.sort(key=lambda item: TIER_RANK[item["priority_tier"]])
        band_id += 1
        for item in band:
            ordered.append({**item, "band_id": band_id})

    needs_review = _non_eligible(items, "needs_review")
    ineligible = _non_eligible(items, "ineligible")
    return {
        "tie_window": tie_window,
        "primary": PRIMARY,
        "tie_breaker": list(TIE_BREAKER),
        "sections": {
            "eligible": [
                {
                    "rank": position,
                    "job_id": item["job_id"],
                    "fit_score": item["fit_score"],
                    "priority_tier": item["priority_tier"],
                    "posted_at": item.get("posted_at"),
                    "band_id": item["band_id"],
                }
                for position, item in enumerate(ordered, start=1)
            ],
            "needs_review": needs_review,
            "ineligible": ineligible,
        },
        "counts": {
            "eligible": len(ordered),
            "needs_review": len(needs_review),
            "ineligible": len(ineligible),
        },
        # Rows whose score or tier is stored badly. They are listed here and the
        # run is still valid.
        "data_issues": issues,
    }


def _validate(candidates: list[dict], issues: list[dict]) -> None:
    """Reject identity faults only; a per-row data issue is reported, not raised."""
    unscored = {issue["job_id"] for issue in issues if issue["reason"] == "missing_fit_score"}
    seen: set[str] = set()
    for item in candidates:
        status = item.get("eligibility_status")
        if status not in {"eligible", "needs_review", "ineligible"}:
            raise RankingError(f"unknown eligibility_status: {status!r}")
        if item["job_id"] in seen:
            raise RankingError(f"duplicate candidate: {item['job_id']}")
        seen.add(item["job_id"])
        score = item.get("fit_score")
        if status == "eligible" and not isinstance(score, int) and item["job_id"] not in unscored:
            raise RankingError(f"eligible candidate without fit_score: {item['job_id']}")
        if status != "eligible" and score is not None:
            raise RankingError(f"fit_score on non-eligible candidate: {item['job_id']}")


def _non_eligible(candidates: list[dict], status: str) -> list[dict]:
    items = [item for item in candidates if item["eligibility_status"] == status]
    items.sort(key=lambda item: item["job_id"])
    return [
        {
            "job_id": item["job_id"],
            "reason_summary": item.get("reason_summary"),
            "fit_score": None,
        }
        for item in items
    ]
