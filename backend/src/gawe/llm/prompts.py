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

    Raises `PromptNotFound` so a missing schema fails before a model call rather
    than after paying for one.
    """
    path = Path(root_dir) / CONTRACTS_DIR / name
    if not path.is_file():
        raise PromptNotFound(f"response schema not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


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


ROLE_PROMPTS = ["extract_profile", "write_cv", "write_cover_letter", "review"]


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
