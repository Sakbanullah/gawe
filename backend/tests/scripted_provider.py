"""Scripted LLM provider shared by the document tests.

Kept out of `test_documents_ai.py` because both document test modules need it,
and `test_documents_ai` imports the helpers from `test_documents`.
"""

from __future__ import annotations

import json
import re

from gawe.documents import draft
from gawe.llm.providers.base import Completion
from gawe.llm.providers.synthetic import SyntheticExtractProvider

BLOCK_RE = re.compile(r"<untrusted>\s*(.*?)\s*</untrusted>", re.DOTALL)


class ScriptedProvider:
    """Answers `write` with a real draft, `review` with a queued report.

    `extract` is delegated to the synthetic provider so the setup path still
    produces a confirmed profile without a network call.
    """

    provider_id = "fake"

    def __init__(self, reviews: list[dict], mutate=None) -> None:
        self.reviews = list(reviews)
        self.mutate = mutate
        self.calls = []
        self._extract = SyntheticExtractProvider()

    def complete(self, call) -> Completion:
        self.calls.append(call)
        if call.role == "extract":
            return self._extract.complete(call)
        blocks = BLOCK_RE.findall(call.messages[-1].get("content", ""))
        if call.role == "review":
            report = self.reviews.pop(0) if self.reviews else _pass_report()
            return Completion(text=json.dumps(report), input_tokens=10, output_tokens=10)
        profile = json.loads(blocks[1])
        job_payload = json.loads(blocks[0])
        kind = "cover_letter" if '"kind": "cover_letter"' in json.dumps(blocks[3]) else "cv"
        content = draft.build(kind, profile, job_payload, "en")
        # `missing` is service-computed and not part of the model's schema.
        content.pop("missing", None)
        if self.mutate is not None:
            self.mutate(content)
        return Completion(text=json.dumps(content), input_tokens=10, output_tokens=10)


def _pass_report(score: float = 8.4) -> dict:
    return {
        "verdict": "pass",
        "overall_score": score,
        "dimension_scores": {
            "clarity": score,
            "relevance": score,
            "credibility": score,
            "differentiation": score,
            "professional_quality": score,
        },
        "findings": [],
    }
