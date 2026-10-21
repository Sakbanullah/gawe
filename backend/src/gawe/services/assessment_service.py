"""Assessment pipeline: requirements → eligibility → fit → ranking → persistence.

Run after a discovery run persists jobs (PLAN.md §4.2 steps 8–11) and on explicit
re-analysis. Everything is deterministic; no model call happens here.
"""

from __future__ import annotations

import json

from ..db.repo import Connection
from ..eligibility.evaluate import evaluate
from ..jobs import requirements as requirement_rules
from ..jobs.priority import effective_tier
from ..master_cv import new_id, now_iso
from ..match.score import score as fit_score
from ..profile.store import ProfileStore
from ..ranking.rank import DEFAULT_TIE_WINDOW, rank

DEFAULT_TIE_WINDOW_VALUE = DEFAULT_TIE_WINDOW
# API-CONTRACTS §4.9: description_text is capped in bytes, and the OpenAPI
# maxLength (262144 / 3) keeps the character count conservative as well.
DESCRIPTION_MAX_BYTES = 262144
DESCRIPTION_MAX_CHARS = 87381


class AssessmentService:
    def __init__(self, connection: Connection, profile_store: ProfileStore) -> None:
        self._connection = connection
        self._profiles = profile_store

    # -- writes ----------------------------------------------------------
    def assess_job(self, job_id: str, profile: dict | None = None) -> dict | None:
        """Assess one job for the active profile; returns the eligibility payload."""
        profile = profile or self._profiles.require_confirmed()
        job = self._job(job_id)
        if job is None:
            return None
        requirements = self._requirements(job)
        eligibility = evaluate(requirements, profile, job)
        fit = None
        if eligibility["status"] == "eligible":
            fit = fit_score(eligibility["checks"])
        with self._connection:
            self._store_requirements(job["job_posting_version_id"], requirements)
            self._store_eligibility(job, profile, eligibility)
            if fit is None:
                self._delete_fit(job["job_posting_version_id"], profile["profile_version_id"])
            else:
                self._store_fit(job, profile, fit)
            self._apply_priority(job_id, job)
        return eligibility

    def assess_pending(self, limit: int = 500) -> dict:
        """Assess open jobs that have no assessment for the active profile yet."""
        profile = self._profiles.require_confirmed()
        rows = self._connection.execute(
            "SELECT j.job_id FROM job j "
            "LEFT JOIN eligibility_assessment e "
            "  ON e.job_id = j.job_id AND e.profile_version_id = ? "
            "WHERE j.status = 'open' AND j.duplicate_of IS NULL "
            "  AND (e.assessment_id IS NULL OR e.status_outdated = 1) "
            "ORDER BY j.created_at, j.job_id LIMIT ?",
            (profile["profile_version_id"], limit),
        ).fetchall()
        counts = {"eligible": 0, "needs_review": 0, "ineligible": 0}
        for row in rows:
            result = self.assess_job(row["job_id"], profile)
            if result is not None:
                counts[result["status"]] += 1
        return {"assessed": len(rows), **counts}

    def recompute_ranking(self, tie_window: int = DEFAULT_TIE_WINDOW) -> dict:
        profile = self._profiles.require_confirmed()
        candidates = self._candidates(profile["profile_version_id"])
        result = rank(candidates, tie_window)
        ranking_run_id = new_id("rnk")
        computed_at = now_iso()
        with self._connection:
            self._connection.execute(
                "INSERT INTO ranking_run (ranking_run_id, profile_version_id, tie_window, "
                "primary_key, tie_breaker_json, sections_json, counts_json, computed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ranking_run_id,
                    profile["profile_version_id"],
                    result["tie_window"],
                    result["primary"],
                    json.dumps(result["tie_breaker"]),
                    json.dumps(result["sections"], ensure_ascii=False),
                    json.dumps(result["counts"]),
                    computed_at,
                ),
            )
        return {**result, "ranking_run_id": ranking_run_id, "computed_at": computed_at}

    def override_tier(self, job_id: str, tier: str | None, reason: str | None) -> dict | None:
        """Record a user tier correction; it never changes the stored fit score.

        The stored ranking run is not recomputed here: the correction is a
        tie-breaker for the next ranking run (API-CONTRACTS §4.8).
        """
        job = self._job(job_id)
        if job is None:
            return None
        with self._connection:
            self._connection.execute(
                "UPDATE job SET priority_tier_override = ?, priority_tier_override_reason = ?, "
                "updated_at = ? WHERE job_id = ?",
                (tier, reason, now_iso(), job_id),
            )
        return self._job(job_id)

    # -- reads -----------------------------------------------------------
    def eligibility_for(self, job_id: str, profile_version_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM eligibility_assessment WHERE job_id = ? AND profile_version_id = ?",
            (job_id, profile_version_id),
        ).fetchone()
        return _eligibility_payload(row) if row else None

    def fit_for(self, job_id: str, profile_version_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM fit_assessment WHERE job_id = ? AND profile_version_id = ?",
            (job_id, profile_version_id),
        ).fetchone()
        return _fit_payload(row) if row else None

    def latest_ranking(self, profile_version_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM ranking_run WHERE profile_version_id = ? "
            "ORDER BY computed_at DESC, ranking_run_id DESC LIMIT 1",
            (profile_version_id,),
        ).fetchone()
        return _ranking_payload(row) if row else None

    def description(self, job_id: str) -> str:
        row = self._connection.execute(
            "SELECT v.description_text FROM job j "
            "JOIN job_posting_version v ON v.job_posting_version_id = j.latest_version_id "
            "WHERE j.job_id = ?",
            (job_id,),
        ).fetchone()
        return row["description_text"] if row else ""

    def match(self, job_id: str, profile_version_id: str) -> dict | None:
        """One list row for a job; ``None`` when it has no assessment yet."""
        return next(
            (
                item
                for item in self.matches(profile_version_id)
                if item["job"]["job_id"] == job_id
            ),
            None,
        )

    def detail(self, job_id: str, profile_version_id: str) -> dict | None:
        """MatchDetail payload: job + truncated description + source + assessments."""
        item = self.match(job_id, profile_version_id)
        if item is None:
            return None
        text, truncated = truncate_description(self.description(job_id))
        return {
            "job_detail": {
                "job": item["job"],
                "description_text": text,
                "description_truncated": truncated,
                "requirements": self._requirements_for(item["job"]["job_posting_version_id"]),
                "source": self._source(item["job"]["source_id"]),
            },
            "eligibility": self.eligibility_for(job_id, profile_version_id),
            "fit": self.fit_for(job_id, profile_version_id),
            "recommendation": item["recommendation"],
            "status_outdated": item["status_outdated"],
            "application_id": item["application_id"],
        }

    def counts(self, profile_version_id: str) -> dict:
        rows = self._connection.execute(
            "SELECT status, COUNT(*) AS total FROM eligibility_assessment "
            "WHERE profile_version_id = ? GROUP BY status",
            (profile_version_id,),
        ).fetchall()
        counts = {"eligible": 0, "needs_review": 0, "ineligible": 0}
        for row in rows:
            counts[row["status"]] = int(row["total"])
        fit = self._connection.execute(
            "SELECT COUNT(*) AS total FROM fit_assessment WHERE profile_version_id = ?",
            (profile_version_id,),
        ).fetchone()
        return {**counts, "fit_computed": int(fit["total"]) if fit else 0}

    def matches(self, profile_version_id: str) -> list[dict]:
        """One row per candidate job for the matches view; backend owns the order."""
        rows = self._connection.execute(
            "SELECT j.*, e.assessment_id AS eligibility_assessment_id, "
            "e.status AS eligibility_status, e.confidence AS eligibility_confidence, "
            "e.reason_summary, e.status_outdated AS eligibility_outdated, "
            "e.job_posting_version_id AS assessed_version_id, "
            "f.assessment_id AS fit_assessment_id, f.fit_score, f.verdict, "
            "f.confidence AS fit_confidence, a.application_id "
            "FROM job j "
            "JOIN eligibility_assessment e ON e.job_id = j.job_id "
            "  AND e.profile_version_id = ? "
            "LEFT JOIN fit_assessment f ON f.job_id = j.job_id "
            "  AND f.profile_version_id = e.profile_version_id "
            "LEFT JOIN application a ON a.job_id = j.job_id "
            "WHERE j.duplicate_of IS NULL",
            (profile_version_id,),
        ).fetchall()
        return [_match_row(row, profile_version_id) for row in rows]

    # -- internals -------------------------------------------------------
    def _job(self, job_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT j.*, v.description_text FROM job j "
            "JOIN job_posting_version v ON v.job_posting_version_id = j.latest_version_id "
            "WHERE j.job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        location = json.loads(row["location_json"] or "{}")
        return {
            "job_id": row["job_id"],
            "job_posting_version_id": row["latest_version_id"],
            "source_id": row["source_id"],
            "company": row["company"],
            "title": row["title"],
            "location_raw": location.get("raw"),
            "work_mode": row["work_mode"],
            "market": row["market"],
            "description_text": row["description_text"] or "",
            "posted_at": row["posted_at"],
            "priority_tier": row["priority_tier"],
            "priority_tier_override": row.get("priority_tier_override"),
        }

    def _requirements(self, job: dict) -> list[dict]:
        rows = self._connection.execute(
            "SELECT * FROM job_requirement WHERE job_posting_version_id = ? "
            "ORDER BY requirement_id",
            (job["job_posting_version_id"],),
        ).fetchall()
        if rows:
            return [
                {
                    "requirement_id": row["requirement_id"],
                    "kind": row["kind"],
                    "category": row["category"],
                    "text": row["text"],
                    "quote": row["quote"],
                    "weight": float(row["weight"]),
                    "constraint": json.loads(row["constraint_json"]) if row["constraint_json"] else None,
                }
                for row in rows
            ]
        extracted = requirement_rules.extract(job["description_text"])
        return extracted or [requirement_rules.fallback_requirement(job["description_text"])]

    def _requirements_for(self, version_id: str) -> list[dict]:
        rows = self._connection.execute(
            "SELECT requirement_id, kind, text, quote FROM job_requirement "
            "WHERE job_posting_version_id = ? ORDER BY requirement_id LIMIT 500",
            (version_id,),
        ).fetchall()
        return [
            {
                "requirement_id": row["requirement_id"],
                "kind": row["kind"],
                "text": row["text"],
                "quote": row["quote"],
            }
            for row in rows
        ]

    def _source(self, source_id: str) -> dict:
        row = self._connection.execute(
            "SELECT source_id, company, verification_status, access_method "
            "FROM source_registry WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        if row is None:
            # Jobs from the synthetic manual_url source have no registry entry.
            return {
                "source_id": source_id,
                "source_kind": "manual_url",
                "company": None,
                "verification_status": "verified",
                "access_method": "manual_url",
            }
        return {
            "source_id": row["source_id"],
            "source_kind": "registry",
            "company": row["company"],
            "verification_status": row["verification_status"],
            "access_method": row["access_method"],
        }

    def _store_requirements(self, version_id: str, requirements: list[dict]) -> None:
        for requirement in requirements:
            self._connection.execute(
                "INSERT INTO job_requirement (requirement_id, job_posting_version_id, kind, "
                "category, text, quote, weight, constraint_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON DUPLICATE KEY UPDATE kind = VALUES(kind), category = VALUES(category), "
                "text = VALUES(text), quote = VALUES(quote), weight = VALUES(weight), "
                "constraint_json = VALUES(constraint_json)",
                (
                    requirement["requirement_id"],
                    version_id,
                    requirement["kind"],
                    requirement["category"],
                    requirement["text"],
                    requirement["quote"],
                    requirement["weight"],
                    json.dumps(requirement["constraint"]) if requirement["constraint"] else None,
                    now_iso(),
                ),
            )

    def _store_eligibility(self, job: dict, profile: dict, result: dict) -> None:
        checks = [
            {key: value for key, value in check.items() if key != "kind"}
            for check in result["checks"]
        ]
        self._connection.execute(
            "INSERT INTO eligibility_assessment (assessment_id, job_id, job_posting_version_id, "
            "profile_version_id, status, checks_json, reason_summary, confidence, "
            "status_outdated, outdated_reason, computed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?) "
            "ON DUPLICATE KEY UPDATE assessment_id = VALUES(assessment_id), status = VALUES(status), "
            "checks_json = VALUES(checks_json), reason_summary = VALUES(reason_summary), "
            "confidence = VALUES(confidence), status_outdated = 0, outdated_reason = NULL, "
            "computed_at = VALUES(computed_at)",
            (
                new_id("ela"),
                job["job_id"],
                job["job_posting_version_id"],
                profile["profile_version_id"],
                result["status"],
                json.dumps(checks, ensure_ascii=False),
                result["reason_summary"],
                result["confidence"],
                now_iso(),
            ),
        )

    def _store_fit(self, job: dict, profile: dict, fit: dict) -> None:
        self._connection.execute(
            "INSERT INTO fit_assessment (assessment_id, job_id, job_posting_version_id, "
            "profile_version_id, fit_score, verdict, confidence, components_json, gaps_json, "
            "status_outdated, outdated_reason, computed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?) "
            "ON DUPLICATE KEY UPDATE assessment_id = VALUES(assessment_id), "
            "fit_score = VALUES(fit_score), verdict = VALUES(verdict), "
            "confidence = VALUES(confidence), components_json = VALUES(components_json), "
            "gaps_json = VALUES(gaps_json), status_outdated = 0, outdated_reason = NULL, "
            "computed_at = VALUES(computed_at)",
            (
                new_id("fita"),
                job["job_id"],
                job["job_posting_version_id"],
                profile["profile_version_id"],
                fit["fit_score"],
                fit["verdict"],
                fit["confidence"],
                json.dumps(fit["components"], ensure_ascii=False),
                json.dumps(fit["gaps"], ensure_ascii=False),
                now_iso(),
            ),
        )

    def _delete_fit(self, version_id: str, profile_version_id: str) -> None:
        self._connection.execute(
            "DELETE FROM fit_assessment WHERE job_posting_version_id = ? AND profile_version_id = ?",
            (version_id, profile_version_id),
        )

    def _apply_priority(self, job_id: str, job: dict) -> None:
        """Store the classification once; a user override is never overwritten."""
        from ..jobs.priority import classify

        row = self._connection.execute(
            "SELECT priority_tier, priority_confidence FROM job WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row and row["priority_confidence"] != "unknown":
            return
        result = classify(job["location_raw"], job["work_mode"], job["description_text"])
        self._connection.execute(
            "UPDATE job SET priority_tier = ?, priority_reason = ?, priority_confidence = ? "
            "WHERE job_id = ?",
            (result["tier"], result["reason"], result["confidence"], job_id),
        )

    def _candidates(self, profile_version_id: str) -> list[dict]:
        rows = self._connection.execute(
            "SELECT j.job_id, j.posted_at, j.priority_tier, j.priority_tier_override, "
            "e.status AS eligibility_status, e.reason_summary, f.fit_score "
            "FROM job j "
            "JOIN eligibility_assessment e ON e.job_id = j.job_id "
            "  AND e.profile_version_id = ? "
            "LEFT JOIN fit_assessment f ON f.job_id = j.job_id "
            "  AND f.profile_version_id = e.profile_version_id "
            "WHERE j.duplicate_of IS NULL AND j.status = 'open' "
            "ORDER BY j.job_id",
            (profile_version_id,),
        ).fetchall()
        return [
            {
                "job_id": row["job_id"],
                "eligibility_status": row["eligibility_status"],
                "fit_score": row["fit_score"] if row["eligibility_status"] == "eligible" else None,
                "priority_tier": effective_tier(row),
                "posted_at": row["posted_at"],
                "reason_summary": row["reason_summary"],
            }
            for row in rows
        ]


def truncate_description(text: str) -> tuple[str, bool]:
    """Cap a description at the contract limits; report whether it was cut.

    Cutting on a UTF-8 boundary first avoids splitting a multi-byte character.
    """
    truncated = False
    if len(text) > DESCRIPTION_MAX_CHARS:
        text = text[:DESCRIPTION_MAX_CHARS]
        truncated = True
    encoded = text.encode("utf-8")
    if len(encoded) > DESCRIPTION_MAX_BYTES:
        text = encoded[:DESCRIPTION_MAX_BYTES].decode("utf-8", "ignore")
        truncated = True
    return text, truncated


def recommendation(eligibility_status: str, fit: dict | None) -> str:
    """Derived from eligibility + fit only. Thresholds stay `OPEN`; this mapping
    uses the documented verdict bands instead of inventing new cut-offs."""
    if eligibility_status == "needs_review":
        return "needs_review"
    if eligibility_status == "ineligible":
        return "ineligible"
    verdict = (fit or {}).get("verdict")
    if verdict == "strong":
        return "apply_now"
    if verdict == "moderate":
        return "consider"
    return "stretch"


def _eligibility_payload(row: dict) -> dict:
    return {
        "assessment_id": row["assessment_id"],
        "job_id": row["job_id"],
        "job_posting_version_id": row["job_posting_version_id"],
        "profile_version_id": row["profile_version_id"],
        "status": row["status"],
        "checks": json.loads(row["checks_json"]),
        "confidence": row["confidence"],
        "reason_summary": row["reason_summary"],
        "status_outdated": bool(row["status_outdated"]),
        "outdated_reason": row["outdated_reason"],
        "computed_at": row["computed_at"],
    }


def _fit_payload(row: dict) -> dict:
    return {
        "assessment_id": row["assessment_id"],
        "job_posting_version_id": row["job_posting_version_id"],
        "profile_version_id": row["profile_version_id"],
        "fit_score": row["fit_score"],
        "verdict": row["verdict"],
        "confidence": row["confidence"],
        "components": json.loads(row["components_json"]),
        "gaps": json.loads(row["gaps_json"]),
        "status_outdated": bool(row["status_outdated"]),
        "outdated_reason": row["outdated_reason"],
        "computed_at": row["computed_at"],
    }


def _ranking_payload(row: dict) -> dict:
    return {
        "ranking_run_id": row["ranking_run_id"],
        "profile_version_id": row["profile_version_id"],
        "tie_window": row["tie_window"],
        "primary": row["primary_key"],
        "tie_breaker": json.loads(row["tie_breaker_json"]),
        "sections": json.loads(row["sections_json"]),
        "counts": json.loads(row["counts_json"]),
        "computed_at": row["computed_at"],
    }


def _match_row(row: dict, profile_version_id: str) -> dict:
    location = json.loads(row["location_json"] or "{}")
    return {
        "job": {
            "job_id": row["job_id"],
            "job_posting_version_id": row["latest_version_id"],
            "source_id": row["source_id"],
            "company": row["company"],
            "title": row["title"],
            "location": location,
            "work_mode": row["work_mode"],
            "employment_type": row["employment_type"],
            "seniority": row["seniority"],
            "market": row["market"],
            "posted_at": row["posted_at"],
            "fetched_at": row["fetched_at"],
            "canonical_url": row["canonical_url"],
            "apply_url": row["apply_url"],
            "apply_url_status": "available" if row["apply_url"] else "unavailable",
            "priority_tier": effective_tier(row),
            "priority_reason": row["priority_reason"],
            "priority_confidence": row["priority_confidence"],
            "duplicate_of": row["duplicate_of"],
            "completeness": _completeness(row),
        },
        "profile_version_id": profile_version_id,
        "eligibility": {
            "assessment_id": row["eligibility_assessment_id"],
            "status": row["eligibility_status"],
            "confidence": row["eligibility_confidence"],
            "reason_summary": row["reason_summary"],
        },
        "fit": (
            {
                "assessment_id": row["fit_assessment_id"],
                "fit_score": row["fit_score"],
                "verdict": row["verdict"],
                "confidence": row["fit_confidence"],
            }
            if row["fit_score"] is not None
            else None
        ),
        "recommendation": recommendation(
            row["eligibility_status"],
            {"verdict": row["verdict"]} if row["fit_score"] is not None else None,
        ),
        "status_outdated": bool(row["eligibility_outdated"]),
        "application_id": row.get("application_id"),
    }


def _completeness(row: dict) -> dict:
    """Stored completeness, with the current fetch state as the fallback."""
    stored = json.loads(row.get("completeness_json") or "{}")
    return {
        "missing_fields": list(stored.get("missing_fields") or []),
        "fetched_at": row["fetched_at"],
        "stale": bool(row.get("stale") or stored.get("stale")),
    }
