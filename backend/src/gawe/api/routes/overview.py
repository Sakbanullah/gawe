"""Overview summary. All values are computed here, never by the frontend."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..deps import consent_store, master_cv_store, profile_store

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
        "discovery": None,
        "counts": {
            "eligible": 0,
            "needs_review": 0,
            "ineligible": 0,
            "total_jobs": 0,
            "documents_pending_review": 0,
        },
        "next_action": _next_action(master_cv, profile, configured, consent_required),
        "consent_required": consent_required,
        "provider_configured": configured,
        "active_task_id": None,
        "recent_activity": [],
    }
