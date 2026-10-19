"""OpenAI-compatible HTTP adapter for the configured provider (D1: 9Router).

No live call is made in the default test suite. The live check is opt-in:
`tests/test_live_9router.py`.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

from .base import Call, Completion, ProviderError


class OpenAICompatibleProvider:
    provider_id = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        provider_id: str = "openai_compatible",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        # Configured provider id, not the adapter type, so llm_call records
        # which configured provider was used (llm-client.md §3).
        self.provider_id = provider_id

    def complete(self, call: Call) -> Completion:
        body = json.dumps(
            {
                "model": call.model,
                "messages": call.messages,
                "temperature": call.temperature,
                "max_tokens": call.max_tokens,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=call.timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (socket.timeout, TimeoutError) as exc:
            raise ProviderError("provider_timeout", retryable=True) from exc
        except urllib.error.HTTPError as exc:
            code = "provider_rate_limited" if exc.code == 429 else "provider_unavailable"
            raise ProviderError(code, retryable=exc.code == 429) from exc
        except urllib.error.URLError as exc:
            raise ProviderError("provider_unavailable", retryable=True) from exc
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("output_invalid_json") from exc
        usage = payload.get("usage") or {}
        return Completion(
            text=text,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            cost_usd=None,
        )
