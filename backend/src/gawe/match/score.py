"""Fit score for eligible jobs only (ELIGIBILITY-AND-SCORING.md §4).

    fit_score = round(100 * (0.60*must_coverage + 0.15*nice_coverage + 0.25*experience_fit))

Weights and thresholds are the documented defaults and are not calibrated yet.
``experience_fit`` is the documented fallback 0.5 because no model judgment is
used in this milestone; that default is still `OPEN` in the domain document.
"""

from __future__ import annotations

import math

WEIGHTS = {"must_coverage": 0.60, "nice_coverage": 0.15, "experience_fit": 0.25}
EXPERIENCE_FIT_FALLBACK = 0.5
WEAK_MUST_COVERAGE = 0.50
STRONG_THRESHOLD = 75
MODERATE_THRESHOLD = 55


def score(checks: list[dict]) -> dict | None:
    """Return the fit payload, or ``None`` when there is nothing to score.

    A description that yielded no mandatory requirement is "cannot be judged",
    not a perfect match: scoring it would credit a job for the requirements it
    never stated. Callers treat ``None`` as "no fit assessment" and keep the
    eligibility verdict, including its reason, as the visible answer.
    """
    must = [check for check in checks if check.get("kind") == "must_have"]
    nice = [check for check in checks if check.get("kind") == "nice_to_have"]
    if not must:
        return None
    must_coverage = _coverage(must)
    nice_coverage = _coverage(nice)
    experience_fit = EXPERIENCE_FIT_FALLBACK

    raw = (
        WEIGHTS["must_coverage"] * must_coverage
        + WEIGHTS["nice_coverage"] * nice_coverage
        + WEIGHTS["experience_fit"] * experience_fit
    )
    fit_score = _round_half_up(100 * raw)
    if must_coverage < WEAK_MUST_COVERAGE:
        verdict = "weak"
    elif fit_score >= STRONG_THRESHOLD:
        verdict = "strong"
    elif fit_score >= MODERATE_THRESHOLD:
        verdict = "moderate"
    else:
        verdict = "weak"

    return {
        "fit_score": fit_score,
        "verdict": verdict,
        "confidence": _confidence(must, nice),
        "components": [
            _component("must_coverage", must_coverage, must),
            _component("nice_coverage", nice_coverage, nice),
            {
                "name": "experience_fit",
                "weight": WEIGHTS["experience_fit"],
                "value": experience_fit,
                "contribution": round(100 * WEIGHTS["experience_fit"] * experience_fit, 2),
                "requirement_ids": [],
                "evidence_ids": [],
            },
        ],
        "gaps": [
            {
                "requirement_id": check["requirement_id"],
                "description": check["reason"][:2000],
                "evidence_ids": list(check.get("evidence_refs") or [])[:100],
            }
            for check in (*must, *nice)
            if check["result"] != "met"
        ][:200],
    }


def _round_half_up(value: float) -> int:
    """Half-up rounding; Python's round() is banker's rounding and would map
    72.5 to 72, which contradicts the documented formula."""
    return int(math.floor(value + 0.5))


def _coverage(checks: list[dict]) -> float:
    if not checks:
        # No requirement of this kind: it neither helps nor hurts the score.
        return 1.0
    met = sum(1.0 for check in checks if check["result"] == "met")
    return met / len(checks)


def _component(name: str, value: float, checks: list[dict]) -> dict:
    evidence: list[str] = []
    for check in checks:
        for evidence_id in check.get("evidence_refs") or []:
            if evidence_id not in evidence:
                evidence.append(evidence_id)
    return {
        "name": name,
        "weight": WEIGHTS[name],
        "value": round(value, 4),
        "contribution": round(100 * WEIGHTS[name] * value, 2),
        "requirement_ids": [check["requirement_id"] for check in checks],
        "evidence_ids": evidence[:200],
    }


def _confidence(must: list[dict], nice: list[dict]) -> str:
    explicit = len(must) + len(nice)
    if explicit >= 5 and must:
        return "high"
    if explicit >= 2:
        return "medium"
    return "low"
