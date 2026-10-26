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
import re
from pathlib import Path

from ..llm.client import LLMClient, LLMContractError
from ..llm.prompts import (
    PromptNotFound,
    load_prompt,
    load_prompt_with_schema,
    load_rules,
    load_schema,
    render,
)
from . import draft

logger = logging.getLogger(__name__)

PROMPT_IDS = {"cv": "write_cv", "cover_letter": "write_cover_letter"}
# A full CV with bullets needs more than 4000 completion tokens; the extract role
# hit the same wall (see profile/extract.py).
MAX_TOKENS = 8000
# Rewrite passes the writer gets when the gate finds a rule violation. Two is
# enough for grammar fixes; more just burns tokens on the same sentence.
WRITE_ATTEMPTS = 2
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
    cv_content: dict | None = None,
    plan: dict | None = None,
) -> tuple[dict | None, dict]:
    """Return (content, metadata).

    `content` is `None` when the writer did not run. There is no deterministic
    writer: `metadata` then carries `source="writer_unavailable"` and a
    `fallback_code`, and the caller fails the task with that code. A CV the model
    did not write must never be stored as if it were.
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
        # No deterministic writer exists any more: a missing prompt or schema is
        # a broken deployment, so fail the task instead of shipping a template
        # document the user would mistake for model output.
        return None, {"source": "writer_unavailable", "fallback_code": "prompt_not_configured"}

    try:
        rules = load_rules(root_dir, prompt_id)
    except PromptNotFound:
        return None, {"source": "writer_unavailable", "fallback_code": "rules_not_configured"}

    messages = [
        {
            "role": "system",
            "content": render(
                body,
                {
                    "rules": rules,
                    "language_instruction": (
                        f"Write the document in {language}. The profile and evidence "
                        f"quotes are in the candidate's source language: translate "
                        f"every fact you use into {language}. Never paste "
                        f"source-language text into the document."
                    ),
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
                kind,
                profile_content,
                evidence_index,
                job,
                language,
                revision_instructions,
                cv_content,
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
        # The caller fails the task with this code instead of writing a template
        # document; the user must never receive a CV the model did not write.
        return None, {"source": "writer_unavailable", "fallback_code": exc.code}

    content = _trusted(result.object, kind, profile_content, job, language)
    metadata_problems: list[str] = []
    if kind == "cv":
        _drop_unsupported_skills(content, evidence_index, job)
        missing_roles = _missing_roles(content, draft.build(kind, profile_content, job, language))
        problems = _writing_problems(content, missing_roles, language)
        # The rules live in the model's prompt, so a violation is sent back to the
        # model to rewrite. Patching it here would put scripted text in a document
        # the user believes the model wrote. Two attempts, then report the rest.
        for _ in range(WRITE_ATTEMPTS):
            if not problems:
                break
            retried = _rewrite(
                client,
                messages,
                schema,
                content,
                missing_roles,
                problems,
                prompt_id,
                prompt_version,
                profile_content,
                job,
                language,
            )
            if retried is None:
                break
            content, result = retried
            _drop_unsupported_skills(content, evidence_index, job)
            missing_roles = _missing_roles(
                content, draft.build(kind, profile_content, job, language)
            )
            problems = _writing_problems(content, missing_roles, language)
        # The model has had its chances. Keep the document, but report exactly
        # which sentences still did not follow the rules.
        metadata_problems = problems
    metadata = result.metadata.as_dict()
    metadata["source"] = "llm"
    # Rule violations the model did not fix after retrying. Reported next to the
    # findings so the reader can judge the sentence themselves.
    metadata["writing_problems"] = metadata_problems
    # Requirements the writer could not support. Reported next to the findings,
    # never merged into the document.
    metadata["gaps"] = list(result.object.get("gaps") or [])
    return content, metadata


def _rewrite(
    client,
    messages: list[dict],
    schema: dict,
    content: dict,
    missing_roles: list[dict],
    problems: list[str],
    prompt_id: str,
    prompt_version: str,
    profile_content: dict,
    job: dict,
    language: str,
):
    """One more model pass that fixes rule violations the gate caught."""
    instructions = list(problems)
    if missing_roles:
        titles = ", ".join(
            f"{role.get('title')} at {role.get('company')}" for role in missing_roles
        )
        instructions.append(
            f"Add back these roles, written in your own words: {titles}."
        )
    retry_messages = list(messages) + [
        {"role": "assistant", "content": json.dumps(content, ensure_ascii=False)},
        {
            "role": "user",
            "content": (
                "Your CV broke these rules:\n- "
                + "\n- ".join(instructions)
                + "\nReturn the complete corrected JSON object. Keep every other part "
                "that already follows the rules.",
            ),
        },
    ]
    try:
        result = client.generate(
            role="write",
            messages=retry_messages,
            response_schema=schema,
            temperature=0.4,
            max_tokens=MAX_TOKENS,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
        )
    except LLMContractError:
        return None
    fixed = _trusted(result.object, "cv", profile_content, job, language)
    _drop_unsupported_skills(fixed, {}, job)
    return fixed, result


def _user_message(
    kind: str,
    profile_content: dict,
    evidence_index: dict,
    job: dict,
    language: str,
    revision_instructions: str,
    cv_content: dict | None = None,
    plan: dict | None = None,
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
            cv_content
            if kind == "cover_letter" and cv_content
            else {
                "target": {
                    "title": job.get("title"),
                    "company": job.get("company"),
                },
                "kind": kind,
            },
            ensure_ascii=False,
        ),
        "plan_json": json.dumps(plan or {}, ensure_ascii=False),
        "language_instruction": (
            f"Write the document in {language}. The profile and evidence quotes are "
            f"in the candidate's source language: translate every fact you use into "
            f"{language}. Never paste source-language text into the document."
        ),
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

<untrusted>
{{plan_json}}
</untrusted>

{{language_instruction}}
{{page_limit}}
{{tone_instruction}}
{{revision_instructions}}
"""


