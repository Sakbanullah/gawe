"""`/api/matches`: ranked job list, side-panel detail, and tier correction.

Order and every authoritative value come from the backend: the stored ranking
run for `sort=ranking`, and the stored assessments for eligibility/fit. Filters
and display sorts never change a stored score (API-CONTRACTS §4.8).
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ...jobs.priority import TIERS
from ...master_cv.store import MasterCvError
from ...profile.store import ProfileStore
from ...services.assessment_service import AssessmentService
from ..deps import profile_store
from ..errors import ApiError

router = APIRouter(prefix="/api/matches")

SORTS = ("ranking", "fit_score_desc", "posted_at_desc", "priority_tier")
TIER_ORDER = {"P1": 1, "P2": 2, "P3": 3, "P4": 4, "unclassified": 5}
ELIGIBILITY = ("all", "eligible", "needs_review", "ineligible")
TIE_BREAKER = ["priority_tier", "posted_at_desc", "job_id"]
CURSOR_VERSION = 1


class TierOverrideRequest(BaseModel):
    tier: str | None = Field(default=None)
    reason: str | None = Field(default=None, max_length=1000)


def _service(request: Request) -> AssessmentService:
    return AssessmentService(request.state.db, profile_store(request))


def _confirmed(request: Request) -> dict:
    try:
        return ProfileStore(request.state.db).require_confirmed()
    except MasterCvError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message, stage="eligibility") from exc


def _bad_request(field: str, message: str) -> ApiError:
    return ApiError(
        400,
        "validation_failed",
        message,
        stage="validation",
        details=[{"field": field, "code": "out_of_range", "message": message}],
    )


@router.get("")
def list_matches(
    request: Request,
    limit: int = 50,
    cursor: str | None = None,
    eligibility: str = "all",
    q: str | None = None,
    tier: str | None = None,
    source_id: str | None = None,
    market: str | None = None,
    work_mode: str | None = None,
    min_fit_score: int = 0,
    sort: str = "ranking",
) -> dict:
    if not 1 <= limit <= 200:
        raise _bad_request("limit", "limit harus 1-200.")
    if eligibility not in ELIGIBILITY:
        raise _bad_request("eligibility", "Nilai eligibility tidak dikenal.")
    if sort not in SORTS:
        raise _bad_request("sort", "Nilai sort tidak dikenal.")
    if tier is not None and tier not in TIER_ORDER:
        raise _bad_request("tier", "Nilai tier tidak dikenal.")
    if not 0 <= min_fit_score <= 100:
        raise _bad_request("min_fit_score", "min_fit_score harus 0-100.")
    if q is not None and len(q) > 200:
        raise _bad_request("q", "q maksimum 200 karakter.")

    profile = _confirmed(request)
    service = _service(request)
    items = service.matches(profile["profile_version_id"])
    counts = service.counts(profile["profile_version_id"])
    ranking = service.latest_ranking(profile["profile_version_id"])
    ranking_run_id = ranking["ranking_run_id"] if ranking else None

    items = [item for item in items if _keep(item, eligibility, q, tier, source_id, market, work_mode)]
    hidden = 0
    if min_fit_score:
        kept = [
            item
            for item in items
            if item["fit"] is None or item["fit"]["fit_score"] >= min_fit_score
        ]
        hidden = len(items) - len(kept)
        items = kept

    ordered = _order(items, sort, ranking)
    start = 0
    if cursor:
        key = _decode_cursor(cursor, sort, ranking_run_id)
        start = _offset_after(ordered, sort, ranking, key)
    page = ordered[start : start + limit]
    has_more = start + limit < len(ordered)
    next_cursor = (
        _encode_cursor(_sort_key(page[-1], sort, ranking), sort, ranking_run_id)
        if has_more and page
        else None
    )
    return {
        "items": page,
        "page": {"limit": limit, "next_cursor": next_cursor, "has_more": has_more},
        "ranking": {
            "ranking_run_id": ranking_run_id,
            "sort": sort,
            "primary": "fit_score_desc",
            "tie_breaker": ranking["tie_breaker"] if ranking else TIE_BREAKER,
            "tie_window": ranking["tie_window"] if ranking else 0,
        },
        "counts": {
            "eligible": counts["eligible"],
            "needs_review": counts["needs_review"],
            "ineligible": counts["ineligible"],
            "hidden_by_min_fit_score": hidden,
        },
    }


@router.get("/{job_id}")
def get_match(request: Request, job_id: str) -> dict:
    profile = _confirmed(request)
    detail = _service(request).detail(job_id, profile["profile_version_id"])
    if detail is None:
        raise ApiError(
            404, "not_found", "Job tidak ditemukan atau belum dianalisis.", stage="eligibility"
        )
    return detail


@router.patch("/{job_id}/tier")
def override_tier(request: Request, job_id: str, body: TierOverrideRequest) -> dict:
    """Store a user tier correction. It never changes the stored fit score.

    The next ranking run reads the override; the current ranking run is left as
    it was computed (API-CONTRACTS §4.8).
    """
    if body.tier is not None and body.tier not in TIERS:
        raise _bad_request("tier", "Nilai tier tidak dikenal.")
    if body.tier is not None and not (body.reason or "").strip():
        raise ApiError(
            400,
            "validation_failed",
            "Alasan wajib diisi saat mengubah tier.",
            stage="validation",
            details=[{"field": "reason", "code": "required", "message": "Alasan wajib diisi."}],
        )
    profile = _confirmed(request)
    service = _service(request)
    if service.override_tier(job_id, body.tier, (body.reason or "").strip() or None) is None:
        raise ApiError(404, "not_found", "Job tidak ditemukan.", stage="eligibility")
    row = service.match(job_id, profile["profile_version_id"])
    if row is None:
        raise ApiError(
            404, "not_found", "Job tidak ditemukan atau belum dianalisis.", stage="eligibility"
        )
    return row


def _keep(item, eligibility, q, tier, source_id, market, work_mode) -> bool:
    job = item["job"]
    if eligibility != "all" and item["eligibility"]["status"] != eligibility:
        return False
    if tier is not None and job["priority_tier"] != tier:
        return False
    if source_id is not None and job["source_id"] != source_id:
        return False
    if market is not None and job["market"] != market:
        return False
    if work_mode is not None and job["work_mode"] != work_mode:
        return False
    if q:
        haystack = " ".join(
            (job["title"], job["company"], (job["location"] or {}).get("raw") or "")
        ).lower()
        if q.lower() not in haystack:
            return False
    return True


def _order(items: list[dict], sort: str, ranking: dict | None) -> list[dict]:
    return sorted(items, key=lambda item: _sort_key(item, sort, ranking))


def _sort_key(item: dict, sort: str, ranking: dict | None = None) -> tuple:
    """Ascending tuple whose first element is the primary sort key.

    The tuple is the cursor key as well, so paging never depends on an offset.
    """
    job = item["job"]
    if sort == "ranking" and ranking is not None:
        positions = {
            entry["job_id"]: entry["rank"] for entry in ranking["sections"]["eligible"]
        }
        return (positions.get(job["job_id"], len(positions) + 1), job["job_id"])
    if sort == "ranking":
        return (TIER_ORDER.get(job["priority_tier"], 5), job["job_id"])
    if sort == "fit_score_desc":
        return (-(item["fit"]["fit_score"] if item["fit"] else -1), job["job_id"])
    if sort == "posted_at_desc":
        return (-_epoch(job["posted_at"]), job["job_id"])
    return (TIER_ORDER.get(job["priority_tier"], 5), job["job_id"])


def _epoch(value: str | None) -> float:
    """Unix seconds for an ISO timestamp; 0 for a missing one (sorts last)."""
    if not value:
        return 0.0
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _offset_after(
    ordered: list[dict], sort: str, ranking: dict | None, key: tuple
) -> int:
    """Index of the first item whose key is strictly after the cursor key."""
    for index, item in enumerate(ordered):
        if _sort_key(item, sort, ranking) > key:
            return index
    return len(ordered)


def _encode_cursor(key: tuple, sort: str, ranking_run_id: str | None) -> str:
    payload = {"v": CURSOR_VERSION, "s": sort, "r": ranking_run_id, "k": key[0], "i": key[1]}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str, sort: str, ranking_run_id: str | None) -> tuple:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise _bad_request("cursor", "cursor tidak valid.") from None
    if not isinstance(payload, dict) or payload.get("v") != CURSOR_VERSION:
        raise _bad_request("cursor", "cursor tidak valid.")
    if payload.get("s") != sort:
        raise _bad_request("cursor", "cursor bukan untuk sort ini.")
    if payload.get("r") != ranking_run_id:
        raise _bad_request(
            "cursor", "cursor berasal dari ranking run lain; mulai dari halaman pertama."
        )
    key = payload.get("k")
    job_id = payload.get("i")
    if not isinstance(key, (int, float, str)) or not isinstance(job_id, str):
        raise _bad_request("cursor", "cursor tidak valid.")
    return (key, job_id)
