"""Phase 3D: the deterministic reviewer must catch every seeded defect.

The fixture is synthetic (`docs/phase-00/fixtures/seeded_defects/`). It pairs a
deliberately defective CV with a confirmed profile and the findings a reviewer
is expected to raise. D9 (separate reviewer model) is still open, so this covers
the deterministic half of PLAN.md §7.4.
"""

from __future__ import annotations

import json
from pathlib import Path

from gawe.documents import factcheck

FIXTURES = Path(__file__).resolve().parents[2] / "docs" / "phase-00" / "fixtures"
SEEDED = FIXTURES / "seeded_defects"


def _load(name: str) -> dict:
    return json.loads((SEEDED / name).read_text(encoding="utf-8"))


def _norm(value: str) -> str:
    for dash in ("\u2013", "\u2014", "\u2212"):
        value = value.replace(dash, "-")
    return " ".join(value.split()).lower()


def test_reviewer_catches_every_seeded_defect() -> None:
    profile = json.loads(
        (FIXTURES / "profiles" / "profile_confirmed.json").read_text(encoding="utf-8")
    )
    text = (SEEDED / "cv_seeded_defects.md").read_text(encoding="utf-8")
    expected = _load("cv_seeded_defects.expected.json")["expected_findings"]

    findings = factcheck.review_text(text, profile, kind="cv")

    missing: list[str] = []
    for item in expected:
        quote = _norm(item["quote"])
        hits = [
            finding
            for finding in findings
            if quote in _norm(finding["quote"]) or _norm(finding["quote"]) in quote
        ]
        if not any(
            hit["severity"] == item["expected_severity"]
            and hit["category"] == item["expected_category"]
            for hit in hits
        ):
            missing.append(item["defect"])

    assert missing == []


def test_reviewer_stays_quiet_on_profile_faithful_text() -> None:
    profile = json.loads(
        (FIXTURES / "profiles" / "profile_confirmed.json").read_text(encoding="utf-8")
    )
    role = profile["experience"][0]
    text = "\n".join(
        [
            f"# {profile['personal']['full_name']}",
            "## Summary",
            f"{role['title']} at {role['company']}.",
            "## Experience",
            f"### {role['title']} - {role['company']}",
            f"{role['start']} - present",
            *(f"- {bullet['text']}" for bullet in role["bullets"]),
        ]
    )

    assert factcheck.review_text(text, profile, kind="cv") == []


def test_page_count_over_limit_is_a_format_finding() -> None:
    profile = json.loads(
        (FIXTURES / "profiles" / "profile_confirmed.json").read_text(encoding="utf-8")
    )
    findings = factcheck.review_text("", profile, kind="cv", page_count=3)

    assert [item["category"] for item in findings] == ["format"]
    assert findings[0]["severity"] == "major"
