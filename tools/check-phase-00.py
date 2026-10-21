#!/usr/bin/env python3
"""Check Phase 0 deliverables. No network, no application code.

Run from repo root:
    python tools/check-phase-00.py

Checks:
  1. Required Phase 0 files exist.
  2. JSON schemas are valid draft 2020-12 schemas.
  3. Fixtures validate against their schema.
  4. Eligibility fixtures cover all three statuses and carry no fit score.
  5. Fit fixture matches the documented formula.
  6. Ranking fixtures satisfy the documented ranking rules.
  7. OpenAPI parses, refs resolve, operationIds are unique, mutations require CSRF.
  8. Prompts exist, are provider-neutral, and wrap untrusted content.
  9. Config examples contain no secret value.
 10. No application directories exist.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from datetime import datetime
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
P00 = ROOT / "docs" / "phase-00"

FAILURES: list[str] = []
PASSES: list[str] = []


def ok(label: str) -> None:
    PASSES.append(label)


def bad(label: str, detail: str = "") -> None:
    FAILURES.append(f"{label}: {detail}" if detail else label)


def check(condition: bool, label: str, detail: str = "") -> bool:
    if condition:
        ok(label)
    else:
        bad(label, detail)
    return condition


REQUIRED_FILES = [
    "AGENTS.md",
    "PLAN.md",
    ".gitignore",
    ".env.example",
    "config.example.toml",
    "docs/adr/0001-frontend-stack.md",
    "docs/phases/PHASE-00.md",
    "docs/source-of-truth/DECISIONS.md",
    "docs/phase-00/contracts/openapi.yaml",
    "docs/phase-00/contracts/master-cv.schema.json",
    "docs/phase-00/contracts/profile.schema.json",
    "docs/phase-00/contracts/job.schema.json",
    "docs/phase-00/contracts/eligibility.schema.json",
    "docs/phase-00/contracts/fit-assessment.schema.json",
    "docs/phase-00/contracts/findings.schema.json",
    "docs/phase-00/contracts/llm-client.md",
    "docs/phase-00/contracts/ranking.md",
    "docs/phase-00/prompts/extract_profile.md",
    "docs/phase-00/prompts/parse_requirements.md",
    "docs/phase-00/prompts/classify_priority.md",
    "docs/phase-00/prompts/write_cv.md",
    "docs/phase-00/prompts/write_cover_letter.md",
    "docs/phase-00/prompts/review.md",
    "docs/phase-00/fixtures/profiles/profile_confirmed.json",
    "docs/phase-00/fixtures/ranking/ranking_cases.json",
]

FIXTURE_SCHEMAS = [
    ("docs/phase-00/fixtures/profiles/profile_confirmed.json", "docs/phase-00/contracts/profile.schema.json"),
    ("docs/phase-00/fixtures/jobs/job_001_eligible.json", "docs/phase-00/contracts/job.schema.json"),
    ("docs/phase-00/fixtures/jobs/job_002_needs_review.json", "docs/phase-00/contracts/job.schema.json"),
    ("docs/phase-00/fixtures/jobs/job_003_ineligible.json", "docs/phase-00/contracts/job.schema.json"),
    ("docs/phase-00/fixtures/eligibility/eligible.json", "docs/phase-00/contracts/eligibility.schema.json"),
    ("docs/phase-00/fixtures/eligibility/needs_review.json", "docs/phase-00/contracts/eligibility.schema.json"),
    ("docs/phase-00/fixtures/eligibility/ineligible.json", "docs/phase-00/contracts/eligibility.schema.json"),
    ("docs/phase-00/fixtures/fit/fit_eligible.json", "docs/phase-00/contracts/fit-assessment.schema.json"),
    ("docs/phase-00/fixtures/findings/findings_changes_required.json", "docs/phase-00/contracts/findings.schema.json"),
]

VENDOR_PATTERNS = [
    "openai",
    "anthropic",
    "gemini",
    "claude",
    "gpt-4",
    "gpt4",
    "ollama",
    "lm studio",
    "mistral",
    "llama",
]


def load_json(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def check_required_files() -> None:
    for rel in REQUIRED_FILES:
        check((ROOT / rel).is_file(), f"file exists: {rel}")


def check_schemas() -> None:
    for path in sorted((P00 / "contracts").glob("*.schema.json")):
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            ok(f"valid JSON schema: {path.relative_to(ROOT)}")
        except Exception as exc:  # noqa: BLE001
            bad(f"invalid JSON schema: {path.relative_to(ROOT)}", str(exc))


def check_fixtures() -> None:
    for path in sorted((P00 / "fixtures").rglob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
            ok(f"fixture is valid JSON: {path.relative_to(ROOT)}")
        except Exception as exc:  # noqa: BLE001
            bad(f"fixture is valid JSON: {path.relative_to(ROOT)}", str(exc))
    for fixture_rel, schema_rel in FIXTURE_SCHEMAS:
        try:
            fixture = load_json(fixture_rel)
            schema = load_json(schema_rel)
            errors = sorted(Draft202012Validator(schema).iter_errors(fixture), key=lambda e: list(e.path))
            if errors:
                first = errors[0]
                location = "/".join(str(p) for p in first.path) or "<root>"
                bad(f"fixture valid: {fixture_rel}", f"{location}: {first.message}")
            else:
                ok(f"fixture valid: {fixture_rel}")
        except Exception as exc:  # noqa: BLE001
            bad(f"fixture valid: {fixture_rel}", str(exc))


def check_eligibility() -> None:
    statuses = set()
    for name in ("eligible", "needs_review", "ineligible"):
        data = load_json(f"docs/phase-00/fixtures/eligibility/{name}.json")
        statuses.add(data["status"])
        check("fit_score" not in data, f"eligibility has no fit_score: {name}")
        check(bool(data["checks"]), f"eligibility has checks: {name}")
        for item in data["checks"]:
            if not item.get("job_quote") or not item.get("reason"):
                bad(f"eligibility check complete: {name}", item.get("requirement_id", "?"))
    check(statuses == {"eligible", "ineligible", "needs_review"}, "eligibility fixtures cover all statuses", str(statuses))


def check_fit_formula() -> None:
    data = load_json("docs/phase-00/fixtures/fit/fit_eligible.json")
    parts = {c["name"]: c for c in data["components"]}
    weights = {"must_coverage": 0.60, "nice_coverage": 0.15, "experience_fit": 0.25}
    total = 0.0
    for name, weight in weights.items():
        component = parts.get(name)
        if component is None:
            bad("fit components complete", f"missing {name}")
            return
        if abs(component["weight"] - weight) > 1e-9:
            bad("fit component weight", f"{name} expected {weight}, got {component['weight']}")
        expected_contribution = round(100 * weight * component["value"], 4)
        if abs(component["contribution"] - expected_contribution) > 1e-6:
            bad("fit contribution", f"{name} expected {expected_contribution}, got {component['contribution']}")
        total += weight * component["value"]
    score = 100 * total
    # Rounding tie behaviour is an implementation detail; allow the half-point band.
    check(abs(score - data["fit_score"]) < 0.51, "fit score matches formula", f"formula={score:.4f} fixture={data['fit_score']}")
    check(data["verdict"] in {"strong", "moderate", "weak"}, "fit verdict is closed enum")


def tier_rank(tier: str) -> int:
    return {"P1": 1, "P2": 2, "P3": 3, "P4": 4, "unclassified": 5}[tier]


def posted_key(candidate: dict) -> tuple[int, float]:
    raw = candidate.get("posted_at")
    if raw is None:
        return (1, 0.0)
    return (0, -datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())


def rank(candidates: list[dict], tie_window: int) -> list[str]:
    eligible = [c for c in candidates if c["eligibility_status"] == "eligible"]
    eligible.sort(key=lambda c: (-c["fit_score"], c["job_id"]))
    ordered: list[str] = []
    index = 0
    while index < len(eligible):
        band_top = eligible[index]["fit_score"]
        band: list[dict] = []
        while index < len(eligible) and band_top - eligible[index]["fit_score"] <= tie_window:
            band.append(eligible[index])
            index += 1
        band.sort(key=lambda c: (tier_rank(c["priority_tier"]), posted_key(c), c["job_id"]))
        ordered.extend(c["job_id"] for c in band)
    return ordered


def check_ranking() -> None:
    data = load_json("docs/phase-00/fixtures/ranking/ranking_cases.json")
    check(data["tie_window_default"] == 0, "ranking default tie_window is 0")
    check(data["tie_window_max"] == 20, "ranking max tie_window is 20")
    for case in data["cases"]:
        got = rank(case["candidates"], case["tie_window"])
        check(
            got == case["expected_eligible_order"],
            f"ranking case: {case['case_id']}",
            f"expected {case['expected_eligible_order']}, got {got}",
        )
        for section in ("needs_review", "ineligible"):
            expected_key = f"expected_{section}_order"
            if expected_key not in case:
                continue
            expected = case[expected_key]
            actual = [c["job_id"] for c in case["candidates"] if c["eligibility_status"] == section]
            check(actual == expected, f"ranking section: {case['case_id']} {section}", f"expected {expected}, got {actual}")
            for candidate in case["candidates"]:
                if candidate["eligibility_status"] == section:
                    check(candidate["fit_score"] is None, f"ranking {section} has no fit score: {candidate['job_id']}")


def resolve_ref(document: dict, ref: str):
    if not ref.startswith("#/"):
        raise ValueError(f"non-local ref not allowed: {ref}")
    node = document
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node


def walk_refs(node) -> list[str]:
    refs: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                refs.append(value)
            else:
                refs.extend(walk_refs(value))
    elif isinstance(node, list):
        for value in node:
            refs.extend(walk_refs(value))
    return refs


def check_openapi() -> None:
    path = P00 / "contracts" / "openapi.yaml"
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        bad("OpenAPI parses", str(exc))
        return
    ok("OpenAPI parses")
    check(document.get("openapi", "").startswith("3.1"), "OpenAPI version is 3.1")

    refs = walk_refs(document)
    unresolved = []
    for ref in refs:
        try:
            resolve_ref(document, ref)
        except Exception:  # noqa: BLE001
            unresolved.append(ref)
    check(not unresolved, "OpenAPI refs resolve", f"{len(unresolved)} unresolved, first={unresolved[:3]}")

    operation_ids: list[str] = []
    mutations_missing_csrf: list[str] = []
    rate_limited: list[str] = []
    for route, item in document.get("paths", {}).items():
        if not route.startswith("/api/"):
            bad("OpenAPI path under /api", route)
        for method, operation in item.items():
            if method not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                continue
            op_id = operation.get("operationId")
            if not op_id:
                bad("OpenAPI operationId present", f"{method.upper()} {route}")
            else:
                operation_ids.append(op_id)
            if "429" in operation.get("responses", {}):
                rate_limited.append(f"{method.upper()} {route}")
            if method in {"post", "put", "patch", "delete"}:
                security = operation.get("security") or []
                if not any("csrfToken" in requirement for requirement in security):
                    mutations_missing_csrf.append(f"{method.upper()} {route}")
    check(len(operation_ids) == len(set(operation_ids)), "OpenAPI operationIds unique", f"{len(operation_ids)} operations")
    check(not mutations_missing_csrf, "OpenAPI mutations require CSRF", str(mutations_missing_csrf[:5]))
    check(not rate_limited, "OpenAPI has no 429 on v1", str(rate_limited[:5]))
    check("csrfToken" in document.get("components", {}).get("securitySchemes", {}), "OpenAPI defines csrfToken scheme")


def check_prompts() -> None:
    prompt_dir = P00 / "prompts"
    prompts = sorted(prompt_dir.glob("*.md"))
    check(len(prompts) == 6, "six prompt drafts exist", f"found {len(prompts)}")
    for path in prompts:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            bad("prompt front-matter", path.name)
            continue
        front = text.split("---", 2)[1]
        for field in ("prompt_id:", "version:", "role:", "temperature_min:", "temperature_max:", "response_schema:"):
            if field not in front:
                bad("prompt front-matter field", f"{path.name}: {field}")
        lowered = text.lower()
        hits = [pattern for pattern in VENDOR_PATTERNS if pattern in lowered]
        check(not hits, f"prompt provider-neutral: {path.name}", str(hits))
        check("<untrusted>" in text, f"prompt wraps untrusted content: {path.name}")


def check_config() -> None:
    try:
        config = tomllib.loads((ROOT / "config.example.toml").read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        bad("config.example.toml parses", str(exc))
        return
    ok("config.example.toml parses")
    check(config["server"]["host"] == "127.0.0.1", "config binds loopback")
    provider = config["llm"]["providers"]["provider_a"]
    check("api_key_ref" in provider, "config uses api_key_ref")
    check("api_key" not in provider, "config has no inline api_key")
    check("api_key" not in config["llm"], "config has no inline api_key at [llm]")
    check(config["privacy"]["log_model_io"] is False, "config disables model IO logging by default")
    check(config["retention"]["job_cache_days"] > 0, "config records provisional retention")

    env_lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    for line in env_lines:
        if line.startswith("GAWE_LLM_API_KEY="):
            check(line.strip() == "GAWE_LLM_API_KEY=", "env example has no secret value", line)
    check(
        "!.env.example" in (ROOT / ".gitignore").read_text(encoding="utf-8"),
        ".env.example is not gitignored",
    )


def check_no_app_dirs() -> None:
    for name in ("backend", "frontend"):
        check(not (ROOT / name).exists(), f"no {name}/ directory during Phase 0")


def check_decisions() -> None:
    decisions = (ROOT / "docs/source-of-truth/DECISIONS.md").read_text(encoding="utf-8")
    check("| D22 |" in decisions and "**Diputuskan**" in decisions, "DECISIONS.md records D22 as decided")
    check("| C4 |" in decisions and "Selesai 2026-10-19" in decisions, "DECISIONS.md records C4 closed after approval")
    phase = (ROOT / "docs/phases/PHASE-00.md").read_text(encoding="utf-8")
    check("Gate Phase 0 lulus" in phase, "PHASE-00.md records gate passed")
    adr = (ROOT / "docs/adr/0001-frontend-stack.md").read_text(encoding="utf-8")
    check("Accepted (Phase 0)" in adr, "ADR-0001 accepted")
    check("@mantine/core" in adr, "ADR-0001 records Mantine")


def main() -> int:
    check_required_files()
    check_schemas()
    check_fixtures()
    check_eligibility()
    check_fit_formula()
    check_ranking()
    check_openapi()
    check_prompts()
    check_config()
    check_no_app_dirs()
    check_decisions()

    for label in PASSES:
        print(f"PASS  {label}")
    for failure in FAILURES:
        print(f"FAIL  {failure}")

    print(f"\n{len(PASSES)} passed, {len(FAILURES)} failed")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
