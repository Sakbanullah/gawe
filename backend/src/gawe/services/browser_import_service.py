"""Job import from the browser extension (JOB-DISCOVERY.md §4.6).

The user reads a job board in their own browser and the extension sends what is
already on screen. Nothing here fetches the board: no session, no `robots.txt`
question, no bot detection. The payload is untrusted text, so every record is
re-validated and normalised exactly like a pasted manual URL.

Two shapes are accepted:

- `cards`  — a search page: many jobs, snippet only. Enough to triage, never
  enough for the requirement extractor, so most land in `needs_review`.
- `detail` — one job page: full description. Same URL, so it updates the row the
  card created instead of adding a second one, then re-assesses that job.

Jobs land under the synthetic `manual_url` source, which is `enabled = 0`, so
the scheduled runner never tries to fetch them and walks into a bot challenge.
"""

from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlsplit, urlunsplit

from ..jobs.dedupe import link_duplicate
from ..jobs.normalize import location_key as _location_key
from ..jobs.sources.base import InvalidJob, RawJob, normalize
from ..jobs.sources.registry import SourceRegistry
from ..master_cv import new_id, now_iso
from ..security.url_guard import UnsafeUrl, validate_url
from .assessment_service import AssessmentService
from .discovery_service import DiscoveryService
from .tasks import TaskStore

MAX_JOBS_PER_REQUEST = 50
ALLOWED_HOST_SUFFIXES = {"jobstreet": ("jobstreet.com",)}
# `normalize` reads HTML, so text is handed over as escaped markup and comes back
# as plain text through `html_to_text`.
TITLE_MAX = 300
DESCRIPTION_MAX_CHARS = 200_000
# A snippet shorter than this is a teaser, not a description. The gap is recorded
# in `completeness.missing_fields` so it stays visible in the UI.
MIN_DESCRIPTION_CHARS = 40


class BrowserImportError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _host_allowed(host: str, source: str) -> bool:
    suffixes = ALLOWED_HOST_SUFFIXES.get(source, ())
    return any(host == suffix or host.endswith("." + suffix) for suffix in suffixes)


