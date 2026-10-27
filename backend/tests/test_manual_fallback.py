"""Manual-URL fallback: parser hardening and the pasted-text escape hatch."""

from __future__ import annotations

import pytest

from gawe.jobs.sources import manual
from gawe.jobs.sources.base import AdapterError, RawJob, company_of, normalize
from gawe.jobs.fetch import FetchError
from gawe.services.assessment_service import AssessmentService
from tests.test_applications import MANUAL_PAGE, _manual_fetcher
from tests.test_assessment import _confirm
from tests.test_discovery import _Fetcher


def _page(*, og_url: str | None = None, body: str | None = None) -> str:
    meta = f'<meta property="og:url" content="{og_url}">' if og_url else ""
    return f"""
<html><head>
<title>Senior Backend Engineer - Acme</title>
<meta property="og:site_name" content="Acme">
{meta}
</head><body>
<h1>Senior Backend Engineer</h1>
{body or "<p>We need a backend engineer with Python and PostgreSQL experience.</p>"}
</body></html>
"""


# -- parser: canonical URL ------------------------------------------------
def test_og_url_is_used_when_it_names_the_same_host() -> None:
    raw = manual.parse(
        _page(og_url="https://example.com/jobs/1?utm_source=board"),
        "https://example.com/jobs/1",
    )
    assert raw.canonical_url == "https://example.com/jobs/1?utm_source=board"


@pytest.mark.parametrize(
    "og_url",
    [
        "https://other.example/jobs/1",
        "http://example.com/jobs/1",
        "https://example.com@evil.example/jobs/1",
    ],
)
def test_og_url_from_another_host_or_scheme_is_ignored(og_url: str) -> None:
    raw = manual.parse(_page(og_url=og_url), "https://example.com/jobs/1")
    assert raw.canonical_url == "https://example.com/jobs/1"


def test_source_job_id_ignores_tracking_parameters() -> None:
    pasted = "https://example.com/jobs/1"
    canonical = "https://example.com/jobs/1?gh_src=abc"
    same = manual.parse(_page(og_url=canonical), pasted)
    assert same.source_job_id == manual._stable_id(pasted)
    assert same.source_job_id == manual._stable_id("https://example.com/jobs/1/")


# -- parser: JavaScript shells -------------------------------------------
def test_javascript_shell_is_reported_as_such() -> None:
    shell = "<html><body><div id='root'></div>" + ("<script src='a.js'></script>" * 200)
    with pytest.raises(AdapterError) as exc:
        manual.parse(shell, "https://example.com/jobs/1")
    assert "JavaScript" in str(exc.value)


def test_thin_page_without_scripts_is_a_plain_unreadable_page() -> None:
    with pytest.raises(AdapterError) as exc:
        manual.parse("<html><body><h1>Jobs</h1></body></html>", "https://example.com/jobs/1")
    assert "no readable description" in str(exc.value)


def test_json_ld_description_survives_a_thin_body() -> None:
    """Structured data is read before the shell heuristic, so it never trips it."""
    payload = (
        '{"@context":"https://schema.org","@type":"JobPosting",'
        '"title":"Data Engineer","hiringOrganization":{"name":"Acme"},'
        '"description":"<p>Build pipelines with Python and SQL every single day.</p>"}'
    )
    page = (
        "<html><head>"
        f'<script type="application/ld+json">{payload}</script>'
        "</head><body>" + ("<div class='shell'></div>" * 200) + "</body></html>"
    )
    raw = manual.parse(page, "https://example.com/jobs/1")
    assert raw.title == "Data Engineer"
    assert raw.extra["company"] == "Acme"


# -- parser: pasted text --------------------------------------------------
def test_pasted_text_splits_title_and_company() -> None:
    raw = manual.from_text(
        "Senior Backend Engineer - Acme\n\nKami mencari backend engineer "
        "dengan pengalaman Python dan PostgreSQL.",
        "https://example.com/jobs/1",
    )
    assert raw.title == "Senior Backend Engineer"
    assert raw.extra["company"] == "Acme"
    assert raw.canonical_url == "https://example.com/jobs/1"


def test_pasted_text_without_separator_keeps_the_whole_title() -> None:
    raw = manual.from_text(
        "Backend Engineer\n\nPython, PostgreSQL, dan pengalaman lima tahun.",
        "https://example.com/jobs/1",
    )
    assert raw.title == "Backend Engineer"
    assert raw.extra["company"] is None


@pytest.mark.parametrize("text", ["", "   ", "short"])
def test_pasted_text_that_is_too_short_is_rejected(text: str) -> None:
    with pytest.raises(AdapterError):
        manual.from_text(text, "https://example.com/jobs/1")


