"""Provider-agnostic LLM gateway.

Pipeline code calls `generate(role=...)`. It never names a provider or model.
Provider/model values come from config (D1: 9Router via `openai_compatible`).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import jsonschema

from ..config import ROLE_TEMPERATURE_RANGE, Config
from .providers.base import Call, Provider, ProviderError

logger = logging.getLogger(__name__)

INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore (all |any )?(previous|above) instructions"),
    re.compile(r"(?i)disregard (the )?(system|previous) prompt"),
    re.compile(r"(?i)you are now (a|an) "),
    re.compile(r"(?i)system prompt:"),
]

REPAIR_INSTRUCTION = (
    "Your previous reply was not valid JSON for the required schema. "
    "Return only a JSON value that matches the schema. Do not add commentary."
)

_FENCE_RE = re.compile(r"^\s*```[A-Za-z0-9_-]*\s*\n(.*?)\n?\s*```\s*$", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    """Accept a fenced JSON block: some providers wrap JSON in markdown."""
    match = _FENCE_RE.match(text)
    return match.group(1) if match else text


class LLMContractError(Exception):
    def __init__(self, code: str, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass
class LLMMetadata:
    provider: str
    model: str
    role: str
    prompt_id: str
    prompt_version: str
    prompt_hash: str
    response_hash: str
    temperature: float
    max_tokens: int
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    latency_ms: int
    attempt: int
    repaired: bool
    config_snapshot_id: str
    injection_suspected: bool

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class LLMResult:
    object: dict
    metadata: LLMMetadata


@dataclass
class LLMClient:
    config: Config
    provider: Provider
    consent_store: Any = None
    connection: Any = None
    sleep: Callable[[float], None] = time.sleep

    def _provider_id(self) -> str:
        return getattr(self.provider, "provider_id", self.config.llm.active_provider)

    def _snapshot_id(self) -> str:
        blob = json.dumps(self.config.snapshot(), sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _log_call(self, run_id: str | None, metadata: LLMMetadata, error_code: str | None) -> None:
        logger.info(
            "llm_call role=%s provider=%s model=%s prompt_hash=%s response_hash=%s "
            "input_tokens=%s output_tokens=%s cost_usd=%s latency_ms=%s attempt=%s "
            "repaired=%s error=%s",
            metadata.role,
            metadata.provider,
            metadata.model,
            metadata.prompt_hash,
            metadata.response_hash,
            metadata.input_tokens,
            metadata.output_tokens,
            metadata.cost_usd,
            metadata.latency_ms,
            metadata.attempt,
            metadata.repaired,
            error_code or "none",
        )
        if self.connection is None:
            return
        with self.connection:
            self.connection.execute(
                "INSERT INTO llm_call (call_id, run_id, role, provider, model, prompt_id, "
                "prompt_hash, response_hash, input_tokens, output_tokens, cost_usd, latency_ms, "
                "attempt, repaired, error_code, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    run_id,
                    metadata.role,
                    metadata.provider,
                    metadata.model,
                    metadata.prompt_id,
                    metadata.prompt_hash,
                    metadata.response_hash,
                    metadata.input_tokens,
                    metadata.output_tokens,
                    metadata.cost_usd,
                    metadata.latency_ms,
                    metadata.attempt,
                    int(metadata.repaired),
                    error_code,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def generate(
        self,
        role: str,
        messages: list[dict],
        response_schema: dict,
        temperature: float,
        max_tokens: int,
        timeout_s: int | None = None,
        request_id: str | None = None,
        prompt_id: str = "adhoc",
        prompt_version: str = "0",
    ) -> LLMResult:
        if role not in ROLE_TEMPERATURE_RANGE:
            raise LLMContractError("provider_not_configured")
        low, high = ROLE_TEMPERATURE_RANGE[role]
        if not low <= temperature <= high:
            raise LLMContractError("output_validation_failed")
        if role not in self.config.llm.roles:
            raise LLMContractError("provider_not_configured")
        if self.config.privacy.cloud_consent_required and self.consent_store is not None:
            try:
                self.consent_store.require()
            except Exception as exc:
                raise LLMContractError("consent_required") from exc

        model = self.config.llm.roles[role]
        timeout = timeout_s or self.config.llm.default_timeout_s
        prompt_hash = hashlib.sha256(
            json.dumps(messages, sort_keys=True).encode("utf-8")
        ).hexdigest()
        injection = any(
            pattern.search(content)
            for message in messages
            for content in [message.get("content")]
            if isinstance(content, str)
            for pattern in INJECTION_PATTERNS
        )

        attempts = 0
        repaired = False
        last_error: LLMContractError | None = None
        while attempts <= self.config.llm.max_retries:
            attempts += 1
            started = time.monotonic()
            try:
                completion = self.provider.complete(
                    Call(
                        role=role,
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout_s=timeout,
                    )
                )
            except ProviderError as exc:
                last_error = LLMContractError(exc.code, exc.retryable)
                if exc.retryable and attempts <= self.config.llm.max_retries:
                    self.sleep(0.2 * attempts)
                    continue
                raise last_error from exc

            text = completion.text
            try:
                parsed = json.loads(_strip_code_fence(text))
            except json.JSONDecodeError:
                if self.config.llm.repair_json_once and not repaired:
                    repaired = True
                    messages = messages + [
                        {"role": "assistant", "content": text},
                        {"role": "user", "content": REPAIR_INSTRUCTION},
                    ]
                    continue
                last_error = LLMContractError("output_invalid_json")
                raise last_error

            try:
                jsonschema.validate(parsed, response_schema)
            except jsonschema.ValidationError as exc:
                last_error = LLMContractError("output_schema_invalid")
                raise last_error from exc

            metadata = LLMMetadata(
                provider=self._provider_id(),
                model=model,
                role=role,
                prompt_id=prompt_id,
                prompt_version=prompt_version,
                prompt_hash=prompt_hash,
                response_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                temperature=temperature,
                max_tokens=max_tokens,
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
                cost_usd=completion.cost_usd,
                latency_ms=int((time.monotonic() - started) * 1000),
                attempt=attempts,
                repaired=repaired,
                config_snapshot_id=self._snapshot_id(),
                injection_suspected=injection,
            )
            self._log_call(request_id, metadata, None)
            return LLMResult(object=parsed, metadata=metadata)

        raise last_error or LLMContractError("provider_unavailable", retryable=True)