def _slug(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def _validate(url: str) -> str:
    """Validate one URL. Host resolution is only needed before a fetch, so a
    hostname that does not resolve still yields a usable string here."""
    try:
        return validate_url(url).url
    except UnsafeUrl as exc:
        if "did not resolve" in str(exc):
            return url.strip()
        raise
    except OSError:  # gaierror: name does not exist on this network
        return url.strip()


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _lines_to_html(text: str) -> str:
    """One paragraph per line, so headings survive as their own line."""
    return "".join(f"<p>{_escape(line.strip())}</p>" for line in text.splitlines() if line.strip())


def _job_url(card: dict, source: str) -> str:
    try:
        safe_url = _validate((card.get("url") or "").strip())
    except UnsafeUrl as exc:
        raise InvalidJob(f"url_rejected: {exc}") from exc
    host = (urlsplit(safe_url).hostname or "").lower()
    if not _host_allowed(host, source):
        raise InvalidJob("url_host_not_allowed")
    return safe_url


def _page_url(page_url: str, source: str) -> str:
    """The page the user is on, checked the same way as a job URL."""
    return _job_url({"url": page_url}, source)


def _raw_location(location_json: str | None) -> str | None:
    try:
        return (json.loads(location_json or "{}") or {}).get("raw")
    except ValueError:
        return None


# Jobstreet puts the posting id in the slug and users reach the same posting
# with or without query noise (`?type=standard`, `?jobId=`, tracking). Hashing
# the raw URL made the card and the detail page look like two different jobs, so
# the posting id is the identity whenever one appears in the path.
JOBSTREET_ID = re.compile(r"/(?:job|jobs)/([^/?#]*?)-?(\d{6,})(?=/|$)")


def _identity_url(safe_url: str) -> str:
    """Stable key for one posting: jobstreet id when present, else cleaned URL."""
    parts = urlsplit(safe_url)
    match = JOBSTREET_ID.search(parts.path)
    if match:
        return f"{parts.scheme}://{parts.netloc}/job/{match.group(2)}"
    # No id in the path: the query is dropped entirely. A search-results page
    # reaches this branch and should not become an identity.
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") or "/", "", ""))


def _to_raw(card: dict, source: str, description: str, *, full: bool) -> RawJob:
    safe_url = _job_url(card, source)
    # One posting, one row: the key drops query noise and survives a different
    # slug for the same jobstreet id.
    identity = _identity_url(safe_url)
    title = (card.get("title") or "").strip()[:TITLE_MAX]
    if not title:
        raise InvalidJob("missing title")
    return RawJob(
        source_job_id=f"browser_{_slug(identity)}",
        title=title,
        canonical_url=identity,
        # The URL is the job page the user was looking at, so it is a real link
        # and not an invented one. Apply still happens on Jobstreet: Gawe never
        # submits.
        apply_url=safe_url,
        description_html=_lines_to_html(description),
        location_raw=(card.get("location") or "").strip() or None,
        posted_at=(card.get("posted_at") or "").strip() or None,
        extra={
            "company": (card.get("company") or "").strip(),
            # A company taken from a slug is a guess; keep it visible as a gap.
            "company_from_slug": not (card.get("company") or "").strip(),
            "posted_at_unknown": not (card.get("posted_at") or "").strip(),
            # The detail page shows the full text, the card only a snippet. A
            # detail import must never be marked as snippet-only, or every
            # later rule trips over a gap that is not there.
            "snippet_only": not full and len(description) < MIN_DESCRIPTION_CHARS,
        },
    )


class BrowserImportService:
    def __init__(
        self,
        connection,
        discovery: DiscoveryService,
        tasks: TaskStore | None = None,
    ) -> None:
        self._connection = connection
        self._discovery = discovery
        self._profiles = discovery._profiles  # noqa: SLF001 - same package
        self._assessments = AssessmentService(connection, self._profiles)
        self._tasks = tasks or TaskStore(connection)

    def import_cards(self, source: str, page_url: str, cards: list[dict]) -> dict:
        if source not in ALLOWED_HOST_SUFFIXES:
            raise BrowserImportError("source_not_supported", "Sumber impor tidak didukung.")
        if not cards:
            raise BrowserImportError("nothing_to_import", "Tidak ada lowongan pada request.")
        if len(cards) > MAX_JOBS_PER_REQUEST:
            raise BrowserImportError(
                "too_many_jobs", f"Maksimal {MAX_JOBS_PER_REQUEST} lowongan per kirim."
            )
        self._check_page(page_url, source)
        return self._run(
            source,
            page_url,
            [(card, (card.get("snippet") or "").strip() or card.get("title") or "", False) for card in cards],
        )

    def import_detail(self, source: str, page_url: str, detail: dict) -> dict:
        """Full description for one job the user opened; updates the same row."""
        if source not in ALLOWED_HOST_SUFFIXES:
            raise BrowserImportError("source_not_supported", "Sumber impor tidak didukung.")
        self._check_page(page_url, source)
        description = (detail.get("description") or "").strip()
        if len(description) < MIN_DESCRIPTION_CHARS:
            raise BrowserImportError(
                "description_too_short",
                "Deskripsi lowongan tidak terbaca dari halaman ini.",
            )
        if len(description) > DESCRIPTION_MAX_CHARS:
            raise BrowserImportError(
                "description_too_long", "Deskripsi lowongan melebihi batas ukuran."
            )
        return self._run(source, page_url, [(detail, description, True)], match_existing=True)

    def _existing_by_title(self, card: dict) -> dict | None:
        """The stored card for this job, used only when the URL has no posting id.

        jobstreet detail pages can open with a query string instead of the slug,
        so the identity URL carries no id. Without this the detail import would
        store a second row for a job the card import already created. The
        location narrows the match, because two employers post the same title.
        """
        title = (card.get("title") or "").strip()
        if not title:
            return None
        rows = self._connection.execute(
            "SELECT job_id, canonical_url, location_json FROM job WHERE source_id = ? "
            "AND title = ? AND duplicate_of IS NULL ORDER BY created_at DESC LIMIT 5",
            (MANUAL_SOURCE_ID, title),
        ).fetchall()
        place = _location_key(card.get("location"))
        for row in rows:
            if _location_key(_raw_location(row["location_json"])) == place:
                return dict(row)
        return None

    def _resolve_identity(self, card: dict, source: str) -> dict:
        """Reuse the stored URL when the detail page URL has no posting id."""
        if JOBSTREET_ID.search(urlsplit(_job_url(card, source)).path):
            return card
        existing = self._existing_by_title(card)
        if existing is None:
            return card
        # The stored identity URL was validated when it was first imported.
        return {**card, "url": existing["canonical_url"]}

    def _check_page(self, page_url: str, source: str) -> None:
        try:
            page = _validate(page_url)
        except UnsafeUrl as exc:
            raise BrowserImportError("url_rejected", f"page_url ditolak: {exc}.") from exc
        if not _host_allowed((urlsplit(page).hostname or "").lower(), source):
            raise BrowserImportError("url_host_not_allowed", "page_url bukan host sumber.")

    def _run(
        self,
        source: str,
        page_url: str,
        entries: list[tuple[dict, str, bool]],
        *,
        match_existing: bool = False,
    ) -> dict:
        profile = self._profiles.require_confirmed()
        manual_source = SourceRegistry(self._connection).ensure_manual_source()
        fetched_at = now_iso()

        run_id = new_id("run")
        task_id = self._tasks.create("discovery", ["import"])["task_id"]
        with self._connection:
            self._connection.execute(
                "INSERT INTO discovery_run (run_id, task_id, profile_version_id, status, "
                "counts_json, error_json, started_at, finished_at) "
                "VALUES (?, ?, ?, 'processing', '{}', NULL, ?, NULL)",
                (run_id, task_id, profile["profile_version_id"], fetched_at),
            )
        self._tasks.start_stage(task_id, "import")

        job_ids: list[str] = []
        duplicates = 0
        created_any = False
        version_added = False
        rejected: list[dict] = []
        for index, (card, description, full) in enumerate(entries):
            try:
                if match_existing:
                    card = self._resolve_identity(card, source)
                raw = _to_raw(card, source, description, full=full)
                company = raw.extra.get("company") or "Jobstreet"
                record = normalize(raw, {**manual_source, "company": company}, fetched_at)
            except (InvalidJob, ValueError) as exc:
                rejected.append({"index": index, "reason": str(exc)})
                continue
            except UnsafeUrl as exc:
                rejected.append({"index": index, "reason": f"url_rejected: {exc}"})
                continue
            raw_sha = hashlib.sha256(raw.description_html.encode("utf-8")).hexdigest()
            created, job_id, new_version = self._discovery._store_job(  # noqa: SLF001
                record, raw_sha, fetched_at
            )
            if created:
                created_any = True
            else:
                duplicates += 1
            # Same dedupe every other path runs: without it an import that lands
            # on a different row for a known URL is invisible in the UI.
            link_duplicate(self._connection, job_id, record)
            version_added = version_added or new_version
            job_ids.append(job_id)

        counts = {
            "fetched": len(entries),
            "new_jobs": len(job_ids) - duplicates,
            "duplicates": duplicates,
            "updated": len(job_ids),
            "rejected": len(rejected),
        }
        assessment: dict | None = None
        assess_error: dict | None = None
        if job_ids:
            assessment, assess_error = self._discovery._assess(profile)  # noqa: SLF001
            if assessment:
                counts.update(
                    {
                        "eligible": assessment["eligible"],
                        "needs_review": assessment["needs_review"],
                        "ineligible": assessment["ineligible"],
                    }
                )
        status = "partial" if assess_error else "completed"
        with self._connection:
            self._connection.execute(
                "UPDATE discovery_run SET status = ?, counts_json = ?, error_json = ?, "
                "finished_at = ? WHERE run_id = ?",
                (
                    status,
                    json.dumps(counts),
                    json.dumps(assess_error) if assess_error else None,
                    now_iso(),
                    run_id,
                ),
            )
        self._tasks.finish_stage(task_id, "import")
        self._tasks.finish(task_id, status, result={"run_id": run_id, "counts": counts})

        return {
            "run_id": run_id,
            "accepted": counts["new_jobs"],
            "duplicates": duplicates,
            "rejected": len(rejected),
            "rejected_details": rejected[:20],
            "job_ids": job_ids,
            # The row was refreshed either way; `accepted` only counts a new job
            # or a new posting version, so say which happened.
            "updated": len(job_ids),
            # True when no row existed for this URL before, so the caller says
            # "new job" instead of claiming an update.
            "created": created_any,
            # True when the description became a new posting version. Importing
            # the same text twice adds none.
            "version_added": version_added,
            "eligibility": (
                self._assessments.eligibility_for(job_id, profile["profile_version_id"])
                if len(job_ids) == 1
                else None
            ),
        }
