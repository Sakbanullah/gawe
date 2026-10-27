"""Versioned prompt loading for every LLM role.

Prompts live as Markdown with a front-matter block:

    ---
    prompt_id: write_cv
    version: 0.2.0
    role: write
    response_schema: tailored-cv.schema.json
    ---

`load_prompt` returns the identity plus the body, so callers can pass
`prompt_id`/`prompt_version` into `LLMClient.generate` and get them recorded in
`llm_call`. The body is what the model sees; the front matter is metadata.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PROMPTS_DIR = Path("docs") / "phase-00" / "prompts"
CONTRACTS_DIR = Path("docs") / "phase-00" / "contracts"
FRONT_MATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


class PromptNotFound(Exception):
    """A prompt file referenced by the pipeline does not exist."""


def prompt_path(root_dir: Path, prompt_id: str) -> Path:
    return Path(root_dir) / PROMPTS_DIR / f"{prompt_id}.md"


def read_front_matter(raw: str) -> tuple[dict[str, str], str]:
    """Return (metadata, body). Missing front matter yields an empty mapping."""
    match = FRONT_MATTER_RE.match(raw)
    if not match:
        return {}, raw
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        if key.strip():
            meta[key.strip()] = value.strip()
    return meta, raw[match.end() :]


def load_prompt(
    root_dir: Path, prompt_id: str, fallback: str | None = None
) -> tuple[str, str, str]:
    """Return (prompt_id, prompt_version, body).

    A missing file falls back to `fallback` when one is supplied; otherwise it
    raises `PromptNotFound` so a misconfigured deployment fails loudly instead of
    silently sending an empty system prompt.
    """
    path = prompt_path(root_dir, prompt_id)
    if not path.is_file():
        if fallback is None:
            raise PromptNotFound(f"prompt file not found: {path}")
        return prompt_id, "0", fallback
    meta, body = read_front_matter(path.read_text(encoding="utf-8"))
    return meta.get("prompt_id", prompt_id), meta.get("version", "0"), body


def load_prompt_with_schema(root_dir: Path, prompt_id: str) -> tuple[str, str, str, str | None]:
    """Like `load_prompt`, plus the `response_schema` name declared in the file."""
    path = prompt_path(root_dir, prompt_id)
    if not path.is_file():
        raise PromptNotFound(f"prompt file not found: {path}")
    meta, body = read_front_matter(path.read_text(encoding="utf-8"))
    return (
        meta.get("prompt_id", prompt_id),
        meta.get("version", "0"),
        body,
        meta.get("response_schema") or None,
    )


def load_schema(root_dir: Path, name: str) -> dict:
    """Load a response schema declared in a prompt's front matter.

    ``name`` may carry a JSON-pointer fragment (``job.schema.json#/properties/x``)
    so a prompt can answer with one part of a larger contract. Raises
    `PromptNotFound` so a missing schema fails before a model call rather than
    after paying for one.
    """
    file_name, _, pointer = name.partition("#")
    path = Path(root_dir) / CONTRACTS_DIR / file_name
    if not path.is_file():
        raise PromptNotFound(f"response schema not found: {path}")
    schema = json.loads(path.read_text(encoding="utf-8"))
    if not pointer:
        return schema
    node: object = schema
    for step in pointer.lstrip("/").split("/"):
        if not isinstance(node, dict) or step not in node:
            raise PromptNotFound(f"response schema fragment not found: {name}")
        node = node[step]
    return node


def validate_prompts(root_dir: Path, prompt_ids: list[str]) -> None:
    """Fail at startup when a role's prompt or response schema is missing.

    Only called for real providers: with the fake provider the prompt files are
    never read, so a test root directory needs nothing.
    """
    for prompt_id in prompt_ids:
        _, _, _, schema_name = load_prompt_with_schema(root_dir, prompt_id)
        if not schema_name:
            raise PromptNotFound(f"{prompt_id} declares no response_schema")
        load_schema(root_dir, schema_name)


ROLE_PROMPTS = ["extract_profile", "parse_requirements", "write_cv", "write_cover_letter", "review"]

# Writer rules live outside the prompt files so the author can rewrite the CV and
# cover-letter templates without touching the JSON contract or the placeholder
# list. Maps prompt_id -> rule file in `docs/phase-00/prompts/rules/`.
RULE_FILES = {
    "write_cv": "CV_MASTER_TEMPLATE.md",
    "write_cover_letter": "COVER_LETTER_MASTER_TEMPLATE.md",
}
RULES_DIR = PROMPTS_DIR / "rules"


def load_rules(root_dir: Path, prompt_id: str) -> str:
    """Return the rule text a writer prompt must obey, or raise.

    The rule file is mandatory: a deployment without it would silently write
    documents with no authoring rules, which is exactly the state this replaced.
    """
    name = RULE_FILES.get(prompt_id)
    if name is None:
        raise PromptNotFound(f"{prompt_id} declares no rule file")
    path = Path(root_dir) / RULES_DIR / name
    if not path.is_file():
        raise PromptNotFound(f"rule file not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise PromptNotFound(f"rule file is empty: {path}")
    return text


def validate_role_prompts(config) -> None:
    """Skip the check for the fake provider: it never reads prompt files."""
    provider_config = config.llm.providers.get(config.llm.active_provider)
    if provider_config is None or provider_config.type == "fake":
        return
    validate_prompts(config.root_dir, ROLE_PROMPTS)


_PLACEHOLDER_RE = re.compile(r"\{\{([a-z_]+)\}\}")


def render(body: str, values: dict[str, str]) -> str:
    """Replace `{{name}}` placeholders; unknown placeholders become empty."""

    def substitute(match: re.Match[str]) -> str:
        return values.get(match.group(1), "")

    return _PLACEHOLDER_RE.sub(substitute, body)