def _fill_header(content: dict, baseline: dict) -> None:
    """Take every header field from the profile, never from the model.

    The model may drop a link it judged irrelevant. A CV without its own GitHub
    or LinkedIn is a fact the reader cannot check, so an empty field falls back
    to the profile value and a non-empty string is kept only when it matches.
    """
    trusted = baseline["header"]
    header = content.get("header") or {}
    filled = {key: trusted.get(key) for key in ("full_name", "email", "phone", "location")}
    model_links = [link for link in header.get("links") or [] if isinstance(link, str)]
    filled["links"] = [
        link for link in model_links if link in trusted.get("links", [])
    ] or list(trusted.get("links") or [])
    content["header"] = filled


def _skill_supported(skill: dict, evidence_index: dict) -> bool:
    """A skill line needs proof somewhere: its own ids must resolve."""
    ids = skill.get("evidence_ids") or []
    if not ids:
        return False
    return all(str(item) in evidence_index for item in ids)


def _drop_unsupported_skills(
    content: dict, evidence_index: dict, job: dict | None = None
) -> None:
    """Keep every CV line answerable in an interview.

    Two rules, both from the CV template: a skill needs a resolvable evidence id,
    and a skill the posting never mentions must also appear in the CV body. A
    keyword that is neither asked for nor used elsewhere is exactly the
    keyword-stuffing the reviewer flags.
    """
    skills = [item for item in content.get("skills") or [] if isinstance(item, dict)]
    if not evidence_index:
        return
    kept = [item for item in skills if _skill_supported(item, evidence_index)]
    if job is None:
        content["skills"] = kept
        return
    body = json.dumps(
        {
            "summary": content.get("summary"),
            "experience": content.get("experience"),
            "projects": content.get("projects"),
        },
        ensure_ascii=False,
    ).lower()
    wanted = _job_terms(job)
    content["skills"] = [
        item
        for item in kept
        if _mentioned(str(item.get("name") or ""), wanted)
        or _mentioned(str(item.get("name") or ""), body)
    ]


