"""Apply user corrections by field path.

Corrections never rewrite an old version: the caller decides whether to edit a
draft or create a new derived draft. A conflict is resolved by sending
`conflicts.<conflict_id>` with the chosen value; the chosen value is written to
the conflict path and the conflict is removed.
"""

from __future__ import annotations

import copy
from typing import Any


class CorrectionError(Exception):
    def __init__(self, path: str, message: str) -> None:
        super().__init__(message)
        self.path = path
        self.message = message


def apply_corrections(
    content: dict, conflicts: list[dict], corrections: list[dict]
) -> tuple[dict, list[dict], list[tuple[str, Any, Any]]]:
    updated = copy.deepcopy(content)
    remaining = copy.deepcopy(conflicts)
    applied: list[tuple[str, Any, Any]] = []

    for correction in corrections:
        path = correction["path"]
        value = correction.get("value")
        if path.startswith("conflicts."):
            conflict_id = path.split(".", 1)[1]
            match = next((item for item in remaining if item["conflict_id"] == conflict_id), None)
            if match is None:
                raise CorrectionError(path, "Konflik tidak ditemukan.")
            old = _get(updated, match["path"])
            _set(updated, match["path"], value, path)
            remaining = [item for item in remaining if item["conflict_id"] != conflict_id]
            applied.append((match["path"], old, value))
            continue
        old = _get(updated, path)
        _set(updated, path, value, path)
        applied.append((path, old, value))

    return updated, remaining, applied


def _segments(path: str) -> list[str]:
    return [segment for segment in path.split(".") if segment]


def _resolve(container: Any, segment: str, path: str) -> Any:
    if isinstance(container, dict):
        if segment not in container:
            raise CorrectionError(path, f"Field '{path}' tidak ditemukan.")
        return container[segment]
    if isinstance(container, list):
        if segment.isdigit():
            index = int(segment)
            if index >= len(container):
                raise CorrectionError(path, f"Field '{path}' tidak ditemukan.")
            return container[index]
        for item in container:
            if isinstance(item, dict) and item.get("id") == segment:
                return item
        raise CorrectionError(path, f"Field '{path}' tidak ditemukan.")
    raise CorrectionError(path, f"Field '{path}' tidak ditemukan.")


def _get(content: dict, path: str) -> Any:
    current: Any = content
    for segment in _segments(path):
        current = _resolve(current, segment, path)
    return current


def _set(content: dict, path: str, value: Any, original_path: str) -> None:
    segments = _segments(path)
    if not segments:
        raise CorrectionError(original_path, "Path koreksi kosong.")
    current: Any = content
    for segment in segments[:-1]:
        current = _resolve(current, segment, original_path)
    last = segments[-1]
    if isinstance(current, dict):
        if last not in current:
            raise CorrectionError(original_path, f"Field '{original_path}' tidak ditemukan.")
        current[last] = value
        return
    if isinstance(current, list):
        if last.isdigit():
            index = int(last)
            if index >= len(current):
                raise CorrectionError(original_path, f"Field '{original_path}' tidak ditemukan.")
            current[index] = value
            return
        for item in current:
            if isinstance(item, dict) and item.get("id") == last:
                if not isinstance(value, dict):
                    raise CorrectionError(original_path, "Nilai item harus objek.")
                item.clear()
                item.update(value)
                return
        raise CorrectionError(original_path, f"Field '{original_path}' tidak ditemukan.")
    raise CorrectionError(original_path, f"Field '{original_path}' tidak ditemukan.")
