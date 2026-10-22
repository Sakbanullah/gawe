"""Deterministic priority tier classification (PLAN.md §4.2, D15/D16).

Tier is a user preference attribute, never eligibility and never part of the
fit score. Classification uses structured metadata only: when the location and
work mode cannot support a tier, the result is ``unclassified`` instead of a
guess. Hybrid counts as onsite (D15). Remote counts as P2 only when the payload
says worldwide/anywhere or names Indonesia/APAC (D16).

A region named in the location field always wins over the word "anywhere" in
the description: "You can work from anywhere within those regions" restricts
the role, it does not open it. Reading the word without the sentence promoted
region-locked postings to P2.
"""

from __future__ import annotations

import re

from .normalize import location_key

TIERS = ("P1", "P2", "P3", "P4", "unclassified")
TIER_LABELS = {
    "P1": "Global onsite",
    "P2": "Global remote",
    "P3": "Indonesia remote",
    "P4": "Indonesia onsite",
    "unclassified": "Belum terklasifikasi",
}
SCOPES = ("indonesia", "worldwide", "region_locked", "unknown")
INDONESIA = re.compile(r"\bindonesia\b", re.IGNORECASE)
# APAC is included because it covers Indonesia; AMER and EMEA do not.
WORLDWIDE = re.compile(
    r"\b(worldwide|anywhere|global|globally|apac|asia[- ]pacific|asia)\b", re.IGNORECASE
)
# Prose that offers the whole world, as opposed to prose that mentions "global"
# in passing ("globally distributed team").
WORLDWIDE_TEXT = re.compile(
    r"\b(worldwide|anywhere in the world|any country|no location restriction|"
    r"open to candidates anywhere)\b",
    re.IGNORECASE,
)
# A trailing segment such as "Berlin, Germany" names a country; "Berlin" alone
# does not prove the role is outside Indonesia.
FOREIGN_LOCATION = re.compile(r",\s*[A-Za-z][A-Za-z .'-]{2,}$")
# Regions and countries that cannot hire a candidate based in Indonesia.
GEO_LOCK = re.compile(
    r"\b("
    r"amer|emea|latam|dach|benelux|nordics|"
    r"north america|south america|central america|"
    r"europe|european union|eu|"
    r"united states|usa|u\.s\.|us|united kingdom|uk|canada|"
    r"australia|new zealand|india|japan|singapore|"
    r"germany|france|netherlands|spain|poland|portugal|italy|ireland|sweden|"
    r"brazil|mexico|argentina|colombia|"
    r"middle east|africa"
    r")\b",
    re.IGNORECASE,
)
# A restriction stated in prose, where the location field names no place. Each
# alternative needs the restriction word itself, so marketing copy does not
# qualify.
DESCRIPTION_LOCK = re.compile(
    r"within (?:those|this|these) regions?"
    r"|open to candidates based in"
    r"|based in (?:the )?(?:us|usa|u\.s\.|united states|uk|united kingdom|canada|"
    r"europe|north america|south america|emea|amer|apac|australia|singapore|india|japan)"
    r"|authori[sz]\w+ to work in"
    r"|right to work in"
    r"|must (?:be )?(?:located|reside|live) in"
    r"|(?:us|emea|amer|eu|uk)[- ]only",
    re.IGNORECASE,
)


