from __future__ import annotations

from gawe.logging import redact


def test_redacts_email_and_phone() -> None:
    text = redact("hubungi budi.santoso@example.com atau 081234567890")
    assert "budi.santoso@example.com" not in text
    assert "081234567890" not in text


def test_redacts_url_query() -> None:
    text = redact("fetch https://example.com/jobs?token=abc123&user=budi gagal")
    assert "token=abc123" not in text
    assert "user=budi" not in text


def test_redacts_secret_assignment() -> None:
    text = redact("api_key = sk-live-123456")
    assert "sk-live-123456" not in text
