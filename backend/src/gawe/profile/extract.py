"""Profile extraction with the `extract` role.

The pipeline only knows the role. Provider/model come from config. With the
fake/synthetic provider no network call happens; the validator still runs.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..ingest.types import DocumentText
from ..llm.client import LLMClient, LLMContractError
from ..llm.prompts import load_prompt as _load_prompt
from .merge import detect_conflicts
from .validate import validate_extraction

FALLBACK_PROMPT = (
    "Extract candidate profile facts from the CV text inside <untrusted> tags. "
    "Every fact needs an evidence quote copied from the source. Return one JSON object."
)

RESPONSE_SCHEMA = {
    "type": "object",
    "required": [
        "personal",
        "education",
        "experience",
        "skills",
        "evidence_index",
    ],
    "properties": {
        "personal": {"type": "object"},
        "education": {"type": "array"},
        "experience": {"type": "array"},
        "skills": {"type": "array"},
        "projects": {"type": "array"},
        "certifications": {"type": "array"},
        "languages": {"type": "array"},
        "awards": {"type": "array"},
        "work_authorization": {"type": "array"},
        "work_preferences": {"type": "object"},
        "evidence_index": {"type": "object"},
        "conflicts": {"type": "array"},
    },
}

FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

# A real multi-page CV extracts to more than 4000 completion tokens; truncation
# then yields unparseable JSON. 8000 covers the largest fixture observed.
MAX_TOKENS = 8000


def load_prompt(root_dir: Path) -> tuple[str, str, str]:
    """Return (prompt_id, prompt_version, body) for the `extract` role."""
    return _load_prompt(root_dir, "extract_profile", FALLBACK_PROMPT)


def locator_text(document: DocumentText) -> str:
    lines = []
    for block in document.blocks:
        lines.append(f"{block.block_id} | {block.text}")
    return "\n".join(lines)


def extract_profile(
    client: LLMClient,
    document: DocumentText,
    doc_id: str,
    prompt_body: str,
    prompt_id: str,
    prompt_version: str,
    active_content: dict | None,
) -> tuple[dict, dict, list[dict], dict]:
    messages = [
        {"role": "system", "content": prompt_body},
        {
            "role": "user",
            "content": "<untrusted>\n" + locator_text(document) + "\n</untrusted>",
        },
    ]
    try:
        result = client.generate(
            role="extract",
            messages=messages,
            response_schema=RESPONSE_SCHEMA,
            temperature=0.0,
            max_tokens=MAX_TOKENS,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
        )
    except LLMContractError as exc:
        raise ExtractionError(exc.code, exc.retryable) from exc

    content, evidence, conflicts, report = validate_extraction(
        result.object, document.text, doc_id
    )
    detected = detect_conflicts(content, active_content)
    metadata = result.metadata.as_dict()
    metadata["validation"] = report.as_dict()
    return content, evidence, conflicts + detected, metadata


class ExtractionError(Exception):
    def __init__(self, code: str, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
