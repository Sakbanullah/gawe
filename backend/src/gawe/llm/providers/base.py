"""Provider adapter contract.

Adapters translate the neutral request to one vendor API. Pipeline code never
imports a vendor SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class ProviderError(Exception):
    """Adapter error mapped to a stable internal code."""

    def __init__(self, code: str, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass
class Completion:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


@dataclass
class Call:
    role: str
    model: str
    messages: list[dict]
    temperature: float
    max_tokens: int
    timeout_s: int
    extra: dict = field(default_factory=dict)


class Provider(Protocol):
    provider_id: str

    def complete(self, call: Call) -> Completion: ...
