"""Chromium session for `access_method = browser` sources.

Login is always manual and headed: the user types their own credentials and 2FA
into a Chromium window Gawe opened. Crawl runs headless on the same profile.
Gawe stores no password and answers no 2FA prompt.

A session is "alive" only as far as the last navigation proved: cookie expiry is
not announced by any site, so the only honest status is the outcome of a real
request. `visit()` reports what it saw in terms both the CLI and the run use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import profile

if TYPE_CHECKING:  # pragma: no cover - typing only
    from playwright.sync_api import BrowserContext, Page

NAV_TIMEOUT_MS = 30_000
# Real Chrome first, bundled Chromium second. Nothing here hides automation.
CHANNEL_ORDER: tuple[str | None, ...] = ("chrome", None)
LOGIN_URL_MARKERS = ("/login", "/signin", "/authwall", "/checkpoint", "/uas/")
BLOCK_TEXT_MARKERS = ("captcha", "verify you are human", "unusual traffic")
BLOCK_TITLE_MARKERS = ("just a moment", "attention required", "security check")


class BrowserUnavailable(RuntimeError):
    """Playwright or Chromium is not installed. Message is safe to show."""


@dataclass(frozen=True)
class Visit:
    """One navigation result. `state` is the only thing callers branch on."""

    state: str  # "ok" | "login_required" | "blocked"
    url: str
    html: str


@dataclass(frozen=True)
class SessionStatus:
    state: str  # "ok" | "login_required" | "blocked" | "no_profile"
    url: str | None
    message: str


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - depends on install
        raise BrowserUnavailable(
            "Playwright belum terpasang. Jalankan: pip install playwright"
        ) from exc
    return sync_playwright()


def _launch(playwright, *, headless: bool) -> "tuple[BrowserContext, object]":
    path = profile.profile_dir()
    path.mkdir(parents=True, exist_ok=True)
    # Real Chrome first: some sites refuse Playwright's bundled Chromium on
    # fingerprint alone. Falling back keeps the CLI usable without Chrome, and
    # the caller is told which one ran.
    errors: list[str] = []
    for channel in CHANNEL_ORDER:
        try:
            context = playwright.chromium.launch_persistent_context(
                str(path),
                headless=headless,
                locale="en-US",
                viewport={"width": 1280, "height": 900},
                **({"channel": channel} if channel else {}),
            )
        except Exception as exc:  # noqa: BLE001 - channel missing or profile locked
            errors.append(f"{channel or 'chromium'}: {type(exc).__name__}")
            continue
        context.set_default_timeout(NAV_TIMEOUT_MS)
        return context, (channel or "chromium")
    raise BrowserUnavailable(
        "Browser tidak dapat dibuka (" + ", ".join(errors) + "). "
        "Jalankan: playwright install chromium"
    )


def classify(url: str, html: str, title: str = "") -> str:
    """Map a loaded page to `ok`, `login_required`, or `blocked`."""
    lowered_url = (url or "").lower()
    if any(marker in lowered_url for marker in LOGIN_URL_MARKERS):
        return "login_required"
    lowered_title = (title or "").lower()
    if any(marker in lowered_title for marker in BLOCK_TITLE_MARKERS):
        return "blocked"
    lowered_html = (html or "").lower()
    if any(marker in lowered_html for marker in BLOCK_TEXT_MARKERS):
        return "blocked"
    return "ok"


def _visit_page(page: "Page", url: str) -> Visit:
    page.goto(url, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
    html = page.content()
    return Visit(
        state=classify(page.url, html, page.title()),
        url=page.url,
        html=html,
    )


def visit(url: str, *, headless: bool = True) -> Visit:
    """Open one page with the stored profile."""
    with _playwright() as playwright:
        context, _browser = _launch(playwright, headless=headless)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            return _visit_page(page, url)
        finally:
            context.close()


def status(url: str) -> SessionStatus:
    """Prove the session by loading `url`. No profile means no session."""
    if not profile.exists():
        return SessionStatus(
            state="no_profile",
            url=None,
            message="Belum ada profil browser. Jalankan `gawe browser login <url>`.",
        )
    try:
        visited = visit(url)
    except BrowserUnavailable as exc:
        return SessionStatus(state="blocked", url=None, message=str(exc))
    message = {
        "ok": "Sesi aktif.",
        "login_required": "Sesi habis. Jalankan `gawe browser login <url>` lagi.",
        "blocked": (
            "Situs menolak browser otomatis. Login ulang tidak membantu; "
            "ganti situs atau hentikan sumber ini."
        ),
    }[visited.state]
    return SessionStatus(state=visited.state, url=visited.url, message=message)


def login(url: str) -> int:
    """Open Chromium headed and keep it open until the user closes it."""
    with _playwright() as playwright:
        context, _browser = _launch(playwright, headless=False)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
            print("Login di jendela Chromium. Tutup jendela bila selesai.")
            page.wait_for_event("close", timeout=0)
            return 0
        except Exception:  # noqa: BLE001 - closing the window ends the wait
            return 0
        finally:
            context.close()
