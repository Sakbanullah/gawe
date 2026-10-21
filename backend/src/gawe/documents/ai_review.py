"""Independent LLM reviewer, merged with the deterministic integrity pass.

Two layers, one report:

- `review_rules.review` proves what code can prove: required fields, evidence ids
  that resolve, dates and numbers that appear in the profile, ATS layout.
- the `review` role reads the document against the job requirements and scores it
  on five dimensions.

Neither layer can overrule the other. A blocker or major from either one fails
the document, whatever the score says.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..llm.client import LLMClient, LLMContractError
from ..llm.prompts import PromptNotFound, load_prompt, load_prompt_with_schema, load_schema, render
from . import review as review_rules

logger = logging.getLogger(__name__)

PROMPT_ID = "review"
MAX_TOKENS = 4000
DIMENSIONS = (
    "clarity",
    "relevance",
    "credibility",
    "differentiation",
    "professional_quality",
)
# Stored findings must use the stored vocabulary. The reviewer may invent a
# label ("ats_keywords"); unmapped labels fall back to `consistency` rather than
# rejecting an otherwise usable report.
CATEGORIES = {
    "factuality",
    "relevance",
    "exaggeration",
    "language",
    "ats",
    "consistency",
    "format",
    "priority",
    "eligibility",
}
CATEGORY_ALIASES = {
    "ats_keywords": "ats",
    "keywords": "ats",
    "grammar": "language",
    "tone": "language",
    "style": "format",
    "structure": "format",
    "accuracy": "factuality",
    "evidence": "factuality",
}


class ReviewError(Exception):
    """The reviewer could not produce a usable report."""

    def __init__(self, code: str, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


def review(
    client: LLMClient,
    root_dir: Path,
    content: dict,
    evidence_index: dict,
    profile_content: dict,
    job: dict,
) -> tuple[dict, dict]:
    """Return (report, metadata).

    `report` carries `verdict`, `overall_score`, `dimension_scores`, `findings`,
    and `source`. `overall_score` is `None` when the reviewer could not run; the
    caller must treat that as "not passed", never as "passed".
    """
    deterministic = review_rules.review(content, evidence_index, profile_content)
    findings = [_normalise(item, content.get("kind")) for item in deterministic["findings"]]

    metadata: dict = {"source": "deterministic"}
    score: float | None = None
    dimensions: dict | None = None
    try:
        llm_report, metadata = _ask(
            client, root_dir, content, evidence_index, profile_content, job
        )
    except ReviewError as exc:
        metadata = {"source": "deterministic", "review_error": exc.code}
        logger.warning("review role unavailable: %s", exc.code)
    else:
        findings.extend(_normalise(item, content.get("kind")) for item in llm_report["findings"])
        score = _round_score(llm_report["overall_score"])
        dimensions = {
            name: _round_score(llm_report["dimension_scores"][name]) for name in DIMENSIONS
        }
        metadata["source"] = "llm"

    return _report(findings, score, dimensions, metadata.get("source")), metadata


def passed(report: dict, threshold: float) -> bool:
    """A document passes only when every gate holds at once."""
    if any(
        item["severity"] in {"blocker", "major"} for item in report.get("findings") or []
    ):
        return False
    score = report.get("overall_score")
    if score is None:
        return False
    return float(score) >= threshold


def _ask(
    client: LLMClient,
    root_dir: Path,
    content: dict,
    evidence_index: dict,
    profile_content: dict,
    job: dict,
) -> tuple[dict, dict]:
    try:
        prompt_id, prompt_version, body = load_prompt(root_dir, PROMPT_ID)
        _, _, _, schema_name = load_prompt_with_schema(root_dir, PROMPT_ID)
        if not schema_name:
            raise PromptNotFound(f"{PROMPT_ID} declares no response_schema")
        schema = load_schema(root_dir, schema_name)
    except PromptNotFound as exc:
        raise ReviewError("provider_not_configured") from exc

    kind = content.get("kind") or "cv"
    messages = [
        {
            "role": "system",
            "content": render(body, {"document_kind": kind, "threshold_instruction": ""}),
        },
        {"role": "user", "content": _user_message(content, evidence_index, job, kind)},
    ]
    try:
        result = client.generate(
            role="review",
            messages=messages,
            response_schema=schema,
            temperature=0.0,
            max_tokens=MAX_TOKENS,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
        )
    except LLMContractError as exc:
        # Log where validation failed, never the offending value: it may be
        # candidate text. Path + validator are enough to fix a schema.
        cause = exc.__cause__
        path = list(getattr(cause, "absolute_path", []) or [])
        logger.warning(
            "review role rejected: code=%s path=%s validator=%s",
            exc.code,
            "/".join(str(part) for part in path) or "-",
            getattr(cause, "validator", "-"),
        )
        raise ReviewError(exc.code, exc.retryable) from exc
    return result.object, result.metadata.as_dict()


def _user_message(content: dict, evidence_index: dict, job: dict, kind: str) -> str:
    payload = {
        "job_requirements_json": json.dumps(
            {
                "title": job.get("title"),
                "company": job.get("company"),
                "requirements": job.get("requirements") or [],
            },
            ensure_ascii=False,
        ),
        "eligibility_json": json.dumps(
            {"status": job.get("eligibility_status")}, ensure_ascii=False
        ),
        "evidence_subset_json": json.dumps(evidence_index, ensure_ascii=False),
        "document_json": json.dumps(content, ensure_ascii=False),
        "document_kind": kind,
        "threshold_instruction": "",
    }
    return render(_USER_TEMPLATE, payload)


_USER_TEMPLATE = """<untrusted>
{{job_requirements_json}}
</untrusted>

<untrusted>
{{eligibility_json}}
</untrusted>

<untrusted>
{{evidence_subset_json}}
</untrusted>

<untrusted>
{{document_json}}
</untrusted>

{{document_kind}}
{{threshold_instruction}}
"""


def _round_score(value: float) -> float:
    """Scores are one decimal. `multipleOf` in JSON Schema is float-unsafe."""
    return round(min(10.0, max(0.0, float(value))), 1)


def _category(value: str | None) -> str:
    label = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if label in CATEGORIES:
        return label
    if label in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[label]
    return "consistency"


def _normalise(finding: dict, kind: str | None) -> dict:
    """Shape one finding for `findings.schema.json`, which forbids extra keys."""
    location = finding.get("location") or {}
    return {
        "finding_id": "",
        "severity": finding.get("severity") if finding.get("severity") in {
            "blocker",
            "major",
            "minor",
            "nit",
        } else "minor",
        "category": _category(finding.get("category")),
        "location": {
            "doc": location.get("doc") or kind or "cv",
            "section": location.get("section"),
            "bullet_id": location.get("bullet_id"),
        },
        "quote": str(finding.get("quote") or "")[:2000],
        "problem": str(finding.get("problem") or "")[:2000],
        "evidence_refs": list(finding.get("evidence_refs") or []),
        "suggested_fix": finding.get("suggested_fix") or finding.get("fix"),
        "auto_fixable": bool(finding.get("auto_fixable", False)),
        "status": "open",
    }


def _report(
    findings: list[dict], score: float | None, dimensions: dict | None, source: str
) -> dict:
    for index, item in enumerate(findings, start=1):
        item["finding_id"] = f"f_{index:03d}"
    hard = any(item["severity"] in {"blocker", "major"} for item in findings)
    return {
        "verdict": "changes_required" if hard else "pass",
        "overall_score": score,
        "dimension_scores": dimensions,
        "findings": findings,
        "source": source,
    }
