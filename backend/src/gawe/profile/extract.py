"""Profile extraction with the `extract` role.

The pipeline only knows the role. Provider/model come from config. With the
fake/synthetic provider no network call happens; the validator still runs.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..ingest.types import DocumentText
from ..llm.client import LLMClient, LLMContractError
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


def load_prompt(root_dir: Path) -> tuple[str, str, str]:
    """Return (prompt_id, prompt_version, body)."""
    path = root_dir / "docs" / "phase-00" / "prompts" / "extract_profile.md"
    if not path.is_file():
        return "extract_profile", "0", FALLBACK_PROMPT
    raw = path.read_text(encoding="utf-8")
    prompt_id, version = "extract_profile", "0"
    body = raw
    match = FRONT_MATTER_RE.match(raw)
    if match:
        body = raw[match.end():]
        for line in match.group(1).splitlines():
            key, _, value = line.partition(":")
            if key.strip() == "prompt_id":
                prompt_id = value.strip()
            elif key.strip() == "version":
                version = value.strip()
    return prompt_id, version, body


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
            max_tokens=4000,
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
