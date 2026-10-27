"""Requirement extraction through the `extract` role, with the regex fallback.

The LLM is mocked: these tests pin the contract around the model, not its
quality. What matters is that only supported quotes are stored, that a failed
reading falls back to the deterministic path instead of inventing an empty list,
and that the call is recorded in `llm_call` once per posting version.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from gawe.jobs import requirements as requirement_rules
from gawe.jobs.sources.base import html_to_text
from gawe.services.browser_import_service import _lines_to_html

ROOT = Path(__file__).resolve().parents[2]
DESCRIPTIONS = Path(__file__).resolve().parent / "fixtures" / "jobs" / "descriptions"


def stored_description(name: str) -> str:
    """The exact text the extension import stores for a detail page."""
    raw = (DESCRIPTIONS / name).read_text(encoding="utf-8")
    return html_to_text(_lines_to_html(raw))


BACKEND_ID = stored_description("jobstreet_backend_id.txt")
ANALYST_ID = stored_description("jobstreet_data_analyst_id.txt")

# Every quote below is copied from the fixture, so it survives the check that a
# stored requirement must quote the posting.
BACKEND_REPLY = {
    "requirements": [
        {
            "requirement_id": "r1",
            "kind": "must_have",
            "text": "Minimal 3 tahun pengalaman membangun backend dengan Python",
            "quote": "Minimal 3 tahun pengalaman membangun backend dengan Python",
            "skill": "Python",
            "weight": None,
        },
        {
            "requirement_id": "r2",
            "kind": "must_have",
            "text": "Menguasai FastAPI atau Django REST Framework",
            "quote": "Menguasai FastAPI atau Django REST Framework",
            "skill": "FastAPI",
            "weight": None,
        },
        {
            "requirement_id": "r3",
            "kind": "nice_to_have",
            "text": "Diutamakan yang pernah menangani sistem pembayaran",
            "quote": "Diutamakan yang pernah menangani sistem pembayaran",
            "skill": None,
            "weight": None,
        },
    ],
    "no_must_have_found": False,
}


@dataclass
class FakeResult:
    object: dict


class FakeClient:
    """Stands in for `LLMClient`; records the request it was given."""

    def __init__(self, reply: dict | None = None, error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.calls: list[dict] = []

    def generate(self, **kwargs) -> FakeResult:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return FakeResult(self.reply or {})


def extract(text: str, client: FakeClient) -> list[dict] | None:
    return requirement_rules.extract_with_llm(text, client=client, root_dir=ROOT)


# -- the reply ---------------------------------------------------------------
def test_model_reply_becomes_stored_requirements() -> None:
    found = extract(BACKEND_ID, FakeClient(BACKEND_REPLY))
    assert found is not None
    assert [item["kind"] for item in found] == ["must_have", "must_have", "nice_to_have"]
    assert [item["category"] for item in found] == ["experience", "other", "other"]
    # Backend decides weight and id, never the model.
    assert [item["weight"] for item in found] == [1.0, 1.0, 0.5]
    assert all(item["requirement_id"].startswith("req_") for item in found)
    assert all(item["quote"] in BACKEND_ID for item in found)


def test_year_count_survives_the_mapping() -> None:
    found = extract(BACKEND_ID, FakeClient(BACKEND_REPLY))
    assert found is not None
    assert found[0]["constraint"] == {"min_years": 3}


def test_item_whose_quote_is_not_in_the_posting_is_dropped() -> None:
    reply = {
        "requirements": [
            BACKEND_REPLY["requirements"][0],
            {
                "requirement_id": "r9",
                "kind": "must_have",
                "text": "Menguasai Kubernetes",
                "quote": "Menguasai Kubernetes",
                "skill": "Kubernetes",
                "weight": None,
            },
        ]
    }
    found = extract(BACKEND_ID, FakeClient(reply))
    assert found is not None
    assert [item["text"] for item in found] == [BACKEND_REPLY["requirements"][0]["text"]]


def test_duplicate_text_keeps_one_requirement() -> None:
    item = BACKEND_REPLY["requirements"][1]
    found = extract(BACKEND_ID, FakeClient({"requirements": [item, dict(item)]}))
    assert found is not None
    assert len(found) == 1


def test_unknown_kind_makes_the_whole_reply_unusable() -> None:
    """Nothing usable came back, so it is a failed reading, not an empty posting."""
    item = {**BACKEND_REPLY["requirements"][0], "kind": "mandatory"}
    assert extract(BACKEND_ID, FakeClient({"requirements": [item]})) is None


def test_same_posting_and_reply_give_the_same_ids() -> None:
    first, second = extract(BACKEND_ID, FakeClient(BACKEND_REPLY)), extract(
        BACKEND_ID, FakeClient(BACKEND_REPLY)
    )
    assert [item["requirement_id"] for item in first] == [
        item["requirement_id"] for item in second
    ]


# -- the request -------------------------------------------------------------
def test_prompt_schema_role_and_untrusted_data() -> None:
    client = FakeClient(BACKEND_REPLY)
    extract(BACKEND_ID, client)
    call = client.calls[0]
    assert call["role"] == "extract"
    assert call["prompt_id"] == "parse_requirements"
    assert call["prompt_version"]
    assert call["temperature"] == 0.0
    # The declared contract is job.schema.json#/properties/requirements.
    item_schema = call["response_schema"]["properties"]["requirements"]
    assert item_schema["type"] == "array"
    assert item_schema["items"]["required"] == ["requirement_id", "kind", "text"]
    # Job text is data: it travels in a user message wrapped as untrusted.
    user = [message for message in call["messages"] if message["role"] == "user"]
    assert len(user) == 1
    assert user[0]["content"].startswith("<untrusted>")
    assert BACKEND_ID in user[0]["content"]


def test_short_description_never_reaches_the_model() -> None:
    client = FakeClient(BACKEND_REPLY)
    assert extract("Backend Engineer di Jakarta.", client) is None
    assert client.calls == []


# -- fallback ----------------------------------------------------------------
def test_reply_that_loses_every_item_falls_back_to_regex() -> None:
    invented = {
        "requirements": [
            {**BACKEND_REPLY["requirements"][0], "quote": "kalimat yang tidak ada"}
        ]
    }
    found, source = requirement_rules.extract_requirements(
        ANALYST_ID, client=FakeClient(invented), root_dir=ROOT
    )
    assert source == "regex"
    assert found == requirement_rules.extract(ANALYST_ID)


def test_provider_error_falls_back_to_regex() -> None:
    found, source = requirement_rules.extract_requirements(
        BACKEND_ID,
        client=FakeClient(error=RuntimeError("provider_unavailable")),
        root_dir=ROOT,
    )
    assert source == "regex"
    assert found == requirement_rules.extract(BACKEND_ID)


def test_missing_prompt_file_falls_back_without_a_call(tmp_path: Path) -> None:
    client = FakeClient(BACKEND_REPLY)
    found, source = requirement_rules.extract_requirements(
        BACKEND_ID, client=client, root_dir=tmp_path
    )
    assert client.calls == []
    assert source == "regex"
    assert found == requirement_rules.extract(BACKEND_ID)


def test_no_client_keeps_the_deterministic_path() -> None:
    found, source = requirement_rules.extract_requirements(BACKEND_ID)
    assert source == "regex"
    assert found == requirement_rules.extract(BACKEND_ID)


def test_description_without_any_requirement_reports_none() -> None:
    text = (
        "Tentang pekerjaan ini. Kami membangun platform pembayaran untuk UMKM "
        "dan mencari Backend Engineer yang siap bekerja di tim kecil. Kamu akan "
        "merancang API dan menjaga reliabilitas layanan bersama tim produk."
    )
    found, source = requirement_rules.extract_requirements(text)
    assert found == []
    assert source == "none"


@pytest.mark.parametrize("text", [BACKEND_ID, ANALYST_ID])
def test_fallback_still_reads_english_cues(text: str) -> None:
    """AMAN: the fallback keeps working when the model is not configured."""
    found, source = requirement_rules.extract_requirements(text, client=None)
    assert isinstance(found, list)
    assert source in {"regex", "none"}
