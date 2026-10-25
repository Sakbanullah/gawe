"""Orphaned tasks must not lock a workspace forever.

A `processing` row whose owner died stays in the database after a restart. Two
things must hold: startup fails those rows, and a document action is not blocked
by an unrelated task type.
"""

from __future__ import annotations

from gawe.services.tasks import TaskStore


def _store(connection) -> TaskStore:
    return TaskStore(connection)


def _insert(connection, task_id: str, kind: str, updated_at: str) -> None:
    with connection:
        connection.execute(
            "INSERT INTO task (task_id, type, status, application_id, progress_json, "
            "result_json, error_json, created_at, updated_at, finished_at, attempt, "
            "retried_from_task_id) VALUES (?, ?, 'processing', 'app_x', '{}', NULL, NULL, "
            "?, ?, NULL, 1, NULL)",
            (task_id, kind, updated_at, updated_at),
        )


def test_reap_stale_covers_every_task_type(connection) -> None:
    app_connection = connection
    _insert(app_connection, "tsk_old_analysis", "analysis", "2020-01-01T00:00:00Z")
    _insert(app_connection, "tsk_old_discovery", "discovery", "2020-01-01T00:00:00Z")
    _insert(app_connection, "tsk_old_generation", "document_generation", "2020-01-01T00:00:00Z")

    reaped = _store(app_connection).reap_stale(exclude=set(), older_than_s=0)

    assert set(reaped) == {"tsk_old_analysis", "tsk_old_discovery", "tsk_old_generation"}
    rows = app_connection.execute(
        "SELECT task_id, status, error_json FROM task WHERE status = 'processing'"
    ).fetchall()
    assert rows == []


def test_reap_stale_can_be_limited_to_one_type(connection) -> None:
    app_connection = connection
    _insert(app_connection, "tsk_a", "analysis", "2020-01-01T00:00:00Z")
    _insert(app_connection, "tsk_d", "discovery", "2020-01-01T00:00:00Z")

    reaped = _store(app_connection).reap_stale(
        exclude=set(), older_than_s=0, types=("discovery",)
    )

    assert reaped == ["tsk_d"]
    left = app_connection.execute(
        "SELECT task_id FROM task WHERE status = 'processing'"
    ).fetchall()
    assert [row["task_id"] for row in left] == ["tsk_a"]


def test_reap_stale_skips_live_tasks(connection) -> None:
    from gawe.services.tasks import now_iso

    app_connection = connection
    _insert(app_connection, "tsk_live", "analysis", now_iso())

    reaped = _store(app_connection).reap_stale(exclude=set(), older_than_s=600)

    assert reaped == []
