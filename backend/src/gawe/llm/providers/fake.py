"""Fake provider for tests and Phase 1.

No network. Returns queued synthetic text. Can emit invalid JSON or invalid
schema output to exercise error paths.
"""

from __future__ import annotations

import json

from .base import Call, Completion, ProviderError


class FakeProvider:
    """Queue-based provider. One queued reply per call, in order.

    `by_role` lets a test answer write and review differently without counting
    calls; the queue stays authoritative when both are supplied.
    """

    provider_id = "fake"

    def __init__(
        self,
        responses: list[str] | None = None,
        default: object | None = None,
        by_role: dict[str, object] | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.default = {"ok": True} if default is None else default
        self.by_role = dict(by_role or {})
        self.calls: list[Call] = []

    def complete(self, call: Call) -> Completion:
        self.calls.append(call)
        if self.responses:
            text = self.responses.pop(0)
        elif call.role in self.by_role:
            text = json.dumps(self.by_role[call.role])
        else:
            text = json.dumps(self.default)
        return Completion(text=text, input_tokens=len(str(call.messages)), output_tokens=len(text))

    def fail(self, code: str = "provider_unavailable", retryable: bool = True) -> None:
        self.responses.insert(0, json.dumps({"__error__": code, "__retryable__": retryable}))

    def complete_raising(self, call: Call) -> Completion:
        raise ProviderError("provider_unavailable", retryable=True)
