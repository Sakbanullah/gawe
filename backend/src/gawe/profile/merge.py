"""Conflict detection between a new extraction and the active profile.

Conflicts are recorded, never overwritten. Matching uses normalised keys:
experience = company + title + start year, education = institution + degree,
skills = canonical slug. Personal fields conflict when both sides are non-null
and differ after normalisation.
"""

from __future__ import annotations

import re
import unicodedata


def norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").lower()
    text = re.sub(r"\b(pt|cv|tbk|persero)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def slug(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(value)).strip("-")


def _year(value: str | None) -> str:
    return (value or "")[:4]


def _evidence(item: dict) -> list[str]:
    refs = list(item.get("evidence") or [])
    for bullet in item.get("bullets") or []:
        refs.extend(bullet.get("evidence") or [])
    return refs[:100]


def _candidate(value: object, evidence: list[str]) -> dict:
    return {"value": value, "evidence": evidence}


def detect_conflicts(new: dict, active: dict | None) -> list[dict]:
    if not active:
        return []
    conflicts: list[dict] = []
    counter = 0

    def add(path: str, old: dict, new_item: dict) -> None:
        nonlocal counter
        counter += 1
        conflicts.append(
            {
                "conflict_id": f"cfl_{counter}",
                "path": path[:300],
                "candidates": [_candidate(old, _evidence(old)), _candidate(new_item, _evidence(new_item))],
            }
        )

    for field in ("full_name", "email", "phone", "location"):
        old_value = (active.get("personal") or {}).get(field)
        new_value = (new.get("personal") or {}).get(field)
        if old_value and new_value and norm(old_value) != norm(new_value):
            add(f"personal.{field}", {"value": old_value}, {"value": new_value})

    _match(
        new.get("experience") or [],
        active.get("experience") or [],
        lambda item: f"{norm(item.get('company'))}|{norm(item.get('title'))}|{_year(item.get('start'))}",
        "experience",
        add,
        compare=("end", "location", "title"),
    )
    _match(
        new.get("education") or [],
        active.get("education") or [],
        lambda item: f"{norm(item.get('institution'))}|{norm(item.get('degree'))}",
        "education",
        add,
        compare=("start", "end", "field"),
    )
    _match(
        new.get("skills") or [],
        active.get("skills") or [],
        lambda item: slug(item.get("name")),
        "skills",
        add,
        compare=("proficiency",),
    )
    return conflicts


def _match(new_items, old_items, key, collection, add, compare) -> None:
    old_by_key = {key(item): item for item in old_items if key(item)}
    for item in new_items:
        old = old_by_key.get(key(item))
        if old is None:
            continue
        differing = [field for field in compare if (old.get(field) or None) != (item.get(field) or None)]
        if differing:
            add(f"{collection}.{item.get('id')}", old, item)
