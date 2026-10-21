"""Overview summary. All values are computed here, never by the frontend."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ...services.assessment_service import AssessmentService
from ..deps import consent_store, discovery_service, master_cv_store, profile_store, task_store

router = APIRouter(prefix="/api")


def _next_action(
    master_cv: dict | None,
    profile: dict | None,
    provider_configured: bool,
    consent_required: bool,
) -> dict:
    if master_cv is None:
        return {
            "code": "upload_master_cv",
            "label": "Unggah Master CV",
            "target_route": "/master-cv",
            "reason": None,
        }
    if not provider_configured:
        return {
            "code": "configure_provider",
            "label": "Konfigurasi provider",
            "target_route": "/settings",
            "reason": "Provider LLM belum dikonfigurasi.",
        }
    if consent_required:
        return {
            "code": "grant_consent",
            "label": "Berikan consent cloud",
            "target_route": "/settings",
            "reason": "Data kandidat hanya dikirim setelah consent.",
        }
    if profile is None:
        return {
            "code": "review_profile",
            "label": "Ekstrak dan review profil",
            "target_route": "/master-cv",
            "reason": "Master CV belum diekstrak menjadi profil.",
        }
    if profile["status"] == "confirmed" and profile["active"]:
        return {
            "code": "run_discovery",
            "label": "Mulai pencarian",
            "target_route": "/discovery",
            "reason": None,
        }
    return {
        "code": "confirm_profile",
        "label": "Konfirmasi profil",
        "target_route": "/master-cv",
        "reason": "Discovery terkunci sampai profil dikonfirmasi.",
    }


@router.get("/overview")
def get_overview(request: Request) -> dict:
    config = request.app.state.config
    configured = bool(config.llm.active_provider and config.llm.providers)
    master_cv = master_cv_store(request).active()
    store = profile_store(request)
    active_profile = store.active()
    profile = active_profile or store.latest()
    consent_required = consent_store(request).status()["required"]
    discovery = discovery_service(request)
    runs, _ = discovery.list_runs(limit=5)
    active_task = task_store(request).active_discovery()
    counts = (
        AssessmentService(request.state.db, store).counts(profile["profile_version_id"])
        if profile is not None and profile["status"] == "confirmed" and profile["active"]
        else {"eligible": 0, "needs_review": 0, "ineligible": 0, "fit_computed": 0}
    )
    return {
        "master_cv": master_cv,
        "profile": {
            "profile_id": profile["profile_id"],
            "profile_version_id": profile["profile_version_id"],
            "master_cv_id": profile["master_cv_id"],
            "derived_from_profile_version_id": profile["derived_from_profile_version_id"],
            "version": profile["version"],
            "status": profile["status"],
            "active": profile["active"],
            "confirmed_at": profile["confirmed_at"],
            "created_at": profile["created_at"],
            "updated_at": profile["updated_at"],
        }
        if profile
        else None,
        "discovery": runs[0] if runs else None,
        "counts": {
            "eligible": counts["eligible"],
            "needs_review": counts["needs_review"],
            "ineligible": counts["ineligible"],
            "total_jobs": discovery.job_total(),
            "documents_pending_review": 0,
        },
        "next_action": _next_action(master_cv, profile, configured, consent_required),
        "consent_required": consent_required,
        "provider_configured": configured,
        "active_task_id": active_task["task_id"] if active_task else None,
        "recent_activity": [_activity_for(run) for run in runs],
    }


def _activity_for(run: dict) -> dict:
    counts = run["counts"]
    return {
        "event_id": run["run_id"],
        "occurred_at": run["started_at"],
        "workflow": "discovery",
        "stage": "fetch",
        "status_context": {"kind": "task", "value": run["status"]},
        "summary": (
            f"Discovery {run['status']}: {counts.get('new_jobs', 0)} lowongan baru "
            f"dari {len(run['sources'])} sumber."
        ),
        "application_id": None,
        "job_id": None,
        "task_id": run["task_id"],
    }