def _job_terms(job: dict) -> str:
    parts = [str(job.get("title") or ""), str(job.get("description_text") or "")]
    parts += [str(item.get("text") or "") for item in job.get("requirements") or []]
    return " ".join(parts).lower()


# Phrases the CV template forbids. The list is short on purpose: it catches the
# empty adjectives a model reaches for when a bullet has no evidence, and the
# gate then asks the model to rewrite instead of patching the text.
_BANNED_PHRASES = (
    "responsible for",
    "worked on",
    "helped with",
    "involved in",
    "hands-on experience",
    "hands on experience",
    "hardworking",
    "hard-working",
    "team player",
    "fast learner",
    "detail-oriented",
    "passionate",
    "comfortable with",
    "worked with",
    "various",
    "etc.",
)
# Placeholders left in output mean the model echoed the prompt back.
_PROMPT_LEAKS = ("{{", "}}", "<untrusted>", "lorem ipsum")


# Words that must be followed by a preposition when a noun phrase comes next.
# The model drops them when it compresses: "delivered government agency",
# "Built CRUD modules Node.js", "authentication 15-minute access tokens".
_NEEDS_PREPOSITION = re.compile(
    r"\b(deliver(?:ed)?|built|implemented|shipped|created|designed|wrote|led|"
    r"reached|presented|reviewed|tested|authentication|authorization|access|"
    r"refresh|deployment|notification|upload|download|integration|migration|"
    r"modules?|tokens?|services?|apis?|report|dashboard)\s+"
    r"([a-z][a-z0-9+.&-]*(?:\s+[a-z][a-z0-9+.&-]*){0,2}?)\s+"
    r"(\d|[a-z]+ing\b|one of|two of|one two|two three)"
)


def _writing_problems(
    content: dict, missing_roles: list[dict], language: str
) -> list[str]:
    """Rule violations the model must fix itself.

    Returns human-readable instructions, empty when the CV follows the template.
    """
    problems: list[str] = []
    texts: list[tuple[str, str]] = []
    summary = (content.get("summary") or {}).get("text")
    if isinstance(summary, str):
        texts.append(("summary", summary))
    for role in content.get("experience") or []:
        if not isinstance(role, dict):
            continue
        for bullet in role.get("bullets") or []:
            if isinstance(bullet, dict) and bullet.get("text"):
                texts.append((f"bullet under {role.get('title')}", bullet["text"]))
    for project in content.get("projects") or []:
        if isinstance(project, dict) and project.get("description"):
            texts.append((f"project {project.get('name')}", project["description"]))

    for where, text in texts:
        lowered = text.lower()
        for phrase in _BANNED_PHRASES:
            if phrase in lowered:
                problems.append(
                    f'The {where} uses "{phrase}". Replace it with a concrete action '
                    f'and a verifiable result: "{text[:120]}"'
                )
        for leak in _PROMPT_LEAKS:
            if leak in lowered:
                problems.append(f"The {where} still contains prompt text ({leak}).")
        if not text.strip().endswith((".", "!", "?", ";")):
            problems.append(
                f'The {where} is cut off mid-sentence: "{text[-80:]}"'
            )
        if language == "en" and re.search(r"\bone two\b|\band and\b", lowered):
            problems.append(f'The {where} has broken grammar: "{text[:120]}"')
        preposition = _NEEDS_PREPOSITION.search(lowered)
        if language == "en" and preposition:
            fragment = text[preposition.start(1): preposition.end(3)]
            if not re.search(
                r"\b(to|of|in|on|for|with|at|by|from|and|as|across|into|over|"
                r"during|through|between|without|within)\b",
                fragment,
            ):
                problems.append(
                    f'Sentence drops a preposition after "{preposition.group(1)}" '
                    f'(missing "with", "for", "in", or "by"): "{text[:140]}". '
                    "Rewrite it as a full sentence with subject, verb, and preposition."
                )
        if language == "en" and len(re.findall(r"[a-z]{2,}", lowered)) > 3:
            if not re.search(
                r"\b(to|of|in|on|for|with|at|by|from|that|which|is|are|was|were|"
                r"and|as|within|across|using|via|over|into|during|after|before|"
                r"without|between|through)\b",
                lowered,
            ):
                problems.append(
                    f'The {where} has no connecting words and reads like keywords: '
                    f'"{text[:140]}"'
                )

    for where, text in texts:
        words = set(re.findall(r"[a-z]+", text.lower()))
        if len(words) > 45:
            problems.append(
                f"The {where} is longer than two lines; split or shorten it: "
                f'"{text[:120]}"'
            )
    if missing_roles:
        problems.append(
            "Roles from the profile are missing: "
            + ", ".join(
                f"{role.get('title')} at {role.get('company')}"
                for role in missing_roles
            )
        )
    return problems


