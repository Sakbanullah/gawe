from __future__ import annotations

import pytest

from gawe.security.url_guard import UnsafeUrl, validate_redirect_chain, validate_url

PUBLIC = {"example.com": ["93.184.216.34"]}


def resolver(host: str, port: int) -> list[str]:
    return PUBLIC.get(host, [])


def test_accepts_public_https() -> None:
    result = validate_url("https://example.com/jobs/1", resolver)
    assert result.host == "example.com"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/jobs",
        "https://user:pass@example.com/jobs",
        "https://127.0.0.1/jobs",
        "https://10.0.0.5/jobs",
        "https://192.168.1.10/jobs",
        "https://169.254.169.254/latest/meta-data",
        "https://localhost/jobs",
        "https://metadata.google.internal/computeMetadata/v1",
        "https://example.com:8080/jobs",
    ],
)
def test_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(UnsafeUrl):
        validate_url(url, resolver)


def test_rejects_hostname_resolving_to_private() -> None:
    with pytest.raises(UnsafeUrl):
        validate_url("https://internal.example.com/jobs", lambda host, port: ["10.1.2.3"])


def test_rejects_too_many_redirects() -> None:
    urls = [f"https://example.com/{index}" for index in range(7)]
    with pytest.raises(UnsafeUrl):
        validate_redirect_chain(urls, resolver)


def test_validates_every_redirect() -> None:
    with pytest.raises(UnsafeUrl):
        validate_redirect_chain(
            ["https://example.com/a", "https://127.0.0.1/b"], resolver
        )
