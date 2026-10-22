"""Opt-in background scheduler for discovery runs.

The v1 run is synchronous inside the request (API-CONTRACTS §4.3), which is fine
for a user-triggered run and useless for "check the boards every few hours". This
module adds the missing half without moving the run: one thread wakes up on an
interval, asks the registry which sources are due, and runs them through the same
`DiscoveryService.start_run`.

Deliberate limits:

- Off by default. A local single-user app must not start fetching boards on its
  own the first time it is launched; the operator enables it in `config.toml`.
- The thread opens its own connection. The request-scoped connection is never
  shared with it.
- One run at a time. The discovery lock already serialises runs, and a scheduled
  run that loses the lock simply waits for the next tick.
"""

from __future__ import annotations

import logging
import threading

from ..config import Config
from ..db import repo
from ..jobs.sources.registry import SourceRegistry
from .discovery_service import DiscoveryService
from .tasks import TaskStore

logger = logging.getLogger(__name__)

MIN_INTERVAL_S = 60


class DiscoveryScheduler:
    def __init__(self, config: Config, *, stop: threading.Event | None = None) -> None:
        self._config = config
        self._interval = max(MIN_INTERVAL_S, config.discovery.schedule_interval_seconds)
        self._stop = stop or threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._loop, name="gawe-discovery-scheduler", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - a scheduler tick must never die
                logger.exception("scheduled discovery tick failed")
            self._stop.wait(self._interval)

    def tick(self) -> dict | None:
        """Run every due source once; returns the run summary, or None."""
        connection = repo.connect(self._config.database)
        try:
            from ..profile.store import ProfileStore

            profiles = ProfileStore(connection)
            try:
                profiles.require_confirmed()
            except Exception:  # noqa: BLE001 - no confirmed profile means no run
                return None
            due = SourceRegistry(connection).due()
            if not due:
                return None
            service = DiscoveryService(
                connection,
                profiles,
                TaskStore(connection),
                max_workers=self._config.discovery.max_workers,
                max_run_seconds=self._config.discovery.max_run_seconds,
            )
            try:
                run = service.start_run(source_ids=[item["source_id"] for item in due])
            except Exception:  # noqa: BLE001 - gate or lock; the next tick retries
                logger.info("scheduled discovery skipped", exc_info=True)
                return None
            return {"run_id": run["run_id"], "sources": len(due)}
        finally:
            connection.close()
