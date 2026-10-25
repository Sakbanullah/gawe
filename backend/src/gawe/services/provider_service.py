"""Provider settings: read, edit, and test the LLM endpoint from the browser.

Two things are edited here, and they are stored differently on purpose:

- `base_url`, provider id, and role models live in `config.toml`, the same file a
  person would edit by hand. The write is atomic (`os.replace`) and only touches
  the `[llm*]` tables; every other section keeps its text.
- The API key goes to Windows Credential Manager through `keyring`, under the
  provider's `api_key_ref`. It is never written to config, the database, a log,
  or a response.

D24 (2026-10-25) allows the browser form to send a key because the backend is
bound to `127.0.0.1` and every mutating route is CSRF-guarded. The key still
never travels back out.
"""

from __future__ import annotations

import json
import os
import re
import socket
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from ..config import Config, ProviderConfig, resolve_api_key
from ..security.consent import key_source

ROLES = ("extract", "classify", "write", "review")
KEYRING_SERVICE = "gawe"
PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
KEY_REF_RE = re.compile(r"^[A-Za-z0-9_./-]{1,100}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9_.:/@+-]{1,120}$")
DEFAULT_KEY_REF = "gawe/llm/provider"
TEST_TIMEOUT_S = 10
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


class ProviderSettingsError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def check_base_url(value: str) -> str:
    """An endpoint is a public HTTPS URL without credentials, query, or fragment."""
    text = (value or "").strip()
    parts = urlsplit(text)
    if parts.scheme.lower() != "https" or not parts.hostname:
        raise ProviderSettingsError("invalid_base_url", "Endpoint harus URL https lengkap.")
    if parts.username or parts.password:
        raise ProviderSettingsError(
            "invalid_base_url", "Endpoint tidak boleh memuat kredensial."
        )
    if parts.query or parts.fragment:
        raise ProviderSettingsError(
            "invalid_base_url", "Endpoint tidak boleh memuat query atau fragmen."
        )
    host = parts.hostname.lower()
    if host in LOCAL_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        raise ProviderSettingsError(
            "invalid_base_url",
            "Endpoint lokal ditolak; provider harus layanan publik lewat https.",
        )
    return text.rstrip("/")


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_llm_section(config: Config) -> str:
    llm = config.llm
    lines = [
        "[llm]",
        f"active_provider = {_toml_string(llm.active_provider)}",
        f"default_timeout_s = {llm.default_timeout_s}",
        f"max_retries = {llm.max_retries}",
        f"repair_json_once = {'true' if llm.repair_json_once else 'false'}",
        "",
        "[llm.roles]",
    ]
    lines += [f"{role} = {_toml_string(llm.roles[role])}" for role in ROLES]
    lines.append("")
    for name, provider in llm.providers.items():
        lines.append(f"[llm.providers.{name}]")
        lines.append(f"type = {_toml_string(provider.type)}")
        if provider.base_url:
            lines.append(f"base_url = {_toml_string(provider.base_url)}")
        if provider.api_key_ref:
            lines.append(f"api_key_ref = {_toml_string(provider.api_key_ref)}")
        if provider.capabilities:
            caps = ", ".join(_toml_string(item) for item in provider.capabilities)
            lines.append(f"capabilities = [{caps}]")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def replace_llm_section(text: str, config: Config) -> str:
    """Rewrite only the `[llm*]` tables; every other line stays as it was."""
    kept: list[str] = []
    skipping = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            skipping = stripped.startswith("[llm")
            if skipping:
                continue
        if skipping:
            continue
        kept.append(line)
    body = "\n".join(kept).rstrip()
    return (body + "\n\n" if body else "") + render_llm_section(config)


def write_config(path: Path, config: Config) -> None:
    """Atomic, and validated before it lands: a broken config never replaces a good one."""
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    updated = replace_llm_section(text, config)
    tomllib.loads(updated)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(updated, encoding="utf-8")
    os.replace(tmp, path)


def key_writable() -> bool:
    """True when a real keyring backend is installed, not the null fallback."""
    try:
        import keyring

        backend = keyring.get_keyring()
        return backend is not None and "fail" not in type(backend).__name__.lower()
    except Exception:
        return False