# -- company_of moved to base: behaviour and identity are unchanged --------
def test_company_of_reads_the_record_then_the_fallback() -> None:
    named = RawJob(
        source_job_id="1",
        title="Backend Engineer",
        canonical_url="https://example.com/jobs/1",
        description_html="<p>x</p>",
        extra={"company": "  Acme  "},
    )
    assert company_of(named, manual.COMPANY) == "Acme"

    unnamed = RawJob(
        source_job_id="2",
        title="Backend Engineer",
        canonical_url="https://example.com/jobs/2",
        description_html="<p>x</p>",
    )
    assert company_of(unnamed, manual.COMPANY) == manual.COMPANY
    # No fallback: the caller must drop the record instead of inventing a name.
    assert company_of(unnamed) is None


def test_manual_normalize_keeps_its_hash_and_fingerprint() -> None:
    """Moving company_of must not change a stored manual job's identity."""
    raw = manual.from_text(
        "Senior Backend Engineer - Acme\n\nKami mencari backend engineer "
        "dengan pengalaman Python dan PostgreSQL.",
        "https://example.com/jobs/1",
    )
    record = normalize(
        raw,
        {"source_id": manual.SOURCE_ID, "company": company_of(raw, manual.COMPANY)},
        "2026-01-01T00:00:00Z",
    )
    assert record["company"] == "Acme"
    assert record["content_hash"] == (
        "d93993f2e45b8877bb7a0ef8a177a2335c6ee48996dc5d2aadf2fe21b589cf5e"
    )
    assert record["fingerprint"] == (
        "59e5bd24a6660d9021f63276296a4fc929df07f60ae00a2d96623a137648dfad"
    )


def test_manual_normalize_falls_back_to_the_source_label() -> None:
    raw = manual.from_text(
        "Backend Engineer\n\nPython, PostgreSQL, dan pengalaman lima tahun.",
        "https://example.com/jobs/1",
    )
    record = normalize(
        raw,
        {"source_id": manual.SOURCE_ID, "company": company_of(raw, manual.COMPANY)},
        "2026-01-01T00:00:00Z",
    )
    assert record["company"] == manual.COMPANY
    assert record["content_hash"] == (
        "110a3489f0e65c5afe432473ae693df0e57fae6a5a191dfaa6c8f46c6efccd43"
    )
    assert record["fingerprint"] == (
        "a5ac68a312e6c482b11957023099dbd8d446390d1e7ce6b6aaceefebf890e24c"
    )


# -- API: text path -------------------------------------------------------
PASTED = (
    "Senior Backend Engineer - Acme\n\n"
    "We need a backend engineer with Python and PostgreSQL experience. "
    "You will build payment services and own reliability for the billing API."
)


