"""Helpers for the approved-plan gate in document tests.

Generation now requires an approved adjustment plan (AGENTS.md §4A.5), so every
document test has to create and approve one first. Keeping the calls here avoids
copying the same two requests into five test modules.
"""

from __future__ import annotations


def create_plan(client, csrf, application_id: str, language: str | None = None) -> dict:
    body: dict = {}
    if language is not None:
        body["language"] = language
    response = client.post(
        f"/api/applications/{application_id}/document-plan",
        headers=csrf,
        json=body,
    )
    assert response.status_code in (200, 201), response.json()
    return response.json()


def approve_plan(client, csrf, application_id: str, plan: dict) -> dict:
    response = client.post(
        f"/api/applications/{application_id}/document-plan/{plan['plan_id']}/approval",
        headers=csrf,
        json={"decision": "approved", "content_hash": plan["content_hash"]},
    )
    assert response.status_code == 200, response.json()
    return response.json()


def plan_and_approve(client, csrf, application_id: str, language: str | None = None) -> dict:
    return approve_plan(client, csrf, application_id, create_plan(client, csrf, application_id, language))
