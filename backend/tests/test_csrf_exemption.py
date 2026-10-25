"""The CSRF exemption must cover one POST only.

`/api/import/browser` skips the SPA CSRF pair because a chrome-extension page
cannot hold the session cookie. Exempting the path alone would also drop the
check from any future GET/PUT handler added under it.
"""

from __future__ import annotations

from gawe.api import app as app_module


class _Request:
    def __init__(self, path: str, method: str) -> None:
        self.url = type("Url", (), {"path": path})()
        self.method = method


def test_extension_import_exempts_only_a_post_to_its_own_path() -> None:
    assert app_module._is_extension_import(_Request("/api/import/browser", "POST"))
    assert not app_module._is_extension_import(_Request("/api/import/browser", "GET"))
    assert not app_module._is_extension_import(_Request("/api/import/browser", "PUT"))
    assert not app_module._is_extension_import(_Request("/api/import/browser/other", "POST"))
    assert not app_module._is_extension_import(_Request("/api/jobs", "POST"))