def test_pasted_text_creates_a_workspace_without_fetching(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    fetcher = _manual_fetcher(monkeypatch, setup_client)

    response = setup_client.post(
        "/api/applications",
        headers=csrf,
        json={"url": "https://example.com/jobs/1", "text": PASTED},
    )
    assert response.status_code == 201, response.text

    workspace = setup_client.get(
        f"/api/applications/{response.json()['application_id']}"
    ).json()
    assert workspace["job"]["title"] == "Senior Backend Engineer"
    assert workspace["job"]["company"] == "Acme"
    assert workspace["job"]["source_id"] == "manual_url"
    assert workspace["job"]["canonical_url"] == "https://example.com/jobs/1"

    # No page and no robots.txt were requested: the text is the whole input.
    assert fetcher.calls == []

    fetch = connection.execute(
        "SELECT raw_json, http_status, final_url, etag FROM source_fetch"
    ).fetchone()
    assert fetch["raw_json"] == PASTED
    assert fetch["http_status"] is None
    assert fetch["final_url"] is None
    assert fetch["etag"] is None

    run = connection.execute(
        "SELECT stats_json FROM discovery_run_source WHERE source_id = 'manual_url'"
    ).fetchone()
    assert "manual_text" in run["stats_json"]


def test_pasted_text_still_needs_a_valid_url(setup_client, csrf, monkeypatch) -> None:
    _confirm(setup_client, csrf)
    _manual_fetcher(monkeypatch, setup_client)
    response = setup_client.post(
        "/api/applications",
        headers=csrf,
        json={"url": "http://example.com/jobs/1", "text": PASTED},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "url_rejected"


def test_text_without_url_is_rejected(setup_client, csrf) -> None:
    _confirm(setup_client, csrf)
    response = setup_client.post(
        "/api/applications", headers=csrf, json={"text": PASTED}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_failed"


def test_text_with_job_id_is_rejected(setup_client, csrf) -> None:
    _confirm(setup_client, csrf)
    response = setup_client.post(
        "/api/applications",
        headers=csrf,
        json={"job_id": "job_1", "text": PASTED},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_failed"


def test_text_that_is_too_short_reports_an_unreadable_page(
    setup_client, csrf, monkeypatch
) -> None:
    _confirm(setup_client, csrf)
    _manual_fetcher(monkeypatch, setup_client)
    response = setup_client.post(
        "/api/applications",
        headers=csrf,
        json={"url": "https://example.com/jobs/1", "text": "short"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "manual_page_unreadable"


def test_text_is_capped_at_the_contract_limit(setup_client, csrf, monkeypatch) -> None:
    _confirm(setup_client, csrf)
    _manual_fetcher(monkeypatch, setup_client)
    response = setup_client.post(
        "/api/applications",
        headers=csrf,
        json={"url": "https://example.com/jobs/1", "text": "x" * 200_001},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_failed"


def test_unreadable_page_reports_a_specific_reason(
    setup_client, csrf, monkeypatch
) -> None:
    """A shell page must not be reported as a generic parse failure."""
    _confirm(setup_client, csrf)
    shell = "<html><body><div id='root'></div>" + ("<script src='a.js'></script>" * 200)
    _manual_fetcher(monkeypatch, setup_client, page=shell)
    response = setup_client.post(
        "/api/applications", headers=csrf, json={"url": "https://example.com/jobs/1"}
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "manual_page_unreadable"
    assert "JavaScript" in error["message"]


def test_fetched_page_keeps_the_existing_stats_marker(
    setup_client, csrf, monkeypatch, connection
) -> None:
    _confirm(setup_client, csrf)
    _manual_fetcher(monkeypatch, setup_client, page=MANUAL_PAGE)
    response = setup_client.post(
        "/api/applications", headers=csrf, json={"url": "https://example.com/jobs/1"}
    )
    assert response.status_code == 201, response.text
    run = connection.execute(
        "SELECT stats_json FROM discovery_run_source WHERE source_id = 'manual_url'"
    ).fetchone()
    assert "manual_url" in run["stats_json"]


def test_blocked_page_is_a_client_error_with_the_paste_hint(
    setup_client, csrf, monkeypatch
) -> None:
    """A page the user chose that refuses us is bad input, not a server fault."""
    _confirm(setup_client, csrf)
    fetcher = _Fetcher(
        {"robots.txt": "User-agent: *\nAllow: /\n"},
        fail_hosts={
            "example.com/jobs": FetchError(
                "source_unavailable",
                "Halaman menolak akses otomatis. Tempelkan teks lowongan secara manual.",
                retryable=False,
                http_status=403,
            )
        },
    )
    monkeypatch.setattr(setup_client.app.state, "manual_url_fetcher", fetcher, raising=False)
    response = setup_client.post(
        "/api/applications", headers=csrf, json={"url": "https://example.com/jobs/1"}
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "manual_fetch_failed"
    assert "Tempelkan teks lowongan" in error["message"]


def test_missing_page_keeps_its_own_code(setup_client, csrf, monkeypatch) -> None:
    _confirm(setup_client, csrf)
    fetcher = _Fetcher(
        {"robots.txt": "User-agent: *\nAllow: /\n"},
        fail_hosts={
            "example.com/jobs": FetchError("source_not_found", "Halaman tidak ditemukan.", retryable=False)
        },
    )
    monkeypatch.setattr(setup_client.app.state, "manual_url_fetcher", fetcher, raising=False)
    response = setup_client.post(
        "/api/applications", headers=csrf, json={"url": "https://example.com/jobs/1"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "source_not_found"


def test_workspace_is_created_when_the_run_assessment_failed(
    setup_client, csrf, monkeypatch
) -> None:
    """A stored job with no assessment must not strand the user on a 404."""
    _confirm(setup_client, csrf)
    _manual_fetcher(monkeypatch, setup_client, page=MANUAL_PAGE)

    original = AssessmentService.assess_pending
    calls = {"count": 0}

    def _fail_once(self, limit: int = 500) -> dict:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("provider unavailable")
        return original(self, limit)

    monkeypatch.setattr(AssessmentService, "assess_pending", _fail_once)

    response = setup_client.post(
        "/api/applications", headers=csrf, json={"url": "https://example.com/jobs/1"}
    )
    assert response.status_code == 201, response.text
    workspace = setup_client.get(
        f"/api/applications/{response.json()['application_id']}"
    ).json()
    assert workspace["eligibility"] is not None
    # One retry only: the second create() call is not followed by a third.
    assert calls["count"] == 1
