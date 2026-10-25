"""Checked findings drive the writer instruction of the next version.

No network and no database: `_revision_instructions` is the seam between the
checkbox list and the prompt the writer receives.
"""

from __future__ import annotations

from gawe.documents import review as review_rules
from gawe.services import document_service


def _finding(finding_id: str, severity: str, problem: str) -> dict:
    return {
        "finding_id": finding_id,
        "severity": severity,
        "category": "factuality",
        "problem": problem,
        "quote": problem,
        "fix": "perbaiki",
        "location": {"doc": "cv"},
    }


def _report(*findings: dict) -> dict:
    return {"verdict": "changes_required", "findings": list(findings)}


def test_only_checked_findings_reach_the_writer() -> None:
    report = _report(
        _finding("f1", "blocker", "Evidence id tidak ditemukan."),
        _finding("f2", "major", "Klaim tanpa evidence."),
        _finding("f3", "minor", "Kalimat lemah."),
    )
    text = document_service._revision_instructions(report, only_ids={"f2"})
    assert "Klaim tanpa evidence." in text
    assert "Evidence id tidak ditemukan." not in text
    assert "Kalimat lemah." not in text


def test_no_filter_keeps_every_actionable_finding() -> None:
    report = _report(
        _finding("f1", "blocker", "Blocker satu."),
        _finding("f2", "minor", "Minor dua."),
    )
    text = document_service._revision_instructions(report)
    assert "Blocker satu." in text
    assert "Minor dua." in text


def test_version_row_shape_is_accepted() -> None:
    """A stored version nests its review: `{"findings": {"findings": [...]}}`."""
    version_row = {
        "findings": {
            "verdict": "changes_required",
            "findings": [
                _finding("f1", "blocker", "Blocker satu."),
                _finding("f2", "major", "Major dua."),
            ],
        }
    }
    text = document_service._revision_instructions(version_row, only_ids={"f2"})
    assert "Major dua." in text
    assert "Blocker satu." not in text


def test_nested_version_row_without_filter_passes_everything() -> None:
    version_row = {
        "findings": {"findings": [_finding("f1", "blocker", "Blocker satu.")]}
    }
    assert "Blocker satu." in document_service._revision_instructions(version_row)


def test_missing_findings_is_empty_not_an_error() -> None:
    assert document_service._revision_instructions({}) == ""
    assert document_service._revision_instructions({"findings": None}) == ""


def test_empty_selection_sends_no_instruction() -> None:
    report = _report(_finding("f1", "blocker", "Blocker satu."))
    assert document_service._revision_instructions(report, only_ids=set()) == ""


def test_deterministic_findings_carry_unique_ids() -> None:
    content = {
        "kind": "cv",
        "header": {"full_name": "Ayu"},
        "summary": {"text": "Ringkasan tanpa evidence.", "evidence_ids": []},
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
    result = review_rules.review(content, evidence_index={})
    ids = [item.get("finding_id") for item in result["findings"]]
    assert ids, result
    assert all(ids)
    assert len(set(ids)) == len(ids)
