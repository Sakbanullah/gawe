"""Configuration loading and validation.

Config lives in TOML at the repository root (C6, decided 2026-10-19).
Secrets are never stored here; only keyring references.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

ROLES = ("extract", "classify", "write", "review")
ROLE_TEMPERATURE_RANGE = {
    "extract": (0.0, 0.2),
    "classify": (0.0, 0.2),
    "write": (0.3, 0.6),
    "review": (0.0, 0.3),
}
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


class ConfigError(Exception):
    """Config is missing or invalid. Startup must fail with a clear message."""


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)

    @field_validator("host")
    @classmethod
    def only_loopback(cls, value: str) -> str:
        if value not in LOOPBACK_HOSTS:
            raise ValueError("server.host must be loopback (127.0.0.1)")
        return value


class StorageConfig(BaseModel):
    data_dir: str = "data"
    profile_dir: str = "profile"
    logs_dir: str = "logs"


class DatabaseConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=3306, ge=1, le=65535)
    user: str = "root"
    password: SecretStr | None = None
    password_env: str = "GAWE_DB_PASSWORD"
    name: str = "gawe"
    charset: str = "utf8mb4"

    @field_validator("name")
    @classmethod
    def valid_schema_name(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", value):
            raise ValueError("database.name must be 1-64 letters, digits, or underscores")
        if value.lower() in {"mysql", "information_schema", "performance_schema", "sys"}:
            raise ValueError("database.name is reserved")
        return value

    @property
    def resolved_password(self) -> str:
        if self.password is not None:
            return self.password.get_secret_value()
        return os.environ.get(self.password_env, "")

    def describe(self) -> str:
        """Connection identity without the password."""
        return f"mysql://{self.user}@{self.host}:{self.port}/{self.name}"


class ProviderConfig(BaseModel):
    type: str = "openai_compatible"
    base_url: str | None = None
    api_key_ref: str | None = None
    capabilities: list[str] = Field(default_factory=list)


class LLMConfig(BaseModel):
    active_provider: str = "provider_a"
    default_timeout_s: int = Field(default=90, ge=1)
    max_retries: int = Field(default=1, ge=0, le=1)
    repair_json_once: bool = True
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    roles: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def roles_resolve(self) -> "LLMConfig":
        for role in ROLES:
            if role not in self.roles:
                raise ValueError(f"llm.roles.{role} is required")
        return self


class PrivacyConfig(BaseModel):
    cloud_consent_required: bool = True
    send_minimum_context: bool = True
    log_document_content: bool = False
    log_model_io: bool = False
    debug_model_io_redacted: bool = True

    @model_validator(mode="after")
    def no_content_logging(self) -> "PrivacyConfig":
        if self.log_document_content or self.log_model_io:
            raise ValueError(
                "privacy.log_document_content and privacy.log_model_io must stay false in v1"
            )
        return self


class RetentionConfig(BaseModel):
    job_cache_days: int = Field(default=90, ge=1)
    log_days: int = Field(default=30, ge=1)
    diagnostics_days: int = Field(default=7, ge=1)


class DiscoveryConfig(BaseModel):
    """Bounded parallelism for discovery runs."""

    max_workers: int = Field(default=3, ge=1, le=8)
    max_run_seconds: int = Field(default=600, ge=30, le=3600)
    # Off by default: a local app must not fetch boards until the operator asks.
    scheduler_enabled: bool = False
    schedule_interval_seconds: int = Field(default=900, ge=60, le=86_400)


class FrontendConfig(BaseModel):
    dist_dir: str = "frontend/dist"


class Config(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    frontend: FrontendConfig = Field(default_factory=FrontendConfig)
    source_path: Path | None = None
    root_dir: Path = Field(default_factory=Path.cwd)

    @property
    def data_dir(self) -> Path:
        return self.root_dir / self.storage.data_dir

    @property
    def profile_dir(self) -> Path:
        return self.root_dir / self.storage.profile_dir

    @property
    def logs_dir(self) -> Path:
        return self.root_dir / self.storage.logs_dir

    @property
    def dist_dir(self) -> Path:
        return self.root_dir / self.frontend.dist_dir

    def role_model(self, role: str) -> str:
        return self.llm.roles[role]

    def snapshot(self) -> dict:
        """Reproducibility metadata. Contains no secret values."""
        return {
            "provider": self.llm.active_provider,
            "roles": dict(self.llm.roles),
            "provider_config": {
                name: provider.model_dump()
                for name, provider in self.llm.providers.items()
            },
            "privacy": self.privacy.model_dump(),
        }


def resolve_api_key(
    api_key_ref: str | None, env_var: str = "GAWE_LLM_API_KEY"
) -> str | None:
    """Resolve a provider secret: keyring reference first, env fallback (D1).

    The value is returned to the adapter only. It is never logged or written
    to config.
    """
    if api_key_ref:
        try:
            import keyring

            value = keyring.get_password("gawe", api_key_ref)
        except Exception:
            value = None
        if value:
            return value
    return os.environ.get(env_var) or None


def default_config_path() -> Path:
    return Path(os.environ.get("GAWE_CONFIG", "config.toml")).resolve()


def load_config(path: Path | str | None = None) -> Config:
    config_path = Path(path) if path is not None else default_config_path()
    if not config_path.is_file():
        raise ConfigError(
            f"config file not found: {config_path}. "
            "Copy config.example.toml to config.toml first."
        )
    try:
        with config_path.open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {config_path}: {exc}") from exc
    try:
        config = Config.model_validate(raw)
    except ValueError as exc:
        raise ConfigError(f"invalid config in {config_path}: {exc}") from exc
    config.source_path = config_path
    config.root_dir = config_path.parent
    return config
