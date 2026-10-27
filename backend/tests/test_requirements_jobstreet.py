"""Reproduction: Jobstreet detail descriptions the regex extractor loses.

The extension path stores the description as one `<p>` per line
(`browser_import_service._lines_to_html`), then `html_to_text` collapses every
newline. These tests feed the extractor the same collapsed string the extension
produces, so a failure here is the same failure a user sees on Job Matches.

The LLM path that fixes this is covered in `test_requirements_llm.py`. What is
left here is the baseline the deterministic fallback must keep, plus one
`xfail(strict=True)` that records what it still cannot do: a strict xfail that
starts passing is reported as a failure, so the marker cannot be forgotten.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gawe.jobs import requirements as requirement_rules
from gawe.jobs.sources.base import html_to_text
from gawe.services.browser_import_service import _lines_to_html

DESCRIPTIONS = Path(__file__).resolve().parent / "fixtures" / "jobs" / "descriptions"

INDONESIAN_BACKEND = "jobstreet_backend_id.txt"
ENGLISH_BACKEND = "jobstreet_senior_backend_en.txt"
INDONESIAN_ANALYST = "jobstreet_data_analyst_id.txt"


def stored_description(name: str) -> str:
    """The exact text the extension import writes to `description_text`."""
    raw = (DESCRIPTIONS / name).read_text(encoding="utf-8")
    return html_to_text(_lines_to_html(raw))


def must_have(requirements: list[dict]) -> list[dict]:
    return [item for item in requirements if item["kind"] == "must_have"]


def quotes(requirements: list[dict]) -> str:
    return " | ".join(item["quote"] for item in requirements)


# -- what the fallback does right --------------------------------------------
def test_english_requirements_heading_is_read() -> None:
    """Baseline: the bug is not "no requirements at all", it is language-specific."""
    found = requirement_rules.extract(stored_description(ENGLISH_BACKEND))
    assert "5+ years" in quotes(must_have(found))
    assert any(item["kind"] == "nice_to_have" for item in found)


def test_responsibility_prose_never_becomes_a_gate() -> None:
    found = requirement_rules.extract(stored_description(INDONESIAN_BACKEND))
    assert all("Kami membangun platform" not in item["text"] for item in found)


def test_stored_description_is_one_line() -> None:
    """Documents the input shape: no newline survives the import path."""
    stored = stored_description(INDONESIAN_BACKEND)
    assert "\n" not in stored
    assert "Kualifikasi - Minimal 3 tahun" in stored


def test_indonesian_posting_without_a_standard_heading_reads_as_nothing() -> None:
    """Why the model path exists: this fixture is invisible to the cue words."""
    found = requirement_rules.extract(stored_description(INDONESIAN_ANALYST))
    assert [item["category"] for item in found] != ["education", "other", "experience"]


@pytest.mark.xfail(
    strict=True,
    reason="fallback only: no Indonesian heading or cue words, and bullets without a period fuse",
)
def test_fallback_splits_indonesian_bullets_into_one_requirement_each() -> None:
    found = must_have(requirement_rules.extract(stored_description(INDONESIAN_BACKEND)))
    assert len(found) >= 4, [item["text"] for item in found]
    assert all(len(item["text"]) <= 120 for item in found)
