"""Opt-in live verification against the configured 9Router provider.

Skipped by default. Two things are required, and neither is an API key:

1. ``GAWE_LIVE_9ROUTER=1`` in the environment.
2. A config file (``GAWE_LIVE_CONFIG``, default: repository ``config.toml``)
   whose ``active_provider`` is a real ``openai_compatible`` provider.

The key itself comes from the keyring reference or ``GAWE_LLM_API_KEY``. A key
alone never enables this test. No default test run reaches the network.

Run:
    cd backend
    $env:GAWE_LIVE_9ROUTER = "1"
    $env:GAWE_LIVE_CONFIG = "D:\\gawe\\config.toml"
    uv run pytest tests/test_live_9router.py -m live -s

The test uses two different synthetic fixtures and validates every quotation
against its own source document. It writes to a ``gawe_test_*`` schema only; the
development schema named in the config file is never connected.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

from gawe.api.app import _make_provider
from gawe.config import LOOPBACK_HOSTS, Config, DatabaseConfig, load_config
from gawe.db import repo
from gawe.ingest.text import parse_text
from gawe.ingest.types import normalize_text
from gawe.llm.client import LLMClient, LLMContractError
from gawe.profile.extract import extract_profile, load_prompt, locator_text
from gawe.security.consent import ConsentStore

from .conftest import CONFIG_TEMPLATE, TEST_SCHEMA

ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS = {
    "doc_live_001": ROOT / "docs" / "phase-00" / "fixtures" / "master_cv" / "candidate_001.md",
    "doc_live_002": (
        ROOT / "docs" / "phase-00" / "fixtures" / "seeded_defects" / "cv_seeded_defects.md"
    ),
}
OPT_IN_ENV = "GAWE_LIVE_9ROUTER"
CONFIG_ENV = "GAWE_LIVE_CONFIG"

FACT_KEYS = (
    "education",
    "experience",
    "skills",
    "projects",
    "certifications",
    "languages",
    "awards",
    "work_authorization",
)

skip_reason = (
    f"live provider test is opt-in: set {OPT_IN_ENV}=1 and point {CONFIG_ENV} at a "
    "config whose active_provider is 9Router"
)


def _live_database(config: Config, test_schema: str) -> DatabaseConfig:
    """Return the disposable test schema. Anything else is rejected."""
    repo.require_test_schema(test_schema)
    return config.database.model_copy(update={"name": test_schema})


def _connect_live(database: DatabaseConfig) -> repo.Connection:
    """Only a ``gawe_test_*`` schema may be opened by the live test."""
    repo.require_test_schema(database.name)
    return repo.connect(database)


def _prepare_live_run(config: Config, test_schema: str):
    """Schema guard first, provider second. Order is the point of the test."""
    database = _live_database(config, test_schema)
    return database, _make_provider(config)


def test_live_guard_rejects_development_schema_before_provider_or_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        CONFIG_TEMPLATE.replace(f'name = "{TEST_SCHEMA}"', 'name = "gawe"'),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.database.name == "gawe"

    provider_calls: list[str] = []
    monkeypatch.setattr(
        f"{__name__}._make_provider",
        lambda *_args, **_kwargs: provider_calls.append("called"),
    )
    monkeypatch.setattr(
        repo, "connect", lambda *_args, **_kwargs: pytest.fail("connected before schema guard")
    )

    # The configured development schema is refused before any connection or
    # provider construction.
    with pytest.raises(repo.SchemaNameError):
        _connect_live(config.database)
    with pytest.raises(repo.SchemaNameError):
        _prepare_live_run(config, "gawe")

    assert provider_calls == []


@pytest.mark.live
@pytest.mark.skipif(os.environ.get(OPT_IN_ENV) != "1", reason=skip_reason)
def test_live_9router_extraction(test_schema: str, _clean_database) -> None:
    config_path = Path(os.environ.get(CONFIG_ENV, ROOT / "config.toml"))
    config = load_config(config_path)

    provider_config = config.llm.providers.get(config.llm.active_provider)
    assert provider_config is not None, "active_provider is not defined in [llm.providers]"
    assert provider_config.type == "openai_compatible", "live test expects the approved adapter"
    assert provider_config.base_url, "provider base_url is empty"
    # Plaintext is refused for remote hosts; a loopback router cannot leave the machine.
    base_host = urlparse(provider_config.base_url).hostname or ""
    assert provider_config.base_url.startswith("https://") or base_host in LOOPBACK_HOSTS, (
        "provider base_url must be HTTPS unless it is a loopback host"
    )
    assert config.llm.roles.get("extract"), "llm.roles.extract is empty"

    # Never touch the development schema named in the config file.
    database, provider = _prepare_live_run(config, test_schema)
    assert database.name.startswith(repo.TEST_SCHEMA_PREFIX)
    connection = _connect_live(database)
    try:
        # Consent gate: the first call must be refused before any request leaves
        # the process. The key is withheld so a gate defect cannot leak data.
        provider.api_key = None
        client = LLMClient(
            config=config,
            provider=provider,
            consent_store=ConsentStore(connection, config),
            connection=connection,
        )
        prompt_id, prompt_version, prompt_body = load_prompt(ROOT)
        first_document = parse_text(DOCUMENTS["doc_live_001"].read_bytes())

        with pytest.raises(LLMContractError) as exc:
            client.generate(
                "extract",
                [{"role": "user", "content": locator_text(first_document)}],
                _response_schema(),
                0.0,
                64,
            )
        assert exc.value.code == "consent_required"

        store = ConsentStore(connection, config)
        record = store.grant()
        assert record["scope"]["provider_id"] == config.llm.active_provider
        assert record["scope"]["model_roles"] == dict(config.llm.roles)

        live = LLMClient(
            config=config,
            provider=_make_provider(config),
            consent_store=store,
            connection=connection,
        )

        sources = {
            doc_id: parse_text(path.read_bytes()) for doc_id, path in DOCUMENTS.items()
        }
        normalized = {
            doc_id: normalize_text(document.text) for doc_id, document in sources.items()
        }
        expected_hashes: dict[str, str] = {}
        summary: list[dict] = []

        for doc_id, document in sources.items():
            content, evidence, conflicts, first = extract_profile(
                client=live,
                document=document,
                doc_id=doc_id,
                prompt_body=prompt_body,
                prompt_id=prompt_id,
                prompt_version=prompt_version,
                active_content=None,
            )

            # Configured provider/model were the ones used.
            assert first["provider"] == config.llm.active_provider
            assert first["model"] == config.llm.roles["extract"]
            assert first["prompt_id"] == prompt_id
            assert first["prompt_version"] == prompt_version

            # Evidence and quotations trace back to this document only.
            source = normalized[doc_id]
            other_sources = {
                other_id: text for other_id, text in normalized.items() if other_id != doc_id
            }
            assert evidence, f"{doc_id}: live extraction returned no evidence"
            quotes: list[str] = []
            for evidence_id, item in evidence.items():
                assert item["doc_id"] == doc_id, evidence_id
                quote = normalize_text(item["quote"])
                assert quote in source, evidence_id
                quotes.append(quote)
            assert any(
                not any(quote in other for other in other_sources.values())
                for quote in quotes
            ), f"{doc_id}: no quotation is unique to its own source"

            facts = [fact for key in FACT_KEYS for fact in content[key]]
            assert facts, f"{doc_id}: live extraction returned no facts"
            for fact in facts:
                assert fact["evidence"], "fact without evidence survived validation"
                assert all(ref in evidence for ref in fact["evidence"])
                assert all(evidence[ref]["doc_id"] == doc_id for ref in fact["evidence"])

            # prompt_hash is reproducible from the messages actually sent.
            messages = [
                {"role": "system", "content": prompt_body},
                {
                    "role": "user",
                    "content": "<untrusted>\n" + locator_text(document) + "\n</untrusted>",
                },
            ]
            expected_hash = hashlib.sha256(
                json.dumps(messages, sort_keys=True).encode("utf-8")
            ).hexdigest()
            assert first["prompt_hash"] == expected_hash
            expected_hashes[doc_id] = expected_hash
            summary.append(
                {
                    "doc_id": doc_id,
                    "prompt_hash": first["prompt_hash"],
                    "response_hash": first["response_hash"],
                    "config_snapshot_id": first["config_snapshot_id"],
                    "input_tokens": first["input_tokens"],
                    "output_tokens": first["output_tokens"],
                    "latency_ms": first["latency_ms"],
                    "facts": len(facts),
                    "evidence": len(evidence),
                    "conflicts": len(conflicts),
                    "validation": first["validation"],
                }
            )

        # Two distinct sources produced two distinct prompts.
        assert len(set(expected_hashes.values())) == len(DOCUMENTS)

        rows = connection.execute(
            "SELECT provider, model, prompt_hash, error_code FROM llm_call "
            "ORDER BY created_at"
        ).fetchall()
        assert len(rows) == len(DOCUMENTS)
        assert {row["prompt_hash"] for row in rows} == set(expected_hashes.values())
        for row in rows:
            assert row["provider"] == config.llm.active_provider
            assert row["model"] == config.llm.roles["extract"]
            assert row["error_code"] is None

        print(
            json.dumps(
                {
                    "provider": config.llm.active_provider,
                    "model": config.llm.roles["extract"],
                    "prompt_id": prompt_id,
                    "prompt_version": prompt_version,
                    "documents": summary,
                },
                indent=2,
            )
        )
    finally:
        connection.close()


def _response_schema() -> dict:
    from gawe.profile.extract import RESPONSE_SCHEMA

    return RESPONSE_SCHEMA


@pytest.mark.live
@pytest.mark.skipif(os.environ.get(OPT_IN_ENV) != "1", reason=skip_reason)
def test_live_9router_write_and_review(test_schema: str, _clean_database) -> None:
    """The writer and the reviewer, on the real provider, end to end.

    Proves the two things unit tests cannot: that the prompts produce
    schema-valid JSON against a real model, and that the reviewer returns a
    score the loop can act on.
    """
    from gawe.documents import ai_draft, ai_review
    from gawe.profile.extract import extract_profile

    config_path = Path(os.environ.get(CONFIG_ENV, ROOT / "config.toml"))
    config = load_config(config_path)
    database, provider = _prepare_live_run(config, test_schema)
    connection = _connect_live(database)
    try:
        store = ConsentStore(connection, config)
        store.grant()
        client = LLMClient(
            config=config,
            provider=provider,
            consent_store=store,
            connection=connection,
        )

        prompt_id, prompt_version, prompt_body = load_prompt(ROOT)
        document = parse_text(DOCUMENTS["doc_live_001"].read_bytes())
        profile, evidence, _conflicts, _meta = extract_profile(
            client=client,
            document=document,
            doc_id="doc_live_001",
            prompt_body=prompt_body,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            active_content=None,
        )
        job = {
            "job_id": "job_live_001",
            "job_posting_version_id": "jpv_live_001",
            "title": "Senior Backend Engineer",
            "company": "Contoh Nusantara",
            "description_text": (
                "Build and operate payment APIs. Must have Python, PostgreSQL, and "
                "experience owning production services."
            ),
            "requirements": [
                {
                    "requirement_id": "req_live_1",
                    "text": "Python",
                    "kind": "must_have",
                    "weight": 1.0,
                },
                {
                    "requirement_id": "req_live_2",
                    "text": "PostgreSQL",
                    "kind": "must_have",
                    "weight": 1.0,
                },
            ],
        }

        content, write_meta = ai_draft.write(
            client, ROOT, "cv", profile, evidence, job, "en"
        )
        assert write_meta["source"] == "llm", write_meta
        assert content["kind"] == "cv"
        assert content["experience"], "writer returned a CV without experience"
        assert content["header"]["full_name"] == (profile.get("personal") or {}).get(
            "full_name"
        ), "identity fields must come from the profile, not the model"
        assert content["target"]["company"] == job["company"]
        unknown = {
            ref
            for ref in _all_evidence_ids(content)
            if ref not in evidence
        }
        assert not unknown, f"writer invented evidence ids: {sorted(unknown)[:5]}"

        report, review_meta = ai_review.review(
            client, ROOT, content, evidence, profile, job
        )
        assert review_meta["source"] == "llm", review_meta
        assert 0.0 <= report["overall_score"] <= 10.0
        assert set(report["dimension_scores"]) == set(ai_review.DIMENSIONS)
        assert report["verdict"] in {"pass", "changes_required"}
        if any(f["severity"] in {"blocker", "major"} for f in report["findings"]):
            assert report["verdict"] == "changes_required"
            assert ai_review.passed(report, 8.0) is False

        print(
            json.dumps(
                {
                    "provider": config.llm.active_provider,
                    "models": {
                        "write": config.llm.roles["write"],
                        "review": config.llm.roles["review"],
                    },
                    "write": {
                        key: write_meta.get(key)
                        for key in (
                            "prompt_id",
                            "prompt_version",
                            "input_tokens",
                            "output_tokens",
                            "latency_ms",
                        )
                    },
                    "review": {
                        "overall_score": report["overall_score"],
                        "dimension_scores": report["dimension_scores"],
                        "verdict": report["verdict"],
                        "findings": len(report["findings"]),
                        "severities": sorted(
                            {item["severity"] for item in report["findings"]}
                        ),
                        "input_tokens": review_meta.get("input_tokens"),
                        "output_tokens": review_meta.get("output_tokens"),
                        "latency_ms": review_meta.get("latency_ms"),
                    },
                },
                indent=2,
            )
        )
    finally:
        connection.close()


def _all_evidence_ids(content: dict) -> list[str]:
    refs: list[str] = []

    def collect(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "evidence_ids":
                    refs.extend(str(ref) for ref in value or [])
                else:
                    collect(value)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    collect(content)
    return refs