# A region named in the title belongs to the posting, not to marketing prose.
# "Support Engineer (EMEA - Weekends)" is an EMEA role even when the location
# field says "Global"; without this check it was promoted to global remote.
# Bare "us" and "eu" are left out: they read as ordinary words in a title, and
# the location field already carries those countries when they apply.
TITLE_REGION = re.compile(
    r"\b(amer|emea|latam|dach|benelux|nordics|"
    r"north america|south america|europe|africa|middle east|"
    r"united states|usa|united kingdom|uk|canada|australia|"
    r"india|japan|singapore|germany|france|netherlands)\b",
    re.IGNORECASE,
)
APAC = re.compile(r"\b(apac|asia[- ]pacific|asia)\b", re.IGNORECASE)
# Narrowest first: Southeast Asia sits inside APAC, which sits inside Asia. The
# order of this tuple is the answer, not an accident, so a location is reported
# against the tightest region it names.
REGIONS = (
    ("indonesia", INDONESIA),
    (
        "sea",
        re.compile(
            r"\b(southeast asia|south-east asia|asean|singapore|malaysia|thailand|"
            r"vietnam|philippines|brunei|cambodia|laos|myanmar)\b",
            re.IGNORECASE,
        ),
    ),
    ("oceania", re.compile(r"\b(oceania|australia|new zealand)\b", re.IGNORECASE)),
    ("apac", APAC),
    (
        "amer",
        re.compile(
            r"\b(amer|north america|south america|central america|latam|"
            r"united states|usa|u\.s\.|us|canada|mexico|brazil)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "emea",
        re.compile(
            r"\b(emea|europe|european union|eu|middle east|africa|dach|benelux|"
            r"nordics|united kingdom|uk|germany|france|netherlands|spain|poland|"
            r"portugal|italy|ireland|sweden)\b",
            re.IGNORECASE,
        ),
    ),
)
REGION_LABELS = {
    "indonesia": "Indonesia",
    "sea": "Asia Tenggara",
    "oceania": "Australia/Selandia Baru",
    "apac": "APAC",
    "amer": "Amerika",
    "emea": "EMEA",
}
# Regions a candidate based in Indonesia can reach by relocating without first
# clearing a work-permit queue. Kept narrow on purpose: the Americas and EMEA
# need a permit, which is a separate requirement, not a distance question.
RELOCATION_REACHABLE = frozenset({"sea", "oceania"})


def _title_locks_region(title: str | None) -> bool:
    """True when the title names only regions that exclude Indonesia.

    "Platform Security Engineer (AMER/APAC)" stays open because APAC covers
    Indonesia; "Support Engineer (EMEA)" does not.
    """
    text = title or ""
    if APAC.search(text):
        return False
    return bool(TITLE_REGION.search(text))


def geo_scope(
    location_raw: str | None,
    description_text: str | None = None,
    title: str | None = None,
) -> str:
    """Return ``indonesia | worldwide | region_locked | unknown`` for one posting.

    A place named in the location field outranks the word "anywhere" in the
    description, because "you can work from anywhere within those regions" is a
    restriction. The title and the description only decide when the location
    names no place.
    """
    location = (location_raw or "").strip()
    if not location:
        return "unknown"
    if INDONESIA.search(location):
        return "indonesia"
    if GEO_LOCK.search(location):
        return "region_locked"
    if WORLDWIDE.search(location):
        return "region_locked" if _title_locks_region(title) else "worldwide"
    # A place the region list does not name is still a place, and a place that
    # is not Indonesia cannot be worked from here.
    if location_key(location) != "anywhere":
        return "region_locked"
    if _title_locks_region(title):
        return "region_locked"
    text = description_text or ""
    if DESCRIPTION_LOCK.search(text):
        return "region_locked"
    if WORLDWIDE_TEXT.search(text):
        return "worldwide"
    return "unknown"


MARKET_BY_SCOPE = {"indonesia": "indonesia", "worldwide": "global"}


def market_from_scope(
    location_raw: str | None,
    description_text: str | None = None,
    title: str | None = None,
) -> str:
    """Coarse display market, derived from the geo scope.

    The old rule looked for the literal word "indonesia" in the location field,
    so all 102 stored jobs were ``unknown`` and the Pasar filter on Job Matches
    never removed a row. ``market`` has only three values, so a region-locked
    posting is not a market: it stays ``unknown``.
    """
    return MARKET_BY_SCOPE.get(
        geo_scope(location_raw, description_text, title), "unknown"
    )


def geo_region(location_raw: str | None, title: str | None = None) -> str | None:
    """Return the narrowest named region, or ``None`` when no region is named."""
    haystack = f"{location_raw or ''} {title or ''}"
    for name, pattern in REGIONS:
        if pattern.search(haystack):
            return name
    return None


def reachable_by_relocation(location_raw: str | None, title: str | None = None) -> bool:
    """True when the posting sits in a region a candidate could relocate to."""
    return geo_region(location_raw, title) in RELOCATION_REACHABLE


def classify(
    location_raw: str | None,
    work_mode: str | None,
    description_text: str | None = None,
    title: str | None = None,
) -> dict:
    """Return ``{tier, reason, confidence}`` for one job."""
    location = (location_raw or "").strip()
    mode = (work_mode or "unknown").lower()

    if not location:
        return _result("unclassified", "Lokasi tidak dicantumkan.", "low")
    if mode == "unknown":
        return _result(
            "unclassified", "Mode kerja tidak dapat ditentukan dari data sumber.", "low"
        )

    scope = geo_scope(location, description_text, title)

    if scope == "indonesia":
        if mode == "remote":
            return _result("P3", f"Remote berbasis Indonesia: {location}.", "high")
        return _result("P4", f"Onsite/hybrid di Indonesia: {location}.", "high")

    if mode == "remote":
        if scope == "worldwide":
            return _result(
                "P2",
                f"Remote tanpa batas negara yang jelas: {location}.",
                "medium",
            )
        if scope == "region_locked":
            return _result(
                "unclassified",
                f"Remote terbatas pada region yang tidak mencakup Indonesia: {location}.",
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
