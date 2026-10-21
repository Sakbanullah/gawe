from __future__ import annotations

from pathlib import Path

import keyring
import pytest

from gawe.config import ConfigError, load_config, resolve_api_key
from gawe.security.consent import key_source

from .conftest import CONFIG_TEMPLATE, TEST_SCHEMA


def test_loads_config(repo_root: Path) -> None:
    config = load_config(repo_root / "config.toml")
    assert config.server.host == "127.0.0.1"
    assert config.role_model("extract") == "model-x"
    assert config.database.host == "127.0.0.1"
    assert config.database.name.startswith("gawe_test_")
    assert "password" not in config.database.describe().lower()


def test_rejects_invalid_database_name(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(CONFIG_TEMPLATE.replace('name = "gawe_test', 'name = "bad-name'))
    with pytest.raises(ConfigError):
        load_config(path)


def test_rejects_reserved_database_name(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(CONFIG_TEMPLATE.replace(f'name = "{TEST_SCHEMA}"', 'name = "mysql"'))
    with pytest.raises(ConfigError):
        load_config(path)


def test_password_comes_from_environment(repo_root: Path, monkeypatch) -> None:
    monkeypatch.setenv("GAWE_DB_PASSWORD", "local-only-secret")
    config = load_config(repo_root / "config.toml")
    assert config.database.resolved_password == "local-only-secret"
    assert "local-only-secret" not in config.database.describe()
    assert "local-only-secret" not in str(config.snapshot())


def test_rejects_non_loopback_host(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(CONFIG_TEMPLATE.replace('host = "127.0.0.1"', 'host = "0.0.0.0"'))
    with pytest.raises(ConfigError):
        load_config(path)


def test_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(tmp_path / "absent.toml")


def test_rejects_model_io_logging(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(CONFIG_TEMPLATE.replace("log_model_io = false", "log_model_io = true"))
    with pytest.raises(ConfigError):
        load_config(path)


def test_key_source_never_returns_value(monkeypatch) -> None:
    monkeypatch.setenv("GAWE_TEST_KEY", "super-secret-value")
    assert key_source(None, "GAWE_TEST_KEY") == "env"
    assert key_source(None, "GAWE_ABSENT_KEY") == "missing"


# -- resolve_api_key --------------------------------------------------------
def test_resolve_api_key_prefers_keyring_over_env(monkeypatch) -> None:
    monkeypatch.setenv("GAWE_LLM_API_KEY", "synthetic-env-key")
    monkeypatch.setattr(keyring, "get_password", lambda service, name: "synthetic-keyring-key")
    assert resolve_api_key("gawe/llm/test") == "synthetic-keyring-key"


def test_resolve_api_key_falls_back_to_env(monkeypatch) -> None:
    monkeypatch.setenv("GAWE_LLM_API_KEY", "synthetic-env-key")
    monkeypatch.setattr(keyring, "get_password", lambda service, name: None)
    assert resolve_api_key("gawe/llm/test") == "synthetic-env-key"


def test_resolve_api_key_reads_env_without_a_ref(monkeypatch) -> None:
    monkeypatch.setenv("GAWE_LLM_API_KEY", "synthetic-env-key")

    def must_not_read(*args):
        raise AssertionError("keyring must not be read without api_key_ref")

    monkeypatch.setattr(keyring, "get_password", must_not_read)
    assert resolve_api_key(None) == "synthetic-env-key"


def test_resolve_api_key_returns_none_when_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("GAWE_LLM_API_KEY", raising=False)
    monkeypatch.setattr(keyring, "get_password", lambda service, name: None)
    assert resolve_api_key("gawe/llm/missing") is None
    assert resolve_api_key(None) is None


def test_resolve_api_key_survives_keyring_error(monkeypatch) -> None:
    monkeypatch.setenv("GAWE_LLM_API_KEY", "synthetic-env-key")

    def unavailable(service, name):
        raise RuntimeError("keyring backend unavailable")

    monkeypatch.setattr(keyring, "get_password", unavailable)
    assert resolve_api_key("gawe/llm/test") == "synthetic-env-key"


def test_resolve_api_key_uses_the_requested_env_var(monkeypatch) -> None:
    monkeypatch.delenv("GAWE_LLM_API_KEY", raising=False)
    monkeypatch.setenv("GAWE_TEST_ALT_KEY", "synthetic-alt-key")
    monkeypatch.setattr(keyring, "get_password", lambda service, name: None)
    assert resolve_api_key("gawe/llm/test", "GAWE_TEST_ALT_KEY") == "synthetic-alt-key"


def test_resolved_api_key_never_reaches_config_output(config, monkeypatch) -> None:
    secret = "synthetic-key-not-for-output"
    monkeypatch.setenv("GAWE_LLM_API_KEY", secret)
    resolved = resolve_api_key(None)
    if resolved != secret:
        pytest.fail("resolve_api_key did not return the configured environment key")
    for label, text in (
        ("config snapshot", str(config.snapshot())),
        ("config dump", config.model_dump_json()),
    ):
        if secret in text:
            pytest.fail(f"{label} contains the API key")