class ProviderSettingsService:
    def __init__(self, config: Config) -> None:
        self._config = config

    def read(self) -> dict:
        llm = self._config.llm
        provider = llm.providers.get(llm.active_provider)
        return {
            "provider_id": llm.active_provider,
            "configured": bool(provider and provider.base_url),
            "base_url": provider.base_url if provider else None,
            "roles": {role: {"model": llm.roles.get(role)} for role in ROLES},
            "key_source": key_source(provider.api_key_ref if provider else None),
            "key_writable": key_writable(),
            "providers": sorted(llm.providers),
        }

    def update(
        self,
        provider_id: str,
        base_url: str,
        roles: dict[str, str],
        api_key: str | None = None,
        api_key_ref: str | None = None,
    ) -> dict:
        if not PROVIDER_ID_RE.fullmatch(provider_id):
            raise ProviderSettingsError(
                "invalid_provider_id", "Nama provider hanya huruf, angka, titik, garis."
            )
        clean_url = check_base_url(base_url)
        models: dict[str, str] = {}
        for role in ROLES:
            model = (roles.get(role) or "").strip()
            if not model:
                raise ProviderSettingsError(
                    "invalid_model", f"Model untuk role {role} wajib diisi."
                )
            if not MODEL_RE.fullmatch(model):
                raise ProviderSettingsError(
                    "invalid_model", f"Model untuk role {role} tidak valid."
                )
            models[role] = model

        llm = self._config.llm
        existing = llm.providers.get(provider_id) or ProviderConfig()
        ref = (api_key_ref or existing.api_key_ref or DEFAULT_KEY_REF).strip()
        if not KEY_REF_RE.fullmatch(ref):
            raise ProviderSettingsError("invalid_key_ref", "Nama referensi key tidak valid.")
        new_key = (api_key or "").strip()
        if len(new_key) > 512:
            raise ProviderSettingsError("invalid_api_key", "API key terlalu panjang.")

        previous = self._config.model_copy(deep=True)
        llm.providers[provider_id] = ProviderConfig(
            type=existing.type or "openai_compatible",
            base_url=clean_url,
            api_key_ref=ref,
            capabilities=existing.capabilities or ["chat"],
        )
        llm.active_provider = provider_id
        llm.roles = models

        if new_key:
            try:
                import keyring

                keyring.set_password(KEYRING_SERVICE, ref, new_key)
            except Exception as exc:
                self._config = previous
                raise ProviderSettingsError(
                    "keyring_unavailable",
                    "Tidak dapat menulis API key ke Windows Credential Manager.",
                    500,
                ) from exc

        path = self._config.source_path
        if path is not None:
            try:
                write_config(Path(path), self._config)
            except Exception as exc:
                self._config = previous
                raise ProviderSettingsError(
                    "config_write_failed", "Gagal menyimpan config.toml.", 500
                ) from exc
        return self.read()

    def test_connection(self) -> dict:
        """One `GET /models` against the configured endpoint.

        No candidate data is sent, so no consent is needed: only the URL and the
        Authorization header leave this machine.
        """
        llm = self._config.llm
        provider = llm.providers.get(llm.active_provider)
        if provider is None or not provider.base_url:
            raise ProviderSettingsError(
                "provider_not_configured", "Endpoint belum diisi.", 409
            )
        key = resolve_api_key(provider.api_key_ref)
        if not key:
            raise ProviderSettingsError(
                "api_key_missing", "API key belum tersimpan untuk provider ini.", 409
            )
        request = urllib.request.Request(
            f"{provider.base_url}/models",
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            method="GET",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=TEST_TIMEOUT_S) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ProviderSettingsError(
                    "test_unauthorized", "Endpoint menolak API key (401/403).", 400
                ) from exc
            raise ProviderSettingsError(
                "test_failed", f"Endpoint menjawab HTTP {exc.code}.", 400
            ) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise ProviderSettingsError(
                "test_timeout", "Endpoint tidak menjawab dalam 10 detik.", 400
            ) from exc
        except urllib.error.URLError as exc:
            raise ProviderSettingsError(
                "test_unreachable", "Endpoint tidak dapat dihubungi.", 400
            ) from exc
        except ValueError as exc:
            raise ProviderSettingsError(
                "test_invalid_response", "Respons endpoint bukan JSON.", 400
            ) from exc
        elapsed = int((time.monotonic() - started) * 1000)
        models = [
            item.get("id")
            for item in (body.get("data") or [])
            if isinstance(item, dict) and item.get("id")
        ]
        return {
            "ok": True,
            "latency_ms": elapsed,
            "model_count": len(models),
            "models": models[:50],
            "key_source": key_source(provider.api_key_ref),
        }