def _mentioned(name: str, haystack: str) -> bool:
    return bool(name) and name.lower() in haystack


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
    if kind == "cv":
        _fill_header(content, baseline)
    else:
        content["header"] = baseline["header"]
    if kind == "cover_letter":
        content["signature"] = baseline["signature"]
    else:
        _restore_missing_facts(content, baseline)
    content["missing"] = draft.missing_information(content)
    return content


# Sections the model curates: it may drop an item that does not serve the
# target, so a dropped item is NOT restored. Only an empty section is refilled,
# because that means the model returned nothing usable at all.
_CURATED_SECTIONS = ("skills", "projects")

# Sections where the model may reorder or reword but must not drop a real fact.
# Education and certifications are facts about the candidate, not tailoring
# levers: losing one makes the CV incomplete.
_MERGE_SECTIONS = (
    "education",
    "certifications",
    "languages",
)


def _restore_missing_facts(content: dict, baseline: dict) -> None:
    for section in _MERGE_SECTIONS:
        present: set[str] = set()
        for item in content.get(section) or []:
            if isinstance(item, dict):
                present |= _fact_keys(item)
        restored = [
            item
            for item in baseline.get(section) or []
            if not (_fact_keys(item) & present)
        ]
        if restored:
            content[section] = list(content.get(section) or []) + restored
    # Curated sections: honour the model's selection, but never ship a CV with
    # no skills or no projects when the profile has them.
    for section in _CURATED_SECTIONS:
        if not content.get(section) and baseline.get(section):
            content[section] = list(baseline[section])


def _fact_keys(item: dict) -> set[str]:
    """Identify a fact by id *and* label.

    A model may invent or omit ids, so matching on id alone would let the same
    skill appear twice: once from the model, once restored from the profile.
    """
    keys = set()
    if item.get("id"):
        keys.add(f"id:{item['id']}")
    label = item.get("name") or item.get("institution") or item.get("title") or ""
    if str(label).strip():
        keys.add(f"name:{str(label).strip().lower()}")
    return keys


def _role_keys(role: dict) -> set[str]:
    """A role is identified by company + title; an id alone is too fragile."""
    company = str(role.get("company") or "").strip().lower()
    title = str(role.get("title") or "").strip().lower()
    return {f"role:{company}|{title}"} if company or title else set()


def _missing_roles(content: dict, baseline: dict) -> list[dict]:
    """Roles the profile lists but the model dropped.

    Tailoring may reorder roles and reword their bullets, but not delete a role:
    the reader takes the CV as the complete history.
    """
    kept_keys: set[str] = set()
    for role in content.get("experience") or []:
        if isinstance(role, dict):
            kept_keys |= _role_keys(role)
    return [
        role
        for role in baseline.get("experience") or []
        if not (_role_keys(role) & kept_keys)
    ]
