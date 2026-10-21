"""Manual URL fallback: one job page pasted by the user.

Not a crawler. One URL, one fetch, no links followed. `robots.txt` is checked
before the page is fetched (JOB-DISCOVERY.md §10), and the URL goes through the
same guard as discovery. The parsed page is untrusted data.
"""

from __future__ import annotations

from html.parser import HTMLParser

from .base import AdapterError, RawJob, html_to_text

SOURCE_ID = "manual_url"
COMPANY = "Manual URL"
_META = {"og:title", "og:site_name", "og:description", "twitter:title"}
_TITLE_TAGS = {"h1"}


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self.headings: list[str] = []
        self._capture: str | None = None
        self._buffer: list[str] = []
        self._skip = 0
        self._json_ld: list[str] = []
        self._in_json_ld = False

    def handle_starttag(self, tag, attrs):
        attributes = {key: value for key, value in attrs if value}
        if tag in {"script", "style"}:
            if (attributes.get("type") or "").lower() == "application/ld+json":
                self._in_json_ld = True
                self._json_ld.append("")
            else:
                self._skip += 1
        elif tag == "meta":
            name = (attributes.get("property") or attributes.get("name") or "").lower()
            if name in _META and attributes.get("content"):
                self.meta.setdefault(name, attributes["content"])
        elif tag == "title":
            self._capture = "title"
            self._buffer = []
        elif tag in _TITLE_TAGS:
            self._capture = "h1"
            self._buffer = []

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            if self._in_json_ld and tag == "script":
                self._in_json_ld = False
            elif self._skip:
                self._skip -= 1
        elif tag == "title" and self._capture == "title":
            self.title = " ".join(self._buffer).strip()
            self._capture = None
        elif tag in _TITLE_TAGS and self._capture == "h1":
            text = " ".join(self._buffer).strip()
            if text:
                self.headings.append(text)
            self._capture = None

    def handle_data(self, data):
        if self._in_json_ld:
            self._json_ld[-1] += data
            return
        if self._skip:
            return
        if self._capture:
            self._buffer.append(data)

    @property
    def json_ld(self) -> str:
        return "".join(self._json_ld)


def _split_title(title: str) -> tuple[str | None, str | None]:
    """`Role - Company` / `Role at Company` / `Role | Company` -> (role, company)."""
    for separator in (" at ", " - ", " – ", " | ", " — "):
        if separator in title:
            left, _, right = title.partition(separator)
            if left.strip() and right.strip():
                return left.strip(), right.strip()
    return title.strip() or None, None


def parse(body: str, url: str) -> RawJob:
    parser = _PageParser()
    try:
        parser.feed(body or "")
        parser.close()
    except Exception as exc:  # noqa: BLE001 - malformed HTML is a source error
        raise AdapterError("manual page could not be parsed") from exc

    posting = _job_posting(parser.json_ld)
    title = posting.get("title") or parser.meta.get("og:title") or parser.title
    company = posting.get("company") or parser.meta.get("og:site_name")
    if title and not company:
        title, company = _split_title(title)
    if not title and parser.headings:
        title = parser.headings[0]
    if not title:
        raise AdapterError("manual page has no title")
    if company:
        title = _strip_company(title, company)

    description_html = posting.get("description") or body or ""
    description = html_to_text(description_html)
    if len(description) < 40:
        raise AdapterError("manual page has no readable description")

    return RawJob(
        source_job_id=_stable_id(url),
        title=title[:300],
        canonical_url=url,
        description_html=description_html,
        location_raw=posting.get("location"),
        extra={"company": company},
    )


def _job_posting(json_ld: str) -> dict:
    """Read a schema.org JobPosting block when the page publishes one."""
    import json

    if not json_ld.strip():
        return {}
    try:
        payload = json.loads(json_ld)
    except json.JSONDecodeError:
        return {}
    items = payload if isinstance(payload, list) else [payload]
    for item in items:
        if not isinstance(item, dict):
            continue
        graph = item.get("@graph")
        candidates = graph if isinstance(graph, list) else [item]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            kind = candidate.get("@type")
            kinds = kind if isinstance(kind, list) else [kind]
            if "JobPosting" not in kinds:
                continue
            organisation = candidate.get("hiringOrganization") or {}
            location = candidate.get("jobLocation") or {}
            if isinstance(location, list):
                location = location[0] if location else {}
            address = (location or {}).get("address") or {}
            parts = [
                address.get("addressLocality"),
                address.get("addressRegion"),
                address.get("addressCountry"),
            ]
            return {
                "title": candidate.get("title"),
                "company": organisation.get("name") if isinstance(organisation, dict) else None,
                "description": candidate.get("description"),
                "location": ", ".join(str(part) for part in parts if part) or None,
            }
    return {}


def _strip_company(title: str, company: str) -> str:
    """`Senior Engineer - Acme` with company `Acme` -> `Senior Engineer`."""
    for separator in (" - ", " – ", " | ", " — ", " at "):
        suffix = f"{separator}{company}"
        if title.lower().endswith(suffix.lower()):
            return title[: -len(suffix)].strip()
    return title


def _stable_id(url: str) -> str:
    import hashlib

    return "manual_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def company_of(raw: RawJob) -> str:
    value = (raw.extra or {}).get("company")
    if value and value.strip():
        return value.strip()
    return COMPANY
