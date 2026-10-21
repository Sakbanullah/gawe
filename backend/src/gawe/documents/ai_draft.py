"""LLM writer for tailored documents, with the deterministic draft as fallback.

The `write` role must return the same JSON shape as `draft.build()`, because
`render.py`, `factcheck.py`, `diff_against_profile`, and the export path already
consume that shape.

The model writes prose only. Identity fields (`header`, `target`, ids, schema
markers) come from trusted data: a wrong email or a wrong company would reach a
recruiter before anyone reads the review.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..llm.client import LLMClient, LLMContractError
from ..llm.prompts import PromptNotFound, load_prompt, load_prompt_with_schema, load_schema, render
from . import draft

logger = logging.getLogger(__name__)

PROMPT_IDS = {"cv": "write_cv", "cover_letter": "write_cover_letter"}
# A full CV with bullets needs more than 4000 completion tokens; the extract role
# hit the same wall (see profile/extract.py).
MAX_TOKENS = 8000
# The model may report gaps, but they are not document content: `draft` owns
# `missing`, and a stray `gaps` key would break the stored content shape.
_DROP_KEYS = {"gaps", "missing"}


class DraftError(Exception):
    """The `write` role failed before any model output could be used."""

    def __init__(self, code: str, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


def write(
    client: LLMClient,
    root_dir: Path,
    kind: str,
    profile_content: dict,
    evidence_index: dict,
    job: dict,
    language: str,
    revision_instructions: str = "",
) -> tuple[dict, dict]:
    """Return (content, metadata).

    `metadata["source"]` is `"llm"` or `"fallback"`. On fallback it also carries
    `fallback_code`, so the caller records why the deterministic draft was used
    instead of pretending the model wrote the document.
    """
    if kind not in PROMPT_IDS:
        raise DraftError("output_validation_failed")

    prompt_id = PROMPT_IDS[kind]
    try:
        prompt_id, prompt_version, body = load_prompt(root_dir, prompt_id)
        _, _, _, schema_name = load_prompt_with_schema(root_dir, PROMPT_IDS[kind])
        if not schema_name:
            raise PromptNotFound(f"{PROMPT_IDS[kind]} declares no response_schema")
        schema = load_schema(root_dir, schema_name)
    except PromptNotFound as exc:
        # Deployment without prompt files: the deterministic draft still works,
        # and `validate_prompts` is what fails loudly at startup.
        content = draft.build(kind, profile_content, job, language)
        return content, {"source": "fallback", "fallback_code": "prompt_not_configured"}

    messages = [
        {
            "role": "system",
            "content": render(
                body,
                {
                    "language_instruction": f"Write the document in {language}.",
                    "page_limit": "Maximum 2 pages." if kind == "cv" else "One page.",
                    "tone_instruction": "Professional, specific, no flattery.",
                    "document_kind": kind,
                    "revision_instructions": revision_instructions,
                },
            ),
        },
        {
            "role": "user",
            "content": _user_message(
                kind, profile_content, evidence_index, job, language, revision_instructions
            ),
        },
    ]
    try:
        result = client.generate(
            role="write",
            messages=messages,
            response_schema=schema,
            temperature=0.4,
            max_tokens=MAX_TOKENS,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
        )
    except LLMContractError as exc:
        content = draft.build(kind, profile_content, job, language)
        return content, {"source": "fallback", "fallback_code": exc.code, "kind": kind}

    content = _trusted(result.object, kind, profile_content, job, language)
    metadata = result.metadata.as_dict()
    metadata["source"] = "llm"
    # Requirements the writer could not support. Reported next to the findings,
    # never merged into the document.
    metadata["gaps"] = list(result.object.get("gaps") or [])
    return content, metadata


def _user_message(
    kind: str,
    profile_content: dict,
    evidence_index: dict,
    job: dict,
    language: str,
    revision_instructions: str,
) -> str:
    payload = {
        "job_requirements_json": json.dumps(
            {
                "title": job.get("title"),
                "company": job.get("company"),
                "description_text": job.get("description_text"),
                "requirements": job.get("requirements") or [],
            },
            ensure_ascii=False,
        ),
        "profile_subset_json": json.dumps(profile_content, ensure_ascii=False),
        "evidence_subset_json": json.dumps(evidence_index, ensure_ascii=False),
        "cv_content_json": json.dumps(
            {
                "target": {
                    "title": job.get("title"),
                    "company": job.get("company"),
                },
                "kind": kind,
            },
            ensure_ascii=False,
        ),
        "language_instruction": f"Write the document in {language}.",
        "page_limit": "Maximum 2 pages." if kind == "cv" else "One page.",
        "tone_instruction": "Professional, specific, no flattery.",
        "document_kind": kind,
        "revision_instructions": revision_instructions,
        "threshold_instruction": "",
    }
    return render(_USER_TEMPLATE, payload)


_USER_TEMPLATE = """<untrusted>
{{job_requirements_json}}
</untrusted>

<untrusted>
{{profile_subset_json}}
</untrusted>

<untrusted>
{{evidence_subset_json}}
</untrusted>

<untrusted>
{{cv_content_json}}
</untrusted>

{{language_instruction}}
{{page_limit}}
{{tone_instruction}}
{{revision_instructions}}
"""


def _trusted(
    raw: dict, kind: str, profile_content: dict, job: dict, language: str
) -> dict:
    """Keep the model's prose; restore every identity field from trusted data."""
    content = {key: value for key, value in raw.items() if key not in _DROP_KEYS}
    baseline = draft.build(kind, profile_content, job, language)
    content["schema_version"] = draft.SCHEMA_VERSION
    content["kind"] = kind
    content["language"] = language
    content["target"] = baseline["target"]
    content["header"] = baseline["header"]
    if kind == "cover_letter":
        content["signature"] = baseline["signature"]
    content["missing"] = draft.missing_information(content)
    return content
