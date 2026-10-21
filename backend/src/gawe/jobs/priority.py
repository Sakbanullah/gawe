"""Deterministic priority tier classification (PLAN.md §4.2, D15/D16).

Tier is a user preference attribute, never eligibility and never part of the
fit score. Classification uses structured metadata only: when the location and
work mode cannot support a tier, the result is ``unclassified`` instead of a
guess. Hybrid counts as onsite (D15). Remote counts as P2 only when the payload
says worldwide/anywhere or names Indonesia/APAC (D16).
"""

from __future__ import annotations

import re

TIERS = ("P1", "P2", "P3", "P4", "unclassified")
TIER_LABELS = {
    "P1": "Global onsite",
    "P2": "Global remote",
    "P3": "Indonesia remote",
    "P4": "Indonesia onsite",
    "unclassified": "Belum terklasifikasi",
}
INDONESIA = re.compile(r"\bindonesia\b", re.IGNORECASE)
WORLDWIDE = re.compile(
    r"\b(worldwide|anywhere|global|globally|apac|asia[- ]pacific)\b", re.IGNORECASE
)
# A trailing segment such as "Berlin, Germany" names a country; "Berlin" alone
# does not prove the role is outside Indonesia.
FOREIGN_LOCATION = re.compile(r",\s*[A-Za-z][A-Za-z .'-]{2,}$")


def classify(
    location_raw: str | None, work_mode: str | None, description_text: str | None = None
) -> dict:
    """Return ``{tier, reason, confidence}`` for one job."""
    location = (location_raw or "").strip()
    mode = (work_mode or "unknown").lower()
    text = f"{location} {description_text or ''}"

    if not location:
        return _result("unclassified", "Lokasi tidak dicantumkan.", "low")
    if mode == "unknown":
        return _result(
            "unclassified", "Mode kerja tidak dapat ditentukan dari data sumber.", "low"
        )

    in_indonesia = bool(INDONESIA.search(location))
    if in_indonesia:
        if mode == "remote":
            return _result("P3", f"Remote berbasis Indonesia: {location}.", "high")
        return _result("P4", f"Onsite/hybrid di Indonesia: {location}.", "high")

    if mode == "remote":
        if WORLDWIDE.search(text):
            return _result(
                "P2",
                f"Remote tanpa batas negara yang jelas: {location}.",
                "medium",
            )
        return _result(
            "unclassified",
            f"Remote tanpa bukti menerima kandidat dari Indonesia: {location}.",
            "low",
        )

    if FOREIGN_LOCATION.search(location):
        return _result("P1", f"Onsite/hybrid di luar Indonesia: {location}.", "medium")
    return _result(
        "unclassified", f"Lokasi tanpa negara yang jelas: {location}.", "low"
    )


def effective_tier(record: dict) -> str:
    """A user override wins over the stored classification."""
    return record.get("priority_tier_override") or record.get("priority_tier") or "unclassified"


def _result(tier: str, reason: str, confidence: str) -> dict:
    return {"tier": tier, "reason": reason, "confidence": confidence}
